-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;

-- Create tables for monitoring data
CREATE TABLE IF NOT EXISTS metrics_history (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    database_name VARCHAR(100),
    metric_name VARCHAR(100),
    metric_value NUMERIC,
    tags JSONB
);

CREATE TABLE IF NOT EXISTS query_performance (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    database_name VARCHAR(100),
    query_text TEXT,
    execution_time NUMERIC,
    rows_affected BIGINT,
    shared_blks_hit BIGINT,
    shared_blks_read BIGINT,
    shared_blks_written BIGINT,
    temp_blks_read BIGINT,
    temp_blks_written BIGINT,
    cache_hit_ratio NUMERIC
);

CREATE TABLE IF NOT EXISTS system_health (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    database_name VARCHAR(100),
    total_connections INTEGER,
    active_connections INTEGER,
    idle_connections INTEGER,
    max_connections INTEGER,
    connection_usage_percent NUMERIC,
    database_size BIGINT,
    temp_file_size BIGINT,
    deadlocks BIGINT,
    conflicts BIGINT
);

CREATE TABLE IF NOT EXISTS alerts (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    alert_type VARCHAR(50),
    severity VARCHAR(20),
    database_name VARCHAR(100),
    message TEXT,
    details JSONB,
    acknowledged BOOLEAN DEFAULT FALSE,
    acknowledged_by VARCHAR(100),
    acknowledged_at TIMESTAMPTZ
);

-- Create indexes for better query performance
CREATE INDEX IF NOT EXISTS idx_metrics_history_timestamp ON metrics_history(timestamp);
CREATE INDEX IF NOT EXISTS idx_metrics_history_database ON metrics_history(database_name);
CREATE INDEX IF NOT EXISTS idx_metrics_history_metric ON metrics_history(metric_name);

CREATE INDEX IF NOT EXISTS idx_query_performance_timestamp ON query_performance(timestamp);
CREATE INDEX IF NOT EXISTS idx_query_performance_database ON query_performance(database_name);
CREATE INDEX IF NOT EXISTS idx_query_performance_execution_time ON query_performance(execution_time);

CREATE INDEX IF NOT EXISTS idx_system_health_timestamp ON system_health(timestamp);
CREATE INDEX IF NOT EXISTS idx_system_health_database ON system_health(database_name);

CREATE INDEX IF NOT EXISTS idx_alerts_timestamp ON alerts(timestamp);
CREATE INDEX IF NOT EXISTS idx_alerts_type ON alerts(alert_type);
CREATE INDEX IF NOT EXISTS idx_alerts_database ON alerts(database_name);
CREATE INDEX IF NOT EXISTS idx_alerts_severity ON alerts(severity);

-- Create a view for recent alerts
CREATE OR REPLACE VIEW recent_alerts AS
SELECT *
FROM alerts
WHERE timestamp >= NOW() - INTERVAL '24 hours'
ORDER BY timestamp DESC;
