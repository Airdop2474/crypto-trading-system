"""Tests for constants and df_hash utilities"""

import pandas as pd
import pytest

from src.constants import (
    DEFAULT_SYMBOL, DEFAULT_INITIAL_CAPITAL, GRID_COUNT,
    WARMUP_BARS, BINANCE_WS_URL,
)
from src.utils.df_hash import hash_dataframe, hash_ohlcv


class TestConstants:
    def test_default_symbol(self):
        assert DEFAULT_SYMBOL == "BTC/USDT"

    def test_default_capital(self):
        assert DEFAULT_INITIAL_CAPITAL == 10000.0

    def test_grid_count(self):
        assert GRID_COUNT == 10

    def test_warmup_bars(self):
        assert WARMUP_BARS == 30

    def test_ws_url(self):
        assert "binance" in BINANCE_WS_URL


class TestDfHash:
    def test_hash_consistency(self):
        df = pd.DataFrame({"a": [1, 2, 3], "b": [4, 5, 6]})
        h1 = hash_dataframe(df)
        h2 = hash_dataframe(df)
        assert h1 == h2

    def test_hash_differs(self):
        df1 = pd.DataFrame({"a": [1, 2, 3]})
        df2 = pd.DataFrame({"a": [4, 5, 6]})
        assert hash_dataframe(df1) != hash_dataframe(df2)

    def test_hash_columns_subset(self):
        df = pd.DataFrame({"a": [1, 2], "b": [3, 4], "c": [5, 6]})
        h_all = hash_dataframe(df)
        h_ab = hash_dataframe(df, columns=["a", "b"])
        assert h_all != h_ab

    def test_hash_ohlcv(self):
        df = pd.DataFrame({
            "timestamp": ["2024-01-01"],
            "open": [100], "high": [110],
            "low": [90], "close": [105],
            "volume": [1000],
        })
        h = hash_ohlcv(df)
        assert len(h) == 64  # SHA-256 hex length
