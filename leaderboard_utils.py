"""
Leaderboard utilities for calculating performance metrics and market cap classifications
"""
from datetime import datetime, date, timedelta
from models import db, User, Stock, StockInfo, LeaderboardEntry, PortfolioSnapshot
from flask import current_app
import requests
import os

def classify_market_cap(market_cap):
    """
    Classify market cap as small or large
    Small cap: < $2B, Large cap: >= $2B
    """
    if market_cap is None:
        return 'unknown'
    
    threshold = 2_000_000_000  # $2 billion
    return 'small' if market_cap < threshold else 'large'

def get_or_create_stock_info(ticker):
    """
    Get stock info from database or fetch from Alpha Vantage if not exists
    """
    stock_info = StockInfo.query.filter_by(ticker=ticker.upper()).first()
    
    if stock_info and stock_info.last_updated > datetime.now() - timedelta(days=30):
        # Use cached data if less than 30 days old
        return stock_info
    
    # Fetch from Alpha Vantage
    api_key = os.environ.get('ALPHA_VANTAGE_API_KEY')
    if not api_key:
        current_app.logger.warning("No Alpha Vantage API key found, using mock data")
        return create_mock_stock_info(ticker)
    
    try:
        # Company Overview endpoint
        url = f"https://www.alphavantage.co/query"
        params = {
            'function': 'OVERVIEW',
            'symbol': ticker,
            'apikey': api_key
        }
        
        response = requests.get(url, params=params, timeout=10)
        data = response.json()
        
        if 'MarketCapitalization' in data and data['MarketCapitalization'] != 'None':
            market_cap = int(data['MarketCapitalization'])
            company_name = data.get('Name', ticker)
            
            if not stock_info:
                stock_info = StockInfo(ticker=ticker.upper())
                db.session.add(stock_info)
            
            stock_info.company_name = company_name
            stock_info.market_cap = market_cap
            stock_info.cap_classification = classify_market_cap(market_cap)
            stock_info.last_updated = datetime.now()
            
            db.session.commit()
            return stock_info
        else:
            current_app.logger.warning(f"No market cap data for {ticker}, using mock data")
            return create_mock_stock_info(ticker)
            
    except Exception as e:
        current_app.logger.error(f"Error fetching stock info for {ticker}: {str(e)}")
        return create_mock_stock_info(ticker)

