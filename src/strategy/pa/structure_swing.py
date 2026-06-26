"""策略 A：市场结构 Swing 做多

状态机追踪 swing high/low 序列（HH+HL → Bull，LH+LL → Bear），
Bull 状态下等待回调到最近 swing low 附近，确认后做多。

进场：Bull 状态 + 价格回调到 swing low 上方 0.3% 以内 + close > prev high
出场：SL = swing low - 0.1% | TP = 2R | 时间止损 72 bar | CHoCH down 平仓
冷却：进场后 24 bar 不再开新仓
"""

from typing import Optional
from datetime import datetime

import pandas as pd

from src.strategy.risk_aware import RiskAwareStrategy
from src.strategy.pa.components import SwingPoint, detect_swings


class StructureSwingStrategy(RiskAwareStrategy):

    PARAM_SCHEMA = {
        "swing_n": {"type": int, "min": 3, "max": 20, "default": 8},
        "pullback_pct": {"type": float, "min": 0.001, "max": 0.02, "default": 0.003},
        "sl_buffer_pct": {"type": float, "min": 0.0005, "max": 0.01, "default": 0.001},
        "tp_rr": {"type": float, "min": 1.0, "max": 5.0, "default": 2.0},
        "time_stop_bars": {"type": int, "min": 12, "max": 200, "default": 72},
        "cooldown_bars": {"type": int, "min": 0, "max": 100, "default": 24},
    }

    def __init__(
        self,
        swing_n: int = 8,
        pullback_pct: float = 0.003,
        sl_buffer_pct: float = 0.001,
        tp_rr: float = 2.0,
        time_stop_bars: int = 72,
        cooldown_bars: int = 24,
        max_consecutive_losses: int = 3,
        max_daily_loss: float = 0.02,
        initial_capital: float = 10000.0,
    ):
        super().__init__(
            name="StructureSwing",
            max_consecutive_losses=max_consecutive_losses,
            max_daily_loss=max_daily_loss,
            initial_capital=initial_capital,
        )
        self.swing_n = swing_n
        self.pullback_pct = pullback_pct
        self.sl_buffer_pct = sl_buffer_pct
        self.tp_rr = tp_rr
        self.time_stop_bars = time_stop_bars
        self.cooldown_bars = cooldown_bars

        self._entry_price: Optional[float] = None
        self._sl_price: Optional[float] = None
        self._tp_price: Optional[float] = None
        self._entry_bar_index: Optional[int] = None

        self._state: str = "Neutral"
        self._last_swing_high: Optional[SwingPoint] = None
        self._last_swing_low: Optional[SwingPoint] = None
        self._prev_swing_high: Optional[SwingPoint] = None
        self._prev_swing_low: Optional[SwingPoint] = None

        self._last_entry_bar: int = -9999

        self.set_parameters(
            swing_n=swing_n, pullback_pct=pullback_pct,
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
        self._state = "Neutral"
        self._last_swing_high = None
        self._last_swing_low = None
        self._prev_swing_high = None
        self._prev_swing_low = None
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

        swings = detect_swings(data, n=self.swing_n)
        self._update_state(swings)

        # --- Exit logic ---
        if self._entry_price is not None:
            if self._state == "Bear":
                self._clear_position()
                return "SELL"

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

        if self._state != "Bull":
            return None

        if self._last_swing_low is None:
            return None

        swing_low_price = self._last_swing_low.price
        pullback_zone_top = swing_low_price * (1 + self.pullback_pct)

        if low > pullback_zone_top:
            return None

        if len(data) < 2:
            return None
        prev_high = float(data.iloc[-2]["high"])
        if close <= prev_high:
            return None

        # Enter long
        self._entry_price = close
        self._sl_price = swing_low_price * (1 - self.sl_buffer_pct)
        risk = self._entry_price - self._sl_price
        if risk <= 0:
            self._clear_position()
            return None
        self._tp_price = self._entry_price + risk * self.tp_rr
        self._entry_bar_index = bar_idx
        self._last_entry_bar = bar_idx

        return "BUY"

    def _update_state(self, swings: list[SwingPoint]) -> None:
        highs = [s for s in swings if s.typ == "high"]
        lows = [s for s in swings if s.typ == "low"]

        if len(highs) >= 2:
            self._prev_swing_high = highs[-2]
            self._last_swing_high = highs[-1]
        elif len(highs) == 1:
            self._last_swing_high = highs[-1]

        if len(lows) >= 2:
            self._prev_swing_low = lows[-2]
            self._last_swing_low = lows[-1]
        elif len(lows) == 1:
            self._last_swing_low = lows[-1]

        if self._prev_swing_high is None or self._prev_swing_low is None:
            return

        hh = self._last_swing_high.price > self._prev_swing_high.price
        hl = self._last_swing_low.price > self._prev_swing_low.price

        if hh and hl:
            self._state = "Bull"
        elif not hh and not hl:
            self._state = "Bear"
        else:
            self._state = "Neutral"

    def _clear_position(self) -> None:
        self._entry_price = None
        self._sl_price = None
        self._tp_price = None
        self._entry_bar_index = None

    def on_fill(self, trade: dict) -> None:
        super().on_fill(trade)
