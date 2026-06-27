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
    ExchangeRunnerBroker, assess_position_drift, ExchangeUnavailable,
)


class FakeExchange:
    """带精度/限额/成交可配 + 余额可配的交易所替身。"""

    def __init__(self, *, create_result=None, min_amount=0.0001, min_cost=5.0,
                 order_status=None, usdt_free=10000.0, base_free=1.0,
                 base="BTC", balance_raises=None, cancel_result=True):
        self._create_result = create_result
        self._min_amount = min_amount
        self._min_cost = min_cost
        self._order_status = order_status
        self._usdt_free = usdt_free
        self._base_free = base_free
        self._base = base
        self._balance_raises = balance_raises
        self._cancel_result = cancel_result

    def amount_to_precision(self, symbol, amount):
        return f"{float(amount):.5f}"

    def price_to_precision(self, symbol, price):
        return f"{float(price):.2f}"

    def market(self, symbol):
        return {"limits": {"amount": {"min": self._min_amount},
                           "cost": {"min": self._min_cost}}}

    def create_order(self, symbol, type, side, amount, price=None, params=None):
        return self._create_result or {
            "id": "OID", "status": "closed",
            "average": 65000.0, "filled": float(f"{amount:.5f}"),
        }

    def fetch_order(self, order_id, symbol=None):
        return self._order_status

    def fetch_balance(self):
        if self._balance_raises is not None:
            raise self._balance_raises
        return {"USDT": {"free": self._usdt_free},
                self._base: {"free": self._base_free}}

    def cancel_order(self, order_id, symbol=None):
        """FakeExchange 撤单：cancel_result=True 成功；False 抛 OrderNotFound 模拟失败"""
        if not self._cancel_result:
            import ccxt
            raise ccxt.OrderNotFound(f"test mock: {order_id} not found")
        return True


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


# ---- CODE-007: 交易所不可达时构造抛清晰领域异常（不带坏基线续跑）----

class TestUnavailableExchange:
    def test_init_raises_exchange_unavailable_on_connect_failure(self):
        """交易所基线快照失败 → ExchangeUnavailable（而非原始 ccxt traceback）。"""
        with pytest.raises(ExchangeUnavailable) as exc:
            _adapter(balance_raises=ConnectionError("network down"))
        # 异常消息含 symbol 和原因，便于诊断
        assert "BTC/USDT" in str(exc.value)
        assert "network down" in str(exc.value)

    def test_exchange_unavailable_chains_original_cause(self):
        """保留原始异常 __cause__，不丢失底层栈信息。"""
        orig = ConnectionError("boom")
        with pytest.raises(ExchangeUnavailable) as exc:
            _adapter(balance_raises=orig)
        assert exc.value.__cause__ is orig


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
        # cancel_result=False 模拟撤单失败 → 入 _unconfirmed 对账兜底
        a = _adapter(create_result={"id": "T1", "status": "open"},
                     order_status={"status": "open"}, cancel_result=False)
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


# ============== 阶段3 路径统一：限价单跨 bar 挂单 ==============

class _ScriptedExchange(FakeExchange):
    """可编程交易所替身：支持挂单返回 open + fetch_order 动态状态 + cancel_order 记录。

    用于阶段3 限价单挂单/撮合/TTL撤单/重启对账测试。
    """

    def __init__(self, *, create_result=None, **kw):
        super().__init__(create_result=create_result, **kw)
        self._order_counter = 0
        self._order_states = {}  # order_id → status dict
        self.cancelled = []  # 记录被撤的 order_id

    def create_order(self, symbol, type, side, amount, price=None, params=None):
        self._order_counter += 1
        oid = f"LIM{self._order_counter}"
        # 默认挂单返回 open（限价单未立即成交）
        result = self._create_result or {
            "id": oid, "status": "open", "average": None, "filled": 0.0,
        }
        # 若 create_result 指定了 id，用它；否则用生成的 oid
        actual_oid = result.get("id", oid)
        self._order_states[actual_oid] = dict(result)
        return result

    def fetch_order(self, order_id, symbol=None):
        # 返回当前状态（可被 set_order_status 修改）
        return self._order_states.get(order_id, self._order_status)

    def set_order_status(self, order_id, status, average=None, filled=None):
        """测试用：修改订单状态（模拟交易所撮合）"""
        st = self._order_states.get(order_id)
        if st is None:
            st = {"id": order_id}
            self._order_states[order_id] = st
        st["status"] = status
        if average is not None:
            st["average"] = average
        if filled is not None:
            st["filled"] = filled
        st.setdefault("side", "buy")

    def cancel_order(self, order_id, symbol=None):
        self.cancelled.append(order_id)
        st = self._order_states.get(order_id)
        if st:
            st["status"] = "canceled"
        return True


