"""
AI 审计日志 (audit_log)

替代 JSON 文件存储，记录所有 AI 分析调用。
"""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Boolean, DateTime, Integer, String, Text, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base


class AuditLogEntry(Base):
    __tablename__ = "audit_log"
    __table_args__ = (
        Index("ix_audit_log_task_timestamp", "task", "timestamp"),
    )

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    phase: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    task: Mapped[str] = mapped_column(
        String(64), nullable=False,
        comment="backtest / trade_attribution / risk_checklist / param_sensitivity / weekly_review",
    )
    input_summary: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    output_summary: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    model: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    tokens_used: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, default=0)
    human_approved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    action_taken: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return f"<AuditLogEntry {self.id} task={self.task} approved={self.human_approved}>"
