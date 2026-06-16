"""SimpleMA / BuyAndHold 策略单元测试（覆盖信号分支）。"""

import sys
from datetime import datetime
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

import pandas as pd

from src.strategy.simple_ma import SimpleMAStrategy
from src.strategy.buy_and_hold import BuyAndHoldStrategy

T0 = datetime(2024, 1, 1)


def _df(closes):
    return pd.DataFrame({"close": closes})


class TestSimpleMA:
    def test_none_when_not_enough_data(self):
        s = SimpleMAStrategy(short_window=2, long_window=3)
        assert s.on_bar(_df([1, 2]), T0) is None

    def test_golden_cross_buy(self):
        s = SimpleMAStrategy(short_window=2, long_window=3)
        # 前一根：SMA2==SMA3==1；当前：SMA2=50.5 > SMA3=34 → 金叉
        assert s.on_bar(_df([1, 1, 1, 1, 100]), T0) == "BUY"

    def test_death_cross_sell(self):
        s = SimpleMAStrategy(short_window=2, long_window=3)
        # 前一根：SMA2==SMA3==100；当前：SMA2=50.5 < SMA3=67 → 死叉
        assert s.on_bar(_df([100, 100, 100, 100, 1]), T0) == "SELL"

    def test_no_signal_when_flat(self):
        s = SimpleMAStrategy(short_window=2, long_window=3)
        assert s.on_bar(_df([5, 5, 5, 5, 5]), T0) is None

    def test_parameters_recorded(self):
        s = SimpleMAStrategy(short_window=4, long_window=9)
        assert s.parameters == {"short_window": 4, "long_window": 9}
        assert s.name == "SimpleMA"


class TestBuyAndHold:
    def test_first_bar_buys_then_holds(self):
        s = BuyAndHoldStrategy()
        assert s.on_bar(_df([10]), T0) == "BUY"
        assert s.on_bar(_df([10, 11]), T0) is None
        assert s.on_bar(_df([10, 11, 12]), T0) is None
        assert s.bar_count == 3

    def test_reset_clears_state(self):
        s = BuyAndHoldStrategy()
        s.on_bar(_df([10]), T0)
        assert s.has_bought is True
        s.reset()
        assert s.has_bought is False
        assert s.bar_count == 0
        # 重置后第一根又买入
        assert s.on_bar(_df([10]), T0) == "BUY"
