from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
import os
from datetime import datetime
import sys

# Add parent directory to path to import app modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import app and db from the main app
from app import app, db, User, Stock, Transaction

def create_tables():
    """Create the Transaction table if it doesn't exist"""
    with app.app_context():
        # Check if the Transaction table already exists
        inspector = db.inspect(db.engine)
        tables = inspector.get_table_names()
        
        if 'transaction' not in tables:
            print("Creating Transaction table...")
            # Create the Transaction table
            db.create_all()
            print("Transaction table created successfully!")
        else:
            print("Transaction table already exists.")

if __name__ == "__main__":
    create_tables()
