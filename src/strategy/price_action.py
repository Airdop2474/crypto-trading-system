"""
Price Action 策略

核心思想：不依赖指标，通过 K 线结构、关键位和流动性概念解读市场。

三层框架（从大到小）：
  1. 市场结构 —— 整体趋势阶段与结构完整性
  2. 关键供需区 —— OB / FVG / 流动性池
  3. 入场确认 —— 结构破坏 + 供需区测试 + 反转 candle

术语映射：
  - BoS (Break of Structure)：突破前一个 swing high/low，结构转变确认
  - ChoCH (Change of Character)：趋势方向切换的信号
  - OB (Order Block)：大实体 candle 之前最后一根反向 candle，机构挂单区
  - FVG (Fair Value Gap)：三连 K 之间的未回补缺口
  - 流动性池：sweep 前高/前低、止损集中的区域
  - HH/HL: higher high/higher low 上升结构
  - LH/LL: lower high/lower low 下降结构

信号强度评分制（累积 confluence，不靠单一形态触发）：
  +3  结构破坏 (BoS / ChoCH)
  +2  关键位测试（S/R / OB / FVG / 流动性）
  +2  反转型 candle 确认（engulfing / 放量 pin bar）
  +1  顺趋势方向
  -1  假突破（突破后迅速回到区间内）
  -2  趋势方向冲突（见位进反方向）
  -3  近期结构不完整（摆动混乱）
  总分 >= 5 → BUY,  <= -5 → SELL
"""

from typing import Optional, Literal
from datetime import datetime
from dataclasses import dataclass, field
from enum import Enum

import pandas as pd
import numpy as np

from src.strategy.risk_aware import RiskAwareStrategy
from src.utils.logger import logger


# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

_CONFLUENCE_THRESHOLD = 5


# ---------------------------------------------------------------------------
# K 线解析 & 形态识别
# ---------------------------------------------------------------------------

class CandleType(Enum):
    BULLISH = 1
    BEARISH = -1
    DOJI = 0


@dataclass
class ParsedCandle:
    o: float
    h: float
    l: float
    c: float
    body: float
    upper: float
    lower: float
    typ: CandleType
    range_pct: float      # 振幅百分比
    body_pct: float       # 实体占振幅比例

    @classmethod
    def from_row(cls, row: pd.Series) -> "ParsedCandle":
        o, h, l, c = float(row["open"]), float(row["high"]), float(row["low"]), float(row["close"])
        body = abs(c - o)
        upper = h - max(o, c)
        lower = min(o, c) - l
        rng = h - l
        typ = CandleType.BULLISH if c > o else (CandleType.BEARISH if c < o else CandleType.DOJI)
        return cls(
            o=o, h=h, l=l, c=c,
            body=body, upper=upper, lower=lower, typ=typ,
            range_pct=rng / o if o else 0.0,
            body_pct=body / rng if rng else 0.0,
        )


def _detect_engulfing(prev: ParsedCandle, curr: ParsedCandle) -> Optional[Literal["bullish", "bearish"]]:
    """吞没形态：当前实体完全覆盖前根实体，方向相反。"""
    if prev.typ == CandleType.BEARISH and curr.typ == CandleType.BULLISH:
        if curr.c > prev.o and curr.o < prev.c:
            return "bullish"
    if prev.typ == CandleType.BULLISH and curr.typ == CandleType.BEARISH:
        if curr.c < prev.o and curr.o > prev.c:
            return "bearish"
    return None


def _detect_pin_bar(c: ParsedCandle, min_ratio: float = 2.0) -> Optional[Literal["hammer", "shooting_star"]]:
    """锤子线 / 上吊线：影线 >= body * ratio，另一侧影线很短。"""
    if c.body == 0:
        return None
    if c.lower >= c.body * min_ratio and c.upper <= c.body * 0.3 and c.typ == CandleType.BULLISH:
        return "hammer"
    if c.upper >= c.body * min_ratio and c.lower <= c.body * 0.3 and c.typ == CandleType.BEARISH:
        return "shooting_star"
    return None


