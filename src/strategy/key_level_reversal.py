"""
关键位反转策略（Price Action）

基于支撑/阻力位 + pin bar 确认的反转策略。
在历史关键价位等待价格行为确认信号入场。

与网格策略的异同：
- 相同：都在关键区间内低买高卖
- 不同：网格是固定间距机械挂单，反转是价格行为确认后入场
- 互补：网格负责区间内持续收割，反转负责转折点的精准入场

适用环境：支撑阻力清晰的震荡/转折市场。
不适用环境：强单边、无历史结构的新高/新低区域。
"""

from typing import Optional, Tuple
from datetime import datetime

import pandas as pd
import numpy as np

from src.strategy.risk_aware import RiskAwareStrategy
from src.utils.logger import logger


class KeyLevelReversalStrategy(RiskAwareStrategy):
    """关键位反转策略

    逻辑：
    1. 从近 lookback 根 bar 中识别支撑/阻力区域
    2. 在 S/R 附近检测 pin bar（拒绝信号）
    3. pin bar 确认后入场
    4. 固定 ATR 止损 + 反向 pin bar 出场
    """

    PARAM_SCHEMA = {
        "lookback":                {"type": int,   "min": 10,  "max": 100, "default": 50},
        "pin_threshold":           {"type": float, "min": 1.0, "max": 5.0, "default": 2.0},
        "stop_atr_mult":           {"type": float, "min": 1.0, "max": 5.0, "default": 2.0},
        "atr_period":              {"type": int,   "min": 2,   "max": 50,  "default": 14},
    }

    def __init__(
        self,
        lookback: int = 50,
        pin_threshold: float = 2.0,
        stop_atr_mult: float = 2.0,
        atr_period: int = 14,
        max_consecutive_losses: int = 3,
        max_daily_loss: float = 0.02,
        initial_capital: float = 10000.0,
    ):
        super().__init__(
            name="KeyLevelReversal",
            max_consecutive_losses=max_consecutive_losses,
            max_daily_loss=max_daily_loss,
            initial_capital=initial_capital,
        )

        self.lookback = lookback
        self.pin_threshold = pin_threshold
        self.stop_atr_mult = stop_atr_mult
        self.atr_period = atr_period

        self._in_position = False
        self._support_zone: Tuple[float, float] = (0.0, 0.0)
        self._resistance_zone: Tuple[float, float] = (0.0, 0.0)
        self._entry_price: Optional[float] = None

        # 增量 ATR 状态
        self._tr_window: list[float] = []
        self._tr_sum: float = 0.0
        self._prev_close_atr: Optional[float] = None

        self.set_parameters(
            lookback=lookback, pin_threshold=pin_threshold,
            stop_atr_mult=stop_atr_mult, atr_period=atr_period,
        )
        self._init_risk_state()

        logger.info(
            f"KeyLevelReversal initialized: "
            f"lookback={lookback}, pin_threshold={pin_threshold}"
        )

    def reset(self):
        super().reset()
        self._in_position = False
        self._support_zone = (0.0, 0.0)
        self._resistance_zone = (0.0, 0.0)
        self._entry_price = None
        self._tr_window.clear()
        self._tr_sum = 0.0
        self._prev_close_atr = None

    # ---- 核心逻辑 ----

    def on_bar(self, data: pd.DataFrame, current_time: datetime) -> Optional[str]:
        if len(data) < self.lookback:
            return None

        if self._is_paused(current_time):
            return None

        close = float(data["close"].iloc[-1])
        atr = self._update_atr(
            float(data["high"].iloc[-1]),
            float(data["low"].iloc[-1]),
            close,
        )

        sr = self._identify_sr_zones(data)
        self._support_zone = sr["support"]
        self._resistance_zone = sr["resistance"]

        pin = self._detect_pin_bar(data)

        if not self._in_position:
            # 在支撑区附近 + 下影线 pin bar → BUY
            near_support = self._in_zone(close, self._support_zone, atr)
            if near_support and pin == "bullish":
                self._in_position = True
                self._entry_price = close
                return "BUY"
        else:
            # 出场条件检查
            if self._check_exit(data, close, atr, pin):
                self._in_position = False
                self._entry_price = None
                return "SELL"

        return None

    # ---- 辅助方法 ----

    def _identify_sr_zones(self, data: pd.DataFrame) -> dict:
        """从 lookback 窗口识别支撑/阻力区域。

        使用分位数法：取 lookback 内低价的 10%-30% 分位作为支撑区，
        高价的 70%-90% 分位作为阻力区。
        """
        window = data.iloc[-self.lookback:]
        highs = window["high"].values
        lows = window["low"].values

        support = (
            float(np.percentile(lows, 10)),
            float(np.percentile(lows, 30)),
        )
        resistance = (
            float(np.percentile(highs, 70)),
            float(np.percentile(highs, 90)),
        )
        return {"support": support, "resistance": resistance}

    def _in_zone(self, price: float, zone: Tuple[float, float], atr: float) -> bool:
        """检查价格是否在区域附近（±0.5 ATR 容忍度）。"""
        margin = atr * 0.5
        return (zone[0] - margin) <= price <= (zone[1] + margin)

    def _detect_pin_bar(self, data: pd.DataFrame) -> Optional[str]:
        """检测 pin bar（拒绝信号）。

        返回：
            'bullish' — 下影线 pin bar（探底被拒绝，看涨）
            'bearish' — 上影线 pin bar（冲高被拒绝，看跌）
            None     — 非 pin bar
        """
        bar = data.iloc[-1]
        open_, high, low, close = (
            float(bar["open"]), float(bar["high"]),
            float(bar["low"]), float(bar["close"]),
        )

        body = abs(close - open_)
        if body == 0:
            return None  # doji，不算 pin bar

        upper_wick = high - max(open_, close)
        lower_wick = min(open_, close) - low

        if lower_wick > body * self.pin_threshold:
            return "bullish"
        if upper_wick > body * self.pin_threshold:
            return "bearish"
        return None

    def _check_exit(
        self, data: pd.DataFrame, close: float, atr: Optional[float], pin: Optional[str]
    ) -> bool:
        if pin == "bearish" and self._in_zone(close, self._resistance_zone, atr or 0):
            return True

        if self._entry_price is not None and atr is not None and atr > 0:
            stop_loss = self._entry_price - self.stop_atr_mult * atr
            if close < stop_loss:
                return True

        return False

    def _update_atr(self, high: float, low: float, close: float) -> Optional[float]:
        """增量 ATR，O(1) per bar。"""
        if self._prev_close_atr is None:
            self._prev_close_atr = close
            return None

        tr = max(high - low, abs(high - self._prev_close_atr), abs(low - self._prev_close_atr))
        self._prev_close_atr = close

        window_size = self.atr_period
        if len(self._tr_window) >= window_size:
            self._tr_sum -= self._tr_window.pop(0)
        self._tr_window.append(tr)
        self._tr_sum += tr

        if len(self._tr_window) < window_size:
            return None
        return self._tr_sum / window_size

    @staticmethod
    def _calc_atr(data: pd.DataFrame, period: int) -> float:
        """计算 ATR（全量 rolling 实现）。"""
        high, low, close = data["high"], data["low"], data["close"]
        prev_close = close.shift(1)
        tr = pd.concat([
            high - low,
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ], axis=1).max(axis=1)
        return float(tr.rolling(period).mean().iloc[-1])
