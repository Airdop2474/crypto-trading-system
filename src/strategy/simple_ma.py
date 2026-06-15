"""
简单移动平均策略

金叉买入，死叉卖出
"""

from typing import Optional
from datetime import datetime
import pandas as pd

from src.strategy.base import Strategy


class SimpleMAStrategy(Strategy):
    """
    简单移动平均策略

    逻辑：
    - 短期均线上穿长期均线：买入（金叉）
    - 短期均线下穿长期均线：卖出（死叉）
    """

    def __init__(self, short_window: int = 5, long_window: int = 10):
        """
        初始化策略

        参数：
            short_window: 短期均线窗口
            long_window: 长期均线窗口
        """
        super().__init__(name="SimpleMA")
        self.short_window = short_window
        self.long_window = long_window
        self.set_parameters(short_window=short_window, long_window=long_window)

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

        # 计算短期和长期均线
        short_ma = data["close"].rolling(window=self.short_window).mean()
        long_ma = data["close"].rolling(window=self.long_window).mean()

        # 当前和前一根 K 线的均线值
        if len(short_ma) < 2 or len(long_ma) < 2:
            return None

        short_ma_current = short_ma.iloc[-1]
        short_ma_previous = short_ma.iloc[-2]
        long_ma_current = long_ma.iloc[-1]
        long_ma_previous = long_ma.iloc[-2]

        # 检查金叉（买入信号）
        if short_ma_previous <= long_ma_previous and short_ma_current > long_ma_current:
            return "BUY"

        # 检查死叉（卖出信号）
        if short_ma_previous >= long_ma_previous and short_ma_current < long_ma_current:
            return "SELL"

        return None


# 导出
__all__ = ["SimpleMAStrategy"]
