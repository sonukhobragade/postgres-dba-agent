#!/usr/bin/env python3
"""
DBA AI Agent - Intelligent database administration assistant with LLM-powered query optimization
"""

import logging
import os
import sys
import json
from typing import Dict, List, Tuple
from datetime import datetime
import re
import psycopg2
from psycopg2.extras import RealDictCursor
import decimal
import requests

# FastAPI for backend API
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

# Database connectors
try:
    import psycopg2  # PostgreSQL
    import psycopg2.extras  # For better PG support
    import mysql.connector  # MySQL  # noqa: F401  (presence check for the optional MySQL driver)
    HAS_DB_CONNECTORS = True
except ImportError:
    HAS_DB_CONNECTORS = False
    print("Warning: Database connector libraries not installed. Running in simulation mode.")

# LLM integration for query optimization
try:
    import openai  # For API compatibility with various LLMs
    HAS_LLM_API = True
except ImportError:
    HAS_LLM_API = False
    print("Warning: LLM API libraries not installed. AI-based query optimization disabled.")

# Monitoring integration
try:
    from prometheus_client import Counter, Gauge, Histogram, start_http_server, CollectorRegistry
    HAS_PROMETHEUS = True
except ImportError:
    HAS_PROMETHEUS = False
    print("Warning: Prometheus client not installed. Monitoring will be disabled.")

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("dba_ai_agent.log"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("DBA-AI-Agent")

# Initialize FastAPI app
app = FastAPI(
    title="DBA AI Agent",
    description="API for an intelligent database administration assistant with LLM-powered query optimization",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, restrict this to specific origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Define API endpoints
@app.get("/")
async def root():
    return {"message": "Welcome to DBA AI Agent"}

@app.get("/health")
async def health_check():
    return {"status": "healthy"}

@app.post("/analyze")
async def analyze_db(background_tasks: BackgroundTasks):
    try:
        optimizer = LLMQueryOptimizer()
        # Use the first available connection or a specific one if needed
        conn_name = os.environ.get('DEFAULT_DB_CONNECTION', 'default_postgres')
        background_tasks.add_task(optimizer.generate_insights, conn_name)
        return {"status": "success", "message": f"Database analysis started in the background for connection {conn_name}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Initialize Prometheus metrics if available
if HAS_PROMETHEUS:
    # Create a new registry for our metrics
    REGISTRY = CollectorRegistry()
    
    # Query metrics
    QUERY_EXECUTIONS = Counter('query_executions_total', 'Total number of query executions', ['db_type', 'status'], registry=REGISTRY)
    QUERY_DURATION = Histogram('query_duration_seconds', 'Query execution duration in seconds', ['db_type'], registry=REGISTRY)
    
    # Database metrics
    DB_SIZE = Gauge('database_size_bytes', 'Database size in bytes', ['database'], registry=REGISTRY)
    TABLE_SIZE = Gauge('table_size_bytes', 'Table size in bytes', ['database', 'table'], registry=REGISTRY)
    
    # Optimization metrics
    OPTIMIZATIONS_APPLIED = Counter('optimizations_applied_total', 'Total number of query optimizations applied', ['db_type', 'optimization_type'], registry=REGISTRY)
    
    # Start Prometheus metrics server only if ENABLE_PROMETHEUS_SERVER is set
    if os.environ.get('ENABLE_PROMETHEUS_SERVER', 'false').lower() == 'true':
        start_http_server(8002, registry=REGISTRY)


class SlackNotifier:
    """Handles sending notifications to Slack"""
    
    def __init__(self, token: str = None, channel: str = None):
        """Initialize Slack notifier with token and channel"""
        self.token = token or os.environ.get('SLACK_TOKEN', '')
        self.channel = channel or os.environ.get('SLACK_CHANNEL', '')
        self.slack_url = 'https://slack.com/api/chat.postMessage'
        
    def send_notification(self, message: str, severity: str = 'info'):
        """Send a notification to Slack using Web API"""
        if not self.token or not self.channel:
            logger.warning("Slack token or channel not configured - notification not sent")
            return False
            
        _color = {
            'info': '#2EB67D',     # Green
            'warning': '#ECB22E',  # Yellow
            'error': '#E01E5A'     # Red
        }.get(severity, '#2EB67D')
        
        blocks = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*DBA AI Agent {severity.capitalize()} Notification*\n{message}"
                }
            }
        ]
        
        payload = {
            "channel": self.channel,
            "blocks": blocks
        }
        
        headers = {
            'Authorization': f'Bearer {self.token}',
            'Content-Type': 'application/json; charset=utf-8'
        }
        
        try:
            response = requests.post(self.slack_url, json=payload, headers=headers)
            if not response.ok:
                logger.error(f"Error sending Slack notification. Status: {response.status_code}, Response: {response.text}")
                return False
            return True
        except Exception as e:
            logger.error(f"Error sending Slack notification: {str(e)}")
            return False

    def send_alert(self, alert_type: str, message: str, severity: str = 'info'):
        """Send an alert to Slack using Web API"""
        if not self.token or not self.channel:
            logger.warning("Slack token or channel not configured - alert not sent")
            return False
            
        _color = {
            'info': '#2EB67D',     # Green
            'warning': '#ECB22E',  # Yellow
            'error': '#E01E5A'     # Red
        }.get(severity, '#2EB67D')
        
        blocks = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*DBA AI Agent {alert_type} Alert*\n{message}"
                }
            }
        ]
        
        payload = {
            "channel": self.channel,
            "blocks": blocks
        }
        
        headers = {
            'Authorization': f'Bearer {self.token}',
            'Content-Type': 'application/json; charset=utf-8'
        }
        
        try:
            response = requests.post(self.slack_url, json=payload, headers=headers)
            if not response.ok:
                logger.error(f"Error sending Slack alert. Status: {response.status_code}, Response: {response.text}")
                return False
            return True
        except Exception as e:
            logger.error(f"Error sending Slack alert: {str(e)}")
            return False


