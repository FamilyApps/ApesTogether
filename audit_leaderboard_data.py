"""
Audit script to check leaderboard data requirements and quality
"""
from datetime import datetime, date, timedelta
from models import db, PortfolioSnapshot, MarketData, User, Stock, StockInfo, PortfolioSnapshotIntraday
from app import app
import json

def audit_portfolio_snapshots():
    """Audit portfolio snapshot data availability and quality"""
    print('=== PORTFOLIO SNAPSHOT DATA AUDIT ===')
    
    yesterday = date.today() - timedelta(days=1)
    today = date.today()
    
    print(f'Checking data for yesterday ({yesterday}) and today ({today})')
    
    # Total snapshots
    total_snapshots = PortfolioSnapshot.query.count()
    print(f'Total portfolio snapshots in database: {total_snapshots}')
    
    # Yesterday's snapshots
    yesterday_snapshots = PortfolioSnapshot.query.filter_by(date=yesterday).count()
    print(f'Snapshots for yesterday ({yesterday}): {yesterday_snapshots}')
    
    # Today's snapshots
    today_snapshots = PortfolioSnapshot.query.filter_by(date=today).count()
    print(f'Snapshots for today ({today}): {today_snapshots}')
    
    # Recent snapshots with values
    recent_snapshots = PortfolioSnapshot.query.filter(
        PortfolioSnapshot.date >= yesterday
    ).order_by(PortfolioSnapshot.date.desc(), PortfolioSnapshot.user_id.asc()).limit(10).all()
    
    print(f'\nRecent snapshots (last 10):')
    for snapshot in recent_snapshots:
        print(f'  User {snapshot.user_id}: {snapshot.date} = ${snapshot.total_value:,.2f}')
    
    # Check for unrealistic values
    print(f'\nChecking for unrealistic portfolio values...')
    high_value_snapshots = PortfolioSnapshot.query.filter(PortfolioSnapshot.total_value > 1000000).count()
    zero_value_snapshots = PortfolioSnapshot.query.filter(PortfolioSnapshot.total_value <= 0).count()
    negative_value_snapshots = PortfolioSnapshot.query.filter(PortfolioSnapshot.total_value < 0).count()
    
    print(f'Portfolios over $1M: {high_value_snapshots}')
    print(f'Portfolios at or below $0: {zero_value_snapshots}')
    print(f'Portfolios with negative values: {negative_value_snapshots}')
    
    # Check date range coverage
    earliest_snapshot = PortfolioSnapshot.query.order_by(PortfolioSnapshot.date.asc()).first()
    latest_snapshot = PortfolioSnapshot.query.order_by(PortfolioSnapshot.date.desc()).first()
    
    if earliest_snapshot and latest_snapshot:
        print(f'\nDate range coverage:')
        print(f'  Earliest snapshot: {earliest_snapshot.date}')
        print(f'  Latest snapshot: {latest_snapshot.date}')
        
        # Check for gaps in recent data
        last_7_days = [date.today() - timedelta(days=i) for i in range(7)]
        missing_days = []
        for check_date in last_7_days:
            count = PortfolioSnapshot.query.filter_by(date=check_date).count()
            if count == 0:
                missing_days.append(check_date)
        
        if missing_days:
            print(f'  Missing snapshot days in last 7 days: {missing_days}')
        else:
            print(f'  ✓ All days in last 7 days have snapshots')
    
    return {
        'total_snapshots': total_snapshots,
        'yesterday_snapshots': yesterday_snapshots,
        'today_snapshots': today_snapshots,
        'high_value_count': high_value_snapshots,
        'zero_value_count': zero_value_snapshots,
        'negative_value_count': negative_value_snapshots
    }

def audit_intraday_data():
    """Audit intraday portfolio snapshot data"""
    print('\n=== INTRADAY DATA AUDIT ===')
    
    yesterday = date.today() - timedelta(days=1)
    today = date.today()
    
    # Total intraday snapshots
    total_intraday = PortfolioSnapshotIntraday.query.count()
    print(f'Total intraday snapshots: {total_intraday}')
    
    # Yesterday's intraday data
    yesterday_intraday = PortfolioSnapshotIntraday.query.filter(
        PortfolioSnapshotIntraday.timestamp >= datetime.combine(yesterday, datetime.min.time()),
        PortfolioSnapshotIntraday.timestamp < datetime.combine(today, datetime.min.time())
    ).count()
    print(f'Intraday snapshots for yesterday: {yesterday_intraday}')
    
    # Today's intraday data
    today_intraday = PortfolioSnapshotIntraday.query.filter(
        PortfolioSnapshotIntraday.timestamp >= datetime.combine(today, datetime.min.time())
    ).count()
    print(f'Intraday snapshots for today: {today_intraday}')
    
    # Recent intraday snapshots
    recent_intraday = PortfolioSnapshotIntraday.query.filter(
        PortfolioSnapshotIntraday.timestamp >= datetime.combine(yesterday, datetime.min.time())
    ).order_by(PortfolioSnapshotIntraday.timestamp.desc()).limit(5).all()
    
    print(f'\nRecent intraday snapshots (last 5):')
    for snapshot in recent_intraday:
        print(f'  User {snapshot.user_id}: {snapshot.timestamp} = ${snapshot.total_value:,.2f}')
    
    return {
        'total_intraday': total_intraday,
        'yesterday_intraday': yesterday_intraday,
        'today_intraday': today_intraday
    }

