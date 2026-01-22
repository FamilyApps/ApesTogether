#!/usr/bin/env python3
"""
Fix zero-value snapshots by using purchase price estimates
"""

import os
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from models import db, User, Stock, PortfolioSnapshot
from datetime import date

def fix_zero_snapshots():
    """Fix snapshots that have $0 values by estimating from purchase prices"""
    print("=== FIXING ZERO-VALUE SNAPSHOTS ===")
    
    target_dates = [date(2025, 9, 25), date(2025, 9, 26)]
    
    for target_date in target_dates:
        print(f"\n📅 Fixing snapshots for {target_date}:")
        
        snapshots = PortfolioSnapshot.query.filter_by(date=target_date).all()
        
        for snapshot in snapshots:
            if snapshot.total_value == 0:
                user = User.query.get(snapshot.user_id)
                username = user.username if user else f"User {snapshot.user_id}"
                
                # Calculate estimated value from purchase prices
                stocks = Stock.query.filter_by(user_id=snapshot.user_id).all()
                estimated_value = 0
                
                for stock in stocks:
                    if stock.purchase_price and stock.quantity > 0:
                        # Use purchase price as baseline estimate
                        estimated_value += stock.quantity * stock.purchase_price
                
                if estimated_value > 0:
                    print(f"  🔧 {username}: ${snapshot.total_value:.2f} → ${estimated_value:.2f}")
                    snapshot.total_value = estimated_value
                else:
                    print(f"  ⚠️  {username}: No valid purchase prices found")
        
        try:
            db.session.commit()
            print(f"  ✅ Committed changes for {target_date}")
        except Exception as e:
            print(f"  ❌ Error committing: {e}")
            db.session.rollback()

if __name__ == "__main__":
    fix_zero_snapshots()
