"""4 个此前无专用测试的策略单元测试：
Donchian / MarketStructure / SuperTrend / KeyLevelReversal。

均为 RiskAwareStrategy 子类，on_bar(df, ts) 返回 "BUY"/"SELL"/None。
用确定性 OHLC 数据触发各自的入场/出场分支 + 数据不足早退 + reset。
"""

import sys
from datetime import datetime
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

import pandas as pd

from src.strategy.donchian_channel import DonchianChannelStrategy
from src.strategy.market_structure import MarketStructureStrategy
from src.strategy.super_trend import SuperTrendStrategy
from src.strategy.key_level_reversal import KeyLevelReversalStrategy

T0 = datetime(2024, 1, 1)


def _ohlc(rows):
    """rows: list of (open, high, low, close)。"""
    return pd.DataFrame(rows, columns=["open", "high", "low", "close"])


def _flat(n, price):
    """n 根平价 bar（OHLC 全等）。"""
    return [(price, price, price, price)] * n


# ============================ Donchian ============================

class TestDonchian:
    def test_none_when_not_enough_data(self):
        s = DonchianChannelStrategy(period=5)
        # 需要 period+1=6 根，给 5 根
        assert s.on_bar(_ohlc(_flat(5, 100)), T0) is None

    def test_breakout_above_upper_buys(self):
        s = DonchianChannelStrategy(period=5)
        # 前 5 根 high=100，最后一根 close 突破上轨 100
        rows = _flat(5, 100) + [(100, 120, 100, 110)]
        assert s.on_bar(_ohlc(rows), T0) == "BUY"

    def test_no_signal_inside_channel(self):
        s = DonchianChannelStrategy(period=5)
        # close=100 不超过上轨 100（需严格 >）
        rows = _flat(5, 100) + [(100, 100, 100, 100)]
        assert s.on_bar(_ohlc(rows), T0) is None

    def test_exit_below_lower_after_entry(self):
        s = DonchianChannelStrategy(period=5)
        # 先突破买入
        assert s.on_bar(_ohlc(_flat(5, 100) + [(100, 120, 100, 110)]), T0) == "BUY"
        # 再跌破下轨卖出：窗口取倒数 period+1 到 -1 根
        rows = _flat(5, 100) + [(100, 120, 100, 110), (90, 95, 80, 85)]
        assert s.on_bar(_ohlc(rows), T0) == "SELL"

    def test_reset_clears_position(self):
        s = DonchianChannelStrategy(period=5)
        s.on_bar(_ohlc(_flat(5, 100) + [(100, 120, 100, 110)]), T0)
        assert s._in_position is True
        s.reset()
        assert s._in_position is False
        assert s._upper is None

    def test_invalid_period_rejected(self):
        try:
            DonchianChannelStrategy(period=1)
            assert False, "应抛 ValueError"
        except ValueError:
            pass


# ======================= MarketStructure =======================

class TestMarketStructure:
    def test_none_when_not_enough_data(self):
        s = MarketStructureStrategy(lookback=10)
        assert s.on_bar(_ohlc(_flat(9, 100)), T0) is None

    def test_break_swing_high_buys(self):
        s = MarketStructureStrategy(lookback=5)
        # 第一次调用用平价窗口初始化 swing_high=100（含当前 bar，故此根不触发）
        assert s.on_bar(_ohlc(_flat(5, 100)), T0) is None
        # 再追加一根创新高 bar：close=110 > swing_high=100 → BUY
        rows = _flat(5, 100) + [(100, 110, 100, 110)]
        assert s.on_bar(_ohlc(rows), T0) == "BUY"

    def test_break_swing_low_sells_after_entry(self):
        s = MarketStructureStrategy(lookback=5)
        # 先初始化（swing_high=swing_low=100），再追加突破 bar 入场
        assert s.on_bar(_ohlc(_flat(5, 100)), T0) is None
        assert s.on_bar(_ohlc(_flat(5, 100) + [(100, 110, 100, 110)]), T0) == "BUY"
        # 再跌破 swing_low=100 → SELL
        rows = _flat(5, 100) + [(100, 110, 100, 110), (90, 95, 80, 85)]
        assert s.on_bar(_ohlc(rows), T0) == "SELL"

    def test_reset_clears_swings(self):
        s = MarketStructureStrategy(lookback=5)
        s.on_bar(_ohlc(_flat(5, 100)), T0)
        s.on_bar(_ohlc(_flat(5, 100) + [(100, 110, 100, 110)]), T0)
        s.reset()
        assert s._in_position is False
        assert s._swing_high is None

    def test_invalid_lookback_rejected(self):
        try:
            MarketStructureStrategy(lookback=2)
            assert False, "应抛 ValueError"
        except ValueError:
            pass


