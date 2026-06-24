"""
市场结构突破策略（Price Action）

基于传统 Wyckoff/Dow 理论的市场结构分析：
持续追踪 swing high / swing low，在结构突破时入场，
在结构破坏时出场。

与网格策略的互补关系：
- 网格适合震荡（区间内反复低买高卖）
- 结构突破适合趋势（突破关键位后吃大段）

适用环境：趋势市场，尤其结构清晰的单边行情。
不适用环境：窄幅横盘（结构不清晰，频繁假突破）。
"""

from typing import Optional
from datetime import datetime

import pandas as pd

from src.strategy.risk_aware import RiskAwareStrategy
from src.utils.logger import logger


class MarketStructureStrategy(RiskAwareStrategy):
    """市场结构突破策略

    逻辑：
    - swing_high: 自上次创新高以来的最高收盘价
    - swing_low:  自上次创新低以来的最低收盘价
    - close > swing_high → BUY（结构向上突破）
    - close < swing_low  → SELL（结构向下破坏）

    风控（继承自 RiskAwareStrategy）：
    - 连亏熔断（默认 3 笔）
    - 当日亏损熔断（默认 2%）
    - 累计回撤熔断（默认 15%）
    """

    PARAM_SCHEMA = {
        "lookback":               {"type": int,   "min": 3,  "max": 50,  "default": 10},
    }

    def __init__(
        self,
        lookback: int = 10,
        max_consecutive_losses: int = 3,
        max_daily_loss: float = 0.02,
        initial_capital: float = 10000.0,
        stop_loss_config=None,
    ):
        super().__init__(
            name="MarketStructure",
            max_consecutive_losses=max_consecutive_losses,
            max_daily_loss=max_daily_loss,
            initial_capital=initial_capital,
            stop_loss_config=stop_loss_config,
        )

        if lookback < 3:
            raise ValueError("lookback must be >= 3")
        self.lookback = lookback

        self._in_position = False

        self.set_parameters(lookback=lookback)
        self._init_risk_state()

        logger.info(f"MarketStructure initialized: lookback={lookback}")

    def reset(self):
        super().reset()
        self._in_position = False

    def on_bar(self, data: pd.DataFrame, current_time: datetime) -> Optional[str]:
        if len(data) < self.lookback:
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

        close = float(data["close"].iloc[-1])

        # 滚动窗口：用前 lookback 根 bar 的极值（排除当前 bar，否则 close 永远 <= swing_high）
        window = data.iloc[-(self.lookback + 1):-1]
        swing_high = float(window["high"].max())
        swing_low = float(window["low"].min())

        signal: Optional[str] = None

        if not self._in_position:
            if close > swing_high:
                self._in_position = True
                signal = "BUY"
        else:
            if close < swing_low:
                self._in_position = False
                signal = "SELL"

        return signal
