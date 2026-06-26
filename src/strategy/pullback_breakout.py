from typing import Optional
from datetime import datetime

import pandas as pd
import numpy as np

from src.strategy.risk_aware import RiskAwareStrategy
from src.utils.logger import logger


class PullbackBreakoutStrategy(RiskAwareStrategy):
    """回踩突破策略

    前 m 根内曾突破前 n high，当前 close 回踩到突破点 ±tol_pct 入场。
    跌破 n low 离场。
    """

    PARAM_SCHEMA = {
        "n":       {"type": int,   "min": 5, "max": 100, "default": 20},
        "m":       {"type": int,   "min": 1, "max": 10,  "default": 3},
        "tol_pct": {"type": float, "min": 0.001, "max": 0.05, "default": 0.005},
    }

    def __init__(self, n=20, m=3, tol_pct=0.005,
                 max_consecutive_losses=3, max_daily_loss=0.02,
                 initial_capital=10000.0, stop_loss_config=None):
        super().__init__(name="PullbackBreakout",
                         max_consecutive_losses=max_consecutive_losses,
                         max_daily_loss=max_daily_loss,
                         initial_capital=initial_capital,
                         stop_loss_config=stop_loss_config)
        self.n = n
        self.m = m
        self.tol_pct = tol_pct
        self._in_position = False
        self._breakout_price = None
        self.set_parameters(n=n, m=m, tol_pct=tol_pct)
        self._init_risk_state()
        logger.info(f"PullbackBreakout initialized: n={n}, m={m}")

    def reset(self):
        super().reset()
        self._in_position = False
        self._breakout_price = None

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
            # 跌破 n low 离场
            window = data.iloc[-(self.n + 1):-1]
            win_low = float(window["low"].min())
            if close < win_low:
                self._in_position = False
                return "SELL"

        # 前 m 根（不含当前）的 high 与各自 n high 比较
        # 简化：找近 m+1 根中是否有 close > n_high 的根
        broke_up_recent = False
        breakout_p = None
        for i in range(-self.m - 1, 0):
            # data.iloc[i] 对应 m 根之一
            past = data.iloc[i - self.n:i]
            hh = float(past["high"].max())
            ci = float(data.iloc[i]["close"])
            if ci > hh:
                broke_up_recent = True
                breakout_p = hh
                break

        if not broke_up_recent or breakout_p is None:
            return None

        if not self._in_position:
            # 当前 close 回踩到突破点附近
            if abs(close - breakout_p) / max(breakout_p, 1e-9) <= self.tol_pct and close >= breakout_p * 0.99:
                self._in_position = True
                return "BUY"
        return None


__all__ = ["PullbackBreakoutStrategy"]
