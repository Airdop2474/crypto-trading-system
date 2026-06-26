from typing import Optional
from datetime import datetime

import pandas as pd
import numpy as np

from src.strategy.risk_aware import RiskAwareStrategy
from src.utils.logger import logger


class AmplitudeBreakoutStrategy(RiskAwareStrategy):
    """幅度突破策略

    突破根振幅 > 近 n 根平均振幅 × k（放量突破的纯K线版）。
    反向幅度跌破离场。
    """

    PARAM_SCHEMA = {
        "n": {"type": int,   "min": 5, "max": 100, "default": 20},
        "k": {"type": float, "min": 1.0, "max": 5.0, "default": 1.5},
    }

    def __init__(self, n=20, k=1.5,
                 max_consecutive_losses=3, max_daily_loss=0.02,
                 initial_capital=10000.0, stop_loss_config=None):
        super().__init__(name="AmplitudeBreakout",
                         max_consecutive_losses=max_consecutive_losses,
                         max_daily_loss=max_daily_loss,
                         initial_capital=initial_capital,
                         stop_loss_config=stop_loss_config)
        self.n = n
        self.k = k
        self._in_position = False
        self.set_parameters(n=n, k=k)
        self._init_risk_state()
        logger.info(f"AmplitudeBreakout initialized: n={n}, k={k}")

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

        row = data.iloc[-1]
        o = float(row["open"]); h = float(row["high"]); l = float(row["low"]); c = float(row["close"])
        cur_range = h - l
        window = data.iloc[-(self.n + 1):-1]
        win_high = float(window["high"].max())
        win_low = float(window["low"].min())
        avg_range = float((window["high"] - window["low"]).mean())
        if avg_range <= 0:
            return None
        big_bar = cur_range > avg_range * self.k
        if not big_bar:
            return None

        if not self._in_position and c > win_high:
            self._in_position = True
            return "BUY"
        if self._in_position and c < win_low:
            self._in_position = False
            return "SELL"
        return None


__all__ = ["AmplitudeBreakoutStrategy"]
