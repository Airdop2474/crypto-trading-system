"""
策略基类

所有策略的抽象基类
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional
from datetime import datetime
import pandas as pd

from src.utils.logger import logger


@dataclass
class Order:
    """
    订单意图（多仓位策略使用）

    策略只用网格索引/标签思考，不直接计算数量；
    引擎负责现金、数量、成本的全部计算。

    属性：
        side: 'BUY' 或 'SELL'
        tag: 仓位标签（如网格索引），用于配对买入和卖出
        fraction: 占初始资金的比例（仅 BUY 使用，0-1）
        limit_price: 限价单价格（None 表示市价单，按 next-bar-open 成交）
    """
    side: str
    tag: object
    fraction: float = 0.0
    limit_price: Optional[float] = None


class Strategy(ABC):
    """
    策略抽象基类

    所有策略必须继承此类并实现 on_bar 方法
    """

    def __init__(self, name: str = "BaseStrategy"):
        """
        初始化策略

        参数：
            name: 策略名称
        """
        self.name = name
        self.parameters = {}

    @abstractmethod
    def on_bar(self, data: pd.DataFrame, current_time: datetime):
        """
        处理每根 K 线

        参数：
            data: 历史数据（包括当前 K 线，不包括未来）
            current_time: 当前时间

        返回：
            以下三种之一：
            - None：无操作
            - 'BUY' / 'SELL'：单仓位信号（全仓买入/清仓卖出）
            - List[Order]：多仓位订单（网格等多档策略）
        """
        pass

    def on_fill(self, trade: dict) -> None:
        """
        成交回报钩子（可选）

        引擎在每笔订单成交后调用，策略可借此跟踪盈亏、
        实现连亏/当日亏损等熔断逻辑。默认不做任何处理。

        参数：
            trade: 成交记录字典
        """
        pass

    def reset(self):
        """
        重置策略状态（每次回测前调用）
        """
        logger.debug(f"Strategy {self.name} reset")

    def set_parameters(self, **kwargs):
        """设置策略参数"""
        self.parameters.update(kwargs)
        logger.info(f"Strategy {self.name} parameters updated: {self.parameters}")

    def __repr__(self):
        return f"{self.__class__.__name__}(name={self.name})"


# 导出
__all__ = ["Strategy", "Order"]
