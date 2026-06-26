from typing import Optional
from datetime import datetime

import pandas as pd
import numpy as np

from src.strategy.risk_aware import RiskAwareStrategy
from src.utils.logger import logger


class MonthPositionStrategy(RiskAwareStrategy):
    """月内位置策略

    仅在月内特定时段交易：
      - 月初（1-7 日）：机构调仓期，方向选择
      - 月末（最后 7 日）：option 交割、月末调仓
    默认 enabled_days = (1,2,3,4,5,6,7, 24,25,26,27,28)
    """

    PARAM_SCHEMA = {
        "early_days":  {"type": int, "min": 1, "max": 15, "default": 7},
        "late_days":   {"type": int, "min": 1, "max": 15, "default": 7},
        "period":      {"type": int, "min": 5, "max": 100, "default": 20},
    }

    def __init__(self, early_days=7, late_days=7, period=20,
                 max_consecutive_losses=3, max_daily_loss=0.02,
                 initial_capital=10000.0, stop_loss_config=None):
        super().__init__(name="MonthPosition",
                         max_consecutive_losses=max_consecutive_losses,
                         max_daily_loss=max_daily_loss,
                         initial_capital=initial_capital,
                         stop_loss_config=stop_loss_config)
        self.early_days = early_days
        self.late_days = late_days
        self.period = period
        self._in_position = False
        self.set_parameters(early_days=early_days, late_days=late_days, period=period)
        self._init_risk_state()
        logger.info(f"MonthPosition initialized: early={early_days}, late={late_days}")

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

        day = current_time.day
        import calendar
        last_day = calendar.monthrange(current_time.year, current_time.month)[1]
        in_early = day <= self.early_days
        in_late = day > last_day - self.late_days
        allowed = in_early or in_late

        if not self._in_position:
            if allowed and close > win_high:
                self._in_position = True
                return "BUY"
        else:
            if (not allowed) or close < win_low:
                self._in_position = False
                return "SELL"
        return None


__all__ = ["MonthPositionStrategy"]
