-- Insert test data for monitoring
INSERT INTO metrics_history (metric_name, metric_value, database_name, instance_name)
SELECT 
    'cpu_usage',
    random() * 100,
    'dba_monitoring',
    'main'
FROM generate_series(1, 100);

INSERT INTO query_performance (query_id, query_text, execution_time, rows_affected, database_name)
SELECT 
    'query_' || id,
    'SELECT * FROM large_table WHERE id = ' || id,
    random() * 10,
    floor(random() * 1000)::integer,
    'dba_monitoring'
FROM generate_series(1, 50) id;

INSERT INTO system_health (cpu_usage, memory_usage, disk_usage, connection_count, instance_name)
SELECT 
    random() * 100,
    random() * 100,
    random() * 100,
    floor(random() * 50)::integer,
    'main'
FROM generate_series(1, 100);

INSERT INTO alerts (alert_type, severity, message, status)
VALUES 
    ('high_cpu', 'warning', 'CPU usage exceeded 80%', 'active'),
    ('slow_query', 'critical', 'Query execution time > 30s', 'active'),
    ('disk_space', 'warning', 'Disk usage above 75%', 'resolved'),
    ('connection_limit', 'critical', 'Too many database connections', 'active');
