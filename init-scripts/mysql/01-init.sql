-- Initialize MySQL tables for DBA analytics

-- Performance Metrics table
CREATE TABLE performance_metrics (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    metric_name VARCHAR(100),
    metric_value DECIMAL(10,2),
    database_name VARCHAR(50),
    instance_name VARCHAR(50),
    INDEX idx_timestamp (timestamp)
);

-- Slow Queries table
CREATE TABLE slow_queries (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    query_id VARCHAR(100),
    query_text TEXT,
    execution_time DECIMAL(10,2),
    rows_examined BIGINT,
    database_name VARCHAR(50),
    INDEX idx_timestamp (timestamp)
);

-- Resource Usage table
CREATE TABLE resource_usage (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    cpu_usage DECIMAL(5,2),
    memory_usage DECIMAL(5,2),
    disk_usage DECIMAL(5,2),
    connections INT,
    instance_name VARCHAR(50),
    INDEX idx_timestamp (timestamp)
);

-- Maintenance Logs table
CREATE TABLE maintenance_logs (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    operation_type VARCHAR(50),
    description TEXT,
    status VARCHAR(20),
    duration_seconds INT,
    affected_objects TEXT,
    INDEX idx_timestamp (timestamp)
);
