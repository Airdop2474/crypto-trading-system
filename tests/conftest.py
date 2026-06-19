"""
Shared test fixtures for the trading system test suite.

Usage:
    def test_something(self, sample_ohlcv, grid_strategy, paper_broker):
        ...
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from src.execution.paper_broker import PaperBroker
from src.execution.paper_trading_runner import PaperTradingRunner
from src.strategy.grid_trading import GridTradingStrategy
from src.strategy.rsi_momentum import RSIMomentumStrategy


@pytest.fixture
def sample_ohlcv():
    """Generate 200-bar OHLCV DataFrame for testing"""
    rng = np.random.RandomState(42)
    n = 200
    dates = pd.date_range("2024-01-01", periods=n, freq="4h")
    price = 50000.0
    prices = []
    for _ in range(n):
        price *= 1 + rng.normal(0, 0.005)
        prices.append(price)
    close = np.array(prices)
    high = close * (1 + rng.uniform(0, 0.01, n))
    low = close * (1 - rng.uniform(0, 0.01, n))
    open_ = close * (1 + rng.normal(0, 0.002, n))
    return pd.DataFrame({
        "timestamp": dates,
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": rng.uniform(100, 1000, n),
    })


@pytest.fixture
def grid_strategy(sample_ohlcv):
    """Grid strategy with boundaries from sample data"""
    lo = float(sample_ohlcv["low"].min())
    hi = float(sample_ohlcv["high"].max())
    span = hi - lo
    return GridTradingStrategy(
        lower_price=lo + span * 0.1,
        upper_price=hi - span * 0.1,
        grid_count=10,
        initial_capital=10000,
    )


@pytest.fixture
def rsi_strategy():
    """RSI momentum strategy"""
    return RSIMomentumStrategy(rsi_period=14, ema_period=50)


@pytest.fixture
def paper_broker():
    """PaperBroker with default settings"""
    return PaperBroker(
        10000, commission=0.001,
        slippage={"BTC/USDT": 0.0005},
        max_position_per_trade=1.0,
        max_total_position=1.0,
    )


@pytest.fixture
def runner(paper_broker):
    """PaperTradingRunner"""
    return PaperTradingRunner(paper_broker, "BTC/USDT")
