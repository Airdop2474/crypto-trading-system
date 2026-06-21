"""
风控事件日志 (risk_events)

记录 RiskManager 的状态转换和熔断事件。
"""

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, Text, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base


class RiskEvent(Base):
    __tablename__ = "risk_events"
    __table_args__ = (
        Index("ix_risk_events_timestamp", "timestamp"),
        Index("ix_risk_events_run", "run_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    run_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("strategy_runs.id", ondelete="SET NULL"), nullable=True,
    )
    event_type: Mapped[str] = mapped_column(
        String(32), nullable=False,
        comment="PAUSE / RESUME / EMERGENCY_STOP / CIRCUIT_BREAK",
    )
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    state: Mapped[Optional[str]] = mapped_column(
        String(16), nullable=True, comment="事件后状态：ACTIVE / PAUSED / STOPPED",
    )
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    # 关系
    run = relationship("StrategyRun", back_populates="risk_events")

    def __repr__(self) -> str:
        return f"<RiskEvent {self.id} {self.event_type} at {self.timestamp}>"
