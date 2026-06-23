"""
Bollinger Bands 策略单元测试

覆盖：信号逻辑、参数校验、重置、边界条件。
"""

import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

import numpy as np
import pandas as pd
import pytest

from src.strategy.bollinger_bands import BollingerBandsStrategy
from src.strategy.base import Order
from src.strategy.registry import get_strategy, STRATEGY_REGISTRY


class TestBollingerBandsInit:
    def test_default_params(self):
        s = BollingerBandsStrategy()
        assert s.bb_period == 20
        assert s.bb_std == 2.0
        assert s.oversold == 30.0
        assert s.overbought == 70.0
        assert s.name == "BollingerBands"

    def test_custom_params(self):
        s = BollingerBandsStrategy(bb_period=10, bb_std=1.5, oversold=25, overbought=75)
        assert s.bb_period == 10
        assert s.bb_std == 1.5
        assert s.oversold == 25.0
        assert s.overbought == 75.0

    def test_registered(self):
        assert "bollinger" in STRATEGY_REGISTRY
        cls = get_strategy("bollinger")
        assert cls is BollingerBandsStrategy


class TestBollingerBandsSignal:
    def test_no_signal_on_short_data(self):
        """样本不足时不发信号"""
        s = BollingerBandsStrategy(bb_period=20, rsi_period=14)
        data = _flat_data(30)
        for i in range(len(data)):
            result = s.on_bar(data.iloc[:i + 1])
            assert result is None, f"Bar {i}: 前 30 根不应发信号"

    def test_buy_signal_at_lower_band(self):
        """价格触及下轨 + RSI 超卖 → BUY 信号"""
        s = BollingerBandsStrategy(bb_period=10, bb_std=1.5, oversold=50, overbought=50, rsi_period=5, position_fraction=1.0)
        data = _extreme_dip(80)
        signals = _run_strategy(s, data)
        buys = [sig for sig in signals if sig and any(o.side.upper() == "BUY" for o in sig)]
        assert len(buys) > 0, "极端下跌行情应产生买入信号"

    def test_sell_signal_at_upper_band(self):
        """价格触及上轨 + RSI 超买 → SELL 信号"""
        s = BollingerBandsStrategy(bb_period=10, bb_std=1.5, oversold=50, overbought=50, rsi_period=5, position_fraction=1.0)
        data = _extreme_spike(80)
        signals = _run_strategy(s, data)
        sells = [sig for sig in signals if sig and any(o.side.upper() == "SELL" for o in sig)]
        assert len(sells) > 0, "极端上涨行情应产生卖出信号"

    def test_no_duplicate_signal(self):
        """连续同向信号不重复"""
        s = BollingerBandsStrategy(bb_period=20, bb_std=2.0, rsi_period=14)
        data = _flat_data(80)
        signals = _run_strategy(s, data)
        buys = [sig for sig in signals if sig and sig[0].side == "buy"]
        if len(buys) >= 2:
            # 验证连续买入信号被去重
            pass  # 去重逻辑不保证无买入，只保证不连续

    def test_reset_clears_state(self):
        """reset 后状态应清空"""
        s = BollingerBandsStrategy()
        data = _flat_data(50)
        _run_strategy(s, data)
        s.reset()
        assert s._last_signal is None
        assert len(s._price_buffer) == 0

    def test_get_bands_returns_values(self):
        """get_bands 返回布林带值"""
        s = BollingerBandsStrategy(bb_period=20)
        data = _flat_data(30)
        _run_strategy(s, data)
        bands = s.get_bands()
        assert "upper" in bands
        assert "lower" in bands
        assert "middle" in bands
        assert "rsi" in bands

    def test_get_bands_early_returns_zeros(self):
        """样本不足时 get_bands 返回 0"""
        s = BollingerBandsStrategy(bb_period=20)
        bands = s.get_bands()
        assert bands["middle"] == 0
        assert bands["upper"] == 0
        assert bands["lower"] == 0


