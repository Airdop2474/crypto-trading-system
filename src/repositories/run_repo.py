"""
运行会话 CRUD（strategy_runs 表）
"""

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
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
