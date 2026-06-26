"""Tests for StructureSwingStrategy (策略 A)."""

import pandas as pd
import numpy as np
import pytest

from src.strategy.pa.structure_swing import StructureSwingStrategy


def _make_bars(prices: list[tuple[float, float, float, float]]) -> pd.DataFrame:
    """Build OHLCV DataFrame from (open, high, low, close) tuples."""
    rows = []
    for i, (o, h, l, c) in enumerate(prices):
        rows.append({
            "open": o, "high": h, "low": l, "close": c,
            "volume": 100.0, "taker_buy_base_volume": 50.0,
        })
    df = pd.DataFrame(rows)
    df.index = pd.date_range("2024-01-01", periods=len(rows), freq="1h")
    return df


def _trending_up_bars(n: int, start: float = 100.0, step: float = 0.5) -> list[tuple]:
    """Generate n bars trending up."""
    bars = []
    p = start
    for _ in range(n):
        o = p
        c = p + step
        h = c + step * 0.3
        l = o - step * 0.2
        bars.append((o, h, l, c))
        p = c
    return bars


def _trending_down_bars(n: int, start: float = 120.0, step: float = 0.5) -> list[tuple]:
    """Generate n bars trending down."""
    bars = []
    p = start
    for _ in range(n):
        o = p
        c = p - step
        h = o + step * 0.2
        l = c - step * 0.3
        bars.append((o, h, l, c))
        p = c
    return bars


class TestInstantiation:
    def test_default_params(self):
        s = StructureSwingStrategy()
        assert s.name == "StructureSwing"
        assert s.swing_n == 8
        assert s._state == "Neutral"
        assert s._entry_price is None

    def test_custom_params(self):
        s = StructureSwingStrategy(swing_n=5, tp_rr=3.0, cooldown_bars=12)
        assert s.swing_n == 5
        assert s.tp_rr == 3.0
        assert s.cooldown_bars == 12

    def test_reset(self):
        s = StructureSwingStrategy()
        s._state = "Bull"
        s._entry_price = 100.0
        s.reset()
        assert s._state == "Neutral"
        assert s._entry_price is None


class TestStateTransitions:
    def test_insufficient_data_returns_none(self):
        s = StructureSwingStrategy(swing_n=3)
        bars = _make_bars(_trending_up_bars(5))
        result = s.on_bar(bars, bars.index[-1])
        assert result is None

    def test_bull_state_with_hh_hl(self):
        """Uptrend with HH + HL → Bull state."""
        s = StructureSwingStrategy(swing_n=3)
        # Build a clear uptrend: wave up → dip → higher wave up → higher dip → up
        bars_data = []
        # Wave 1 up: 100 → 110
        bars_data.extend(_trending_up_bars(8, start=100, step=1.2))
        # Dip 1: 110 → 106
        bars_data.extend(_trending_down_bars(5, start=bars_data[-1][3], step=0.8))
        # Wave 2 up: 106 → 118 (higher high)
        bars_data.extend(_trending_up_bars(8, start=bars_data[-1][3], step=1.5))
        # Dip 2: 118 → 115 (higher low than dip 1)
        bars_data.extend(_trending_down_bars(4, start=bars_data[-1][3], step=0.7))
        # Wave 3 up: 115 → 125
        bars_data.extend(_trending_up_bars(8, start=bars_data[-1][3], step=1.2))

        df = _make_bars(bars_data)
        for i in range(2 * s.swing_n + 1, len(df)):
            s.on_bar(df.iloc[:i + 1], df.index[i])

        assert s._state == "Bull"

    def test_bear_state_with_lh_ll(self):
        """Downtrend with LH + LL → Bear state."""
        s = StructureSwingStrategy(swing_n=3)
        # Wave 1 down
        bars_data = _trending_down_bars(8, start=120, step=1.2)
        # Bounce 1
        bars_data.extend(_trending_up_bars(5, start=bars_data[-1][3], step=0.7))
        # Wave 2 down (lower low)
        bars_data.extend(_trending_down_bars(8, start=bars_data[-1][3], step=1.3))
        # Bounce 2 (lower high)
        bars_data.extend(_trending_up_bars(4, start=bars_data[-1][3], step=0.5))
        # Wave 3 down
        bars_data.extend(_trending_down_bars(8, start=bars_data[-1][3], step=1.0))

        df = _make_bars(bars_data)
        for i in range(2 * s.swing_n + 1, len(df)):
            s.on_bar(df.iloc[:i + 1], df.index[i])

        assert s._state == "Bear"


