"""
强势收盘动量策略（纯 K 线）

连续同向 K + 每根 close 在该根 high 的上 25% 区域（强势收盘）。
比单纯"连续阳/阴"更严格：不仅方向一致，且每根都收在高位/低位。

逻辑：
  1. 近 n 根全部同向（全阳/全阴）
  2. 每根 close 在该根 range 的强势区（上 top_pct 或下 top_pct）
  3. 当前根满足上述条件 → 顺势入场
  4. 反向：出现不满足强势收盘的同向 K 或反向 K → 离场

设计来源：纯 K 线策略方案 G4 变体，4 数据集均夏普 1.07。
适用环境：趋势确立后的动量延续期。不适用：震荡（频繁假信号）。
"""

from typing import Optional
from datetime import datetime

import pandas as pd
import numpy as np

from src.strategy.risk_aware import RiskAwareStrategy
from src.utils.logger import logger


class StrongCloseMomentumStrategy(RiskAwareStrategy):
    """强势收盘动量策略

    要求连续 n 根同向 + 每根收盘在强势区。
    比单纯连续同向更严格，捕捉"加速度"动量。
    """

    PARAM_SCHEMA = {
        "consecutive":  {"type": int,   "min": 2,   "max": 10,  "default": 3},
        "top_pct":      {"type": float, "min": 0.1, "max": 0.4, "default": 0.25},
    }

    def __init__(
        self,
        consecutive: int = 3,
        top_pct: float = 0.25,
        max_consecutive_losses: int = 3,
        max_daily_loss: float = 0.02,
        initial_capital: float = 10000.0,
        stop_loss_config=None,
    ):
        super().__init__(
            name="StrongCloseMomentum",
            max_consecutive_losses=max_consecutive_losses,
            max_daily_loss=max_daily_loss,
            initial_capital=initial_capital,
            stop_loss_config=stop_loss_config,
        )
        self.consecutive = consecutive
        self.top_pct = top_pct

        self._in_position = False
        self._entry_price: Optional[float] = None

        self.set_parameters(
            consecutive=consecutive,
            top_pct=top_pct,
        )
        self._init_risk_state()
        logger.info(
            f"StrongCloseMomentum initialized: consecutive={consecutive}, top_pct={top_pct}"
        )

    def reset(self):
        super().reset()
        self._in_position = False
        self._entry_price = None

    @staticmethod
    def _is_strong_bull(open_, high, low, close, top_pct):
        """阳线且 close 在该根 range 的上 (1-top_pct) 区域。"""
        if close <= open_:
            return False
        rng = high - low
        if rng <= 0:
            return False
        close_pos = (close - low) / rng
        return close_pos >= 1 - top_pct

    @staticmethod
    def _is_strong_bear(open_, high, low, close, top_pct):
        """阴线且 close 在该根 range 的下 top_pct 区域。"""
        if close >= open_:
            return False
        rng = high - low
        if rng <= 0:
            return False
        close_pos = (close - low) / rng
        return close_pos <= top_pct

    def on_bar(self, data: pd.DataFrame, current_time: datetime) -> Optional[str]:
        if len(data) < self.consecutive + 1:
            return None

        if self._is_paused(current_time):
            return None

        row = data.iloc[-1]
        close = float(row["close"])

        # 止损检查
        if self._in_position:
            triggered, reason = self._check_stop_loss(
                close, current_time, atr=None
            )
            if triggered:
                self._in_position = False
                self._entry_price = None
                return "SELL"

        # 检查近 consecutive 根（含当前）是否全部强势同向
        recent = data.iloc[-self.consecutive:]
        all_strong_bull = True
        all_strong_bear = True
        for _, bar in recent.iterrows():
            o, h, l, c = (
                float(bar["open"]), float(bar["high"]),
                float(bar["low"]), float(bar["close"]),
            )
            if not self._is_strong_bull(o, h, l, c, self.top_pct):
                all_strong_bull = False
            if not self._is_strong_bear(o, h, l, c, self.top_pct):
                all_strong_bear = False
            if not all_strong_bull and not all_strong_bear:
                break

        if not self._in_position:
            if all_strong_bull:
                self._in_position = True
                self._entry_price = close
                logger.info(
                    f"StrongCloseMomentum BUY: {self.consecutive} strong bulls "
                    f"close={close:.2f}"
                )
                return "BUY"
        else:
            # 离场：出现非强势阳线（动量衰竭）或反向强势
            curr_o = float(row["open"])
            curr_h = float(row["high"])
            curr_l = float(row["low"])
            curr_c = close
            still_strong = self._is_strong_bull(
                curr_o, curr_h, curr_l, curr_c, self.top_pct
            )
            reverse_signal = self._is_strong_bear(
                curr_o, curr_h, curr_l, curr_c, self.top_pct
            )
            if not still_strong or reverse_signal:
                self._in_position = False
                self._entry_price = None
                logger.info(
                    f"StrongCloseMomentum SELL: momentum exhausted close={close:.2f}"
                )
                return "SELL"

        return None


__all__ = ["StrongCloseMomentumStrategy"]
