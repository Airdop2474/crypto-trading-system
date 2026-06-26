from typing import Optional
from datetime import datetime

import pandas as pd
import numpy as np

from src.strategy.risk_aware import RiskAwareStrategy
from src.utils.logger import logger


class BigBarStrategy(RiskAwareStrategy):
    """大实体策略

    当前实体 > 近 lookback 根平均实体 × mult 时入场。
    反向 K（反向实体 > 平均×mult）离场。
    """

    PARAM_SCHEMA = {
        "lookback": {"type": int,   "min": 5,  "max": 100, "default": 20},
        "mult":     {"type": float, "min": 1.2, "max": 5.0, "default": 2.0},
    }

    def __init__(self, lookback=20, mult=2.0,
                 max_consecutive_losses=3, max_daily_loss=0.02,
                 initial_capital=10000.0, stop_loss_config=None):
        super().__init__(name="BigBar",
                         max_consecutive_losses=max_consecutive_losses,
                         max_daily_loss=max_daily_loss,
                         initial_capital=initial_capital,
                         stop_loss_config=stop_loss_config)
        self.lookback = lookback
        self.mult = mult
        self._in_position = False
        self.set_parameters(lookback=lookback, mult=mult)
        self._init_risk_state()
        logger.info(f"BigBar initialized: lookback={lookback}, mult={mult}")

    def reset(self):
        super().reset()
        self._in_position = False

    def on_bar(self, data, current_time):
        if len(data) < self.lookback + 1:
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
        o = float(row["open"]); c = float(row["close"])
        body = abs(c - o)
        window = data.iloc[-(self.lookback + 1):-1]
        avg_body = float((window["close"] - window["open"]).abs().mean())
        if avg_body <= 0:
            return None
        big = body > avg_body * self.mult
        if not big:
            return None
        if not self._in_position and c > o:
            self._in_position = True
            return "BUY"
        if self._in_position and c < o:
            self._in_position = False
            return "SELL"
        return None


__all__ = ["BigBarStrategy"]
