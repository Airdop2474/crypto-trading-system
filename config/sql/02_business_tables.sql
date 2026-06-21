-- ==========================================================================
-- 业务表初始化（Docker entrypoint / 手动执行均可）
-- 与 src/models/ ORM 定义保持同步
-- ==========================================================================

-- 策略运行会话
CREATE TABLE IF NOT EXISTS strategy_runs (
    id              UUID PRIMARY KEY,
    strategy_id     TEXT NOT NULL,
    symbol          TEXT NOT NULL,
    timeframe       TEXT,
    mode            TEXT,                              -- backtest / paper / exchange
    initial_capital DOUBLE PRECISION,
    status          TEXT NOT NULL DEFAULT 'running',   -- running / completed / failed
    started_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    ended_at        TIMESTAMPTZ,
    final_equity    DOUBLE PRECISION,
    realized_pnl    DOUBLE PRECISION,
    total_return    DOUBLE PRECISION,
    config          JSONB
);
CREATE INDEX IF NOT EXISTS idx_strategy_runs_strategy_id ON strategy_runs(strategy_id);

-- 经纪商订单
CREATE TABLE IF NOT EXISTS orders (
    id              BIGSERIAL PRIMARY KEY,
    run_id          UUID NOT NULL REFERENCES strategy_runs(id) ON DELETE CASCADE,
    order_id        TEXT,                              -- 经纪商订单号
    symbol          TEXT NOT NULL,
    side            TEXT NOT NULL,                     -- buy / sell
    order_type      TEXT DEFAULT 'market',             -- market / limit
    amount          DOUBLE PRECISION,
    reference_price DOUBLE PRECISION,
    actual_price    DOUBLE PRECISION,
    commission      DOUBLE PRECISION DEFAULT 0,
    slippage        DOUBLE PRECISION DEFAULT 0,
    status          TEXT NOT NULL DEFAULT 'filled',    -- filled / pending / rejected
    balance_after   DOUBLE PRECISION,
    position_after  DOUBLE PRECISION,
    timestamp       TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_orders_run_timestamp ON orders(run_id, timestamp);
CREATE INDEX IF NOT EXISTS ix_orders_symbol_timestamp ON orders(symbol, timestamp);

-- 已平仓交易
CREATE TABLE IF NOT EXISTS closed_trades (
    id              BIGSERIAL PRIMARY KEY,
    run_id          UUID NOT NULL REFERENCES strategy_runs(id) ON DELETE CASCADE,
    strategy_id     TEXT NOT NULL,
    symbol          TEXT NOT NULL,
    tag             TEXT,                              -- 网格层级等标签
    open_time       TIMESTAMPTZ,
    close_time      TIMESTAMPTZ NOT NULL DEFAULT now(),
    open_price      DOUBLE PRECISION,
    close_price     DOUBLE PRECISION,
    quantity        DOUBLE PRECISION,
    profit          DOUBLE PRECISION NOT NULL,
    commission      DOUBLE PRECISION DEFAULT 0
);
CREATE INDEX IF NOT EXISTS ix_closed_trades_run ON closed_trades(run_id);
CREATE INDEX IF NOT EXISTS ix_closed_trades_strategy_close ON closed_trades(strategy_id, close_time);
CREATE INDEX IF NOT EXISTS idx_closed_trades_strategy_id ON closed_trades(strategy_id);

-- 当前持仓
CREATE TABLE IF NOT EXISTS open_positions (
    id              BIGSERIAL PRIMARY KEY,
    run_id          UUID NOT NULL REFERENCES strategy_runs(id) ON DELETE CASCADE,
    strategy_id     TEXT NOT NULL,
    symbol          TEXT NOT NULL,
    tag             TEXT,
    amount          DOUBLE PRECISION NOT NULL,
    cost_price      DOUBLE PRECISION NOT NULL,
    opened_at       TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_open_positions_run ON open_positions(run_id);
CREATE INDEX IF NOT EXISTS ix_open_positions_strategy ON open_positions(strategy_id);
CREATE INDEX IF NOT EXISTS idx_open_positions_strategy_id ON open_positions(strategy_id);

-- 风控事件日志
CREATE TABLE IF NOT EXISTS risk_events (
    id              BIGSERIAL PRIMARY KEY,
    run_id          UUID REFERENCES strategy_runs(id) ON DELETE SET NULL,
    event_type      TEXT NOT NULL,                     -- PAUSE / RESUME / EMERGENCY_STOP
    reason          TEXT,
    state           TEXT,                              -- ACTIVE / PAUSED / STOPPED
    timestamp       TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_risk_events_timestamp ON risk_events(timestamp);
CREATE INDEX IF NOT EXISTS ix_risk_events_run ON risk_events(run_id);

-- AI 审计日志
CREATE TABLE IF NOT EXISTS audit_log (
    id              TEXT PRIMARY KEY,
    timestamp       TIMESTAMPTZ NOT NULL DEFAULT now(),
    phase           TEXT,
    task            TEXT NOT NULL,                     -- backtest / trade_attribution 等
    input_summary   JSONB,
    output_summary  JSONB,
    model           TEXT,
    tokens_used     INTEGER DEFAULT 0,
    human_approved  BOOLEAN NOT NULL DEFAULT FALSE,
    action_taken    TEXT
);
CREATE INDEX IF NOT EXISTS ix_audit_log_task_timestamp ON audit_log(task, timestamp);
