#!/usr/bin/env python3
"""
Snapshot-Based Chart Generator
==============================
Generate chart data directly from PortfolioSnapshot data using the same logic
as the working leaderboard system. This replaces the broken PortfolioPerformanceCalculator.
"""

def generate_chart_from_snapshots(user_id, period):
    """Generate chart data from snapshots using same logic as leaderboards"""
    from datetime import datetime, date, timedelta
    from models import PortfolioSnapshot
    from leaderboard_utils import get_last_market_day
    import json
    
    # Use same date calculation logic as leaderboard_utils
    today = get_last_market_day()
    
    if period == '1D':
        start_date = today - timedelta(days=1)
    elif period == '5D':
        # Get 5 business days back (same logic as leaderboards)
        business_days_back = 0
        check_date = today
        while business_days_back < 5:
            check_date = check_date - timedelta(days=1)
            if check_date.weekday() < 5:  # Monday=0, Friday=4
                business_days_back += 1
        start_date = check_date
    elif period == '1M':
        start_date = today - timedelta(days=30)
    elif period == '3M':
        start_date = today - timedelta(days=90)
    elif period == 'YTD':
        start_date = date(today.year, 1, 1)
    elif period == '1Y':
        start_date = today - timedelta(days=365)
    else:
        start_date = date(today.year, 1, 1)  # Default to YTD
    
    # Get all snapshots for user in date range
    snapshots = PortfolioSnapshot.query.filter(
        PortfolioSnapshot.user_id == user_id,
        PortfolioSnapshot.date >= start_date,
        PortfolioSnapshot.date <= today
    ).order_by(PortfolioSnapshot.date.asc()).all()
    
    if not snapshots:
        return None
    
    # Build chart data
    labels = []
    portfolio_data = []
    
    for snapshot in snapshots:
        labels.append(snapshot.date.strftime('%Y-%m-%d'))
        portfolio_data.append(float(snapshot.total_value))
    
    # Calculate performance percentage for each point
    if len(portfolio_data) > 0:
        start_value = portfolio_data[0]
        performance_data = []
        
        for value in portfolio_data:
            if start_value > 0:
                performance_pct = ((value - start_value) / start_value) * 100
            else:
                performance_pct = 0.0
            performance_data.append(round(performance_pct, 2))
    else:
        performance_data = []
    
    # Format as Chart.js compatible data
    chart_data = {
        'labels': labels,
        'datasets': [
            {
                'label': 'Portfolio Value',
                'data': portfolio_data,
                'borderColor': 'rgb(75, 192, 192)',
                'backgroundColor': 'rgba(75, 192, 192, 0.2)',
                'tension': 0.1
            },
            {
                'label': 'Performance %',
                'data': performance_data,
                'borderColor': 'rgb(255, 99, 132)',
                'backgroundColor': 'rgba(255, 99, 132, 0.2)',
                'tension': 0.1,
                'yAxisID': 'y1'
            }
        ]
    }
    
    return chart_data

def update_user_chart_cache(user_id, period):
    """Update chart cache for specific user and period"""
    from models import db, UserPortfolioChartCache
    from datetime import datetime
    import json
    
    # Generate fresh chart data
    chart_data = generate_chart_from_snapshots(user_id, period)
    
    if not chart_data:
        return False
    
    # Update or create cache entry
    cache_entry = UserPortfolioChartCache.query.filter_by(
        user_id=user_id,
        period=period
    ).first()
    
    if cache_entry:
        cache_entry.chart_data = json.dumps(chart_data)
        cache_entry.generated_at = datetime.now()
    else:
        cache_entry = UserPortfolioChartCache(
            user_id=user_id,
            period=period,
            chart_data=json.dumps(chart_data),
            generated_at=datetime.now()
        )
        db.session.add(cache_entry)
    
    try:
        db.session.commit()
        return True
    except Exception as e:
        db.session.rollback()
        print(f"Error updating chart cache: {e}")
        return False

def regenerate_all_chart_cache():
    """Regenerate chart cache for all users using snapshot data"""
    from models import User
    
    results = {
        'users_processed': 0,
        'cache_entries_updated': 0,
        'errors': []
    }
    
    # Get all users with stocks
    users_with_stocks = User.query.join(User.stocks).distinct().all()
    
    for user in users_with_stocks:
        results['users_processed'] += 1
        
        for period in ['1D', '5D', '1M', '3M', 'YTD', '1Y']:
            try:
                success = update_user_chart_cache(user.id, period)
                if success:
                    results['cache_entries_updated'] += 1
                else:
                    results['errors'].append(f"Failed to update {user.username} {period}")
            except Exception as e:
                results['errors'].append(f"Error updating {user.username} {period}: {str(e)}")
    
    return results

if __name__ == '__main__':
    from app import app
    with app.app_context():
        print("Regenerating all chart cache from snapshots...")
        results = regenerate_all_chart_cache()
        print(f"Processed {results['users_processed']} users")
        print(f"Updated {results['cache_entries_updated']} cache entries")
        if results['errors']:
            print(f"Errors: {results['errors']}")