# ---------------------------------------------------------------------------
# 市场结构
# ---------------------------------------------------------------------------

@dataclass
class SwingPoint:
    """摆动点"""
    price: float
    index: int
    typ: Literal["high", "low"]


class MarketStructure:
    """市场结构分析。

    追踪 swing high/low → 判断趋势阶段 (uptrend / downtrend / ranging)，
    检测结构破坏 (BoS) 和趋势切换 (ChoCH)。
    """

    HIGH = "high"
    LOW = "low"

    def __init__(self, lookback: int = 10):
        self.lookback = lookback
        self.swings: list[SwingPoint] = []
        self.trend: Literal["bullish", "bearish", "ranging"] = "ranging"
        self.last_bos_price: Optional[float] = None
        self.last_bos_dir: Optional[Literal["bullish", "bearish"]] = None

    def reset(self):
        self.swings.clear()
        self.trend = "ranging"
        self.last_bos_price = None
        self.last_bos_dir = None

    def _find_pivot_highs(self, highs: np.ndarray) -> list[int]:
        """识别 swing high（两侧各 2 根更低的 bar）。"""
        pivots: list[int] = []
        for i in range(2, len(highs) - 2):
            if (highs[i] > highs[i-1] and highs[i] > highs[i-2]
                    and highs[i] > highs[i+1] and highs[i] > highs[i+2]):
                pivots.append(i)
        return pivots

    def _find_pivot_lows(self, lows: np.ndarray) -> list[int]:
        """识别 swing low（两侧各 2 根更高的 bar）。"""
        pivots: list[int] = []
        for i in range(2, len(lows) - 2):
            if (lows[i] < lows[i-1] and lows[i] < lows[i-2]
                    and lows[i] < lows[i+1] and lows[i] < lows[i+2]):
                pivots.append(i)
        return pivots

    def update(self, data: pd.DataFrame):
        """从数据更新摆动点和趋势判断。"""
        if len(data) < 10:
            return

        highs = data["high"].values
        lows = data["low"].values
        close = data["close"].values

        h_idx = self._find_pivot_highs(highs)
        l_idx = self._find_pivot_lows(lows)

        self.swings = (
            [SwingPoint(highs[i], i, self.HIGH) for i in h_idx]
            + [SwingPoint(lows[i], i, self.LOW) for i in l_idx]
        )
        self.swings.sort(key=lambda sp: sp.index)

        if len(self.swings) < 4:
            return

        recent = self.swings[-self.lookback:] if len(self.swings) > self.lookback else self.swings

        hh = 0  # higher high
        hl = 0  # higher low
        lh = 0  # lower high
        ll = 0  # lower low
        for i in range(1, len(recent)):
            prev, cur = recent[i-1], recent[i]
            if cur.typ == self.HIGH:
                if cur.price > prev.price:
                    hh += 1
                else:
                    lh += 1
            else:
                if cur.price > prev.price:
                    hl += 1
                else:
                    ll += 1

        total = hh + hl + lh + ll
        if total == 0:
            return

        bullish = (hh + hl) / total
        bearish = (lh + ll) / total

        if bullish >= 0.65:
            # 检测 ChoCH（上升结构中最后一个 higher low 被跌破）
            current_close = close[-1]
            last_bullish_swing_low = max(
                (sp.price for sp in self.swings if sp.typ == self.LOW),
                default=None,
            )
            if last_bullish_swing_low and current_close < last_bullish_swing_low:
                self.trend = "bearish"
                self.last_bos_dir = "bearish"
                self.last_bos_price = last_bullish_swing_low
            else:
                self.trend = "bullish"
        elif bearish >= 0.65:
            current_close = close[-1]
            last_bearish_swing_high = max(
                (sp.price for sp in self.swings if sp.typ == self.HIGH),
                default=None,
            )
            if last_bearish_swing_high and current_close > last_bearish_swing_high:
                self.trend = "bullish"
                self.last_bos_dir = "bullish"
                self.last_bos_price = last_bearish_swing_high
            else:
                self.trend = "bearish"
        else:
            self.trend = "ranging"


