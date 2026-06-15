"""
回测引擎的单元测试

重点验证：
- 单仓位（字符串信号）路径行为不变
- 多仓位（Order 列表）分仓买卖、现金/权益正确
- on_fill 回调
"""

import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

import pandas as pd
import pytest

from src.backtest.engine import BacktestEngine
from src.strategy.base import Strategy, Order


def make_data(closes: list) -> pd.DataFrame:
    """从收盘价列表构建 4h OHLCV，open=close（同根，便于断言成交价）"""
    times = pd.date_range("2024-01-01", periods=len(closes), freq="4h")
    rows = []
    for ts, c in zip(times, closes):
        rows.append({
            "timestamp": ts,
            "open": c,
            "high": c + 1,
            "low": c - 1,
            "close": c,
            "volume": 100.0,
        })
    return pd.DataFrame(rows)


class FixedSignalStrategy(Strategy):
    """按 bar 索引返回预设信号的测试策略"""

    def __init__(self, signals: dict):
        super().__init__(name="FixedSignal")
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


class TestLegacySinglePosition:
    """单仓位（字符串信号）路径"""

    def test_buy_then_sell_profit(self):
        # bar0 收盘发 BUY -> bar1 开盘成交；bar2 发 SELL -> bar3 开盘成交
        data = make_data([100, 110, 120, 130, 140])
        strat = FixedSignalStrategy({0: "BUY", 2: "SELL"})
        engine = BacktestEngine(10000.0, commission=0.0, slippage=0.0)
        r = engine.run(data, strat)

        assert r["total_trades"] == 2
        buy, sell = r["trades"]
        assert buy["type"] == "BUY" and buy["price"] == 110  # bar1 open
        assert sell["type"] == "SELL" and sell["price"] == 130  # bar3 open
        assert sell["profit"] > 0

    def test_buy_blocked_when_already_long(self):
        data = make_data([100, 110, 120, 130])
        strat = FixedSignalStrategy({0: "BUY", 1: "BUY"})
        engine = BacktestEngine(10000.0, commission=0.0, slippage=0.0)
        r = engine.run(data, strat)
        # 第二个 BUY 应被忽略（已有持仓）
        assert sum(1 for t in r["trades"] if t["type"] == "BUY") == 1


class TestMultiPositionLots:
    """多仓位（Order 列表）分仓路径"""

    def test_two_lots_held_simultaneously(self):
        # bar0 同时开两档；bar2 平掉一档
        data = make_data([100, 105, 110, 115, 120])
        signals = {
            0: [Order("BUY", tag=1, fraction=0.1),
                Order("BUY", tag=2, fraction=0.1)],
            2: [Order("SELL", tag=1)],
        }
        strat = FixedSignalStrategy(signals)
        engine = BacktestEngine(10000.0, commission=0.0, slippage=0.0)
        r = engine.run(data, strat)

        # 2 买 1 卖
        assert sum(1 for t in r["trades"] if t["type"] == "BUY") == 2
        assert sum(1 for t in r["trades"] if t["type"] == "SELL") == 1
        # 结束时仍持有 tag=2 一档
        assert set(engine.lots.keys()) == {2}

    def test_fraction_limits_cash(self):
        # 两档各 10% -> 共用 20% 现金
        data = make_data([100, 100, 100])
        signals = {0: [Order("BUY", tag=1, fraction=0.1),
                       Order("BUY", tag=2, fraction=0.1)]}
        strat = FixedSignalStrategy(signals)
        engine = BacktestEngine(10000.0, commission=0.0, slippage=0.0)
        engine.run(data, strat)
        # 花掉约 2000，现金约 8000
        assert engine.cash == pytest.approx(8000.0, abs=1.0)

    def test_sell_unknown_tag_noop(self):
        data = make_data([100, 100, 100])
        signals = {0: [Order("SELL", tag=99)]}
        strat = FixedSignalStrategy(signals)
        engine = BacktestEngine(10000.0, commission=0.0, slippage=0.0)
        r = engine.run(data, strat)
        assert r["total_trades"] == 0
        assert engine.cash == 10000.0


class TestOnFillCallback:
    """on_fill 回调"""

    def test_fill_callback_invoked(self):
        data = make_data([100, 110, 120, 130, 140])
        strat = FixedSignalStrategy({0: "BUY", 2: "SELL"})
        engine = BacktestEngine(10000.0, commission=0.0, slippage=0.0)
        engine.run(data, strat)
        # 两笔成交都回调
        assert len(strat.fills) == 2
        assert strat.fills[0]["type"] == "BUY"
        assert strat.fills[1]["type"] == "SELL"
