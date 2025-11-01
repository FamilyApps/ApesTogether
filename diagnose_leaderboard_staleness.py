"""
Diagnostic script to check why leaderboard is showing stale data
"""
from datetime import datetime, timedelta
from models import db, User, UserPortfolioChartCache, LeaderboardCache, PortfolioSnapshot
from performance_calculator import calculate_portfolio_performance, get_period_dates
import json

def diagnose_leaderboard_staleness():
    """Check leaderboard cache freshness vs live calculations"""
    
    print("\n" + "="*80)
    print("LEADERBOARD STALENESS DIAGNOSTIC")
    print("="*80)
    
    # Check all users
    users = User.query.all()
    print(f"\n📊 Total Users: {len(users)}")
    
    # Check 1M period (most commonly viewed)
    period = '1M'
    
    print(f"\n🔍 Checking {period} Period Cache Status:")
    print("-" * 80)
    
    for user in users:
        print(f"\n👤 User: {user.username} (ID: {user.id})")
        
        # 1. Check latest snapshot
        latest_snapshot = PortfolioSnapshot.query.filter_by(user_id=user.id)\
            .order_by(PortfolioSnapshot.date.desc()).first()
        
        if latest_snapshot:
            print(f"   Latest Snapshot: {latest_snapshot.date} - ${latest_snapshot.total_value:,.2f}")
        else:
            print(f"   ❌ No snapshots found")
            continue
        
        # 2. Check chart cache
        chart_cache = UserPortfolioChartCache.query.filter_by(
            user_id=user.id,
            period=period
        ).first()
        
        if chart_cache:
            cache_age = datetime.now() - chart_cache.generated_at
            cache_age_hours = cache_age.total_seconds() / 3600
            
            print(f"   Chart Cache:")
            print(f"      Generated: {chart_cache.generated_at}")
            print(f"      Age: {cache_age_hours:.1f} hours ago")
            
            try:
                cached_data = json.loads(chart_cache.chart_data)
                cached_return = cached_data.get('portfolio_return')
                print(f"      Cached Return: {cached_return}%")
            except:
                print(f"      ❌ Error parsing cache")
                cached_return = None
        else:
            print(f"   ❌ No chart cache found")
            cached_return = None
        
        # 3. Calculate LIVE performance
        try:
            start_date, end_date = get_period_dates(period, user_id=user.id)
            live_result = calculate_portfolio_performance(
                user.id,
                start_date,
                end_date,
                include_chart_data=False,
                period=period
            )
            
            if live_result:
                live_return = live_result.get('portfolio_return')
                print(f"   Live Calculation: {live_return}%")
                
                # Compare
                if cached_return is not None:
                    diff = abs(live_return - cached_return)
                    if diff > 0.01:
                        print(f"   ⚠️  MISMATCH: Cache shows {cached_return}%, Live is {live_return}% (diff: {diff:.2f}%)")
                    else:
                        print(f"   ✅ Cache matches live calculation")
            else:
                print(f"   ❌ Live calculation returned None")
        except Exception as e:
            print(f"   ❌ Error in live calculation: {e}")
    
    # 4. Check LeaderboardCache table
    print(f"\n📋 Leaderboard Cache Table Status:")
    print("-" * 80)
    
    leaderboard_caches = LeaderboardCache.query.filter_by(period=f'{period}_all').all()
    
    if leaderboard_caches:
        for cache in leaderboard_caches:
            cache_age = datetime.now() - cache.generated_at
            cache_age_hours = cache_age.total_seconds() / 3600
            print(f"   Period: {cache.period}")
            print(f"   Generated: {cache.generated_at}")
            print(f"   Age: {cache_age_hours:.1f} hours ago")
            
            try:
                cached_data = json.loads(cache.leaderboard_data)
                print(f"   Entries: {len(cached_data)}")
                
                # Show top 3
                for i, entry in enumerate(cached_data[:3], 1):
                    print(f"      #{i}: {entry.get('username')} - {entry.get('performance_percent')}%")
            except:
                print(f"   ❌ Error parsing cache")
    else:
        print(f"   ❌ No leaderboard cache found for {period}_all")
    
    print("\n" + "="*80)
    print("DIAGNOSTIC COMPLETE")
    print("="*80 + "\n")

if __name__ == '__main__':
    from app import app
    with app.app_context():
        diagnose_leaderboard_staleness()
