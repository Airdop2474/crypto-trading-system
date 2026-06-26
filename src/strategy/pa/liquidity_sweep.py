"""策略 B：流动性扫荡做多

检测 equal lows 聚类（流动性池），等待价格扫荡（sweep below），
确认反弹后做多。

进场：equal lows 被 sweep（low < level）+ 同根或下根 close > level
出场：SL = sweep low - buffer | TP = 2R | 时间止损 48 bar
冷却：进场后 24 bar 不再开新仓
"""

from typing import Optional
from datetime import datetime

import pandas as pd

from src.strategy.risk_aware import RiskAwareStrategy
from src.strategy.pa.components import (
    SwingPoint, detect_swings, EqualLevel, cluster_equal_lows,
)


class LiquiditySweepStrategy(RiskAwareStrategy):

    PARAM_SCHEMA = {
        "swing_n": {"type": int, "min": 3, "max": 20, "default": 5},
        "eq_tolerance_pct": {"type": float, "min": 0.0005, "max": 0.005, "default": 0.001},
        "eq_min_members": {"type": int, "min": 2, "max": 5, "default": 2},
        "sl_buffer_pct": {"type": float, "min": 0.0005, "max": 0.01, "default": 0.001},
        "tp_rr": {"type": float, "min": 1.0, "max": 5.0, "default": 2.0},
        "time_stop_bars": {"type": int, "min": 12, "max": 200, "default": 48},
        "cooldown_bars": {"type": int, "min": 0, "max": 100, "default": 24},
        "max_level_age": {"type": int, "min": 20, "max": 500, "default": 200},
    }

    def __init__(
        self,
        swing_n: int = 5,
        eq_tolerance_pct: float = 0.001,
        eq_min_members: int = 2,
        sl_buffer_pct: float = 0.001,
        tp_rr: float = 2.0,
        time_stop_bars: int = 48,
        cooldown_bars: int = 24,
        max_level_age: int = 200,
        max_consecutive_losses: int = 3,
        max_daily_loss: float = 0.02,
        initial_capital: float = 10000.0,
    ):
        super().__init__(
            name="LiquiditySweep",
            max_consecutive_losses=max_consecutive_losses,
            max_daily_loss=max_daily_loss,
            initial_capital=initial_capital,
        )
        self.swing_n = swing_n
        self.eq_tolerance_pct = eq_tolerance_pct
        self.eq_min_members = eq_min_members
        self.sl_buffer_pct = sl_buffer_pct
        self.tp_rr = tp_rr
        self.time_stop_bars = time_stop_bars
        self.cooldown_bars = cooldown_bars
        self.max_level_age = max_level_age

        self._entry_price: Optional[float] = None
        self._sl_price: Optional[float] = None
        self._tp_price: Optional[float] = None
        self._entry_bar_index: Optional[int] = None
        self._last_entry_bar: int = -9999

        self.set_parameters(
            swing_n=swing_n, eq_tolerance_pct=eq_tolerance_pct,
            eq_min_members=eq_min_members, sl_buffer_pct=sl_buffer_pct,
            tp_rr=tp_rr, time_stop_bars=time_stop_bars,
            cooldown_bars=cooldown_bars, max_level_age=max_level_age,
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
        if bar_idx < 2 * self.swing_n + 1:
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

        swings = detect_swings(data, n=self.swing_n)
        levels = cluster_equal_lows(
            swings,
            tolerance_pct=self.eq_tolerance_pct,
            min_members=self.eq_min_members,
        )

        for level in levels:
            if level.swept:
                continue
            if bar_idx - level.last_index > self.max_level_age:
                continue

            if low < level.price and close > level.price:
                sweep_low = low
                self._entry_price = close
                self._sl_price = sweep_low * (1 - self.sl_buffer_pct)
                risk = self._entry_price - self._sl_price
                if risk <= 0:
                    continue
                self._tp_price = self._entry_price + risk * self.tp_rr
                self._entry_bar_index = bar_idx
                self._last_entry_bar = bar_idx
                level.swept = True
                level.swept_at = bar_idx
                return "BUY"

        return None

    def _clear_position(self) -> None:
        self._entry_price = None
        self._sl_price = None
        self._tp_price = None
        self._entry_bar_index = None

    def on_fill(self, trade: dict) -> None:
        super().on_fill(trade)