def _scripted_adapter(**fake_kw):
    """构造带 _ScriptedExchange 的适配器（用于阶段3 挂单测试）。"""
    fake = _ScriptedExchange(**fake_kw)
    broker = ExchangeBroker(exchange=fake)
    executor = ExchangeExecutor(broker, _clock=_FakeClock(), _sleep=lambda s: None)
    return ExchangeRunnerBroker(executor, "BTC/USDT", commission=0.001), fake


class TestLimitOrderPending:
    """限价单挂单路径：place_order 返 pending，入 _pending_limits 队列。"""

    def test_limit_order_returns_pending_and_enters_queue(self):
        a, fake = _scripted_adapter()
        order = Order("BTC/USDT", "buy", 0.01, 64000.0, "limit",
                      limit_price=64000.0, client_order_id="cid-1")
        res = a.place_order(order, timestamp="2024-01-01 00:00")
        assert res.status == "pending"
        assert res.order_id is not None
        assert len(a._pending_limits) == 1
        assert a._pending_limits[0]["side"] == "buy"
        assert a._pending_limits[0]["limit_price"] == 64000.0
        assert a._pending_limits[0]["client_order_id"] == "cid-1"

    def test_pending_orders_property_reflects_queue(self):
        """pending_orders 属性让 runner 的 hasattr + if not broker.pending_orders 通过"""
        a, fake = _scripted_adapter()
        assert hasattr(a, "check_pending_orders")
        assert a.pending_orders == []  # 初始空
        order = Order("BTC/USDT", "buy", 0.01, 64000.0, "limit", limit_price=64000.0)
        a.place_order(order, timestamp="t0")
        assert len(a.pending_orders) == 1

    def test_get_order_status_returns_pending_record_with_tag(self):
        """get_order_status 返回挂单记录（含 side），runner 据此设置 _tag"""
        a, fake = _scripted_adapter()
        order = Order("BTC/USDT", "buy", 0.01, 64000.0, "limit", limit_price=64000.0)
        res = a.place_order(order, timestamp="t0")
        rec = a.get_order_status(res.order_id)
        assert rec is not None
        assert rec["side"] == "buy"
        assert rec["_tag"] is None  # 初始无 tag
        # runner 设置 tag（直接改返回的 dict 引用）
        rec["_tag"] = "grid_0"
        assert a.get_order_status(res.order_id)["_tag"] == "grid_0"

    def test_market_order_still_uses_place_and_confirm(self):
        """市价单不走挂单路径，仍走 place_and_confirm 同步确认"""
        a, fake = _scripted_adapter(create_result={
            "id": "M1", "status": "closed", "average": 65000.0, "filled": 0.01,
        })
        order = Order("BTC/USDT", "buy", 0.01, 65000.0, "market")
        res = a.place_order(order, timestamp="t0")
        assert res.status == "filled"
        assert len(a._pending_limits) == 0  # 市价单不入挂单队列


