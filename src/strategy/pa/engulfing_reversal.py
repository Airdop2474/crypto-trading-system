"""策略 G：吞没反转做多

价格位于近期区间底部（接近 N bar 低点），出现 bullish engulfing 时做多。

进场：close 在 N bar 低点 + range*threshold 以内 + bullish engulfing 确认
出场：SL = engulfing 低点 - 0.1% | TP = 2R | 时间止损 60 bar
冷却：进场后 20 bar 不再开新仓
"""

from typing import Optional
from datetime import datetime

import pandas as pd

from src.strategy.risk_aware import RiskAwareStrategy
from src.strategy.pa.components import is_engulfing, parse_wick


class EngulfingReversalStrategy(RiskAwareStrategy):

    PARAM_SCHEMA = {
        "lookback": {"type": int, "min": 10, "max": 100, "default": 30},
        "zone_pct": {"type": float, "min": 0.05, "max": 0.5, "default": 0.2},
        "engulf_mult": {"type": float, "min": 1.0, "max": 3.0, "default": 1.5},
        "sl_buffer_pct": {"type": float, "min": 0.0005, "max": 0.01, "default": 0.001},
        "tp_rr": {"type": float, "min": 1.0, "max": 5.0, "default": 2.0},
        "time_stop_bars": {"type": int, "min": 10, "max": 150, "default": 60},
        "cooldown_bars": {"type": int, "min": 0, "max": 50, "default": 20},
    }

    def __init__(
        self,
        lookback: int = 30,
        zone_pct: float = 0.2,
        engulf_mult: float = 1.5,
        sl_buffer_pct: float = 0.001,
        tp_rr: float = 2.0,
        time_stop_bars: int = 60,
        cooldown_bars: int = 20,
        max_consecutive_losses: int = 3,
        max_daily_loss: float = 0.02,
        initial_capital: float = 10000.0,
    ):
        super().__init__(
            name="EngulfingReversal",
            max_consecutive_losses=max_consecutive_losses,
            max_daily_loss=max_daily_loss,
            initial_capital=initial_capital,
        )
        self.lookback = lookback
        self.zone_pct = zone_pct
        self.engulf_mult = engulf_mult
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
            lookback=lookback, zone_pct=zone_pct, engulf_mult=engulf_mult,
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
        if bar_idx < self.lookback:
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

        if len(data) < 2:
            return None

        window = data.iloc[-self.lookback:]
        range_low = float(window["low"].min())
        range_high = float(window["high"].max())
        price_range = range_high - range_low
        if price_range <= 0:
            return None

        zone_top = range_low + price_range * self.zone_pct
        if close > zone_top:
            return None

        prev_wick = parse_wick(data.iloc[-2])
        curr_wick = parse_wick(current)
        if is_engulfing(prev_wick, curr_wick, size_mult=self.engulf_mult) != "bullish":
            return None

        engulf_low = low
        self._entry_price = close
        self._sl_price = engulf_low * (1 - self.sl_buffer_pct)
        risk = self._entry_price - self._sl_price
        if risk <= 0:
            self._clear_position()
            return None
        self._tp_price = self._entry_price + risk * self.tp_rr
        self._entry_bar_index = bar_idx
        self._last_entry_bar = bar_idx

        return "BUY"

    def _clear_position(self) -> None:
        self._entry_price = None
        self._sl_price = None
        self._tp_price = None
        self._entry_bar_index = None

    def on_fill(self, trade: dict) -> None:
        super().on_fill(trade)
