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

-- 转为 hypertable（按时间分片）；if_not_exists 保证幂等
SELECT create_hypertable('monitor_metrics', 'timestamp', if_not_exists => TRUE);