class TestCheckPendingOrders:
    """每 bar 撮合挂单队列：已成交回填账本、TTL 撤单、仍 open 保留。"""

    def test_filled_order_records_ledger_and_returns_result(self):
        """挂单成交 → check_pending_orders 返 OrderResult(filled) + 回填账本"""
        a, fake = _scripted_adapter()
        order = Order("BTC/USDT", "buy", 0.01, 64000.0, "limit", limit_price=64000.0)
        res = a.place_order(order, timestamp="t0")
        # 模拟交易所撮合成交
        fake.set_order_status(res.order_id, "closed", average=63900.0, filled=0.01)
        # 标记 tag（模拟 runner 行为）
        a.get_order_status(res.order_id)["_tag"] = "grid_0"

        results = a.check_pending_orders(bar_high=65000, bar_low=63800, timestamp="t1")
        assert len(results) == 1
        assert results[0].status == "filled"
        assert results[0].filled_price == 63900.0
        assert results[0].filled_amount == pytest.approx(0.01)
        # 账本已回填
        assert len(a.get_trade_history()) == 1
        assert a.get_trade_history()[0]["price"] == 63900.0
        # 挂单已移出队列
        assert len(a._pending_limits) == 0

    def test_open_order_kept_in_queue_with_bars_held_increment(self):
        """仍 open → bars_held += 1，保留队列"""
        a, fake = _scripted_adapter()
        order = Order("BTC/USDT", "buy", 0.01, 64000.0, "limit", limit_price=64000.0)
        res = a.place_order(order, timestamp="t0")
        # 状态仍 open（_ScriptedExchange.create_order 默认返 open）
        results = a.check_pending_orders(bar_high=65000, bar_low=64100, timestamp="t1")
        assert results == []  # 无成交
        assert len(a._pending_limits) == 1
        assert a._pending_limits[0]["bars_held"] == 1

    def test_ttl_expiry_cancels_order(self):
        """bars_held >= max_pending_bars → 撤单 + 移出队列"""
        a, fake = _scripted_adapter()
        order = Order("BTC/USDT", "buy", 0.01, 64000.0, "limit", limit_price=64000.0)
        res = a.place_order(order, timestamp="t0")
        # 模拟 6 bar 未成交（max_pending_bars=6）
        for i in range(6):
            a.check_pending_orders(bar_high=65000, bar_low=64100,
                                   timestamp=f"t{i}", max_pending_bars=6)
        # 第 6 次调用时 bars_held 达到 6 → 撤单
        assert len(a._pending_limits) == 0
        assert res.order_id in fake.cancelled

    def test_canceled_order_removed_from_queue(self):
        """交易所侧已撤单 → 移出队列（不记账）"""
        a, fake = _scripted_adapter()
        order = Order("BTC/USDT", "buy", 0.01, 64000.0, "limit", limit_price=64000.0)
        res = a.place_order(order, timestamp="t0")
        # 模拟交易所侧已撤单
        fake.set_order_status(res.order_id, "canceled")
        results = a.check_pending_orders(bar_high=65000, bar_low=64100, timestamp="t1")
        assert results == []
        assert len(a._pending_limits) == 0
        assert len(a.get_trade_history()) == 0  # 不记账

    def test_multiple_orders_partial_fill(self):
        """多笔挂单：部分成交 + 部分仍 open"""
        a, fake = _scripted_adapter()
        o1 = a.place_order(Order("BTC/USDT", "buy", 0.01, 64000.0, "limit", limit_price=64000.0), timestamp="t0")
        o2 = a.place_order(Order("BTC/USDT", "buy", 0.02, 63000.0, "limit", limit_price=63000.0), timestamp="t0")
        # o1 成交，o2 仍 open
        fake.set_order_status(o1.order_id, "closed", average=63900.0, filled=0.01)
        results = a.check_pending_orders(bar_high=65000, bar_low=63800, timestamp="t1")
        assert len(results) == 1
        assert results[0].order_id == o1.order_id
        assert len(a._pending_limits) == 1
        assert a._pending_limits[0]["order_id"] == o2.order_id


