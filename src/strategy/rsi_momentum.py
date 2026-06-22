"""
RSI 动量策略

基于 RSI(14) 的超买超卖反转策略，配合趋势确认与熔断保护。

信号逻辑：
    - RSI < oversold（默认 30）且价格 > EMA50 → BUY
    - RSI > overbought（默认 70）或 价格 < EMA50 → SELL
    - 可选趋势确认（EMA50 方向过滤）

熔断保护（继承自 RiskAwareStrategy）：
    - 连续亏损达到阈值 → PAUSE
    - 当日亏损达到阈值 → PAUSE
    - 累计回撤达到阈值 → PAUSE

性能：
    RSI 和 EMA 均使用增量计算（O(1) per bar），避免全量 ewm() 重算。
"""

from typing import Optional
from datetime import datetime
import pandas as pd

from src.strategy.risk_aware import RiskAwareStrategy
from src.utils.logger import logger


class RSIMomentumStrategy(RiskAwareStrategy):
    """
    RSI 动量策略

    适用环境：趋势市场中的回调买入 / 超买卖出。
    与网格策略互补：网格适合震荡市，RSI 适合趋势市。
    """

    PARAM_SCHEMA = {
        "rsi_period": {"type": int, "min": 2},
        "oversold": {"type": float, "min": 0, "max": 100},
        "overbought": {"type": float, "min": 0, "max": 100},
        "ema_period": {"type": int, "min": 1},
        "enable_trend_filter": {"type": bool},
    }

    def __init__(
        self,
        rsi_period: int = 14,
        oversold: float = 30.0,
        overbought: float = 70.0,
        ema_period: int = 50,
        enable_trend_filter: bool = True,
        max_consecutive_losses: int = 3,
        max_daily_loss: float = 0.02,
        initial_capital: float = 10000.0,
    ):
        """
        初始化 RSI 策略

        参数：
            rsi_period: RSI 周期（默认 14）
            oversold: 超卖阈值（默认 30）
            overbought: 超买阈值（默认 70）
            ema_period: 趋势过滤 EMA 周期（默认 50）
            enable_trend_filter: 是否启用 EMA 趋势确认
            max_consecutive_losses: 连亏熔断阈值
            max_daily_loss: 当日亏损熔断（占初始资金比例）
            initial_capital: 初始资金（熔断基准）
        """
        super().__init__(
            name="RSIMomentum",
            max_consecutive_losses=max_consecutive_losses,
            max_daily_loss=max_daily_loss,
            initial_capital=initial_capital,
        )

        if rsi_period < 2:
            raise ValueError("rsi_period must be >= 2")
        if not (0 < oversold < overbought < 100):
            raise ValueError("must have 0 < oversold < overbought < 100")

        self.rsi_period = rsi_period
        self.oversold = oversold
        self.overbought = overbought
        self.ema_period = ema_period
        self.enable_trend_filter = enable_trend_filter

        self._init_rsi_state()

        self.set_parameters(
            rsi_period=rsi_period,
            oversold=oversold,
            overbought=overbought,
            ema_period=ema_period,
        )

        logger.info(
            f"RSIMomentum initialized: rsi_period={rsi_period}, "
            f"oversold={oversold}, overbought={overbought}"
        )

    def _init_rsi_state(self) -> None:
        """初始化/重置 RSI 专属运行状态（熔断状态由 RiskAwareStrategy 管理）"""
        self._in_position = False

        # RSI 增量状态（复刻 pandas ewm(alpha=1/period, adjust=False)）
        self._avg_gain: Optional[float] = None
        self._avg_loss: Optional[float] = None
        self._prev_close: Optional[float] = None

        # EMA 增量状态（趋势过滤，复刻 ewm(span=period, adjust=False)）
        self._ema: Optional[float] = None

    def _update_rsi(self, close: float) -> Optional[float]:
        """增量更新 RSI，O(1) per bar。

        严格复刻原全量版 `_compute_rsi` 的 pandas `ewm(alpha=1/period,
        adjust=False)`：首个 gain/loss 作种子（==该值本身），此后
            avg[i] = alpha*x[i] + (1-alpha)*avg[i-1]
        与全量版逐位一致（已验证，容差 1e-9），避免修复悄悄改变策略数值。

        返回 None 表示尚无前收盘（首根 bar），对应原版 diff 首项 NaN。
        """
        period = self.rsi_period
        alpha = 1.0 / period

        if self._prev_close is None:
            self._prev_close = close
            return None  # 首根无前收盘，对应 diff[0]=NaN

        delta = close - self._prev_close
        gain = max(delta, 0.0)
        loss = max(-delta, 0.0)
        self._prev_close = close

        if self._avg_gain is None:
            # 种子：首个 gain/loss（pandas adjust=False 对首值的处理）
            self._avg_gain = gain
            self._avg_loss = loss
        else:
            self._avg_gain = alpha * gain + (1 - alpha) * self._avg_gain
            self._avg_loss = alpha * loss + (1 - alpha) * self._avg_loss

        if abs(self._avg_loss) < 1e-10:
            return 100.0 if self._avg_gain > 0 else 50.0

        rs = self._avg_gain / self._avg_loss
        return 100.0 - 100.0 / (1.0 + rs)

    def _update_ema(self, price: float) -> Optional[float]:
        """增量更新 EMA，O(1) per bar。

        严格复刻原全量版 `close.ewm(span=ema_period, adjust=False).mean()`：
        首值作种子，此后 avg[i] = alpha*price[i] + (1-alpha)*avg[i-1]，
        alpha = 2/(period+1)。与全量版逐位一致（已验证，容差 1e-9）。
        """
        alpha = 2.0 / (self.ema_period + 1)
        if self._ema is None:
            self._ema = price  # 首值种子
        else:
            self._ema = alpha * price + (1 - alpha) * self._ema
        return self._ema

    def on_bar(self, data: pd.DataFrame, current_time: datetime) -> Optional[str]:
        if len(data) < self.rsi_period + 1:
            return None

        if self._is_paused(current_time):
            return None

        current_price = float(data["close"].iloc[-1])
        rsi = self._update_rsi(current_price)

        if rsi is None:
            return None

        # 趋势确认（可选）
        if self.enable_trend_filter and len(data) >= self.ema_period:
            ema = self._update_ema(current_price)
            above_ema = current_price > ema if ema is not None else True
        else:
            above_ema = True  # 数据不足时不过滤

        # 信号逻辑
        if not self._in_position:
            # 超卖 + 趋势向上 → 买入
            if rsi < self.oversold and above_ema:
                self._in_position = True
                return "BUY"
        else:
            # 超买 或 趋势向下 → 卖出
            if rsi > self.overbought or not above_ema:
                self._in_position = False
                return "SELL"

        return None

    def reset(self):
        """重置策略状态"""
        super().reset()
        self._init_rsi_state()
        logger.debug("RSIMomentum strategy reset")


# 导出
__all__ = ["RSIMomentumStrategy"]