def create_mock_stock_info(ticker):
    """Create mock stock info for testing"""
    # Mock market caps for common stocks
    mock_data = {
        'AAPL': {'name': 'Apple Inc.', 'market_cap': 3_000_000_000_000},  # Large cap
        'MSFT': {'name': 'Microsoft Corporation', 'market_cap': 2_800_000_000_000},  # Large cap
        'GOOGL': {'name': 'Alphabet Inc.', 'market_cap': 1_700_000_000_000},  # Large cap
        'AMZN': {'name': 'Amazon.com Inc.', 'market_cap': 1_500_000_000_000},  # Large cap
        'TSLA': {'name': 'Tesla Inc.', 'market_cap': 800_000_000_000},  # Large cap
        'META': {'name': 'Meta Platforms Inc.', 'market_cap': 750_000_000_000},  # Large cap
        'NVDA': {'name': 'NVIDIA Corporation', 'market_cap': 1_200_000_000_000},  # Large cap
        'AMD': {'name': 'Advanced Micro Devices', 'market_cap': 180_000_000_000},  # Large cap
        'NFLX': {'name': 'Netflix Inc.', 'market_cap': 190_000_000_000},  # Large cap
        'SPOT': {'name': 'Spotify Technology S.A.', 'market_cap': 25_000_000_000},  # Large cap
        'PLTR': {'name': 'Palantir Technologies Inc.', 'market_cap': 15_000_000_000},  # Large cap
        'RBLX': {'name': 'Roblox Corporation', 'market_cap': 18_000_000_000},  # Large cap
        'CRWD': {'name': 'CrowdStrike Holdings Inc.', 'market_cap': 45_000_000_000},  # Large cap
        'ZM': {'name': 'Zoom Video Communications', 'market_cap': 20_000_000_000},  # Large cap
        'SQ': {'name': 'Block Inc.', 'market_cap': 35_000_000_000},  # Large cap
        'SHOP': {'name': 'Shopify Inc.', 'market_cap': 65_000_000_000},  # Large cap
        'ROKU': {'name': 'Roku Inc.', 'market_cap': 3_500_000_000},  # Large cap
        'PINS': {'name': 'Pinterest Inc.', 'market_cap': 18_000_000_000},  # Large cap
        'SNAP': {'name': 'Snap Inc.', 'market_cap': 15_000_000_000},  # Large cap
        'TWTR': {'name': 'Twitter Inc.', 'market_cap': 40_000_000_000},  # Large cap
        # Some small cap examples
        'SPCE': {'name': 'Virgin Galactic Holdings', 'market_cap': 500_000_000},  # Small cap
        'BB': {'name': 'BlackBerry Limited', 'market_cap': 1_200_000_000},  # Small cap
        'NOK': {'name': 'Nokia Corporation', 'market_cap': 25_000_000_000},  # Large cap
        'GME': {'name': 'GameStop Corp.', 'market_cap': 8_000_000_000},  # Large cap
        'AMC': {'name': 'AMC Entertainment Holdings', 'market_cap': 1_800_000_000},  # Small cap
    }
    
    ticker_upper = ticker.upper()
    if ticker_upper in mock_data:
        data = mock_data[ticker_upper]
        market_cap = data['market_cap']
        company_name = data['name']
    else:
        # Default mock data for unknown tickers
        market_cap = 5_000_000_000  # Default to large cap
        company_name = f"{ticker_upper} Corporation"
    
    stock_info = StockInfo.query.filter_by(ticker=ticker_upper).first()
    if not stock_info:
        stock_info = StockInfo(ticker=ticker_upper)
        db.session.add(stock_info)
    
    stock_info.company_name = company_name
    stock_info.market_cap = market_cap
    stock_info.cap_classification = classify_market_cap(market_cap)
    stock_info.last_updated = datetime.now()
    
    db.session.commit()
    return stock_info

def calculate_portfolio_cap_percentages(user_id):
    """
    Calculate small cap vs large cap percentages using existing stock info - no API calls
    Returns (small_cap_percent, large_cap_percent)
    """
    # Get the latest portfolio snapshot for total value
    latest_snapshot = PortfolioSnapshot.query.filter_by(user_id=user_id)\
        .order_by(PortfolioSnapshot.date.desc()).first()
    
    if not latest_snapshot:
        return 0.0, 0.0
    
    total_value = latest_snapshot.total_value
    stocks = Stock.query.filter_by(user_id=user_id).all()
    
    if not stocks or total_value == 0:
        return 0.0, 0.0
    
    small_cap_value = 0
    large_cap_value = 0
    
    # Calculate proportional values based on purchase prices and existing stock info
    total_purchase_value = sum(stock.quantity * stock.purchase_price for stock in stocks)
    
    for stock in stocks:
        # Get stock info (should already exist from previous population)
        stock_info = StockInfo.query.filter_by(ticker=stock.ticker.upper()).first()
        
        if stock_info and total_purchase_value > 0:
            # Calculate proportional value based on purchase weight
            stock_purchase_value = stock.quantity * stock.purchase_price
            stock_current_value = (stock_purchase_value / total_purchase_value) * total_value
            
            if stock_info.cap_classification == 'small':
                small_cap_value += stock_current_value
            else:
                large_cap_value += stock_current_value
    
    if total_value == 0:
        return 0.0, 0.0
    
    small_cap_percent = (small_cap_value / total_value) * 100
    large_cap_percent = (large_cap_value / total_value) * 100
    
    return round(small_cap_percent, 2), round(large_cap_percent, 2)

def get_real_stock_price(ticker):
    """Get real stock price using Alpha Vantage API"""
    try:
        # Import from the production app location
        import sys
        sys.path.append('/var/task')
        from api.index import get_stock_data
        
        stock_data = get_stock_data(ticker)
        if stock_data and stock_data.get('price'):
            return stock_data['price']
    except ImportError:
        try:
            # Fallback to local app import
            from app import get_stock_data
            stock_data = get_stock_data(ticker)
            if stock_data and stock_data.get('price'):
                return stock_data['price']
        except Exception as e:
            current_app.logger.error(f"Could not import get_stock_data: {str(e)}")
    except Exception as e:
        current_app.logger.error(f"Error getting stock data for {ticker}: {str(e)}")
    
    # If API fails, return None to indicate failure
    current_app.logger.error(f"Could not get real price for {ticker}")
    return None

