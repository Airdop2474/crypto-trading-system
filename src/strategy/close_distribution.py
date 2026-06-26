from typing import Optional
from datetime import datetime

import pandas as pd
import numpy as np

from src.strategy.risk_aware import RiskAwareStrategy
from src.utils.logger import logger


class CloseDistributionStrategy(RiskAwareStrategy):
    """收盘分布位置策略

    当前 close 在近 lookback 根 range 的相对位置。
    始终在上 top_pct → 强势；始终在下 top_pct → 弱势。
    用 rolling 统计的中位数作为均值替代（不引入均值平滑）。
    """

    PARAM_SCHEMA = {
        "lookback": {"type": int,   "min": 10, "max": 200, "default": 50},
        "top_pct":  {"type": float, "min": 0.05, "max": 0.4, "default": 0.2},
    }

    def __init__(self, lookback=50, top_pct=0.2,
                 max_consecutive_losses=3, max_daily_loss=0.02,
                 initial_capital=10000.0, stop_loss_config=None):
        super().__init__(name="CloseDistribution",
                         max_consecutive_losses=max_consecutive_losses,
                         max_daily_loss=max_daily_loss,
                         initial_capital=initial_capital,
                         stop_loss_config=stop_loss_config)
        self.lookback = lookback
        self.top_pct = top_pct
        self._in_position = False
        self.set_parameters(lookback=lookback, top_pct=top_pct)
        self._init_risk_state()
        logger.info(f"CloseDistribution initialized: lookback={lookback}, top={top_pct}")

    def reset(self):
        super().reset()
        self._in_position = False

    def on_bar(self, data, current_time):
        if len(data) < self.lookback + 1:
            return None
        if self._is_paused(current_time):
            return None
        close = float(data["close"].iloc[-1])
        if self._in_position:
            t, _ = self._check_stop_loss(close, current_time, atr=None)
            if t:
                self._in_position = False
                return "SELL"

        window = data.iloc[-(self.lookback + 1):-1]
        win_high = float(window["high"].max())
        win_low = float(window["low"].min())
        rng = win_high - win_low
        if rng <= 0:
            return None
        pos = (close - win_low) / rng

        if not self._in_position and pos > 1 - self.top_pct:
            self._in_position = True
            return "BUY"
        if self._in_position and pos < 0.5:
            self._in_position = False
            return "SELL"
        return None


__all__ = ["CloseDistributionStrategy"]
