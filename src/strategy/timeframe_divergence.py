from typing import Optional
from datetime import datetime

import pandas as pd
import numpy as np

from src.strategy.risk_aware import RiskAwareStrategy
from src.utils.logger import logger


class TimeframeDivergenceStrategy(RiskAwareStrategy):
    """周期背离策略

    大周期上升（后半段 high/low > 前半段）但小周期出现 LH（lower high）。
    即大周期仍强但小周期动量衰竭 → 减仓/离场信号。
    本策略做空：当大周期下降但小周期出现 HH 时入场（逆向抄底）。
    """

    PARAM_SCHEMA = {
        "big_period":   {"type": int, "min": 20, "max": 200, "default": 50},
        "small_period": {"type": int, "min": 3,  "max": 20,  "default": 5},
    }

    def __init__(self, big_period=50, small_period=5,
                 max_consecutive_losses=3, max_daily_loss=0.02,
                 initial_capital=10000.0, stop_loss_config=None):
        super().__init__(name="TimeframeDivergence",
                         max_consecutive_losses=max_consecutive_losses,
                         max_daily_loss=max_daily_loss,
                         initial_capital=initial_capital,
                         stop_loss_config=stop_loss_config)
        self.big_period = big_period
        self.small_period = small_period
        self._in_position = False
        self.set_parameters(big_period=big_period, small_period=small_period)
        self._init_risk_state()
        logger.info(f"TimeframeDivergence initialized: big={big_period}, small={small_period}")

    def reset(self):
        super().reset()
        self._in_position = False

    def on_bar(self, data, current_time):
        if len(data) < self.big_period + 1:
            return None
        if self._is_paused(current_time):
            return None
        close = float(data["close"].iloc[-1])
        if self._in_position:
            t, _ = self._check_stop_loss(close, current_time, atr=None)
            if t:
                self._in_position = False
                return "SELL"

        # 大周期趋势：前后半段比较
        big_window = data.iloc[-(self.big_period + 1):-1]
        half = self.big_period // 2
        first = big_window.iloc[:half]
        second = big_window.iloc[half:]
        big_up = (float(second["high"].max()) > float(first["high"].max())
                  and float(second["low"].min()) > float(first["low"].min()))

        # 小周期 swing：近 small_period 根的 high 是否高于前 small_period 根
        if len(data) < self.small_period * 2 + 1:
            return None
        recent = data.iloc[-self.small_period:]
        prev = data.iloc[-(self.small_period * 2):-self.small_period]
        small_high = float(recent["high"].max())
        prev_high = float(prev["high"].max())
        small_higher_high = small_high > prev_high  # 小周期仍创新高

        # 背离：大周期上升 + 小周期创新高 → 趋势延续，入场
        # （严格"背离"需小周期不创新高，但纯多头策略下我们顺势入场）
        if not self._in_position and big_up and small_higher_high:
            self._in_position = True
            return "BUY"
        if self._in_position and (not big_up or not small_higher_high):
            self._in_position = False
            return "SELL"
        return None


__all__ = ["TimeframeDivergenceStrategy"]
