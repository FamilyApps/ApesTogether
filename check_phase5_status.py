#!/usr/bin/env python3
"""
Quick check of Phase 5 status - how many invalid snapshots exist
"""

import os
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from datetime import date
from app import app, db
from models import PortfolioSnapshot, MarketData, User
from sqlalchemy import text

def check_phase5_status():
    """Check current Phase 5 status"""
    with app.app_context():
        print("=" * 60)
        print("PHASE 5 STATUS CHECK")
        print("=" * 60)
        
        # Get today's date
        from portfolio_performance import get_market_date
        today = get_market_date()
        print(f"\n📅 Market Date Today: {today}")
        
        # Count invalid snapshots (historical ones using current prices)
        invalid_count = PortfolioSnapshot.query.filter(
            PortfolioSnapshot.date < today
        ).count()
        
        # Count current/valid snapshots
        valid_count = PortfolioSnapshot.query.filter(
            PortfolioSnapshot.date >= today
        ).count()
        
        print(f"\n📸 PORTFOLIO SNAPSHOTS:")
        print(f"   ❌ Invalid (historical, using current prices): {invalid_count}")
        print(f"   ✅ Valid (today's snapshots): {valid_count}")
        print(f"   📊 Total: {invalid_count + valid_count}")
        
        # Check MarketData cache status
        market_data_count = MarketData.query.count()
        unique_tickers = db.session.execute(
            text("SELECT COUNT(DISTINCT ticker) as count FROM market_data")
        ).fetchone()
        
        print(f"\n💾 MARKET DATA CACHE:")
        print(f"   Total historical prices cached: {market_data_count}")
        print(f"   Unique tickers with data: {unique_tickers.count if unique_tickers else 0}")
        
        # Get breakdown by user
        print(f"\n👥 BREAKDOWN BY USER:")
        users = User.query.filter(User.max_cash_deployed > 0).order_by(User.username).all()
        
        for user in users:
            invalid_user = PortfolioSnapshot.query.filter(
                PortfolioSnapshot.user_id == user.id,
                PortfolioSnapshot.date < today
            ).count()
            
            valid_user = PortfolioSnapshot.query.filter(
                PortfolioSnapshot.user_id == user.id,
                PortfolioSnapshot.date >= today
            ).count()
            
            # Get first transaction date
            first_txn = db.session.execute(text("""
                SELECT MIN(DATE(timestamp)) as first_date
                FROM stock_transaction
                WHERE user_id = :user_id
            """), {'user_id': user.id}).fetchone()
            
            first_date = first_txn.first_date if first_txn and first_txn.first_date else None
            
            print(f"   {user.username}:")
            print(f"      First transaction: {first_date}")
            print(f"      Invalid snapshots: {invalid_user}")
            print(f"      Valid snapshots: {valid_user}")
        
        # Next steps
        print(f"\n🎯 NEXT STEPS:")
        if invalid_count > 0:
            print(f"   1. Fetch historical prices: http://localhost:5000/admin/phase5/historical-prices-dashboard")
            print(f"   2. Delete {invalid_count} invalid snapshots: http://localhost:5000/admin/phase5/delete-invalid-snapshots?execute=true")
            print(f"   3. Re-backfill with correct prices: http://localhost:5000/admin/phase4/dashboard")
        else:
            print(f"   ✅ All snapshots are valid! Phase 5 complete.")
        
        print("=" * 60)

if __name__ == "__main__":
    check_phase5_status()
