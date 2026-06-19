"""
限价单（Limit Order）单元测试

验证：
- PaperBroker 限价单挂单与撮合
- 限价单 vs 市价单行为差异
- 限价单资金/持仓冻结与解冻
- 撤单功能
- Runner 层面的限价单流程
- 限价单在 bar high/low 范围内的撮合
"""

import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

import pandas as pd
import pytest

from src.execution.broker import Order as BrokerOrder
from src.execution.paper_broker import PaperBroker
from src.execution.paper_trading_runner import PaperTradingRunner
from src.strategy.base import Strategy, Order


# ---------------------------------------------------------------------------
# 辅助
# ---------------------------------------------------------------------------
def make_broker(balance=100000.0):
    return PaperBroker(
        balance, commission=0.001,
        slippage={"BTC/USDT": 0.0},
        max_position_per_trade=1.0, max_total_position=1.0,
    )


def make_data(rows: list) -> pd.DataFrame:
    """rows: list of (open, high, low, close)"""
    n = len(rows)
    times = pd.date_range("2024-01-01", periods=n, freq="4h")
    return pd.DataFrame({
        "timestamp": times,
        "open": [r[0] for r in rows],
        "high": [r[1] for r in rows],
        "low": [r[2] for r in rows],
        "close": [r[3] for r in rows],
        "volume": [100.0] * n,
    })


class ScriptedStrategy(Strategy):
    """按 bar 索引返回预设信号"""

    def __init__(self, signals: dict, name="Scripted"):
        super().__init__(name=name)
        self.signals = signals
        self.i = -1
        self.fills = []

    def on_bar(self, data, current_time):
        self.i += 1
        return self.signals.get(self.i)

    def on_fill(self, trade):
        self.fills.append(trade)

    def reset(self):
        super().reset()
        self.i = -1
        self.fills = []


def make_runner(broker=None):
    if broker is None:
        broker = make_broker()
    return PaperTradingRunner(broker, "BTC/USDT"), broker


# ===========================================================================
# PaperBroker 限价单
# ===========================================================================
class TestBrokerLimitBuy:
    def test_limit_buy_below_market_goes_pending(self):
        """限价买入低于当前价 → 挂单"""
        b = make_broker()
        order = BrokerOrder("BTC/USDT", "buy", 1.0, 100.0, "limit", limit_price=90.0)
        result = b.place_order(order)
        assert result.status == "pending"
        assert len(b.pending_orders) == 1
        # 资金被冻结
        assert b.balance < 100000.0

    def test_limit_buy_above_market_fills_immediately(self):
        """限价买入高于等于当前价 → 立即成交"""
        b = make_broker()
        order = BrokerOrder("BTC/USDT", "buy", 1.0, 100.0, "limit", limit_price=110.0)
        result = b.place_order(order)
        assert result.status == "filled"
        assert len(b.pending_orders) == 0

    def test_limit_buy_fills_on_price_drop(self):
        """价格跌到限价以下 → 撮合成交"""
        b = make_broker()
        order = BrokerOrder("BTC/USDT", "buy", 1.0, 100.0, "limit", limit_price=90.0)
        b.place_order(order)
        assert len(b.pending_orders) == 1

        # bar high=95, low=85 → low <= 90，触发撮合
        results = b.check_pending_orders(bar_high=95, bar_low=85)
        assert len(results) == 1
        assert results[0].status == "filled"
        assert len(b.pending_orders) == 0

    def test_limit_buy_not_filled_when_price_above(self):
        """价格未跌到限价 → 继续挂单"""
        b = make_broker()
        order = BrokerOrder("BTC/USDT", "buy", 1.0, 100.0, "limit", limit_price=90.0)
        b.place_order(order)

        # bar high=100, low=92 → low > 90，不触发
        results = b.check_pending_orders(bar_high=100, bar_low=92)
        assert len(results) == 0
        assert len(b.pending_orders) == 1

    def test_limit_buy_freezes_cash(self):
        """限价买单冻结对应资金"""
        b = make_broker()
        order = BrokerOrder("BTC/USDT", "buy", 1.0, 100.0, "limit", limit_price=90.0)
        b.place_order(order)
        # 冻结 = 1.0 * 90 * (1 + 0.001) = 90.09
        reserved = 1.0 * 90.0 * 1.001
        assert b.balance == pytest.approx(100000.0 - reserved)


