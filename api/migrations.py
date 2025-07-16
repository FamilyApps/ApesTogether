"""
Database migration script for ApesTogether stock portfolio app

This script creates and applies migrations to add missing columns to the production database.
It specifically adds the 'created_at' column to the User table.
"""
import os
import sys
from datetime import datetime
from sqlalchemy import create_engine, MetaData, Table, Column, DateTime
from sqlalchemy.exc import OperationalError
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Get database URL with fallbacks
DATABASE_URL = os.environ.get('DATABASE_URL') or os.environ.get('POSTGRES_PRISMA_URL')

# Make sure DATABASE_URL is properly formatted for SQLAlchemy
if DATABASE_URL and DATABASE_URL.startswith('postgres://'):
    DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql://', 1)

def run_migration():
    """Run the migration to add created_at column to User table"""
    if not DATABASE_URL:
        print("Error: No database URL found in environment variables")
        sys.exit(1)
    
    print(f"Connecting to database...")
    
    try:
        # Connect to the database
        engine = create_engine(DATABASE_URL)
        conn = engine.connect()
        metadata = MetaData()
        metadata.reflect(bind=engine)
        
        # Check if the User table exists
        if 'user' not in metadata.tables:
            print("Error: User table not found in database")
            sys.exit(1)
        
        # Get the User table
        user_table = metadata.tables['user']
        
        # Check if created_at column already exists
        if 'created_at' in user_table.columns:
            print("created_at column already exists in User table")
            return
        
        # Add created_at column with current timestamp as default
        print("Adding created_at column to User table...")
        conn.execute(f'ALTER TABLE "user" ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP')
        
        print("Migration completed successfully!")
        
    except OperationalError as e:
        print(f"Database error: {str(e)}")
        sys.exit(1)
    except Exception as e:
        print(f"Error: {str(e)}")
        sys.exit(1)
    finally:
        if 'conn' in locals():
            conn.close()

if __name__ == "__main__":
    run_migration()
