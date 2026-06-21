-- ==========================================================================
-- 策略进化记录表
-- 与 src/models/strategy_evolution.py ORM 定义保持同步
-- ==========================================================================

CREATE TABLE IF NOT EXISTS strategy_evolutions (
    id                    BIGSERIAL PRIMARY KEY,
    timestamp             TIMESTAMPTZ NOT NULL DEFAULT now(),
    strategy_id           TEXT NOT NULL,
    strategy_name         TEXT NOT NULL,
    old_params            JSONB NOT NULL,
    new_params            JSONB,
    old_metrics           JSONB NOT NULL,
    new_metrics           JSONB,
    guardrail_passed      BOOLEAN NOT NULL,
    guardrail_reasons     JSONB,
    llm_provider          TEXT,
    llm_summary           TEXT,
    llm_confidence        DOUBLE PRECISION,
    applied               BOOLEAN NOT NULL DEFAULT FALSE,
    walk_forward_windows  INTEGER NOT NULL DEFAULT 3,
    audit_log_id          TEXT
);

CREATE INDEX IF NOT EXISTS ix_evo_strategy_timestamp
    ON strategy_evolutions(strategy_id, timestamp DESC);
