"""
多级突破策略（纯 K 线）

短期 + 长期 high/low 同时突破才入场，过滤单级突破的假信号。
比 DonchianChannel 多了一层长期结构确认。

逻辑：
  1. 收盘同时突破短期(n1)和长期(n2) high → BUY
  2. 持仓中收盘跌破短期 low → SELL(结构破坏即离场)

设计来源：纯 K 线策略方案 D5 变体，4 数据集均夏普 1.28。
适用环境：趋势启动期。不适用：横盘震荡（频繁假突破）。
"""

from typing import Optional
from datetime import datetime

import pandas as pd

from src.strategy.risk_aware import RiskAwareStrategy
from src.utils.logger import logger


class MultiLevelBreakoutStrategy(RiskAwareStrategy):
    """多级突破策略

    要求收盘价同时突破短期和长期窗口的 high/low。
    双窗口共振过滤单级假突破，信号少但可靠性高。
    """

    PARAM_SCHEMA = {
        "short_period":      {"type": int,   "min": 5,   "max": 50,  "default": 10},
        "long_period":       {"type": int,   "min": 20,  "max": 200, "default": 50},
        "exit_on_short_low": {"type": bool,  "default": True},
    }

    def __init__(
        self,
        short_period: int = 10,
        long_period: int = 50,
        exit_on_short_low: bool = True,
        max_consecutive_losses: int = 3,
        max_daily_loss: float = 0.02,
        initial_capital: float = 10000.0,
        stop_loss_config=None,
    ):
        super().__init__(
            name="MultiLevelBreakout",
            max_consecutive_losses=max_consecutive_losses,
            max_daily_loss=max_daily_loss,
            initial_capital=initial_capital,
            stop_loss_config=stop_loss_config,
        )
        if short_period >= long_period:
            raise ValueError("short_period must be < long_period")
        self.short_period = short_period
        self.long_period = long_period
        self.exit_on_short_low = exit_on_short_low

        self._in_position = False
        self._entry_price: Optional[float] = None

        self.set_parameters(
            short_period=short_period,
            long_period=long_period,
            exit_on_short_low=exit_on_short_low,
        )
        self._init_risk_state()
        logger.info(
            f"MultiLevelBreakout initialized: short={short_period}, long={long_period}"
        )

    def reset(self):
        super().reset()
        self._in_position = False
        self._entry_price = None

    def on_bar(self, data: pd.DataFrame, current_time: datetime) -> Optional[str]:
        if len(data) < self.long_period + 1:
            return None

        if self._is_paused(current_time):
            return None

        close = float(data["close"].iloc[-1])

        # 止损检查（在策略逻辑之前）
        if self._in_position:
            triggered, reason = self._check_stop_loss(
                close, current_time, atr=None
            )
            if triggered:
                self._in_position = False
                self._entry_price = None
                return "SELL"

        # 计算前 n1/n2 根（不含当前）的 high/low
        window = data.iloc[-(self.long_period + 1):-1]
        short_window = window.iloc[-self.short_period:]

        short_high = float(short_window["high"].max())
        short_low = float(short_window["low"].min())
        long_high = float(window["high"].max())
        long_low = float(window["low"].min())

        if not self._in_position:
            # 双窗口共振突破
            if close > short_high and close > long_high:
                self._in_position = True
                self._entry_price = close
                logger.info(
                    f"MultiLevelBreakout BUY: close={close:.2f} "
                    f"> short_high={short_high:.2f} & long_high={long_high:.2f}"
                )
                return "BUY"
        else:
            # 离场：跌破短期 low（结构破坏即离场）
            if self.exit_on_short_low and close < short_low:
                self._in_position = False
                self._entry_price = None
                logger.info(
                    f"MultiLevelBreakout SELL: close={close:.2f} < short_low={short_low:.2f}"
                )
                return "SELL"

        return None


__all__ = ["MultiLevelBreakoutStrategy"]