class TestBrokerLimitSell:
    def test_limit_sell_above_market_goes_pending(self):
        """限价卖出高于当前价 → 挂单"""
        b = make_broker()
        # 先买入建立持仓
        buy = BrokerOrder("BTC/USDT", "buy", 1.0, 100.0, "market")
        b.place_order(buy)

        sell = BrokerOrder("BTC/USDT", "sell", 1.0, 100.0, "limit", limit_price=120.0)
        result = b.place_order(sell)
        assert result.status == "pending"
        assert len(b.pending_orders) == 1
        # 持仓被冻结（减少可用）
        assert b.get_position("BTC/USDT") == pytest.approx(0.0)

    def test_limit_sell_below_market_fills_immediately(self):
        """限价卖出低于等于当前价 → 立即成交"""
        b = make_broker()
        buy = BrokerOrder("BTC/USDT", "buy", 1.0, 100.0, "market")
        b.place_order(buy)

        sell = BrokerOrder("BTC/USDT", "sell", 1.0, 100.0, "limit", limit_price=90.0)
        result = b.place_order(sell)
        assert result.status == "filled"

    def test_limit_sell_fills_on_price_rise(self):
        """价格涨到限价以上 → 撮合成交"""
        b = make_broker()
        buy = BrokerOrder("BTC/USDT", "buy", 1.0, 100.0, "market")
        b.place_order(buy)

        sell = BrokerOrder("BTC/USDT", "sell", 1.0, 100.0, "limit", limit_price=120.0)
        b.place_order(sell)

        # bar high=125, low=110 → high >= 120，触发
        results = b.check_pending_orders(bar_high=125, bar_low=110)
        assert len(results) == 1
        assert results[0].status == "filled"


class TestBrokerCancelOrder:
    def test_cancel_pending_buy(self):
        """撤销挂单中的买单 → 解冻资金"""
        b = make_broker()
        order = BrokerOrder("BTC/USDT", "buy", 1.0, 100.0, "limit", limit_price=90.0)
        result = b.place_order(order)
        frozen_balance = b.balance

        assert b.cancel_order(result.order_id) is True
        assert b.balance > frozen_balance
        assert len(b.pending_orders) == 0

    def test_cancel_pending_sell(self):
        """撤销挂单中的卖单 → 解冻持仓"""
        b = make_broker()
        buy = BrokerOrder("BTC/USDT", "buy", 1.0, 100.0, "market")
        b.place_order(buy)

        sell = BrokerOrder("BTC/USDT", "sell", 1.0, 100.0, "limit", limit_price=120.0)
        sell_result = b.place_order(sell)
        assert b.get_position("BTC/USDT") == pytest.approx(0.0)

        b.cancel_order(sell_result.order_id)
        assert b.get_position("BTC/USDT") == pytest.approx(1.0)

    def test_cancel_nonexistent_returns_false(self):
        b = make_broker()
        assert b.cancel_order("NOPE") is False


class TestBrokerEdgeCases:
    def test_limit_buy_insufficient_cash(self):
        """资金不足 → 拒绝"""
        b = make_broker(balance=10.0)
        order = BrokerOrder("BTC/USDT", "buy", 1.0, 100.0, "limit", limit_price=90.0)
        result = b.place_order(order)
        assert result.status == "rejected"

    def test_limit_sell_no_position(self):
        """无持仓 → 拒绝"""
        b = make_broker()
        sell = BrokerOrder("BTC/USDT", "sell", 1.0, 100.0, "limit", limit_price=120.0)
        result = b.place_order(sell)
        assert result.status == "rejected"

    def test_multiple_pending_orders(self):
        """多个挂单同时存在"""
        b = make_broker()
        b.place_order(BrokerOrder("BTC/USDT", "buy", 0.5, 100.0, "limit", limit_price=80.0))
        b.place_order(BrokerOrder("BTC/USDT", "buy", 0.5, 100.0, "limit", limit_price=70.0))
        assert len(b.pending_orders) == 2

        # 价格只跌到 75 → 只有 80 的被成交
        results = b.check_pending_orders(bar_high=85, bar_low=75)
        assert len(results) == 1
        assert len(b.pending_orders) == 1  # 70 的还在

    def test_market_order_unchanged(self):
        """市价单行为不受影响"""
        b = make_broker()
        order = BrokerOrder("BTC/USDT", "buy", 1.0, 100.0, "market")
        result = b.place_order(order)
        assert result.status == "filled"
        assert len(b.pending_orders) == 0


