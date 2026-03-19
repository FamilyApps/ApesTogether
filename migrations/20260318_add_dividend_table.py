"""
Migration: Add dividend table for tracking dividend payments.

Run with: python migrations/20260318_add_dividend_table.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app, db

CREATE_SQL = """
CREATE TABLE IF NOT EXISTS dividend (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES "user"(id),
    ticker VARCHAR(10) NOT NULL,
    amount_per_share FLOAT NOT NULL,
    shares_held FLOAT NOT NULL,
    total_amount FLOAT NOT NULL,
    ex_date DATE NOT NULL,
    pay_date DATE,
    recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT unique_user_ticker_exdate_dividend UNIQUE (user_id, ticker, ex_date)
);

CREATE INDEX IF NOT EXISTS idx_dividend_user_id ON dividend(user_id);
CREATE INDEX IF NOT EXISTS idx_dividend_ticker ON dividend(ticker);
CREATE INDEX IF NOT EXISTS idx_dividend_ex_date ON dividend(ex_date);
"""

if __name__ == '__main__':
    with app.app_context():
        try:
            db.session.execute(db.text(CREATE_SQL))
            db.session.commit()
            print("Successfully created dividend table")
        except Exception as e:
            db.session.rollback()
            print(f"Error: {e}")
            # Try with SQLite syntax if PostgreSQL fails
            try:
                sqlite_sql = CREATE_SQL.replace('SERIAL', 'INTEGER').replace('"user"', 'user')
                db.session.execute(db.text(sqlite_sql))
                db.session.commit()
                print("Successfully created dividend table (SQLite)")
            except Exception as e2:
                print(f"SQLite fallback also failed: {e2}")
