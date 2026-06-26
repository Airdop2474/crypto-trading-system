from typing import Optional
from datetime import datetime

import pandas as pd
import numpy as np

from src.strategy.risk_aware import RiskAwareStrategy
from src.utils.logger import logger


class WickSweepStrategy(RiskAwareStrategy):
    """影线扫损策略

    当前 K 的 high/low 破前 n 极值，但 close 收回前 n range 中点以内。
    反向入场。中点反向离场。
    """

    PARAM_SCHEMA = {
        "n": {"type": int, "min": 5, "max": 100, "default": 20},
    }

    def __init__(self, n=20,
                 max_consecutive_losses=3, max_daily_loss=0.02,
                 initial_capital=10000.0, stop_loss_config=None):
        super().__init__(name="WickSweep",
                         max_consecutive_losses=max_consecutive_losses,
                         max_daily_loss=max_daily_loss,
                         initial_capital=initial_capital,
                         stop_loss_config=stop_loss_config)
        self.n = n
        self._in_position = False
        self.set_parameters(n=n)
        self._init_risk_state()
        logger.info(f"WickSweep initialized: n={n}")

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
        h = float(row["high"]); l = float(row["low"])
        window = data.iloc[-(self.n + 1):-1]
        win_high = float(window["high"].max())
        win_low = float(window["low"].min())
        mid = (win_high + win_low) / 2

        # 上扫：high 破前高，close 收回中点以下 → 看跌
        bear_sweep = h > win_high and close < mid
        # 下扫：low 破前低，close 收回中点以上 → 看涨
        bull_sweep = l < win_low and close > mid

        if not self._in_position and bull_sweep:
            self._in_position = True
            return "BUY"
        if self._in_position and (bear_sweep or close < win_low):
            self._in_position = False
            return "SELL"
        return None


__all__ = ["WickSweepStrategy"]
