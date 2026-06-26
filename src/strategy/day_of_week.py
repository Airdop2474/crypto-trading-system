from typing import Optional
from datetime import datetime

import pandas as pd
import numpy as np

from src.strategy.risk_aware import RiskAwareStrategy
from src.utils.logger import logger


class DayOfWeekStrategy(RiskAwareStrategy):
    """周内效应策略

    仅在指定星期几允许交易。
    直觉：周末流动性低、周一方向选择、周五平仓效应。

    week_mask: list[int]，0=周一 ... 6=周日
    默认 [1,2,3,4]（周二三四五，避开周末和周一）。
    """

    PARAM_SCHEMA = {
        "week_mask": {"type": list, "default": [1, 2, 3, 4]},
        "period":    {"type": int,  "min": 5, "max": 100, "default": 20},
    }

    def __init__(self, week_mask=None, period=20,
                 max_consecutive_losses=3, max_daily_loss=0.02,
                 initial_capital=10000.0, stop_loss_config=None):
        super().__init__(name="DayOfWeek",
                         max_consecutive_losses=max_consecutive_losses,
                         max_daily_loss=max_daily_loss,
                         initial_capital=initial_capital,
                         stop_loss_config=stop_loss_config)
        self.week_mask = set(week_mask or [1, 2, 3, 4])
        self.period = period
        self._in_position = False
        self.set_parameters(week_mask=list(self.week_mask), period=period)
        self._init_risk_state()
        logger.info(f"DayOfWeek initialized: mask={sorted(self.week_mask)}")

    def reset(self):
        super().reset()
        self._in_position = False

    def on_bar(self, data, current_time):
        if self._is_paused(current_time):
            return None
        close = float(data["close"].iloc[-1])
        if self._in_position:
            t, _ = self._check_stop_loss(close, current_time, atr=None)
            if t:
                self._in_position = False
                return "SELL"

        if len(data) < self.period + 1:
            return None
        window = data.iloc[-(self.period + 1):-1]
        win_high = float(window["high"].max())
        win_low = float(window["low"].min())

        wd = current_time.weekday()
        allowed = wd in self.week_mask

        if not self._in_position:
            if allowed and close > win_high:
                self._in_position = True
                return "BUY"
        else:
            if (not allowed) or close < win_low:
                self._in_position = False
                return "SELL"
        return None


__all__ = ["DayOfWeekStrategy"]
