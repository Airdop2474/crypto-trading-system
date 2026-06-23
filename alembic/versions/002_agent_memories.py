"""002_agent_memories

Agent 长期记忆表（pgvector）

启用 pgvector 扩展，创建 agent_memories 表和向量索引。
支持语义搜索和标签过滤。

Revision ID: 002
Revises: 001
Create Date: 2026-06-23
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # pgvector 扩展（幂等）
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # agent_memories 表
    op.create_table(
        "agent_memories",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("content", JSONB, nullable=False),
        sa.Column("embedding", sa.Text(), nullable=True),  # pgvector 列，类型在 execute 中设置
        sa.Column("tags", sa.ARRAY(sa.Text()), nullable=True, server_default=sa.text("'{}'")),
        sa.Column("score", sa.Double(), nullable=True, server_default=sa.text("1.0")),
        sa.Column("source", sa.Text(), nullable=True, server_default=sa.text("''")),
        sa.Column("feedback_count", sa.Integer(), nullable=True, server_default=sa.text("0")),
        sa.Column("feedback_avg_score", sa.Double(), nullable=True, server_default=sa.text("0.0")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True, server_default=sa.func.now()),
    )

    # 将 embedding 列转为 vector 类型（pgvector 原生语法）
    op.execute("ALTER TABLE agent_memories ALTER COLUMN embedding TYPE VECTOR(1536) USING embedding::vector(1536)")

    # 索引
    op.create_index("idx_memories_kind", "agent_memories", ["kind"])
    op.create_index("idx_memories_tags", "agent_memories", ["tags"], postgresql_using="gin")
    op.create_index("idx_memories_created", "agent_memories", [sa.text("created_at DESC")])
    op.create_index("idx_memories_score", "agent_memories", ["score"])

    # pgvector IVFFlat 索引
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_memories_vector "
        "ON agent_memories USING ivfflat (embedding vector_cosine_ops) "
        "WITH (lists = 100)"
    )


def downgrade() -> None:
    op.drop_table("agent_memories")
    # 不删除 vector 扩展（可能被其他表使用）
