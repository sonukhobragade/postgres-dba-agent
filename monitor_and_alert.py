import os
import psycopg2
import time
from slack_notifier import SlackNotifier
from dotenv import load_dotenv
import logging
import sys

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

load_dotenv()

class DatabaseMonitor:
    def __init__(self, db_config):
        self.db_config = db_config
        self.connection = None
        self.notifier = SlackNotifier()
        self.connect_to_db()
        
    def connect_to_db(self):
        """Establish database connection with retry mechanism"""
        max_retries = 5
        retry_delay = 10  # seconds
        
        for attempt in range(max_retries):
            try:
                self.connection = psycopg2.connect(**self.db_config)
                logger.info(f"Successfully connected to PostgreSQL database {self.db_config['database']}")
                return
            except psycopg2.Error as e:
                if attempt < max_retries - 1:
                    logger.warning(f"Connection attempt {attempt + 1} failed for {self.db_config['database']}. Retrying in {retry_delay} seconds...")
                    time.sleep(retry_delay)
                else:
                    logger.error(f"Failed to connect to database {self.db_config['database']} after {max_retries} attempts")
                    self.notifier.send_alert(
                        "Database Connection Error",
                        f"Failed to connect to {self.db_config['database']} database",
                        f"Error: {str(e)}",
                        "critical"
                    )
                    raise

    def check_slow_queries(self):
        """Monitor for slow queries using pg_stat_statements"""
        try:
            # Enable pg_stat_statements if not enabled
            with self.connection.cursor() as cur:
                cur.execute("""
                    SELECT EXISTS (
                        SELECT 1 
                        FROM pg_extension 
                        WHERE extname = 'pg_stat_statements'
                    );
                """)
                if not cur.fetchone()[0]:
                    logger.warning(f"pg_stat_statements extension not found in {self.db_config['database']}")
                    self.notifier.send_alert(
                        "Monitoring Setup Required",
                        f"pg_stat_statements extension is not enabled in {self.db_config['database']}",
                        "Run: CREATE EXTENSION pg_stat_statements;",
                        "warning"
                    )
                    return

            query = """
            SELECT query, 
                   total_exec_time/calls as avg_time,
                   calls,
                   rows,
                   shared_blks_hit::float / nullif(shared_blks_hit + shared_blks_read, 0) * 100 as cache_hit_ratio
            FROM pg_stat_statements
            WHERE total_exec_time/calls > %s
              AND calls > 5  -- Ignore rarely called queries
              AND query NOT LIKE '%%pg_stat%%'  -- Ignore monitoring queries
            ORDER BY total_exec_time/calls DESC
            LIMIT 5;
            """
            
            with self.connection.cursor() as cur:
                cur.execute(query, (float(os.getenv('SLOW_QUERY_THRESHOLD_MS', 1000)),))
                slow_queries = cur.fetchall()
                
                if slow_queries:
                    for query, avg_time, calls, rows, cache_hit in slow_queries:
                        # Tuning advice is the point of the tool, so ask for it
                        # here rather than only from the standalone agent. The
                        # monitor previously alerted with the raw query and the
                        # README's central claim went unmet by the entry point.
                        advice = self._tuning_advice(query)
                        self.notifier.send_query_alert({
                            "database": self.db_config['database'],
                            "query": query[:500] + '...' if len(query) > 500 else query,  # Truncate long queries
                            "duration": round(avg_time, 2),
                            "rows": rows,
                            "cache_hit_ratio": round(cache_hit, 2) if cache_hit else 0,
                            "advice": advice,
                        })
                        logger.info(f"Slow query alert sent for {self.db_config['database']}: {avg_time}ms")

        except psycopg2.Error as e:
            logger.error(f"Error checking slow queries in {self.db_config['database']}: {str(e)}")
            self.handle_db_error(e)

    def _tuning_advice(self, query: str) -> str:
        """Ask the LLM how to improve a slow query.

        Optional: with no API key configured the monitor still alerts, just
        without advice. A missing key must not stop the alert from going out,
        and neither must a failure from the model.
        """
        if not os.getenv('LLM_API_KEY'):
            return ''
        try:
            from dba_ai_agent import LLMQueryOptimizer

            optimizer = LLMQueryOptimizer(api_key=os.getenv('LLM_API_KEY'))
            return optimizer.optimize_query(query, db_type='postgresql', table_metadata=None) or ''
        except Exception as e:  # advice is a bonus; alerting is the job
            logger.warning(f"Could not generate tuning advice: {e}")
            return ''

    def check_connections(self):
        """Monitor database connections"""
        try:
            query = """
            WITH stats AS (
                SELECT 
                    count(*) as active_connections,
                    count(*) FILTER (WHERE state = 'active') as running_queries,
                    count(*) FILTER (WHERE state = 'idle') as idle_connections,
                    current_setting('max_connections')::int as max_connections
                FROM pg_stat_activity
                WHERE datname = current_database()
            )
            SELECT 
                active_connections, 
                running_queries,
                idle_connections,
                max_connections,
                (active_connections::float / max_connections * 100)::numeric(5,2) as usage_percent
            FROM stats;
            """
            
            with self.connection.cursor() as cur:
                cur.execute(query)
                stats = cur.fetchone()
                if stats:
                    active, running, idle, max_conn, usage = stats
                    
                    if usage > float(os.getenv('MAX_CONNECTIONS_THRESHOLD', 80)):
                        self.notifier.send_connection_alert({
                            "database": self.db_config['database'],
                            "current": active,
                            "running": running,
                            "idle": idle,
                            "max": max_conn,
                            "percentage": usage
                        })
                        logger.warning(f"High connection usage alert sent for {self.db_config['database']}: {usage}%")

        except psycopg2.Error as e:
            logger.error(f"Error checking connections in {self.db_config['database']}: {str(e)}")
            self.handle_db_error(e)

    def check_table_bloat(self):
        """Monitor tables for bloat and vacuum requirements"""
        try:
            query = """
            WITH table_stats AS (
                SELECT 
                    schemaname || '.' || relname as table_name,
                    n_dead_tup,
                    n_live_tup,
                    last_vacuum,
                    last_autovacuum,
                    pg_total_relation_size(relid) as total_size,
                    pg_size_pretty(pg_total_relation_size(relid)) as total_size_pretty
                FROM pg_stat_user_tables
                WHERE n_dead_tup > %s
                  AND schemaname NOT IN ('pg_catalog', 'information_schema')
            )
            SELECT *
            FROM table_stats
            ORDER BY n_dead_tup DESC;
            """
            
            with self.connection.cursor() as cur:
                cur.execute(query, (int(os.getenv('DEAD_TUPLES_THRESHOLD', 10000)),))
                bloated_tables = cur.fetchall()
                
                for table, dead_tup, live_tup, last_vacuum, last_autovacuum, total_size, size_pretty in bloated_tables:
                    dead_ratio = (dead_tup / (dead_tup + live_tup) * 100) if (dead_tup + live_tup) > 0 else 0
                    if dead_ratio > 20:  # Alert if more than 20% dead tuples
                        self.notifier.send_vacuum_alert({
                            "database": self.db_config['database'],
                            "table": table,
                            "dead_tuples": dead_tup,
                            "live_tuples": live_tup,
                            "dead_ratio": round(dead_ratio, 2),
                            "total_size": size_pretty,
                            "last_vacuum": last_vacuum.strftime("%Y-%m-%d %H:%M:%S") if last_vacuum else "Never",
                            "last_autovacuum": last_autovacuum.strftime("%Y-%m-%d %H:%M:%S") if last_autovacuum else "Never"
                        })
                        logger.warning(f"Table bloat alert sent for {self.db_config['database']}.{table}: {dead_ratio}% dead tuples")

        except psycopg2.Error as e:
            logger.error(f"Error checking table bloat in {self.db_config['database']}: {str(e)}")
            self.handle_db_error(e)

    def handle_db_error(self, error):
        """Handle database errors and connection recovery"""
        try:
            if self.connection.closed:
                logger.info(f"Attempting to reconnect to {self.db_config['database']}...")
                self.connect_to_db()
            else:
                self.connection.rollback()
        except Exception as e:
            logger.error(f"Error in error handler for {self.db_config['database']}: {str(e)}")

    def check_metrics(self):
        """Run all monitoring checks"""
        try:
            logger.info(f"Running checks for {self.db_config['database']}...")
            self.check_connections()
            self.check_slow_queries()
            self.check_table_bloat()
        except Exception as e:
            logger.error(f"Error in monitoring checks for {self.db_config['database']}: {str(e)}")
            self.handle_db_error(e)

    def close(self):
        """Close database connection"""
        if self.connection:
            self.connection.close()
            logger.info(f"Connection closed for {self.db_config['database']}")

