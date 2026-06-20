"""
买入持有策略

最简单的策略，用于验证回测引擎
"""

from typing import Optional
from datetime import datetime
import pandas as pd

from src.strategy.risk_aware import RiskAwareStrategy


class BuyAndHoldStrategy(RiskAwareStrategy):
    """
    买入持有策略

    在第一根 K 线买入，在最后一根 K 线卖出
    """

    PARAM_SCHEMA = {}

    def __init__(self):
        super().__init__(name="BuyAndHold")
        self._init_risk_state()
        self.has_bought = False
        self.bar_count = 0

    def on_bar(self, data: pd.DataFrame, current_time: datetime) -> Optional[str]:
        """
        处理每根 K 线

        逻辑：
        - 第一根 K 线：买入
        - 最后一根 K 线：卖出
        - 其他时间：持有

        参数：
            data: 历史数据
            current_time: 当前时间

        返回：
            信号
        """
        self.bar_count += 1

        # 第一根 K 线买入
        if not self.has_bought:
            self.has_bought = True
            return "BUY"

        # 注意：这里无法知道是否是最后一根 K 线
        # 所以买入持有策略需要外部手动触发卖出
        return None

    def reset(self):
        """重置策略状态"""
        super().reset()
        self.has_bought = False
        self.bar_count = 0


# 导出
__all__ = ["BuyAndHoldStrategy"]
