"""
SuperTrend 策略

基于 ATR 的动态趋势跟踪指标。相比 Donchian Channel 和双均线，
SuperTrend 自带波动率调整，在高波动时放宽止损、低波动时收紧止损，
对假突破的过滤更好。

核心优势：出场逻辑内建（SuperTrend 线反向信号即出场），
不依赖固定回看窗口（由 ATR 自适应）。

适用环境：趋势市场。
不适用环境：横盘震荡（频繁翻转）。
"""

from typing import Optional
from datetime import datetime

import pandas as pd

from src.strategy.risk_aware import RiskAwareStrategy
from src.utils.logger import logger


class SuperTrendStrategy(RiskAwareStrategy):
    """SuperTrend 策略

    逻辑：
    - 计算 ATR(period)
    - 上轨 = hl2 + multiplier × ATR
    - 下轨 = hl2 - multiplier × ATR
    - SuperTrend 方向翻转 → 入场/出场

    优势：出场逻辑内建，止损由波动率自适应。
    """

    PARAM_SCHEMA = {
        "period":                  {"type": int,   "min": 2,   "max": 50,  "default": 10},
        "multiplier":              {"type": float, "min": 0.5, "max": 5.0, "default": 3.0},
        "max_consecutive_losses":  {"type": int,   "min": 1,              "default": 3},
        "max_daily_loss":          {"type": float, "min": 0,   "max": 0.1, "default": 0.02},
    }

    def __init__(
        self,
        period: int = 10,
        multiplier: float = 3.0,
        max_consecutive_losses: int = 3,
        max_daily_loss: float = 0.02,
        initial_capital: float = 10000.0,
    ):
        super().__init__(
            name="SuperTrend",
            max_consecutive_losses=max_consecutive_losses,
            max_daily_loss=max_daily_loss,
            initial_capital=initial_capital,
        )

        if period < 2:
            raise ValueError("period must be >= 2")
        if multiplier <= 0:
            raise ValueError("multiplier must be positive")
        self.period = period
        self.multiplier = multiplier

        self._in_position = False
        self._trend_up: Optional[bool] = None  # True=上升趋势，False=下降趋势

        self.set_parameters(period=period, multiplier=multiplier)
        self._init_risk_state()

        logger.info(
            f"SuperTrend initialized: period={period}, multiplier={multiplier}"
        )

    def reset(self):
        super().reset()
        self._in_position = False
        self._trend_up = None

    def on_bar(self, data: pd.DataFrame, current_time: datetime) -> Optional[str]:
        if len(data) < self.period + 1:
            return None

        if self._is_paused():
            return None

        close = data["close"]
        high = data["high"]
        low = data["low"]
        current_close = float(close.iloc[-1])

        # 计算 ATR（全量 rolling 实现）
        atr = self._calc_atr(high, low, close, self.period)
        hl2 = (float(high.iloc[-1]) + float(low.iloc[-1])) / 2.0

        upper_band = hl2 + self.multiplier * atr
        lower_band = hl2 - self.multiplier * atr

        # 判断 SuperTrend 方向
        # 初值：当前价在下轨之上 → 上升趋势
        if self._trend_up is None:
            self._trend_up = current_close > lower_band

        # SuperTrend 方向更新（单向翻转）
        if self._trend_up:
            if current_close < lower_band:
                self._trend_up = False  # 趋势翻转向下
        else:
            if current_close > upper_band:
                self._trend_up = True   # 趋势翻转向上

        # 信号生成
        if not self._in_position:
            if self._trend_up:
                self._in_position = True
                return "BUY"
        else:
            if not self._trend_up:
                self._in_position = False
                return "SELL"

        return None

    @staticmethod
    def _calc_atr(
        high: pd.Series, low: pd.Series, close: pd.Series, period: int
    ) -> float:
        """计算 ATR（全量 rolling 实现）"""
        prev_close = close.shift(1)
        tr = pd.concat([
            high - low,
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ], axis=1).max(axis=1)
        return float(tr.rolling(period).mean().iloc[-1])
