#!/usr/bin/env python3
"""
Migration script to add the StockTransaction table to the database.
"""
import os
import sys
import sqlite3
from datetime import datetime
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Database path
DB_PATH = 'portfolio.db'

def create_transaction_table():
    """Create the StockTransaction table in the database"""
    # Connect to SQLite database
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        # Check if table already exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='stock_transaction'")
        if cursor.fetchone():
            logger.info("StockTransaction table already exists")
            return False
        
        # Create the StockTransaction table
        cursor.execute('''
        CREATE TABLE stock_transaction (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            symbol TEXT NOT NULL,
            shares REAL NOT NULL,
            price REAL NOT NULL,
            transaction_type TEXT NOT NULL,
            date TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            notes TEXT,
            FOREIGN KEY (user_id) REFERENCES user (id)
        )
        ''')
        
        # Create an index on user_id for faster lookups
        cursor.execute('CREATE INDEX idx_stock_transaction_user_id ON stock_transaction (user_id)')
        
        # Commit the changes
        conn.commit()
        logger.info("StockTransaction table created successfully")
        return True
        
    except Exception as e:
        logger.error(f"Error creating StockTransaction table: {str(e)}")
        conn.rollback()
        return False
    finally:
        conn.close()

if __name__ == "__main__":
    try:
        if create_transaction_table():
            print("Migration successful: StockTransaction table created")
        else:
            print("Migration skipped: StockTransaction table already exists or error occurred")
    except Exception as e:
        logger.error(f"Migration failed: {str(e)}")
        sys.exit(1)
