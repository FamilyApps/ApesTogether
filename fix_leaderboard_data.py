#!/usr/bin/env python3
"""
Fix leaderboard data population issues
This script will diagnose and fix the core leaderboard data problems
"""

import os
import sys
from datetime import datetime, date, timedelta
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add the project root to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def diagnose_and_fix_leaderboard():
    """Diagnose and fix leaderboard data issues"""
    
    print("=== LEADERBOARD DATA FIX ===")
    print(f"Starting at: {datetime.now().isoformat()}")
    print()
    
    try:
        # Import required modules
        from models import db, User, LeaderboardCache, LeaderboardEntry, PortfolioSnapshot
        from leaderboard_utils import update_leaderboard_cache, calculate_leaderboard_data
        from portfolio_performance import PortfolioPerformanceCalculator
        from sqlalchemy import inspect
        import json
        
        # Step 1: Verify schema is fixed
        print("1. VERIFYING SCHEMA...")
        inspector = inspect(db.engine)
        leaderboard_columns = [col['name'] for col in inspector.get_columns('leaderboard_entry')]
        required_columns = ['period', 'performance_percent', 'small_cap_percent', 'large_cap_percent', 'avg_trades_per_week']
        
        missing_columns = [col for col in required_columns if col not in leaderboard_columns]
        if missing_columns:
            print(f"   ❌ CRITICAL: Missing columns in leaderboard_entry: {missing_columns}")
            print("   Run the schema fix endpoint first!")
            return False
        else:
            print("   ✅ Schema is correct - all required columns exist")
        print()
        
        # Step 2: Check data availability
        print("2. CHECKING DATA AVAILABILITY...")
        total_users = User.query.count()
        users_with_stocks = User.query.join(User.stocks).distinct().all()
        total_snapshots = PortfolioSnapshot.query.count()
        
        print(f"   Total users: {total_users}")
        print(f"   Users with stocks: {len(users_with_stocks)}")
        print(f"   Total portfolio snapshots: {total_snapshots}")
        
        if len(users_with_stocks) == 0:
            print("   ❌ CRITICAL: No users have stocks!")
            return False
        
        if total_snapshots == 0:
            print("   ❌ CRITICAL: No portfolio snapshots exist!")
            print("   Need to create snapshots first")
            return False
        
        print("   ✅ Basic data is available")
        print()
        
        # Step 3: Check current leaderboard status
        print("3. CURRENT LEADERBOARD STATUS...")
        for period in ['1D', '5D']:
            # Check cache
            cache_entry = LeaderboardCache.query.filter_by(period=period).first()
            cache_count = 0
            if cache_entry:
                try:
                    cache_data = json.loads(cache_entry.leaderboard_data)
                    cache_count = len(cache_data)
                except:
                    cache_count = 0
            
            # Check entries
            entry_count = LeaderboardEntry.query.filter_by(period=period).count()
            
            print(f"   {period}: Cache={cache_count} entries, DB entries={entry_count}")
            
            if cache_count == 0 and entry_count == 0:
                print(f"      ❌ No data for {period}")
            elif cache_count == 1 or entry_count == 1:
                print(f"      ⚠ Only 1 entry for {period} (should be {len(users_with_stocks)})")
        print()
        
        # Step 4: Test live calculations
        print("4. TESTING LIVE CALCULATIONS...")
        calculator = PortfolioPerformanceCalculator()
        working_users = []
        
        for user in users_with_stocks[:3]:  # Test first 3 users
            user_working = True
            print(f"   Testing User {user.id} ({user.username}):")
            
            for period in ['1D', '5D']:
                try:
                    perf_data = calculator.get_performance_data(user.id, period)
                    portfolio_return = perf_data.get('portfolio_return')
                    chart_points = len(perf_data.get('chart_data', []))
                    
                    if portfolio_return is not None and chart_points > 0:
                        print(f"      {period}: {portfolio_return:.2f}% ({chart_points} chart points) ✅")
                    else:
                        print(f"      {period}: No data or empty chart ❌")
                        user_working = False
                        
                except Exception as e:
                    print(f"      {period}: ERROR - {str(e)} ❌")
                    user_working = False
            
            if user_working:
                working_users.append(user)
        
        print(f"   Working users: {len(working_users)}/{len(users_with_stocks[:3])}")
        print()
        
        # Step 5: Fix the data
        print("5. FIXING LEADERBOARD DATA...")
        
        if len(working_users) == 0:
            print("   ❌ No users have working calculations - cannot fix leaderboard")
            return False
        
        # Clear existing broken data
        print("   Clearing existing leaderboard data...")
        LeaderboardEntry.query.filter(LeaderboardEntry.period.in_(['1D', '5D'])).delete()
        LeaderboardCache.query.filter(LeaderboardCache.period.in_(['1D', '5D'])).delete()
        db.session.commit()
        print("   ✅ Cleared old data")
        
        # Regenerate leaderboard cache for key periods
        print("   Regenerating leaderboard cache...")
        try:
            updated_count = update_leaderboard_cache(['1D', '5D'])
            print(f"   ✅ Updated {updated_count} cache entries")
        except Exception as e:
            print(f"   ❌ Cache update failed: {str(e)}")
            return False
        
        # Step 6: Verify the fix
        print("6. VERIFYING FIX...")
        for period in ['1D', '5D']:
            cache_entry = LeaderboardCache.query.filter_by(period=period).first()
            entry_count = LeaderboardEntry.query.filter_by(period=period).count()
            
            cache_count = 0
            if cache_entry:
                try:
                    cache_data = json.loads(cache_entry.leaderboard_data)
                    cache_count = len(cache_data)
                    
                    # Show sample data
                    if cache_data:
                        sample = cache_data[0]
                        print(f"   {period}: {cache_count} cache entries, {entry_count} DB entries")
                        print(f"      Sample: User {sample.get('user_id')} = {sample.get('performance_percent', 'N/A')}%")
                    
                except Exception as e:
                    print(f"   {period}: Cache parse error - {str(e)}")
            else:
                print(f"   {period}: No cache entry created")
        
        print()
        print("=== FIX COMPLETE ===")
        return True
        
    except Exception as e:
        print(f"CRITICAL ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = diagnose_and_fix_leaderboard()
    if success:
        print("✅ Leaderboard fix completed successfully!")
    else:
        print("❌ Leaderboard fix failed!")
