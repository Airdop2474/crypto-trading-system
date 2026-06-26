from typing import Optional
from datetime import datetime

import pandas as pd
import numpy as np

from src.strategy.risk_aware import RiskAwareStrategy
from src.utils.logger import logger


class VolumePriceDivergenceStrategy(RiskAwareStrategy):
    """量价背离策略

    价格创新高但 volume 低于前 N 根平均 → 顶背离（动能衰竭）→ 离场/不入场。
    价格创新低但 volume 放大 → 底背离 → 抄底信号。

    本策略做多：底背离时入场（价格新低 + 放量）。
    """

    PARAM_SCHEMA = {
        "n":    {"type": int,   "min": 5, "max": 100, "default": 20},
        "mult": {"type": float, "min": 1.0, "max": 5.0, "default": 1.3},
    }

    def __init__(self, n=20, mult=1.3,
                 max_consecutive_losses=3, max_daily_loss=0.02,
                 initial_capital=10000.0, stop_loss_config=None):
        super().__init__(name="VolumePriceDivergence",
                         max_consecutive_losses=max_consecutive_losses,
                         max_daily_loss=max_daily_loss,
                         initial_capital=initial_capital,
                         stop_loss_config=stop_loss_config)
        self.n = n
        self.mult = mult
        self._in_position = False
        self.set_parameters(n=n, mult=mult)
        self._init_risk_state()
        logger.info(f"VolumePriceDivergence initialized: n={n}, mult={mult}")

    def reset(self):
        super().reset()
        self._in_position = False

    def on_bar(self, data, current_time):
        if len(data) < self.n + 1:
            return None
        if self._is_paused(current_time):
            return None
        close = float(data["close"].iloc[-1])
        if self._in_position:
            t, _ = self._check_stop_loss(close, current_time, atr=None)
            if t:
                self._in_position = False
                return "SELL"

        row = data.iloc[-1]
        vol = float(row["volume"])
        window = data.iloc[-(self.n + 1):-1]
        avg_vol = float(window["volume"].mean())
        if avg_vol <= 0:
            return None
        win_low = float(window["low"].min())
        win_high = float(window["high"].max())

        # 底背离：价格创新低但放量
        bottom_div = close <= win_low and vol > avg_vol * self.mult
        # 顶背离：价格创新高但缩量 → 离场
        top_div = close >= win_high and vol < avg_vol

        if not self._in_position and bottom_div:
            self._in_position = True
            return "BUY"
        if self._in_position and (top_div or close < win_low):
            self._in_position = False
            return "SELL"
        return None


__all__ = ["VolumePriceDivergenceStrategy"]