class DecimalEncoder(json.JSONEncoder):
    """Custom JSON encoder for Decimal types"""
    def default(self, obj):
        if isinstance(obj, decimal.Decimal):
            return str(obj)
        return super().default(obj)


class DatabaseConnection:
    """Handles database connections and query execution"""
    
    def __init__(self, db_type: str, host: str, port: int, database: str, user: str, password: str):
        self.db_type = db_type
        self.host = host
        self.port = port
        self.database = database
        self.user = user
        self.password = password
        self.conn = None
        
        # Try to connect immediately to validate connection
        try:
            self.connect()
            logger.info(f"Successfully connected to {db_type} database at {host}:{port}/{database}")
        except Exception as e:
            logger.error(f"Failed to connect to {db_type} database: {str(e)}")
    
    def connect(self):
        """Connect to the database"""
        if self.conn is not None:
            try:
                # Test if connection is still alive
                if self.db_type == 'postgresql':
                    self.conn.cursor().execute("SELECT 1")
                    return
            except Exception:
                # Connection is dead, close it
                try:
                    self.conn.close()
                except Exception:
                    pass
                self.conn = None
        
        # Create a new connection
        if self.db_type == 'postgresql':
            self.conn = psycopg2.connect(
                host=self.host,
                port=self.port,
                database=self.database,
                user=self.user,
                password=self.password
            )
            self.conn.autocommit = True
        else:
            raise ValueError(f"Unsupported database type: {self.db_type}")
    
    def execute_query(self, query: str, params: Dict = None) -> Tuple[bool, List[Dict], str]:
        """Execute a query and return the results"""
        try:
            self.connect()  # Ensure connection is active
            
            cursor = None
            if self.db_type == 'postgresql':
                cursor = self.conn.cursor(cursor_factory=RealDictCursor)
            
            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)
            
            # Get results if any
            results = []
            if cursor.description:
                results = [dict(row) for row in cursor.fetchall()]
            
            cursor.close()
            return True, results, ""
        except Exception as e:
            error_msg = f"Error executing query: {str(e)}"
            logger.error(error_msg)
            return False, [], error_msg


