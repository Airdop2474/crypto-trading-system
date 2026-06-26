"""
收盘突破策略（纯 K 线，单级）

与现有 DonchianChannel 的差异：
  - DonchianChannel 用 ATR trailing 止损 + 通道中线离场
  - 本策略用反向突破离场（跌破 n low → SELL），无 ATR 依赖

设计来源：纯 K 线策略方案 D1 变体。
适用环境：趋势启动期。4h 周期表现优于 1h。
"""

from typing import Optional
from datetime import datetime

import pandas as pd

from src.strategy.risk_aware import RiskAwareStrategy
from src.utils.logger import logger


class CloseBreakoutStrategy(RiskAwareStrategy):
    """收盘突破策略

    close > 前 n 根 high → BUY；close < 前 n 根 low → SELL(平仓)。
    无 ATR 止损，纯结构离场。
    """

    PARAM_SCHEMA = {
        "period": {"type": int, "min": 5, "max": 100, "default": 20},
    }

    def __init__(
        self,
        period: int = 20,
        max_consecutive_losses: int = 3,
        max_daily_loss: float = 0.02,
        initial_capital: float = 10000.0,
        stop_loss_config=None,
    ):
        super().__init__(
            name="CloseBreakout",
            max_consecutive_losses=max_consecutive_losses,
            max_daily_loss=max_daily_loss,
            initial_capital=initial_capital,
            stop_loss_config=stop_loss_config,
        )
        if period < 2:
            raise ValueError("period must be >= 2")
        self.period = period

        self._in_position = False
        self._entry_price: Optional[float] = None

        self.set_parameters(period=period)
        self._init_risk_state()
        logger.info(f"CloseBreakout initialized: period={period}")

    def reset(self):
        super().reset()
        self._in_position = False
        self._entry_price = None

    def on_bar(self, data: pd.DataFrame, current_time: datetime) -> Optional[str]:
        if len(data) < self.period + 1:
            return None

        if self._is_paused(current_time):
            return None

        close = float(data["close"].iloc[-1])

        # 止损检查
        if self._in_position:
            triggered, reason = self._check_stop_loss(
                close, current_time, atr=None
            )
            if triggered:
                self._in_position = False
                self._entry_price = None
                return "SELL"

        # 前 n 根（不含当前）的 high/low
        window = data.iloc[-(self.period + 1):-1]
        win_high = float(window["high"].max())
        win_low = float(window["low"].min())

        if not self._in_position:
            if close > win_high:
                self._in_position = True
                self._entry_price = close
                logger.info(
                    f"CloseBreakout BUY: close={close:.2f} > high={win_high:.2f}"
                )
                return "BUY"
        else:
            if close < win_low:
                self._in_position = False
                self._entry_price = None
                logger.info(
                    f"CloseBreakout SELL: close={close:.2f} < low={win_low:.2f}"
                )
                return "SELL"

        return None


__all__ = ["CloseBreakoutStrategy"]
