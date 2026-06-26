"""Fair Value Gap (FVG) 检测。

三连 K bar[i-2], bar[i-1], bar[i]：
- Bullish FVG: bar[i].low > bar[i-2].high  → 区间 [bar[i-2].high, bar[i].low]
- Bearish FVG: bar[i].high < bar[i-2].low  → 区间 [bar[i].high, bar[i-2].low]

强化：bar[i-1] body_ratio > body_threshold 才视为有效（实体主导）。
"""

from dataclasses import dataclass
from typing import Literal
import pandas as pd


@dataclass
class FVG:
    typ: Literal["bullish", "bearish"]
    high: float
    low: float
    index: int           # 创建该 FVG 的 bar[i] 的位置
    mitigated: bool = False
    mitigated_at: int = -1

    @property
    def height(self) -> float:
        return self.high - self.low

    @property
    def mid(self) -> float:
        return (self.high + self.low) / 2.0

    def contains(self, price: float) -> bool:
        return self.low <= price <= self.high


def detect_fvgs(
    data: pd.DataFrame,
    body_ratio_threshold: float = 0.6,
    min_height_pct: float = 0.003,
    max_height_pct: float = 0.03,
) -> list[FVG]:
    """扫描整段数据找出所有 FVG（未应用 mitigation）。

    参数：
        data: 含 open/high/low/close 的 DataFrame
        body_ratio_threshold: bar[i-1] 实体/range 最小值
        min_height_pct / max_height_pct: FVG 高度占 bar[i].close 的比例范围

    返回：
        FVG 列表，按 index 升序
    """
    if len(data) < 3:
        return []

    o = data["open"].to_numpy()
    h = data["high"].to_numpy()
    l = data["low"].to_numpy()
    c = data["close"].to_numpy()
    fvgs: list[FVG] = []

    for i in range(2, len(data)):
        mid_body = abs(c[i - 1] - o[i - 1])
        mid_range = h[i - 1] - l[i - 1]
        if mid_range <= 0 or mid_body / mid_range < body_ratio_threshold:
            continue

        ref_price = c[i]
        # Bullish FVG
        if l[i] > h[i - 2]:
            height = l[i] - h[i - 2]
            pct = height / ref_price
            if min_height_pct <= pct <= max_height_pct:
                fvgs.append(FVG(
                    typ="bullish",
                    high=float(l[i]),
                    low=float(h[i - 2]),
                    index=i,
                ))
        # Bearish FVG
        elif h[i] < l[i - 2]:
            height = l[i - 2] - h[i]
            pct = height / ref_price
            if min_height_pct <= pct <= max_height_pct:
                fvgs.append(FVG(
                    typ="bearish",
                    high=float(l[i - 2]),
                    low=float(h[i]),
                    index=i,
                ))

    return fvgs


def mark_mitigated(fvgs: list[FVG], data: pd.DataFrame, expire_bars: int = 50) -> None:
    """就地标记 FVG 是否已被 mitigate / 过期。

    Mitigation 规则：
    - Bullish FVG: 后续 bar.low 进入 [low, high] 区间 → mitigated
    - Bearish FVG: 后续 bar.high 进入 [low, high] 区间 → mitigated
    - 创建后 expire_bars 仍未 mitigate → 不再考虑（mitigated=True，mitigated_at=-1 标识过期）
    """
    h = data["high"].to_numpy()
    l = data["low"].to_numpy()

    for fvg in fvgs:
        if fvg.mitigated:
            continue
        for j in range(fvg.index + 1, min(fvg.index + 1 + expire_bars, len(data))):
            if fvg.typ == "bullish" and l[j] <= fvg.high:
                fvg.mitigated = True
                fvg.mitigated_at = j
                break
            if fvg.typ == "bearish" and h[j] >= fvg.low:
                fvg.mitigated = True
                fvg.mitigated_at = j
                break
        else:
            # 过期未触发
            if fvg.index + expire_bars < len(data):
                fvg.mitigated = True
                fvg.mitigated_at = -1
