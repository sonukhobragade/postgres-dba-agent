#!/usr/bin/env python3
"""
Manual integration check for Slack notifications.

This needs a reachable database and real Slack credentials, so it is a script
rather than a test: run it by hand after configuring .env.

    python scripts/check_slack_integration.py

It previously lived at the repo root as test_slack_notification.py, where
pytest collected it. Each function returns True/False instead of asserting, so
every run was reported as passing whether or not anything worked.
"""

import os
import sys
import logging
from dotenv import load_dotenv
sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parents[1]))
from dba_ai_agent import SlackNotifier, LLMQueryOptimizer, DatabaseConnection

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

def check_slack_notification():
    """Test Slack notification functionality"""
    # Load environment variables
    load_dotenv()
    
    # Initialize Slack notifier
    slack_notifier = SlackNotifier()
    
    # Test basic notification
    logger.info("Testing basic Slack notification...")
    success = slack_notifier.send_notification(
        "🧪 *Test Notification*\nThis is a test message from the DBA AI Agent.",
        severity="info"
    )
    
    if success:
        logger.info("✅ Basic Slack notification test passed")
    else:
        logger.error("❌ Basic Slack notification test failed")
        return False
    
    return True

def check_database_connection_and_alert():
    """Test database connection and send alert to Slack"""
    # Load environment variables
    load_dotenv()
    
    # Initialize Slack notifier
    slack_notifier = SlackNotifier()
    
    try:
        # Get database connection parameters from environment variables
        host = os.environ.get('DB_HOST')
        database = os.environ.get('DB_NAME')
        user = os.environ.get('DB_USER')
        password = os.environ.get('DB_PASSWORD')
        port = int(os.environ.get('DB_PORT', '5432'))
        
        logger.info(f"Connecting to database: {host}/{database}")
        
        # Create database connection
        db_conn = DatabaseConnection(
            db_type='postgresql',
            host=host,
            port=port,
            database=database,
            user=user,
            password=password
        )
        
        # Test connection
        test_query = "SELECT current_database() as db_name, current_user as username, version() as version;"
        success, result, error = db_conn.execute_query(test_query)
        
        if success and result and len(result) > 0:
            db_info = result[0]
            db_name = db_info.get('db_name', 'Unknown')
            username = db_info.get('username', 'Unknown')
            version = db_info.get('version', 'Unknown')
            
            # Send success notification to Slack
            message = (
                "🟢 *Database Connection Successful*\n\n"
                f"*Database:* {db_name}\n"
                f"*User:* {username}\n"
                f"*Version:* {version}\n\n"
                "Connection to the session database was successful."
            )
            
            success = slack_notifier.send_notification(message, severity="info")
            
            if success:
                logger.info("✅ Database connection test and Slack notification passed")
            else:
                logger.error("❌ Database connection succeeded but Slack notification failed")
                return False
                
            return True
        else:
            # Send failure notification to Slack
            message = (
                "🔴 *Database Connection Test Failed*\n\n"
                f"Failed to retrieve database information from {host}/{database}."
            )
            
            slack_notifier.send_alert("database_connection", message, severity="error")
            logger.error(f"❌ Database connection test failed - {error}")
            return False
            
    except Exception as e:
        # Send error notification to Slack
        error_message = (
            "🔴 *Database Connection Error*\n\n"
            f"Failed to connect to {host}/{database}:\n"
            f"```{str(e)}```"
        )
        
        slack_notifier.send_alert("database_connection", error_message, severity="error")
        logger.error(f"❌ Database connection test failed with error: {str(e)}")
        return False

def check_database_insights():
    """Test database insights and Slack notification"""
    # Load environment variables
    load_dotenv()
    
    try:
        # Initialize LLMQueryOptimizer
        optimizer = LLMQueryOptimizer()
        
        # Generate insights for the session database
        logger.info("Generating insights for session database...")
        insights = optimizer.generate_insights('gcp_postgres')
        
        if insights:
            # Analyze database performance and send to Slack
            logger.info("Analyzing database performance and sending to Slack...")
            result = optimizer.analyze_database_performance(insights)
            
            logger.info(f"Result: {result}")
            return "sent to Slack" in result
        else:
            logger.error("Failed to generate database insights")
            return False
    except Exception as e:
        logger.error(f"Error in test_database_insights: {str(e)}")
        return False

if __name__ == "__main__":
    print("=== Testing Slack Notification Functionality ===")
    
    # Test basic Slack notification
    basic_test_result = check_slack_notification()
    print(f"Basic Slack notification test: {'PASSED' if basic_test_result else 'FAILED'}")
    
    # Test database connection and alert
    db_test_result = check_database_connection_and_alert()
    print(f"Database connection and alert test: {'PASSED' if db_test_result else 'FAILED'}")
    
    # Test database insights
    insights_test_result = check_database_insights()
    print(f"Database insights and notification test: {'PASSED' if insights_test_result else 'FAILED'}")
    
    # Overall result
    if basic_test_result and db_test_result and insights_test_result:
        print("\n✅ All tests PASSED!")
    else:
        print("\n❌ Some tests FAILED!")
