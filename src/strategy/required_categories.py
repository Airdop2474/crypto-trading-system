from typing import Optional
from datetime import datetime

import pandas as pd
import numpy as np

from src.strategy.risk_aware import RiskAwareStrategy
from src.utils.logger import logger


class RequiredCategoriesStrategy(RiskAwareStrategy):
    """必含项策略

    必须同时含"位置类证据"（在极值附近）和"形态类证据"（反转 K）才入场。
    """

    PARAM_SCHEMA = {
        "lookback":   {"type": int,   "min": 10, "max": 200, "default": 50},
        "edge_pct":   {"type": float, "min": 0.05,"max": 0.4, "default": 0.2},
        "pin_ratio":  {"type": float, "min": 1.0, "max": 5.0, "default": 2.0},
    }

    def __init__(self, lookback=50, edge_pct=0.2, pin_ratio=2.0,
                 max_consecutive_losses=3, max_daily_loss=0.02,
                 initial_capital=10000.0, stop_loss_config=None):
        super().__init__(name="RequiredCategories",
                         max_consecutive_losses=max_consecutive_losses,
                         max_daily_loss=max_daily_loss,
                         initial_capital=initial_capital,
                         stop_loss_config=stop_loss_config)
        self.lookback = lookback
        self.edge_pct = edge_pct
        self.pin_ratio = pin_ratio
        self._in_position = False
        self.set_parameters(lookback=lookback, edge_pct=edge_pct, pin_ratio=pin_ratio)
        self._init_risk_state()
        logger.info(f"RequiredCategories initialized: lookback={lookback}")

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

    @staticmethod
    def _detect_engulfing(prev_o, prev_c, curr_o, curr_c):
        if prev_c < prev_o and curr_c > curr_o:
            if curr_c > prev_o and curr_o < prev_c:
                return "bullish"
        if prev_c > prev_o and curr_c < curr_o:
            if curr_c < prev_o and curr_o > prev_c:
                return "bearish"
        return None

    def on_bar(self, data, current_time):
        if len(data) < self.lookback + 2:
            return None
        if self._is_paused(current_time):
            return None
        row = data.iloc[-1]
        prev = data.iloc[-2]
        close = float(row["close"])
        if self._in_position:
            t, _ = self._check_stop_loss(close, current_time, atr=None)
            if t:
                self._in_position = False
                return "SELL"

        window = data.iloc[-(self.lookback + 1):-1]
        win_high = float(window["high"].max())
        win_low = float(window["low"].min())
        pos = (close - win_low) / max(win_high - win_low, 1e-9)

        # 位置类证据
        pos_bull = pos < self.edge_pct
        pos_bear = pos > 1 - self.edge_pct

        # 形态类证据
        engulf = self._detect_engulfing(
            float(prev["open"]), float(prev["close"]),
            float(row["open"]), float(row["close"]),
        )
        pin = self._detect_pin(
            float(row["open"]), float(row["high"]),
            float(row["low"]), float(row["close"]),
            self.pin_ratio,
        )
        form_bull = engulf == "bullish" or pin == "bullish"
        form_bear = engulf == "bearish" or pin == "bearish"

        if not self._in_position and pos_bull and form_bull:
            self._in_position = True
            return "BUY"
        if self._in_position and pos_bear and form_bear:
            self._in_position = False
            return "SELL"
        return None


__all__ = ["RequiredCategoriesStrategy"]
