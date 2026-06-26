from typing import Optional
from datetime import datetime

import pandas as pd
import numpy as np

from src.strategy.risk_aware import RiskAwareStrategy
from src.utils.logger import logger


class DecayKeyLevelStrategy(RiskAwareStrategy):
    """降权关键位策略

    关键位被测试超过 max_hits 次后失效。
    与 PureKeyLevelReversal 的差异：维护位状态字典，多次测试后降权。
    """

    PARAM_SCHEMA = {
        "lookback":  {"type": int,   "min": 10,  "max": 200, "default": 50},
        "tol_pct":   {"type": float, "min": 0.001,"max": 0.02, "default": 0.005},
        "pin_ratio": {"type": float, "min": 1.0, "max": 5.0, "default": 2.0},
        "max_hits":  {"type": int,   "min": 1,   "max": 10,  "default": 3},
    }

    def __init__(self, lookback=50, tol_pct=0.005, pin_ratio=2.0, max_hits=3,
                 max_consecutive_losses=3, max_daily_loss=0.02,
                 initial_capital=10000.0, stop_loss_config=None):
        super().__init__(name="DecayKeyLevel",
                         max_consecutive_losses=max_consecutive_losses,
                         max_daily_loss=max_daily_loss,
                         initial_capital=initial_capital,
                         stop_loss_config=stop_loss_config)
        self.lookback = lookback
        self.tol_pct = tol_pct
        self.pin_ratio = pin_ratio
        self.max_hits = max_hits
        self._in_position = False
        self._levels = {}  # price -> hits
        self.set_parameters(lookback=lookback, tol_pct=tol_pct,
                            pin_ratio=pin_ratio, max_hits=max_hits)
        self._init_risk_state()
        logger.info(f"DecayKeyLevel initialized: lookback={lookback}, max_hits={max_hits}")

    def reset(self):
        super().reset()
        self._in_position = False
        self._levels = {}

    @staticmethod
    def _detect_engulfing(prev_o, prev_c, curr_o, curr_c):
        if prev_c < prev_o and curr_c > curr_o:
            if curr_c > prev_o and curr_o < prev_c:
                return "bullish"
        if prev_c > prev_o and curr_c < curr_o:
            if curr_c < prev_o and curr_o > prev_c:
                return "bearish"
        return None

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

        near_low = abs(close - win_low) / max(close, 1e-9) <= self.tol_pct
        near_high = abs(close - win_high) / max(close, 1e-9) <= self.tol_pct

        # 找最接近的活跃位
        best_lvl = None
        best_dist = float("inf")
        for lvl, hits in list(self._levels.items()):
            if hits > self.max_hits:
                continue
            d = abs(lvl - close) / max(close, 1e-9)
            if d < best_dist:
                best_dist = d
                best_lvl = lvl

        if best_lvl is None or best_dist > self.tol_pct:
            if near_low:
                best_lvl = win_low
                self._levels[win_low] = 0
            elif near_high:
                best_lvl = win_high
                self._levels[win_high] = 0
            else:
                return None

        # 命中且未达降权上限
        if abs(best_lvl - close) / max(close, 1e-9) <= self.tol_pct:
            hits = self._levels.get(best_lvl, 0)
            if hits <= self.max_hits:
                self._levels[best_lvl] = hits + 1
                if not self._in_position and near_low and bull_rev:
                    self._in_position = True
                    return "BUY"
                if self._in_position and near_high and bear_rev:
                    self._in_position = False
                    return "SELL"
        return None


__all__ = ["DecayKeyLevelStrategy"]