def audit_market_data():
    """Audit SPY/market data for realistic values"""
    print('\n=== MARKET DATA AUDIT ===')
    
    yesterday = date.today() - timedelta(days=1)
    
    # SPY daily data
    spy_daily_count = MarketData.query.filter_by(ticker='SPY_SP500').count()
    print(f'SPY daily data points: {spy_daily_count}')
    
    # Recent SPY data
    recent_spy = MarketData.query.filter_by(ticker='SPY_SP500').filter(
        MarketData.date >= yesterday - timedelta(days=7)
    ).order_by(MarketData.date.desc()).limit(10).all()
    
    print(f'\nRecent SPY data (last 10 days):')
    spy_values = []
    for data in recent_spy:
        print(f'  {data.date}: ${data.close_price:,.2f}')
        spy_values.append(data.close_price)
    
    # Check for unrealistic SPY values
    if spy_values:
        min_spy = min(spy_values)
        max_spy = max(spy_values)
        avg_spy = sum(spy_values) / len(spy_values)
        
        print(f'\nSPY value analysis:')
        print(f'  Min: ${min_spy:,.2f}')
        print(f'  Max: ${max_spy:,.2f}')
        print(f'  Avg: ${avg_spy:,.2f}')
        
        # Check for spikes (>10% daily change)
        spikes = []
        for i in range(1, len(recent_spy)):
            prev_price = recent_spy[i].close_price
            curr_price = recent_spy[i-1].close_price
            if prev_price > 0:
                change_pct = abs((curr_price - prev_price) / prev_price) * 100
                if change_pct > 10:
                    spikes.append({
                        'date': recent_spy[i-1].date,
                        'prev_price': prev_price,
                        'curr_price': curr_price,
                        'change_pct': change_pct
                    })
        
        if spikes:
            print(f'\n⚠️  SPY price spikes detected (>10% daily change):')
            for spike in spikes:
                print(f'  {spike["date"]}: ${spike["prev_price"]:.2f} → ${spike["curr_price"]:.2f} ({spike["change_pct"]:.1f}%)')
        else:
            print(f'  ✓ No unrealistic SPY price spikes detected')
    
    # SPY intraday data
    spy_intraday_count = MarketData.query.filter_by(ticker='SPY_INTRADAY').count()
    print(f'\nSPY intraday data points: {spy_intraday_count}')
    
    return {
        'spy_daily_count': spy_daily_count,
        'spy_intraday_count': spy_intraday_count,
        'recent_spy_values': spy_values,
        'spikes_detected': len(spikes) if 'spikes' in locals() else 0
    }

def audit_user_data():
    """Audit user and stock data for leaderboard requirements"""
    print('\n=== USER & STOCK DATA AUDIT ===')
    
    # User counts
    total_users = User.query.count()
    users_with_stocks = User.query.join(Stock).distinct().count()
    users_with_snapshots = User.query.join(PortfolioSnapshot).distinct().count()
    
    print(f'Total users: {total_users}')
    print(f'Users with stocks: {users_with_stocks}')
    print(f'Users with portfolio snapshots: {users_with_snapshots}')
    
    # Stock data
    total_stocks = Stock.query.count()
    unique_tickers = Stock.query.distinct(Stock.ticker).count()
    
    print(f'\nStock holdings:')
    print(f'Total stock holdings: {total_stocks}')
    print(f'Unique tickers held: {unique_tickers}')
    
    # StockInfo for market cap data
    stock_info_count = StockInfo.query.count()
    stock_info_with_market_cap = StockInfo.query.filter(StockInfo.market_cap.isnot(None)).count()
    
    print(f'\nStock info data:')
    print(f'Total stock info records: {stock_info_count}')
    print(f'Records with market cap data: {stock_info_with_market_cap}')
    
    # Sample stock info for market cap classification
    sample_stock_info = StockInfo.query.filter(StockInfo.market_cap.isnot(None)).limit(5).all()
    print(f'\nSample market cap data:')
    for info in sample_stock_info:
        market_cap_b = info.market_cap / 1_000_000_000 if info.market_cap else 0
        cap_type = 'Large Cap' if market_cap_b >= 10 else 'Small Cap'
        print(f'  {info.ticker}: ${market_cap_b:.1f}B ({cap_type})')
    
    return {
        'total_users': total_users,
        'users_with_stocks': users_with_stocks,
        'users_with_snapshots': users_with_snapshots,
        'total_stocks': total_stocks,
        'unique_tickers': unique_tickers,
        'stock_info_count': stock_info_count,
        'stock_info_with_market_cap': stock_info_with_market_cap
    }