# ---------------------------------------------------------------------------
# 供需区
# ---------------------------------------------------------------------------

@dataclass
class OrderBlock:
    """订单块：最后一根反向 candle 的区域。"""
    typ: Literal["bullish", "bearish"]
    high: float
    low: float
    strength: int       # 被扫次数越多越弱
    index: int          # data 中的位置
    mitigated: bool = False

    def contains(self, price: float) -> bool:
        return self.low <= price <= self.high

    def dist_from(self, price: float) -> float:
        if self.contains(price):
            return 0.0
        return min(abs(price - self.low), abs(price - self.high))


@dataclass
class FairValueGap:
    """未回补缺口：三连 K 中间未重叠区域。"""
    typ: Literal["bullish", "bearish"]
    high: float
    low: float
    index: int
    mitigated: bool = False

    def contains(self, price: float) -> bool:
        return self.low <= price <= self.high

    def dist_from(self, price: float) -> float:
        if self.contains(price):
            return 0.0
        return min(abs(price - self.low), abs(price - self.high))


class SupplyDemand:
    """供需区识别。

    检测两类关键区：
      - Order Block：最后一段推动行情前的那根反向实体 candle
      - FVG：三根连续 candle 中间与两侧无重叠
    """

    def __init__(self, lookback: int = 30):
        self.lookback = lookback
        self.obs: list[OrderBlock] = []
        self.fvgs: list[FairValueGap] = []

    def reset(self):
        self.obs.clear()
        self.fvgs.clear()

    def update(self, data: pd.DataFrame):
        if len(data) < 5:
            return

        df = data.iloc[-self.lookback:].reset_index(drop=True)
        candles = [ParsedCandle.from_row(df.iloc[i]) for i in range(len(df))]

        self.obs.clear()
        self.fvgs.clear()

        # --- Order Blocks ---
        for i in range(2, len(candles) - 1):
            prev, curr, next_c = candles[i-1], candles[i], candles[i+1]
            # 推动 K（大实体）
            if next_c.range_pct < 0.005:
                continue
            # 找推动前的反向 candle
            if next_c.typ == CandleType.BULLISH and curr.body >= next_c.body * 0.3:
                if curr.typ == CandleType.BEARISH:
                    self.obs.append(OrderBlock(
                        typ="bullish",
                        high=max(curr.o, curr.c),
                        low=min(curr.o, curr.c),
                        strength=0,
                        index=i,
                    ))
            if next_c.typ == CandleType.BEARISH and curr.body >= next_c.body * 0.3:
                if curr.typ == CandleType.BULLISH:
                    self.obs.append(OrderBlock(
                        typ="bearish",
                        high=max(curr.o, curr.c),
                        low=min(curr.o, curr.c),
                        strength=0,
                        index=i,
                    ))

        # --- FVGs ---
        for i in range(2, len(candles)):
            c1, c2, c3 = candles[i-2], candles[i-1], candles[i]
            # 看涨 FVG：c2 low > c1 high（缺口在中间）
            if c2.l > c1.h and c3.l > c1.h:
                gap_high = c2.l
                gap_low = c1.h
                if gap_high - gap_low > 0:
                    self.fvgs.append(FairValueGap(
                        typ="bullish",
                        high=gap_high,
                        low=gap_low,
                        index=i,
                    ))
            # 看跌 FVG：c2 high < c1 low
            if c2.h < c1.l and c3.h < c1.l:
                gap_high = c1.l
                gap_low = c2.h
                if gap_high - gap_low > 0:
                    self.fvgs.append(FairValueGap(
                        typ="bearish",
                        high=gap_high,
                        low=gap_low,
                        index=i,
                    ))


# ---------------------------------------------------------------------------
# 流动性
# ---------------------------------------------------------------------------