def calculate_performance_metrics(user_id, period):
    """
    Calculate performance metrics using existing portfolio snapshots - no API calls needed
    Returns performance percentage
    """
    from datetime import datetime, date, timedelta
    
    try:
        # Get the most recent snapshot for current value
        latest_snapshot = PortfolioSnapshot.query.filter_by(user_id=user_id)\
            .order_by(PortfolioSnapshot.date.desc()).first()
        
        if not latest_snapshot:
            return 0.0
        
        current_value = latest_snapshot.total_value
        
        # Calculate start date based on period
        end_date = latest_snapshot.date
        
        if period == '1D':
            start_date = end_date - timedelta(days=1)
        elif period == '5D':
            start_date = end_date - timedelta(days=5)
        elif period == '3M':
            start_date = end_date - timedelta(days=90)
        elif period == 'YTD':
            start_date = date(end_date.year, 1, 1)
        elif period == '1Y':
            start_date = end_date - timedelta(days=365)
        elif period == '5Y':
            start_date = end_date - timedelta(days=1825)
        elif period == 'MAX':
            # Find the earliest snapshot
            earliest_snapshot = PortfolioSnapshot.query.filter_by(user_id=user_id)\
                .order_by(PortfolioSnapshot.date.asc()).first()
            if earliest_snapshot:
                start_date = earliest_snapshot.date
            else:
                return 0.0
        else:
            return 0.0
        
        # Get snapshot closest to start date
        start_snapshot = PortfolioSnapshot.query.filter_by(user_id=user_id)\
            .filter(PortfolioSnapshot.date >= start_date)\
            .order_by(PortfolioSnapshot.date.asc()).first()
        
        if not start_snapshot:
            return 0.0
        
        start_value = start_snapshot.total_value
        
        if start_value > 0:
            return ((current_value - start_value) / start_value) * 100
        else:
            return 0.0
                
    except Exception as e:
        current_app.logger.error(f"Error calculating performance for user {user_id}, period {period}: {str(e)}")
        return 0.0

def update_leaderboard_entry(user_id, period):
    """
    Update or create leaderboard entry for user and period
    """
    # Get or create leaderboard entry
    entry = LeaderboardEntry.query.filter_by(user_id=user_id, period=period).first()
    if not entry:
        entry = LeaderboardEntry(user_id=user_id, period=period)
        db.session.add(entry)
    
    # Calculate metrics
    performance_percent = calculate_performance_metrics(user_id, period)
    small_cap_percent, large_cap_percent = calculate_portfolio_cap_percentages(user_id)
    
    # Get portfolio value from latest snapshot - no API calls needed
    latest_snapshot = PortfolioSnapshot.query.filter_by(user_id=user_id)\
        .order_by(PortfolioSnapshot.date.desc()).first()
    
    portfolio_value = latest_snapshot.total_value if latest_snapshot else 0.0
    
    # Calculate average trades per week (last 4 weeks)
    from subscription_utils import get_user_avg_trades_per_day
    avg_trades_per_day = get_user_avg_trades_per_day(user_id, 28)  # 4 weeks
    avg_trades_per_week = avg_trades_per_day * 7
    
    # Update entry
    entry.performance_percent = performance_percent
    entry.small_cap_percent = small_cap_percent
    entry.large_cap_percent = large_cap_percent
    entry.avg_trades_per_week = round(avg_trades_per_week, 2)
    entry.portfolio_value = round(portfolio_value, 2)
    entry.calculated_at = datetime.now()
    
    db.session.commit()
    return entry

def get_leaderboard_data(period='YTD', limit=50):
    """
    Get cached leaderboard data from LeaderboardCache table
    Returns pre-calculated leaderboard data updated at market close
    """
    import json
    from models import LeaderboardCache
    
    # Try to get cached data first
    cache_entry = LeaderboardCache.query.filter_by(period=period).first()
    
    if cache_entry:
        # Return cached data
        cached_data = json.loads(cache_entry.leaderboard_data)
        return cached_data[:limit]
    
    # Fallback: calculate on-demand if no cache exists
    return calculate_leaderboard_data(period, limit)

