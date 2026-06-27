"""
Paper Trading 运行循环

把策略与 PaperBroker 连通：逐根喂历史数据，驱动策略生成信号，
经 Broker 模拟成交。保持与回测一致的无前视偏差时序：
bar t 收盘生成信号 -> bar t+1 开盘价经 Broker 成交。

适配职责（关键）：
- 策略按 tag 分档管理（strategy.base.Order: tag/fraction）
- Broker 只按 symbol 记净持仓（execution.Order: symbol/amount/price）
- Runner 维护 tag -> amount 记账，把分档拍平成 Broker 的单 symbol 下单，
  并在平仓时按 tag 找回对应数量。
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Protocol

import pandas as pd

from src.execution.broker import Order as BrokerOrder
from src.execution.broker import OrderResult
from src.strategy.base import Order as StrategyOrder
from src.utils.logger import logger


def _make_client_order_id(symbol: str, side: str, time, amount: float) -> str:
    """生成幂等 clientOrderId：symbol-side-timestamp-amount_hash

    用途：传给交易所做去重，网络错误后用此键对账查询，避免重复下单。
    规则：同一 bar 同方向同数量的订单生成相同 ID（幂等）；
    不同 bar/方向/数量生成不同 ID（区分）。
    """
    import hashlib
    # 归一化：symbol 小写、amount 取 8 位小数避免浮点抖动
    sym = symbol.replace("/", "").lower()
    amt = f"{amount:.8f}"
    ts = str(time)
    raw = f"{sym}-{side}-{ts}-{amt}"
    # 取 8 位短 hash 拼接，保证 ID 可读且不超长（交易所通常限制 36 字符）
    h = hashlib.md5(raw.encode()).hexdigest()[:8]
    return f"{sym}-{side}-{h}"


@dataclass(frozen=True)
class ExecutionConfig:
    """成交经济参数（手续费/滑点/初始资金）。

    Stage 2：把 runner 对 broker 内部经济参数的读取收口到这里。paper 路径用
    `from_broker(broker)` 快照，数值与原先逐位一致；将来 exchange 路径（Stage 3）
    显式传入真实手续费/滑点/起始权益，runner 主循环不再触碰 broker 内部。
    """

    commission: float
    slippage: Dict[str, float]
    initial_balance: float

    @classmethod
    def from_broker(cls, broker) -> "ExecutionConfig":
        """从 PaperBroker 快照经济参数（slippage 按引用，运行中不被改写）。"""
        return cls(
            commission=broker.commission,
            slippage=broker.slippage,
            initial_balance=broker.initial_balance,
        )


class RunnerBroker(Protocol):
    """runner 运行所需的最小 broker 协议（仅类型提示，无运行时开销）。

    刻意不继承 BrokerInterface：保持窄接口，便于 Stage 3 用 exchange 适配器替换。
    """

    def get_balance(self) -> float: ...

    def get_position(self, symbol: str) -> float: ...

    def place_order(self, order: BrokerOrder, timestamp=None) -> OrderResult: ...

    def get_statistics(self) -> dict: ...

    def get_trade_history(self) -> List[dict]: ...


class PaperTradingRunner:
    """策略 → PaperBroker 运行循环"""

    LEGACY_TAG = "_all"

    def __init__(self, broker: RunnerBroker, symbol: str, risk_manager=None,
                 metrics_collector=None, exec_config: Optional[ExecutionConfig] = None):
        """
        参数：
            broker: 满足 RunnerBroker 协议的实例（paper 为 PaperBroker）
            symbol: 交易对（如 'BTC/USDT'）
            risk_manager: 可选 RiskManager，提供账户级熔断门禁
            metrics_collector: 可选 MetricsCollector，逐根采集运行时指标快照
            exec_config: 可选成交经济参数；省略则从 broker 快照（paper 路径行为不变）
        """
        self.broker = broker
        self.symbol = symbol
        self.risk_manager = risk_manager
        self.metrics_collector = metrics_collector
        self.exec_cfg = exec_config or ExecutionConfig.from_broker(broker)
        # tag -> {"amount": 数量, "cost_price": 加权平均成本价}
        self.lots: Dict[object, Dict[str, float]] = {}
        # 累计已实现盈亏（卖出时累加）
        self.realized_pnl: float = 0.0
        # 逐笔平仓记录：{tag, time, profit}，用于精确胜率/复盘
        self.closed_trades: List[dict] = []

    def run(self, data: pd.DataFrame, strategy) -> Dict:
        """
        逐根回放数据驱动策略经 Broker 成交

        参数：
            data: OHLCV 数据（需含 timestamp/open/close）
            strategy: 策略实例

        返回：
            运行结果字典（统计 + 成交历史 + 信号）
        """
        strategy.reset()
        self.lots = {}
        self.realized_pnl = 0.0
        self.closed_trades = []
        signals_log = []

        # 模拟盘批量回放时不推送 Hermes 事件（避免生成数据产生大量无意义事件）
        from src.agent.hermes_bridge import set_events_enabled, events_enabled
        _was_enabled = events_enabled()
        set_events_enabled(False)

        # 无前视：bar t 的信号在 bar t+1 开盘成交。用 pending 串接，逐 bar 推进，
        # 与守护进程（run_paper_trading_daemon）共用同一 process_bar 逻辑。
        pending = None
        for i in range(len(data)):
            bar = data.iloc[i]
            historical = data.iloc[: i + 1]
            pending = self.process_bar(bar, historical, strategy, pending)
            if pending:
                signals_log.append({"time": bar["timestamp"], "signal": pending})

        set_events_enabled(_was_enabled)
        return self._build_result(signals_log)

    def process_bar(self, bar, historical, strategy, pending_signal):
        """处理单根 bar（批量与实时共用）：

        0. 先检查 Broker 的限价挂单（用本 bar 的 high/low 撮合）
        1. 再按本 bar 开盘价执行上一根挂起的信号（无前视：t-1 信号 / t 开盘成交）
        2. 用含本 bar 的历史计算新信号，作为下一根的 pending 返回
        3. 用本 bar 收盘价采集一次指标快照

        参数 pending_signal 为上一次调用返回的信号（首根传 None）。
        """
        # 限价单撮合：用本 bar 的 high/low 检查挂单队列
        self._check_pending_limit_orders(bar, strategy)

        if pending_signal is not None:
            self._execute_signal(
                pending_signal, bar["open"], bar["timestamp"], strategy
            )

        signal = strategy.on_bar(historical, bar["timestamp"])

        if self.metrics_collector is not None:
            self.metrics_collector.snapshot(
                self._current_state_result(),
                {self.symbol: bar["close"]},
                risk_manager=self.risk_manager,
                timestamp=bar["timestamp"],
            )

        return signal

    def _check_pending_limit_orders(self, bar, strategy) -> None:
        """检查并撮合挂单队列中的限价单"""
        if not hasattr(self.broker, 'check_pending_orders'):
            return
        if not self.broker.pending_orders:
            return

        results = self.broker.check_pending_orders(
            bar_high=bar["high"],
            bar_low=bar["low"],
            timestamp=bar["timestamp"],
        )
        # 对每笔成交更新 lots 记账并通知策略
        for result in results:
            # 从 broker 的 orders 记录找到对应的 side 和 tag
            order_record = self.broker.get_order_status(result.order_id)
            if order_record is None:
                continue
            side = order_record["side"]
            # 查找 pending_limit 中标记的 tag
            tag = order_record.get("_tag", self.LEGACY_TAG)
            if side == "buy":
                self._record_buy_fill(tag, result, strategy, bar["timestamp"])
            elif side == "sell":
                self._record_sell_fill(tag, result, strategy, bar["timestamp"])

    def _current_state_result(self) -> Dict:
        """构造运行中状态快照（MetricsCollector.snapshot 所需的 runner_result 形态）。"""
        return {
            "statistics": self.broker.get_statistics(),
            "realized_pnl": self.realized_pnl,
            "open_lots": {t: {"amount": lot["amount"], "cost_price": lot["cost_price"]} for t, lot in self.lots.items()},
        }

    def _execute_signal(self, signal, exec_price, exec_time, strategy) -> None:
        """把策略信号转成 Broker 订单并执行"""
        # 风控门禁：非 ACTIVE 状态不交易
        if self.risk_manager is not None and not self.risk_manager.can_trade():
            return

        if signal == "BUY":
            self._buy(self.LEGACY_TAG, self._all_cash_amount(exec_price),
                      exec_price, exec_time, strategy)
        elif signal == "SELL":
            self._sell(self.LEGACY_TAG, self.broker.get_position(self.symbol),
                       exec_price, exec_time, strategy)
        elif isinstance(signal, list):
            for order in signal:
                self._execute_strategy_order(order, exec_price, exec_time, strategy)

    def _execute_strategy_order(
        self, order: StrategyOrder, exec_price, exec_time, strategy
    ) -> None:
        """处理多仓位 strategy.Order（按 tag），支持限价单"""
        limit_price = getattr(order, 'limit_price', None)

        if order.side == "BUY":
            amount = self._fraction_amount(order.fraction, exec_price)
            self._buy(order.tag, amount, exec_price, exec_time, strategy,
                      limit_price=limit_price)
        elif order.side == "SELL":
            lot = self.lots.get(order.tag)
            if lot and lot["amount"] > 0:
                self._sell(order.tag, lot["amount"], exec_price, exec_time, strategy,
                           limit_price=limit_price)

    def _buy(self, tag, amount, price, time, strategy, limit_price=None) -> None:
        """下买单；成交后记录该 tag 的数量与成本价（加权平均）

        参数 limit_price: 如果非 None，则以限价单方式下单。
        """
        if amount <= 0:
            return
        order_type = "limit" if limit_price is not None else "market"
        broker_order = BrokerOrder(
            self.symbol, "buy", amount, price, order_type,
            client_order_id=_make_client_order_id(self.symbol, "buy", time, amount),
        )
        if limit_price is not None:
            broker_order.limit_price = limit_price
        result = self.broker.place_order(broker_order, timestamp=time)
        if result.status == "filled":
            self._record_buy_fill(tag, result, strategy, time)
        elif result.status == "pending":
            # 限价挂单中，在 broker 的订单记录中标记 tag
            order_record = self.broker.get_order_status(result.order_id)
            if order_record is not None:
                order_record["_tag"] = tag

    def _sell(self, tag, amount, price, time, strategy, limit_price=None) -> None:
        """下卖单；成交后算 profit（同回测引擎公式）并清除记账

        参数 limit_price: 如果非 None，则以限价单方式下单。
        """
        if amount <= 0:
            return
        lot = self.lots.get(tag)
        order_type = "limit" if limit_price is not None else "market"
        broker_order = BrokerOrder(
            self.symbol, "sell", amount, price, order_type,
            client_order_id=_make_client_order_id(self.symbol, "sell", time, amount),
        )
        if limit_price is not None:
            broker_order.limit_price = limit_price
        result = self.broker.place_order(broker_order, timestamp=time)
        if result.status == "filled":
            self._record_sell_fill(tag, result, strategy, time)
        elif result.status == "pending":
            # 限价挂单中，标记 tag 并保留 lot（不立即清除）
            order_record = self.broker.get_order_status(result.order_id)
            if order_record is not None:
                order_record["_tag"] = tag

    def _record_buy_fill(self, tag, result, strategy, time) -> None:
        """记录买单成交到 lots 记账"""
        existing = self.lots.get(tag)
        if existing:
            total = existing["amount"] + result.filled_amount
            existing["cost_price"] = (
                existing["amount"] * existing["cost_price"]
                + result.filled_amount * result.filled_price
            ) / total
            existing["amount"] = total
        else:
            self.lots[tag] = {
                "amount": result.filled_amount,
                "cost_price": result.filled_price,
            }
        self._notify_fill(strategy, result, "buy", tag, time, profit=None)

    def _record_sell_fill(self, tag, result, strategy, time) -> None:
        """记录卖单成交，计算 profit 并清除 lot"""
        lot = self.lots.get(tag)
        profit = None
        if lot is not None:
            qty = result.filled_amount
            proceeds = qty * result.filled_price * (1 - self.exec_cfg.commission)
            cost_basis = qty * lot["cost_price"] * (1 + self.exec_cfg.commission)
            profit = proceeds - cost_basis
            self.realized_pnl += profit
            self.closed_trades.append({"tag": tag, "time": time, "profit": profit})
            # Hermes 事件推送
            try:
                from src.agent.hermes_bridge import push_trade_closed
                push_trade_closed({"tag": tag, "time": time, "profit": profit})
            except Exception as e:
                logger.debug(f"Hermes trade_closed 推送失败 (tag={tag}): {e}")
        self.lots.pop(tag, None)
        self._notify_fill(strategy, result, "sell", tag, time, profit=profit)

    def _all_cash_amount(self, price: float) -> float:
        """用全部现金可买的数量（含滑点+手续费余量）"""
        slip = self.exec_cfg.slippage.get(self.symbol, 0.0005)
        unit_cost = price * (1 + slip) * (1 + self.exec_cfg.commission)
        if unit_cost <= 0:
            return 0.0
        # 留 0.1% 余量，避免浮点精度导致 cost > balance 被拒
        return (self.broker.get_balance() * 0.999) / unit_cost

    def _fraction_amount(self, fraction: float, price: float) -> float:
        """按初始资金比例可买的数量"""
        slip = self.exec_cfg.slippage.get(self.symbol, 0.0005)
        unit_cost = price * (1 + slip) * (1 + self.exec_cfg.commission)
        budget = fraction * self.exec_cfg.initial_balance
        return budget / unit_cost if unit_cost > 0 else 0.0

    def _notify_fill(self, strategy, result, side, tag, time, profit) -> None:
        """回写成交给策略 on_fill 与 RiskManager（钩子存在才调）"""
        trade = {
            "time": time,
            "type": side.upper(),
            "tag": tag,
            "price": result.filled_price,
            "quantity": result.filled_amount,
        }
        if profit is not None:
            trade["profit"] = profit
        if hasattr(strategy, "on_fill"):
            strategy.on_fill(trade)
        if self.risk_manager is not None:
            self.risk_manager.record_fill(trade)

    def _build_result(self, signals_log: List[dict]) -> Dict:
        """汇总运行结果"""
        stats = self.broker.get_statistics()
        return {
            "symbol": self.symbol,
            "statistics": stats,
            "trade_history": self.broker.get_trade_history(),
            "signals": signals_log,
            "open_lots": {t: {"amount": lot["amount"], "cost_price": lot["cost_price"]} for t, lot in self.lots.items()},
            "realized_pnl": self.realized_pnl,
            "closed_trades": list(self.closed_trades),
        }


# 导出
__all__ = ["PaperTradingRunner", "ExecutionConfig", "RunnerBroker"]
