"""
Paper Broker 单元测试（Phase 4 验收清单）

覆盖：买入、卖出、资金不足拒单、持仓不足拒单、风控拒单、
手续费计算、滑点计算、统计信息。
"""

import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

import pytest

from src.execution.broker import Order
from src.execution.paper_broker import PaperBroker


def make_broker(balance=100000.0):
    # 滑点设 0 便于精确断言，单独测试滑点时再开
    return PaperBroker(balance, commission=0.001, slippage={"BTC/USDT": 0.0})


class TestBuyOrder:
    def test_buy_fills_and_updates_state(self):
        b = make_broker()
        r = b.place_order(Order("BTC/USDT", "buy", amount=0.1, price=50000))
        assert r.status == "filled"
        assert r.order_id == "PAPER_000001"
        assert b.get_position("BTC/USDT") == pytest.approx(0.1)
        # 花费 = 0.1*50000*(1+0.001) = 5005
        assert b.get_balance() == pytest.approx(100000 - 5005)

    def test_buy_records_trade(self):
        b = make_broker()
        b.place_order(Order("BTC/USDT", "buy", 0.1, 50000))
        hist = b.get_trade_history()
        assert len(hist) == 1
        assert hist[0]["side"] == "buy"
        assert hist[0]["status"] == "filled"


class TestSellOrder:
    def test_sell_after_buy(self):
        b = make_broker()
        b.place_order(Order("BTC/USDT", "buy", 0.1, 50000))
        r = b.place_order(Order("BTC/USDT", "sell", 0.1, 51000))
        assert r.status == "filled"
        assert b.get_position("BTC/USDT") == pytest.approx(0.0)
        # 卖出回款增加余额
        assert b.get_balance() > 100000 - 5005


class TestRejections:
    def test_insufficient_funds(self):
        # 放开风控以隔离资金检查（否则风控会先拦截大单）。
        # 订单价值正好等于现金（风控通过），但加上手续费后超出 -> 资金不足。
        b = PaperBroker(1000.0, commission=0.001, slippage={"BTC/USDT": 0.0},
                        max_position_per_trade=1.0, max_total_position=1.0)
        # 0.02 * 50000 = 1000 == 余额；成本 = 1000 * 1.001 = 1001 > 1000
        r = b.place_order(Order("BTC/USDT", "buy", 0.02, 50000))
        assert r.status == "rejected"
        assert "资金不足" in r.reason
        assert b.get_position("BTC/USDT") == 0.0
        assert b.get_balance() == 1000.0  # 状态未变

    def test_insufficient_position(self):
        b = make_broker()
        r = b.place_order(Order("BTC/USDT", "sell", 0.5, 50000))  # 无持仓
        assert r.status == "rejected"
        assert "持仓不足" in r.reason

    def test_risk_limit_per_trade(self):
        # 单笔超 20%：余额 10000，买 0.1 BTC @ 50000 = 5000 = 50% > 20%
        b = PaperBroker(10000.0, commission=0.001, slippage={"BTC/USDT": 0.0})
        r = b.place_order(Order("BTC/USDT", "buy", 0.1, 50000))
        assert r.status == "rejected"
        assert "风控" in r.reason

    def test_zero_amount_rejected(self):
        b = make_broker()
        r = b.place_order(Order("BTC/USDT", "buy", 0.0, 50000))
        assert r.status == "rejected"

    def test_invalid_side_rejected(self):
        b = make_broker()
        r = b.place_order(Order("BTC/USDT", "hold", 0.1, 50000))
        assert r.status == "rejected"


class TestCostCalculation:
    def test_commission_charged(self):
        b = make_broker()
        b.place_order(Order("BTC/USDT", "buy", 0.1, 50000))
        stats = b.get_statistics()
        # 手续费 = 0.1*50000*0.001 = 5.0
        assert stats["total_commission"] == pytest.approx(5.0)

    def test_slippage_charged_on_buy(self):
        # 滑点 0.05%：买入 actual=50000*1.0005=50025
        b = PaperBroker(100000.0, commission=0.0,
                        slippage={"BTC/USDT": 0.0005})
        r = b.place_order(Order("BTC/USDT", "buy", 0.1, 50000))
        assert r.filled_price == pytest.approx(50025.0)
        stats = b.get_statistics()
        # 滑点成本 = 0.1*(50025-50000) = 2.5
        assert stats["total_slippage"] == pytest.approx(2.5)

    def test_slippage_charged_on_sell(self):
        b = PaperBroker(100000.0, commission=0.0,
                        slippage={"BTC/USDT": 0.0005})
        b.place_order(Order("BTC/USDT", "buy", 0.1, 50000))
        r = b.place_order(Order("BTC/USDT", "sell", 0.1, 50000))
        # 卖出 actual = 50000*0.9995 = 49975
        assert r.filled_price == pytest.approx(49975.0)


class TestAccountValue:
    def test_total_value_includes_position(self):
        b = make_broker()
        b.place_order(Order("BTC/USDT", "buy", 0.1, 50000))
        # 总价值 = 现金 + 持仓市值（按当前价 50000）
        tv = b.get_total_value({"BTC/USDT": 50000})
        assert tv == pytest.approx(100000 - 5005 + 0.1 * 50000)


class TestMisc:
    def test_invalid_initial_balance(self):
        with pytest.raises(ValueError):
            PaperBroker(0.0)

    def test_cancel_returns_false(self):
        b = make_broker()
        r = b.place_order(Order("BTC/USDT", "buy", 0.1, 50000))
        assert b.cancel_order(r.order_id) is False

    def test_get_order_status(self):
        b = make_broker()
        r = b.place_order(Order("BTC/USDT", "buy", 0.1, 50000))
        status = b.get_order_status(r.order_id)
        assert status is not None
        assert status["order_id"] == r.order_id
        assert b.get_order_status("NONEXISTENT") is None
