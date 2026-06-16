"""交易所 RunnerBroker 适配层测试（src/execution/exchange_runner_broker.py）。

FakeExchange 注入，离线覆盖下单归一化（filled/partial/timeout/rejected）、本地账本
统计、余额/持仓透传、检查点往返、漂移对账纯函数，不触网。
"""

import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

import pytest

from src.execution.broker import Order
from src.execution.exchange_broker import ExchangeBroker
from src.execution.exchange_execution import ExchangeExecutor
from src.execution.exchange_runner_broker import (
    ExchangeRunnerBroker, assess_position_drift,
)


class FakeExchange:
    """带精度/限额/成交可配 + 余额可配的交易所替身。"""

    def __init__(self, *, create_result=None, min_amount=0.0001, min_cost=5.0,
                 order_status=None, usdt_free=10000.0, base_free=1.0,
                 base="BTC"):
        self._create_result = create_result
        self._min_amount = min_amount
        self._min_cost = min_cost
        self._order_status = order_status
        self._usdt_free = usdt_free
        self._base_free = base_free
        self._base = base

    def amount_to_precision(self, symbol, amount):
        return f"{float(amount):.5f}"

    def price_to_precision(self, symbol, price):
        return f"{float(price):.2f}"

    def market(self, symbol):
        return {"limits": {"amount": {"min": self._min_amount},
                           "cost": {"min": self._min_cost}}}

    def create_order(self, symbol, type, side, amount, price):
        return self._create_result or {
            "id": "OID", "status": "closed",
            "average": 65000.0, "filled": float(f"{amount:.5f}"),
        }

    def fetch_order(self, order_id, symbol=None):
        return self._order_status

    def fetch_balance(self):
        return {"USDT": {"free": self._usdt_free},
                self._base: {"free": self._base_free}}


class _FakeClock:
    """每次调用前进 10s，确保超时循环必然退出且不真睡。"""
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        self.t += 10.0
        return self.t


def _adapter(commission=0.001, **fake_kw):
    fake = FakeExchange(**fake_kw)
    broker = ExchangeBroker(exchange=fake)
    executor = ExchangeExecutor(broker, _clock=_FakeClock(), _sleep=lambda s: None)
    return ExchangeRunnerBroker(executor, "BTC/USDT", commission=commission)


# ---- 基线快照 ----

class TestBaseline:
    def test_snapshots_initial_balance_and_position(self):
        a = _adapter(usdt_free=12345.0, base_free=2.0)
        assert a.initial_balance == 12345.0
        assert a.initial_position == 2.0

    def test_balance_position_passthrough(self):
        a = _adapter(usdt_free=999.0, base_free=0.5)
        assert a.get_balance() == 999.0
        assert a.get_position("BTC/USDT") == 0.5


# ---- 下单归一化 ----

class TestPlaceOrder:
    def test_filled_records_ledger_and_returns_filled(self):
        a = _adapter()
        res = a.place_order(Order("BTC/USDT", "buy", 0.01, 65000.0, "market"),
                            timestamp="t0")
        assert res.status == "filled"
        assert res.filled_amount == pytest.approx(0.01, abs=1e-6)
        hist = a.get_trade_history()
        assert len(hist) == 1
        assert hist[0]["side"] == "buy"
        assert hist[0]["price"] == 65000.0
        assert hist[0]["timestamp"] == "t0"

    def test_partial_normalized_to_filled_with_real_amount(self):
        # 请求 0.01 但只成 0.004（< 0.01*0.99）→ executor 判 partial
        a = _adapter(create_result={"id": "P1", "status": "closed",
                                    "average": 64000.0, "filled": 0.004})
        res = a.place_order(Order("BTC/USDT", "buy", 0.01, 64000.0, "market"))
        assert res.status == "filled"  # 归一化
        assert res.filled_amount == pytest.approx(0.004)
        assert len(a.get_trade_history()) == 1
        assert a.get_trade_history()[0]["amount"] == pytest.approx(0.004)

    def test_rejected_sizing_no_ledger(self):
        # 最小下单量 10 → 0.01 被 sizing 拒
        a = _adapter(min_amount=10.0)
        res = a.place_order(Order("BTC/USDT", "buy", 0.01, 65000.0, "market"))
        assert res.status == "rejected"
        assert a.get_trade_history() == []
        assert a._unconfirmed == []

    def test_timeout_tracks_unconfirmed_no_ledger(self):
        # 下单返回无成交价量 + 查单始终 open → executor 判 timeout
        a = _adapter(create_result={"id": "T1", "status": "open"},
                     order_status={"status": "open"})
        res = a.place_order(Order("BTC/USDT", "buy", 0.01, 65000.0, "market"))
        assert res.status == "timeout"
        assert a._unconfirmed == ["T1"]
        assert a.get_trade_history() == []
        assert a._errors == 1


