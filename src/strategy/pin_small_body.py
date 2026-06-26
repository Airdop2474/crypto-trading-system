from typing import Optional
from datetime import datetime

import pandas as pd
import numpy as np

from src.strategy.risk_aware import RiskAwareStrategy
from src.utils.logger import logger


class PinWithSmallBodyStrategy(RiskAwareStrategy):
    """Pin + 小实体 + 位置过滤

    pin bar + 实体占振幅<0.3（避免大阳线带长下影的伪锤子）
    + 出现在近 lookback 根区间极值附近。
    反向 pin 离场。
    """

    PARAM_SCHEMA = {
        "lookback":       {"type": int,   "min": 10,  "max": 100, "default": 20},
        "pin_ratio":      {"type": float, "min": 1.0, "max": 5.0, "default": 2.0},
        "max_body_ratio": {"type": float, "min": 0.1, "max": 0.6, "default": 0.3},
        "edge_pct":       {"type": float, "min": 0.05,"max": 0.4, "default": 0.15},
    }

    def __init__(self, lookback=20, pin_ratio=2.0, max_body_ratio=0.3, edge_pct=0.15,
                 max_consecutive_losses=3, max_daily_loss=0.02,
                 initial_capital=10000.0, stop_loss_config=None):
        super().__init__(name="PinSmallBody",
                         max_consecutive_losses=max_consecutive_losses,
                         max_daily_loss=max_daily_loss,
                         initial_capital=initial_capital,
                         stop_loss_config=stop_loss_config)
        self.lookback = lookback
        self.pin_ratio = pin_ratio
        self.max_body_ratio = max_body_ratio
        self.edge_pct = edge_pct
        self._in_position = False
        self.set_parameters(lookback=lookback, pin_ratio=pin_ratio,
                            max_body_ratio=max_body_ratio, edge_pct=edge_pct)
        self._init_risk_state()
        logger.info(f"PinSmallBody initialized: lookback={lookback}")

    def reset(self):
        super().reset()
        self._in_position = False

    @staticmethod
    def _detect_pin(o, h, l, c, min_ratio):
        body = abs(c - o)
        if body <= 0:
            return None
        upper = h - max(o, c)
        lower = min(o, c) - l
        if lower >= body * min_ratio and upper <= body * 0.3 and c > o:
            return "bullish"
        if upper >= body * min_ratio and lower <= body * 0.3 and c < o:
            return "bearish"
        return None

    def on_bar(self, data, current_time):
        if len(data) < self.lookback + 1:
            return None
        if self._is_paused(current_time):
            return None
        row = data.iloc[-1]
        close = float(row["close"])
        if self._in_position:
            t, _ = self._check_stop_loss(close, current_time, atr=None)
            if t:
                self._in_position = False
                return "SELL"

        o = float(row["open"]); h = float(row["high"]); l = float(row["low"]); c = float(row["close"])
        rng = h - l
        if rng <= 0:
            return None
        body_ratio = abs(c - o) / rng

        window = data.iloc[-(self.lookback + 1):-1]
        win_high = float(window["high"].max())
        win_low = float(window["low"].min())
        pos = (c - win_low) / max(win_high - win_low, 1e-9)

        pin = self._detect_pin(o, h, l, c, self.pin_ratio)
        if pin is None or body_ratio >= self.max_body_ratio:
            return None

        if not self._in_position:
            if pin == "bullish" and pos < self.edge_pct:
                self._in_position = True
                return "BUY"
        else:
            if pin == "bearish" and pos > 1 - self.edge_pct:
                self._in_position = False
                return "SELL"
        return None


__all__ = ["PinWithSmallBodyStrategy"]
