"""
AI Agent 审计日志

记录所有 AI 分析调用，满足 AI_USAGE_BOUNDARIES.md 的审计要求：
- 时间戳
- 分析任务类型
- 输入摘要
- 输出摘要
- 是否人工采纳
- 执行的动作（如果有）

存储：DB 优先（audit_log 表），JSON 文件回退。
"""

import json
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone

from src.utils.logger import logger
from src.utils.database import db


class AuditLog:
    """AI 分析调用审计日志（DB 优先 + JSON 回退）"""

    def __init__(self, log_dir: str = "data/reports/agent"):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self._log_file = self.log_dir / "audit_log.json"
        self._lock = threading.Lock()

    def _db_available(self) -> bool:
        """检测 DB 是否可用。"""
        try:
            return db.is_postgres_available()
        except Exception:
            return False

    def record(
        self,
        task: str,
        phase: str,
        input_summary: Dict[str, Any],
        output_summary: Dict[str, Any],
        model: str = "local-analyzer",
        tokens_used: int = 0,
    ) -> str:
        """
        记录一次 AI 分析调用

        参数：
            task: 分析任务类型 (backtest/trade_attribution/risk_checklist/param_sensitivity/weekly_review)
            phase: 项目阶段 (Phase 1-7)
            input_summary: 输入摘要（脱敏后）
            output_summary: 输出摘要
            model: 使用的模型（默认 local-analyzer）
            tokens_used: token 用量（本地分析器为 0）

        返回：
            日志条目的 ID（用于后续更新采纳状态）
        """
        entry_id = f"{task}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{id(input_summary) % 10000:04d}"

        entry = {
            "id": entry_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "phase": phase,
            "task": task,
            "input_summary": input_summary,
            "output_summary": output_summary,
            "model": model,
            "tokens_used": tokens_used,
            "human_approved": False,
            "action_taken": None,
        }

        # DB 优先
        if self._db_available():
            try:
                from src.repositories.audit_repo import AuditRepository
                with db.get_session() as session:
                    AuditRepository.insert_entry(session, entry)
                    session.commit()
                logger.info(f"Agent audit log recorded (DB): {entry_id}")
                return entry_id
            except Exception as e:
                logger.warning(f"DB audit log failed, falling back to JSON: {e}")

        # JSON 文件回退
        with self._lock:
            logs = self._load_logs()
            logs.append(entry)
            self._save_logs(logs)

        logger.info(f"Agent audit log recorded (JSON): {entry_id}")
        return entry_id

    def update_approval(self, entry_id: str, approved: bool, action: Optional[str] = None) -> bool:
        """
        更新审计条目的采纳状态

        参数：
            entry_id: 日志条目 ID
            approved: 是否被人工采纳
            action: 如果采纳，记录执行的操作

        返回：
            是否成功更新
        """
        # DB 优先
        if self._db_available():
            try:
                from src.repositories.audit_repo import AuditRepository
                with db.get_session() as session:
                    ok = AuditRepository.update_approval(session, entry_id, approved, action)
                    session.commit()
                if ok:
                    logger.info(f"Agent audit log updated (DB): {entry_id}, approved={approved}")
                    return True
            except Exception as e:
                logger.warning(f"DB audit update failed, falling back to JSON: {e}")

        # JSON 文件回退
        with self._lock:
            logs = self._load_logs()
            for entry in logs:
                if entry["id"] == entry_id:
                    entry["human_approved"] = approved
                    entry["action_taken"] = action
                    self._save_logs(logs)
                    logger.info(f"Agent audit log updated (JSON): {entry_id}, approved={approved}")
                    return True

        logger.warning(f"Agent audit log entry not found: {entry_id}")
        return False

    def get_logs(self, task: Optional[str] = None, limit: int = 100) -> List[Dict]:
        """
        查询审计日志

        参数：
            task: 过滤特定任务类型（可选）
            limit: 返回最近 N 条

        返回：
            日志条目列表
        """
        # DB 优先
        if self._db_available():
            try:
                from src.repositories.audit_repo import AuditRepository
                with db.get_session() as session:
                    results = AuditRepository.get_logs(session, task, limit)
                return results
            except Exception as e:
                logger.warning(f"DB audit log query failed, falling back to JSON: {e}")

        # JSON 文件回退
        logs = self._load_logs()
        if task:
            logs = [e for e in logs if e["task"] == task]
        return logs[-limit:]

    def get_adoption_rate(self, task: Optional[str] = None) -> Dict[str, Any]:
        """
        统计 AI 建议采纳率

        参数：
            task: 过滤特定任务类型（可选）

        返回：
            统计结果
        """
        # DB 优先
        if self._db_available():
            try:
                from src.repositories.audit_repo import AuditRepository
                with db.get_session() as session:
                    return AuditRepository.get_adoption_rate(session, task)
            except Exception as e:
                logger.warning(f"DB adoption rate failed, falling back to JSON: {e}")

        # JSON 文件回退
        logs = self._load_logs()
        if task:
            logs = [e for e in logs if e["task"] == task]

        total = len(logs)
        approved = sum(1 for e in logs if e.get("human_approved"))

        return {
            "total_calls": total,
            "approved": approved,
            "adoption_rate": approved / total if total > 0 else 0.0,
            "task": task or "all",
        }

    def _load_logs(self) -> List[Dict]:
        """加载日志文件"""
        if not self._log_file.exists():
            return []
        try:
            return json.loads(self._log_file.read_text(encoding="utf-8"))
        except Exception:
            return []

    def _save_logs(self, logs: List[Dict]) -> None:
        """保存日志文件"""
        self._log_file.write_text(
            json.dumps(logs, indent=2, ensure_ascii=False, default=str),
            encoding="utf-8",
        )


# 导出
__all__ = ["AuditLog"]
