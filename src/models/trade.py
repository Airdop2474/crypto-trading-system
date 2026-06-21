"""
已平仓交易 (closed_trades)

一次完整的买卖平仓，对应 PaperTradingRunner.closed_trades 条目。
"""

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import BigInteger, DateTime, Double, ForeignKey, String, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base


class ClosedTrade(Base):
    __tablename__ = "closed_trades"
    __table_args__ = (
        Index("ix_closed_trades_run", "run_id"),
        Index("ix_closed_trades_strategy_close", "strategy_id", "close_time"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("strategy_runs.id", ondelete="CASCADE"), nullable=False,
    )
    strategy_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    tag: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, comment="网格层级等标签")
    open_time: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    close_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    open_price: Mapped[Optional[float]] = mapped_column(Double, nullable=True)
    close_price: Mapped[Optional[float]] = mapped_column(Double, nullable=True)
    quantity: Mapped[Optional[float]] = mapped_column(Double, nullable=True)
    profit: Mapped[float] = mapped_column(Double, nullable=False)
    commission: Mapped[Optional[float]] = mapped_column(Double, nullable=True, default=0.0)

    # 关系
    run = relationship("StrategyRun", back_populates="closed_trades")

    def __repr__(self) -> str:
        return f"<ClosedTrade {self.id} {self.strategy_id} profit={self.profit}>"
