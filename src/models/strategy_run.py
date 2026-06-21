"""
策略运行会话 (strategy_runs)

每次 Paper / Backtest / Exchange 运行产生一条记录，
是 orders / closed_trades / open_positions / risk_events 的外键目标。
"""

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import DateTime, Double, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base


class StrategyRun(Base):
    __tablename__ = "strategy_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    strategy_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    timeframe: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    mode: Mapped[Optional[str]] = mapped_column(
        String(16), nullable=True, comment="backtest / paper / exchange",
    )
    initial_capital: Mapped[Optional[float]] = mapped_column(Double, nullable=True)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="running",
        comment="running / completed / failed",
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )
    ended_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    final_equity: Mapped[Optional[float]] = mapped_column(Double, nullable=True)
    realized_pnl: Mapped[Optional[float]] = mapped_column(Double, nullable=True)
    total_return: Mapped[Optional[float]] = mapped_column(Double, nullable=True)
    config: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    # 关系
    orders = relationship("Order", back_populates="run", lazy="noload")
    closed_trades = relationship("ClosedTrade", back_populates="run", lazy="noload")
    open_positions = relationship("OpenPosition", back_populates="run", lazy="noload")
    risk_events = relationship("RiskEvent", back_populates="run", lazy="noload")

    def __repr__(self) -> str:
        return f"<StrategyRun {self.id} strategy_id={self.strategy_id} status={self.status}>"
