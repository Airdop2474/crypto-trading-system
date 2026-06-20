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
        "max_consecutive_losses": {"type": int,   "min": 1,             "default": 3},
        "max_daily_loss":         {"type": float, "min": 0,  "max": 0.1, "default": 0.02},
    }

    def __init__(
        self,
        lookback: int = 10,
        max_consecutive_losses: int = 3,
        max_daily_loss: float = 0.02,
        initial_capital: float = 10000.0,
    ):
        super().__init__(
            name="MarketStructure",
            max_consecutive_losses=max_consecutive_losses,
            max_daily_loss=max_daily_loss,
            initial_capital=initial_capital,
        )

        if lookback < 3:
            raise ValueError("lookback must be >= 3")
        self.lookback = lookback

        self._in_position = False
        self._swing_high: Optional[float] = None
        self._swing_low: Optional[float] = None

        self.set_parameters(lookback=lookback)
        self._init_risk_state()

        logger.info(f"MarketStructure initialized: lookback={lookback}")

    def reset(self):
        super().reset()
        self._in_position = False
        self._swing_high = None
        self._swing_low = None

    def on_bar(self, data: pd.DataFrame, current_time: datetime) -> Optional[str]:
        if len(data) < self.lookback:
            return None

        if self._is_paused():
            return None

        close = float(data["close"].iloc[-1])

        # 初始化 swing points（用 lookback 窗口的极值）
        if self._swing_high is None:
            window = data.iloc[-self.lookback:]
            self._swing_high = float(window["high"].max())
            self._swing_low = float(window["low"].min())

        # ---- 关键修正：先判断入场/出场，再更新 swing points ----
        # 原稿中存在顺序 bug：如果先更新 swing_high = close，
        # 再判断 close > swing_high，则永远为 False，信号永远不会触发。
        signal: Optional[str] = None

        if not self._in_position:
            if close > self._swing_high:
                self._in_position = True
                signal = "BUY"
        else:
            if close < self._swing_low:
                self._in_position = False
                signal = "SELL"

        # 更新 swing points（只在创新高/新低时更新）
        if close > self._swing_high:
            self._swing_high = close
        if close < self._swing_low:
            self._swing_low = close

        return signal
