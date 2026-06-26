"""
多信号共振投票策略

与现有 PriceAction 的差异：
  - PriceAction 是 ICT/SMC 框架（OB/FVG/流动性/BoS）加权评分
  - 本策略是 7 个简单形态角度的等权投票，≥阈值入场

7 个角度：吞没、Pin、收盘突破、假突破、连续同向、振幅收缩、关键位反转。
设计来源：纯 K 线策略方案 C2 变体，4 数据集均夏普 1.03。
"""

from typing import Optional
from datetime import datetime

import pandas as pd
import numpy as np

from src.strategy.risk_aware import RiskAwareStrategy
from src.utils.logger import logger


class ConfluenceVotingStrategy(RiskAwareStrategy):
    """多信号共振投票策略

    7 个角度各投 ±1 票，累计 ≥ threshold 票入场。
    """

    PARAM_SCHEMA = {
        "lookback":    {"type": int, "min": 10,  "max": 100, "default": 20},
        "threshold":   {"type": int, "min": 2,   "max": 7,   "default": 3},
        "pin_ratio":   {"type": float, "min": 1.0, "max": 5.0, "default": 2.0},
    }

    def __init__(
        self,
        lookback: int = 20,
        threshold: int = 3,
        pin_ratio: float = 2.0,
        max_consecutive_losses: int = 3,
        max_daily_loss: float = 0.02,
        initial_capital: float = 10000.0,
        stop_loss_config=None,
    ):
        super().__init__(
            name="ConfluenceVoting",
            max_consecutive_losses=max_consecutive_losses,
            max_daily_loss=max_daily_loss,
            initial_capital=initial_capital,
            stop_loss_config=stop_loss_config,
        )
        self.lookback = lookback
        self.threshold = threshold
        self.pin_ratio = pin_ratio

        self._in_position = False
        self._entry_price: Optional[float] = None

        self.set_parameters(
            lookback=lookback, threshold=threshold, pin_ratio=pin_ratio,
        )
        self._init_risk_state()
        logger.info(
            f"ConfluenceVoting initialized: lookback={lookback}, threshold={threshold}"
        )

    def reset(self):
        super().reset()
        self._in_position = False
        self._entry_price = None

    def _vote(self, data: pd.DataFrame) -> int:
        """7 个角度投票，返回 +1..+7 或 -1..-7。"""
        if len(data) < self.lookback + 2:
            return 0
        row = data.iloc[-1]
        prev = data.iloc[-2]
        o, h, l, c = (float(row[k]) for k in ["open", "high", "low", "close"])
        po, pc = float(prev["open"]), float(prev["close"])

        window = data.iloc[-(self.lookback + 1):-1]
        win_high = float(window["high"].max())
        win_low = float(window["low"].min())
        win_avg_range = float((window["high"] - window["low"]).mean())

        score = 0

        # 1. 吞没
        if pc < po and c > o and c > po and o < pc:
            score += 1
        elif pc > po and c < o and c < po and o > pc:
            score -= 1

        # 2. Pin bar
        body = abs(c - o)
        if body > 0:
            upper = h - max(o, c)
            lower = min(o, c) - l
            if lower >= body * self.pin_ratio and upper <= body * 0.3 and c > o:
                score += 1
            elif upper >= body * self.pin_ratio and lower <= body * 0.3 and c < o:
                score -= 1

        # 3. 收盘突破
        if c > win_high:
            score += 1
        elif c < win_low:
            score -= 1

        # 4. 假突破（high 破前高但 close 收回）
        if h > win_high and c < win_high:
            score -= 1
        elif l < win_low and c > win_low:
            score += 1

        # 5. 连续同向（近 3 根全阳/全阴，含当前）
        if len(data) >= 3:
            recent = data.iloc[-3:]
            if all(recent["close"] > recent["open"]):
                score += 1
            elif all(recent["close"] < recent["open"]):
                score -= 1

        # 6. 振幅收缩突破（短期振幅 < 长期 × 0.6 + 大实体突破）
        if len(data) >= self.lookback + 6:
            short_avg = float((data["high"].iloc[-6:] - data["low"].iloc[-6:]).mean())
            long_avg = float((window["high"] - window["low"]).mean())
            cur_range = h - l
            cur_body_pct = body / cur_range if cur_range > 0 else 0
            if short_avg < long_avg * 0.6 and cur_body_pct >= 0.6:
                if c > o:
                    score += 1
                elif c < o:
                    score -= 1

        # 7. 关键位反转（近 lookback low/high ±0.5% + 反转 K）
        if abs(c - win_low) / max(c, 1e-9) <= 0.005 and c > o:
            score += 1
        elif abs(c - win_high) / max(c, 1e-9) <= 0.005 and c < o:
            score -= 1

        return score

    def on_bar(self, data: pd.DataFrame, current_time: datetime) -> Optional[str]:
        if self._is_paused(current_time):
            return None

        close = float(data["close"].iloc[-1])

        # 止损检查
        if self._in_position:
            triggered, reason = self._check_stop_loss(
                close, current_time, atr=None
            )
            if triggered:
                self._in_position = False
                self._entry_price = None
                return "SELL"

        score = self._vote(data)

        if not self._in_position:
            if score >= self.threshold:
                self._in_position = True
                self._entry_price = close
                logger.info(
                    f"ConfluenceVoting BUY: score={score}/{self.threshold} close={close:.2f}"
                )
                return "BUY"
        else:
            if score <= -self.threshold:
                self._in_position = False
                self._entry_price = None
                logger.info(
                    f"ConfluenceVoting SELL: score={score}/-{self.threshold} close={close:.2f}"
                )
                return "SELL"

        return None


__all__ = ["ConfluenceVotingStrategy"]
