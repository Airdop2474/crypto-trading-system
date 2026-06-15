"""
Broker 抽象接口与数据类

定义三层 Broker 架构（Paper / Exchange / Live）的统一接口。
本模块的 Order 是「下单请求」（symbol/side/amount/price），
与 src.strategy.base.Order（回测信号意图）是不同概念。

参见 docs/technical/BROKER_ARCHITECTURE.md
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass
class Order:
    """下单请求"""
    symbol: str
    side: str  # 'buy' or 'sell'
    amount: float  # 基础货币数量（如 BTC 数量）
    price: float
    order_type: str = "limit"  # 'limit' or 'market'


@dataclass
class OrderResult:
    """下单结果"""
    order_id: Optional[str]
    status: str  # 'filled', 'rejected', 'pending', 'error'
    filled_price: Optional[float] = None
    filled_amount: Optional[float] = None
    reason: Optional[str] = None


class BrokerInterface(ABC):
    """Broker 抽象接口"""

    @abstractmethod
    def get_balance(self) -> float:
        """获取账户现金余额（计价货币，如 USDT）"""
        raise NotImplementedError

    @abstractmethod
    def get_position(self, symbol: str) -> float:
        """获取某交易对的持仓数量"""
        raise NotImplementedError

    @abstractmethod
    def place_order(self, order: Order) -> OrderResult:
        """下单"""
        raise NotImplementedError

    @abstractmethod
    def cancel_order(self, order_id: str) -> bool:
        """撤单，返回是否成功"""
        raise NotImplementedError

    @abstractmethod
    def get_order_status(self, order_id: str) -> Optional[dict]:
        """查询订单状态，不存在返回 None"""
        raise NotImplementedError


# 导出
__all__ = ["Order", "OrderResult", "BrokerInterface"]
