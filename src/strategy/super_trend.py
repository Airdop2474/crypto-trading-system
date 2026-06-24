"""
SuperTrend 策略

基于 ATR 的动态趋势跟踪指标。相比 Donchian Channel 和双均线，
SuperTrend 自带波动率调整，在高波动时放宽止损、低波动时收紧止损。

核心优势：出场逻辑内建（SuperTrend 线反向信号即出场），
不依赖固定回看窗口（由 ATR 自适应）。
"""

from typing import Optional
from datetime import datetime

import pandas as pd

from src.strategy.risk_aware import RiskAwareStrategy
from src.utils.logger import logger


class SuperTrendStrategy(RiskAwareStrategy):
    PARAM_SCHEMA = {
        "period":                  {"type": int,   "min": 2,   "max": 50,  "default": 10},
        "multiplier":              {"type": float, "min": 0.5, "max": 5.0, "default": 3.0},
    }

    def __init__(
        self,
        period: int = 10,
        multiplier: float = 3.0,
        max_consecutive_losses: int = 3,
        max_daily_loss: float = 0.02,
        initial_capital: float = 10000.0,
        stop_loss_config=None,
    ):
        super().__init__(
            name="SuperTrend",
            max_consecutive_losses=max_consecutive_losses,
            max_daily_loss=max_daily_loss,
            initial_capital=initial_capital,
            stop_loss_config=stop_loss_config,
        )
        if period < 2:
            raise ValueError("period must be >= 2")
        if multiplier <= 0:
            raise ValueError("multiplier must be positive")
        self.period = period
        self.multiplier = multiplier

        self._in_position = False
        self._trend_up: Optional[bool] = None

        # 增量 ATR 状态
        self._tr_window: list[float] = []
        self._tr_sum: float = 0.0
        self._prev_close_atr: Optional[float] = None

        # SuperTrend band 携带状态（关键：不能每根重算，需向前携带）
        self._prev_upper: Optional[float] = None
        self._prev_lower: Optional[float] = None

        self.set_parameters(period=period, multiplier=multiplier)
        self._init_risk_state()
        logger.info(f"SuperTrend initialized: period={period}, multiplier={multiplier}")

    def reset(self):
        super().reset()
        self._in_position = False
        self._trend_up = None
        self._tr_window.clear()
        self._tr_sum = 0.0
        self._prev_close_atr = None
        self._prev_upper = None
        self._prev_lower = None

    def _update_atr(self, high: float, low: float, close: float) -> Optional[float]:
        """增量 ATR，O(1) per bar。"""
        if self._prev_close_atr is None:
            self._prev_close_atr = close
            return None

        tr = max(high - low, abs(high - self._prev_close_atr), abs(low - self._prev_close_atr))
        self._prev_close_atr = close

        window_size = self.period
        if len(self._tr_window) >= window_size:
            self._tr_sum -= self._tr_window.pop(0)
        self._tr_window.append(tr)
        self._tr_sum += tr

        if len(self._tr_window) < window_size:
            return None
        return self._tr_sum / window_size

    def on_bar(self, data: pd.DataFrame, current_time: datetime) -> Optional[str]:
        if len(data) < self.period + 1:
            return None

        if self._is_paused(current_time):
            return None

        close = data["close"]
        current_close = float(close.iloc[-1])
        current_high = float(data["high"].iloc[-1])
        current_low = float(data["low"].iloc[-1])

        atr = self._update_atr(current_high, current_low, current_close)
        if atr is None:
            return None

        # 止损检查（在策略逻辑之前）
        if self._in_position:
            triggered, reason = self._check_stop_loss(
                current_close, current_time, atr=atr
            )
            if triggered:
                self._in_position = False
                return "SELL"

        hl2 = (current_high + current_low) / 2.0

        # 原始 band
        raw_upper = hl2 + self.multiplier * atr
        raw_lower = hl2 - self.multiplier * atr

        # SuperTrend 核心：band 向前携带，只在有利方向更新
        if self._prev_upper is None:
            self._prev_upper = raw_upper
            self._prev_lower = raw_lower
        else:
            # lower band：趋势向上时只上移（收紧），趋势向下时用原始值
            if self._trend_up is not None and self._trend_up:
                self._prev_lower = max(raw_lower, self._prev_lower) if current_close > self._prev_lower else raw_lower
            else:
                self._prev_lower = raw_lower
            # upper band：趋势向下时只下移（收紧），趋势向上时用原始值
            if self._trend_up is not None and not self._trend_up:
                self._prev_upper = min(raw_upper, self._prev_upper) if current_close < self._prev_upper else raw_upper
            else:
                self._prev_upper = raw_upper

        upper_band = self._prev_upper
        lower_band = self._prev_lower

        if self._trend_up is None:
            self._trend_up = current_close > lower_band

        if self._trend_up:
            if current_close < lower_band:
                self._trend_up = False
        else:
            if current_close > upper_band:
                self._trend_up = True

        if not self._in_position:
            if self._trend_up:
                self._in_position = True
                return "BUY"
        else:
            if not self._trend_up:
                self._in_position = False
                return "SELL"

        return None


__all__ = ["SuperTrendStrategy"]
