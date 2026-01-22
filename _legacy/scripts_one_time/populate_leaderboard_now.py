#!/usr/bin/env python3
"""
Direct script to populate leaderboard cache with real user data
Run this to immediately fix the leaderboard display issue
"""

import os
import sys
from datetime import datetime, date, timedelta

# Add the current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def populate_leaderboard():
    """Populate leaderboard cache with real user performance data"""
    try:
        # Import Flask app and models
        from models import db, PortfolioSnapshot, User, Stock, LeaderboardCache
        from leaderboard_utils import update_leaderboard_cache, get_leaderboard_data
        
        print("=== Leaderboard Population Script ===")
        print(f"Started at: {datetime.now()}")
        
        # Check basic data availability
        total_users = User.query.count()
        users_with_stocks = User.query.join(Stock).distinct().count()
        total_snapshots = PortfolioSnapshot.query.count()
        yesterday = date.today() - timedelta(days=1)
        yesterday_snapshots = PortfolioSnapshot.query.filter_by(date=yesterday).count()
        
        print(f"\n=== Data Check ===")
        print(f"Total users: {total_users}")
        print(f"Users with stocks: {users_with_stocks}")
        print(f"Total snapshots: {total_snapshots}")
        print(f"Yesterday snapshots: {yesterday_snapshots}")
        
        if users_with_stocks == 0:
            print("ERROR: No users have stocks - leaderboard cannot be populated")
            return False
        
        if total_snapshots == 0:
            print("ERROR: No portfolio snapshots exist - need to create snapshots first")
            print("SUGGESTION: Run create_initial_snapshots.py first")
            return False
        
        # Show recent snapshots for verification
        print(f"\n=== Recent Snapshots ===")
        recent_snapshots = PortfolioSnapshot.query.filter(
            PortfolioSnapshot.date >= yesterday - timedelta(days=2)
        ).order_by(PortfolioSnapshot.date.desc()).limit(5).all()
        
        for snapshot in recent_snapshots:
            user = User.query.get(snapshot.user_id)
            print(f"User: {user.username if user else 'Unknown'} | Date: {snapshot.date} | Value: ${snapshot.total_value:,.2f}")
        
        # Update leaderboard cache with real data
        print(f"\n=== Updating Leaderboard Cache ===")
        updated_count = update_leaderboard_cache()
        print(f"Updated {updated_count} leaderboard periods")
        
        # Test the results
        print(f"\n=== Testing Results ===")
        test_data = get_leaderboard_data('YTD', 10, 'all')
        print(f"YTD leaderboard entries: {len(test_data)}")
        
        if test_data:
            print("\nTop 3 performers (YTD):")
            for i, entry in enumerate(test_data[:3], 1):
                print(f"{i}. {entry['username']} - {entry['performance_percent']:+.2f}% (${entry['portfolio_value']:,.2f})")
        
        # Check cache status
        print(f"\n=== Cache Status ===")
        cache_entries = LeaderboardCache.query.all()
        for cache in cache_entries:
            import json
            try:
                cached_data = json.loads(cache.leaderboard_data)
                print(f"Period: {cache.period} | Entries: {len(cached_data)} | Generated: {cache.generated_at}")
            except Exception as e:
                print(f"Period: {cache.period} | ERROR: {e}")
        
        print(f"\n=== SUCCESS ===")
        print("Leaderboard cache populated with real user performance data")
        print("The homepage should now display actual user rankings")
        
        return True
        
    except Exception as e:
        import traceback
        print(f"\nERROR: {e}")
        print(f"Traceback: {traceback.format_exc()}")
        return False

if __name__ == "__main__":
    # Set up Flask app context
    try:
        from api.index import app
        with app.app_context():
            success = populate_leaderboard()
            sys.exit(0 if success else 1)
    except ImportError:
        # Try local app.py if api/index.py doesn't work
        try:
            from app import app
            with app.app_context():
                success = populate_leaderboard()
                sys.exit(0 if success else 1)
        except Exception as e:
            print(f"Failed to import Flask app: {e}")
            sys.exit(1)