def audit_leaderboard_variables():
    """Audit leaderboard variable names and data structure"""
    print('\n=== LEADERBOARD VARIABLE AUDIT ===')
    
    from leaderboard_utils import calculate_leaderboard_data, generate_user_portfolio_chart
    
    # Test leaderboard data calculation
    try:
        test_leaderboard = calculate_leaderboard_data('YTD', 5, 'all')
        
        if test_leaderboard:
            print(f'✓ Leaderboard calculation successful')
            print(f'Sample leaderboard entry structure:')
            sample_entry = test_leaderboard[0]
            for key, value in sample_entry.items():
                print(f'  {key}: {type(value).__name__} = {value}')
            
            # Check required fields
            required_fields = ['user_id', 'username', 'performance_percent', 'portfolio_value', 
                             'small_cap_percent', 'large_cap_percent', 'subscription_price']
            missing_fields = [field for field in required_fields if field not in sample_entry]
            
            if missing_fields:
                print(f'⚠️  Missing required fields: {missing_fields}')
            else:
                print(f'✓ All required leaderboard fields present')
                
            # Check for realistic values
            print(f'\nValue validation:')
            perf = sample_entry.get('performance_percent', 0)
            if abs(perf) > 1000:  # More than 1000% change is suspicious
                print(f'⚠️  Extreme performance value: {perf}%')
            else:
                print(f'✓ Performance value realistic: {perf}%')
                
            portfolio_val = sample_entry.get('portfolio_value', 0)
            if portfolio_val <= 0:
                print(f'⚠️  Invalid portfolio value: ${portfolio_val}')
            elif portfolio_val > 10_000_000:  # Over $10M is suspicious
                print(f'⚠️  Extremely high portfolio value: ${portfolio_val:,.2f}')
            else:
                print(f'✓ Portfolio value realistic: ${portfolio_val:,.2f}')
        else:
            print(f'⚠️  No leaderboard data returned')
    
    except Exception as e:
        print(f'❌ Error calculating leaderboard: {str(e)}')
        import traceback
        traceback.print_exc()
    
    # Test chart data generation
    try:
        if test_leaderboard:
            user_id = test_leaderboard[0]['user_id']
            test_chart = generate_user_portfolio_chart(user_id, 'YTD')
            
            if test_chart:
                print(f'\n✓ Chart generation successful')
                print(f'Chart data structure:')
                for key, value in test_chart.items():
                    if key == 'datasets':
                        print(f'  {key}: {len(value)} dataset(s)')
                        if value:
                            dataset = value[0]
                            print(f'    Dataset keys: {list(dataset.keys())}')
                            data_points = dataset.get("data", [])
                            print(f'    Data points: {len(data_points)}')
                            if data_points:
                                print(f'    Value range: ${min(data_points):,.2f} - ${max(data_points):,.2f}')
                    elif key == 'labels':
                        print(f'  {key}: {len(value)} labels')
                        if value:
                            print(f'    Date range: {value[0]} to {value[-1]}')
                    else:
                        print(f'  {key}: {type(value).__name__} = {value}')
                        
                # Validate chart data consistency
                if 'datasets' in test_chart and 'labels' in test_chart:
                    datasets = test_chart['datasets']
                    labels = test_chart['labels']
                    if datasets and len(datasets[0].get('data', [])) == len(labels):
                        print(f'✓ Chart data and labels are consistent')
                    else:
                        print(f'⚠️  Chart data and labels length mismatch')
            else:
                print(f'⚠️  No chart data returned')
    
    except Exception as e:
        print(f'❌ Error generating chart: {str(e)}')
        import traceback
        traceback.print_exc()

def main():
    """Run complete leaderboard data audit"""
    with app.app_context():
        print('LEADERBOARD DATA AUDIT')
        print('=' * 50)
        
        # Run all audits
        snapshot_results = audit_portfolio_snapshots()
        intraday_results = audit_intraday_data()
        market_results = audit_market_data()
        user_results = audit_user_data()
        audit_leaderboard_variables()
        
        # Summary
        print('\n=== AUDIT SUMMARY ===')
        print(f'Portfolio snapshots: {snapshot_results["total_snapshots"]} total')
        print(f'Yesterday snapshots: {snapshot_results["yesterday_snapshots"]}')
        print(f'Intraday snapshots: {intraday_results["total_intraday"]} total')
        print(f'SPY data points: {market_results["spy_daily_count"]} daily')
        print(f'Users with data: {user_results["users_with_snapshots"]}/{user_results["total_users"]}')
        
        # Data quality flags
        issues = []
        if snapshot_results["zero_value_count"] > 0:
            issues.append(f'{snapshot_results["zero_value_count"]} zero-value portfolios')
        if snapshot_results["negative_value_count"] > 0:
            issues.append(f'{snapshot_results["negative_value_count"]} negative-value portfolios')
        if market_results["spikes_detected"] > 0:
            issues.append(f'{market_results["spikes_detected"]} SPY price spikes')
        
        if issues:
            print(f'\n⚠️  Data quality issues detected:')
            for issue in issues:
                print(f'  - {issue}')
        else:
            print(f'\n✓ No major data quality issues detected')

if __name__ == '__main__':
    main()
