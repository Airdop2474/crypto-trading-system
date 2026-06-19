"""
简单移动平均策略

金叉买入，死叉卖出。配合连亏/日亏损熔断保护。
"""

from typing import Optional
from datetime import datetime
import pandas as pd

from src.strategy.base import Strategy
from src.utils.logger import logger


class SimpleMAStrategy(Strategy):
    """
    简单移动平均策略

    逻辑：
    - 短期均线上穿长期均线：买入（金叉）
    - 短期均线下穿长期均线：卖出（死叉）

    风控：
    - 连亏熔断（默认 5 笔）
    - 当日亏损熔断（默认 2%）
    """

    def __init__(
        self,
        short_window: int = 5,
        long_window: int = 10,
        max_consecutive_losses: int = 5,
        max_daily_loss: float = 0.02,
        initial_capital: float = 10000.0,
    ):
        """
        初始化策略

        参数：
            short_window: 短期均线窗口
            long_window: 长期均线窗口
            max_consecutive_losses: 连亏熔断阈值
            max_daily_loss: 当日亏损熔断（占初始资金比例）
            initial_capital: 初始资金（熔断基准）
        """
        super().__init__(name="SimpleMA")
        self.short_window = short_window
        self.long_window = long_window
        self.max_consecutive_losses = max_consecutive_losses
        self.max_daily_loss = max_daily_loss
        self.initial_capital = initial_capital

        self._init_state()
        self.set_parameters(short_window=short_window, long_window=long_window)

    def _init_state(self) -> None:
        """初始化/重置运行状态"""
        self.consecutive_losses = 0
        self.paused = False
        self.current_day = None
        self.daily_pnl = 0.0
        # MA 增量缓存
        self._short_ma: Optional[float] = None
        self._long_ma: Optional[float] = None
        self._prev_short_ma: Optional[float] = None
        self._prev_long_ma: Optional[float] = None

    def on_bar(self, data: pd.DataFrame, current_time: datetime) -> Optional[str]:
        """
        处理每根 K 线

        参数：
            data: 历史数据
            current_time: 当前时间

        返回：
            信号
        """
        # 需要足够的数据计算均线
        if len(data) < self.long_window:
            return None

        if self.paused:
            return None

        close = data["close"]

        # 增量 MA 计算（避免每根 bar 全量 rolling O(n²)）
        if self._short_ma is None:
            # 首次：全量初始化（同时计算当前和前一根 MA，支持单次调用）
            if len(close) < self.long_window:
                return None
            short_ma_series = close.rolling(window=self.short_window).mean()
            long_ma_series = close.rolling(window=self.long_window).mean()

            self._short_ma = float(short_ma_series.iloc[-1])
            self._long_ma = float(long_ma_series.iloc[-1])

            if len(close) > self.long_window:
                self._prev_short_ma = float(short_ma_series.iloc[-2])
                self._prev_long_ma = float(long_ma_series.iloc[-2])
            else:
                self._prev_short_ma = None
                self._prev_long_ma = None
        else:
            # 增量更新：new_ma = old_ma + (new_price - dropped_price) / window
            new_price = float(close.iloc[-1])
            if len(close) > self.short_window:
                old_price_short = float(close.iloc[-self.short_window - 1])
            else:
                old_price_short = float(close.iloc[0])
            if len(close) > self.long_window:
                old_price_long = float(close.iloc[-self.long_window - 1])
            else:
                old_price_long = float(close.iloc[0])

            self._prev_short_ma = self._short_ma
            self._prev_long_ma = self._long_ma
            self._short_ma += (new_price - old_price_short) / self.short_window
            self._long_ma += (new_price - old_price_long) / self.long_window

        # 需要前一根 MA 值才能判断交叉
        if self._prev_short_ma is None or self._prev_long_ma is None:
            return None

        # 检查金叉（买入信号）
        if (self._prev_short_ma <= self._prev_long_ma
                and self._short_ma > self._long_ma):
            return "BUY"

        # 检查死叉（卖出信号）
        if (self._prev_short_ma >= self._prev_long_ma
                and self._short_ma < self._long_ma):
            return "SELL"

        return None

    def on_fill(self, trade: dict) -> None:
        """成交回报：跟踪盈亏，触发连亏/日亏损熔断"""
        profit = trade.get("profit")
        if profit is None:
            return

        trade_day = pd.Timestamp(trade["time"]).date()
        if self.current_day != trade_day:
            self.current_day = trade_day
            self.daily_pnl = 0.0

        self.daily_pnl += profit

        if profit < 0:
            self.consecutive_losses += 1
        elif profit > 0:
            self.consecutive_losses = 0

        if self.consecutive_losses >= self.max_consecutive_losses:
            logger.warning(
                f"SimpleMA PAUSE: {self.consecutive_losses} consecutive losses"
            )
            self.paused = True

        if self.daily_pnl < 0 and self.initial_capital > 0:
            loss_ratio = abs(self.daily_pnl) / self.initial_capital
            if loss_ratio >= self.max_daily_loss:
                logger.warning(f"SimpleMA PAUSE: daily loss {loss_ratio:.2%}")
                self.paused = True

    def reset(self):
        """重置策略状态"""
        super().reset()
        self._init_state()
        logger.debug("SimpleMA strategy reset")


# 导出
__all__ = ["SimpleMAStrategy"]
