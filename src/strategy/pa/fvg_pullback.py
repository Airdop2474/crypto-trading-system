"""策略 C：FVG 回填做多

检测 bullish FVG（三根 K 线中间缺口），等待价格回踩 FVG 区间后做多。
烟雾测试显示 87.6% FVG 在 50 bar 内被 mitigated，edge 基础好。

进场：bullish FVG 未过期 + 价格回踩进入 FVG 区间 + close 收在 FVG 上半部
出场：SL = FVG 底部 - buffer | TP = 2R | 时间止损 36 bar
冷却：进场后 12 bar 不再开新仓
"""

from typing import Optional
from datetime import datetime

import pandas as pd

from src.strategy.risk_aware import RiskAwareStrategy
from src.strategy.pa.components import FVG, detect_fvgs, mark_mitigated


class FVGPullbackStrategy(RiskAwareStrategy):

    PARAM_SCHEMA = {
        "body_ratio_threshold": {"type": float, "min": 0.3, "max": 0.9, "default": 0.6},
        "min_height_pct": {"type": float, "min": 0.001, "max": 0.01, "default": 0.003},
        "max_height_pct": {"type": float, "min": 0.01, "max": 0.10, "default": 0.03},
        "expire_bars": {"type": int, "min": 20, "max": 100, "default": 50},
        "sl_buffer_pct": {"type": float, "min": 0.0005, "max": 0.01, "default": 0.001},
        "tp_rr": {"type": float, "min": 1.0, "max": 5.0, "default": 2.0},
        "time_stop_bars": {"type": int, "min": 12, "max": 100, "default": 36},
        "cooldown_bars": {"type": int, "min": 0, "max": 50, "default": 12},
    }

    def __init__(
        self,
        body_ratio_threshold: float = 0.6,
        min_height_pct: float = 0.003,
        max_height_pct: float = 0.03,
        expire_bars: int = 50,
        sl_buffer_pct: float = 0.001,
        tp_rr: float = 2.0,
        time_stop_bars: int = 36,
        cooldown_bars: int = 12,
        max_consecutive_losses: int = 3,
        max_daily_loss: float = 0.02,
        initial_capital: float = 10000.0,
    ):
        super().__init__(
            name="FVGPullback",
            max_consecutive_losses=max_consecutive_losses,
            max_daily_loss=max_daily_loss,
            initial_capital=initial_capital,
        )
        self.body_ratio_threshold = body_ratio_threshold
        self.min_height_pct = min_height_pct
        self.max_height_pct = max_height_pct
        self.expire_bars = expire_bars
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
            body_ratio_threshold=body_ratio_threshold,
            min_height_pct=min_height_pct, max_height_pct=max_height_pct,
            expire_bars=expire_bars, sl_buffer_pct=sl_buffer_pct,
            tp_rr=tp_rr, time_stop_bars=time_stop_bars,
            cooldown_bars=cooldown_bars,
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
        if bar_idx < 3:
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

        fvgs = detect_fvgs(
            data,
            body_ratio_threshold=self.body_ratio_threshold,
            min_height_pct=self.min_height_pct,
            max_height_pct=self.max_height_pct,
        )
        mark_mitigated(fvgs, data, expire_bars=self.expire_bars)

        for fvg in reversed(fvgs):
            if fvg.typ != "bullish":
                continue
            if fvg.mitigated:
                continue
            if bar_idx - fvg.index > self.expire_bars:
                continue

            if low <= fvg.high and close >= fvg.mid:
                self._entry_price = close
                self._sl_price = fvg.low * (1 - self.sl_buffer_pct)
                risk = self._entry_price - self._sl_price
                if risk <= 0:
                    continue
                self._tp_price = self._entry_price + risk * self.tp_rr
                self._entry_bar_index = bar_idx
                self._last_entry_bar = bar_idx
                return "BUY"

        return None

    def _clear_position(self) -> None:
        self._entry_price = None
        self._sl_price = None
        self._tp_price = None
        self._entry_bar_index = None

    def on_fill(self, trade: dict) -> None:
        super().on_fill(trade)
