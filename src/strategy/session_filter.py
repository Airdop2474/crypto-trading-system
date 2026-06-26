from typing import Optional
from datetime import datetime

import pandas as pd
import numpy as np

from src.strategy.risk_aware import RiskAwareStrategy
from src.utils.logger import logger


class SessionFilterStrategy(RiskAwareStrategy):
    """时段过滤策略

    仅在指定时段（亚/欧/美盘）允许交易。
    直觉：BTC 不同时段 K 线信号可信度不同，美股盘(16-24 UTC)波动大、突破更有效。

    时段定义（UTC 小时）：
      asia:  00-08
      euro:  08-16
      us:    16-24
    """

    PARAM_SCHEMA = {
        "session": {"type": str, "default": "us"},
    }

    SESSIONS = {
        "asia": (0, 8),
        "euro": (8, 16),
        "us":   (16, 24),
    }

    def __init__(self, session="us",
                 max_consecutive_losses=3, max_daily_loss=0.02,
                 initial_capital=10000.0, stop_loss_config=None):
        super().__init__(name="SessionFilter",
                         max_consecutive_losses=max_consecutive_losses,
                         max_daily_loss=max_daily_loss,
                         initial_capital=initial_capital,
                         stop_loss_config=stop_loss_config)
        if session not in self.SESSIONS:
            raise ValueError(f"session must be one of {list(self.SESSIONS)}")
        self.session = session
        self._in_position = False
        self.set_parameters(session=session)
        self._init_risk_state()
        logger.info(f"SessionFilter initialized: session={session}")

    def reset(self):
        super().reset()
        self._in_position = False

    def on_bar(self, data, current_time):
        if self._is_paused(current_time):
            return None
        close = float(data["close"].iloc[-1])
        if self._in_position:
            t, _ = self._check_stop_loss(close, current_time, atr=None)
            if t:
                self._in_position = False
                return "SELL"

        # 时段判断（UTC）
        hour = current_time.hour
        start, end = self.SESSIONS[self.session]
        in_session = start <= hour < end

        # 简单突破逻辑作为信号
        if len(data) < 21:
            return None
        window = data.iloc[-21:-1]
        win_high = float(window["high"].max())
        win_low = float(window["low"].min())

        if not self._in_position:
            if in_session and close > win_high:
                self._in_position = True
                return "BUY"
        else:
            # 出时段或跌破 low 即离场
            if (not in_session) or close < win_low:
                self._in_position = False
                return "SELL"
        return None


__all__ = ["SessionFilterStrategy"]
