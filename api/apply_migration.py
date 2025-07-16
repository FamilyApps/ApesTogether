"""
Apply database migrations for ApesTogether stock portfolio app

This script is designed to be run as a one-time operation in the Vercel environment
to apply the necessary database migrations.
"""
from migrations import run_migration
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def handler(event, context):
    """Serverless function handler to run migrations"""
    try:
        logger.info("Starting database migration...")
        run_migration()
        logger.info("Migration completed successfully")
        return {
            "statusCode": 200,
            "body": "Migration completed successfully"
        }
    except Exception as e:
        logger.error(f"Migration failed: {str(e)}")
        return {
            "statusCode": 500,
            "body": f"Migration failed: {str(e)}"
        }

# For local testing
if __name__ == "__main__":
    handler(None, None)
