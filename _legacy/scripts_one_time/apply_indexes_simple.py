"""
Simple script to apply indexes - uses SQLAlchemy (already installed)
Just run: python apply_indexes_simple.py
"""

import os
import sys

# Add the current directory to path so we can import from api
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

# Import the app to get the db connection
from api.index import app, db

def apply_indexes():
    """Apply composite indexes using SQLAlchemy."""
    
    print("\n" + "="*60)
    print("APPLYING COMPOSITE INDEXES")
    print("="*60)
    
    with app.app_context():
        try:
            # Index 1: PortfolioSnapshot (user_id, date)
            print("\n1. Creating index on portfolio_snapshot (user_id, date)...")
            db.session.execute(db.text("""
                CREATE INDEX IF NOT EXISTS idx_portfolio_snapshot_user_date 
                ON portfolio_snapshot (user_id, date)
            """))
            print("   ✓ idx_portfolio_snapshot_user_date")
            
            # Index 2: Stock (user_id, ticker)
            print("\n2. Creating index on stock (user_id, ticker)...")
            db.session.execute(db.text("""
                CREATE INDEX IF NOT EXISTS idx_stock_user_ticker 
                ON stock (user_id, ticker)
            """))
            print("   ✓ idx_stock_user_ticker")
            
            # Index 3: MarketData (ticker, date)
            print("\n3. Creating index on market_data (ticker, date)...")
            db.session.execute(db.text("""
                CREATE INDEX IF NOT EXISTS idx_market_data_ticker_date 
                ON market_data (ticker, date)
            """))
            print("   ✓ idx_market_data_ticker_date")
            
            # Refresh statistics
            print("\n4. Refreshing query planner statistics...")
            db.session.execute(db.text("ANALYZE portfolio_snapshot"))
            db.session.execute(db.text("ANALYZE stock"))
            db.session.execute(db.text("ANALYZE market_data"))
            print("   ✓ Statistics refreshed")
            
            # Commit
            db.session.commit()
            
            # Verify
            print("\n" + "="*60)
            print("VERIFYING INDEXES")
            print("="*60)
            
            result = db.session.execute(db.text("""
                SELECT 
                    tablename, 
                    indexname
                FROM pg_indexes 
                WHERE tablename IN ('portfolio_snapshot', 'stock', 'market_data')
                    AND indexname LIKE 'idx_%'
                ORDER BY tablename, indexname
            """))
            
            indexes = result.fetchall()
            for table, index_name in indexes:
                print(f"  ✓ {table}.{index_name}")
            
            print("\n" + "="*60)
            print("✅ SUCCESS! Indexes applied.")
            print("="*60)
            print("\nNEXT STEPS:")
            print("1. Go to: https://apestogether.ai/admin/complete-sept-backfill")
            print("2. Click: ⚡ Bulk Recalc: witty-raven")
            print("3. Should complete in <10 seconds (was timing out)")
            
        except Exception as e:
            print(f"\n❌ ERROR: {str(e)}")
            import traceback
            traceback.print_exc()
            db.session.rollback()
            sys.exit(1)

if __name__ == "__main__":
    apply_indexes()
