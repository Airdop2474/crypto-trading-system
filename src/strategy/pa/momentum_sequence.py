"""策略 F：动量序列做多

连续 N 根阳 K 线（close > open 且实体占比大）确认做多动量，
在序列完成后入场。

进场：连续 N 根阳线（body_ratio > 阈值）+ 最后一根 close > 序列第一根 open
出场：SL = 序列最低价 - 0.2% | TP = 1.5R | 时间止损 48 bar
冷却：进场后 12 bar 不再开新仓
"""

from typing import Optional
from datetime import datetime

import pandas as pd

from src.strategy.risk_aware import RiskAwareStrategy


class MomentumSequenceStrategy(RiskAwareStrategy):

    PARAM_SCHEMA = {
        "seq_len": {"type": int, "min": 2, "max": 8, "default": 3},
        "body_ratio_min": {"type": float, "min": 0.3, "max": 0.9, "default": 0.6},
        "sl_buffer_pct": {"type": float, "min": 0.001, "max": 0.01, "default": 0.002},
        "tp_rr": {"type": float, "min": 1.0, "max": 5.0, "default": 1.5},
        "time_stop_bars": {"type": int, "min": 6, "max": 100, "default": 48},
        "cooldown_bars": {"type": int, "min": 0, "max": 50, "default": 12},
    }

    def __init__(
        self,
        seq_len: int = 3,
        body_ratio_min: float = 0.6,
        sl_buffer_pct: float = 0.002,
        tp_rr: float = 1.5,
        time_stop_bars: int = 48,
        cooldown_bars: int = 12,
        max_consecutive_losses: int = 3,
        max_daily_loss: float = 0.02,
        initial_capital: float = 10000.0,
    ):
        super().__init__(
            name="MomentumSequence",
            max_consecutive_losses=max_consecutive_losses,
            max_daily_loss=max_daily_loss,
            initial_capital=initial_capital,
        )
        self.seq_len = seq_len
        self.body_ratio_min = body_ratio_min
        self.sl_buffer_pct = sl_buffer_pct
        self.tp_rr = tp_rr
        self.time_stop_bars = time_stop_bars
        self.cooldown_bars = cooldown_bars

        self._entry_price: Optional[float] = None
        self._sl_price: Optional[float] = None
        self._tp_price: Optional[float] = None
        self._entry_bar_index: Optional[int] = None
        self._last_entry_bar: int = -9999

        self.set_parameters(
            seq_len=seq_len, body_ratio_min=body_ratio_min,
            sl_buffer_pct=sl_buffer_pct, tp_rr=tp_rr,
            time_stop_bars=time_stop_bars, cooldown_bars=cooldown_bars,
        )
        self._init_risk_state()

    def reset(self):
        super().reset()
        self._entry_price = None
        self._sl_price = None
        self._tp_price = None
        self._entry_bar_index = None
        self._last_entry_bar = -9999

    def on_bar(self, data: pd.DataFrame, current_time: datetime) -> Optional[str]:
        if self._is_paused(current_time):
            return None

        bar_idx = len(data) - 1
        if bar_idx < self.seq_len:
            return None

        current = data.iloc[-1]
        close = float(current["close"])
        high = float(current["high"])
        low = float(current["low"])

        # --- Exit logic ---
        if self._entry_price is not None:
            if low <= self._sl_price:
                self._clear_position()
                return "SELL"

            if high >= self._tp_price:
                self._clear_position()
                return "SELL"

            bars_held = bar_idx - self._entry_bar_index
            if bars_held >= self.time_stop_bars:
                self._clear_position()
                return "SELL"

            return None

        # --- Entry logic ---
        if bar_idx - self._last_entry_bar < self.cooldown_bars:
            return None

        seq = data.iloc[-self.seq_len:]
        if not self._is_bull_sequence(seq):
            return None

        seq_low = float(seq["low"].min())
        self._entry_price = close
        self._sl_price = seq_low * (1 - self.sl_buffer_pct)
        risk = self._entry_price - self._sl_price
        if risk <= 0:
            self._clear_position()
            return None
        self._tp_price = self._entry_price + risk * self.tp_rr
        self._entry_bar_index = bar_idx
        self._last_entry_bar = bar_idx

        return "BUY"

    def _is_bull_sequence(self, seq: pd.DataFrame) -> bool:
        for i in range(len(seq)):
            row = seq.iloc[i]
            o, c, h, l = float(row["open"]), float(row["close"]), float(row["high"]), float(row["low"])
            if c <= o:
                return False
            bar_range = h - l
            if bar_range <= 0:
                return False
            body = c - o
            if body / bar_range < self.body_ratio_min:
                return False
        first_open = float(seq.iloc[0]["open"])
        last_close = float(seq.iloc[-1]["close"])
        if last_close <= first_open:
            return False
        return True

    def _clear_position(self) -> None:
        self._entry_price = None
        self._sl_price = None
        self._tp_price = None
        self._entry_bar_index = None

    def on_fill(self, trade: dict) -> None:
        super().on_fill(trade)
