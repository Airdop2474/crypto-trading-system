"""Equal Highs / Equal Lows 聚类。

把 swing high 按价格容差聚合成"流动性位"群，作为 sweep 策略的目标位。
"""

from dataclasses import dataclass, field
from typing import Literal
from src.strategy.pa.components.swing import SwingPoint


@dataclass
class EqualLevel:
    typ: Literal["high", "low"]
    price: float                         # 群代表价（取群内最值）
    members: list[SwingPoint] = field(default_factory=list)
    swept: bool = False
    swept_at: int = -1

    @property
    def count(self) -> int:
        return len(self.members)

    @property
    def first_index(self) -> int:
        return self.members[0].index if self.members else -1

    @property
    def last_index(self) -> int:
        return self.members[-1].index if self.members else -1


def _cluster(
    swings: list[SwingPoint],
    typ: Literal["high", "low"],
    tolerance_pct: float,
    min_members: int,
) -> list[EqualLevel]:
    """单方向聚类（贪心 + 容差）。

    遍历按 index 升序的同类型 swing，若与当前群"代表价"的距离在容差内则加入。
    群代表价：high 取群内最高，low 取群内最低。
    """
    filtered = [s for s in swings if s.typ == typ]
    if not filtered:
        return []

    groups: list[list[SwingPoint]] = []
    for sp in filtered:
        added = False
        for g in groups:
            ref = max(s.price for s in g) if typ == "high" else min(s.price for s in g)
            if abs(sp.price - ref) / ref <= tolerance_pct:
                g.append(sp)
                added = True
                break
        if not added:
            groups.append([sp])

    levels: list[EqualLevel] = []
    for g in groups:
        if len(g) < min_members:
            continue
        rep = max(s.price for s in g) if typ == "high" else min(s.price for s in g)
        levels.append(EqualLevel(typ=typ, price=rep, members=sorted(g, key=lambda s: s.index)))
    return levels


def cluster_equal_highs(
    swings: list[SwingPoint],
    tolerance_pct: float = 0.001,
    min_members: int = 2,
) -> list[EqualLevel]:
    """聚类 equal highs。tolerance_pct=0.001 即 0.1%（BTC 60k ≈ 60$）。"""
    return _cluster(swings, "high", tolerance_pct, min_members)


def cluster_equal_lows(
    swings: list[SwingPoint],
    tolerance_pct: float = 0.001,
    min_members: int = 2,
) -> list[EqualLevel]:
    return _cluster(swings, "low", tolerance_pct, min_members)