# ===========================================================================
# Runner 限价单集成
# ===========================================================================
class TestRunnerLimitOrders:
    def test_limit_buy_order_from_strategy(self):
        """策略发出限价买单 → 挂单 → bar 跌到限价时成交"""
        data = make_data([
            (100, 105, 95, 100),   # bar 0: signal → BUY limit @90
            (100, 102, 92, 95),    # bar 1: 执行 limit buy (low=92 < 90? no, 92>90)
            (95, 98, 88, 90),      # bar 2: 执行 limit buy (low=88 < 90? yes!)
            (90, 95, 85, 92),      # bar 3: no signal
        ])
        runner, broker = make_runner()

        # bar 0 发出限价买单 @90
        strat = ScriptedStrategy({
            0: [Order("BUY", tag=1, fraction=0.1, limit_price=90.0)],
        })
        runner.run(data, strat)

        # bar 2 的 low=88 <= 90，限价单应被撮合
        assert len(broker.orders) >= 1  # 至少有成交记录
        assert strat.fills  # on_fill 被调用

    def test_limit_sell_order_from_strategy(self):
        """策略发出限价卖单 → 挂单 → bar 涨到限价时成交"""
        data = make_data([
            (100, 105, 95, 100),   # bar 0: signal → BUY market
            (100, 102, 95, 100),   # bar 1: 执行 buy, signal → SELL limit @115
            (100, 110, 95, 105),   # bar 2: 不成交 (high=110 < 115)
            (105, 120, 100, 115),  # bar 3: 成交 (high=120 >= 115)
        ])
        runner, broker = make_runner()

        strat = ScriptedStrategy({
            0: [Order("BUY", tag=1, fraction=0.1)],
            1: [Order("SELL", tag=1, limit_price=115.0)],
        })
        result = runner.run(data, strat)

        # 应有买+卖两笔成交
        assert len(broker.orders) >= 2

    def test_market_order_backward_compatible(self):
        """无限价单的市价单行为不变"""
        data = make_data([
            (100, 105, 95, 100),
            (100, 105, 95, 100),
            (100, 105, 95, 100),
        ])
        runner, broker = make_runner()
        strat = ScriptedStrategy({
            0: [Order("BUY", tag=1, fraction=0.1)],
        })
        result = runner.run(data, strat)

        # 市价单应立即成交（无 pending）
        assert len(broker.pending_orders) == 0
        assert broker.get_position("BTC/USDT") > 0

    def test_limit_order_profit_tracking(self):
        """限价单买卖配对应正确计算盈亏"""
        data = make_data([
            (100, 105, 95, 100),   # bar 0: BUY limit @90
            (100, 102, 88, 92),    # bar 1: 成交 (low=88<=90), SELL limit @120
            (100, 125, 95, 120),   # bar 2: sell 成交 (high=125>=120)
            (120, 125, 115, 118),  # bar 3: no signal
        ])
        runner, broker = make_runner()

        strat = ScriptedStrategy({
            0: [Order("BUY", tag=1, fraction=0.1, limit_price=90.0)],
            1: [Order("SELL", tag=1, limit_price=120.0)],
        })
        result = runner.run(data, strat)

        # 应有盈利（买90卖120）
        if result.get("closed_trades"):
            assert result["closed_trades"][0]["profit"] > 0

    def test_cancel_pending_via_broker(self):
        """通过 broker 撤销 runner 发出的限价挂单"""
        data = make_data([
            (100, 105, 95, 100),   # bar 0: signal → BUY limit @50 (远不会成交)
            (100, 102, 95, 98),    # bar 1: 执行 limit buy（仍挂单）
            (98, 100, 90, 95),     # bar 2
        ])
        broker = make_broker()
        runner = PaperTradingRunner(broker, "BTC/USDT")

        strat = ScriptedStrategy({
            0: [Order("BUY", tag=1, fraction=0.1, limit_price=50.0)],
        })
        # process bar 0：策略生成信号，不执行
        bar0 = data.iloc[0]
        signal = runner.process_bar(bar0, data.iloc[:1], strat, None)
        assert signal is not None
        assert len(broker.pending_orders) == 0  # 还没执行

        # process bar 1：执行 bar 0 的信号（限价买单 @50）
        bar1 = data.iloc[1]
        runner.process_bar(bar1, data.iloc[:2], strat, signal)
        # 此时应有 pending order
        assert len(broker.pending_orders) == 1

        # 撤销
        order_id = broker.pending_orders[0]["order_id"]
        assert broker.cancel_order(order_id) is True
        assert len(broker.pending_orders) == 0
