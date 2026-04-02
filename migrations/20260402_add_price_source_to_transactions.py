"""
Migration: Add price_source column to stock_transaction table.
Tracks where the trade price came from: 'cached', 'bulk_api', 'single_api', 'manual', 'email'.

Run with: python migrations/20260402_add_price_source_to_transactions.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app, db

ALTER_SQL = """
ALTER TABLE stock_transaction ADD COLUMN IF NOT EXISTS price_source VARCHAR(20);
"""

if __name__ == '__main__':
    with app.app_context():
        try:
            db.session.execute(db.text(ALTER_SQL))
            db.session.commit()
            print("Successfully added price_source column to stock_transaction")
        except Exception as e:
            db.session.rollback()
            print(f"Error: {e}")
