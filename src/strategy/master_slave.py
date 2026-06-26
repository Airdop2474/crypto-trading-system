from typing import Optional
from datetime import datetime

import pandas as pd
import numpy as np

from src.strategy.risk_aware import RiskAwareStrategy
from src.utils.logger import logger


class MasterSlaveStrategy(RiskAwareStrategy):
    """主从策略

    主策略（关键位反转）做主入场，辅助策略（突破）做加仓确认。
    主策略 SELL 或反向信号 SELL 离场。
    """

    PARAM_SCHEMA = {
        "lookback":    {"type": int,   "min": 10,  "max": 200, "default": 50},
        "tol_pct":     {"type": float, "min": 0.001,"max": 0.02, "default": 0.005},
        "pin_ratio":   {"type": float, "min": 1.0, "max": 5.0, "default": 2.0},
        "aux_n":       {"type": int,   "min": 5,   "max": 50,  "default": 10},
    }

    def __init__(self, lookback=50, tol_pct=0.005, pin_ratio=2.0, aux_n=10,
                 max_consecutive_losses=3, max_daily_loss=0.02,
                 initial_capital=10000.0, stop_loss_config=None):
        super().__init__(name="MasterSlave",
                         max_consecutive_losses=max_consecutive_losses,
                         max_daily_loss=max_daily_loss,
                         initial_capital=initial_capital,
                         stop_loss_config=stop_loss_config)
        self.lookback = lookback
        self.tol_pct = tol_pct
        self.pin_ratio = pin_ratio
        self.aux_n = aux_n
        self._in_position = False
        self._has_aux = False  # 是否已加仓确认
        self.set_parameters(lookback=lookback, tol_pct=tol_pct,
                            pin_ratio=pin_ratio, aux_n=aux_n)
        self._init_risk_state()
        logger.info(f"MasterSlave initialized: lookback={lookback}")

    def reset(self):
        super().reset()
        self._in_position = False
        self._has_aux = False

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
                self._has_aux = False
                return "SELL"

        window = data.iloc[-(self.lookback + 1):-1]
        win_high = float(window["high"].max())
        win_low = float(window["low"].min())

        # 主信号：关键位 + 反转 K
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

        # 辅助信号：突破 aux_n high
        if len(data) >= self.aux_n + 1:
            aux_window = data.iloc[-(self.aux_n + 1):-1]
            aux_high = float(aux_window["high"].max())
            aux_break = close > aux_high
        else:
            aux_break = False

        if not self._in_position:
            if near_low and bull_rev:
                self._in_position = True
                self._has_aux = aux_break
                return "BUY"
        else:
            # 离场：反向主信号或跌破辅助位
            if near_high and bear_rev:
                self._in_position = False
                self._has_aux = False
                return "SELL"
        return None


__all__ = ["MasterSlaveStrategy"]
