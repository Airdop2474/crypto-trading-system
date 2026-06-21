"""
交易 / 订单 / 持仓数据访问（orders + closed_trades + open_positions 表）
"""

import uuid
from typing import List, Optional, Tuple

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.models.order import Order
from src.models.trade import ClosedTrade
from src.models.position import OpenPosition
from src.utils.logger import logger


class TradeRepository:
    """订单 / 交易 / 持仓数据访问"""

    # ------------------------------------------------------------------
    # 写入
    # ------------------------------------------------------------------
    @staticmethod
    def save_orders(
        session: Session,
        run_id: uuid.UUID,
        orders: list[dict],
    ) -> int:
        """批量写入经纪商订单，返回写入条数。"""
        if not orders:
            return 0
        rows = []
        for o in orders:
            rows.append(Order(
                run_id=run_id,
                order_id=o.get("order_id"),
                symbol=o.get("symbol", ""),
                side=o.get("side", "buy"),
                order_type=o.get("order_type", "market"),
                amount=o.get("amount"),
                reference_price=o.get("reference_price") or o.get("price"),
                actual_price=o.get("actual_price") or o.get("price"),
                commission=o.get("commission", 0.0),
                slippage=o.get("slippage", 0.0),
                status=o.get("status", "filled"),
                balance_after=o.get("balance_after"),
                position_after=o.get("position_after"),
                timestamp=o.get("timestamp"),
            ))
        session.add_all(rows)
        session.flush()
        logger.debug(f"Saved {len(rows)} orders for run {run_id}")
        return len(rows)

    @staticmethod
    def save_closed_trades(
        session: Session,
        run_id: uuid.UUID,
        strategy_id: str,
        trades: list[dict],
    ) -> int:
        """批量写入已平仓交易，返回写入条数。"""
        if not trades:
            return 0
        rows = []
        for t in trades:
            rows.append(ClosedTrade(
                run_id=run_id,
                strategy_id=strategy_id,
                symbol=t.get("symbol", "BTC/USDT"),
                tag=t.get("tag"),
                open_time=t.get("open_time"),
                close_time=t.get("close_time") or t.get("time"),
                open_price=t.get("open_price"),
                close_price=t.get("close_price"),
                quantity=t.get("quantity"),
                profit=t.get("profit", 0.0),
                commission=t.get("commission", 0.0),
            ))
        session.add_all(rows)
        session.flush()
        logger.debug(f"Saved {len(rows)} closed_trades for run {run_id}")
        return len(rows)

    @staticmethod
    def save_open_positions(
        session: Session,
        run_id: uuid.UUID,
        strategy_id: str,
        positions: list[dict],
    ) -> int:
        """批量写入当前持仓，返回写入条数。"""
        if not positions:
            return 0
        rows = []
        for p in positions:
            rows.append(OpenPosition(
                run_id=run_id,
                strategy_id=strategy_id,
                symbol=p.get("symbol", "BTC/USDT"),
                tag=p.get("tag"),
                amount=p.get("amount", 0.0),
                cost_price=p.get("cost_price", 0.0),
                opened_at=p.get("opened_at"),
            ))
        session.add_all(rows)
        session.flush()
        logger.debug(f"Saved {len(rows)} open_positions for run {run_id}")
        return len(rows)

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------
    @staticmethod
    def get_orders_paginated(
        session: Session,
        run_id: uuid.UUID,
        limit: int = 100,
        offset: int = 0,
    ) -> Tuple[list[dict], int]:
        """分页查询订单，返回 (items, total_count)。"""
        # 总数
        count_stmt = (
            select(func.count(Order.id))
            .where(Order.run_id == run_id)
        )
        total = session.scalar(count_stmt) or 0

        # 分页数据（最新在前）
        stmt = (
            select(Order)
            .where(Order.run_id == run_id)
            .order_by(Order.timestamp.desc())
            .offset(offset)
            .limit(limit)
        )
        rows = session.scalars(stmt).all()
        items = [
            {
                "id": r.order_id or str(r.id),
                "time": r.timestamp.isoformat() if r.timestamp else "",
                "symbol": r.symbol,
                "side": r.side,
                "type": r.order_type or "market",
                "price": r.actual_price or 0.0,
                "amount": r.amount or 0.0,
                "filled": r.amount or 0.0,
                "status": r.status,
                "fee": r.commission or 0.0,
                "strategyName": "",  # 由调用方填充
            }
            for r in rows
        ]
        return items, total

    @staticmethod
    def get_closed_trades(
        session: Session,
        strategy_id: Optional[str] = None,
        run_id: Optional[uuid.UUID] = None,
        limit: int = 200,
    ) -> list[dict]:
        """查询已平仓交易。可按 strategy_id 或 run_id 过滤。"""
        stmt = select(ClosedTrade)
        if strategy_id:
            stmt = stmt.where(ClosedTrade.strategy_id == strategy_id)
        if run_id:
            stmt = stmt.where(ClosedTrade.run_id == run_id)
        stmt = stmt.order_by(ClosedTrade.close_time.desc()).limit(limit)
        rows = session.scalars(stmt).all()
        return [
            {
                "id": f"{r.strategy_id}-{r.tag or ''}-{r.close_time}",
                "strategy_id": r.strategy_id,
                "symbol": r.symbol,
                "tag": r.tag or "",
                "open_time": r.open_time.isoformat() if r.open_time else "",
                "close_time": r.close_time.isoformat() if r.close_time else "",
                "profit": r.profit,
                "commission": r.commission or 0.0,
            }
            for r in rows
        ]

    @staticmethod
    def get_open_positions(
        session: Session,
        strategy_id: Optional[str] = None,
        run_id: Optional[uuid.UUID] = None,
    ) -> list[dict]:
        """查询当前持仓。"""
        stmt = select(OpenPosition)
        if strategy_id:
            stmt = stmt.where(OpenPosition.strategy_id == strategy_id)
        if run_id:
            stmt = stmt.where(OpenPosition.run_id == run_id)
        rows = session.scalars(stmt).all()
        return [
            {
                "strategy_id": r.strategy_id,
                "symbol": r.symbol,
                "tag": r.tag or "",
                "amount": r.amount,
                "cost_price": r.cost_price,
                "opened_at": r.opened_at.isoformat() if r.opened_at else "",
            }
            for r in rows
        ]
