-- 04_agent_memories.sql
-- Agent 长期记忆表（pgvector）
-- 在 Docker 初始化时自动加载

-- 启用 pgvector 扩展（幂等：已存在则跳过）
CREATE EXTENSION IF NOT EXISTS vector;

-- agent_memories：长期记忆主表
CREATE TABLE IF NOT EXISTS agent_memories (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    kind TEXT NOT NULL,
    content JSONB NOT NULL,
    embedding VECTOR(1536),
    tags TEXT[] DEFAULT '{}',
    score DOUBLE PRECISION DEFAULT 1.0,
    source TEXT DEFAULT '',
    feedback_count INTEGER DEFAULT 0,
    feedback_avg_score DOUBLE PRECISION DEFAULT 0.0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 索引
CREATE INDEX IF NOT EXISTS idx_memories_kind ON agent_memories(kind);
CREATE INDEX IF NOT EXISTS idx_memories_tags ON agent_memories USING GIN(tags);
CREATE INDEX IF NOT EXISTS idx_memories_created ON agent_memories(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_memories_score ON agent_memories(score);

-- pgvector 索引（IVFFlat，余弦相似度）
-- lists = sqrt(rows) 的近似值，小数据量用 100
CREATE INDEX IF NOT EXISTS idx_memories_vector
    ON agent_memories
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);
