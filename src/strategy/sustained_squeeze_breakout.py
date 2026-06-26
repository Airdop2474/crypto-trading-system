"""
持续收缩突破策略（纯 K 线）

振幅持续收缩后的大实体突破。系统首个"波动率状态"类策略。

逻辑：
  1. 连续 m 根振幅都 < 长期平均 × ratio（持续收缩）
  2. 收缩期结束后出现大实体 K（实体占比 ≥ 0.6）且突破收缩期 high/low → 入场
  3. 反向突破收缩期 low/high 离场

设计来源：纯 K 线策略方案 H3 变体，4 数据集均夏普 1.07。
适用环境：低波动收缩后的爆发期。不适用：已处于趋势中段。
"""

from typing import Optional
from datetime import datetime

import pandas as pd
import numpy as np

from src.strategy.risk_aware import RiskAwareStrategy
from src.utils.logger import logger


class SustainedSqueezeBreakoutStrategy(RiskAwareStrategy):
    """持续收缩突破策略

    要求连续 m 根振幅都低于长期平均 × ratio，确认"持续收缩"而非偶然低波动。
    突破根需大实体（实体占振幅 ≥ brk_body_pct）且突破收缩期区间。
    """

    PARAM_SCHEMA = {
        "long_period":    {"type": int,   "min": 20,  "max": 200, "default": 50},
        "squeeze_bars":   {"type": int,   "min": 2,   "max": 10,  "default": 3},
        "squeeze_ratio":  {"type": float, "min": 0.3, "max": 1.0, "default": 0.7},
        "brk_body_pct":   {"type": float, "min": 0.4, "max": 0.9, "default": 0.6},
    }

    def __init__(
        self,
        long_period: int = 50,
        squeeze_bars: int = 3,
        squeeze_ratio: float = 0.7,
        brk_body_pct: float = 0.6,
        max_consecutive_losses: int = 3,
        max_daily_loss: float = 0.02,
        initial_capital: float = 10000.0,
        stop_loss_config=None,
    ):
        super().__init__(
            name="SustainedSqueezeBreakout",
            max_consecutive_losses=max_consecutive_losses,
            max_daily_loss=max_daily_loss,
            initial_capital=initial_capital,
            stop_loss_config=stop_loss_config,
        )
        self.long_period = long_period
        self.squeeze_bars = squeeze_bars
        self.squeeze_ratio = squeeze_ratio
        self.brk_body_pct = brk_body_pct

        self._in_position = False
        self._entry_price: Optional[float] = None
        # 收缩期 high/low，作为离场参考
        self._squeeze_high: Optional[float] = None
        self._squeeze_low: Optional[float] = None

        self.set_parameters(
            long_period=long_period,
            squeeze_bars=squeeze_bars,
            squeeze_ratio=squeeze_ratio,
            brk_body_pct=brk_body_pct,
        )
        self._init_risk_state()
        logger.info(
            f"SustainedSqueezeBreakout initialized: long={long_period}, "
            f"squeeze_bars={squeeze_bars}, ratio={squeeze_ratio}"
        )

    def reset(self):
        super().reset()
        self._in_position = False
        self._entry_price = None
        self._squeeze_high = None
        self._squeeze_low = None

    def on_bar(self, data: pd.DataFrame, current_time: datetime) -> Optional[str]:
        need = self.long_period + self.squeeze_bars + 1
        if len(data) < need:
            return None

        if self._is_paused(current_time):
            return None

        row = data.iloc[-1]
        close = float(row["close"])
        open_ = float(row["open"])
        high = float(row["high"])
        low = float(row["low"])

        # 止损检查
        if self._in_position:
            triggered, reason = self._check_stop_loss(
                close, current_time, atr=None
            )
            if triggered:
                self._in_position = False
                self._entry_price = None
                return "SELL"

        # 计算近 long_period 根（不含当前）的平均振幅
        window = data.iloc[-(self.long_period + 1):-1]
        ranges = (window["high"] - window["low"]).values
        avg_range = float(ranges.mean())
        if avg_range <= 0:
            return None

        # 检查前 squeeze_bars 根（不含当前）是否都满足收缩
        prev_bars = data.iloc[-(self.squeeze_bars + 1):-1]
        prev_ranges = (prev_bars["high"] - prev_bars["low"]).values
        all_squeezed = all(r < avg_range * self.squeeze_ratio for r in prev_ranges)

        if not all_squeezed:
            # 维护持仓中的离场参考（即使无新信号）
            if self._in_position and self._squeeze_high is not None:
                if close < self._squeeze_low:
                    self._in_position = False
                    self._entry_price = None
                    return "SELL"
            return None

        # 记录收缩期 high/low（前 squeeze_bars 根的区间）
        self._squeeze_high = float(prev_bars["high"].max())
        self._squeeze_low = float(prev_bars["low"].min())

        # 当前根是否为大实体突破根
        cur_range = high - low
        if cur_range <= 0:
            return None
        body = abs(close - open_)
        body_pct = body / cur_range
        big_body = body_pct >= self.brk_body_pct

        if not big_body:
            return None

        if not self._in_position:
            # 突破收缩期上沿 → BUY
            if close > self._squeeze_high:
                self._in_position = True
                self._entry_price = close
                logger.info(
                    f"SustainedSqueezeBreakout BUY: close={close:.2f} "
                    f"> squeeze_high={self._squeeze_high:.2f} (body_pct={body_pct:.2f})"
                )
                return "BUY"
        else:
            # 跌破收缩期下沿 → SELL
            if close < self._squeeze_low:
                self._in_position = False
                self._entry_price = None
                logger.info(
                    f"SustainedSqueezeBreakout SELL: close={close:.2f} "
                    f"< squeeze_low={self._squeeze_low:.2f}"
                )
                return "SELL"

        return None


__all__ = ["SustainedSqueezeBreakoutStrategy"]
