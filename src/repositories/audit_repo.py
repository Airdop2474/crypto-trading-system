"""
审计日志数据访问（audit_log 表）

提供与 src/agent/audit_log.py::AuditLog 同接口的 DB 操作。
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.models.audit_log import AuditLogEntry
from src.utils.logger import logger


class AuditRepository:
    """AI 审计日志数据访问"""

    @staticmethod
    def insert_entry(session: Session, entry: dict) -> str:
        """插入一条审计日志，返回 entry id。"""
        row = AuditLogEntry(
            id=entry["id"],
            timestamp=entry.get("timestamp", datetime.now(timezone.utc)),
            phase=entry.get("phase"),
            task=entry["task"],
            input_summary=entry.get("input_summary"),
            output_summary=entry.get("output_summary"),
            model=entry.get("model", "local-analyzer"),
            tokens_used=entry.get("tokens_used", 0),
            human_approved=entry.get("human_approved", False),
            action_taken=entry.get("action_taken"),
        )
        session.add(row)
        session.flush()
        logger.debug(f"AuditLog inserted: {entry['id']}")
        return entry["id"]

    @staticmethod
    def get_logs(
        session: Session,
        task: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """查询审计日志，按时间倒序。"""
        stmt = select(AuditLogEntry).order_by(AuditLogEntry.timestamp.desc())
        if task:
            stmt = stmt.where(AuditLogEntry.task == task)
        stmt = stmt.limit(limit)

        rows = session.scalars(stmt).all()
        return [
            {
                "id": r.id,
                "timestamp": r.timestamp.isoformat() if r.timestamp else "",
                "phase": r.phase or "",
                "task": r.task,
                "input_summary": r.input_summary or {},
                "output_summary": r.output_summary or {},
                "model": r.model or "",
                "tokens_used": r.tokens_used or 0,
                "human_approved": r.human_approved,
                "action_taken": r.action_taken,
            }
            for r in rows
        ]

    @staticmethod
    def update_approval(
        session: Session,
        audit_id: str,
        approved: bool,
        action_taken: Optional[str] = None,
    ) -> bool:
        """更新采纳状态，返回是否找到并更新。"""
        row = session.get(AuditLogEntry, audit_id)
        if row is None:
            return False
        row.human_approved = approved
        row.action_taken = action_taken
        session.flush()
        logger.debug(f"AuditLog updated: {audit_id}, approved={approved}")
        return True

    @staticmethod
    def get_adoption_rate(
        session: Session,
        task: Optional[str] = None,
    ) -> Dict[str, Any]:
        """统计 AI 建议采纳率。"""
        stmt = select(AuditLogEntry)
        if task:
            stmt = stmt.where(AuditLogEntry.task == task)

        rows = session.scalars(stmt).all()
        total = len(rows)
        approved = sum(1 for r in rows if r.human_approved)

        return {
            "total_calls": total,
            "approved": approved,
            "adoption_rate": approved / total if total > 0 else 0.0,
            "task": task or "all",
        }
