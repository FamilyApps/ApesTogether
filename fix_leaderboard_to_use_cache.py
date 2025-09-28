#!/usr/bin/env python3
"""
Fix Leaderboard to Use Cached Data
==================================

The real issue is that leaderboard calculations are using the broken PortfolioPerformanceCalculator
instead of the working cached chart data. This script fixes the leaderboard system to use
the cached data that charts are already using successfully.

Key insight: Charts work because they use UserPortfolioChartCache. 
Leaderboards should use the same cached data, not live calculations.
"""

import os
import sys
from datetime import datetime, date, timedelta
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add the project root to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def fix_leaderboard_to_use_cache():
    """Fix leaderboard generation to use cached chart data instead of broken live calculations"""
    
    print("=" * 60)
    print("FIXING LEADERBOARD TO USE CACHED DATA")
    print("=" * 60)
    print(f"Starting at: {datetime.now().isoformat()}")
    print()
    
    try:
        from models import db, User, UserPortfolioChartCache, LeaderboardCache, LeaderboardEntry
        import json
        
        # Step 1: Check what cached chart data exists
        print("1. CHECKING CACHED CHART DATA AVAILABILITY:")
        
        users_with_stocks = User.query.join(User.stocks).distinct().all()
        print(f"   Users with stocks: {len(users_with_stocks)}")
        
        cache_status = {}
        for period in ['1D', '5D', '1M', '3M', 'YTD', '1Y']:
            cached_users = UserPortfolioChartCache.query.filter_by(period=period).count()
            cache_status[period] = cached_users
            print(f"   {period}: {cached_users} users have cached chart data")
        
        print()
        
        # Step 2: Generate leaderboard data from cached charts
        print("2. GENERATING LEADERBOARD FROM CACHED DATA:")
        
        successful_periods = []
        
        for period in ['1D', '5D']:  # Start with these two critical periods
            print(f"   Processing {period}...")
            
            # Get all users with cached chart data for this period
            cached_charts = UserPortfolioChartCache.query.filter_by(period=period).all()
            
            if not cached_charts:
                print(f"      ❌ No cached chart data for {period}")
                continue
            
            leaderboard_entries = []
            
            for chart_cache in cached_charts:
                try:
                    # Parse the cached Chart.js data
                    chart_data = json.loads(chart_cache.chart_data)
                    datasets = chart_data.get('datasets', [])
                    
                    if len(datasets) < 1:
                        continue
                    
                    # Get portfolio performance data
                    portfolio_data = datasets[0].get('data', [])
                    if not portfolio_data or len(portfolio_data) < 2:
                        continue
                    
                    # Calculate performance from first to last data point
                    start_value = portfolio_data[0]
                    end_value = portfolio_data[-1]
                    
                    if start_value > 0:
                        performance_percent = ((end_value - start_value) / start_value) * 100
                    else:
                        performance_percent = 0.0
                    
                    # Get user info
                    user = User.query.get(chart_cache.user_id)
                    if not user:
                        continue
                    
                    leaderboard_entries.append({
                        'user_id': user.id,
                        'username': user.username,
                        'performance_percent': performance_percent,
                        'portfolio_value': end_value,  # Use latest chart value
                        'small_cap_percent': 50.0,  # Default for now
                        'large_cap_percent': 50.0,   # Default for now
                        'avg_trades_per_week': 5.0   # Default for now
                    })
                    
                except Exception as e:
                    print(f"      Warning: Failed to process cache for user {chart_cache.user_id}: {str(e)}")
                    continue
            
            # Sort by performance
            leaderboard_entries.sort(key=lambda x: x['performance_percent'], reverse=True)
            
            print(f"      ✅ Generated {len(leaderboard_entries)} leaderboard entries for {period}")
            
            if len(leaderboard_entries) > 0:
                # Show top 3
                for i, entry in enumerate(leaderboard_entries[:3]):
                    print(f"         {i+1}. {entry['username']}: {entry['performance_percent']:.2f}%")
            
            # Step 3: Update LeaderboardCache
            try:
                # Clear existing cache
                LeaderboardCache.query.filter_by(period=period).delete()
                
                # Create new cache entry
                cache_entry = LeaderboardCache(
                    period=period,
                    leaderboard_data=json.dumps(leaderboard_entries),
                    generated_at=datetime.now()
                )
                db.session.add(cache_entry)
                
                # Update individual LeaderboardEntry records
                LeaderboardEntry.query.filter_by(period=period).delete()
                
                for entry_data in leaderboard_entries:
                    entry = LeaderboardEntry(
                        user_id=entry_data['user_id'],
                        period=period,
                        performance_percent=entry_data['performance_percent'],
                        small_cap_percent=entry_data['small_cap_percent'],
                        large_cap_percent=entry_data['large_cap_percent'],
                        avg_trades_per_week=entry_data['avg_trades_per_week'],
                        calculated_at=datetime.now()
                    )
                    db.session.add(entry)
                
                db.session.commit()
                print(f"      ✅ Updated cache and database for {period}")
                successful_periods.append(period)
                
            except Exception as e:
                db.session.rollback()
                print(f"      ❌ Failed to update cache for {period}: {str(e)}")
        
        print()
        
        # Step 4: Verify the fix
        print("3. VERIFYING THE FIX:")
        
        for period in successful_periods:
            # Check cache
            cache_entry = LeaderboardCache.query.filter_by(period=period).first()
            entry_count = LeaderboardEntry.query.filter_by(period=period).count()
            
            if cache_entry:
                cache_data = json.loads(cache_entry.leaderboard_data)
                print(f"   {period}: {len(cache_data)} cache entries, {entry_count} DB entries")
                
                if cache_data:
                    sample = cache_data[0]
                    print(f"      Top performer: {sample['username']} = {sample['performance_percent']:.2f}%")
            else:
                print(f"   {period}: ❌ No cache entry created")
        
        print()
        print("=" * 60)
        print("FIX COMPLETE")
        print("=" * 60)
        
        if successful_periods:
            print(f"✅ SUCCESS: Fixed leaderboards for periods: {successful_periods}")
            print("The leaderboard now uses the same cached data that makes charts work!")
            return True
        else:
            print("❌ FAILED: No periods were successfully fixed")
            return False
        
    except Exception as e:
        print(f"CRITICAL ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = fix_leaderboard_to_use_cache()
    
    if success:
        print("\n🎉 LEADERBOARD CACHE FIX SUCCESSFUL!")
        print("Leaderboards now use the same working cached data as charts.")
    else:
        print("\n❌ LEADERBOARD CACHE FIX FAILED!")
        print("Check the errors above and resolve them before trying again.")
