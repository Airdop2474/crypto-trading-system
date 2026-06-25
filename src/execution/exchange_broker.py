"""
Exchange Broker（Phase 5-6）

三层 Broker 架构中的交易所接口适配层：把统一的 BrokerInterface
映射到 ccxt 交易所 API。Phase 5-6 只用于查询和测试（testnet），
不做实盘资金的额外保护——那是 Live Broker（Phase 7+）的职责。

交易逻辑本身在 Paper Broker 验证，本层只负责接口转换与异常归一化。

参见 docs/technical/BROKER_ARCHITECTURE.md
"""

from typing import Optional

import ccxt

from src.execution.broker import BrokerInterface, Order, OrderResult
from src.utils.logger import logger


class ExchangeBroker(BrokerInterface):
    """交易所接口适配器（Phase 5-6，testnet/查询为主）"""

    def __init__(
        self,
        exchange_id: str = "binance",
        api_key: Optional[str] = None,
        secret: Optional[str] = None,
        testnet: bool = True,
        exchange=None,
    ):
        """
        参数：
            exchange_id: 交易所ID（'binance'）
            api_key: API Key
            secret: Secret
            testnet: 是否使用测试网（Phase 5-6 强制 True）
            exchange: 已构造的交易所实例（依赖注入，主要用于测试）；
                      传 None 时内部用 ccxt 构造。
        """
        self.exchange_id = exchange_id
        self.testnet = testnet
        # 记本实例下过的单 order_id -> symbol：ccxt binance 的 fetch_order/
        # cancel_order 强制要 symbol，下单时记下来供查单/撤单回查。
        self._order_symbols: dict = {}

        if exchange is not None:
            self.exchange = exchange
        else:
            exchange_class = getattr(ccxt, exchange_id)
            params = {
                "apiKey": api_key,
                "secret": secret,
                "enableRateLimit": True,  # 限流保护
                "options": {"defaultType": "spot"},  # 只做现货
            }
            self.exchange = exchange_class(params)
            # 关键：必须用 set_sandbox_mode 才能真正把 API endpoint 切到 testnet。
            # 仅设 options.testnet 不改请求地址——会打到主网（用主网 key 即真实下单）。
            self.exchange.set_sandbox_mode(testnet)

        logger.info(
            f"ExchangeBroker initialized: {exchange_id} (testnet={testnet})"
        )

    def get_balance(self) -> float:
        """获取账户现金余额（USDT free）"""
        balance = self.exchange.fetch_balance()
        return balance.get("USDT", {}).get("free", 0.0)

    def get_position(self, symbol: str) -> float:
        """获取某交易对的持仓数量（base 币种 free）"""
        symbol = symbol.upper()
        parts = symbol.split("/")
        if len(parts) != 2:
            logger.warning(f"Unexpected symbol format: '{symbol}', expected 'BASE/QUOTE'")
            return 0.0
        balance = self.exchange.fetch_balance()
        base_currency = parts[0]  # 'BTC/USDT' -> 'BTC'
        return balance.get(base_currency, {}).get("free", 0.0)

    def place_order(self, order: Order) -> OrderResult:
        """通过交易所 API 下单（Phase 5-6 仅 testnet 测试）"""
        try:
            result = self.exchange.create_order(
                symbol=order.symbol,
                type=order.order_type,
                side=order.side,
                amount=order.amount,
                price=order.price if order.order_type == "limit" else None,
            )
            order_id = result.get("id")
            if order_id is not None:
                self._order_symbols[order_id] = order.symbol
            return OrderResult(
                order_id=order_id,
                status=result.get("status"),
                filled_price=result.get("average"),
                filled_amount=result.get("filled"),
            )
        except ccxt.InsufficientFunds:
            return OrderResult(order_id=None, status="rejected", reason="资金不足")
        except ccxt.NetworkError as e:
            return OrderResult(
                order_id=None, status="error", reason=f"网络错误：{e}"
            )
        except Exception as e:
            return OrderResult(
                order_id=None, status="error", reason=f"下单失败：{e}"
            )

    def cancel_order(self, order_id: str) -> bool:
        """撤单，返回是否成功（带回查 symbol，binance 撤单必需）

        失败时记录异常上下文（订单 ID + 错误类型），便于调用方排查。
        """
        try:
            self.exchange.cancel_order(order_id, self._order_symbols.get(order_id))
            return True
        except ccxt.OrderNotFound:
            logger.warning(f"撤单失败：订单不存在 {order_id}")
            return False
        except ccxt.NetworkError as e:
            logger.warning(f"撤单网络错误 {order_id}: {e}")
            return False
        except Exception as e:
            logger.warning(f"撤单失败 {order_id}: {type(e).__name__}: {e}")
            return False

    def get_order_status(self, order_id: str) -> Optional[dict]:
        """查询订单状态，不存在或失败返回 None（带回查 symbol，binance 查单必需）

        失败时记录异常上下文，便于调用方区分错误类型。
        """
        try:
            return self.exchange.fetch_order(order_id, self._order_symbols.get(order_id))
        except ccxt.OrderNotFound:
            logger.debug(f"查单：订单不存在 {order_id}")
            return None
        except ccxt.NetworkError as e:
            logger.warning(f"查单网络错误 {order_id}: {e}")
            return None
        except Exception as e:
            logger.warning(f"查单失败 {order_id}: {type(e).__name__}: {e}")
            return None


__all__ = ["ExchangeBroker"]
