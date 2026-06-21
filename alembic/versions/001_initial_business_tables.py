"""001_initial_business_tables

Revision ID: 001
Revises:
Create Date: 2026-06-22

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # strategy_runs
    op.create_table(
        "strategy_runs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("strategy_id", sa.String(128), nullable=False, index=True),
        sa.Column("symbol", sa.String(32), nullable=False),
        sa.Column("timeframe", sa.String(16), nullable=True),
        sa.Column("mode", sa.String(16), nullable=True),
        sa.Column("initial_capital", sa.Double, nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="running"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("final_equity", sa.Double, nullable=True),
        sa.Column("realized_pnl", sa.Double, nullable=True),
        sa.Column("total_return", sa.Double, nullable=True),
        sa.Column("config", JSONB, nullable=True),
    )

    # orders
    op.create_table(
        "orders",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("run_id", UUID(as_uuid=True), sa.ForeignKey("strategy_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("order_id", sa.String(64), nullable=True),
        sa.Column("symbol", sa.String(32), nullable=False),
        sa.Column("side", sa.String(8), nullable=False),
        sa.Column("order_type", sa.String(16), nullable=True, server_default="market"),
        sa.Column("amount", sa.Double, nullable=True),
        sa.Column("reference_price", sa.Double, nullable=True),
        sa.Column("actual_price", sa.Double, nullable=True),
        sa.Column("commission", sa.Double, nullable=True, server_default="0"),
        sa.Column("slippage", sa.Double, nullable=True, server_default="0"),
        sa.Column("status", sa.String(16), nullable=False, server_default="filled"),
        sa.Column("balance_after", sa.Double, nullable=True),
        sa.Column("position_after", sa.Double, nullable=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_orders_run_timestamp", "orders", ["run_id", "timestamp"])
    op.create_index("ix_orders_symbol_timestamp", "orders", ["symbol", "timestamp"])

    # closed_trades
    op.create_table(
        "closed_trades",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("run_id", UUID(as_uuid=True), sa.ForeignKey("strategy_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("strategy_id", sa.String(128), nullable=False, index=True),
        sa.Column("symbol", sa.String(32), nullable=False),
        sa.Column("tag", sa.String(128), nullable=True),
        sa.Column("open_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("close_time", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("open_price", sa.Double, nullable=True),
        sa.Column("close_price", sa.Double, nullable=True),
        sa.Column("quantity", sa.Double, nullable=True),
        sa.Column("profit", sa.Double, nullable=False),
        sa.Column("commission", sa.Double, nullable=True, server_default="0"),
    )
    op.create_index("ix_closed_trades_run", "closed_trades", ["run_id"])
    op.create_index("ix_closed_trades_strategy_close", "closed_trades", ["strategy_id", "close_time"])

    # open_positions
    op.create_table(
        "open_positions",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("run_id", UUID(as_uuid=True), sa.ForeignKey("strategy_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("strategy_id", sa.String(128), nullable=False, index=True),
        sa.Column("symbol", sa.String(32), nullable=False),
        sa.Column("tag", sa.String(128), nullable=True),
        sa.Column("amount", sa.Double, nullable=False),
        sa.Column("cost_price", sa.Double, nullable=False),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=True, server_default=sa.func.now()),
    )
    op.create_index("ix_open_positions_run", "open_positions", ["run_id"])
    op.create_index("ix_open_positions_strategy", "open_positions", ["strategy_id"])

    # risk_events
    op.create_table(
        "risk_events",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("run_id", UUID(as_uuid=True), sa.ForeignKey("strategy_runs.id", ondelete="SET NULL"), nullable=True),
        sa.Column("event_type", sa.String(32), nullable=False),
        sa.Column("reason", sa.Text, nullable=True),
        sa.Column("state", sa.String(16), nullable=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_risk_events_timestamp", "risk_events", ["timestamp"])
    op.create_index("ix_risk_events_run", "risk_events", ["run_id"])

    # audit_log
    op.create_table(
        "audit_log",
        sa.Column("id", sa.String(128), primary_key=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("phase", sa.String(32), nullable=True),
        sa.Column("task", sa.String(64), nullable=False),
        sa.Column("input_summary", JSONB, nullable=True),
        sa.Column("output_summary", JSONB, nullable=True),
        sa.Column("model", sa.String(128), nullable=True),
        sa.Column("tokens_used", sa.Integer, nullable=True, server_default="0"),
        sa.Column("human_approved", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("action_taken", sa.Text, nullable=True),
    )
    op.create_index("ix_audit_log_task_timestamp", "audit_log", ["task", "timestamp"])


def downgrade() -> None:
    op.drop_table("audit_log")
    op.drop_table("risk_events")
    op.drop_table("open_positions")
    op.drop_table("closed_trades")
    op.drop_table("orders")
    op.drop_table("strategy_runs")
