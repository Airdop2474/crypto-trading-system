"""
Paper Broker（Phase 4）

三层 Broker 架构中最完善的实现：完整的资金/仓位/成本/风控逻辑，
纯模拟、不接交易所、不涉及真实资金。所有交易逻辑在此验证，
Exchange/Live Broker 只是接口切换。

参见 docs/technical/BROKER_ARCHITECTURE.md
"""

from datetime import datetime
from typing import Dict, List, Optional

from src.execution.broker import BrokerInterface, Order, OrderResult
from src.utils.logger import logger


class PaperBroker(BrokerInterface):
    """模拟交易 Broker"""

    def __init__(
        self,
        initial_balance: float,
        commission: float = 0.001,
        slippage: Optional[Dict[str, float]] = None,
        max_position_per_trade: float = 0.20,
        max_total_position: float = 0.60,
    ):
        """
        参数：
            initial_balance: 初始资金（计价货币）
            commission: 手续费率（0.1%）
            slippage: 各交易对滑点率，默认 BTC 0.05% / ETH 0.1%
            max_position_per_trade: 单笔最大仓位占比
            max_total_position: 总仓位最大占比
        """
        if initial_balance <= 0:
            raise ValueError("initial_balance must be positive")

        self.initial_balance = initial_balance
        self.balance = initial_balance
        self.commission = commission
        self.slippage = slippage or {"BTC/USDT": 0.0005, "ETH/USDT": 0.001}
        self.max_position_per_trade = max_position_per_trade
        self.max_total_position = max_total_position

        self.positions: Dict[str, float] = {}
        self.orders: List[dict] = []
        self.order_id_counter = 0

        logger.info(
            f"PaperBroker initialized: balance={initial_balance}, "
            f"commission={commission}"
        )

    # ---- 查询 ----

    def get_balance(self) -> float:
        return self.balance

    def get_position(self, symbol: str) -> float:
        return self.positions.get(symbol, 0.0)

    def get_total_value(self, current_prices: Dict[str, float]) -> float:
        """账户总价值 = 现金 + 各持仓市值"""
        total = self.balance
        for symbol, amount in self.positions.items():
            if amount != 0:
                total += amount * current_prices.get(symbol, 0.0)
        return total

    # ---- 下单 ----

    def place_order(self, order: Order) -> OrderResult:
        """
        下单（简化：价格触及即按下单价 + 滑点立即成交）

        流程：参数校验 -> 风控 -> 资金/持仓校验 -> 计算成本 -> 更新状态 -> 记录
        """
        if order.amount <= 0:
            return OrderResult(None, "rejected", reason="下单数量必须为正")

        if order.side not in ("buy", "sell"):
            return OrderResult(None, "rejected", reason=f"无效方向：{order.side}")

        # 风控检查（仅买入加仓需要）
        if order.side == "buy" and not self._check_risk_limits(order):
            return OrderResult(None, "rejected", reason="风控拒绝：超过仓位限制")

        slippage_pct = self.slippage.get(order.symbol, 0.0005)

        if order.side == "buy":
            actual_price = order.price * (1 + slippage_pct)
            cost = order.amount * actual_price * (1 + self.commission)
            if cost > self.balance:
                return OrderResult(
                    None, "rejected",
                    reason=f"资金不足：需要 {cost:.2f}，余额 {self.balance:.2f}",
                )
            self.balance -= cost
            self.positions[order.symbol] = (
                self.positions.get(order.symbol, 0.0) + order.amount
            )
        else:  # sell
            current = self.get_position(order.symbol)
            if order.amount > current:
                return OrderResult(
                    None, "rejected",
                    reason=f"持仓不足：需要 {order.amount}，持仓 {current}",
                )
            actual_price = order.price * (1 - slippage_pct)
            proceeds = order.amount * actual_price * (1 - self.commission)
            self.balance += proceeds
            self.positions[order.symbol] = current - order.amount

        commission_paid = order.amount * actual_price * self.commission
        slippage_paid = order.amount * abs(actual_price - order.price)

        order_id = self._generate_order_id()
        self.orders.append({
            "order_id": order_id,
            "timestamp": datetime.now(),
            "symbol": order.symbol,
            "side": order.side,
            "amount": order.amount,
            "price": order.price,
            "actual_price": actual_price,
            "commission": commission_paid,
            "slippage": slippage_paid,
            "status": "filled",
            "balance_after": self.balance,
            "position_after": self.positions.get(order.symbol, 0.0),
        })

        logger.debug(
            f"{order.side.upper()} {order.amount} {order.symbol} "
            f"@ {actual_price:.2f} -> {order_id}"
        )

        return OrderResult(
            order_id=order_id,
            status="filled",
            filled_price=actual_price,
            filled_amount=order.amount,
        )

    def cancel_order(self, order_id: str) -> bool:
        """撤单：简化版立即成交，无挂单可撤"""
        return False

    def get_order_status(self, order_id: str) -> Optional[dict]:
        for order in self.orders:
            if order["order_id"] == order_id:
                return order
        return None

    # ---- 风控 ----

    def _check_risk_limits(self, order: Order) -> bool:
        """单笔 <= max_position_per_trade，总仓位 <= max_total_position"""
        total_value = self.balance + sum(
            amt * order.price for amt in self.positions.values()
        )
        if total_value <= 0:
            return False

        order_value = order.amount * order.price
        if order_value / total_value > self.max_position_per_trade:
            return False

        new_total = sum(self.positions.values()) + order.amount
        if (new_total * order.price) / total_value > self.max_total_position:
            return False

        return True

    def _generate_order_id(self) -> str:
        self.order_id_counter += 1
        return f"PAPER_{self.order_id_counter:06d}"

    # ---- 统计 ----

    def get_trade_history(self) -> List[dict]:
        return self.orders.copy()

    def get_statistics(self) -> dict:
        total_commission = sum(o["commission"] for o in self.orders)
        total_slippage = sum(o["slippage"] for o in self.orders)
        return {
            "initial_balance": self.initial_balance,
            "current_balance": self.balance,
            "total_trades": len(self.orders),
            "total_commission": total_commission,
            "total_slippage": total_slippage,
            "total_cost": total_commission + total_slippage,
            "positions": self.positions.copy(),
        }


# 导出
__all__ = ["PaperBroker"]