class TestPendingLimitsPersistence:
    """state_dict/load_state 持久化挂单队列 + 重启对账。"""

    def test_state_dict_includes_pending_limits(self):
        a, fake = _scripted_adapter()
        a.place_order(Order("BTC/USDT", "buy", 0.01, 64000.0, "limit", limit_price=64000.0), timestamp="t0")
        st = a.state_dict()
        assert "pending_limits" in st
        assert "pending_order_records" in st
        assert len(st["pending_limits"]) == 1

    def test_load_state_restores_pending_limits(self):
        a, fake = _scripted_adapter()
        a.place_order(Order("BTC/USDT", "buy", 0.01, 64000.0, "limit", limit_price=64000.0), timestamp="t0")
        st = a.state_dict()

        b, fake2 = _scripted_adapter()
        b.load_state(st)
        assert len(b._pending_limits) == 1
        assert b._pending_limits[0]["limit_price"] == 64000.0
        assert len(b._pending_order_records) == 1

    def test_load_state_old_checkpoint_no_pending_limits_field(self):
        """旧 checkpoint 无 pending_limits 字段 → 向后兼容（空队列）"""
        a, fake = _scripted_adapter()
        old_st = {
            "ledger": [], "unconfirmed": [], "errors": 0,
            "initial_balance": 10000.0, "initial_position": 1.0,
        }
        a.load_state(old_st)
        assert a._pending_limits == []
        assert a._pending_order_records == {}

    def test_reconcile_pending_limits_filled_during_restart(self):
        """重启对账：挂单在重启期间已成交 → 回填账本"""
        a, fake = _scripted_adapter()
        res = a.place_order(Order("BTC/USDT", "buy", 0.01, 64000.0, "limit", limit_price=64000.0), timestamp="t0")
        st = a.state_dict()

        # 模拟重启：新适配器加载状态，但交易所侧订单已成交
        b, fake2 = _scripted_adapter()
        b.load_state(st)
        # 复制订单状态到新 fake（模拟交易所侧仍记录该订单）
        fake2._order_states[res.order_id] = {
            "id": res.order_id, "status": "closed",
            "average": 63900.0, "filled": 0.01, "side": "buy",
        }
        unresolved = b.reconcile_pending_limits()
        assert unresolved == []
        assert len(b._pending_limits) == 0  # 已成交，移出
        assert len(b.get_trade_history()) == 1  # 回填账本

    def test_reconcile_pending_limits_still_open_kept(self):
        """重启对账：挂单仍 open → 保留续跑"""
        a, fake = _scripted_adapter()
        res = a.place_order(Order("BTC/USDT", "buy", 0.01, 64000.0, "limit", limit_price=64000.0), timestamp="t0")
        st = a.state_dict()

        b, fake2 = _scripted_adapter()
        b.load_state(st)
        fake2._order_states[res.order_id] = {
            "id": res.order_id, "status": "open", "side": "buy",
        }
        unresolved = b.reconcile_pending_limits()
        assert unresolved == []
        assert len(b._pending_limits) == 1  # 保留续跑

    def test_reconcile_pending_limits_query_fail_returns_unresolved(self):
        """重启对账：查询失败 → 返回未解决列表（拒绝静默续跑）"""
        a, fake = _scripted_adapter()
        a.place_order(Order("BTC/USDT", "buy", 0.01, 64000.0, "limit", limit_price=64000.0), timestamp="t0")
        st = a.state_dict()

        b, fake2 = _scripted_adapter()
        b.load_state(st)
        # fake2 没有该订单状态 → fetch_order 返回 None → 查询失败
        unresolved = b.reconcile_pending_limits()
        assert len(unresolved) == 1


class TestLimitOrderGuardInteraction:
    """护栏与限价单交互：挂单成交时 guard.record 才调用（不在挂单时调）"""

    def test_guard_not_recorded_on_pending(self):
        """挂单成功（pending）不调 guard.record（未实际成交）"""
        from src.execution.order_guard import OrderRateGuard
        a, fake = _scripted_adapter()
        a.guard = OrderRateGuard(reference_capital=1e9, max_position_per_trade=1.0,
                                 min_trade_interval=0, max_trades_per_day=100)
        a.place_order(Order("BTC/USDT", "buy", 0.01, 64000.0, "limit", limit_price=64000.0), timestamp="t0")
        assert a.guard._count == 0  # 挂单不算成交

    def test_guard_recorded_on_fill_from_check_pending(self):
        """挂单成交时（check_pending_orders）调 guard.record"""
        from src.execution.order_guard import OrderRateGuard
        a, fake = _scripted_adapter()
        a.guard = OrderRateGuard(reference_capital=1e9, max_position_per_trade=1.0,
                                 min_trade_interval=0, max_trades_per_day=100)
        res = a.place_order(Order("BTC/USDT", "buy", 0.01, 64000.0, "limit", limit_price=64000.0), timestamp="t0")
        fake.set_order_status(res.order_id, "closed", average=63900.0, filled=0.01)
        a.check_pending_orders(bar_high=65000, bar_low=63800, timestamp="t1")
        assert a.guard._count == 1  # 成交时登记
