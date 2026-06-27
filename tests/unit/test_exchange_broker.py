"""
Exchange Broker 单元测试（Phase 5-6）

完全离线：用 FakeExchange 注入构造器，不触网。
覆盖：余额、持仓、下单成功/资金不足/网络错误/通用异常、
撤单成功失败、查单存在/不存在。
"""

import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

import ccxt
import pytest

from src.execution.broker import Order
from src.execution.exchange_broker import ExchangeBroker


class FakeExchange:
    """最小化的 ccxt 交易所替身，按需返回数据或抛异常。"""

    def __init__(self, balance=None, create_raises=None, create_result=None):
        self._balance = balance if balance is not None else {
            "USDT": {"free": 1000.0},
            "BTC": {"free": 0.5},
        }
        self._create_raises = create_raises
        self._create_result = create_result or {
            "id": "EX_1",
            "status": "open",
            "average": 50000.0,
            "filled": 0.1,
        }
        self.cancelled = []
        self.cancel_raises = False
        self.orders = {"EX_1": {"id": "EX_1", "status": "closed"}}
        self.last_cancel_symbol = "__unset__"
        self.last_fetch_symbol = "__unset__"
        self.last_params = {}  # 记录最近一次 create_order 的 params（验证 clientOrderId）

    def fetch_balance(self):
        return self._balance

    def create_order(self, symbol, type, side, amount, price=None, params=None):
        if self._create_raises is not None:
            raise self._create_raises
        self.last_params = params or {}
        return self._create_result

    def cancel_order(self, order_id, symbol=None):
        if self.cancel_raises:
            raise ccxt.BaseError("cancel failed")
        self.last_cancel_symbol = symbol
        self.cancelled.append(order_id)

    def fetch_order(self, order_id, symbol=None):
        self.last_fetch_symbol = symbol
        if order_id not in self.orders:
            raise ccxt.OrderNotFound(order_id)
        return self.orders[order_id]


def make_broker(**fake_kwargs):
    return ExchangeBroker(exchange=FakeExchange(**fake_kwargs))


class TestBalanceAndPosition:
    def test_get_balance(self):
        assert make_broker().get_balance() == pytest.approx(1000.0)

    def test_get_balance_missing_usdt(self):
        b = make_broker(balance={})
        assert b.get_balance() == 0.0

    def test_get_position(self):
        assert make_broker().get_position("BTC/USDT") == pytest.approx(0.5)

    def test_get_position_missing(self):
        assert make_broker().get_position("ETH/USDT") == 0.0


class TestPlaceOrder:
    def test_place_order_success(self):
        b = make_broker()
        r = b.place_order(Order("BTC/USDT", "buy", 0.1, 50000))
        assert r.order_id == "EX_1"
        assert r.status == "open"
        assert r.filled_price == pytest.approx(50000.0)
        assert r.filled_amount == pytest.approx(0.1)

    def test_place_order_insufficient_funds(self):
        b = make_broker(create_raises=ccxt.InsufficientFunds("no money"))
        r = b.place_order(Order("BTC/USDT", "buy", 100, 50000))
        assert r.status == "rejected"
        assert r.order_id is None
        assert "资金不足" in r.reason

    def test_place_order_network_error(self):
        """网络错误不再返回 error，而是 pending_query（避免重复下单）"""
        b = make_broker(create_raises=ccxt.NetworkError("timeout"))
        r = b.place_order(Order("BTC/USDT", "buy", 0.1, 50000))
        assert r.status == "pending_query"
        assert "网络错误" in r.reason
        assert r.order_id is None  # 响应丢失，无 order_id

    def test_place_order_network_error_carries_client_order_id(self):
        """网络错误时 OrderResult 携带 client_order_id，便于后续对账查询"""
        b = make_broker(create_raises=ccxt.NetworkError("timeout"))
        order = Order("BTC/USDT", "buy", 0.1, 50000,
                      client_order_id="btcusdt-buy-abc12345")
        r = b.place_order(order)
        assert r.status == "pending_query"
        assert r.client_order_id == "btcusdt-buy-abc12345"

    def test_place_order_passes_client_order_id_to_exchange(self):
        """client_order_id 通过 params 传给 ccxt create_order 做幂等去重"""
        fake = FakeExchange(create_result={"id": "EX_1", "status": "closed"})
        b = ExchangeBroker(exchange=fake)
        order = Order("BTC/USDT", "buy", 0.1, 50000,
                      client_order_id="btcusdt-buy-abc12345")
        b.place_order(order)
        # FakeExchange.create_order 把 params 存到 last_params
        assert fake.last_params.get("clientOrderId") == "btcusdt-buy-abc12345"

    def test_place_order_generic_error(self):
        b = make_broker(create_raises=ValueError("boom"))
        r = b.place_order(Order("BTC/USDT", "buy", 0.1, 50000))
        assert r.status == "error"
        assert "下单失败" in r.reason


class TestCancelAndStatus:
    def test_cancel_order_success(self):
        b = make_broker()
        assert b.cancel_order("EX_1") is True

    def test_cancel_order_failure(self):
        fake = FakeExchange()
        fake.cancel_raises = True
        b = ExchangeBroker(exchange=fake)
        assert b.cancel_order("EX_1") is False

    def test_get_order_status_found(self):
        b = make_broker()
        assert b.get_order_status("EX_1")["status"] == "closed"

    def test_get_order_status_not_found(self):
        b = make_broker()
        assert b.get_order_status("NOPE") is None

    def test_symbol_threaded_to_fetch_and_cancel_after_place(self):
        """回归：下单记 order_id->symbol，查单/撤单回查并把 symbol 传给 ccxt
        （binance 的 fetch_order/cancel_order 必需 symbol）。"""
        fake = FakeExchange(create_result={"id": "EX_1", "status": "open",
                                           "average": None, "filled": 0.0})
        b = ExchangeBroker(exchange=fake)
        b.place_order(Order("BTC/USDT", "buy", 0.1, 30000, "limit"))
        b.get_order_status("EX_1")
        assert fake.last_fetch_symbol == "BTC/USDT"
        b.cancel_order("EX_1")
        assert fake.last_cancel_symbol == "BTC/USDT"


def test_default_testnet_true():
    """默认 testnet=True（不构造真实 ccxt，注入替身仍校验标志）。"""
    b = ExchangeBroker(exchange=FakeExchange())
    assert b.testnet is True


def _spot_api_url(exchange):
    api = exchange.urls["api"]
    return api.get("public") if isinstance(api, dict) else api


def test_internal_construction_switches_to_testnet_endpoint():
    """回归：testnet=True 必须真正切到 testnet endpoint（仅设 options.testnet 无效）。"""
    b = ExchangeBroker(api_key="k", secret="s", testnet=True)
    assert "testnet.binance.vision" in _spot_api_url(b.exchange)


def test_internal_construction_mainnet_when_not_testnet():
    """testnet=False 时走主网 endpoint。"""
    b = ExchangeBroker(api_key="k", secret="s", testnet=False)
    assert "testnet" not in _spot_api_url(b.exchange)
