from typing import Optional
from datetime import datetime

import pandas as pd
import numpy as np

from src.strategy.risk_aware import RiskAwareStrategy
from src.utils.logger import logger


class TakerBuyRatioStrategy(RiskAwareStrategy):
    """Taker 主动买盘比策略

    taker_buy_base_volume / volume > threshold 时为强势买盘。
    Binance 特有微结构数据。
    threshold 默认 0.6（主动买盘占 60% 以上）。

    注：taker_buy_ratio 是 volume 的衍生量，但基于 Binance 原始字段，
    属于"极宽松派"边界定义。
    """

    PARAM_SCHEMA = {
        "n":         {"type": int,   "min": 5, "max": 100, "default": 20},
        "threshold": {"type": float, "min": 0.5, "max": 0.9, "default": 0.6},
    }

    def __init__(self, n=20, threshold=0.6,
                 max_consecutive_losses=3, max_daily_loss=0.02,
                 initial_capital=10000.0, stop_loss_config=None):
        super().__init__(name="TakerBuyRatio",
                         max_consecutive_losses=max_consecutive_losses,
                         max_daily_loss=max_daily_loss,
                         initial_capital=initial_capital,
                         stop_loss_config=stop_loss_config)
        self.n = n
        self.threshold = threshold
        self._in_position = False
        # 标记是否已警告过数据列缺失（避免每根 bar 都刷日志）
        self._warned_missing_col = False
        self.set_parameters(n=n, threshold=threshold)
        self._init_risk_state()
        logger.info(f"TakerBuyRatio initialized: n={n}, threshold={threshold}")

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

        # 数据列检查：taker_buy_base_volume 是 Binance 原生字段，
        # 但 CCXT 统一 fetch_ohlcv 只返回标准 6 列 OHLCV，不包含此列。
        # 缺失时策略无法计算主动买盘比，记录一次警告后返回 None（不出信号），
        # 避免静默失效让用户误以为策略在运行。
        if "taker_buy_base_volume" not in data.columns:
            if not self._warned_missing_col:
                logger.warning(
                    "TakerBuyRatio: 数据缺少 'taker_buy_base_volume' 列，"
                    "无法计算主动买盘比，策略将不产生信号。"
                    "此策略需要 Binance 原生 klines 数据（12 列），"
                    "当前数据源只提供标准 6 列 OHLCV。"
                )
                self._warned_missing_col = True
            return None

        taker_buy = float(row.get("taker_buy_base_volume", 0))
        if vol <= 0:
            return None
        ratio = taker_buy / vol

        window = data.iloc[-(self.n + 1):-1]
        win_high = float(window["high"].max())
        win_low = float(window["low"].min())

        if not self._in_position and ratio >= self.threshold and close > win_high:
            self._in_position = True
            return "BUY"
        if self._in_position and (ratio < 0.4 or close < win_low):
            self._in_position = False
            return "SELL"
        return None


__all__ = ["TakerBuyRatioStrategy"]
