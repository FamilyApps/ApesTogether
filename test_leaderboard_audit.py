"""
Quick test to verify leaderboard data availability and structure
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from datetime import datetime, date, timedelta
from app import app

def test_leaderboard_data():
    """Test leaderboard data calculation and structure"""
    with app.app_context():
        try:
            from models import db, PortfolioSnapshot, MarketData, User, Stock, StockInfo
            from leaderboard_utils import calculate_leaderboard_data, generate_user_portfolio_chart
            
            print('=== LEADERBOARD DATA TEST ===')
            
            # Check basic data availability
            total_users = User.query.count()
            total_snapshots = PortfolioSnapshot.query.count()
            users_with_snapshots = User.query.join(PortfolioSnapshot).distinct().count()
            
            print(f'Users: {total_users}, Snapshots: {total_snapshots}, Users with snapshots: {users_with_snapshots}')
            
            if users_with_snapshots == 0:
                print('❌ No users have portfolio snapshots - leaderboard cannot function')
                return
            
            # Test leaderboard calculation
            print('\nTesting leaderboard calculation...')
            leaderboard_data = calculate_leaderboard_data('YTD', 5, 'all')
            
            if not leaderboard_data:
                print('❌ No leaderboard data returned')
                return
            
            print(f'✓ Leaderboard returned {len(leaderboard_data)} entries')
            
            # Check first entry structure
            entry = leaderboard_data[0]
            required_fields = ['user_id', 'username', 'performance_percent', 'portfolio_value', 
                             'small_cap_percent', 'large_cap_percent', 'subscription_price']
            
            print('\nEntry structure:')
            for field in required_fields:
                if field in entry:
                    value = entry[field]
                    print(f'  ✓ {field}: {value} ({type(value).__name__})')
                else:
                    print(f'  ❌ Missing: {field}')
            
            # Test chart generation
            print('\nTesting chart generation...')
            user_id = entry['user_id']
            chart_data = generate_user_portfolio_chart(user_id, 'YTD')
            
            if chart_data:
                print(f'✓ Chart generated with {len(chart_data.get("labels", []))} data points')
                if 'datasets' in chart_data and chart_data['datasets']:
                    data_points = chart_data['datasets'][0].get('data', [])
                    if data_points:
                        print(f'  Value range: ${min(data_points):,.2f} - ${max(data_points):,.2f}')
            else:
                print('❌ No chart data generated')
            
            # Check for realistic values
            print('\nValue validation:')
            perf = entry.get('performance_percent', 0)
            portfolio_val = entry.get('portfolio_value', 0)
            
            if abs(perf) > 1000:
                print(f'⚠️  Extreme performance: {perf}%')
            else:
                print(f'✓ Performance realistic: {perf}%')
                
            if portfolio_val <= 0:
                print(f'⚠️  Invalid portfolio value: ${portfolio_val}')
            elif portfolio_val > 10_000_000:
                print(f'⚠️  Very high portfolio: ${portfolio_val:,.2f}')
            else:
                print(f'✓ Portfolio value realistic: ${portfolio_val:,.2f}')
            
            print('\n✓ Leaderboard system appears functional')
            
        except Exception as e:
            print(f'❌ Error testing leaderboard: {str(e)}')
            import traceback
            traceback.print_exc()

if __name__ == '__main__':
    test_leaderboard_data()
