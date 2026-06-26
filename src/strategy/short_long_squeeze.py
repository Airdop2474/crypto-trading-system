from typing import Optional
from datetime import datetime

import pandas as pd
import numpy as np

from src.strategy.risk_aware import RiskAwareStrategy
from src.utils.logger import logger


class ShortLongSqueezeStrategy(RiskAwareStrategy):
    """短长期收缩突破策略

    短期平均振幅 < 长期 × ratio（收缩态），大实体突破。
    反向跌破短期 low 离场。
    """

    PARAM_SCHEMA = {
        "short":      {"type": int,   "min": 3, "max": 30,  "default": 6},
        "long":       {"type": int,   "min": 20,"max": 200, "default": 50},
        "ratio":      {"type": float, "min": 0.3, "max": 1.0, "default": 0.6},
        "brk_body_pct":{"type": float, "min": 0.4, "max": 0.9, "default": 0.6},
    }

    def __init__(self, short=6, long=50, ratio=0.6, brk_body_pct=0.6,
                 max_consecutive_losses=3, max_daily_loss=0.02,
                 initial_capital=10000.0, stop_loss_config=None):
        super().__init__(name="ShortLongSqueeze",
                         max_consecutive_losses=max_consecutive_losses,
                         max_daily_loss=max_daily_loss,
                         initial_capital=initial_capital,
                         stop_loss_config=stop_loss_config)
        self.short = short
        self.long = long
        self.ratio = ratio
        self.brk_body_pct = brk_body_pct
        self._in_position = False
        self.set_parameters(short=short, long=long, ratio=ratio, brk_body_pct=brk_body_pct)
        self._init_risk_state()
        logger.info(f"ShortLongSqueeze initialized: short={short}, long={long}")

    def reset(self):
        super().reset()
        self._in_position = False

    def on_bar(self, data, current_time):
        if len(data) < self.long + 2:
            return None
        if self._is_paused(current_time):
            return None
        close = float(data["close"].iloc[-1])
        if self._in_position:
            t, _ = self._check_stop_loss(close, current_time, atr=None)
            if t:
                self._in_position = False
                return "SELL"

        row = data.iloc[-1]
        o = float(row["open"]); h = float(row["high"]); l = float(row["low"]); c = float(row["close"])
        cur_range = h - l
        if cur_range <= 0:
            return None
        body_pct = abs(c - o) / cur_range

        short_window = data.iloc[-(self.short + 1):-1]
        long_window = data.iloc[-(self.long + 1):-1]
        short_avg = float((short_window["high"] - short_window["low"]).mean())
        long_avg = float((long_window["high"] - long_window["low"]).mean())
        if long_avg <= 0:
            return None
        squeezed = short_avg < long_avg * self.ratio
        if not squeezed:
            return None
        big_body = body_pct >= self.brk_body_pct
        if not big_body:
            return None

        short_high = float(short_window["high"].max())
        short_low = float(short_window["low"].min())

        if not self._in_position and c > short_high:
            self._in_position = True
            return "BUY"
        if self._in_position and c < short_low:
            self._in_position = False
            return "SELL"
        return None


__all__ = ["ShortLongSqueezeStrategy"]
