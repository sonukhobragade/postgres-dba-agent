-- Initialize PostgreSQL tables for DBA monitoring

-- Metrics History table
CREATE TABLE metrics_history (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    metric_name VARCHAR(100),
    metric_value NUMERIC,
    database_name VARCHAR(50),
    instance_name VARCHAR(50)
);

-- Query Performance table
CREATE TABLE query_performance (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    query_id VARCHAR(100),
    query_text TEXT,
    execution_time NUMERIC,
    rows_affected INTEGER,
    database_name VARCHAR(50)
);

-- System Health table
CREATE TABLE system_health (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    cpu_usage NUMERIC,
    memory_usage NUMERIC,
    disk_usage NUMERIC,
    connection_count INTEGER,
    instance_name VARCHAR(50)
);

-- Alerts table
CREATE TABLE alerts (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    alert_type VARCHAR(50),
    severity VARCHAR(20),
    message TEXT,
    status VARCHAR(20),
    resolved_at TIMESTAMPTZ
);

-- Create indexes for better query performance
CREATE INDEX idx_metrics_history_timestamp ON metrics_history(timestamp);
CREATE INDEX idx_query_performance_timestamp ON query_performance(timestamp);
CREATE INDEX idx_system_health_timestamp ON system_health(timestamp);
CREATE INDEX idx_alerts_timestamp ON alerts(timestamp);
