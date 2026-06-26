"""
纯关键位反转策略（极值法）

与现有 KeyLevelReversal 的差异：
  - 关键位识别：用窗口 max/min 极值（而非分位数法）
  - 反转形态：engulfing 或 pin bar 皆可（而非仅 pin bar）
  - 容差基准：百分比 ±tol_pct（而非 ATR）
  - 离场：反向反转 K（而非 ATR 止损）

设计来源：纯 K 线策略方案 J1 变体，4 数据集均夏普 1.60，
是唯一在熊市（2022）取得正收益的纯 K 线策略。
"""

from typing import Optional, Tuple
from datetime import datetime

import pandas as pd

from src.strategy.risk_aware import RiskAwareStrategy
from src.utils.logger import logger


class PureKeyLevelReversalStrategy(RiskAwareStrategy):
    """纯关键位反转策略（极值法）

    在近 lookback 根的 high/low 极值 ±tol_pct 内出现反转 K（吞没或 pin）时入场。
    """

    PARAM_SCHEMA = {
        "lookback":     {"type": int,   "min": 10,  "max": 200, "default": 50},
        "tol_pct":      {"type": float, "min": 0.001,"max": 0.02, "default": 0.005},
        "pin_ratio":    {"type": float, "min": 1.0, "max": 5.0,  "default": 2.0},
    }

    def __init__(
        self,
        lookback: int = 50,
        tol_pct: float = 0.005,
        pin_ratio: float = 2.0,
        max_consecutive_losses: int = 3,
        max_daily_loss: float = 0.02,
        initial_capital: float = 10000.0,
        stop_loss_config=None,
    ):
        super().__init__(
            name="PureKeyLevelReversal",
            max_consecutive_losses=max_consecutive_losses,
            max_daily_loss=max_daily_loss,
            initial_capital=initial_capital,
            stop_loss_config=stop_loss_config,
        )
        self.lookback = lookback
        self.tol_pct = tol_pct
        self.pin_ratio = pin_ratio

        self._in_position = False
        self._entry_price: Optional[float] = None

        self.set_parameters(
            lookback=lookback, tol_pct=tol_pct, pin_ratio=pin_ratio,
        )
        self._init_risk_state()
        logger.info(
            f"PureKeyLevelReversal initialized: lookback={lookback}, tol_pct={tol_pct}"
        )

    def reset(self):
        super().reset()
        self._in_position = False
        self._entry_price = None

    @staticmethod
    def _detect_engulfing(prev_o, prev_c, curr_o, curr_c) -> Optional[str]:
        """吞没形态。"""
        if prev_c < prev_o and curr_c > curr_o:
            if curr_c > prev_o and curr_o < prev_c:
                return "bullish"
        if prev_c > prev_o and curr_c < curr_o:
            if curr_c < prev_o and curr_o > prev_c:
                return "bearish"
        return None

    @staticmethod
    def _detect_pin(o, h, l, c, min_ratio) -> Optional[str]:
        """pin bar。"""
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

    def on_bar(self, data: pd.DataFrame, current_time: datetime) -> Optional[str]:
        if len(data) < self.lookback + 2:
            return None

        if self._is_paused(current_time):
            return None

        row = data.iloc[-1]
        prev = data.iloc[-2]
        close = float(row["close"])

        # 止损检查
        if self._in_position:
            triggered, reason = self._check_stop_loss(
                close, current_time, atr=None
            )
            if triggered:
                self._in_position = False
                self._entry_price = None
                return "SELL"

        # 窗口极值（不含当前根）
        window = data.iloc[-(self.lookback + 1):-1]
        win_high = float(window["high"].max())
        win_low = float(window["low"].min())

        # 反转 K 检测
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

        # 关键位邻近判断（百分比容差）
        near_low = abs(close - win_low) / max(close, 1e-9) <= self.tol_pct
        near_high = abs(close - win_high) / max(close, 1e-9) <= self.tol_pct

        if not self._in_position:
            if near_low and bull_rev:
                self._in_position = True
                self._entry_price = close
                logger.info(
                    f"PureKeyLevelReversal BUY: close={close:.2f} "
                    f"near low={win_low:.2f} (tol={self.tol_pct:.3%})"
                )
                return "BUY"
        else:
            # 反向反转 K 离场
            if near_high and bear_rev:
                self._in_position = False
                self._entry_price = None
                logger.info(
                    f"PureKeyLevelReversal SELL: close={close:.2f} "
                    f"near high={win_high:.2f} bear reversal"
                )
                return "SELL"

        return None


__all__ = ["PureKeyLevelReversalStrategy"]
