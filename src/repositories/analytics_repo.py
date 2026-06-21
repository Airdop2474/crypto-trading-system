"""
分析聚合查询（analytics_repo）

提供盈亏分布、胜率趋势、策略相关性等聚合分析。
"""

import uuid
from typing import Optional

import numpy as np
from sqlalchemy import func, select, case
from sqlalchemy.orm import Session

from src.models.trade import ClosedTrade
from src.utils.logger import logger


class AnalyticsRepository:
    """分析聚合数据访问"""

    @staticmethod
    def get_pnl_distribution(
        session: Session,
        strategy_id: Optional[str] = None,
        run_id: Optional[uuid.UUID] = None,
        bins: int = 10,
    ) -> dict:
        """盈亏分布直方图（与 service.py::pnl_distribution 同结构）。"""
        stmt = select(ClosedTrade.profit)
        if strategy_id:
            stmt = stmt.where(ClosedTrade.strategy_id == strategy_id)
        if run_id:
            stmt = stmt.where(ClosedTrade.run_id == run_id)

        profits = np.array([row[0] for row in session.execute(stmt).all()])
        if len(profits) == 0:
            return {"bins": [], "stats": {
                "total": 0, "wins": 0, "losses": 0, "win_rate": 0.0,
                "avg_profit": 0.0, "avg_loss": 0.0, "profit_factor": 0.0,
                "best": 0.0, "worst": 0.0,
            }}

        # 分箱
        if len(profits) > 1:
            lo, hi = float(profits.min()), float(profits.max())
            if lo == hi:
                lo, hi = lo - 1, hi + 1
            edges = np.linspace(lo, hi, bins + 1)
            counts, _ = np.histogram(profits, bins=edges)
        else:
            edges = np.array([-1, 0, 1])
            counts = np.array([0, 1])

        bin_list = []
        for i in range(len(counts)):
            left, right = float(edges[i]), float(edges[i + 1])
            bin_list.append({
                "range": f"{left:.0f}~{right:.0f}",
                "count": int(counts[i]),
                "label": "盈利" if right > 0 and left >= 0 else "亏损" if right <= 0 else "混合",
            })

        wins_arr = profits[profits > 0]
        losses_arr = profits[profits < 0]
        total_profit = float(wins_arr.sum()) if len(wins_arr) else 0.0
        total_loss = float(abs(losses_arr.sum())) if len(losses_arr) else 0.0

        stats = {
            "total": int(len(profits)),
            "wins": int(len(wins_arr)),
            "losses": int(len(losses_arr)),
            "win_rate": (len(wins_arr) / len(profits) * 100) if len(profits) else 0.0,
            "avg_profit": float(wins_arr.mean()) if len(wins_arr) else 0.0,
            "avg_loss": float(losses_arr.mean()) if len(losses_arr) else 0.0,
            "profit_factor": (
                (total_profit / total_loss) if total_loss > 0
                else float("inf") if total_profit > 0
                else 0.0
            ),
            "best": float(profits.max()) if len(profits) else 0.0,
            "worst": float(profits.min()) if len(profits) else 0.0,
        }
        return {"bins": bin_list, "stats": stats}

    @staticmethod
    def get_daily_pnl_by_strategy(session: Session) -> dict[str, dict[str, float]]:
        """每策略按日聚合 PnL，用于相关性矩阵。

        返回: { strategy_id: { "YYYY-MM-DD": pnl, ... }, ... }
        """
        stmt = (
            select(
                ClosedTrade.strategy_id,
                func.date_trunc("day", ClosedTrade.close_time).label("day"),
                func.sum(ClosedTrade.profit).label("pnl"),
            )
            .group_by(ClosedTrade.strategy_id, func.date_trunc("day", ClosedTrade.close_time))
            .order_by(ClosedTrade.strategy_id, func.date_trunc("day", ClosedTrade.close_time))
        )
        result = {}
        for row in session.execute(stmt).all():
            sid = row.strategy_id
            day_str = row.day.strftime("%Y-%m-%d") if row.day else ""
            if not day_str:
                continue
            if sid not in result:
                result[sid] = {}
            result[sid][day_str] = float(row.pnl or 0.0)
        return result

    @staticmethod
    def get_win_rate_trend(
        session: Session,
        strategy_id: Optional[str] = None,
        window: int = 20,
        limit: int = 10000,
    ) -> list[dict]:
        """滚动胜率趋势（每笔平仓后基于最近 N 笔算胜率）。"""
        stmt = select(ClosedTrade).order_by(ClosedTrade.close_time.asc())
        if strategy_id:
            stmt = stmt.where(ClosedTrade.strategy_id == strategy_id)
        stmt = stmt.limit(limit)

        trades = session.scalars(stmt).all()
        if not trades:
            return []

        out = []
        for i, t in enumerate(trades, 1):
            start = max(0, i - window)
            recent = trades[start:i]
            wins = sum(1 for r in recent if r.profit > 0)
            wr = (wins / len(recent) * 100) if recent else 0.0
            out.append({
                "index": i,
                "close_time": t.close_time.isoformat() if t.close_time else "",
                "win_rate": wr,
                "strategy_id": t.strategy_id,
            })
        return out
