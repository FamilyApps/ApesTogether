#!/usr/bin/env python3
"""
Production migration script to create the stock_transaction table.
This script is designed to work with both SQLite and PostgreSQL databases.
"""
import os
import sys
import logging
from sqlalchemy import create_engine, MetaData, Table, Column, Integer, Float, String, DateTime, ForeignKey, Index
from sqlalchemy.sql import text
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def get_database_url():
    """Get the database URL from environment or use SQLite default"""
    database_url = os.environ.get('DATABASE_URL')
    if database_url:
        # Vercel/Neon uses postgres://, but SQLAlchemy needs postgresql://
        database_url = database_url.replace('postgres://', 'postgresql://')
        return database_url
    return 'sqlite:///portfolio.db'

def create_transaction_table():
    """Create the stock_transaction table if it doesn't exist"""
    db_url = get_database_url()
    engine = create_engine(db_url)
    metadata = MetaData()
    
    # Check if table already exists
    inspector = engine.dialect.inspector
    existing_tables = inspector.get_table_names(engine)
    
    if 'stock_transaction' in existing_tables:
        logger.info("stock_transaction table already exists")
        return False
    
    # Define the stock_transaction table
    stock_transaction = Table(
        'stock_transaction', 
        metadata,
        Column('id', Integer, primary_key=True),
        Column('user_id', Integer, ForeignKey('user.id'), nullable=False),
        Column('symbol', String(10), nullable=False),
        Column('shares', Float, nullable=False),
        Column('price', Float, nullable=False),
        Column('transaction_type', String(10), nullable=False),
        Column('date', DateTime, nullable=False, default=datetime.utcnow),
        Column('notes', String(255)),
    )
    
    # Create the table
    try:
        metadata.create_all(engine)
        
        # Create an index on user_id for faster lookups
        with engine.connect() as conn:
            conn.execute(text(
                "CREATE INDEX idx_stock_transaction_user_id ON stock_transaction (user_id)"
            ))
            conn.commit()
        
        logger.info("stock_transaction table created successfully")
        return True
    
    except Exception as e:
        logger.error(f"Error creating stock_transaction table: {str(e)}")
        return False

if __name__ == "__main__":
    try:
        if create_transaction_table():
            print("Migration successful: stock_transaction table created")
        else:
            print("Migration skipped: stock_transaction table already exists or error occurred")
    except Exception as e:
        logger.error(f"Migration failed: {str(e)}")
        sys.exit(1)
