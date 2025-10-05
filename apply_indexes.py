#!/usr/bin/env python3
"""
Apply composite indexes recommended by Grok for query performance.

Run this ONCE before testing the bulk recalculation endpoint.

Usage:
    python apply_indexes.py
"""

import os
import sys
from dotenv import load_dotenv
import psycopg2

# Load environment variables
load_dotenv()

def apply_indexes():
    """Apply composite indexes to improve query performance."""
    
    database_url = os.environ.get('POSTGRES_URL')
    
    if not database_url:
        print("ERROR: POSTGRES_URL not found in environment")
        sys.exit(1)
    
    print("Connecting to database...")
    
    try:
        conn = psycopg2.connect(database_url)
        cursor = conn.cursor()
        
        print("\n" + "="*60)
        print("APPLYING COMPOSITE INDEXES (Grok's Recommendation)")
        print("="*60)
        
        # Index 1: PortfolioSnapshot (user_id, date)
        print("\n1. Creating index on portfolio_snapshot (user_id, date)...")
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_portfolio_snapshot_user_date 
            ON portfolio_snapshot (user_id, date)
        """)
        print("   ✓ idx_portfolio_snapshot_user_date created")
        
        # Index 2: Stock (user_id, ticker)
        print("\n2. Creating index on stock (user_id, ticker)...")
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_stock_user_ticker 
            ON stock (user_id, ticker)
        """)
        print("   ✓ idx_stock_user_ticker created")
        
        # Index 3: MarketData (ticker, date)
        print("\n3. Creating index on market_data (ticker, date)...")
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_market_data_ticker_date 
            ON market_data (ticker, date)
        """)
        print("   ✓ idx_market_data_ticker_date created")
        
        # Refresh statistics
        print("\n4. Refreshing query planner statistics...")
        cursor.execute("ANALYZE portfolio_snapshot")
        cursor.execute("ANALYZE stock")
        cursor.execute("ANALYZE market_data")
        print("   ✓ Statistics refreshed")
        
        # Commit changes
        conn.commit()
        
        # Verify indexes
        print("\n" + "="*60)
        print("VERIFYING INDEXES")
        print("="*60)
        
        cursor.execute("""
            SELECT 
                tablename, 
                indexname, 
                indexdef 
            FROM pg_indexes 
            WHERE tablename IN ('portfolio_snapshot', 'stock', 'market_data')
            ORDER BY tablename, indexname
        """)
        
        indexes = cursor.fetchall()
        for table, index_name, index_def in indexes:
            print(f"\n{table}:")
            print(f"  - {index_name}")
            if 'idx_' in index_name:
                print(f"    {index_def}")
        
        print("\n" + "="*60)
        print("✅ SUCCESS! Indexes applied.")
        print("="*60)
        print("\nNEXT STEPS:")
        print("1. Deploy code: git push")
        print("2. Wait ~1 minute for Vercel deployment")
        print("3. Test: https://apestogether.ai/admin/complete-sept-backfill")
        print("4. Click '⚡ Bulk Recalc: witty-raven'")
        print("\nExpected: Should complete in <10 seconds (was timing out)")
        
        cursor.close()
        conn.close()
        
    except Exception as e:
        print(f"\n❌ ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    apply_indexes()
