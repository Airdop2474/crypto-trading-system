from typing import Optional
from datetime import datetime

import pandas as pd
import numpy as np

from src.strategy.risk_aware import RiskAwareStrategy
from src.utils.logger import logger


class HighLowExpansionStrategy(RiskAwareStrategy):
    """高低点扩散策略

    近 n 根 high 序列单调上升 + low 序列也单调上升 → 严格上升趋势。
    两者都下降 → 严格下降趋势。
    序列被打破即离场。
    """

    PARAM_SCHEMA = {
        "n": {"type": int, "min": 2, "max": 20, "default": 3},
    }

    def __init__(self, n=3,
                 max_consecutive_losses=3, max_daily_loss=0.02,
                 initial_capital=10000.0, stop_loss_config=None):
        super().__init__(name="HighLowExpansion",
                         max_consecutive_losses=max_consecutive_losses,
                         max_daily_loss=max_daily_loss,
                         initial_capital=initial_capital,
                         stop_loss_config=stop_loss_config)
        self.n = n
        self._in_position = False
        self.set_parameters(n=n)
        self._init_risk_state()
        logger.info(f"HighLowExpansion initialized: n={n}")

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
        highs = recent["high"].values
        lows = recent["low"].values
        h_inc = all(highs[i] > highs[i - 1] for i in range(1, len(highs)))
        l_inc = all(lows[i] > lows[i - 1] for i in range(1, len(lows)))
        h_dec = all(highs[i] < highs[i - 1] for i in range(1, len(highs)))
        l_dec = all(lows[i] < lows[i - 1] for i in range(1, len(lows)))

        bull_expansion = h_inc and l_inc
        bear_expansion = h_dec and l_dec

        if not self._in_position and bull_expansion:
            self._in_position = True
            return "BUY"
        if self._in_position and not bull_expansion:
            self._in_position = False
            return "SELL"
        return None


__all__ = ["HighLowExpansionStrategy"]
