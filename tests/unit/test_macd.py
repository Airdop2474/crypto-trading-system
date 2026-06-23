"""
MACD 策略单元测试
"""

import sys
from pathlib import Path
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

import numpy as np
import pandas as pd
import pytest
from src.strategy.macd import MACDStrategy
from src.strategy.registry import get_strategy, STRATEGY_REGISTRY


class TestMACDInit:
    def test_default_params(self):
        s = MACDStrategy()
        assert s.fast_period == 12
        assert s.slow_period == 26
        assert s.signal_period == 9

    def test_registered(self):
        assert "macd" in STRATEGY_REGISTRY
        cls = get_strategy("macd")
        assert cls is MACDStrategy


class TestMACDSignal:
    def test_upward_cross_generates_buy(self):
        s = MACDStrategy(fast_period=5, slow_period=10, signal_period=3, position_fraction=1.0)
        data = _upward_trend(60)
        signals = []
        for i in range(len(data)):
            sig = s.on_bar(data.iloc[:i + 1])
            signals.append(sig)
        buys = [sig for sig in signals if sig and any(o.side.upper() == "BUY" for o in sig)]
        assert len(buys) > 0, "上涨趋势应产生买入信号"

    def test_downward_cross_generates_sell(self):
        s = MACDStrategy(fast_period=5, slow_period=10, signal_period=3, position_fraction=1.0)
        data = _downward_trend(60)
        signals = []
        for i in range(len(data)):
            sig = s.on_bar(data.iloc[:i + 1])
            signals.append(sig)
        sells = [sig for sig in signals if sig and any(o.side.upper() == "SELL" for o in sig)]
        assert len(sells) > 0, "下跌趋势应产生卖出信号"

    def test_no_signal_on_short_data(self):
        s = MACDStrategy(fast_period=5, slow_period=10, signal_period=3)
        data = _flat_data(5)
        for i in range(len(data)):
            sig = s.on_bar(data.iloc[:i + 1])
            assert sig is None, f"前 10 根不应发信号"

    def test_get_macd_returns_values(self):
        s = MACDStrategy(fast_period=5, slow_period=10, signal_period=3)
        data = _flat_data(30)
        for i in range(len(data)):
            s.on_bar(data.iloc[:i + 1])
        macd = s.get_macd()
        assert "macd" in macd and "signal" in macd and "histogram" in macd


def _flat_data(n):
    base = 50000.0
    close = base + np.random.RandomState(42).normal(0, 10, n)
    return pd.DataFrame({
        "timestamp": pd.date_range("2024-01-01", periods=n, freq="4h"),
        "open": close * 0.999, "high": close * 1.002, "low": close * 0.998,
        "close": np.abs(close), "volume": 500,
    })


def _upward_trend(n):
    rng = np.random.RandomState(42)
    base = 50000.0
    prices = [base]
    for i in range(1, n):
        drift = 0.003 if i > 10 else 0
        prices.append(prices[-1] * (1 + drift + rng.normal(0, 0.005)))
    close = np.array(prices)
    return pd.DataFrame({
        "timestamp": pd.date_range("2024-01-01", periods=n, freq="4h"),
        "open": close * 0.999, "high": close * 1.005, "low": close * 0.995,
        "close": close, "volume": 500,
    })


def _downward_trend(n):
    rng = np.random.RandomState(99)
    base = 50000.0
    prices = [base]
    for i in range(1, n):
        drift = -0.003 if i > 10 else 0
        prices.append(prices[-1] * (1 + drift + rng.normal(0, 0.005)))
    close = np.array(prices)
    return pd.DataFrame({
        "timestamp": pd.date_range("2024-01-01", periods=n, freq="4h"),
        "open": close * 0.999, "high": close * 1.005, "low": close * 0.995,
        "close": close, "volume": 500,
    })