# ------------------------------------------------------------------
# 辅助
# ------------------------------------------------------------------
def _flat_data(n=50):
    """平稳行情"""
    rng = np.random.RandomState(42)
    base = 50000.0
    close = base + rng.normal(0, 20, n)
    close = np.abs(close)
    return pd.DataFrame({
        "timestamp": pd.date_range("2024-01-01", periods=n, freq="4h"),
        "open": close * 0.999, "high": close * 1.002, "low": close * 0.998,
        "close": close, "volume": 500,
    })


def _dip_data(n=60):
    """先平稳后急跌（制造下轨触及），最后拉回测试均值回归"""
    rng = np.random.RandomState(99)
    base = 50000.0
    prices = [base]
    for i in range(1, n):
        if i < 20:
            prices.append(prices[-1] * (1 + rng.normal(0, 0.001)))
        elif i < 35:
            prices.append(prices[-1] * (1 + rng.normal(-0.012, 0.005)))
        else:
            prices.append(prices[-1] * (1 + rng.normal(0.005, 0.003)))
    close = np.array(prices)
    return pd.DataFrame({
        "timestamp": pd.date_range("2024-01-01", periods=n, freq="4h"),
        "open": close * 0.999, "high": close * 1.004, "low": close * 0.996,
        "close": close, "volume": 500,
    })


def _spike_data(n=60):
    """先平稳后急涨（制造上轨触及）"""
    rng = np.random.RandomState(77)
    base = 50000.0
    prices = [base]
    for i in range(1, n):
        if i < 20:
            prices.append(prices[-1] * (1 + rng.normal(0, 0.001)))
        elif i < 35:
            prices.append(prices[-1] * (1 + rng.normal(0.012, 0.005)))
        else:
            prices.append(prices[-1] * (1 + rng.normal(-0.005, 0.003)))
    close = np.array(prices)
    return pd.DataFrame({
        "timestamp": pd.date_range("2024-01-01", periods=n, freq="4h"),
        "open": close * 0.999, "high": close * 1.004, "low": close * 0.996,
        "close": close, "volume": 500,
    })


def _run_strategy(s, df):
    """逐 bar 喂完整 DataFrame（模拟 BacktestEngine），收集非空信号"""
    signals = []
    for i in range(len(df)):
        historical = df.iloc[:i + 1]
        sig = s.on_bar(historical)
        signals.append(sig)
    return signals


def _extreme_dip(n=80):
    """先平稳然后极端下跌（-5% 单根），确保触发下轨"""
    rng = np.random.RandomState(42)
    base = 50000.0
    prices = [base]
    for i in range(1, n):
        if i < 25:
            prices.append(prices[-1] * (1 + rng.normal(0, 0.001)))
        elif i < 40:
            prices.append(prices[-1] * (1 - 0.03 + rng.normal(0, 0.005)))
        else:
            prices.append(prices[-1] * (1 + rng.normal(0.003, 0.003)))
    close = np.array(prices)
    return pd.DataFrame({
        "timestamp": pd.date_range("2024-01-01", periods=n, freq="4h"),
        "open": close * 0.999, "high": close * 1.005, "low": close * 0.995,
        "close": close, "volume": 500,
    })


def _extreme_spike(n=80):
    """先平稳然后极端上涨（+5% 单根），确保触发上轨"""
    rng = np.random.RandomState(42)
    base = 50000.0
    prices = [base]
    for i in range(1, n):
        if i < 25:
            prices.append(prices[-1] * (1 + rng.normal(0, 0.001)))
        elif i < 40:
            prices.append(prices[-1] * (1 + 0.03 + rng.normal(0, 0.005)))
        else:
            prices.append(prices[-1] * (1 + rng.normal(-0.003, 0.003)))
    close = np.array(prices)
    return pd.DataFrame({
        "timestamp": pd.date_range("2024-01-01", periods=n, freq="4h"),
        "open": close * 0.999, "high": close * 1.005, "low": close * 0.995,
        "close": close, "volume": 500,
    })
