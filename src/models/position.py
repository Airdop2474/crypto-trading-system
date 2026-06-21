"""
当前持仓 (open_positions)

对应 PaperTradingRunner.lots / open_lots 条目。
"""

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import BigInteger, DateTime, Double, ForeignKey, String, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base


class OpenPosition(Base):
    __tablename__ = "open_positions"
    __table_args__ = (
        Index("ix_open_positions_run", "run_id"),
        Index("ix_open_positions_strategy", "strategy_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("strategy_runs.id", ondelete="CASCADE"), nullable=False,
    )
    strategy_id: Mapped[str] = mapped_column(String(128), nullable=False)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    tag: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    amount: Mapped[float] = mapped_column(Double, nullable=False)
    cost_price: Mapped[float] = mapped_column(Double, nullable=False)
    opened_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
        default=lambda: datetime.now(timezone.utc),
    )

    # 关系
    run = relationship("StrategyRun", back_populates="open_positions")

    def __repr__(self) -> str:
        return f"<OpenPosition {self.id} {self.strategy_id} {self.amount}@{self.cost_price}>"
