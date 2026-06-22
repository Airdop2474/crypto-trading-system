"""
运行会话 CRUD（strategy_runs 表）
"""

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from src.models.strategy_run import StrategyRun
from src.utils.logger import logger


class RunRepository:
    """策略运行会话数据访问"""

    @staticmethod
    def create_run(
        session: Session,
        strategy_id: str,
        symbol: str,
        mode: str = "paper",
        timeframe: Optional[str] = None,
        initial_capital: Optional[float] = None,
        config: Optional[dict] = None,
    ) -> StrategyRun:
        """创建一条新的运行会话记录。"""
        run = StrategyRun(
            id=uuid.uuid4(),
            strategy_id=strategy_id,
            symbol=symbol,
            mode=mode,
            timeframe=timeframe,
            initial_capital=initial_capital,
            status="running",
            config=config,
        )
        session.add(run)
        session.flush()  # 确保 id 已生成
        logger.debug(f"StrategyRun created: {run.id} ({strategy_id})")
        return run

    @staticmethod
    def complete_run(
        session: Session,
        run_id: uuid.UUID,
        final_equity: Optional[float] = None,
        realized_pnl: Optional[float] = None,
        total_return: Optional[float] = None,
        status: str = "completed",
    ) -> Optional[StrategyRun]:
        """标记运行完成并记录最终结果。"""
        run = session.get(StrategyRun, run_id)
        if run is None:
            logger.warning(f"StrategyRun not found: {run_id}")
            return None
        run.status = status
        run.ended_at = datetime.now(timezone.utc)
        run.final_equity = final_equity
        run.realized_pnl = realized_pnl
        run.total_return = total_return
        session.flush()
        logger.debug(f"StrategyRun completed: {run_id}")
        return run

    @staticmethod
    def get_latest_run(
        session: Session,
        strategy_id: str,
    ) -> Optional[StrategyRun]:
        """获取某策略最新的一次运行。"""
        stmt = (
            select(StrategyRun)
            .where(StrategyRun.strategy_id == strategy_id)
            .order_by(StrategyRun.started_at.desc())
            .limit(1)
        )
        return session.scalars(stmt).first()

    @staticmethod
    def get_run(session: Session, run_id: uuid.UUID) -> Optional[StrategyRun]:
        """按 ID 获取运行会话。"""
        return session.get(StrategyRun, run_id)

    @staticmethod
    def get_history(
        session: Session,
        strategy_id: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[dict], int]:
        """分页查询运行历史，按开始时间倒序。返回 (items, total)。"""
        base = select(StrategyRun)
        if strategy_id:
            base = base.where(StrategyRun.strategy_id == strategy_id)

        # total count
        from sqlalchemy import func
        count_stmt = select(func.count()).select_from(base.subquery())
        total = session.scalar(count_stmt) or 0

        # paged items
        stmt = base.order_by(StrategyRun.started_at.desc()).offset(offset).limit(limit)
        rows = session.scalars(stmt).all()

        items = [
            {
                "id": str(r.id),
                "strategy_id": r.strategy_id,
                "symbol": r.symbol,
                "mode": r.mode or "paper",
                "timeframe": r.timeframe or "",
                "initial_capital": r.initial_capital,
                "status": r.status,
                "started_at": r.started_at.isoformat() if r.started_at else "",
                "ended_at": r.ended_at.isoformat() if r.ended_at else "",
                "final_equity": r.final_equity,
                "realized_pnl": r.realized_pnl,
                "total_return": r.total_return,
                "config": r.config or {},
            }
            for r in rows
        ]
        return items, total

    @staticmethod
    def delete_all_runs(session: Session) -> int:
        """删除所有运行会话（CASCADE 自动删除关联的 orders/closed_trades/open_positions）。
        返回删除的行数。"""
        stmt = delete(StrategyRun)
        result = session.execute(stmt)
        session.flush()
        count = result.rowcount
        logger.info(f"All strategy_runs deleted: {count} rows")
        return count

    @staticmethod
    def delete_runs_before(session: Session, cutoff_date: datetime) -> int:
        """删除指定日期之前的运行会话。返回删除的行数。"""
        stmt = delete(StrategyRun).where(StrategyRun.started_at < cutoff_date)
        result = session.execute(stmt)
        session.flush()
        count = result.rowcount
        logger.info(f"Strategy_runs before {cutoff_date} deleted: {count} rows")
        return count
