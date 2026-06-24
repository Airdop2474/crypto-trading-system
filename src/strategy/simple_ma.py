"""
简单移动平均策略

金叉买入，死叉卖出。配合连亏/日亏损熔断保护（继承自 RiskAwareStrategy）。
"""

from typing import Optional
from datetime import datetime
import pandas as pd

from src.strategy.risk_aware import RiskAwareStrategy
from src.utils.logger import logger


class SimpleMAStrategy(RiskAwareStrategy):
    """
    简单移动平均策略

    逻辑：
    - 短期均线上穿长期均线：买入（金叉）
    - 短期均线下穿长期均线：卖出（死叉）

    风控（继承自 RiskAwareStrategy）：
    - 连亏熔断（默认 5 笔）
    - 当日亏损熔断（默认 2%）
    - 累计回撤熔断（默认 15%）
    """

    PARAM_SCHEMA = {
        "short_window": {"type": int, "min": 1},
        "long_window": {"type": int, "min": 1},
    }

    def __init__(
        self,
        short_window: int = 5,
        long_window: int = 10,
        max_consecutive_losses: int = 5,
        max_daily_loss: float = 0.02,
        initial_capital: float = 10000.0,
        stop_loss_config=None,
    ):
        super().__init__(
            name="SimpleMA",
            max_consecutive_losses=max_consecutive_losses,
            max_daily_loss=max_daily_loss,
            initial_capital=initial_capital,
            stop_loss_config=stop_loss_config,
        )
        self.short_window = short_window
        self.long_window = long_window

        self._in_position = False
        self._init_ma_state()
        self.set_parameters(short_window=short_window, long_window=long_window)

    def _init_ma_state(self) -> None:
        self._short_ma: Optional[float] = None
        self._long_ma: Optional[float] = None
        self._prev_short_ma: Optional[float] = None
        self._prev_long_ma: Optional[float] = None

    def on_bar(self, data: pd.DataFrame, current_time: datetime) -> Optional[str]:
        if len(data) < self.long_window:
            return None

        if self._is_paused(current_time):
            return None

        # 止损检查（在策略逻辑之前）
        if self._in_position:
            triggered, reason = self._check_stop_loss(
                float(data["close"].iloc[-1]), current_time, atr=None
            )
            if triggered:
                self._in_position = False
                return "SELL"

        close = data["close"]

        if self._short_ma is None:
            if len(close) < self.long_window:
                return None
            short_ma_series = close.rolling(window=self.short_window).mean()
            long_ma_series = close.rolling(window=self.long_window).mean()

            self._short_ma = float(short_ma_series.iloc[-1])
            self._long_ma = float(long_ma_series.iloc[-1])

            if len(close) > self.long_window:
                self._prev_short_ma = float(short_ma_series.iloc[-2])
                self._prev_long_ma = float(long_ma_series.iloc[-2])
            else:
                self._prev_short_ma = None
                self._prev_long_ma = None
        else:
            new_price = float(close.iloc[-1])
            if len(close) > self.short_window:
                old_price_short = float(close.iloc[-self.short_window - 1])
            else:
                old_price_short = float(close.iloc[0])
            if len(close) > self.long_window:
                old_price_long = float(close.iloc[-self.long_window - 1])
            else:
                old_price_long = float(close.iloc[0])

            self._prev_short_ma = self._short_ma
            self._prev_long_ma = self._long_ma
            self._short_ma += (new_price - old_price_short) / self.short_window
            self._long_ma += (new_price - old_price_long) / self.long_window

        if self._prev_short_ma is None or self._prev_long_ma is None:
            return None

        # 金叉：短均线上穿长期均线 → BUY
        if self._prev_short_ma <= self._prev_long_ma and self._short_ma > self._long_ma:
            if not self._in_position:
                self._in_position = True
                return "BUY"
        # 死叉：短均线下穿长期均线 → SELL
        elif self._prev_short_ma >= self._prev_long_ma and self._short_ma < self._long_ma:
            self._in_position = False
            return "SELL"

        return None

    def reset(self):
        """重置策略状态"""
        super().reset()
        self._init_ma_state()
        logger.debug("SimpleMA strategy reset")


# 导出
__all__ = ["SimpleMAStrategy"]
