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
    order_type: str = "market"  # 'market', 'limit', 'stop_limit'
    limit_price: Optional[float] = None  # 限价单价格 / stop-limit 的限价
    stop_price: Optional[float] = None   # stop-limit 的触发价
    # 幂等键：用于网络错误后对账查询，避免重复下单。
    # 由调用方生成（如 strategy_id-bar_ts-side-amount_hash），传给交易所做去重。
    client_order_id: Optional[str] = None


@dataclass
class OrderResult:
    """下单结果

    status 取值：
    - 'filled'/'partial'：已成交（携带真实价量）
    - 'rejected'：交易所拒单（资金不足、sizing 不过等，无 order_id）
    - 'pending'：挂单等待成交（限价单未触发）
    - 'pending_query'：下单请求已发但响应丢失（网络错误），需后续对账。
    - 'timeout'：下单成功但确认超时（有 order_id，调用方决定撤单/对账）
    - 'error'：其他未知错误
    """
    order_id: Optional[str]
    status: str
    filled_price: Optional[float] = None
    filled_amount: Optional[float] = None
    reason: Optional[str] = None
    # 携带 client_order_id 便于后续对账查询（网络错误时尤其重要）
    client_order_id: Optional[str] = None


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
