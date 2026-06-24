"""
Donchian Channel 突破策略

Richard Donchian 的经典趋势跟踪策略：价格突破 N 日最高价时买入，
跌破 N 日最低价时卖出。持仓期间用通道中线作追踪止损参考。

适用环境：趋势市场（尤其单边行情）。
不适用环境：横盘震荡（频繁假突破）。
"""

from typing import Optional
from datetime import datetime

import pandas as pd

from src.strategy.risk_aware import RiskAwareStrategy
from src.utils.logger import logger


class DonchianChannelStrategy(RiskAwareStrategy):
    PARAM_SCHEMA = {
        "period":                  {"type": int,   "min": 5,  "max": 100, "default": 20},
        "trailing_atr_mult":       {"type": float, "min": 0.5,"max": 5.0, "default": 2.0},
        "atr_period":              {"type": int,   "min": 2,  "max": 50,  "default": 14},
    }

    def __init__(
        self,
        period: int = 20,
        trailing_atr_mult: float = 2.0,
        atr_period: int = 14,
        max_consecutive_losses: int = 3,
        max_daily_loss: float = 0.02,
        initial_capital: float = 10000.0,
        stop_loss_config=None,
    ):
        super().__init__(
            name="DonchianChannel",
            max_consecutive_losses=max_consecutive_losses,
            max_daily_loss=max_daily_loss,
            initial_capital=initial_capital,
            stop_loss_config=stop_loss_config,
        )
        if period < 2:
            raise ValueError("period must be >= 2")
        self.period = period
        self.trailing_atr_mult = trailing_atr_mult
        self.atr_period = atr_period

        self._in_position = False
        self._entry_price: Optional[float] = None
        self._trailing_stop: Optional[float] = None

        # 增量 ATR 状态
        self._tr_window: list[float] = []
        self._tr_sum: float = 0.0
        self._prev_close_atr: Optional[float] = None

        self.set_parameters(period=period, trailing_atr_mult=trailing_atr_mult)
        self._init_risk_state()
        logger.info(f"DonchianChannel initialized: period={period}")

    def reset(self):
        super().reset()
        self._in_position = False
        self._entry_price = None
        self._trailing_stop = None
        self._tr_window.clear()
        self._tr_sum = 0.0
        self._prev_close_atr = None

    def _update_atr(self, high: float, low: float, close: float) -> Optional[float]:
        """增量 ATR，O(1) per bar。"""
        if self._prev_close_atr is None:
            self._prev_close_atr = close
            return None

        tr = max(high - low, abs(high - self._prev_close_atr), abs(low - self._prev_close_atr))
        self._prev_close_atr = close

        window_size = self.atr_period
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

        window = data.iloc[-(self.period + 1):-1]
        upper = float(window["high"].max())
        lower = float(window["low"].min())
        mid = (upper + lower) / 2.0

        current_price = float(data["close"].iloc[-1])
        atr = self._update_atr(
            float(data["high"].iloc[-1]),
            float(data["low"].iloc[-1]),
            current_price,
        )

        if not self._in_position:
            if current_price > upper:
                self._in_position = True
                self._entry_price = current_price
                self._trailing_stop = mid
                return "BUY"
        else:
            # 更新追踪止损（跟随通道中线上移）
            if atr is not None and self._entry_price is not None:
                candidate = mid

                # 只上移不止损收紧（前高型追踪）
                trailing_atr = self.trailing_atr_mult * atr
                candidate = max(candidate, self._entry_price - trailing_atr)

                if self._trailing_stop is not None:
                    candidate = max(candidate, self._trailing_stop)
                self._trailing_stop = candidate

            sell = False
            # 下破通道下线
            if current_price < lower:
                sell = True
            # ATR 追踪止损触发
            if self._trailing_stop is not None and current_price < self._trailing_stop:
                sell = True

            if sell:
                self._in_position = False
                self._entry_price = None
                self._trailing_stop = None
                return "SELL"

        return None


__all__ = ["DonchianChannelStrategy"]
