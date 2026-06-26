from typing import Optional
from datetime import datetime

import pandas as pd
import numpy as np

from src.strategy.risk_aware import RiskAwareStrategy
from src.utils.logger import logger


class ConsecutiveFakeoutStrategy(RiskAwareStrategy):
    """连续假突破策略

    近 m 根内出现 ≥2 次假突破，最后一次反向入场。
    反向突破离场。
    """

    PARAM_SCHEMA = {
        "n": {"type": int, "min": 5, "max": 100, "default": 20},
        "m": {"type": int, "min": 2, "max": 20,  "default": 5},
    }

    def __init__(self, n=20, m=5,
                 max_consecutive_losses=3, max_daily_loss=0.02,
                 initial_capital=10000.0, stop_loss_config=None):
        super().__init__(name="ConsecutiveFakeout",
                         max_consecutive_losses=max_consecutive_losses,
                         max_daily_loss=max_daily_loss,
                         initial_capital=initial_capital,
                         stop_loss_config=stop_loss_config)
        self.n = n
        self.m = m
        self._in_position = False
        self.set_parameters(n=n, m=m)
        self._init_risk_state()
        logger.info(f"ConsecutiveFakeout initialized: n={n}, m={m}")

    def reset(self):
        super().reset()
        self._in_position = False

    def on_bar(self, data, current_time):
        if len(data) < self.n + self.m + 1:
            return None
        if self._is_paused(current_time):
            return None
        close = float(data["close"].iloc[-1])
        if self._in_position:
            t, _ = self._check_stop_loss(close, current_time, atr=None)
            if t:
                self._in_position = False
                return "SELL"

        row = data.iloc[-1]
        h = float(row["high"]); l = float(row["low"])
        # 当前根是否假突破
        # 用各自时点的前 n high/low（简化为同一窗口）
        window = data.iloc[-(self.n + 1):-1]
        win_high = float(window["high"].max())
        win_low = float(window["low"].min())

        curr_fake_up = h > win_high and close < win_high
        curr_fake_dn = l < win_low and close > win_low

        # 近 m 根（不含当前）的假突破次数
        prev_bars = data.iloc[-(self.m + 1):-1]
        fake_up_cnt = 0
        fake_dn_cnt = 0
        for j in range(self.n, len(prev_bars)):
            # 简化：用窗口 high/low 判断
            ph = float(prev_bars.iloc[j]["high"])
            pl = float(prev_bars.iloc[j]["low"])
            pc = float(prev_bars.iloc[j]["close"])
            if ph > win_high and pc < win_high:
                fake_up_cnt += 1
            if pl < win_low and pc > win_low:
                fake_dn_cnt += 1

        if not self._in_position:
            # 当前下扫假突破 + 历史有 ≥1 次下扫假突破
            if curr_fake_dn and fake_dn_cnt >= 1:
                self._in_position = True
                return "BUY"
        else:
            if curr_fake_up and fake_up_cnt >= 1:
                self._in_position = False
                return "SELL"
            if close > win_high:
                self._in_position = False
                return "SELL"
        return None


__all__ = ["ConsecutiveFakeoutStrategy"]