class Liquidity:
    """流动性识别。

    检测两类模式：
      - Equal Highs / Lows：双顶/双底（止损集中区）
      - Sweep：价格快速扫过前高/前低后反转（liquidity grab / stop run）
    """

    def __init__(self, lookback: int = 20):
        self.lookback = lookback
        self.equivalent_levels: dict[float, int] = {}  # price -> count

    def reset(self):
        self.equivalent_levels.clear()

    def update(self, data: pd.DataFrame):
        if len(data) < self.lookback:
            return

        window = data.iloc[-self.lookback:]
        highs = window["high"].values
        lows = window["low"].values
        closes = window["close"].values

        # 找摆动点
        eq_highs: dict[int, list[float]] = {}
        for i in range(2, len(highs) - 2):
            if highs[i] > highs[i-1] and highs[i] > highs[i-2] and highs[i] > highs[i+1] and highs[i] > highs[i+2]:
                key = round(highs[i], 2)
                eq_highs.setdefault(key, []).append(highs[i])

        eq_lows: dict[int, list[float]] = {}
        for i in range(2, len(lows) - 2):
            if lows[i] < lows[i-1] and lows[i] < lows[i-2] and lows[i] < lows[i+1] and lows[i] < lows[i+2]:
                key = round(lows[i], 2)
                eq_lows.setdefault(key, []).append(lows[i])

        self.equivalent_levels = {}
        for key, vals in {**eq_highs, **eq_lows}.items():
            if len(vals) >= 2:
                self.equivalent_levels[key] = len(vals)

    def detect_sweep(self, data: pd.DataFrame) -> Optional[Literal["bullish", "bearish"]]:
        """检测最近一根是否为 liquidity sweep（扫止损后反转）。

        看涨 sweep：价格跌破前低后迅速拉回（震出多头后反转向上）
        看跌 sweep：价格突破前高后迅速回落（诱多后反转向下）
        """
        if len(data) < 5 or not self.equivalent_levels:
            return None

        curr = data.iloc[-1]
        prev_close = data.iloc[-2]["close"]
        curr_close = float(curr["close"])
        curr_low = float(curr["low"])
        curr_high = float(curr["high"])

        sorted_levels = sorted(self.equivalent_levels.keys())

        # 看涨 sweep：当前 low 打掉前 low 后 close > prev_close
        nearest_low = None
        for lvl in sorted_levels:
            if abs(curr_low - lvl) / lvl < 0.005 and curr_low < lvl:
                nearest_low = lvl
        if nearest_low is not None and curr_close > prev_close:
            return "bullish"

        # 看跌 sweep：当前 high 突破前 high 后 close < prev_close
        nearest_high = None
        for lvl in reversed(sorted_levels):
            if abs(curr_high - lvl) / lvl < 0.005 and curr_high > lvl:
                nearest_high = lvl
        if nearest_high is not None and curr_close < prev_close:
            return "bearish"

        return None


# ---------------------------------------------------------------------------
# 评分引擎
# ---------------------------------------------------------------------------

@dataclass
class ConfluenceScore:
    total: int = 0
    details: list[str] = field(default_factory=list)


