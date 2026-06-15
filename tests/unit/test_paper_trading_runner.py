"""
PaperTradingRunner 单元测试

验证：fraction→amount 转换、tag 记账买卖配对、无前视偏差（t+1 开盘成交）、
Broker 拒单时不更新记账、字符串信号路径、on_fill 回写。
"""

import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

import pandas as pd
import pytest

from src.execution.paper_broker import PaperBroker
from src.execution.paper_trading_runner import PaperTradingRunner
from src.execution.risk_manager import RiskManager
from src.strategy.base import Strategy, Order


def make_data(closes: list) -> pd.DataFrame:
    times = pd.date_range("2024-01-01", periods=len(closes), freq="4h")
    return pd.DataFrame({
        "timestamp": times,
        "open": closes,
        "high": [c + 1 for c in closes],
        "low": [c - 1 for c in closes],
        "close": closes,
        "volume": [100.0] * len(closes),
    })


class ScriptedStrategy(Strategy):
    """按 bar 索引返回预设信号的测试策略"""

    def __init__(self, signals: dict):
        super().__init__(name="Scripted")
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


def make_runner(balance=100000.0):
    broker = PaperBroker(balance, commission=0.001,
                         slippage={"BTC/USDT": 0.0},
                         max_position_per_trade=1.0, max_total_position=1.0)
    return PaperTradingRunner(broker, "BTC/USDT"), broker


class TestNoLookahead:
    def test_signal_fills_at_next_open(self):
        # bar0 收盘发 BUY -> bar1 开盘价 110 成交
        data = make_data([100, 110, 120])
        runner, broker = make_runner()
        strat = ScriptedStrategy({0: [Order("BUY", tag=1, fraction=0.1)]})
        runner.run(data, strat)
        hist = broker.get_trade_history()
        assert len(hist) == 1
        assert hist[0]["price"] == 110  # bar1 open，非 bar0 close

    def test_last_bar_signal_not_executed(self):
        # 最后一根的信号无下一根可成交
        data = make_data([100, 110])
        runner, broker = make_runner()
        strat = ScriptedStrategy({1: [Order("BUY", tag=1, fraction=0.1)]})
        runner.run(data, strat)
        assert len(broker.get_trade_history()) == 0


class TestTagBookkeeping:
    def test_buy_records_lot_amount(self):
        data = make_data([100, 100, 100])
        runner, broker = make_runner()
        strat = ScriptedStrategy({0: [Order("BUY", tag=5, fraction=0.1)]})
        runner.run(data, strat)
        # fraction 0.1 of 100000 = 10000 预算，价格100 -> ~100 单位
        assert runner.lots[5]["amount"] == pytest.approx(
            broker.get_position("BTC/USDT")
        )

    def test_sell_clears_lot(self):
        data = make_data([100, 100, 100, 100])
        runner, broker = make_runner()
        strat = ScriptedStrategy({
            0: [Order("BUY", tag=5, fraction=0.1)],
            1: [Order("SELL", tag=5)],
        })
        runner.run(data, strat)
        assert 5 not in runner.lots
        assert broker.get_position("BTC/USDT") == pytest.approx(0.0)

    def test_sell_unknown_tag_noop(self):
        data = make_data([100, 100, 100])
        runner, broker = make_runner()
        strat = ScriptedStrategy({0: [Order("SELL", tag=99)]})
        runner.run(data, strat)
        assert len(broker.get_trade_history()) == 0

    def test_two_tags_held_simultaneously(self):
        data = make_data([100, 100, 100])
        runner, broker = make_runner()
        strat = ScriptedStrategy({
            0: [Order("BUY", tag=1, fraction=0.1),
                Order("BUY", tag=2, fraction=0.1)],
        })
        runner.run(data, strat)
        assert set(runner.lots.keys()) == {1, 2}


class TestRejectionHandling:
    def test_rejected_buy_no_bookkeeping(self):
        # 收紧风控（单笔上限 10%），大额买单被风控拒 -> 不应记账
        broker = PaperBroker(100000.0, commission=0.001,
                             slippage={"BTC/USDT": 0.0},
                             max_position_per_trade=0.10, max_total_position=1.0)
        runner = PaperTradingRunner(broker, "BTC/USDT")
        data = make_data([100, 100, 100])
        # fraction 0.5 -> 订单价值 ~50%，超过单笔 10% 上限 -> 风控拒
        strat = ScriptedStrategy({0: [Order("BUY", tag=1, fraction=0.5)]})
        runner.run(data, strat)
        assert 1 not in runner.lots
        assert broker.get_balance() == 100000.0
        assert broker.get_position("BTC/USDT") == 0.0


class TestLegacySignals:
    def test_string_buy_sell(self):
        data = make_data([100, 110, 120, 130])
        runner, broker = make_runner()
        strat = ScriptedStrategy({0: "BUY", 2: "SELL"})
        runner.run(data, strat)
        hist = broker.get_trade_history()
        assert len(hist) == 2
        assert hist[0]["side"] == "buy"
        assert hist[1]["side"] == "sell"
        # 清仓后无持仓
        assert broker.get_position("BTC/USDT") == pytest.approx(0.0, abs=1e-9)


