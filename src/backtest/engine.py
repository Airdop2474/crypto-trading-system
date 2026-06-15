"""回测引擎.

事件驱动的 Bar-by-bar 回测引擎
"""

from datetime import datetime
from typing import Any, Dict, List

import pandas as pd

from src.backtest.metrics import PerformanceMetrics
from src.strategy.base import Order
from src.utils.logger import logger


class BacktestEngine:
    """
    回测引擎

    核心原则：
    1. Bar-by-bar 迭代，避免前视偏差
    2. 事件顺序：K线闭合 -> 计算指标 -> 生成信号 -> 下一根K线开盘成交
    3. 严格的时间戳管理

    仓位模型（统一分仓）：
    - 持仓以「标签分仓」管理：self.lots[tag] = {"qty", "cost_price"}
    - 单仓位策略（返回 'BUY'/'SELL'）走全仓买入/清仓卖出路径
    - 多仓位策略（返回 List[Order]）按标签独立建仓/平仓
    """

    LEGACY_TAG = "_all"

    def __init__(
        self,
        initial_capital: float = 10000.0,
        commission: float = 0.001,  # 0.1%
        slippage: float = 0.0005,   # 0.05%
    ):
        """
        初始化回测引擎

        参数：
            initial_capital: 初始资金
            commission: 手续费率
            slippage: 滑点率
        """
        self.initial_capital = initial_capital
        self.commission = commission
        self.slippage = slippage

        # Portfolio 状态
        self.cash = initial_capital
        # 标签分仓：tag -> {"qty": 数量, "cost_price": 含滑点的成交价}
        self.lots: Dict[Any, Dict[str, float]] = {}

        # 记录
        self.trades: List[Dict[str, Any]] = []  # 交易记录
        self.equity_curve: List[Dict[str, Any]] = []  # 权益曲线
        self.signals: List[Dict[str, Any]] = []  # 信号记录

        # 当前状态
        self.current_time: datetime | None = None
        self.current_bar: pd.Series | None = None

        logger.info(
            f"BacktestEngine initialized: "
            f"capital={initial_capital}, "
            f"commission={commission}, "
            f"slippage={slippage}"
        )

    @property
    def position(self) -> float:
        """总持仓数量（所有分仓之和，兼容旧接口）"""
        return sum(lot["qty"] for lot in self.lots.values())


    def run(
        self,
        data: pd.DataFrame,
        strategy,
    ) -> Dict[str, Any]:
        """
        运行回测

        参数：
            data: OHLCV 数据
            strategy: 策略实例

        返回：
            回测结果字典
        """
        logger.info(f"Starting backtest with {len(data)} bars")

        # 重置状态
        self._reset()

        # 初始化策略
        strategy.reset()

        # Bar-by-bar 迭代
        for i in range(len(data)):
            # 当前 bar（已经闭合）
            self.current_bar = data.iloc[i]
            self.current_time = self.current_bar["timestamp"]

            # 策略可以使用到 i 为止的所有数据（不包括未来）
            historical_data = data.iloc[: i + 1].copy()

            # 调用策略的 on_bar
            signal = strategy.on_bar(historical_data, self.current_time)

            # 记录信号
            if signal:
                self.signals.append({
                    "time": self.current_time,
                    "signal": signal,
                })

            # 下一根 bar 的开盘价成交（避免前视偏差）
            if i < len(data) - 1:
                next_bar = data.iloc[i + 1]
                execution_price = next_bar["open"]
                execution_time = next_bar["timestamp"]

                self._dispatch_signal(
                    signal, execution_price, execution_time, strategy
                )

            # 更新权益
            self._update_equity(self.current_bar["close"])

        logger.info(f"Backtest completed: {len(self.trades)} trades")

        # 返回结果
        return self._generate_results()

    def _dispatch_signal(
        self,
        signal,
        price: float,
        time: datetime,
        strategy,
    ) -> None:
        """
        分发信号到对应的成交路径

        - 'BUY'/'SELL'：单仓位（全仓买入/清仓卖出）
        - List[Order]：多仓位（按标签建仓/平仓）
        """
        if signal == "BUY":
            self._execute_buy(price, time, strategy)
        elif signal == "SELL":
            self._execute_sell(price, time, strategy)
        elif isinstance(signal, list):
            for order in signal:
                self._execute_order(order, price, time, strategy)

    def _execute_buy(self, price: float, time: datetime, strategy=None) -> None:
        """执行全仓买入（单仓位路径）：用全部现金买入到 LEGACY_TAG 分仓"""
        if self.position != 0:
            return

        # 计算滑点后的价格（买入时价格更高）
        execution_price = price * (1 + self.slippage)

        # 计算可买数量（扣除手续费）
        cost_per_unit = execution_price * (1 + self.commission)
        quantity = self.cash / cost_per_unit

        if quantity > 0:
            self.lots[self.LEGACY_TAG] = {
                "qty": quantity,
                "cost_price": execution_price,
            }

            # 更新现金
            total_cost = quantity * cost_per_unit
            self.cash -= total_cost

            # 记录交易
            trade = {
                "time": time,
                "type": "BUY",
                "price": execution_price,
                "quantity": quantity,
                "cost": total_cost,
                "commission": quantity * execution_price * self.commission,
                "slippage": quantity * price * self.slippage,
            }
            self.trades.append(trade)
            self._notify_fill(strategy, trade)

            logger.debug(
                f"BUY: {quantity:.4f} @ {execution_price:.2f}, "
                f"cost={total_cost:.2f}"
            )

    def _execute_sell(self, price: float, time: datetime, strategy=None) -> None:
        """执行清仓卖出（单仓位路径）：平掉 LEGACY_TAG 分仓"""
        if self.position <= 0:
            return

        lot = self.lots.get(self.LEGACY_TAG)
        if lot is None:
            return

        qty = lot["qty"]
        cost_price = lot["cost_price"]

        # 计算滑点后的价格（卖出时价格更低）
        execution_price = price * (1 - self.slippage)

        # 计算收益
        proceeds = qty * execution_price * (1 - self.commission)

        # 更新现金
        self.cash += proceeds

        # 记录交易
        trade = {
            "time": time,
            "type": "SELL",
            "price": execution_price,
            "quantity": qty,
            "proceeds": proceeds,
            "commission": qty * execution_price * self.commission,
            "slippage": qty * price * self.slippage,
            "profit": proceeds - (qty * cost_price * (1 + self.commission)),
        }
        self.trades.append(trade)

        logger.debug(
            f"SELL: {qty:.4f} @ {execution_price:.2f}, "
            f"proceeds={proceeds:.2f}, "
            f"profit={trade['profit']:.2f}"
        )

        # 清空分仓
        del self.lots[self.LEGACY_TAG]
        self._notify_fill(strategy, trade)

    def _execute_order(
        self,
        order: Order,
        price: float,
        time: datetime,
        strategy=None,
    ) -> None:
        """执行多仓位订单（按标签建仓/平仓）"""
        if order.side == "BUY":
            self._open_lot(order, price, time, strategy)
        elif order.side == "SELL":
            self._close_lot(order, price, time, strategy)

    def _open_lot(
        self,
        order: Order,
        price: float,
        time: datetime,
        strategy=None,
    ) -> None:
        """按标签建仓：使用 fraction * 初始资金（受可用现金限制）"""
        budget = min(order.fraction * self.initial_capital, self.cash)
        if budget <= 0:
            return

        execution_price = price * (1 + self.slippage)
        cost_per_unit = execution_price * (1 + self.commission)
        quantity = budget / cost_per_unit
        if quantity <= 0:
            return

        total_cost = quantity * cost_per_unit
        self.cash -= total_cost

        # 同标签已有分仓则按加权平均合并成本
        existing = self.lots.get(order.tag)
        if existing:
            total_qty = existing["qty"] + quantity
            existing["cost_price"] = (
                existing["qty"] * existing["cost_price"]
                + quantity * execution_price
            ) / total_qty
            existing["qty"] = total_qty
        else:
            self.lots[order.tag] = {
                "qty": quantity,
                "cost_price": execution_price,
            }

        trade = {
            "time": time,
            "type": "BUY",
            "tag": order.tag,
            "price": execution_price,
            "quantity": quantity,
            "cost": total_cost,
            "commission": quantity * execution_price * self.commission,
            "slippage": quantity * price * self.slippage,
        }
        self.trades.append(trade)
        self._notify_fill(strategy, trade)

        logger.debug(
            f"BUY[{order.tag}]: {quantity:.4f} @ {execution_price:.2f}, "
            f"cost={total_cost:.2f}"
        )

    def _close_lot(
        self,
        order: Order,
        price: float,
        time: datetime,
        strategy=None,
    ) -> None:
        """按标签平仓：卖出该标签的全部数量"""
        lot = self.lots.get(order.tag)
        if lot is None or lot["qty"] <= 0:
            return

        qty = lot["qty"]
        cost_price = lot["cost_price"]

        execution_price = price * (1 - self.slippage)
        proceeds = qty * execution_price * (1 - self.commission)
        self.cash += proceeds

        trade = {
            "time": time,
            "type": "SELL",
            "tag": order.tag,
            "price": execution_price,
            "quantity": qty,
            "proceeds": proceeds,
            "commission": qty * execution_price * self.commission,
            "slippage": qty * price * self.slippage,
            "profit": proceeds - (qty * cost_price * (1 + self.commission)),
        }
        self.trades.append(trade)

        del self.lots[order.tag]
        self._notify_fill(strategy, trade)

        logger.debug(
            f"SELL[{order.tag}]: {qty:.4f} @ {execution_price:.2f}, "
            f"proceeds={proceeds:.2f}, profit={trade['profit']:.2f}"
        )

    @staticmethod
    def _notify_fill(strategy, trade: Dict[str, Any]) -> None:
        """成交后回调策略的 on_fill 钩子（若存在）"""
        if strategy is not None and hasattr(strategy, "on_fill"):
            strategy.on_fill(trade)

    def _update_equity(self, current_price: float) -> None:
        """更新权益曲线"""
        if self.current_time is None:
            return

        # 当前权益 = 现金 + 持仓市值
        position_value = self.position * current_price
        total_equity = self.cash + position_value

        self.equity_curve.append(
            {
                "time": self.current_time,
                "cash": self.cash,
                "position_value": position_value,
                "total_equity": total_equity,
            }
        )

    def _reset(self) -> None:
        """重置回测状态"""
        self.cash = self.initial_capital
        self.lots = {}
        self.trades = []
        self.equity_curve = []
        self.signals = []
        self.current_time = None
        self.current_bar = None

    def _generate_results(self) -> Dict[str, Any]:
        """生成回测结果"""
        if not self.equity_curve:
            return {
                "success": False,
                "message": "No equity curve data",
            }

        # 最终权益
        final_equity = self.equity_curve[-1]["total_equity"]

        # 基本指标
        total_return = (final_equity - self.initial_capital) / self.initial_capital

        # 构建基础结果
        results = {
            "success": True,
            "initial_capital": self.initial_capital,
            "final_equity": final_equity,
            "total_return": total_return,
            "total_trades": len(self.trades),
            "equity_curve": self.equity_curve,
            "trades": self.trades,
            "signals": self.signals,
        }

        # 计算性能指标
        metrics = PerformanceMetrics.calculate_all(results)
        results["metrics"] = metrics

        return results


# 导出
__all__ = ["BacktestEngine"]
