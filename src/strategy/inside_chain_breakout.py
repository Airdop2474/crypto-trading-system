from typing import Optional
from datetime import datetime

import pandas as pd
import numpy as np

from src.strategy.risk_aware import RiskAwareStrategy
from src.utils.logger import logger


class InsideChainBreakoutStrategy(RiskAwareStrategy):
    """内含线链突破策略

    连续 chain_len 根内含线（母子嵌套）后突破母线。
    反向跌破母线 low 离场。
    """

    PARAM_SCHEMA = {
        "chain_len": {"type": int, "min": 1, "max": 5, "default": 2},
    }

    def __init__(self, chain_len=2,
                 max_consecutive_losses=3, max_daily_loss=0.02,
                 initial_capital=10000.0, stop_loss_config=None):
        super().__init__(name="InsideChainBreakout",
                         max_consecutive_losses=max_consecutive_losses,
                         max_daily_loss=max_daily_loss,
                         initial_capital=initial_capital,
                         stop_loss_config=stop_loss_config)
        self.chain_len = chain_len
        self._in_position = False
        self._mother_high = None
        self._mother_low = None
        self.set_parameters(chain_len=chain_len)
        self._init_risk_state()
        logger.info(f"InsideChainBreakout initialized: chain={chain_len}")

    def reset(self):
        super().reset()
        self._in_position = False
        self._mother_high = None
        self._mother_low = None

    def on_bar(self, data, current_time):
        if len(data) < self.chain_len + 2:
            return None
        if self._is_paused(current_time):
            return None
        close = float(data["close"].iloc[-1])
        if self._in_position:
            t, _ = self._check_stop_loss(close, current_time, atr=None)
            if t:
                self._in_position = False
                return "SELL"
            if self._mother_low is not None and close < self._mother_low:
                self._in_position = False
                return "SELL"

        # 检查前 chain_len 根是否都为内含线
        # 内含线：当前 high<=前根 high 且 low>=前根 low
        inside_chain = True
        mother_h = None
        mother_l = None
        for i in range(1, self.chain_len + 1):
            curr_idx = -i
            prev_idx = -i - 1
            if -prev_idx > len(data):
                inside_chain = False
                break
            curr_h = float(data.iloc[curr_idx]["high"])
            curr_l = float(data.iloc[curr_idx]["low"])
            prev_h = float(data.iloc[prev_idx]["high"])
            prev_l = float(data.iloc[prev_idx]["low"])
            if not (curr_h <= prev_h and curr_l >= prev_l):
                inside_chain = False
                break
            if i == self.chain_len:
                # 最外层母线
                mother_h = prev_h
                mother_l = prev_l

        if not inside_chain or mother_h is None:
            return None

        self._mother_high = mother_h
        self._mother_low = mother_l

        row = data.iloc[-1]
        c = float(row["close"])
        if not self._in_position and c > mother_h:
            self._in_position = True
            return "BUY"
        return None


__all__ = ["InsideChainBreakoutStrategy"]
