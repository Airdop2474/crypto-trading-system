"""
MACD 策略

基于 MACD 指标的趋势跟踪策略：
- MACD 线（快EMA - 慢EMA）上穿信号线 → BUY
- MACD 线（快EMA - 慢EMA）下穿信号线 → SELL
- 柱状图方向确认信号可靠性

所有计算使用增量 EMA（O(1) per bar）。
"""

from typing import Optional, List
from datetime import datetime
import pandas as pd

from src.strategy.risk_aware import RiskAwareStrategy
from src.strategy.base import Order


class MACDStrategy(RiskAwareStrategy):
    """
    MACD 趋势跟踪策略。

    适用环境：趋势市场。与网格/布林带均值回归互补。
    """

    PARAM_SCHEMA = {
        "fast_period": {"type": int, "min": 2, "max": 50},
        "slow_period": {"type": int, "min": 5, "max": 100},
        "signal_period": {"type": int, "min": 2, "max": 50},
        "position_fraction": {"type": float, "min": 0.05, "max": 1.0},
    }

    def __init__(
        self,
        fast_period: int = 12,
        slow_period: int = 26,
        signal_period: int = 9,
        position_fraction: float = 0.5,
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
        self.fast_period = fast_period
        self.slow_period = slow_period
        self.signal_period = signal_period
        self.position_fraction = position_fraction
        self.name = "MACD"
        self.parameters = {
            "fast_period": fast_period, "slow_period": slow_period,
            "signal_period": signal_period, "position_fraction": position_fraction,
        }

        # 增量 EMA 状态
        self._fast_ema: Optional[float] = None
        self._slow_ema: Optional[float] = None
        self._signal_ema: Optional[float] = None
        self._prev_macd: Optional[float] = None
        self._bar_count: int = 0
        self._last_signal: Optional[str] = None

    def reset(self) -> None:
        super().reset()
        self._fast_ema = None
        self._slow_ema = None
        self._signal_ema = None
        self._prev_macd = None
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
        self._bar_count += 1

        # 增量 EMA：fast
        alpha_fast = 2.0 / (self.fast_period + 1)
        if self._fast_ema is None:
            self._fast_ema = close
        else:
            self._fast_ema = (close - self._fast_ema) * alpha_fast + self._fast_ema

        # 增量 EMA：slow
        alpha_slow = 2.0 / (self.slow_period + 1)
        if self._slow_ema is None:
            self._slow_ema = close
        else:
            self._slow_ema = (close - self._slow_ema) * alpha_slow + self._slow_ema

        # 样本不足（至少需要 slow_period 根才有意义）
        if self._bar_count < self.slow_period:
            return None

        # MACD 线
        macd = self._fast_ema - self._slow_ema

        # 增量 EMA：信号线
        alpha_sig = 2.0 / (self.signal_period + 1)
        if self._signal_ema is None:
            self._signal_ema = macd
            self._prev_macd = macd
            return None
        self._signal_ema = (macd - self._signal_ema) * alpha_sig + self._signal_ema

        # 信号判断：MACD 线与信号线交叉
        signal = None
        if self._prev_macd is not None and self._signal_ema is not None:
            prev_macd = self._prev_macd
            if prev_macd < self._signal_ema and macd >= self._signal_ema:
                signal = "BUY"
            elif prev_macd > self._signal_ema and macd <= self._signal_ema:
                signal = "SELL"

        self._prev_macd = macd

        if signal is None or signal == self._last_signal:
            return None
        self._last_signal = signal

        return [Order(side=signal, tag="macd", fraction=self.position_fraction)]

    def get_macd(self) -> dict:
        """返回当前 MACD 值（供前端展示）。"""
        return {
            "macd": round(self._prev_macd or 0, 4),
            "signal": round(self._signal_ema or 0, 4),
            "histogram": round((self._prev_macd or 0) - (self._signal_ema or 0), 4),
        }