class LLMQueryOptimizer:
    """Uses LLM APIs to optimize SQL queries"""
    
    def __init__(self, api_key: str = None, model: str = "gpt-4"):
        self.api_key = api_key or os.environ.get('LLM_API_KEY', '')
        self.model = model
        self.base_url = os.environ.get('LLM_API_BASE_URL', 'https://api.openai.com/v1')
        
        if self.api_key and HAS_LLM_API:
            try:
                # Initialize the OpenAI client with the API key and base URL
                self.client = openai.OpenAI(
                    api_key=self.api_key,
                    base_url=self.base_url
                )
                logger.info(f"Successfully initialized OpenAI client with model: {self.model}")
            except Exception as e:
                self.client = None
                logger.error(f"Failed to initialize OpenAI client: {str(e)}")
        else:
            self.client = None
            logger.warning("LLM client not initialized - API key missing or openai not installed")
            
        # Initialize database connections
        self.connections = {}
        self.init_connections()
        
    def init_connections(self):
        """Initialize database connections"""
        try:
            # Default PostgreSQL connection.
            # DB_PASSWORD has no default on purpose: a fallback password gets
            # committed, then quietly authenticates somewhere real.
            password = os.environ.get('DB_PASSWORD')
            if password is None:
                raise RuntimeError(
                    "DB_PASSWORD is not set. Set it in the environment; "
                    "there is deliberately no default."
                )
            default_postgres = DatabaseConnection(
                db_type='postgresql',
                host=os.environ.get('DB_HOST', 'localhost'),
                port=int(os.environ.get('DB_PORT', 5432)),
                database=os.environ.get('DB_NAME', 'postgres'),
                user=os.environ.get('DB_USER', 'postgres'),
                password=password
            )
            self.connections['default_postgres'] = default_postgres
            
            # Add more connections as needed
            
            logger.info(f"Initialized {len(self.connections)} database connections")
        except Exception as e:
            logger.error(f"Error initializing database connections: {str(e)}")
    
    def optimize_query(self, query: str, db_type: str, table_metadata: Dict = None) -> Tuple[str, List[str]]:
        """
        Optimize a SQL query using LLM analysis
        
        Args:
            query: Original SQL query
            db_type: Database type ('postgresql' or 'mysql')
            table_metadata: Optional metadata about tables referenced in the query
            
        Returns:
            Tuple of (optimized_query, list_of_optimizations_applied)
        """
        if not self.client:
            logger.warning("LLM client not initialized - returning original query")
            return query, ["LLM optimization not available"]
            
        # Construct prompt for the LLM
        system_prompt = f"""You are a database query optimization expert specializing in {db_type}.
Analyze the following SQL query and suggest optimizations to improve its performance.
Your task is to rewrite the query to make it more efficient while maintaining the exact same functionality.
- Analyze the query structure and identify performance issues
- Consider indexing strategies
- Apply {db_type}-specific optimizations
- Return both an optimized query and explanation of changes

Output format:
QUERY: <optimized SQL query>
OPTIMIZATIONS:
- <optimization 1>
- <optimization 2>
...
"""

        # Add metadata if available
        if table_metadata:
            metadata_str = json.dumps(table_metadata, indent=2)
            system_prompt += f"\n\nHere is metadata about the tables involved:\n```json\n{metadata_str}\n```"
            
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Original query:\n```sql\n{query}\n```"}
                ],
                temperature=0.1  # Low temperature for more focused responses
            )
            
            # Parse response
            output = response.choices[0].message.content
            
            # Extract optimized query and optimization list
            query_match = re.search(r'QUERY:\s*(.*?)(?=OPTIMIZATIONS:|$)', output, re.DOTALL)
            optimizations_match = re.search(r'OPTIMIZATIONS:(.*?)$', output, re.DOTALL)
            
            optimized_query = query_match.group(1).strip() if query_match else query
            
            optimizations = []
            if optimizations_match:
                for line in optimizations_match.group(1).strip().split('\n'):
                    if line.strip().startswith('-'):
                        optimizations.append(line.strip()[1:].strip())
            
            if not optimizations:
                optimizations = ["No specific optimizations identified"]
                
            return optimized_query, optimizations
            
        except Exception as e:
            logger.error(f"Error in LLM query optimization: {str(e)}")
            return query, [f"LLM optimization error: {str(e)}"]
    
    def analyze_execution_plan(self, plan: Dict, db_type: str) -> List[str]:
        """
        Analyze a query execution plan to identify performance issues
        
        Args:
            plan: JSON representation of the execution plan
            db_type: Database type ('postgresql' or 'mysql')
            
        Returns:
            List of identified issues and recommendations
        """
        if not self.client:
            return ["LLM analysis not available"]
            
        system_prompt = f"""You are a database performance expert specializing in {db_type}.
Analyze the following execution plan and identify potential performance issues.
Focus on:
1. Sequential scans on large tables
2. Missing indexes
3. High-cost operations
4. Nested loops with many iterations
5. Hash joins with large tables
6. {db_type}-specific performance bottlenecks

Output format:
ISSUES:
- <issue 1>
- <issue 2>

RECOMMENDATIONS:
- <recommendation 1>
- <recommendation 2>
"""
        
        try:
            plan_json = json.dumps(plan, indent=2)
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Execution plan:\n```json\n{plan_json}\n```"}
                ],
                temperature=0.1
            )
            
            # Parse response
            output = response.choices[0].message.content
            
            # Extract issues and recommendations
            results = []
            issues_match = re.search(r'ISSUES:(.*?)(?=RECOMMENDATIONS:|$)', output, re.DOTALL)
            recommendations_match = re.search(r'RECOMMENDATIONS:(.*?)$', output, re.DOTALL)
            
            if issues_match:
                for line in issues_match.group(1).strip().split('\n'):
                    if line.strip().startswith('-'):
                        results.append(f"Issue: {line.strip()[1:].strip()}")
            
            if recommendations_match:
                for line in recommendations_match.group(1).strip().split('\n'):
                    if line.strip().startswith('-'):
                        results.append(f"Recommendation: {line.strip()[1:].strip()}")
                        
            return results
            
        except Exception as e:
            logger.error(f"Error in LLM execution plan analysis: {str(e)}")
            return [f"LLM analysis error: {str(e)}"]
    
    def suggest_index(self, table_info: Dict) -> str:
        """Get index recommendations for a table using LLM"""
        try:
            prompt = f"""
You are an expert PostgreSQL Database Administrator. Your task is to analyze this table information and suggest specific indexes:

Table Statistics:
- Sequential Scans: {table_info.get('seq_scan', 'N/A')}
- Sequential Rows Read: {table_info.get('seq_tup_read', 'N/A')}
- Index Scans: {table_info.get('idx_scan', 'N/A')}
- Row Count: {table_info.get('estimated_row_count', 'N/A')}

Existing Indexes:
{json.dumps(table_info.get('indexes', []), indent=2)}

Most Frequent Queries:
{json.dumps(table_info.get('queries', []), indent=2)}

Please provide:
1. Specific columns to index based on the query patterns
2. Type of index (B-tree, Hash, etc.)
3. Whether it should be a compound index
4. Explanation of why this index would help
5. Expected performance impact

Format the response in a clear, structured way."""

            completion = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are an expert PostgreSQL Database Administrator."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.2
            )
            
            return completion.choices[0].message.content
        except Exception as e:
            logger.error(f"Error in LLM index suggestion: {str(e)}")
            return f"Error getting index recommendations: {str(e)}"

    def analyze_database_performance(self, insights: Dict) -> str:
        """Analyze database performance using LLM"""
        try:
            # Extract the actual insights from the response structure
            if isinstance(insights, dict) and 'insights' in insights:
                insights = insights['insights']
            
            # Initialize Slack notifier
            notifier = SlackNotifier()
            
            # Format the performance analysis
            message = (
                "*Database Performance Analysis*\n\n"
                "*1. Database Overview:*\n"
            )
            
            # Safely access database size
            if 'database_size' in insights and isinstance(insights['database_size'], list) and len(insights['database_size']) > 0:
                message += f"- Total Size: {insights['database_size'][0]['size_pretty']}\n"
                if len(insights['database_size']) > 1:
                    message += "- Individual Databases:\n"
                    for db in insights['database_size']:
                        message += f"  • {db.get('database_name', 'Unknown')}: {db.get('size_pretty', 'Unknown')}\n"
            else:
                message += "- Total Size: Unknown\n"
            
            message += "\n*2. Largest Tables:*\n"
            if 'largest_tables' in insights and isinstance(insights['largest_tables'], list) and len(insights['largest_tables']) > 0:
                for table in insights['largest_tables']:
                    message += f"• {table.get('table_name', 'Unknown')}: {table.get('total_size_pretty', 'Unknown')}\n"
            else:
                message += "No table size information available.\n"
            
            message += "\n*3. Index Recommendations:*\n"
            if 'index_recommendations' in insights and isinstance(insights['index_recommendations'], list) and len(insights['index_recommendations']) > 0:
                for rec in insights['index_recommendations']:
                    message += (
                        f"• Table '{rec.get('table_name', 'Unknown')}':\n"
                        f"  - Sequential Scans: {rec.get('seq_scan', 'N/A')}\n"
                        f"  - Sequential Rows Read: {rec.get('seq_tup_read', 'N/A')}\n"
                        f"  - Index Scans: {rec.get('idx_scan', 'N/A')}\n"
                        f"  - Estimated Row Count: {rec.get('estimated_row_count', 'N/A')}\n\n"
                    )
            else:
                message += "No index recommendations available.\n\n"
                
            # Add performance issues section
            message += "\n*4. Performance Issues:*\n"
            if 'performance_issues' in insights and isinstance(insights['performance_issues'], list) and len(insights['performance_issues']) > 0:
                for issue in insights['performance_issues']:
                    if 'query_text' in issue:
                        query_text = issue.get('query_text', 'Unknown')
                        duration = issue.get('duration_seconds', 'Unknown')
                        message += f"• Query: {query_text}\n  Duration: {duration} seconds\n\n"
            else:
                message += "No performance issues detected.\n\n"
            
            # Add overall health assessment
            message += "\n*5. Overall Health:*\n"
            message += f"Database health is currently: {insights.get('overall_health', 'Unknown')}\n"

            # Send notification to Slack
            try:
                logger.info("Sending database analysis to Slack")
                success = notifier.send_notification(message, severity='info')
                if not success:
                    logger.error("Failed to send Slack notification")
                    return "Database analysis completed but failed to send to Slack"
                logger.info("Successfully sent database analysis to Slack")
            except Exception as e:
                logger.error(f"Error sending Slack notification: {str(e)}")
                return f"Database analysis completed but failed to send to Slack: {str(e)}"
            
            return "Database analysis completed and sent to Slack"
        except Exception as e:
            logger.error(f"Error in analyze_database_performance: {str(e)}")
            raise Exception(f"Failed to analyze database performance: {str(e)}")
            
    def generate_fix_suggestions(self, insights: Dict) -> str:
        """
        Generate AI-powered suggestions for fixing database issues based on insights
        
        Args:
            insights: Database insights dictionary
            
        Returns:
            String with AI-generated suggestions for fixing database issues
        """
        if not self.client:
            logger.warning("LLM client not initialized, using fallback suggestions")
            return self._generate_fallback_suggestions(insights)
            
        try:
            # Format the insights for the LLM prompt
            insights_json = json.dumps(insights, cls=DecimalEncoder)
            
            # Create a prompt for the LLM
            prompt = f"""
            You are a database performance expert. Analyze the following database insights and provide specific recommendations to improve performance.
            
            Database Insights:
            {insights_json}
            
            Please provide:
            1. Specific index recommendations for tables with high sequential scans
            2. Maintenance suggestions for large tables
            3. Query optimization recommendations for slow queries
            4. Any other performance improvements
            
            Format your response in Markdown with clear sections and code examples where appropriate.
            Include specific SQL commands that can be executed to implement your recommendations.
            """
            
            # Call the LLM API
            completion = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a database performance expert providing actionable recommendations."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                max_tokens=2000
            )
            
            # Extract the suggestions from the LLM response
            suggestions = completion.choices[0].message.content
            
            # Add a section specifically for the slow queries if they exist
            insights_data = insights.get('insights', {})
            if 'slow_queries' in insights_data and isinstance(insights_data['slow_queries'], list) and insights_data['slow_queries']:
                suggestions += "\n\n## Detailed Slow Query Analysis\n\n"
                
                for i, query in enumerate(insights_data['slow_queries'], 1):
                    query_text = query.get('query', '')
                    mean_time = query.get('mean_time', 0)
                    calls = query.get('calls', 0)
                    
                    suggestions += f"### Slow Query {i}\n"
                    suggestions += f"**Query Text:**\n```sql\n{query_text}\n```\n\n"
                    suggestions += f"**Mean Time:** {mean_time} ms\n"
                    suggestions += f"**Calls:** {calls}\n\n"
                    
                    # Add specific recommendations for replication queries
                    if 'REPLICATION' in query_text.upper():
                        suggestions += "**Recommendation:** This is a replication query. Consider reviewing your replication configuration and ensuring that your WAL (Write-Ahead Log) settings are optimized.\n\n"
            
            return suggestions
            
        except Exception as e:
            logger.error(f"Error generating fix suggestions: {str(e)}")
            return self._generate_fallback_suggestions(insights)
    
    def _generate_fallback_suggestions(self, insights: Dict) -> str:
        """
        Generate fallback suggestions when the LLM API is not available
        
        Args:
            insights: Database insights dictionary
            
        Returns:
            String with fallback suggestions for fixing database issues
        """
        suggestions = []
        
        try:
            # Extract insights data
            insights_data = insights.get('insights', {})
            
            # Add suggestions for tables with high sequential scans
            if 'index_recommendations' in insights_data and isinstance(insights_data['index_recommendations'], list):
                suggestions.append("## Index Recommendations\n")
                
                for rec in insights_data['index_recommendations']:
                    table_name = rec.get('table_name')
                    seq_scan = rec.get('seq_scan', 0)
                    idx_scan = rec.get('idx_scan', 0)
                    
                    if table_name and seq_scan > 100 and (idx_scan == 0 or (seq_scan / max(idx_scan, 1)) > 10):
                        suggestions.append(f"### Table: `{table_name}`\n")
                        suggestions.append(f"- **Issue**: High sequential scan count ({seq_scan}) with low index usage ({idx_scan})\n")
                        suggestions.append("- **Recommendation**: Consider adding indexes on frequently queried columns\n")
                        suggestions.append(f"```sql\n-- Example index creation (modify column names as needed)\nCREATE INDEX idx_{table_name}_column ON {table_name}(column_name);\n```\n")
            
            # Add suggestions for large tables
            if 'largest_tables' in insights_data and isinstance(insights_data['largest_tables'], list):
                suggestions.append("## Large Table Maintenance\n")
                
                for table in insights_data['largest_tables']:
                    table_name = table.get('table_name')
                    total_size = table.get('total_size_pretty')
                    
                    if table_name and total_size:
                        suggestions.append(f"### Table: `{table_name}` (Size: {total_size})\n")
                        suggestions.append("- **Issue**: Large table size may lead to performance degradation\n")
                        suggestions.append("- **Recommendation**: Regular maintenance and optimization\n")
                        suggestions.append("```sql\n-- Perform VACUUM ANALYZE to reclaim space and update statistics\nVACUUM ANALYZE {table_name};\n\n-- Consider table partitioning for very large tables\n-- Example: CREATE TABLE {table_name}_partitioned PARTITION BY RANGE (date_column);\n```\n")
            
            # Add suggestions for slow queries
            if 'slow_queries' in insights_data and isinstance(insights_data['slow_queries'], list):
                suggestions.append("## Slow Query Optimization\n")
                
                for query in insights_data['slow_queries']:
                    query_text = query.get('query', '')
                    mean_time = query.get('mean_time', 0)
                    
                    if query_text and mean_time > 100:
                        truncated_query = query_text[:100] + '...' if len(query_text) > 100 else query_text
                        suggestions.append(f"### Slow Query (Avg Time: {mean_time}ms)\n")
                        suggestions.append(f"- **Query**: `{truncated_query}`\n")
                        suggestions.append("- **Recommendation**: Analyze execution plan and optimize\n")
                        suggestions.append("```sql\n-- Analyze the query execution plan\nEXPLAIN ANALYZE {query_text};\n\n-- Consider adding indexes on columns used in WHERE, JOIN, and ORDER BY clauses\n```\n")
            
            # Add general recommendations if no specific issues found
            if not suggestions:
                suggestions.append("## General Database Optimization Recommendations\n")
                suggestions.append("1. **Regular Maintenance**: Schedule regular VACUUM and ANALYZE operations\n")
                suggestions.append("2. **Index Review**: Periodically review and optimize indexes\n")
                suggestions.append("3. **Query Monitoring**: Monitor and optimize slow queries\n")
                suggestions.append("4. **Resource Allocation**: Ensure adequate resources for database operations\n")
            
            return "\n".join(suggestions)
            
        except Exception as e:
            logger.error(f"Error generating fallback suggestions: {str(e)}")
            return "Unable to generate suggestions due to an error. Please check the database insights manually."
    
    def analyze_query_patterns(self, conn_name: str, table_name: str) -> Dict:
        """
        Analyze query patterns for a specific table to identify optimal indexes
        
        Args:
            conn_name: Name of the database connection to use
            table_name: Name of the table to analyze
            
        Returns:
            Dictionary with query pattern analysis and index recommendations
        """
        if conn_name not in self.connections:
            logger.error(f"Database connection '{conn_name}' not found")
            return {"success": False, "message": f"Database connection '{conn_name}' not found"}
            
        # Get the database connection
        db_conn = self.connections[conn_name]
        
        # Results dictionary
        results = {
            "table_name": table_name,
            "query_patterns": [],
            "recommended_indexes": [],
            "success": True
        }
        
        try:
            # Get recent queries that access this table
            recent_queries_sql = f"""
                SELECT query, calls, total_time, mean_time, rows
                FROM pg_stat_statements
                WHERE query ILIKE '%{table_name}%'
                  AND query NOT ILIKE '%pg_stat_statements%'
                ORDER BY total_time DESC
                LIMIT 20;
            """
            
            success, queries_result, _ = db_conn.execute_query(recent_queries_sql)
            
            if not success or not queries_result:
                # Try an alternative approach if pg_stat_statements is not available
                logger.warning("Could not retrieve query patterns from pg_stat_statements")
                
                # Get table columns to determine what to index
                columns_query = f"""
                    SELECT column_name, data_type 
                    FROM information_schema.columns 
                    WHERE table_name = '{table_name}'
                    ORDER BY ordinal_position;
                """
                success, columns_result, _ = db_conn.execute_query(columns_query)
                
                if success and columns_result:
                    # Identify potentially useful columns for indexing based on naming patterns
                    indexable_columns = []
                    for col in columns_result:
                        col_name = col[0]
                        data_type = col[1]
                        
                        # Skip primary key columns as they're already indexed
                        if col_name == 'id' or col_name.endswith('_id'):
                            continue
                            
                        # Identify columns that are commonly used in WHERE clauses
                        if any(keyword in col_name for keyword in ['status', 'type', 'category', 'date', 'time', 'name', 'code']):
                            indexable_columns.append({
                                "column_name": col_name,
                                "data_type": data_type,
                                "reason": "Common filter column based on naming pattern"
                            })
                    
                    # Add recommendations for single-column indexes
                    for col in indexable_columns:
                        results["recommended_indexes"].append({
                            "index_name": f"idx_{table_name}_{col['column_name']}",
                            "columns": [col['column_name']],
                            "type": "btree",
                            "reason": col['reason']
                        })
                    
                    # Add recommendations for compound indexes if we have status + time columns
                    status_cols = [col["column_name"] for col in indexable_columns if "status" in col["column_name"]]
                    time_cols = [col["column_name"] for col in indexable_columns if "time" in col["column_name"] or "date" in col["column_name"]]
                    
                    if status_cols and time_cols:
                        for status_col in status_cols:
                            for time_col in time_cols:
                                results["recommended_indexes"].append({
                                    "index_name": f"idx_{table_name}_{status_col}_{time_col}",
                                    "columns": [status_col, time_col],
                                    "type": "btree",
                                    "reason": "Compound index for status + time filtering"
                                })
            else:
                # Analyze the queries to identify patterns
                for query_data in queries_result:
                    query = query_data.get('query', '')
                    calls = query_data.get('calls', 0)
                    total_time = query_data.get('total_time', 0)
                    rows = query_data.get('rows', 0)
                    
                    # Skip non-SELECT queries for now
                    if not query.lower().startswith('select'):
                        continue
                    
                    # Extract WHERE clause conditions
                    where_match = re.search(r'where\s+(.*?)(?:order by|group by|limit|$)', query.lower(), re.DOTALL)
                    where_clause = where_match.group(1).strip() if where_match else ""
                    
                    # Extract ORDER BY clause
                    order_match = re.search(r'order by\s+(.*?)(?:limit|$)', query.lower(), re.DOTALL)
                    order_clause = order_match.group(1).strip() if order_match else ""
                    
                    # Add to query patterns
                    results["query_patterns"].append({
                        "query_type": "SELECT",
                        "where_clause": where_clause,
                        "order_clause": order_clause,
                        "calls": calls,
                        "total_time": total_time,
                        "rows": rows
                    })
                
                # Analyze WHERE clauses to identify columns for indexing
                where_columns = set()
                for pattern in results["query_patterns"]:
                    where_clause = pattern.get("where_clause", "")
                    if where_clause:
                        # Simple pattern matching for column names in WHERE clause
                        col_matches = re.findall(r'(\w+)\s*[=><]', where_clause)
                        where_columns.update(col_matches)
                
                # Analyze ORDER BY clauses to identify columns for indexing
                order_columns = set()
                for pattern in results["query_patterns"]:
                    order_clause = pattern.get("order_clause", "")
                    if order_clause:
                        # Simple pattern matching for column names in ORDER BY clause
                        col_matches = re.findall(r'(\w+)(?:\s+(?:asc|desc))?', order_clause)
                        order_columns.update(col_matches)
                
                # Get table columns to validate our findings
                columns_query = f"""
                    SELECT column_name, data_type 
                    FROM information_schema.columns 
                    WHERE table_name = '{table_name}'
                    ORDER BY ordinal_position;
                """
                success, columns_result, _ = db_conn.execute_query(columns_query)
                
                if success and columns_result:
                    # Get list of valid column names
                    valid_columns = [col[0] for col in columns_result]
                    
                    # Filter out invalid column names
                    where_columns = [col for col in where_columns if col in valid_columns]
                    order_columns = [col for col in order_columns if col in valid_columns]
                    
                    # Add recommendations for single-column indexes
                    for col in where_columns:
                        results["recommended_indexes"].append({
                            "index_name": f"idx_{table_name}_{col}",
                            "columns": [col],
                            "type": "btree",
                            "reason": "Frequently used in WHERE clauses"
                        })
                    
                    for col in order_columns:
                        if col not in where_columns:  # Avoid duplicate recommendations
                            results["recommended_indexes"].append({
                                "index_name": f"idx_{table_name}_{col}",
                                "columns": [col],
                                "type": "btree",
                                "reason": "Frequently used in ORDER BY clauses"
                            })
                    
                    # Identify potential compound indexes (pairs of columns often used together)
                    if len(where_columns) >= 2:
                        # For simplicity, just recommend a compound index on the first two columns
                        col1, col2 = list(where_columns)[:2]
                        results["recommended_indexes"].append({
                            "index_name": f"idx_{table_name}_{col1}_{col2}",
                            "columns": [col1, col2],
                            "type": "btree",
                            "reason": "Frequently used together in WHERE clauses"
                        })
            
            return results
            
        except Exception as e:
            logger.error(f"Error analyzing query patterns for table {table_name}: {str(e)}")
            return {
                "success": False,
                "message": f"Error analyzing query patterns: {str(e)}",
                "table_name": table_name
            }
    
    def send_to_slack(self, message: str, severity: str = "info") -> bool:
        """
        Send a message to Slack
        
        Args:
            message: Message to send
            severity: Message severity (info, warning, error)
            
        Returns:
            True if message was sent successfully, False otherwise
        """
        try:
            # Get Slack token and channel from environment variables
            slack_token = os.environ.get('SLACK_TOKEN', '')
            slack_channel = os.environ.get('SLACK_CHANNEL', '')
            
            # Never log any part of the token: the first characters identify
            # the workspace and the token type, and application logs are the
            # least controlled place a credential fragment can end up.
            logger.info("Slack token: %s", "configured" if slack_token else "not set")
            logger.info(f"Using Slack channel: {slack_channel}")
            
            if not slack_token or not slack_channel:
                logger.warning("Slack token or channel not configured")
                return False
                
            # Prepare the payload
            payload = {
                "token": slack_token,
                "channel": slack_channel,
                "text": message,
                "mrkdwn": True
            }
            
            # Add color based on severity
            attachments = []
            if severity == "warning":
                attachments = [{"color": "#FFA500"}]
            elif severity == "error":
                attachments = [{"color": "#FF0000"}]
            else:
                attachments = [{"color": "#36a64f"}]
                
            if attachments:
                payload["attachments"] = json.dumps(attachments)
                
            # Send the message to Slack using the Web API
            response = requests.post(
                'https://slack.com/api/chat.postMessage',
                data=payload,
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            )
            
            response_data = response.json()
            
            if response.status_code == 200 and response_data.get('ok', False):
                logger.info("Successfully sent message to Slack")
                return True
            else:
                logger.error(f"Failed to send message to Slack: {response.status_code} {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"Error sending message to Slack: {str(e)}")
            return False
            
    def generate_insights(self, conn_name: str) -> Dict:
        """Generate insights about database health"""
        if conn_name not in self.connections:
            logger.error(f"Connection '{conn_name}' not found in generate_insights")
            return {"success": False, "error": f"Connection '{conn_name}' not found"}

        try:
            conn = self.connections[conn_name]
            insights = {
                "timestamp": datetime.now().isoformat(),
                "database_size": [],
                "largest_tables": [],
                "index_recommendations": [],
                "performance_issues": [],
                "overall_health": "Unknown"
            }

            # Get database size info
            try:
                if conn.db_type == 'postgresql':
                    query = """
                        SELECT 
                            datname as database_name,
                            pg_size_pretty(pg_database_size(datname)) as size_pretty,
                            pg_database_size(datname) as size_bytes
                        FROM pg_database
                        ORDER BY pg_database_size(datname) DESC;
                    """
                else:  # mysql
                    query = """
                        SELECT 
                            table_schema as database_name,
                            CONCAT(ROUND(SUM(data_length + index_length) / 1024 / 1024, 2), ' MB') as size_pretty,
                            SUM(data_length + index_length) as size_bytes
                        FROM information_schema.tables
                        GROUP BY table_schema
                        ORDER BY size_bytes DESC;
                    """
                
                success, result, _ = conn.execute_query(query)
                if success and result:
                    insights["database_size"] = result
            except Exception as e:
                logger.error(f"Error getting database size: {str(e)}")
                insights["database_size"] = [{"database_name": "Error", "size_pretty": "Failed to retrieve", "error": str(e)}]

            # Get largest tables
            try:
                if conn.db_type == 'postgresql':
                    query = """
                        SELECT
                            schemaname as table_schema,
                            relname as table_name,
                            pg_size_pretty(pg_total_relation_size(relid)) as total_size_pretty,
                            pg_total_relation_size(relid) as total_size_bytes,
                            pg_size_pretty(pg_relation_size(relid)) as table_size_pretty,
                            pg_relation_size(relid) as table_size_bytes,
                            pg_size_pretty(pg_total_relation_size(relid) - pg_relation_size(relid)) as index_size_pretty,
                            pg_total_relation_size(relid) - pg_relation_size(relid) as index_size_bytes
                        FROM pg_catalog.pg_statio_user_tables
                        ORDER BY pg_total_relation_size(relid) DESC
                        LIMIT 5;
                    """
                else:  # mysql
                    query = """
                        SELECT 
                            table_schema as table_schema,
                            table_name,
                            CONCAT(ROUND(data_length / 1024 / 1024, 2), ' MB') as data_size_pretty,
                            data_length as data_size_bytes,
                            CONCAT(ROUND(index_length / 1024 / 1024, 2), ' MB') as index_size_pretty,
                            index_length as index_size_bytes,
                            CONCAT(ROUND((data_length + index_length) / 1024 / 1024, 2), ' MB') as total_size_pretty,
                            (data_length + index_length) as total_size_bytes
                        FROM information_schema.tables
                        ORDER BY (data_length + index_length) DESC;
                    """
                
                success, result, _ = conn.execute_query(query)
                if success and result:
                    insights["largest_tables"] = result
            except Exception as e:
                logger.error(f"Error getting largest tables: {str(e)}")
                insights["largest_tables"] = [{"table_name": "Error", "total_size_pretty": "Failed to retrieve", "error": str(e)}]

            # Get index recommendations
            try:
                if conn.db_type == 'postgresql':
                    query = """
                        SELECT
                            schemaname as schema_name,
                            relname as table_name,
                            seq_scan,
                            seq_tup_read,
                            idx_scan,
                            n_live_tup as estimated_row_count,
                            CASE 
                                WHEN seq_scan = 0 THEN 0
                                ELSE round(100.0 * seq_scan / (seq_scan + idx_scan), 2)
                            END as seq_scan_percent
                        FROM pg_stat_user_tables
                        WHERE (seq_scan + idx_scan) > 0
                        AND seq_scan > idx_scan
                        AND n_live_tup > 100
                        ORDER BY seq_tup_read DESC
                        LIMIT 5;
                    """
                    success, result, _ = conn.execute_query(query)
                    if success and result:
                        insights["index_recommendations"] = result
                else:  # mysql
                    query = """
                        SELECT
                            table_schema,
                            table_name,
                            table_rows as estimated_row_count,
                            index_length,
                            data_length
                        FROM information_schema.tables
                        WHERE table_rows > 100
                        AND table_schema NOT IN ('mysql', 'information_schema', 'performance_schema')
                        ORDER BY table_rows DESC
                        LIMIT 5;
                    """
                    success, result, _ = conn.execute_query(query)
                    if success and result:
                        insights["index_recommendations"] = result
            except Exception as e:
                logger.error(f"Error getting index recommendations: {str(e)}")
                insights["index_recommendations"] = []

            # Get performance issues
            try:
                if conn.db_type == 'postgresql':
                    # Try to use pg_stat_activity instead of pg_stat_statements
                    query = """
                        SELECT 
                            datname as database,
                            usename as username,
                            application_name,
                            state,
                            substr(query, 1, 200) as query_text,
                            extract(epoch from (now() - query_start)) as duration_seconds
                        FROM pg_stat_activity
                        WHERE state != 'idle'
                        AND query != '<IDLE>'
                        AND query NOT ILIKE '%pg_stat_activity%'
                        ORDER BY duration_seconds DESC
                        LIMIT 10;
                    """
                    success, result, _ = conn.execute_query(query)
                    if success and result:
                        insights["performance_issues"] = result
                else:  # MySQL
                    query = """
                        SELECT 
                            user as username,
                            host,
                            db as database,
                            command,
                            time as duration_seconds,
                            state,
                            info as query
                        FROM information_schema.processlist
                        WHERE command != 'Sleep'
                        AND info IS NOT NULL
                        ORDER BY time DESC;
                    """
                    success, result, _ = conn.execute_query(query)
                    if success and result:
                        insights["performance_issues"] = result
            except Exception as e:
                logger.error(f"Error getting performance issues: {str(e)}")
                insights["performance_issues"] = []

            # Set overall health based on collected metrics
            health_score = 0
            total_metrics = 0

            if insights["database_size"]:
                health_score += 1
                total_metrics += 1

            if insights["largest_tables"]:
                health_score += 1
                total_metrics += 1

            if not insights["index_recommendations"]:
                health_score += 1
                total_metrics += 1

            if not insights["performance_issues"]:
                health_score += 1
                total_metrics += 1

            if total_metrics > 0:
                health_score_percent = (health_score / total_metrics) * 100
                if health_score_percent >= 90:
                    insights["overall_health"] = "Excellent"
                elif health_score_percent >= 70:
                    insights["overall_health"] = "Good"
                elif health_score_percent >= 50:
                    insights["overall_health"] = "Fair"
                else:
                    insights["overall_health"] = "Poor"

            # Return the insights
            return {"success": True, "insights": insights}

        except Exception as e:
            logger.error(f"Error generating insights: {str(e)}")
            return {"success": False, "error": str(e)}
            
    # Get or create connection
    def main(self):
        """Run the DBA AI Agent API server"""
        port = int(os.environ.get("PORT", 8000))
        uvicorn.run(app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    LLMQueryOptimizer().main()