"""K 线影线/实体解析。

提供原始几何量：body / upper_wick / lower_wick / range，以及比例与方向。
独立于其他组件，便于影线/吞没/序列策略复用。
"""

from dataclasses import dataclass
from typing import Literal
import pandas as pd


@dataclass
class WickProfile:
    o: float
    h: float
    l: float
    c: float
    body: float            # |c - o|
    upper_wick: float      # h - max(o, c)
    lower_wick: float      # min(o, c) - l
    rng: float             # h - l
    direction: Literal["bull", "bear", "doji"]

    @property
    def body_ratio(self) -> float:
        return self.body / self.rng if self.rng > 0 else 0.0

    @property
    def upper_wick_ratio(self) -> float:
        return self.upper_wick / self.rng if self.rng > 0 else 0.0

    @property
    def lower_wick_ratio(self) -> float:
        return self.lower_wick / self.rng if self.rng > 0 else 0.0


def parse_wick(row: pd.Series) -> WickProfile:
    """从单行 OHLC 解析为 WickProfile。"""
    o, h, l, c = float(row["open"]), float(row["high"]), float(row["low"]), float(row["close"])
    body = abs(c - o)
    upper = h - max(o, c)
    lower = min(o, c) - l
    rng = h - l
    if c > o:
        direction: Literal["bull", "bear", "doji"] = "bull"
    elif c < o:
        direction = "bear"
    else:
        direction = "doji"
    return WickProfile(o=o, h=h, l=l, c=c, body=body, upper_wick=upper, lower_wick=lower, rng=rng, direction=direction)


def is_engulfing(prev: WickProfile, curr: WickProfile, size_mult: float = 1.5) -> Literal["bullish", "bearish", "none"]:
    """吞没形态判定。

    要求当前实体 > 前实体 × size_mult，方向相反，且实体完全覆盖。
    """
    if prev.direction == "bear" and curr.direction == "bull":
        if curr.body >= prev.body * size_mult and curr.c > prev.o and curr.o < prev.c:
            return "bullish"
    if prev.direction == "bull" and curr.direction == "bear":
        if curr.body >= prev.body * size_mult and curr.c < prev.o and curr.o > prev.c:
            return "bearish"
    return "none"
