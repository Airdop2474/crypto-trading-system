"""
策略进化记录 (strategy_evolutions)

每次策略参数优化（Walk-Forward 搜索 + 安全校验 + LLM 解读）产生一条记录。
"""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import BigInteger, Boolean, DateTime, Float, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base


class StrategyEvolution(Base):
    __tablename__ = "strategy_evolutions"
    __table_args__ = (
        Index("ix_evo_strategy_timestamp", "strategy_id", "timestamp"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    strategy_id: Mapped[str] = mapped_column(String(128), nullable=False)
    strategy_name: Mapped[str] = mapped_column(String(64), nullable=False)

    # 参数（JSONB 灵活存储）
    old_params: Mapped[dict] = mapped_column(JSONB, nullable=False)
    new_params: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    # 优化前后指标
    old_metrics: Mapped[dict] = mapped_column(JSONB, nullable=False)
    new_metrics: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    # 安全护栏
    guardrail_passed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    guardrail_reasons: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)

    # LLM 解读
    llm_provider: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    llm_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    llm_confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # 结果
    applied: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    walk_forward_windows: Mapped[int] = mapped_column(Integer, nullable=False, default=3)

    # 审计关联
    audit_log_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)

    def __repr__(self) -> str:
        return (
            f"<StrategyEvolution {self.id} {self.strategy_id} "
            f"passed={self.guardrail_passed} applied={self.applied}>"
        )
