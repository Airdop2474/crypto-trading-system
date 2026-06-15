"""
网格交易策略的单元测试

覆盖：多档买卖、NO_TRADE 过滤（趋势/波动率/越界）、
PAUSE 熔断（连亏）、参数范围校验。
"""

import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

import pandas as pd
import pytest

from src.strategy.base import Order
from src.strategy.grid_trading import GridTradingStrategy


def make_bar(close, o=None, high=None, low=None):
    """构建单根 K 线 DataFrame 行 dict"""
    o = close if o is None else o
    return {
        "open": o,
        "high": high if high is not None else max(o, close) + 1,
        "low": low if low is not None else min(o, close) - 1,
        "close": close,
        "volume": 100.0,
    }


def make_df(rows: list) -> pd.DataFrame:
    times = pd.date_range("2024-01-01", periods=len(rows), freq="4h")
    df = pd.DataFrame(rows)
    df.insert(0, "timestamp", times)
    return df


class TestParamValidation:
    """参数范围校验"""

    def test_invalid_price_range(self):
        with pytest.raises(ValueError):
            GridTradingStrategy(lower_price=100, upper_price=100)

    def test_grid_count_out_of_range(self):
        with pytest.raises(ValueError):
            GridTradingStrategy(lower_price=100, upper_price=200, grid_count=3)
        with pytest.raises(ValueError):
            GridTradingStrategy(lower_price=100, upper_price=200, grid_count=50)

    def test_position_per_grid_out_of_range(self):
        with pytest.raises(ValueError):
            GridTradingStrategy(
                lower_price=100, upper_price=200, grid_count=10,
                position_per_grid=0.5,
            )

    def test_default_position_capped(self):
        # grid_count=5 -> 1/5=0.2 应被压到上限 0.15
        s = GridTradingStrategy(lower_price=100, upper_price=200, grid_count=5)
        assert s.position_per_grid == pytest.approx(0.15)


class TestGridMechanics:
    """网格多档买卖"""

    def _feed(self, strat, closes):
        """逐根喂价格，返回每根产生的订单列表"""
        rows = [make_bar(c) for c in closes]
        df = make_df(rows)
        all_orders = []
        for i in range(len(df)):
            orders = strat.on_bar(df.iloc[: i + 1], df.iloc[i]["timestamp"])
            all_orders.append(orders)
        return all_orders

    def test_falling_price_generates_multiple_buys(self):
        # 区间 100-200，10 格，间距 10。价格从 195 跌到 145 应多档买入
        strat = GridTradingStrategy(
            lower_price=100, upper_price=200, grid_count=10,
            enable_filters=False,
        )
        orders = self._feed(strat, [195, 145])
        buys = [o for o in orders[-1] if o.side == "BUY"]
        # 从档 9 跌到档 4，应买入多档
        assert len(buys) >= 3
        assert all(isinstance(o, Order) for o in buys)

    def test_rising_price_sells_filled_grids(self):
        strat = GridTradingStrategy(
            lower_price=100, upper_price=200, grid_count=10,
            enable_filters=False,
        )
        # 先跌买入，再涨卖出
        self._feed(strat, [195, 145])
        orders = self._feed(strat, [145, 195])
        sells = [o for o in orders[-1] if o.side == "SELL"]
        assert len(sells) >= 1
        assert all(o.side == "SELL" for o in sells)


class TestNoTradeFilters:
    """NO_TRADE 过滤条件"""

    def _bar(self, strat, df):
        return strat.on_bar(df, df.iloc[-1]["timestamp"])

    def test_price_above_upper_breakout(self):
        strat = GridTradingStrategy(
            lower_price=100, upper_price=200, grid_count=10, enable_filters=False,
        )
        # 第一根普通价，第二根突破上界 20%（>240）
        df = make_df([make_bar(150), make_bar(250)])
        assert self._bar(strat, df) == []

    def test_price_below_lower_breakout(self):
        strat = GridTradingStrategy(
            lower_price=100, upper_price=200, grid_count=10, enable_filters=False,
        )
        df = make_df([make_bar(150), make_bar(80)])  # <100*0.85=85
        assert self._bar(strat, df) == []

    def test_high_volatility_blocks(self):
        strat = GridTradingStrategy(
            lower_price=100, upper_price=200, grid_count=10, enable_filters=True,
        )
        # 单根振幅 >5%: open=150, high=160, low=140 -> (160-140)/150=13%
        df = make_df([
            make_bar(150),
            make_bar(150, o=150, high=160, low=140),
        ])
        assert self._bar(strat, df) == []

    def test_low_volatility_blocks(self):
        strat = GridTradingStrategy(
            lower_price=100, upper_price=200, grid_count=10, enable_filters=True,
        )
        # 振幅 <0.5%: open=150, high=150.1, low=149.9 -> 0.13%
        df = make_df([
            make_bar(150),
            make_bar(150, o=150, high=150.1, low=149.9),
        ])
        assert self._bar(strat, df) == []


class TestCircuitBreakers:
    """PAUSE 熔断"""

    def test_consecutive_losses_pause(self):
        strat = GridTradingStrategy(
            lower_price=100, upper_price=200, grid_count=10,
            max_consecutive_losses=3,
        )
        # 模拟 3 笔亏损成交
        for k in range(3):
            strat.on_fill({
                "time": pd.Timestamp("2024-01-01"),
                "type": "SELL", "profit": -10.0,
            })
        assert strat.paused

    def test_win_resets_consecutive_losses(self):
        strat = GridTradingStrategy(
            lower_price=100, upper_price=200, grid_count=10,
            max_consecutive_losses=3,
        )
        strat.on_fill({"time": pd.Timestamp("2024-01-01"),
                       "type": "SELL", "profit": -10.0})
        strat.on_fill({"time": pd.Timestamp("2024-01-01"),
                       "type": "SELL", "profit": -10.0})
        strat.on_fill({"time": pd.Timestamp("2024-01-01"),
                       "type": "SELL", "profit": 5.0})  # 盈利重置
        assert strat.consecutive_losses == 0
        assert not strat.paused

    def test_daily_loss_pause(self):
        strat = GridTradingStrategy(
            lower_price=100, upper_price=200, grid_count=10,
            max_daily_loss=0.02, initial_capital=10000.0,
            max_consecutive_losses=99,  # 排除连亏干扰
        )
        # 当日亏损 250 = 2.5% > 2%
        strat.on_fill({"time": pd.Timestamp("2024-01-01"),
                       "type": "SELL", "profit": -250.0})
        assert strat.paused

    def test_paused_blocks_trading(self):
        strat = GridTradingStrategy(
            lower_price=100, upper_price=200, grid_count=10, enable_filters=False,
        )
        strat.paused = True
        df = make_df([make_bar(150), make_bar(140)])
        result = strat.on_bar(df, df.iloc[-1]["timestamp"])
        assert result == []
