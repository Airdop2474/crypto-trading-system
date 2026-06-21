"""执行层：Broker 三层架构（Paper / Exchange / Live）+ 风控 + 多策略编排"""

from src.execution.broker import BrokerInterface, Order, OrderResult
from src.execution.exchange_broker import ExchangeBroker
from src.execution.exchange_runner_broker import (
    ExchangeRunnerBroker, ExchangeUnavailable, assess_position_drift,
)
from src.execution.multi_runner import MultiStrategyRunner, StrategyConfig, StrategySlot
from src.execution.order_guard import OrderRateGuard
from src.execution.paper_broker import PaperBroker
from src.execution.paper_report import PaperTradingReportGenerator
from src.execution.paper_trading_runner import PaperTradingRunner
from src.execution.risk_manager import RiskManager, ACTIVE, PAUSED, STOPPED

__all__ = [
    "BrokerInterface",
    "Order",
    "OrderResult",
    "ExchangeBroker",
    "ExchangeRunnerBroker",
    "ExchangeUnavailable",
    "assess_position_drift",
    "MultiStrategyRunner",
    "OrderRateGuard",
    "PaperBroker",
    "PaperTradingRunner",
    "PaperTradingReportGenerator",
    "RiskManager",
    "StrategyConfig",
    "StrategySlot",
    "ACTIVE",
    "PAUSED",
    "STOPPED",
]
