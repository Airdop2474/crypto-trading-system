from typing import Optional
from datetime import datetime

import pandas as pd
import numpy as np

from src.strategy.risk_aware import RiskAwareStrategy
from src.utils.logger import logger


class CloseMonotonicStrategy(RiskAwareStrategy):
    """收盘价单调策略

    近 n 根 close 严格单调递增（或递减）。
    比单纯"连续同向"更严格：要求 close 序列本身单调，不看实体方向。
    单调被打破即离场。
    """

    PARAM_SCHEMA = {
        "n": {"type": int, "min": 2, "max": 20, "default": 3},
    }

    def __init__(self, n=3,
                 max_consecutive_losses=3, max_daily_loss=0.02,
                 initial_capital=10000.0, stop_loss_config=None):
        super().__init__(name="CloseMonotonic",
                         max_consecutive_losses=max_consecutive_losses,
                         max_daily_loss=max_daily_loss,
                         initial_capital=initial_capital,
                         stop_loss_config=stop_loss_config)
        self.n = n
        self._in_position = False
        self.set_parameters(n=n)
        self._init_risk_state()
        logger.info(f"CloseMonotonic initialized: n={n}")

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
        closes = recent["close"].values
        increasing = all(closes[i] > closes[i - 1] for i in range(1, len(closes)))
        decreasing = all(closes[i] < closes[i - 1] for i in range(1, len(closes)))

        if not self._in_position and increasing:
            self._in_position = True
            return "BUY"
        if self._in_position and (not increasing):
            self._in_position = False
            return "SELL"
        return None


__all__ = ["CloseMonotonicStrategy"]