class TestGuard:
    def test_guard_rejection_counts_error_no_ledger(self):
        from src.execution.order_guard import OrderRateGuard
        a = _adapter()
        # 单笔上限极小 → 必拒
        a.guard = OrderRateGuard(reference_capital=1.0, max_position_per_trade=0.0001)
        res = a.place_order(Order("BTC/USDT", "buy", 0.01, 65000.0, "market"),
                            timestamp="t0")
        assert res.status == "rejected"
        assert a.get_trade_history() == []  # 未触达交易所
        assert a._errors == 1

    def test_guard_records_on_fill(self):
        from src.execution.order_guard import OrderRateGuard
        a = _adapter()
        a.guard = OrderRateGuard(reference_capital=1e9, max_position_per_trade=1.0,
                                 min_trade_interval=0, max_trades_per_day=100)
        a.place_order(Order("BTC/USDT", "buy", 0.01, 65000.0, "market"),
                      timestamp="2024-01-01 00:00")
        assert a.guard._count == 1  # 成交后登记


# ---- 统计 ----

class TestStatistics:
    def test_statistics_shape_and_values(self):
        a = _adapter(commission=0.001, usdt_free=8000.0, base_free=1.5)
        a.place_order(Order("BTC/USDT", "buy", 0.01, 65000.0, "market"))
        stats = a.get_statistics()
        for k in ("initial_balance", "current_balance", "total_trades",
                  "total_commission", "total_slippage", "total_cost", "positions"):
            assert k in stats
        assert stats["total_trades"] == 1
        assert stats["total_slippage"] == 0.0
        # commission = filled_amount * price * rate
        assert stats["total_commission"] == pytest.approx(0.01 * 65000.0 * 0.001)
        assert stats["total_cost"] == stats["total_commission"]
        assert stats["positions"]["BTC/USDT"] == 1.5


# ---- 检查点往返 ----

class TestCheckpoint:
    def test_state_dict_load_state_roundtrip(self):
        a = _adapter()
        a.place_order(Order("BTC/USDT", "buy", 0.01, 65000.0, "market"),
                      timestamp="t0")
        st = a.state_dict()

        b = _adapter(usdt_free=1.0, base_free=0.0)  # 不同基线
        b.load_state(st)
        assert b.get_trade_history() == a.get_trade_history()
        assert b.initial_balance == a.initial_balance
        assert b.initial_position == a.initial_position
        assert b._unconfirmed == a._unconfirmed


# ---- 漂移对账纯函数 ----

class TestDrift:
    def test_within_tolerance_ok(self):
        # 交易所 1.0→1.01（+0.01），本地净 0.01 → 对得上
        ok, drift = assess_position_drift(1.01, 1.0, 0.01, abs_tol=1e-6, rel_tol=0.0)
        assert ok
        assert drift == pytest.approx(0.0, abs=1e-9)

    def test_beyond_tolerance_flags(self):
        # 交易所多了 0.5（如卡单后成交），本地只记 0.01 → 漂移
        ok, drift = assess_position_drift(1.5, 1.0, 0.01, abs_tol=1e-6, rel_tol=0.01)
        assert not ok
        assert drift == pytest.approx(0.49)

    def test_relative_tolerance_absorbs_small_diff(self):
        ok, _ = assess_position_drift(1.0105, 1.0, 0.01, abs_tol=0.0, rel_tol=0.1)
        assert ok  # |0.0105-0.01|=5e-4 <= 0.1*0.01=1e-3
