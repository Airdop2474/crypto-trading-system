"""
Bollinger Bands 均值回归策略

基于布林带通道 + RSI 确认的超买超卖反转策略。

信号逻辑：
    - 价格触及下轨（close ≤ lower_band）且 RSI < oversold → BUY
    - 价格触及上轨（close ≥ upper_band）且 RSI > overbought → SELL
    - 无仓位时不追，已有反向仓位时才入场

适用环境：震荡/盘整市场，与趋势策略（MA/SuperTrend）互补。
"""

from typing import Optional, List
from datetime import datetime
from collections import deque
import pandas as pd
import numpy as np

from src.strategy.risk_aware import RiskAwareStrategy
from src.strategy.base import Order


class BollingerBandsStrategy(RiskAwareStrategy):
    """
    布林带均值回归策略。

    价格触及通道边界 + RSI 确认 → 反转入场。
    """

    PARAM_SCHEMA = {
        "bb_period": {"type": int, "min": 5, "max": 100},
        "bb_std": {"type": float, "min": 1.0, "max": 4.0},
        "oversold": {"type": float, "min": 0, "max": 100},
        "overbought": {"type": float, "min": 0, "max": 100},
        "rsi_period": {"type": int, "min": 2, "max": 50},
        "position_fraction": {"type": float, "min": 0.05, "max": 1.0},
        "enable_adx_filter": {"type": bool},
        "adx_period": {"type": int, "min": 5, "max": 30},
    }

    def __init__(
        self,
        bb_period: int = 20,
        bb_std: float = 2.0,
        oversold: float = 30.0,
        overbought: float = 70.0,
        rsi_period: int = 14,
        position_fraction: float = 0.5,
        enable_adx_filter: bool = False,
        adx_period: int = 14,
        max_consecutive_losses: int = 3,
        max_daily_loss: float = 0.02,
        max_drawdown: float = 0.15,
        initial_capital: float = 10000.0,
        stop_loss_config=None,
    ):
        super().__init__(
            max_consecutive_losses=max_consecutive_losses,
            max_daily_loss=max_daily_loss,
            max_drawdown=max_drawdown,
            initial_capital=initial_capital,
            stop_loss_config=stop_loss_config,
        )
        self.bb_period = bb_period
        self.bb_std = bb_std
        self.oversold = oversold
        self.overbought = overbought
        self.rsi_period = rsi_period
        self.position_fraction = position_fraction
        self.enable_adx_filter = enable_adx_filter
        self.name = "BollingerBands"
        self.parameters = {
            "bb_period": bb_period, "bb_std": bb_std,
            "oversold": oversold, "overbought": overbought,
            "rsi_period": rsi_period, "position_fraction": position_fraction,
            "enable_adx_filter": enable_adx_filter,
        }

        # ADX 初始化
        self._init_adx(adx_period)

        # 增量计算状态
        self._price_buffer: List[float] = []
        self._price_deque: deque = deque(maxlen=self.bb_period)
        self._price_sum: float = 0.0
        self._price_sq_sum: float = 0.0
        self._rsi_gain_buffer: List[float] = []
        self._rsi_loss_buffer: List[float] = []
        self._avg_gain: float = 0.0
        self._avg_loss: float = 0.0
        self._prev_close: Optional[float] = None
        self._prev_rsi: Optional[float] = None
        self._bar_count: int = 0
        self._last_signal: Optional[str] = None

    def reset(self) -> None:
        super().reset()
        self._price_buffer.clear()
        self._price_deque.clear()
        self._price_sum = 0.0
        self._price_sq_sum = 0.0
        self._avg_gain = 0.0
        self._avg_loss = 0.0
        self._rsi_gain_buffer.clear()
        self._rsi_loss_buffer.clear()
        self._init_adx(self._adx_period)
        self._prev_close = None
        self._prev_rsi = None
        self._bar_count = 0
        self._last_signal = None

    def on_bar(
        self,
        data: pd.DataFrame,
        current_time: Optional[datetime] = None,
    ) -> Optional[List[Order]]:
        if self._is_paused(current_time):
            return None

        # 止损检查（在策略逻辑之前）
        if self._last_signal == "BUY":
            triggered, reason = self._check_stop_loss(
                float(data["close"].iloc[-1]), current_time, atr=None
            )
            if triggered:
                self._last_signal = "SELL"
                return [Order(side="SELL", tag="stop_loss", fraction=self.position_fraction)]

        close = float(data["close"].iloc[-1])
        high = float(data["high"].iloc[-1])
        low = float(data["low"].iloc[-1])
        self._bar_count += 1

        # ADX 增量更新
        self._update_adx(high, low, close)

        # 1. 增量更新价格缓冲区（供 get_bands 使用）
        self._price_buffer.append(close)
        if len(self._price_buffer) > self.bb_period * 3:
            self._price_buffer = self._price_buffer[-(self.bb_period * 3):]

        # 增量更新 deque + 滚动求和（O(1) SMA/Std）
        if len(self._price_deque) == self.bb_period:
            old = self._price_deque[0]
            self._price_sum -= old
            self._price_sq_sum -= old * old
        self._price_deque.append(close)
        self._price_sum += close
        self._price_sq_sum += close * close

        # 样本不足
        if self._bar_count < self.bb_period + self.rsi_period:
            self._prev_close = close
            return None

        # ADX 趋势过滤（布林带均值回归只在震荡市交易）
        if self.enable_adx_filter and self._is_trending():
            return None

        # 2. 计算布林带（增量 SMA/Std，O(1)）
        n = self.bb_period
        if len(self._price_deque) < n:
            self._prev_close = close
            return None

        sma = self._price_sum / n
        var = self._price_sq_sum / n - sma * sma
        if var < 0:
            var = 0.0
        std = (var * n / (n - 1)) ** 0.5
        upper_band = sma + self.bb_std * std
        lower_band = sma - self.bb_std * std

        # 3. 增量 RSI（纯 Wilder 平滑）
        if self._prev_close is not None:
            change = close - self._prev_close
            gain = max(change, 0)
            loss = abs(min(change, 0))

            if self._prev_rsi is None:
                # 种子阶段：累积 gain/loss，满 period 后用 SMA 初始化一次
                self._rsi_gain_buffer.append(gain)
                self._rsi_loss_buffer.append(loss)
                if len(self._rsi_gain_buffer) >= self.rsi_period:
                    self._avg_gain = sum(self._rsi_gain_buffer[-self.rsi_period:]) / self.rsi_period
                    self._avg_loss = sum(self._rsi_loss_buffer[-self.rsi_period:]) / self.rsi_period
                    rsi = 100 - (100 / (1 + self._avg_gain / self._avg_loss)) if self._avg_loss > 0 else 100.0
                    self._prev_rsi = rsi
            else:
                # Wilder 平滑：纯增量
                self._avg_gain = (self._avg_gain * (self.rsi_period - 1) + gain) / self.rsi_period
                self._avg_loss = (self._avg_loss * (self.rsi_period - 1) + loss) / self.rsi_period
                rsi = 100 - (100 / (1 + self._avg_gain / self._avg_loss)) if self._avg_loss > 0 else 100.0
                self._prev_rsi = rsi
                # 保留 buffer 供调试
                self._rsi_gain_buffer.append(gain)
                self._rsi_loss_buffer.append(loss)
                if len(self._rsi_gain_buffer) > self.rsi_period * 3:
                    self._rsi_gain_buffer = self._rsi_gain_buffer[-(self.rsi_period * 3):]
                    self._rsi_loss_buffer = self._rsi_loss_buffer[-(self.rsi_period * 3):]
        else:
            self._prev_close = close
            return None

        if self._prev_rsi is None:
            self._prev_close = close
            return None

        # 4. 信号逻辑：触带即信号
        signal = None

        if close >= upper_band:
            signal = "SELL"
        elif close <= lower_band:
            signal = "BUY"

        self._prev_close = close

        if signal is None:
            return None

        # 避免重复同向信号
        if signal == self._last_signal:
            return None
        self._last_signal = signal

        fraction = self.position_fraction
        return [Order(side=signal, tag="bb", fraction=fraction)]

    def get_bands(self) -> dict:
        """返回当前布林带值（供前端展示）。"""
        if len(self._price_buffer) < self.bb_period:
            return {"middle": 0, "upper": 0, "lower": 0, "rsi": 0}
        recent = self._price_buffer[-self.bb_period:]
        sma = float(np.mean(recent))
        std = float(np.std(recent, ddof=1))
        return {
            "middle": round(sma, 2),
            "upper": round(sma + self.bb_std * std, 2),
            "lower": round(sma - self.bb_std * std, 2),
            "rsi": round(self._prev_rsi or 0, 2),
        }

