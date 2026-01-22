#!/usr/bin/env python3
"""
Debug script to check current leaderboard status without needing web endpoints
"""

import os
import sys
from datetime import datetime, date, timedelta
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add the project root to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def debug_leaderboard_status():
    """Check current leaderboard data status"""
    try:
        from models import db, User, LeaderboardCache, LeaderboardEntry
        from portfolio_performance import PortfolioPerformanceCalculator
        from sqlalchemy import inspect
        import json
        
        print("=== LEADERBOARD STATUS DEBUG ===")
        print(f"Timestamp: {datetime.now().isoformat()}")
        print()
        
        # Check database schema
        print("1. DATABASE SCHEMA CHECK:")
        try:
            inspector = inspect(db.engine)
            leaderboard_columns = [col['name'] for col in inspector.get_columns('leaderboard_entry')]
            print(f"   LeaderboardEntry columns: {leaderboard_columns}")
            print(f"   Has 'period' column: {'period' in leaderboard_columns}")
            print(f"   Has 'performance_percent' column: {'performance_percent' in leaderboard_columns}")
        except Exception as e:
            print(f"   ERROR: {str(e)}")
        print()
        
        # Check users with stocks
        print("2. USER DATA CHECK:")
        try:
            total_users = User.query.count()
            users_with_stocks = User.query.join(User.stocks).distinct().all()
            print(f"   Total users: {total_users}")
            print(f"   Users with stocks: {len(users_with_stocks)}")
            for user in users_with_stocks[:5]:  # Show first 5
                stock_count = len(user.stocks.all())
                print(f"   - User {user.id} ({user.username}): {stock_count} stocks")
        except Exception as e:
            print(f"   ERROR: {str(e)}")
        print()
        
        # Check leaderboard cache for key periods
        print("3. LEADERBOARD CACHE STATUS:")
        for period in ['1D', '5D', '1M', 'YTD']:
            try:
                cache_entry = LeaderboardCache.query.filter_by(period=period).first()
                if cache_entry:
                    cache_data = json.loads(cache_entry.leaderboard_data)
                    print(f"   {period}: {len(cache_data)} entries, generated at {cache_entry.generated_at}")
                    if cache_data:
                        print(f"      Sample: User {cache_data[0].get('user_id')} = {cache_data[0].get('performance_percent', 'N/A')}%")
                else:
                    print(f"   {period}: NO CACHE ENTRY")
            except Exception as e:
                print(f"   {period}: ERROR - {str(e)}")
        print()
        
        # Check leaderboard entries
        print("4. LEADERBOARD ENTRY RECORDS:")
        for period in ['1D', '5D']:
            try:
                entry_records = LeaderboardEntry.query.filter_by(period=period).all()
                print(f"   {period}: {len(entry_records)} entry records")
                for entry in entry_records[:3]:  # Show first 3
                    print(f"      User {entry.user_id}: {entry.performance_percent}% (calculated: {entry.calculated_at})")
            except Exception as e:
                print(f"   {period}: ERROR - {str(e)}")
        print()
        
        # Test live calculations for comparison
        print("5. LIVE CALCULATION TEST:")
        calculator = PortfolioPerformanceCalculator()
        for user in users_with_stocks[:3]:  # Test first 3 users
            print(f"   User {user.id} ({user.username}):")
            for period in ['1D', '5D']:
                try:
                    perf_data = calculator.get_performance_data(user.id, period)
                    portfolio_return = perf_data.get('portfolio_return', 'N/A')
                    chart_points = len(perf_data.get('chart_data', []))
                    print(f"      {period}: {portfolio_return}% (chart points: {chart_points})")
                except Exception as e:
                    print(f"      {period}: ERROR - {str(e)}")
        print()
        
        print("=== DEBUG COMPLETE ===")
        
    except Exception as e:
        print(f"CRITICAL ERROR: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    debug_leaderboard_status()
