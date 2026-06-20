"""
Paper Broker（Phase 4）

三层 Broker 架构中最完善的实现：完整的资金/仓位/成本/风控逻辑，
纯模拟、不接交易所、不涉及真实资金。所有交易逻辑在此验证，
Exchange/Live Broker 只是接口切换。

参见 docs/technical/BROKER_ARCHITECTURE.md
"""

from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional

from src.execution.broker import BrokerInterface, Order, OrderResult
from src.utils.logger import logger
from src.utils.trading import apply_slippage


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
        # 限价单挂单队列：待撮合的订单
        self.pending_orders: List[dict] = []

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

    def place_order(self, order: Order, **kwargs) -> OrderResult:
        """
        下单：支持市价单（立即成交）和限价单（挂单等待撮合）

        市价单（order_type='market' 或 limit_price=None）：
            按 order.price ± 滑点立即成交

        限价单（order_type='limit' 且 limit_price != None）：
            - BUY limit_price=P：当市场价格 <= P 时按 P 成交
            - SELL limit_price=P：当市场价格 >= P 时按 P 成交
            如果不满足条件，订单进入 pending_orders 队列等待

        timestamp: 成交时间。回测/纸面运行应传入当根 bar 时间。
        """
        timestamp = kwargs.get("timestamp")
        if order.amount <= 0:
            return OrderResult(None, "rejected", reason="下单数量必须为正")

        if order.side not in ("buy", "sell"):
            return OrderResult(None, "rejected", reason=f"无效方向：{order.side}")

        # 风控检查（仅买入加仓需要）
        if order.side == "buy" and not self._check_risk_limits(order):
            return OrderResult(None, "rejected", reason="风控拒绝：超过仓位限制")

        # 限价单：检查是否可立即成交
        limit_price = getattr(order, 'limit_price', None)
        is_limit = order.order_type == "limit" and limit_price is not None

        if is_limit:
            # BUY limit: 当前价 <= limit_price 才能立即成交
            # SELL limit: 当前价 >= limit_price 才能立即成交
            can_fill_now = False
            if order.side == "buy" and order.price <= limit_price:
                can_fill_now = True
            elif order.side == "sell" and order.price >= limit_price:
                can_fill_now = True

            if not can_fill_now:
                # 挂入 pending 队列
                return self._place_pending_limit(order, timestamp)

        # 市价单 或 可立即成交的限价单 → 立即成交
        return self._fill_order(order, order.price, timestamp)

    def _fill_order(self, order: Order, exec_price: float, timestamp) -> OrderResult:
        """立即成交逻辑（从原 place_order 提取）

        限价单按精确限价成交（无额外滑点），市价单施加滑点。
        """
        slippage_pct = self.slippage.get(order.symbol, 0.0005)
        is_limit = order.order_type == "limit" and getattr(order, 'limit_price', None) is not None

        if order.side == "buy":
            actual_price = exec_price if is_limit else apply_slippage(exec_price, slippage_pct, "buy")
            cost = float(
                Decimal(str(order.amount)) * Decimal(str(actual_price))
                * (Decimal("1") + Decimal(str(self.commission)))
            )
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
            actual_price = exec_price if is_limit else apply_slippage(exec_price, slippage_pct, "sell")
            proceeds = float(
                Decimal(str(order.amount)) * Decimal(str(actual_price))
                * (Decimal("1") - Decimal(str(self.commission)))
            )
            self.balance += proceeds
            self.positions[order.symbol] = current - order.amount

        commission_paid = float(
            Decimal(str(order.amount)) * Decimal(str(actual_price))
            * Decimal(str(self.commission))
        )
        slippage_paid = (
            0.0
            if is_limit
            else float(
                Decimal(str(order.amount))
                * abs(Decimal(str(actual_price)) - Decimal(str(exec_price)))
            )
        )

        order_id = self._generate_order_id()
        self.orders.append({
            "order_id": order_id,
            "timestamp": timestamp if timestamp is not None else datetime.now(),
            "symbol": order.symbol,
            "side": order.side,
            "order_type": order.order_type,
            "amount": order.amount,
            "price": exec_price,
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

    def _place_pending_limit(self, order: Order, timestamp) -> OrderResult:
        """将限价单放入挂单队列"""
        order_id = self._generate_order_id()
        limit_price = order.limit_price

        # 买入限价单需预留资金
        if order.side == "buy":
            reserved = order.amount * limit_price * (1 + self.commission)
            if reserved > self.balance:
                return OrderResult(
                    None, "rejected",
                    reason=f"资金不足：需预留 {reserved:.2f}，余额 {self.balance:.2f}",
                )
            self.balance -= reserved  # 冻结资金

        # 卖出限价单需检查持仓
        elif order.side == "sell":
            current = self.get_position(order.symbol)
            if order.amount > current:
                return OrderResult(
                    None, "rejected",
                    reason=f"持仓不足：需要 {order.amount}，持仓 {current}",
                )
            # 冻结持仓（减少可用）
            self.positions[order.symbol] = current - order.amount

        self.pending_orders.append({
            "order_id": order_id,
            "order": order,
            "placed_at": timestamp if timestamp is not None else datetime.now(),
        })

        logger.debug(
            f"LIMIT {order.side.upper()} {order.amount} {order.symbol} "
            f"@ {limit_price:.2f} -> {order_id} (pending)"
        )

        return OrderResult(
            order_id=order_id,
            status="pending",
            filled_price=None,
            filled_amount=0.0,
        )

    def check_pending_orders(
        self,
        bar_high: float,
        bar_low: float,
        timestamp=None,
    ) -> List[OrderResult]:
        """检查挂单队列，撮合满足条件的限价单。

        在每根 bar 处理时调用，用 bar 的 high/low 判断是否触及限价：
        - BUY limit P：bar_low <= P 时按 P 成交（价格跌到了限价）
        - SELL limit P：bar_high >= P 时按 P 成交（价格涨到了限价）

        参数：
            bar_high: 当前 bar 最高价
            bar_low: 当前 bar 最低价
            timestamp: 撮合时间

        返回：
            本 bar 成交的 OrderResult 列表
        """
        filled_results = []
        remaining = []

        for pending in self.pending_orders:
            order = pending["order"]
            limit_price = order.limit_price
            filled = False

            if order.side == "buy" and bar_low <= limit_price:
                # 解冻资金（_fill_order 会重新扣除实际成本）
                reserved = order.amount * limit_price * (1 + self.commission)
                self.balance += reserved
                result = self._fill_order(order, limit_price, timestamp)
                filled = True

            elif order.side == "sell" and bar_high >= limit_price:
                # 解冻持仓（_fill_order 会重新扣除）
                current = self.positions.get(order.symbol, 0.0)
                self.positions[order.symbol] = current + order.amount
                result = self._fill_order(order, limit_price, timestamp)
                filled = True

            if filled:
                if result.status == "filled":
                    filled_results.append(result)
                # 如果成交失败（资金/持仓不足），挂单作废
            else:
                remaining.append(pending)

        self.pending_orders = remaining
        return filled_results

    def cancel_order(self, order_id: str) -> bool:
        """撤单：取消挂单队列中的限价单，解冻资金/持仓"""
        for i, pending in enumerate(self.pending_orders):
            if pending["order_id"] == order_id:
                order = pending["order"]
                limit_price = order.limit_price

                # 解冻
                if order.side == "buy":
                    reserved = order.amount * limit_price * (1 + self.commission)
                    self.balance += reserved
                elif order.side == "sell":
                    current = self.positions.get(order.symbol, 0.0)
                    self.positions[order.symbol] = current + order.amount

                self.pending_orders.pop(i)
                logger.debug(f"CANCEL {order_id}")
                return True

        return False

    def get_order_status(self, order_id: str) -> Optional[dict]:
        for order in self.orders:
            if order["order_id"] == order_id:
                return order
        return None

    # ---- 风控 ----

    def _check_risk_limits(self, order: Order) -> bool:
        """单笔 <= max_position_per_trade，总仓位 <= max_total_position

        注意：当前实现假设单币种交易——sum(self.positions.values()) 把所有币种
        数量相加、统一乘 order.price。多币种场景下此计算不正确（不同币种不可
        直接相加、价格不可混用）。本项目当前只交易单币种（BTC/USDT），若将来
        扩展多币种需改为按各币种当前价格分别折算。
        """
        assert len(self.positions) <= 1, "Multi-currency risk calc not validated"
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
