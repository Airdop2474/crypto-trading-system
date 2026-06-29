-- 监控指标表（Phase 5）
-- 由 docker-entrypoint-initdb.d 在容器首次启动时执行。
-- 对应 MetricsCollector.to_records() 的展平时序，供 Grafana 读取。

CREATE EXTENSION IF NOT EXISTS timescaledb;

CREATE TABLE IF NOT EXISTS monitor_metrics (
    timestamp           TIMESTAMPTZ      NOT NULL,
    total_value         DOUBLE PRECISION NOT NULL,
    total_return        DOUBLE PRECISION NOT NULL,
    realized_pnl        DOUBLE PRECISION NOT NULL,
    total_trades        INTEGER          NOT NULL,
    risk_state          TEXT,
    consecutive_losses  INTEGER
);

-- 转为 hypertable（按时间分片）；显式 chunk_time_interval=1 天，匹配 bar 频率
SELECT create_hypertable('monitor_metrics', 'timestamp',
    if_not_exists => TRUE,
    chunk_time_interval => INTERVAL '1 day'
);

-- 索引：按 risk_state 过滤 + 时间倒序查询（Grafana 常用模式）
CREATE INDEX IF NOT EXISTS idx_metrics_risk_state
    ON monitor_metrics(risk_state, timestamp DESC);

-- 压缩策略：7 天前的 chunk 压缩，减 80% 存储
ALTER TABLE monitor_metrics SET (timescaledb.compress);
SELECT add_compression_policy('monitor_metrics', INTERVAL '7 days');

-- retention 策略：90 天后自动清理，避免无限增长
SELECT add_retention_policy('monitor_metrics', INTERVAL '90 days');
