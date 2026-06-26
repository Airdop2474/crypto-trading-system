from typing import Optional
from datetime import datetime

import pandas as pd
import numpy as np

from src.strategy.risk_aware import RiskAwareStrategy
from src.utils.logger import logger


class MorningStarStrategy(RiskAwareStrategy):
    """晨星/暮星策略

    三根 K：大实体同向 + 小实体十字星 + 反向大实体收复第一根中点。
    反向三兵离场。
    """

    PARAM_SCHEMA = {
        "small_body_pct": {"type": float, "min": 0.05, "max": 0.4, "default": 0.3},
        "big_body_pct":   {"type": float, "min": 0.3,  "max": 0.9, "default": 0.5},
    }

    def __init__(self, small_body_pct=0.3, big_body_pct=0.5,
                 max_consecutive_losses=3, max_daily_loss=0.02,
                 initial_capital=10000.0, stop_loss_config=None):
        super().__init__(name="MorningStar",
                         max_consecutive_losses=max_consecutive_losses,
                         max_daily_loss=max_daily_loss,
                         initial_capital=initial_capital,
                         stop_loss_config=stop_loss_config)
        self.small_body_pct = small_body_pct
        self.big_body_pct = big_body_pct
        self._in_position = False
        self.set_parameters(small_body_pct=small_body_pct, big_body_pct=big_body_pct)
        self._init_risk_state()
        logger.info("MorningStar initialized")

    def reset(self):
        super().reset()
        self._in_position = False

    def on_bar(self, data, current_time):
        if len(data) < 4:
            return None
        if self._is_paused(current_time):
            return None
        close = float(data["close"].iloc[-1])
        if self._in_position:
            t, _ = self._check_stop_loss(close, current_time, atr=None)
            if t:
                self._in_position = False
                return "SELL"

        # 三根：c2=前前 c1=前 c0=当前
        d2, d1, d0 = data.iloc[-3], data.iloc[-2], data.iloc[-1]
        o2, c2 = float(d2["open"]), float(d2["close"])
        o1, h1, l1, c1 = float(d1["open"]), float(d1["high"]), float(d1["low"]), float(d1["close"])
        o0, h0, l0, c0 = float(d0["open"]), float(d0["high"]), float(d0["low"]), float(d0["close"])

        def body_ratio_pct(o, h, l, c):
            r = h - l
            return abs(c - o) / r if r > 0 else 0

        br2 = body_ratio_pct(o2, float(d2["high"]), float(d2["low"]), c2)
        br1 = body_ratio_pct(o1, h1, l1, c1)
        br0 = body_ratio_pct(o0, h0, l0, c0)

        # 晨星：c2 大阴 + c1 小实体 + c0 大阳且收复 c2 中点
        morning = (c2 < o2 and br2 >= self.big_body_pct
                   and br1 < self.small_body_pct
                   and c0 > o0 and br0 >= self.big_body_pct
                   and c0 > (o2 + c2) / 2)
        # 暮星
        evening = (c2 > o2 and br2 >= self.big_body_pct
                   and br1 < self.small_body_pct
                   and c0 < o0 and br0 >= self.big_body_pct
                   and c0 < (o2 + c2) / 2)

        if not self._in_position and morning:
            self._in_position = True
            return "BUY"
        if self._in_position and evening:
            self._in_position = False
            return "SELL"
        return None


__all__ = ["MorningStarStrategy"]
