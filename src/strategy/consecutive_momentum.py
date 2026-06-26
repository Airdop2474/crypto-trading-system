from typing import Optional
from datetime import datetime

import pandas as pd
import numpy as np

from src.strategy.risk_aware import RiskAwareStrategy
from src.utils.logger import logger


class ConsecutiveMomentumStrategy(RiskAwareStrategy):
    """连续动量策略

    n 连同向 + 实体占振幅≥0.6。
    反向 K 离场。
    """

    PARAM_SCHEMA = {
        "n":               {"type": int,   "min": 2, "max": 10, "default": 3},
        "min_body_ratio":  {"type": float, "min": 0.4, "max": 0.9, "default": 0.6},
    }

    def __init__(self, n=3, min_body_ratio=0.6,
                 max_consecutive_losses=3, max_daily_loss=0.02,
                 initial_capital=10000.0, stop_loss_config=None):
        super().__init__(name="ConsecutiveMomentum",
                         max_consecutive_losses=max_consecutive_losses,
                         max_daily_loss=max_daily_loss,
                         initial_capital=initial_capital,
                         stop_loss_config=stop_loss_config)
        self.n = n
        self.min_body_ratio = min_body_ratio
        self._in_position = False
        self.set_parameters(n=n, min_body_ratio=min_body_ratio)
        self._init_risk_state()
        logger.info(f"ConsecutiveMomentum initialized: n={n}")

    def reset(self):
        super().reset()
        self._in_position = False

    def on_bar(self, data, current_time):
        if len(data) < self.n + 1:
            return None
        if self._is_paused(current_time):
            return None
        close = float(data["close"].iloc[-1])
        if self._in_position:
            t, _ = self._check_stop_loss(close, current_time, atr=None)
            if t:
                self._in_position = False
                return "SELL"

        recent = data.iloc[-self.n:]
        o = recent["open"].values
        c = recent["close"].values
        h = recent["high"].values
        l = recent["low"].values

        all_bull = all(c[i] > o[i] for i in range(len(c)))
        all_bear = all(c[i] < o[i] for i in range(len(c)))
        big_body = all(abs(c[i] - o[i]) / max(h[i] - l[i], 1e-9) >= self.min_body_ratio
                       for i in range(len(c)))

        if not big_body:
            return None

        if not self._in_position and all_bull:
            self._in_position = True
            return "BUY"
        if self._in_position and all_bear:
            self._in_position = False
            return "SELL"
        return None


__all__ = ["ConsecutiveMomentumStrategy"]