def calculate_leaderboard_data(period='YTD', limit=50):
    """
    Calculate leaderboard data directly from portfolio snapshots
    Used for cache generation and fallback
    """
    from datetime import datetime, date, timedelta
    
    # Calculate date range for the period
    today = date.today()
    
    if period == '1D':
        start_date = today - timedelta(days=1)
    elif period == '5D':
        start_date = today - timedelta(days=5)
    elif period == '3M':
        start_date = today - timedelta(days=90)
    elif period == 'YTD':
        start_date = date(today.year, 1, 1)
    elif period == '1Y':
        start_date = today - timedelta(days=365)
    elif period == '5Y':
        start_date = today - timedelta(days=1825)
    elif period == 'MAX':
        start_date = date(2020, 1, 1)  # Reasonable start date
    else:
        start_date = date(today.year, 1, 1)  # Default to YTD
    
    # Get all users with portfolio snapshots
    users = User.query.all()
    leaderboard_data = []
    
    for user in users:
        # Get latest snapshot for current value
        latest_snapshot = PortfolioSnapshot.query.filter_by(user_id=user.id)\
            .order_by(PortfolioSnapshot.date.desc()).first()
        
        if not latest_snapshot:
            continue
            
        # Get snapshot closest to start date
        start_snapshot = PortfolioSnapshot.query.filter_by(user_id=user.id)\
            .filter(PortfolioSnapshot.date >= start_date)\
            .order_by(PortfolioSnapshot.date.asc()).first()
        
        if not start_snapshot:
            continue
        
        # Calculate performance
        current_value = latest_snapshot.total_value
        start_value = start_snapshot.total_value
        
        if start_value > 0:
            performance_percent = ((current_value - start_value) / start_value) * 100
        else:
            performance_percent = 0.0
        
        # Calculate market cap percentages using existing stock info
        small_cap_percent, large_cap_percent = calculate_portfolio_cap_percentages(user.id)
        
        leaderboard_data.append({
            'user_id': user.id,
            'username': user.username,
            'performance_percent': round(performance_percent, 2),
            'small_cap_percent': small_cap_percent,
            'large_cap_percent': large_cap_percent,
            'portfolio_value': round(current_value, 2),
            'subscription_price': user.subscription_price,
            'calculated_at': datetime.now().isoformat()
        })
    
    # Sort by performance and limit results
    leaderboard_data.sort(key=lambda x: x['performance_percent'], reverse=True)
    return leaderboard_data[:limit]

def update_leaderboard_cache():
    """
    Update cached leaderboard data for all periods
    Called at market close to pre-generate leaderboard data
    """
    import json
    from datetime import datetime
    from models import db, LeaderboardCache
    
    periods = ['1D', '5D', '3M', 'YTD', '1Y', '5Y', 'MAX']
    updated_count = 0
    
    for period in periods:
        try:
            # Calculate fresh leaderboard data
            leaderboard_data = calculate_leaderboard_data(period, 100)  # Cache top 100
            
            # Update or create cache entry
            cache_entry = LeaderboardCache.query.filter_by(period=period).first()
            if cache_entry:
                cache_entry.leaderboard_data = json.dumps(leaderboard_data)
                cache_entry.generated_at = datetime.now()
            else:
                cache_entry = LeaderboardCache(
                    period=period,
                    leaderboard_data=json.dumps(leaderboard_data),
                    generated_at=datetime.now()
                )
                db.session.add(cache_entry)
            
            updated_count += 1
            
        except Exception as e:
            print(f"Error updating leaderboard cache for period {period}: {str(e)}")
            continue
    
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        print(f"Error committing leaderboard cache updates: {str(e)}")
        return 0
    
    return updated_count

def update_all_user_leaderboards():
    """
    Update leaderboard entries for all users across all periods
    This would typically be run as a scheduled job
    """
    periods = ['1D', '5D', '3M', 'YTD', '1Y', '5Y', 'MAX']
    users = User.query.all()
    
    updated_count = 0
    for user in users:
        for period in periods:
            update_leaderboard_entry(user.id, period)
            updated_count += 1
    
    current_app.logger.info(f"Updated {updated_count} leaderboard entries")
    return updated_count
