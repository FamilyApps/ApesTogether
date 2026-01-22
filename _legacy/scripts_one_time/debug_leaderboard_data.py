"""
Debug script to check actual leaderboard data availability
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from datetime import datetime, date, timedelta
from app import app

def debug_leaderboard_data():
    """Debug why leaderboard shows no data available"""
    with app.app_context():
        try:
            from models import db, PortfolioSnapshot, User, LeaderboardCache
            from leaderboard_utils import calculate_leaderboard_data, get_leaderboard_data
            import json
            
            print('=== LEADERBOARD DATA DEBUG ===')
            
            # Check basic data
            yesterday = date.today() - timedelta(days=1)
            today = date.today()
            
            total_users = User.query.count()
            total_snapshots = PortfolioSnapshot.query.count()
            yesterday_snapshots = PortfolioSnapshot.query.filter_by(date=yesterday).count()
            today_snapshots = PortfolioSnapshot.query.filter_by(date=today).count()
            
            print(f'Users: {total_users}')
            print(f'Total snapshots: {total_snapshots}')
            print(f'Yesterday snapshots: {yesterday_snapshots}')
            print(f'Today snapshots: {today_snapshots}')
            
            # Check recent snapshots
            recent_snapshots = PortfolioSnapshot.query.filter(
                PortfolioSnapshot.date >= yesterday - timedelta(days=3)
            ).order_by(PortfolioSnapshot.date.desc()).limit(10).all()
            
            print(f'\nRecent snapshots:')
            for snapshot in recent_snapshots:
                print(f'  User {snapshot.user_id}: {snapshot.date} = ${snapshot.total_value:,.2f}')
            
            # Test leaderboard calculation directly
            print(f'\n=== TESTING LEADERBOARD CALCULATION ===')
            try:
                leaderboard_data = calculate_leaderboard_data('YTD', 10, 'all')
                print(f'Direct calculation returned {len(leaderboard_data)} entries')
                
                if leaderboard_data:
                    for i, entry in enumerate(leaderboard_data[:3]):
                        print(f'  {i+1}. User {entry["user_id"]} ({entry["username"]}): {entry["performance_percent"]}% - ${entry["portfolio_value"]:,.2f}')
                else:
                    print('  No entries returned from direct calculation')
                    
            except Exception as e:
                print(f'  Error in direct calculation: {str(e)}')
                import traceback
                traceback.print_exc()
            
            # Check leaderboard cache
            print(f'\n=== CHECKING LEADERBOARD CACHE ===')
            cache_entries = LeaderboardCache.query.all()
            print(f'Cache entries: {len(cache_entries)}')
            
            for cache in cache_entries:
                try:
                    cached_data = json.loads(cache.leaderboard_data)
                    print(f'  {cache.period}: {len(cached_data)} entries, generated {cache.generated_at}')
                except Exception as e:
                    print(f'  {cache.period}: Error parsing cache data - {str(e)}')
            
            # Test get_leaderboard_data (what the API uses)
            print(f'\n=== TESTING API FUNCTION ===')
            try:
                api_data = get_leaderboard_data('YTD', 10, 'all')
                print(f'API function returned {len(api_data)} entries')
                
                if api_data:
                    for i, entry in enumerate(api_data[:3]):
                        print(f'  {i+1}. User {entry["user_id"]} ({entry["username"]}): {entry["performance_percent"]}% - ${entry["portfolio_value"]:,.2f}')
                else:
                    print('  No entries returned from API function')
                    
            except Exception as e:
                print(f'  Error in API function: {str(e)}')
                import traceback
                traceback.print_exc()
            
            # Check if users have stocks
            print(f'\n=== CHECKING USER STOCKS ===')
            from models import Stock
            users_with_stocks = User.query.join(Stock).distinct().count()
            total_stocks = Stock.query.count()
            print(f'Users with stocks: {users_with_stocks}/{total_users}')
            print(f'Total stock holdings: {total_stocks}')
            
            if users_with_stocks == 0:
                print('❌ NO USERS HAVE STOCKS - This is why leaderboard is empty!')
                return
            
            # Sample user analysis
            sample_user = User.query.join(Stock).first()
            if sample_user:
                print(f'\nSample user analysis: {sample_user.username} (ID: {sample_user.id})')
                user_stocks = Stock.query.filter_by(user_id=sample_user.id).count()
                user_snapshots = PortfolioSnapshot.query.filter_by(user_id=sample_user.id).count()
                latest_snapshot = PortfolioSnapshot.query.filter_by(user_id=sample_user.id).order_by(PortfolioSnapshot.date.desc()).first()
                
                print(f'  Stocks: {user_stocks}')
                print(f'  Snapshots: {user_snapshots}')
                if latest_snapshot:
                    print(f'  Latest snapshot: {latest_snapshot.date} = ${latest_snapshot.total_value:,.2f}')
                else:
                    print(f'  No snapshots found!')
            
        except Exception as e:
            print(f'❌ Error in debug: {str(e)}')
            import traceback
            traceback.print_exc()

if __name__ == '__main__':
    debug_leaderboard_data()
