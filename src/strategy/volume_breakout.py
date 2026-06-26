from typing import Optional
from datetime import datetime

import pandas as pd
import numpy as np

from src.strategy.risk_aware import RiskAwareStrategy
from src.utils.logger import logger


class VolumeBreakoutStrategy(RiskAwareStrategy):
    """放量突破策略

    突破根 volume > 近 n 根平均 volume × mult（放量）。
    与纯 K 线突破的差异：要求量能配合。
    volume 是原始数据（非指标），符合"实用派"边界定义。
    """

    PARAM_SCHEMA = {
        "n":    {"type": int,   "min": 5, "max": 100, "default": 20},
        "mult": {"type": float, "min": 1.0, "max": 5.0, "default": 1.5},
    }

    def __init__(self, n=20, mult=1.5,
                 max_consecutive_losses=3, max_daily_loss=0.02,
                 initial_capital=10000.0, stop_loss_config=None):
        super().__init__(name="VolumeBreakout",
                         max_consecutive_losses=max_consecutive_losses,
                         max_daily_loss=max_daily_loss,
                         initial_capital=initial_capital,
                         stop_loss_config=stop_loss_config)
        self.n = n
        self.mult = mult
        self._in_position = False
        self.set_parameters(n=n, mult=mult)
        self._init_risk_state()
        logger.info(f"VolumeBreakout initialized: n={n}, mult={mult}")

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
        vol = float(row["volume"])
        window = data.iloc[-(self.n + 1):-1]
        avg_vol = float(window["volume"].mean())
        if avg_vol <= 0:
            return None
        high_vol = vol > avg_vol * self.mult
        win_high = float(window["high"].max())
        win_low = float(window["low"].min())

        if not self._in_position and high_vol and close > win_high:
            self._in_position = True
            return "BUY"
        if self._in_position and close < win_low:
            self._in_position = False
            return "SELL"
        return None


__all__ = ["VolumeBreakoutStrategy"]
