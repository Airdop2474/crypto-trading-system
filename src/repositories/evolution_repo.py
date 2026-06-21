"""
策略进化数据访问 (strategy_evolutions 表)
"""

from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.models.strategy_evolution import StrategyEvolution
from src.utils.logger import logger


class EvolutionRepository:
    """策略进化记录数据访问"""

    @staticmethod
    def create(session: Session, data: dict) -> int:
        """写入一条进化记录，返回 id。"""
        row = StrategyEvolution(
            strategy_id=data["strategy_id"],
            strategy_name=data["strategy_name"],
            old_params=data["old_params"],
            new_params=data.get("new_params"),
            old_metrics=data["old_metrics"],
            new_metrics=data.get("new_metrics"),
            guardrail_passed=data["guardrail_passed"],
            guardrail_reasons=data.get("guardrail_reasons"),
            llm_provider=data.get("llm_provider"),
            llm_summary=data.get("llm_summary"),
            llm_confidence=data.get("llm_confidence"),
            applied=data.get("applied", False),
            walk_forward_windows=data.get("walk_forward_windows", 3),
            audit_log_id=data.get("audit_log_id"),
        )
        session.add(row)
        session.flush()
        logger.debug(f"Evolution created: {row.id} ({row.strategy_id})")
        return row.id

    @staticmethod
    def get_history(
        session: Session,
        strategy_id: Optional[str] = None,
        limit: int = 50,
    ) -> list[dict]:
        """查询进化历史，按时间倒序。"""
        stmt = select(StrategyEvolution).order_by(StrategyEvolution.timestamp.desc())
        if strategy_id:
            stmt = stmt.where(StrategyEvolution.strategy_id == strategy_id)
        stmt = stmt.limit(limit)

        rows = session.scalars(stmt).all()
        return [EvolutionRepository._to_dict(r) for r in rows]

    @staticmethod
    def get_latest(session: Session, strategy_id: str) -> Optional[dict]:
        """获取某策略最近一次进化记录。"""
        stmt = (
            select(StrategyEvolution)
            .where(StrategyEvolution.strategy_id == strategy_id)
            .order_by(StrategyEvolution.timestamp.desc())
            .limit(1)
        )
        row = session.scalars(stmt).first()
        return EvolutionRepository._to_dict(row) if row else None

    @staticmethod
    def get_stats(session: Session) -> dict:
        """聚合统计：总进化次数、采纳数、平均 Sharpe 提升。"""
        stmt = select(StrategyEvolution)
        rows = session.scalars(stmt).all()

        total = len(rows)
        applied_count = sum(1 for r in rows if r.applied)

        # 计算平均 Sharpe 提升（仅统计 applied 且有新旧指标的记录）
        sharpe_improvements = []
        for r in rows:
            if r.applied and r.old_metrics and r.new_metrics:
                old_s = r.old_metrics.get("sharpe_ratio", 0)
                new_s = r.new_metrics.get("sharpe_ratio", 0)
                if old_s and old_s > 0:
                    sharpe_improvements.append((new_s - old_s) / abs(old_s))

        avg_sharpe_improvement = (
            sum(sharpe_improvements) / len(sharpe_improvements)
            if sharpe_improvements
            else 0.0
        )

        return {
            "total_evolutions": total,
            "applied_count": applied_count,
            "avg_sharpe_improvement": round(avg_sharpe_improvement, 4),
        }

    @staticmethod
    def _to_dict(row: StrategyEvolution) -> dict:
        """ORM 对象转 dict。"""
        return {
            "id": row.id,
            "timestamp": row.timestamp.isoformat() if row.timestamp else "",
            "strategy_id": row.strategy_id,
            "strategy_name": row.strategy_name,
            "old_params": row.old_params or {},
            "new_params": row.new_params,
            "old_metrics": row.old_metrics or {},
            "new_metrics": row.new_metrics,
            "guardrail_passed": row.guardrail_passed,
            "guardrail_reasons": row.guardrail_reasons or [],
            "llm_provider": row.llm_provider,
            "llm_summary": row.llm_summary,
            "llm_confidence": row.llm_confidence,
            "applied": row.applied,
            "walk_forward_windows": row.walk_forward_windows,
            "audit_log_id": row.audit_log_id,
        }
