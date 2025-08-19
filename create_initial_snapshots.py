#!/usr/bin/env python3
"""
Script to create initial portfolio snapshots for existing users
This populates historical data needed for performance calculations
"""

import os
import sys
from datetime import date, timedelta
from sqlalchemy import create_database_url

# Add the project root to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import app, db
from models import User, Stock, PortfolioSnapshot
from portfolio_performance import performance_calculator

def create_snapshots_for_user(user_id, days_back=30):
    """Create daily snapshots for a user going back N days"""
    print(f"Creating snapshots for user {user_id}...")
    
    # Get user's stocks
    stocks = Stock.query.filter_by(user_id=user_id).all()
    if not stocks:
        print(f"  No stocks found for user {user_id}")
        return
    
    # Create snapshots for the last N days
    for i in range(days_back, 0, -1):
        snapshot_date = date.today() - timedelta(days=i)
        
        # Skip if snapshot already exists
        existing = PortfolioSnapshot.query.filter_by(
            user_id=user_id, 
            date=snapshot_date
        ).first()
        if existing:
            continue
        
        # Calculate portfolio value for this date
        total_value = 0.0
        for stock in stocks:
            try:
                # Get stock price (this will use cached data or fetch from API)
                stock_data = performance_calculator.get_stock_data(stock.ticker)
                if stock_data and stock_data.get('price'):
                    stock_value = stock.quantity * stock_data['price']
                    total_value += stock_value
            except Exception as e:
                print(f"  Error getting price for {stock.ticker}: {e}")
                # Use current_value as fallback
                total_value += stock.current_value()
        
        # Create snapshot (assuming no cash flows for historical data)
        snapshot = PortfolioSnapshot(
            user_id=user_id,
            date=snapshot_date,
            total_value=total_value,
            cash_flow=0.0
        )
        
        try:
            db.session.add(snapshot)
            db.session.commit()
            print(f"  Created snapshot for {snapshot_date}: ${total_value:.2f}")
        except Exception as e:
            print(f"  Error creating snapshot for {snapshot_date}: {e}")
            db.session.rollback()

def main():
    with app.app_context():
        print("Creating initial portfolio snapshots...")
        
        # Get all users with stocks
        users_with_stocks = db.session.query(User.id).join(Stock).distinct().all()
        
        print(f"Found {len(users_with_stocks)} users with stocks")
        
        for (user_id,) in users_with_stocks:
            create_snapshots_for_user(user_id, days_back=30)
        
        print("Done creating initial snapshots!")
        
        # Also create today's snapshot for all users
        print("Creating today's snapshots...")
        for (user_id,) in users_with_stocks:
            try:
                performance_calculator.create_daily_snapshot(user_id)
                print(f"  Created today's snapshot for user {user_id}")
            except Exception as e:
                print(f"  Error creating today's snapshot for user {user_id}: {e}")

if __name__ == '__main__':
    main()