def monitor_databases():
    """Monitor all configured databases"""
    # Configuration for monitoring database
    monitoring_db = {
        'host': os.getenv('POSTGRES_HOST', 'localhost'),
        'port': int(os.getenv('POSTGRES_PORT', 5433)),
        'database': 'dba_monitoring',
        'user': os.getenv('POSTGRES_USER'),
        'password': os.getenv('POSTGRES_PASSWORD')
    }

    # Configuration for the database being observed. These names match
    # .env.example; the previous GCP_POSTGRES_* names appeared nowhere in the
    # documented setup, so a fresh clone configured from .env.example passed no
    # observed-database settings at all.
    observed_db = {
        'host': os.getenv('DB_HOST'),
        'port': int(os.getenv('DB_PORT', 5432)),
        'database': os.getenv('DB_NAME'),
        'user': os.getenv('DB_USER'),
        'password': os.getenv('DB_PASSWORD')
    }

    monitors = []
    notifier = SlackNotifier()

    try:
        # Initialize monitors for each database
        for db_config in [monitoring_db, observed_db]:
            try:
                monitor = DatabaseMonitor(db_config)
                monitors.append(monitor)
            except Exception as e:
                logger.error(f"Failed to initialize monitor for {db_config['database']}: {str(e)}")

        if not monitors:
            raise Exception("No database monitors could be initialized")

        # Send startup notification
        notifier.send_alert(
            "Database Monitoring Started",
            "PostgreSQL monitoring service is now active",
            "Monitoring databases:\n" +
            "\n".join([f"• {m.db_config['database']} (port {m.db_config['port']})" for m in monitors]) +
            "\n\nMonitoring metrics:\n" +
            "• Connection usage\n" +
            "• Slow queries\n" +
            "• Table bloat and vacuum requirements",
            "info"
        )
        logger.info("Monitoring service started")

        # Main monitoring loop
        while True:
            for monitor in monitors:
                try:
                    monitor.check_metrics()
                except Exception as e:
                    logger.error(f"Error monitoring {monitor.db_config['database']}: {str(e)}")

            # Wait for next check interval
            interval = int(os.getenv('MONITOR_INTERVAL_SECONDS', 300))
            logger.info(f"Waiting {interval} seconds until next check...")
            time.sleep(interval)

    except KeyboardInterrupt:
        logger.info("Monitoring stopped by user")
    except Exception as e:
        logger.error(f"Fatal error in monitoring service: {str(e)}")
        notifier.send_alert(
            "Monitoring Service Error",
            "Database monitoring service encountered an error",
            str(e),
            "critical"
        )
    finally:
        for monitor in monitors:
            try:
                monitor.close()
            except Exception:  # closing a broken connection may raise anything
                pass

if __name__ == "__main__":
    try:
        monitor_databases()
    except Exception as e:
        logger.critical(f"Failed to start monitoring service: {str(e)}")
        sys.exit(1)
