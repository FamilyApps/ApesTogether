#!/usr/bin/env python3
"""
Debug Friday Snapshot Issue
============================
Investigate what happened on Friday 9/26/2025 that caused:
1. Missing market close snapshots in 1M/3M/YTD/1Y charts
2. Incomplete 1D/5D chart cache generation
3. Connection between snapshot system and cache generation
"""

def debug_friday_snapshot_issue():
    """Debug the Friday 9/26/2025 snapshot and cache generation issues"""
    from datetime import datetime, date, timedelta
    from models import db, User, UserPortfolioSnapshot, UserPortfolioChartCache, StockPrice
    import json
    
    print("🔍 DEBUGGING FRIDAY 9/26/2025 SNAPSHOT ISSUE")
    print("=" * 60)
    
    # Friday 9/26/2025
    friday_date = date(2025, 9, 26)
    today = date.today()
    
    print(f"Target Date: {friday_date} (Friday)")
    print(f"Today: {today}")
    print(f"Days since Friday: {(today - friday_date).days}")
    
    results = {
        'friday_date': str(friday_date),
        'snapshot_analysis': {},
        'cache_analysis': {},
        'stock_price_analysis': {},
        'users_analysis': {}
    }
    
    # Get all users with stocks
    users_with_stocks = User.query.join(User.stocks).distinct().all()
    print(f"\n📊 Found {len(users_with_stocks)} users with stocks")
    
    # 1. Check snapshots for Friday
    print(f"\n1️⃣ SNAPSHOT ANALYSIS FOR {friday_date}")
    print("-" * 40)
    
    for user in users_with_stocks:
        friday_snapshot = UserPortfolioSnapshot.query.filter_by(
            user_id=user.id,
            date=friday_date
        ).first()
        
        if friday_snapshot:
            print(f"  ✅ {user.username}: Has Friday snapshot (${friday_snapshot.total_value:.2f})")
            results['snapshot_analysis'][user.username] = {
                'has_friday_snapshot': True,
                'total_value': float(friday_snapshot.total_value),
                'snapshot_id': friday_snapshot.id
            }
        else:
            print(f"  ❌ {user.username}: Missing Friday snapshot")
            results['snapshot_analysis'][user.username] = {
                'has_friday_snapshot': False,
                'total_value': None,
                'snapshot_id': None
            }
    
    # 2. Check recent snapshots (last 5 days)
    print(f"\n2️⃣ RECENT SNAPSHOTS (Last 5 days)")
    print("-" * 40)
    
    for i in range(5):
        check_date = today - timedelta(days=i)
        snapshot_count = UserPortfolioSnapshot.query.filter_by(date=check_date).count()
        print(f"  {check_date}: {snapshot_count} snapshots")
        
        if check_date == friday_date:
            results['snapshot_analysis']['friday_snapshot_count'] = snapshot_count
    
    # 3. Check chart cache status
    print(f"\n3️⃣ CHART CACHE ANALYSIS")
    print("-" * 40)
    
    for period in ['1D', '5D', '1M', '3M', 'YTD', '1Y']:
        cache_count = UserPortfolioChartCache.query.filter_by(period=period).count()
        print(f"  {period}: {cache_count}/{len(users_with_stocks)} users have cache")
        results['cache_analysis'][period] = {
            'cached_users': cache_count,
            'total_users': len(users_with_stocks),
            'percentage': (cache_count / len(users_with_stocks)) * 100 if len(users_with_stocks) > 0 else 0
        }
    
    # 4. Check stock price data for Friday
    print(f"\n4️⃣ STOCK PRICE DATA FOR {friday_date}")
    print("-" * 40)
    
    friday_prices = StockPrice.query.filter_by(date=friday_date).count()
    print(f"  Stock prices for Friday: {friday_prices} records")
    results['stock_price_analysis']['friday_prices'] = friday_prices
    
    # Check S&P 500 data specifically
    sp500_friday = StockPrice.query.filter_by(ticker='^GSPC', date=friday_date).first()
    if sp500_friday:
        print(f"  ✅ S&P 500 Friday data: ${sp500_friday.close:.2f}")
        results['stock_price_analysis']['sp500_friday'] = {
            'available': True,
            'close_price': float(sp500_friday.close)
        }
    else:
        print(f"  ❌ S&P 500 Friday data: Missing")
        results['stock_price_analysis']['sp500_friday'] = {
            'available': False,
            'close_price': None
        }
    
    # 5. Sample chart data to see if Friday is missing
    print(f"\n5️⃣ SAMPLE CHART DATA ANALYSIS")
    print("-" * 40)
    
    sample_user = users_with_stocks[0] if users_with_stocks else None
    if sample_user:
        for period in ['1M', '3M', 'YTD', '1Y']:
            cache_entry = UserPortfolioChartCache.query.filter_by(
                user_id=sample_user.id,
                period=period
            ).first()
            
            if cache_entry:
                try:
                    chart_data = json.loads(cache_entry.chart_data)
                    labels = chart_data.get('labels', [])
                    
                    # Check if Friday's date is in the labels
                    friday_str = friday_date.strftime('%Y-%m-%d')
                    friday_in_labels = friday_str in labels
                    
                    print(f"  {period}: {len(labels)} data points, Friday included: {friday_in_labels}")
                    
                    if not friday_in_labels and len(labels) > 0:
                        print(f"    Last data point: {labels[-1]}")
                    
                    results['cache_analysis'][f'{period}_sample'] = {
                        'data_points': len(labels),
                        'friday_included': friday_in_labels,
                        'last_data_point': labels[-1] if labels else None
                    }
                    
                except Exception as e:
                    print(f"  {period}: Error parsing chart data - {str(e)}")
            else:
                print(f"  {period}: No cache data")
    
    print(f"\n🔍 ANALYSIS COMPLETE")
    print("=" * 60)
    
    return results

def run_and_return_json():
    """API-friendly wrapper"""
    try:
        results = debug_friday_snapshot_issue()
        return {
            'success': True,
            'message': 'Friday snapshot analysis completed',
            'results': results
        }
    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'message': 'Failed to analyze Friday snapshot issue'
        }

if __name__ == '__main__':
    from app import app
    with app.app_context():
        result = run_and_return_json()
        print(f"\nFinal result: {result['success']}")
