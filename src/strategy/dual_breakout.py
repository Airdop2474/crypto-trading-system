from typing import Optional
from datetime import datetime

import pandas as pd
import numpy as np

from src.strategy.risk_aware import RiskAwareStrategy
from src.utils.logger import logger


class DualBreakoutStrategy(RiskAwareStrategy):
    """多周期同向突破策略

    短期窗口和长期窗口的 high 在同一根 K 被同时突破。
    与 MultiLevelBreakout 类似但更激进：不要求"先有趋势"，只要求"双窗口共振突破"。
    差异：N2 用更短的 short_period（如 5），更早捕捉启动。
    """

    PARAM_SCHEMA = {
        "short": {"type": int, "min": 3, "max": 30, "default": 5},
        "long":  {"type": int, "min": 20, "max": 200, "default": 30},
    }

    def __init__(self, short=5, long=30,
                 max_consecutive_losses=3, max_daily_loss=0.02,
                 initial_capital=10000.0, stop_loss_config=None):
        super().__init__(name="DualBreakout",
                         max_consecutive_losses=max_consecutive_losses,
                         max_daily_loss=max_daily_loss,
                         initial_capital=initial_capital,
                         stop_loss_config=stop_loss_config)
        if short >= long:
            raise ValueError("short must be < long")
        self.short = short
        self.long = long
        self._in_position = False
        self.set_parameters(short=short, long=long)
        self._init_risk_state()
        logger.info(f"DualBreakout initialized: short={short}, long={long}")

    def reset(self):
        super().reset()
        self._in_position = False

    def on_bar(self, data, current_time):
        if len(data) < self.long + 1:
            return None
        if self._is_paused(current_time):
            return None
        close = float(data["close"].iloc[-1])
        if self._in_position:
            t, _ = self._check_stop_loss(close, current_time, atr=None)
            if t:
                self._in_position = False
                return "SELL"

        window = data.iloc[-(self.long + 1):-1]
        short_w = window.iloc[-self.short:]
        short_high = float(short_w["high"].max())
        long_high = float(window["high"].max())
        long_low = float(window["low"].min())

        if not self._in_position:
            if close > short_high and close > long_high:
                self._in_position = True
                return "BUY"
        else:
            if close < long_low:
                self._in_position = False
                return "SELL"
        return None


__all__ = ["DualBreakoutStrategy"]
