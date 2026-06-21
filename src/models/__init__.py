"""
ORM 模型层

所有 SQLAlchemy ORM 模型统一从此包导出。
Base.metadata 供 Alembic / create_all 使用。
"""

from src.models.base import Base

# 导入所有模型以确保 metadata 注册
from src.models.strategy_run import StrategyRun
from src.models.order import Order
from src.models.trade import ClosedTrade
from src.models.position import OpenPosition
from src.models.risk_event import RiskEvent
from src.models.audit_log import AuditLogEntry
from src.models.strategy_evolution import StrategyEvolution

__all__ = [
    "Base",
    "StrategyRun",
    "Order",
    "ClosedTrade",
    "OpenPosition",
    "RiskEvent",
    "AuditLogEntry",
    "StrategyEvolution",
]