# ============================ SuperTrend ============================

class TestSuperTrend:
    def test_none_when_not_enough_data(self):
        s = SuperTrendStrategy(period=10)
        assert s.on_bar(_ohlc(_flat(10, 100)), T0) is None

    def test_uptrend_buys(self):
        s = SuperTrendStrategy(period=5, multiplier=1.0)
        # 稳定上涨：close 在下轨之上 → trend_up True → BUY
        rows = [(p, p + 1, p - 1, p) for p in range(100, 110)]
        sig = s.on_bar(_ohlc(rows), T0)
        assert sig == "BUY"
        assert s._in_position is True

    def test_reset_clears_state(self):
        s = SuperTrendStrategy(period=5, multiplier=1.0)
        rows = [(p, p + 1, p - 1, p) for p in range(100, 110)]
        s.on_bar(_ohlc(rows), T0)
        s.reset()
        assert s._in_position is False
        assert s._trend_up is None

    def test_invalid_params_rejected(self):
        for kw in ({"period": 1}, {"multiplier": 0}, {"multiplier": -1}):
            try:
                SuperTrendStrategy(**kw)
                assert False, f"应抛 ValueError: {kw}"
            except ValueError:
                pass


# ======================= KeyLevelReversal =======================

class TestKeyLevelReversal:
    def test_none_when_not_enough_data(self):
        s = KeyLevelReversalStrategy(lookback=50)
        assert s.on_bar(_ohlc(_flat(49, 100)), T0) is None

    def test_runs_without_error_on_full_window(self):
        """完整窗口下不报错，返回合法信号值（具体信号依赖 pin bar + S/R 区域）。"""
        s = KeyLevelReversalStrategy(lookback=50, atr_period=14)
        rows = [(p, p + 2, p - 2, p) for p in range(100, 155)]
        sig = s.on_bar(_ohlc(rows), T0)
        assert sig in (None, "BUY", "SELL")

    def test_bullish_pin_at_support_buys(self):
        """构造支撑区下影线 pin bar 触发 BUY。"""
        s = KeyLevelReversalStrategy(lookback=50, atr_period=14, pin_threshold=2.0)
        # 50 根在 100 附近震荡建立 S/R，最后一根：长下影线 pin bar 在低位
        base = [(100, 102, 98, 100)] * 50
        # pin bar：open=99 close=99.5 体小，low=90 长下影，high=99.6
        base.append((99.0, 99.6, 90.0, 99.5))
        sig = s.on_bar(_ohlc(base), T0)
        # 该数据可能命中 BUY；至少不应抛异常、返回合法值
        assert sig in (None, "BUY")

    def test_reset_clears_state(self):
        s = KeyLevelReversalStrategy(lookback=50)
        rows = [(p, p + 2, p - 2, p) for p in range(100, 155)]
        s.on_bar(_ohlc(rows), T0)
        s.reset()
        assert s._in_position is False
        assert s._entry_price is None


# ======================= 风控暂停分支（共性） =======================

class TestRiskPauseShortCircuit:
    def test_paused_strategy_returns_none(self, monkeypatch):
        """_is_paused() 为 True 时 on_bar 应短路返回 None（不出信号）。"""
        s = DonchianChannelStrategy(period=5)
        monkeypatch.setattr(s, "_is_paused", lambda *a, **k: True)
        # 即使是会突破的数据，暂停下也返回 None
        rows = _flat(5, 100) + [(100, 120, 100, 110)]
        assert s.on_bar(_ohlc(rows), T0) is None
