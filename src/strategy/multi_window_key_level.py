from typing import Optional
from datetime import datetime

import pandas as pd
import numpy as np

from src.strategy.risk_aware import RiskAwareStrategy
from src.utils.logger import logger


class MultiWindowKeyLevelStrategy(RiskAwareStrategy):
    """多窗口关键位策略

    要求 close 同时是 2+ 个窗口（20/50/100）的关键位附近。
    反向反转 K 离场。
    """

    PARAM_SCHEMA = {
        "windows": {"type": list, "default": [20, 50, 100]},
        "tol_pct": {"type": float, "min": 0.001, "max": 0.02, "default": 0.005},
        "pin_ratio": {"type": float, "min": 1.0, "max": 5.0, "default": 2.0},
        "min_hits": {"type": int, "min": 2, "max": 4, "default": 2},
    }

    def __init__(self, windows=None, tol_pct=0.005, pin_ratio=2.0, min_hits=2,
                 max_consecutive_losses=3, max_daily_loss=0.02,
                 initial_capital=10000.0, stop_loss_config=None):
        super().__init__(name="MultiWindowKeyLevel",
                         max_consecutive_losses=max_consecutive_losses,
                         max_daily_loss=max_daily_loss,
                         initial_capital=initial_capital,
                         stop_loss_config=stop_loss_config)
        self.windows = sorted(windows or [20, 50, 100])
        self.tol_pct = tol_pct
        self.pin_ratio = pin_ratio
        self.min_hits = min_hits
        self._in_position = False
        self.set_parameters(windows=self.windows, tol_pct=tol_pct,
                            pin_ratio=pin_ratio, min_hits=min_hits)
        self._init_risk_state()
        logger.info(f"MultiWindowKeyLevel initialized: windows={self.windows}")

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
        if len(data) < max(self.windows) + 2:
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

        engulf = self._detect_engulfing(
            float(prev["open"]), float(prev["close"]),
            float(row["open"]), float(row["close"]),
        )
        pin = self._detect_pin(
            float(row["open"]), float(row["high"]),
            float(row["low"]), float(row["close"]),
            self.pin_ratio,
        )
        bull_rev = engulf == "bullish" or pin == "bullish"
        bear_rev = engulf == "bearish" or pin == "bearish"

        hits_low = 0
        hits_high = 0
        for w in self.windows:
            window = data.iloc[-(w + 1):-1]
            hh = float(window["high"].max())
            ll = float(window["low"].min())
            if abs(close - ll) / max(close, 1e-9) <= self.tol_pct:
                hits_low += 1
            if abs(close - hh) / max(close, 1e-9) <= self.tol_pct:
                hits_high += 1

        if not self._in_position and hits_low >= self.min_hits and bull_rev:
            self._in_position = True
            return "BUY"
        if self._in_position and hits_high >= self.min_hits and bear_rev:
            self._in_position = False
            return "SELL"
        return None


__all__ = ["MultiWindowKeyLevelStrategy"]
