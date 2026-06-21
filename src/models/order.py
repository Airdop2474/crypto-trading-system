"""
经纪商订单 (orders)

每次成交一条，对应 PaperBroker.orders 或 ExchangeBroker 返回的成交记录。
"""

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import BigInteger, DateTime, Double, ForeignKey, String, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base


class Order(Base):
    __tablename__ = "orders"
    __table_args__ = (
        Index("ix_orders_run_timestamp", "run_id", "timestamp"),
        Index("ix_orders_symbol_timestamp", "symbol", "timestamp"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("strategy_runs.id", ondelete="CASCADE"), nullable=False,
    )
    order_id: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True, comment="经纪商订单号（PAPER_000001 等）",
    )
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    side: Mapped[str] = mapped_column(String(8), nullable=False, comment="buy / sell")
    order_type: Mapped[Optional[str]] = mapped_column(
        String(16), nullable=True, default="market", comment="market / limit",
    )
    amount: Mapped[Optional[float]] = mapped_column(Double, nullable=True)
    reference_price: Mapped[Optional[float]] = mapped_column(Double, nullable=True)
    actual_price: Mapped[Optional[float]] = mapped_column(Double, nullable=True)
    commission: Mapped[Optional[float]] = mapped_column(Double, nullable=True, default=0.0)
    slippage: Mapped[Optional[float]] = mapped_column(Double, nullable=True, default=0.0)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="filled",
        comment="filled / pending / rejected",
    )
    balance_after: Mapped[Optional[float]] = mapped_column(Double, nullable=True)
    position_after: Mapped[Optional[float]] = mapped_column(Double, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    # 关系
    run = relationship("StrategyRun", back_populates="orders")

    def __repr__(self) -> str:
        return f"<Order {self.id} {self.symbol} {self.side} {self.amount}@{self.actual_price}>"
