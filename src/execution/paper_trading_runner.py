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

from typing import Dict, List, Optional

import pandas as pd

from src.execution.broker import Order as BrokerOrder
from src.execution.paper_broker import PaperBroker
from src.strategy.base import Order as StrategyOrder
from src.utils.logger import logger


class PaperTradingRunner:
    """策略 → PaperBroker 运行循环"""

    LEGACY_TAG = "_all"

    def __init__(self, broker: PaperBroker, symbol: str, risk_manager=None,
                 metrics_collector=None):
        """
        参数：
            broker: PaperBroker 实例
            symbol: 交易对（如 'BTC/USDT'）
            risk_manager: 可选 RiskManager，提供账户级熔断门禁
            metrics_collector: 可选 MetricsCollector，逐根采集运行时指标快照
        """
        self.broker = broker
        self.symbol = symbol
        self.risk_manager = risk_manager
        self.metrics_collector = metrics_collector
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

        # 无前视：bar t 的信号在 bar t+1 开盘成交。用 pending 串接，逐 bar 推进，
        # 与守护进程（run_paper_trading_daemon）共用同一 process_bar 逻辑。
        pending = None
        for i in range(len(data)):
            bar = data.iloc[i]
            historical = data.iloc[: i + 1]
            pending = self.process_bar(bar, historical, strategy, pending)
            if pending:
                signals_log.append({"time": bar["timestamp"], "signal": pending})

        return self._build_result(signals_log)

    def process_bar(self, bar, historical, strategy, pending_signal):
        """处理单根 bar（批量与实时共用）：

        1. 先按本 bar 开盘价执行上一根挂起的信号（无前视：t-1 信号 / t 开盘成交）
        2. 用含本 bar 的历史计算新信号，作为下一根的 pending 返回
        3. 用本 bar 收盘价采集一次指标快照

        参数 pending_signal 为上一次调用返回的信号（首根传 None）。
        """
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

    def _current_state_result(self) -> Dict:
        """构造运行中状态快照（MetricsCollector.snapshot 所需的 runner_result 形态）。"""
        return {
            "statistics": self.broker.get_statistics(),
            "realized_pnl": self.realized_pnl,
            "open_lots": {t: lot["amount"] for t, lot in self.lots.items()},
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
        """处理多仓位 strategy.Order（按 tag）"""
        if order.side == "BUY":
            amount = self._fraction_amount(order.fraction, exec_price)
            self._buy(order.tag, amount, exec_price, exec_time, strategy)
        elif order.side == "SELL":
            lot = self.lots.get(order.tag)
            if lot and lot["amount"] > 0:
                self._sell(order.tag, lot["amount"], exec_price, exec_time, strategy)

    def _buy(self, tag, amount, price, time, strategy) -> None:
        """下买单；成交后记录该 tag 的数量与成本价（加权平均）"""
        if amount <= 0:
            return
        result = self.broker.place_order(
            BrokerOrder(self.symbol, "buy", amount, price, "market"), timestamp=time
        )
        if result.status != "filled":
            return

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

    def _sell(self, tag, amount, price, time, strategy) -> None:
        """下卖单；成交后算 profit（同回测引擎公式）并清除记账"""
        if amount <= 0:
            return
        lot = self.lots.get(tag)
        result = self.broker.place_order(
            BrokerOrder(self.symbol, "sell", amount, price, "market"), timestamp=time
        )
        if result.status != "filled":
            return

        profit = None
        if lot is not None:
            qty = result.filled_amount
            proceeds = qty * result.filled_price * (1 - self.broker.commission)
            cost_basis = qty * lot["cost_price"] * (1 + self.broker.commission)
            profit = proceeds - cost_basis
            self.realized_pnl += profit
            self.closed_trades.append({"tag": tag, "time": time, "profit": profit})

        self.lots.pop(tag, None)
        self._notify_fill(strategy, result, "sell", tag, time, profit=profit)

    def _all_cash_amount(self, price: float) -> float:
        """用全部现金可买的数量（含滑点+手续费余量）"""
        slip = self.broker.slippage.get(self.symbol, 0.0005)
        unit_cost = price * (1 + slip) * (1 + self.broker.commission)
        return self.broker.get_balance() / unit_cost if unit_cost > 0 else 0.0

    def _fraction_amount(self, fraction: float, price: float) -> float:
        """按初始资金比例可买的数量"""
        slip = self.broker.slippage.get(self.symbol, 0.0005)
        unit_cost = price * (1 + slip) * (1 + self.broker.commission)
        budget = fraction * self.broker.initial_balance
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
            "open_lots": {t: lot["amount"] for t, lot in self.lots.items()},
            "realized_pnl": self.realized_pnl,
            "closed_trades": list(self.closed_trades),
        }


# 导出
__all__ = ["PaperTradingRunner"]
