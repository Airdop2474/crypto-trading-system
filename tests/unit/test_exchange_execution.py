"""执行适配层测试（src/execution/exchange_execution.py）。

FakeExchange 注入，离线覆盖 sizing 守卫 + place_and_confirm 各分支，不触网。
"""

import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

import ccxt
import pytest

from src.execution.exchange_broker import ExchangeBroker
from src.execution.exchange_execution import ExchangeExecutor, extract_fill


class FakeExchange:
    """带精度/限额/成交可配的交易所替身。"""

    def __init__(self, *, create_result=None, create_raises=None,
                 min_amount=0.0001, min_cost=5.0, order_status=None):
        self._create_result = create_result
        self._create_raises = create_raises
        self._min_amount = min_amount
        self._min_cost = min_cost
        self._order_status = order_status
        self.last_params = {}  # 记录最近一次 create_order 的 params（验证 clientOrderId）

    def amount_to_precision(self, symbol, amount):
        return f"{float(amount):.5f}"

    def price_to_precision(self, symbol, price):
        return f"{float(price):.2f}"

    def market(self, symbol):
        return {"limits": {"amount": {"min": self._min_amount},
                           "cost": {"min": self._min_cost}}}

    def create_order(self, symbol, type, side, amount, price=None, params=None):
        if self._create_raises is not None:
            raise self._create_raises
        self.last_params = params or {}
        # 默认市价全成：返回真实成交价量
        return self._create_result or {
            "id": "OID", "status": "closed",
            "average": 65000.0, "filled": float(f"{amount:.5f}"),
        }

    def fetch_order(self, order_id, symbol=None):
        return self._order_status


def _raise(exc):
    def _fn(*a, **k):
        raise exc
    return _fn


def _executor(**fake_kw):
    fake = FakeExchange(**fake_kw)
    broker = ExchangeBroker(exchange=fake)
    return ExchangeExecutor(broker, _clock=_FakeClock(), _sleep=lambda s: None)


class _FakeClock:
    """每次调用前进 10s，确保超时循环必然退出且不真睡。"""
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        self.t += 10.0
        return self.t


# ---- sizing ----

class TestSizeOrder:
    def test_valid_passes(self):
        ex = _executor()
        amt, ok, reason = ex.size_order("BTC/USDT", 0.001, 65000.0)
        assert ok and amt == pytest.approx(0.001) and reason == ""

    def test_below_min_amount_rejected(self):
        ex = _executor(min_amount=0.01)
        amt, ok, reason = ex.size_order("BTC/USDT", 0.001, 65000.0)
        assert not ok and "最小下单量" in reason

    def test_below_min_notional_rejected(self):
        # 0.00005 BTC @ 65000 = 3.25 < minNotional 5
        ex = _executor(min_amount=0.00001)
        amt, ok, reason = ex.size_order("BTC/USDT", 0.00005, 65000.0)
        assert not ok and "minNotional" in reason

    def test_rounds_to_zero_rejected(self):
        ex = _executor()
        amt, ok, reason = ex.size_order("BTC/USDT", 0.0000001, 65000.0)
        assert not ok and "为 0" in reason

    def test_precision_exception_rejected_gracefully(self):
        """回归：amount_to_precision 抛异常（实测 testnet 极小量）→ rejected 不冒泡。"""
        ex = _executor()
        ex.exchange.amount_to_precision = _raise(ccxt.InvalidOrder("below precision"))
        amt, ok, reason = ex.size_order("BTC/USDT", 0.0000001, 65000.0)
        assert not ok and "精度" in reason


# ---- place_and_confirm ----

class TestPlaceAndConfirm:
    def test_market_filled_synchronous(self):
        ex = _executor()
        r = ex.place_and_confirm("BTC/USDT", "buy", 0.001, 65000.0)
        assert r.status == "filled"
        assert r.order_id == "OID"
        assert r.filled_price == 65000.0
        assert r.filled_amount == pytest.approx(0.001)

    def test_rejected_by_sizing(self):
        ex = _executor(min_amount=1.0)
        r = ex.place_and_confirm("BTC/USDT", "buy", 0.001, 65000.0)
        assert r.status == "rejected" and r.order_id is None

    def test_rejected_by_exchange(self):
        ex = _executor(create_raises=ccxt.InsufficientFunds("no money"))
        r = ex.place_and_confirm("BTC/USDT", "buy", 0.001, 65000.0)
        assert r.status == "rejected" and r.order_id is None

    def test_partial_fill(self):
        ex = _executor(create_result={
            "id": "P1", "status": "closed", "average": 65000.0, "filled": 0.0005,
        })
        r = ex.place_and_confirm("BTC/USDT", "buy", 0.001, 65000.0)
        assert r.status == "partial"
        assert r.filled_amount == pytest.approx(0.0005)

    def test_timeout_when_never_fills(self):
        # 下单返回无成交价量，查单始终 open 无 fill → 轮询到超时
        ex = _executor(
            create_result={"id": "T1", "status": "open",
                           "average": None, "filled": 0.0},
            order_status={"status": "open", "average": None, "filled": 0.0},
        )
        r = ex.place_and_confirm("BTC/USDT", "buy", 0.001, 65000.0)
        assert r.status == "timeout" and r.order_id == "T1"


