"""
DataFrame hashing utility for caching and deduplication.

Shared across modules that need to identify DataFrame contents.
"""

import hashlib
from typing import Optional

import pandas as pd


def hash_dataframe(df: pd.DataFrame, columns: Optional[list] = None) -> str:
    """Compute SHA-256 hash of DataFrame contents.

    Args:
        df: DataFrame to hash
        columns: Optional column subset (None = all columns)

    Returns:
        Hex digest string
    """
    if columns:
        df = df[columns]
    data = df.to_csv(index=False)
    return hashlib.sha256(data.encode()).hexdigest()


def hash_ohlcv(df: pd.DataFrame) -> str:
    """Hash OHLCV DataFrame using standard columns."""
    cols = ["timestamp", "open", "high", "low", "close", "volume"]
    available = [c for c in cols if c in df.columns]
    return hash_dataframe(df, available)


__all__ = ["hash_dataframe", "hash_ohlcv"]