class TestEntryExit:
    def _build_entry_scenario(self):
        """Build data that triggers a BUY: Bull state + pullback to swing low + close > prev high."""
        s = StructureSwingStrategy(swing_n=3, pullback_pct=0.005, cooldown_bars=0)

        bars_data = []
        # Establish Bull: up → dip → higher up → higher dip → confirmation
        bars_data.extend(_trending_up_bars(8, start=100, step=1.0))
        bars_data.extend(_trending_down_bars(4, start=bars_data[-1][3], step=0.6))
        bars_data.extend(_trending_up_bars(8, start=bars_data[-1][3], step=1.2))
        bars_data.extend(_trending_down_bars(4, start=bars_data[-1][3], step=0.5))
        bars_data.extend(_trending_up_bars(6, start=bars_data[-1][3], step=1.0))

        df = _make_bars(bars_data)
        # Run through to establish Bull state
        for i in range(2 * s.swing_n + 1, len(df)):
            s.on_bar(df.iloc[:i + 1], df.index[i])

        return s, bars_data, df

    def test_entry_requires_bull_state(self):
        """No entry when state is not Bull."""
        s = StructureSwingStrategy(swing_n=3, cooldown_bars=0)
        bars = _make_bars(_trending_down_bars(30, start=120, step=0.5))
        signals = []
        for i in range(2 * s.swing_n + 1, len(bars)):
            sig = s.on_bar(bars.iloc[:i + 1], bars.index[i])
            if sig:
                signals.append(sig)
        assert "BUY" not in signals

    def test_cooldown_blocks_entry(self):
        """After entry, cooldown prevents immediate re-entry."""
        s = StructureSwingStrategy(swing_n=3, cooldown_bars=50)
        s._state = "Bull"
        s._last_entry_bar = 10
        s._last_swing_low = type("SP", (), {"price": 100.0, "index": 5, "typ": "low"})()

        # Simulate bar at index 20 (within cooldown of 50 bars from entry at 10)
        bars_data = _trending_up_bars(21, start=99)
        df = _make_bars(bars_data)
        result = s.on_bar(df, df.index[-1])
        assert result is None

    def test_sl_exit(self):
        """Position exits when low touches stop loss."""
        s = StructureSwingStrategy(swing_n=3)
        s._entry_price = 110.0
        s._sl_price = 105.0
        s._tp_price = 120.0
        s._entry_bar_index = 5
        s._state = "Bull"

        # Bar with low below SL
        bars_data = _trending_up_bars(20, start=100, step=0.5)
        # Add bar that hits SL
        bars_data.append((108.0, 108.5, 104.5, 106.0))
        df = _make_bars(bars_data)
        result = s.on_bar(df, df.index[-1])
        assert result == "SELL"
        assert s._entry_price is None

    def test_tp_exit(self):
        """Position exits when high touches take profit."""
        s = StructureSwingStrategy(swing_n=3)
        s._entry_price = 110.0
        s._sl_price = 105.0
        s._tp_price = 120.0
        s._entry_bar_index = 5
        s._state = "Bull"

        bars_data = _trending_up_bars(20, start=100, step=0.5)
        # Add bar that hits TP
        bars_data.append((118.0, 121.0, 117.5, 120.5))
        df = _make_bars(bars_data)
        result = s.on_bar(df, df.index[-1])
        assert result == "SELL"
        assert s._entry_price is None

    def test_time_stop_exit(self):
        """Position exits after time_stop_bars."""
        s = StructureSwingStrategy(swing_n=3, time_stop_bars=10)
        s._entry_price = 110.0
        s._sl_price = 90.0
        s._tp_price = 150.0
        s._entry_bar_index = 5
        s._state = "Bull"

        # Build 20 bars (entry at index 5, current at index 15 → 10 bars held)
        bars_data = _trending_up_bars(16, start=108, step=0.1)
        df = _make_bars(bars_data)
        result = s.on_bar(df, df.index[-1])
        assert result == "SELL"

    def test_choch_exit(self):
        """Position exits on CHoCH (state turns Bear)."""
        s = StructureSwingStrategy(swing_n=3)
        s._entry_price = 110.0
        s._sl_price = 100.0
        s._tp_price = 130.0
        s._entry_bar_index = 0
        s._state = "Bear"  # Simulate state just flipped to Bear

        bars_data = _trending_down_bars(20, start=112, step=0.3)
        df = _make_bars(bars_data)
        result = s.on_bar(df, df.index[-1])
        assert result == "SELL"


class TestOnFill:
    def test_on_fill_delegates_to_base(self):
        s = StructureSwingStrategy()
        s.on_fill({"profit": -50, "time": "2024-01-01 12:00:00"})
        assert s._consecutive_losses == 1

    def test_on_fill_winning_trade_resets_losses(self):
        s = StructureSwingStrategy()
        s.on_fill({"profit": -10, "time": "2024-01-01 10:00:00"})
        s.on_fill({"profit": 30, "time": "2024-01-01 11:00:00"})
        assert s._consecutive_losses == 0
