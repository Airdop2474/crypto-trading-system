from typing import Optional
from datetime import datetime

import pandas as pd
import numpy as np

from src.strategy.risk_aware import RiskAwareStrategy
from src.utils.logger import logger


class AcceleratingMomentumStrategy(RiskAwareStrategy):
    """递增动量策略

    n 连同向 + 每根实体 > 前一根实体（加速度）。
    反向 K 离场。
    """

    PARAM_SCHEMA = {
        "n": {"type": int, "min": 2, "max": 10, "default": 3},
    }

    def __init__(self, n=3,
                 max_consecutive_losses=3, max_daily_loss=0.02,
                 initial_capital=10000.0, stop_loss_config=None):
        super().__init__(name="AcceleratingMomentum",
                         max_consecutive_losses=max_consecutive_losses,
                         max_daily_loss=max_daily_loss,
                         initial_capital=initial_capital,
                         stop_loss_config=stop_loss_config)
        self.n = n
        self._in_position = False
        self.set_parameters(n=n)
        self._init_risk_state()
        logger.info(f"AcceleratingMomentum initialized: n={n}")

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
        bodies = [abs(c[i] - o[i]) for i in range(len(c))]
        all_bull = all(c[i] > o[i] for i in range(len(c)))
        all_bear = all(c[i] < o[i] for i in range(len(c)))
        increasing = all(bodies[i] > bodies[i - 1] for i in range(1, len(bodies)))

        if not increasing:
            return None

        if not self._in_position and all_bull:
            self._in_position = True
            return "BUY"
        if self._in_position and all_bear:
            self._in_position = False
            return "SELL"
        return None


__all__ = ["AcceleratingMomentumStrategy"]