class PriceActionStrategy(RiskAwareStrategy):
    """Price Action 策略

    基于市场结构 + 供需区 + 流动性 三层框架，用评分制的累计证据决策，
    不做简单的"if 形态 → BUY"。涵盖：

      - 市场结构 (BoS / ChoCH / HH/HL / LH/LL)
      - 供需区 (Order Block / FVG)
      - 流动性 (equal highs/lows, sweep)
      - 反转 candle 确认 (engulfing, pin bar)
    """

    PARAM_SCHEMA = {
        "lookback_structure":   {"type": int,   "min": 5,   "max": 50,  "default": 15},
        "lookback_supplydemand":{"type": int,   "min": 10,  "max": 100, "default": 30},
        "lookback_liquidity":  {"type": int,   "min": 10,  "max": 50,  "default": 20},
        "min_pin_ratio":       {"type": float, "min": 1.0, "max": 5.0, "default": 2.0},
        "confluence_threshold":{"type": int,   "min": 2,   "max": 10,  "default": 5},
    }

    def __init__(
        self,
        lookback_structure: int = 15,
        lookback_supplydemand: int = 30,
        lookback_liquidity: int = 20,
        min_pin_ratio: float = 2.0,
        confluence_threshold: int = _CONFLUENCE_THRESHOLD,
        initial_capital: float = 10000.0,
        stop_loss_config=None,
    ):
        super().__init__(
            name="PriceAction",
            initial_capital=initial_capital,
            stop_loss_config=stop_loss_config,
        )

        self.lookback_structure = lookback_structure
        self.lookback_supplydemand = lookback_supplydemand
        self.lookback_liquidity = lookback_liquidity
        self.min_pin_ratio = min_pin_ratio
        self.confluence_threshold = confluence_threshold

        self._in_position = False
        self._prev_candle: Optional[ParsedCandle] = None

        self._structure = MarketStructure(lookback=lookback_structure)
        self._supply_demand = SupplyDemand(lookback=lookback_supplydemand)
        self._liquidity = Liquidity(lookback=lookback_liquidity)

        self.set_parameters(
            lookback_structure=lookback_structure,
            lookback_supplydemand=lookback_supplydemand,
            lookback_liquidity=lookback_liquidity,
            min_pin_ratio=min_pin_ratio,
            confluence_threshold=confluence_threshold,
        )
        self._init_risk_state()
        logger.info(f"PriceAction initialized: structure={lookback_structure} sd={lookback_supplydemand} liq={lookback_liquidity}")

    def reset(self):
        super().reset()
        self._in_position = False
        self._prev_candle = None
        self._structure.reset()
        self._supply_demand.reset()
        self._liquidity.reset()

    # ------------------------------------------------------------------
    # 评分项
    # ------------------------------------------------------------------

    def _score_structure(self, data: pd.DataFrame) -> ConfluenceScore:
        """市场结构评分。"""
        score = ConfluenceScore()

        if self._structure.trend == "bullish":
            score.total += 1
            score.details.append("trend=bullish +1")
        elif self._structure.trend == "bearish":
            score.total -= 1
            score.details.append("trend=bearish -1")

        if self._structure.last_bos_dir == "bullish":
            score.total += 3
            score.details.append(f"BoS bullish @{self._structure.last_bos_price:.2f} +3")
        elif self._structure.last_bos_dir == "bearish":
            score.total -= 3
            score.details.append(f"BoS bearish @{self._structure.last_bos_price:.2f} -3")

        return score

    def _score_supply_demand(self, close: float) -> ConfluenceScore:
        """供需区评分。"""
        score = ConfluenceScore()
        nearest_bullish_ob = min(
            (ob for ob in self._supply_demand.obs if ob.typ == "bullish" and not ob.mitigated),
            key=lambda ob: ob.dist_from(close), default=None,
        )
        nearest_bearish_ob = min(
            (ob for ob in self._supply_demand.obs if ob.typ == "bearish" and not ob.mitigated),
            key=lambda ob: ob.dist_from(close), default=None,
        )

        # OB 测试
        for ob in [nearest_bullish_ob, nearest_bearish_ob]:
            if ob is None:
                continue
            distance_pct = ob.dist_from(close) / close if close else 999
            if distance_pct < 0.003 and ob.contains(close):
                if ob.typ == "bullish":
                    score.total += 2
                    score.details.append(f"OB bullish tested +2")
                else:
                    score.total -= 2
                    score.details.append(f"OB bearish tested -2")

        # FVG 测试
        for fvg in self._supply_demand.fvgs:
            if fvg.mitigated:
                continue
            dist = fvg.dist_from(close) / close if close else 999
            if dist < 0.003 and fvg.contains(close):
                if fvg.typ == "bullish":
                    score.total += 2
                    score.details.append(f"FVG bullish touched +2")
                else:
                    score.total -= 2
                    score.details.append(f"FVG bearish touched -2")

        return score

    def _score_liquidity(self, data: pd.DataFrame) -> ConfluenceScore:
        """流动性评分。"""
        score = ConfluenceScore()

        sweep = self._liquidity.detect_sweep(data)
        if sweep == "bullish":
            score.total += 2
            score.details.append("liquidity sweep bullish +2")
        elif sweep == "bearish":
            score.total -= 2
            score.details.append("liquidity sweep bearish -2")

        # 是否有等效价位（双顶/双底）
        for lvl, count in self._liquidity.equivalent_levels.items():
            if count >= 2:
                curr = data.iloc[-1]
                if abs(float(curr["close"]) - lvl) / lvl < 0.005:
                    score.details.append(f"equal level @{lvl} x{count}")

        return score

    def _score_candle(self, curr: ParsedCandle, prev: Optional[ParsedCandle]) -> ConfluenceScore:
        """K 线形态确认评分。"""
        score = ConfluenceScore()

        engulf = _detect_engulfing(prev, curr) if prev else None
        if engulf == "bullish":
            score.total += 2
            score.details.append("engulfing bullish +2")
        elif engulf == "bearish":
            score.total -= 2
            score.details.append("engulfing bearish -2")

        pin = _detect_pin_bar(curr, self.min_pin_ratio) if prev else None
        if pin == "hammer":
            score.total += 2
            score.details.append(f"hammer pin bar +2")
        elif pin == "shooting_star":
            score.total -= 2
            score.details.append(f"shooting star pin bar -2")

        return score

    def _score_fakeout(self, data: pd.DataFrame) -> ConfluenceScore:
        """假突破检测。"""
        score = ConfluenceScore()
        if len(data) < 3:
            return score

        close = float(data["close"].iloc[-1])
        prev_high = float(data["high"].iloc[-2])
        prev_low = float(data["low"].iloc[-2])
        curr_high = float(data["high"].iloc[-1])
        curr_low = float(data["low"].iloc[-1])

        # 向上假突破：破了前高但收在之前
        if curr_high > prev_high and close < prev_high:
            score.total -= 1
            score.details.append("fakeout bullish -1")
        # 向下假突破：破了前低但收在之前
        if curr_low < prev_low and close > prev_low:
            score.total += 1
            score.details.append("fakeout bearish +1")

        return score

    # ------------------------------------------------------------------
    # on_bar
    # ------------------------------------------------------------------

    def on_bar(self, data: pd.DataFrame, current_time: datetime) -> Optional[str]:
        if len(data) < 10:
            return None

        if self._is_paused(current_time):
            return None

        # 止损检查（在策略逻辑之前）
        if self._in_position:
            triggered, reason = self._check_stop_loss(
                float(data["close"].iloc[-1]), current_time, atr=None
            )
            if triggered:
                self._in_position = False
                return "SELL"

        # 更新各层
        self._structure.update(data)
        self._supply_demand.update(data)
        self._liquidity.update(data)

        row = data.iloc[-1]
        close = float(row["close"])
        curr = ParsedCandle.from_row(row)

        if self._prev_candle is None and len(data) >= 2:
            self._prev_candle = ParsedCandle.from_row(data.iloc[-2])
        prev = self._prev_candle

        # 综合评分
        total_score = ConfluenceScore()
        for scorer in [
            self._score_structure(data),
            self._score_supply_demand(close),
            self._score_liquidity(data),
            self._score_candle(curr, prev),
            self._score_fakeout(data),
        ]:
            total_score.total += scorer.total
            total_score.details.extend(scorer.details)

        threshold = self.confluence_threshold

        signal: Optional[str] = None

        if not self._in_position:
            if total_score.total >= threshold:
                signal = "BUY"
        else:
            if total_score.total <= -threshold:
                signal = "SELL"

        if signal is not None:
            logger.info(
                f"Signal: {signal} | score={total_score.total}/{threshold} "
                f"| {'|'.join(total_score.details[-3:])}"
            )
            if signal == "BUY":
                self._in_position = True
            else:
                self._in_position = False

        self._prev_candle = curr
        return signal


__all__ = ["PriceActionStrategy"]
