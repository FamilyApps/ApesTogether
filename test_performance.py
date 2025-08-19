#!/usr/bin/env python3
"""
Test script for portfolio performance calculations using AlphaVantage
"""
import sys
import os
from datetime import datetime, date, timedelta

# Add the project directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import app
from models import db, User, Transaction, PortfolioSnapshot, MarketData
from portfolio_performance import performance_calculator

def test_performance_calculations():
    """Test the portfolio performance calculation system"""
    with app.app_context():
        print("Testing Portfolio Performance System")
        print("=" * 50)
        
        # Create test user if doesn't exist
        test_user = User.query.filter_by(email='test@example.com').first()
        if not test_user:
            test_user = User(
                email='test@example.com',
                username='testuser'
            )
            db.session.add(test_user)
            db.session.commit()
            print(f"Created test user: {test_user.username}")
        
        user_id = test_user.id
        
        # Test 1: Calculate current portfolio value
        print(f"\n1. Testing portfolio value calculation for user {user_id}")
        current_value = performance_calculator.calculate_portfolio_value(user_id)
        print(f"Current portfolio value: ${current_value:.2f}")
        
        # Test 2: Create daily snapshot
        print(f"\n2. Testing daily snapshot creation")
        performance_calculator.create_daily_snapshot(user_id)
        
        snapshot = PortfolioSnapshot.query.filter_by(
            user_id=user_id, 
            date=date.today()
        ).first()
        
        if snapshot:
            print(f"Created snapshot: ${snapshot.total_value:.2f} on {snapshot.date}")
        else:
            print("No snapshot created")
        
        # Test 3: Test S&P 500 data fetching
        print(f"\n3. Testing S&P 500 data fetching")
        end_date = date.today()
        start_date = end_date - timedelta(days=30)
        
        sp500_data = performance_calculator.get_sp500_data(start_date, end_date)
        print(f"Fetched S&P 500 data for {len(sp500_data)} days")
        
        if sp500_data:
            latest_date = max(sp500_data.keys())
            print(f"Latest S&P 500 price: ${sp500_data[latest_date]:.2f} on {latest_date}")
        
        # Test 4: Test performance calculation for 1 month
        print(f"\n4. Testing performance calculation for 1 month")
        try:
            performance_data = performance_calculator.get_performance_data(user_id, '1M')
            print(f"Portfolio return: {performance_data.get('portfolio_return', 'N/A')}%")
            print(f"S&P 500 return: {performance_data.get('sp500_return', 'N/A')}%")
            print(f"Chart data points: {len(performance_data.get('chart_data', []))}")
        except Exception as e:
            print(f"Error calculating performance: {e}")
        
        print("\n" + "=" * 50)
        print("Performance system test completed!")

if __name__ == '__main__':
    test_performance_calculations()