# ---- extract_fill（src 已成 canonical，scripts 复用）----

class TestExtractFill:
    class _Res:
        def __init__(self, fp=None, fa=None):
            self.filled_price = fp
            self.filled_amount = fa

    def test_prefers_place(self):
        assert extract_fill(self._Res(100.0, 0.5)) == (100.0, 0.5, "place")

    def test_falls_back_to_status(self):
        assert extract_fill(self._Res(), {"average": 101.0, "filled": 0.3}) \
            == (101.0, 0.3, "status")

    def test_none(self):
        assert extract_fill(self._Res(), None) == (None, None, "none")


# ---- place_limit_no_wait（阶段3 路径统一：只挂不确认）----

class TestPlaceLimitNoWait:
    """限价单挂单路径：只挂不轮询 30s，挂单成功即返 pending。

    与 place_and_confirm 的区别：不调 _confirm，挂单成功返回 pending 让上层入队。
    """

    def test_pending_when_open(self):
        """挂单成功（交易所返 open）→ status=pending，携带 order_id"""
        ex = _executor(create_result={
            "id": "L1", "status": "open", "average": None, "filled": 0.0,
        })
        r = ex.place_limit_no_wait("BTC/USDT", "buy", 0.001, 64000.0, 65000.0)
        assert r.status == "pending"
        assert r.order_id == "L1"
        assert r.filled_price is None
        assert r.filled_amount is None

    def test_filled_when_synchronous_fill(self):
        """交易所同步成交（testnet 偶尔）→ status=filled，携带价量"""
        ex = _executor(create_result={
            "id": "L2", "status": "closed", "average": 63900.0, "filled": 0.001,
        })
        r = ex.place_limit_no_wait("BTC/USDT", "buy", 0.001, 64000.0, 65000.0)
        assert r.status == "filled"
        assert r.order_id == "L2"
        assert r.filled_price == 63900.0
        assert r.filled_amount == pytest.approx(0.001)

    def test_rejected_by_sizing(self):
        """sizing 拒单 → status=rejected，无 order_id"""
        ex = _executor(min_amount=1.0)
        r = ex.place_limit_no_wait("BTC/USDT", "buy", 0.001, 64000.0, 65000.0)
        assert r.status == "rejected" and r.order_id is None

    def test_rejected_by_exchange(self):
        """交易所拒单（InsufficientFunds）→ status=rejected"""
        ex = _executor(create_raises=ccxt.InsufficientFunds("no money"))
        r = ex.place_limit_no_wait("BTC/USDT", "buy", 0.001, 64000.0, 65000.0)
        assert r.status == "rejected" and r.order_id is None

    def test_pending_query_on_network_error(self):
        """网络错误 → status=pending_query，携带 client_order_id"""
        ex = _executor(create_raises=ccxt.NetworkError("timeout"))
        cid = "btcusdt-buy-abcd1234"
        r = ex.place_limit_no_wait("BTC/USDT", "buy", 0.001, 64000.0, 65000.0,
                                   client_order_id=cid)
        assert r.status == "pending_query"
        assert r.client_order_id == cid

    def test_carries_client_order_id(self):
        """client_order_id 透传给交易所"""
        ex = _executor(create_result={
            "id": "L3", "status": "open", "average": None, "filled": 0.0,
        })
        cid = "btcusdt-sell-xyz789"
        r = ex.place_limit_no_wait("BTC/USDT", "sell", 0.001, 66000.0, 65000.0,
                                   client_order_id=cid)
        assert r.status == "pending"
        assert r.client_order_id == cid
        # FakeExchange.create_order 应收到 clientOrderId
        assert ex.exchange.last_params.get("clientOrderId") == cid
