"""
Donchian Channel 突破策略

Richard Donchian 的经典趋势跟踪策略：价格突破 N 日最高价时买入，
跌破 N 日最低价时卖出。在强趋势市场中表现优异，与网格策略互补。

适用环境：趋势市场（尤其单边行情）。
不适用环境：横盘震荡（频繁假突破）。
"""

from typing import Optional
from datetime import datetime

import pandas as pd

from src.strategy.risk_aware import RiskAwareStrategy
from src.utils.logger import logger


class DonchianChannelStrategy(RiskAwareStrategy):
    """Donchian Channel 突破策略

    逻辑：
    - 上轨 = 过去 period 根 bar 最高价
    - 下轨 = 过去 period 根 bar 最低价
    - close > 上轨 → BUY
    - close < 下轨 → SELL
    - 出场后下轨作为追踪止损参考
    """

    PARAM_SCHEMA = {
        "period":                {"type": int,   "min": 5,  "max": 100, "default": 20},
        "max_consecutive_losses": {"type": int,   "min": 1,             "default": 3},
        "max_daily_loss":        {"type": float, "min": 0,  "max": 0.1, "default": 0.02},
    }

    def __init__(
        self,
        period: int = 20,
        max_consecutive_losses: int = 3,
        max_daily_loss: float = 0.02,
        initial_capital: float = 10000.0,
    ):
        super().__init__(
            name="DonchianChannel",
            max_consecutive_losses=max_consecutive_losses,
            max_daily_loss=max_daily_loss,
            initial_capital=initial_capital,
        )

        if period < 2:
            raise ValueError("period must be >= 2")
        self.period = period

        self._in_position = False
        self._upper: Optional[float] = None
        self._lower: Optional[float] = None

        self.set_parameters(period=period)
        self._init_risk_state()

        logger.info(f"DonchianChannel initialized: period={period}")

    def reset(self):
        super().reset()
        self._in_position = False
        self._upper = None
        self._lower = None

    def on_bar(self, data: pd.DataFrame, current_time: datetime) -> Optional[str]:
        if len(data) < self.period + 1:
            return None

        if self._is_paused():
            return None

        # 计算通道（用前 period 根 bar 的 OHLC 避免当前 bar 的前视偏差）
        window = data.iloc[-(self.period + 1):-1]
        self._upper = float(window["high"].max())
        self._lower = float(window["low"].min())

        current_price = float(data["close"].iloc[-1])

        if not self._in_position:
            if current_price > self._upper:
                self._in_position = True
                return "BUY"
        else:
            if current_price < self._lower:
                self._in_position = False
                return "SELL"

        return None
