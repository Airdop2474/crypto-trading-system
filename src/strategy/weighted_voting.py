from typing import Optional
from datetime import datetime

import pandas as pd
import numpy as np

from src.strategy.risk_aware import RiskAwareStrategy
from src.utils.logger import logger


class WeightedVotingStrategy(RiskAwareStrategy):
    """加权投票策略

    与 ConfluenceVoting 的差异：不同角度不同权重。
    突破权重3、关键位权重2、形态权重2、动量/收缩权重1。
    """

    PARAM_SCHEMA = {
        "lookback":   {"type": int,   "min": 10, "max": 100, "default": 20},
        "threshold":  {"type": float, "min": 2.0,"max": 15.0, "default": 5.0},
        "pin_ratio":  {"type": float, "min": 1.0,"max": 5.0, "default": 2.0},
    }

    def __init__(self, lookback=20, threshold=5.0, pin_ratio=2.0,
                 max_consecutive_losses=3, max_daily_loss=0.02,
                 initial_capital=10000.0, stop_loss_config=None):
        super().__init__(name="WeightedVoting",
                         max_consecutive_losses=max_consecutive_losses,
                         max_daily_loss=max_daily_loss,
                         initial_capital=initial_capital,
                         stop_loss_config=stop_loss_config)
        self.lookback = lookback
        self.threshold = threshold
        self.pin_ratio = pin_ratio
        self._in_position = False
        self.set_parameters(lookback=lookback, threshold=threshold, pin_ratio=pin_ratio)
        self._init_risk_state()
        logger.info(f"WeightedVoting initialized: threshold={threshold}")

    def reset(self):
        super().reset()
        self._in_position = False

    def _weighted_vote(self, data):
        if len(data) < self.lookback + 2:
            return 0.0
        row = data.iloc[-1]
        prev = data.iloc[-2]
        o, h, l, c = (float(row[k]) for k in ["open", "high", "low", "close"])
        po, pc = float(prev["open"]), float(prev["close"])

        window = data.iloc[-(self.lookback + 1):-1]
        win_high = float(window["high"].max())
        win_low = float(window["low"].min())

        score = 0.0

        # 突破 (权重 3)
        if c > win_high:
            score += 3
        elif c < win_low:
            score -= 3

        # 关键位 (权重 2)
        if abs(c - win_low) / max(c, 1e-9) <= 0.005 and c > o:
            score += 2
        elif abs(c - win_high) / max(c, 1e-9) <= 0.005 and c < o:
            score -= 2

        # 形态 (权重 2)
        if pc < po and c > o and c > po and o < pc:
            score += 2
        elif pc > po and c < o and c < po and o > pc:
            score -= 2

        body = abs(c - o)
        if body > 0:
            upper = h - max(o, c)
            lower = min(o, c) - l
            if lower >= body * self.pin_ratio and upper <= body * 0.3 and c > o:
                score += 2
            elif upper >= body * self.pin_ratio and lower <= body * 0.3 and c < o:
                score -= 2

        # 动量 (权重 1)
        if len(data) >= 3:
            recent = data.iloc[-3:]
            if all(recent["close"] > recent["open"]):
                score += 1
            elif all(recent["close"] < recent["open"]):
                score -= 1

        # 收缩 (权重 1)
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

        return score

    def on_bar(self, data, current_time):
        if self._is_paused(current_time):
            return None
        close = float(data["close"].iloc[-1])
        if self._in_position:
            t, _ = self._check_stop_loss(close, current_time, atr=None)
            if t:
                self._in_position = False
                return "SELL"

        score = self._weighted_vote(data)
        if not self._in_position and score >= self.threshold:
            self._in_position = True
            return "BUY"
        if self._in_position and score <= -self.threshold:
            self._in_position = False
            return "SELL"
        return None


__all__ = ["WeightedVotingStrategy"]
