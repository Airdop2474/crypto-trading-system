from typing import Optional
from datetime import datetime

import pandas as pd
import numpy as np

from src.strategy.risk_aware import RiskAwareStrategy
from src.utils.logger import logger


class MultiTimeframeConfluenceStrategy(RiskAwareStrategy):
    """多周期共振策略

    大周期（默认 4h）方向判断 + 小周期（当前数据）信号。
    大周期上升（近 n2 根 HH/HL 简化版：后半段 high > 前半段 high 且 low > 前半段 low）
    + 小周期突破 → 入场。

    参数：
      trend_lookback: 大周期趋势判断窗口（以小周期根数计，如 4h×4=16 根 1h）
      signal_period:  小周期突破窗口
    """

    PARAM_SCHEMA = {
        "trend_lookback": {"type": int, "min": 10, "max": 200, "default": 20},
        "signal_period":  {"type": int, "min": 3, "max": 50, "default": 10},
    }

    def __init__(self, trend_lookback=20, signal_period=10,
                 max_consecutive_losses=3, max_daily_loss=0.02,
                 initial_capital=10000.0, stop_loss_config=None):
        super().__init__(name="MultiTimeframeConfluence",
                         max_consecutive_losses=max_consecutive_losses,
                         max_daily_loss=max_daily_loss,
                         initial_capital=initial_capital,
                         stop_loss_config=stop_loss_config)
        if trend_lookback < signal_period * 2:
            raise ValueError("trend_lookback should be >= signal_period * 2")
        self.trend_lookback = trend_lookback
        self.signal_period = signal_period
        self._in_position = False
        self.set_parameters(trend_lookback=trend_lookback, signal_period=signal_period)
        self._init_risk_state()
        logger.info(f"MultiTimeframeConfluence initialized: trend={trend_lookback}, sig={signal_period}")

    def reset(self):
        super().reset()
        self._in_position = False

    def on_bar(self, data, current_time):
        if len(data) < self.trend_lookback + 1:
            return None
        if self._is_paused(current_time):
            return None
        close = float(data["close"].iloc[-1])
        if self._in_position:
            t, _ = self._check_stop_loss(close, current_time, atr=None)
            if t:
                self._in_position = False
                return "SELL"

        # 大周期趋势：前后半段 high/low 比较
        trend_window = data.iloc[-(self.trend_lookback + 1):-1]
        half = self.trend_lookback // 2
        first_half = trend_window.iloc[:half]
        second_half = trend_window.iloc[half:]
        big_uptrend = (float(second_half["high"].max()) > float(first_half["high"].max())
                       and float(second_half["low"].min()) > float(first_half["low"].min()))

        # 小周期突破信号
        sig_window = data.iloc[-(self.signal_period + 1):-1]
        sig_high = float(sig_window["high"].max())
        sig_low = float(sig_window["low"].min())

        if not self._in_position:
            if big_uptrend and close > sig_high:
                self._in_position = True
                return "BUY"
        else:
            if close < sig_low:
                self._in_position = False
                return "SELL"
        return None


__all__ = ["MultiTimeframeConfluenceStrategy"]
