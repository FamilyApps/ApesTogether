#!/usr/bin/env python3
"""
Debug script to check why portfolio values are showing as $0
"""

import os
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from models import db, User, Stock, PortfolioSnapshot
from portfolio_performance import PortfolioPerformanceCalculator
from datetime import date, datetime

def debug_portfolio_values():
    """Debug portfolio value calculations"""
    print("=== PORTFOLIO VALUE DEBUG ===")
    
    # Check users
    users = User.query.all()
    print(f"\n📊 Found {len(users)} users:")
    for user in users:
        print(f"  - User {user.id}: {user.username} ({user.email})")
    
    if not users:
        print("❌ No users found!")
        return
    
    # Check stocks for each user
    for user in users:
        print(f"\n🏢 Stocks for User {user.id} ({user.username}):")
        stocks = Stock.query.filter_by(user_id=user.id).all()
        
        if not stocks:
            print(f"  ❌ No stocks found for user {user.id}")
            continue
            
        total_cost_basis = 0
        for stock in stocks:
            cost_basis = stock.quantity * stock.purchase_price if stock.purchase_price else 0
            total_cost_basis += cost_basis
            print(f"  - {stock.ticker}: {stock.quantity} shares @ ${stock.purchase_price} = ${cost_basis:.2f}")
        
        print(f"  💰 Total Cost Basis: ${total_cost_basis:.2f}")
        
        # Test portfolio calculator
        print(f"\n🧮 Testing PortfolioPerformanceCalculator for User {user.id}:")
        try:
            calculator = PortfolioPerformanceCalculator()
            
            # Test current value
            current_value = calculator.calculate_portfolio_value(user.id)
            print(f"  Current Value: ${current_value:.2f}")
            
            # Test 9/26/2025 value
            target_date = date(2025, 9, 26)
            historical_value = calculator.calculate_portfolio_value(user.id, target_date)
            print(f"  9/26/2025 Value: ${historical_value:.2f}")
            
        except Exception as e:
            print(f"  ❌ Calculator Error: {e}")
            import traceback
            traceback.print_exc()
    
    # Check recent snapshots
    print(f"\n📸 Recent Portfolio Snapshots:")
    recent_snapshots = PortfolioSnapshot.query.order_by(PortfolioSnapshot.date.desc()).limit(10).all()
    
    if not recent_snapshots:
        print("  ❌ No snapshots found!")
    else:
        for snapshot in recent_snapshots:
            user = User.query.get(snapshot.user_id)
            username = user.username if user else f"User {snapshot.user_id}"
            print(f"  - {snapshot.date}: {username} = ${snapshot.total_value:.2f}")

if __name__ == "__main__":
    debug_portfolio_values()
