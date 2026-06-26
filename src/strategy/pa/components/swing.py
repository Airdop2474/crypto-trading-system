"""Swing pivot 检测。

左右各 N 根更低/更高的 high/low → swing。
N=3 时，swing 在 K[i+N] 收盘后才能确认（look-ahead 防护）。
"""

from dataclasses import dataclass
from typing import Literal
import numpy as np
import pandas as pd


@dataclass
class SwingPoint:
    index: int       # 绝对 bar index（data.index 对应位置）
    price: float
    typ: Literal["high", "low"]


def detect_swings(data: pd.DataFrame, n: int = 3) -> list[SwingPoint]:
    """检测 swing high/low。

    参数：
        data: 含 high / low 列的 DataFrame
        n: 左右各 n 根作为对比窗口

    返回：
        按 index 升序排列的 SwingPoint 列表，仅含已确认的 swing
        （即 i <= len(data) - n - 1）
    """
    if len(data) < 2 * n + 1:
        return []

    highs = data["high"].to_numpy()
    lows = data["low"].to_numpy()
    swings: list[SwingPoint] = []

    for i in range(n, len(data) - n):
        left_h = highs[i - n:i]
        right_h = highs[i + 1:i + n + 1]
        if highs[i] > left_h.max() and highs[i] > right_h.max():
            swings.append(SwingPoint(index=i, price=float(highs[i]), typ="high"))
            continue

        left_l = lows[i - n:i]
        right_l = lows[i + 1:i + n + 1]
        if lows[i] < left_l.min() and lows[i] < right_l.min():
            swings.append(SwingPoint(index=i, price=float(lows[i]), typ="low"))

    return swings