class TestOnFillCallback:
    def test_fills_reported_to_strategy(self):
        data = make_data([100, 110, 120, 130])
        runner, broker = make_runner()
        strat = ScriptedStrategy({
            0: [Order("BUY", tag=1, fraction=0.1)],
            2: [Order("SELL", tag=1)],
        })
        runner.run(data, strat)
        assert len(strat.fills) == 2
        assert strat.fills[0]["type"] == "BUY"
        assert strat.fills[1]["type"] == "SELL"


class TestResultShape:
    def test_result_keys(self):
        data = make_data([100, 110, 120])
        runner, broker = make_runner()
        strat = ScriptedStrategy({0: [Order("BUY", tag=1, fraction=0.1)]})
        result = runner.run(data, strat)
        for key in ("symbol", "statistics", "trade_history", "signals", "open_lots"):
            assert key in result


class TestProfitOnFill:
    def test_sell_reports_profit(self):
        # 买 @110，卖 @130（下一根开盘），profit 应为正
        data = make_data([100, 110, 120, 130, 140])
        runner, broker = make_runner()
        strat = ScriptedStrategy({
            0: [Order("BUY", tag=1, fraction=0.1)],
            2: [Order("SELL", tag=1)],
        })
        runner.run(data, strat)
        sells = [f for f in strat.fills if f["type"] == "SELL"]
        assert len(sells) == 1
        assert "profit" in sells[0]
        assert sells[0]["profit"] > 0  # 130 卖 > 110 买

    def test_buy_fill_has_no_profit(self):
        data = make_data([100, 110, 120])
        runner, broker = make_runner()
        strat = ScriptedStrategy({0: [Order("BUY", tag=1, fraction=0.1)]})
        runner.run(data, strat)
        buys = [f for f in strat.fills if f["type"] == "BUY"]
        assert len(buys) == 1
        assert "profit" not in buys[0]


class TestBreakerInPaperPath:
    def test_negative_profit_delivered_on_loss(self):
        # 买 @130（bar1 开盘），卖 @110（bar3 开盘）-> 亏损，profit<0
        data = make_data([120, 130, 120, 110, 100])
        runner, broker = make_runner()
        strat = ScriptedStrategy({
            0: [Order("BUY", tag=1, fraction=0.1)],
            2: [Order("SELL", tag=1)],
        })
        runner.run(data, strat)
        sells = [f for f in strat.fills if f["type"] == "SELL"]
        assert len(sells) == 1
        assert sells[0]["profit"] < 0  # 110 卖 < 130 买

    def test_strategy_breaker_fires_via_on_fill(self):
        # 自定义策略：on_fill 收到亏损即累计，达阈值暂停（验证 profit 贯通驱动熔断）
        class LossCountingStrategy(ScriptedStrategy):
            def __init__(self, signals):
                super().__init__(signals)
                self.losses = 0
                self.paused = False

            def on_fill(self, trade):
                super().on_fill(trade)
                if trade.get("profit", 0) < 0:
                    self.losses += 1
                    if self.losses >= 2:
                        self.paused = True

        # 两轮买高卖低
        data = make_data([120, 130, 120, 110, 130, 110, 100])
        runner, broker = make_runner()
        strat = LossCountingStrategy({
            0: [Order("BUY", tag=1, fraction=0.1)],
            2: [Order("SELL", tag=1)],
            3: [Order("BUY", tag=2, fraction=0.1)],
            4: [Order("SELL", tag=2)],
        })
        runner.run(data, strat)
        assert strat.losses >= 2
        assert strat.paused


class TestRiskManagerIntegration:
    def test_paused_risk_manager_halts_trading(self):
        # RiskManager 处于 PAUSED -> Runner 不应下任何单
        data = make_data([100, 110, 120, 130])
        runner, broker = make_runner()
        rm = RiskManager(100000.0)
        rm.record_data_anomaly("forced pause")
        runner.risk_manager = rm
        strat = ScriptedStrategy({0: [Order("BUY", tag=1, fraction=0.1)]})
        runner.run(data, strat)
        assert len(broker.get_trade_history()) == 0

    def test_fills_recorded_to_risk_manager(self):
        # 成交应回报给 RiskManager（卖出带 profit 驱动其状态）
        data = make_data([120, 130, 120, 110, 100])
        broker = PaperBroker(100000.0, commission=0.001,
                             slippage={"BTC/USDT": 0.0},
                             max_position_per_trade=1.0, max_total_position=1.0)
        rm = RiskManager(100000.0, max_consecutive_losses=1, max_daily_loss=1.0)
        runner = PaperTradingRunner(broker, "BTC/USDT", risk_manager=rm)
        strat = ScriptedStrategy({
            0: [Order("BUY", tag=1, fraction=0.1)],
            2: [Order("SELL", tag=1)],  # 卖出亏损 -> 连亏阈值 1 -> 暂停
        })
        runner.run(data, strat)
        assert rm.is_paused()

    def test_runner_without_risk_manager_unaffected(self):
        # 不传 risk_manager 时行为不变（向后兼容）
        data = make_data([100, 110, 120])
        runner, broker = make_runner()
        assert runner.risk_manager is None
        strat = ScriptedStrategy({0: [Order("BUY", tag=1, fraction=0.1)]})
        runner.run(data, strat)
        assert len(broker.get_trade_history()) == 1
