"""交易所 RunnerBroker 适配层（Phase 7 Stage 3）

把 ExchangeExecutor（Stage 1：sizing + 市价单同步确认真实价量）适配成
PaperTradingRunner 期望的 RunnerBroker 协议（Stage 2 定义），让守护进程能用
`--broker exchange` 在 testnet 真实下单，而 runner 主循环代码不变。

与 PaperBroker 的根本差异：余额/持仓是交易所端真实状态（每次查询），成交价量
由交易所决定。本适配器自维护一个**本地成交账本**（ExchangeBroker 没有
get_statistics/get_trade_history），只为 report/metrics 复用现有形态。

明确放弃：exchange 模式不保证续跑逐位一致（真实成交不可复现）。

边界：不接 daemon（那是 Stage 3b）；纯靠 FakeExchange 注入可离线单测。
"""

from typing import List, Optional

from src.execution.broker import Order, OrderResult
from src.utils.logger import logger


def assess_position_drift(real_pos, initial_pos, local_net, abs_tol, rel_tol):
    """对账：交易所真实净持仓变化是否与本地账本净持仓一致。

    testnet 账户开跑前本就有底仓（如 BTC 1.0），故按 **delta** 比较：
    交易所侧增量 (real - initial) 应约等于本地 lots 净持仓 local_net。

    返回 (ok, drift)；drift = |(real-initial) - local_net|。
    ok = drift <= max(abs_tol, rel_tol*|local_net|)。
    """
    drift = abs((real_pos - initial_pos) - local_net)
    tol = max(abs_tol, rel_tol * abs(local_net))
    return drift <= tol, drift


class ExchangeRunnerBroker:
    """ExchangeExecutor → RunnerBroker 协议适配器（v1 市价单）。"""

    def __init__(self, executor, symbol: str, commission: float = 0.001):
        """
        参数：
            executor: ExchangeExecutor 实例
            symbol: 交易对（如 'BTC/USDT'）
            commission: 计入账本的手续费率（仅用于成本统计/报表）
        """
        self.executor = executor
        self.broker = executor.broker  # 底层 ExchangeBroker（查单/撤单/查询）
        self.symbol = symbol
        self.commission = commission
        self._ledger: List[dict] = []
        self._unconfirmed: List[str] = []
        # 开跑基线：testnet 账户的现有现金/底仓，对账按 delta 扣掉
        self.initial_balance = self.get_balance()
        self.initial_position = self.get_position(symbol)

    # ---- 查询（透传真实交易所状态）----

    def get_balance(self) -> float:
        return self.broker.get_balance()

    def get_position(self, symbol: str) -> float:
        return self.broker.get_position(symbol)

    # ---- 下单（经 executor 做 sizing + 真实成交确认）----

    def place_order(self, order: Order, timestamp=None) -> OrderResult:
        """下市价单并确认真实成交。timestamp 仅记账本（成交时刻由交易所定）。"""
        res = self.executor.place_and_confirm(
            order.symbol, order.side, order.amount, order.price, order_type="market"
        )
        if res.status in ("filled", "partial"):
            self._record_fill(res, order.side, timestamp)
            # partial 归一成 filled：携真实 filled_amount 交给 runner 记账。
            # 市价单 partial 罕见，剩余不重试，靠每 bar 对账兜底。
            return OrderResult(
                order_id=res.order_id, status="filled",
                filled_price=res.filled_price, filled_amount=res.filled_amount,
            )
        if res.status == "timeout":
            # 下单成功但未确认成交：记为待确认，runner 跳过，对账会发现漂移→熔断
            if res.order_id is not None:
                self._unconfirmed.append(res.order_id)
            logger.warning(f"下单未确认成交（待对账）：{order.symbol} {order.side} "
                           f"{order.amount} -> {res.order_id}")
        return res  # timeout / rejected：原样返回，runner 不记账

    def _record_fill(self, res: OrderResult, side: str, timestamp) -> None:
        commission_paid = res.filled_amount * res.filled_price * self.commission
        self._ledger.append({
            "order_id": res.order_id,
            "timestamp": timestamp,
            "symbol": self.symbol,
            "side": side,
            "amount": res.filled_amount,
            "price": res.filled_price,
            "actual_price": res.filled_price,  # 真实成交价已含滑点
            "commission": commission_paid,
            "slippage": 0.0,
            "status": "filled",
        })

    # ---- 撤单/查单（透传，重启对账用）----

    def cancel_order(self, order_id: str) -> bool:
        return self.broker.cancel_order(order_id)

    def get_order_status(self, order_id: str) -> Optional[dict]:
        return self.broker.get_order_status(order_id)

    def reconcile_unconfirmed(self) -> List[str]:
        """重启对账：查每个待确认订单，已了结的清掉，仍挂单的返回（调用方拒绝静默续跑）。"""
        still_open: List[str] = []
        for oid in list(self._unconfirmed):
            status = self.get_order_status(oid)
            if status and status.get("status") in ("open", "pending"):
                still_open.append(oid)
        self._unconfirmed = still_open
        return still_open

    # ---- 统计（本地账本 + 实时余额/持仓）----

    def get_trade_history(self) -> List[dict]:
        return list(self._ledger)

    def get_statistics(self) -> dict:
        total_commission = sum(o["commission"] for o in self._ledger)
        return {
            "initial_balance": self.initial_balance,
            "current_balance": self.get_balance(),
            "total_trades": len(self._ledger),
            "total_commission": total_commission,
            "total_slippage": 0.0,  # 市价真实成交价已含滑点，不单列
            "total_cost": total_commission,
            "positions": {self.symbol: self.get_position(self.symbol)},
        }

    # ---- 检查点（exchange 模式非逐位一致，仅记账本 + 基线 + 待确认）----

    def state_dict(self) -> dict:
        return {
            "ledger": list(self._ledger),
            "unconfirmed": list(self._unconfirmed),
            "initial_balance": self.initial_balance,
            "initial_position": self.initial_position,
        }

    def load_state(self, st: dict) -> None:
        self._ledger = list(st.get("ledger", []))
        self._unconfirmed = list(st.get("unconfirmed", []))
        self.initial_balance = st["initial_balance"]
        self.initial_position = st["initial_position"]


__all__ = ["ExchangeRunnerBroker", "assess_position_drift"]
