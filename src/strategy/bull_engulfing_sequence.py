from typing import Optional
from datetime import datetime

import pandas as pd
import numpy as np

from src.strategy.risk_aware import RiskAwareStrategy
from src.utils.logger import logger


class BullEngulfingSequenceStrategy(RiskAwareStrategy):
    """阳包阴序列策略

    近 m 组每组都出现"反向 K 被更大同向 K 覆盖"。
    反向吞没序列离场。
    """

    PARAM_SCHEMA = {
        "m": {"type": int, "min": 1, "max": 5, "default": 2},
    }

    def __init__(self, m=2,
                 max_consecutive_losses=3, max_daily_loss=0.02,
                 initial_capital=10000.0, stop_loss_config=None):
        super().__init__(name="BullEngulfingSeq",
                         max_consecutive_losses=max_consecutive_losses,
                         max_daily_loss=max_daily_loss,
                         initial_capital=initial_capital,
                         stop_loss_config=stop_loss_config)
        self.m = m
        self._in_position = False
        self.set_parameters(m=m)
        self._init_risk_state()
        logger.info(f"BullEngulfingSeq initialized: m={m}")

    def reset(self):
        super().reset()
        self._in_position = False

    def on_bar(self, data, current_time):
        need = self.m * 2 + 1
        if len(data) < need + 1:
            return None
        if self._is_paused(current_time):
            return None
        close = float(data["close"].iloc[-1])
        if self._in_position:
            t, _ = self._check_stop_loss(close, current_time, atr=None)
            if t:
                self._in_position = False
                return "SELL"

        # 检查近 m*2 根的吞没序列
        window = data.iloc[-(self.m * 2 + 1):-1]
        bull_engulf_cnt = 0
        bear_engulf_cnt = 0
        for i in range(1, len(window)):
            prev_o = float(window.iloc[i - 1]["open"])
            prev_c = float(window.iloc[i - 1]["close"])
            curr_o = float(window.iloc[i]["open"])
            curr_c = float(window.iloc[i]["close"])
            prev_bear = prev_c < prev_o
            prev_bull = prev_c > prev_o
            curr_bull = curr_c > curr_o
            curr_bear = curr_c < curr_o
            curr_body = abs(curr_c - curr_o)
            prev_body = abs(prev_c - prev_o)
            if prev_bear and curr_bull and curr_body > prev_body:
                bull_engulf_cnt += 1
            if prev_bull and curr_bear and curr_body > prev_body:
                bear_engulf_cnt += 1

        # 当前根是否也是吞没
        row = data.iloc[-1]
        prev = data.iloc[-2]
        curr_o = float(row["open"]); curr_c = float(row["close"])
        prev_o = float(prev["open"]); prev_c = float(prev["close"])
        curr_body = abs(curr_c - curr_o)
        prev_body = abs(prev_c - prev_o)
        curr_bull_engulf = prev_c < prev_o and curr_c > curr_o and curr_body > prev_body
        curr_bear_engulf = prev_c > prev_o and curr_c < curr_o and curr_body > prev_body

        if not self._in_position and curr_bull_engulf and bull_engulf_cnt >= self.m - 1:
            self._in_position = True
            return "BUY"
        if self._in_position and curr_bear_engulf and bear_engulf_cnt >= self.m - 1:
            self._in_position = False
            return "SELL"
        return None


__all__ = ["BullEngulfingSequenceStrategy"]
