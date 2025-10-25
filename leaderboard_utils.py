"""
Leaderboard utilities for calculating performance metrics and market cap classifications
"""
from datetime import datetime, date, timedelta
from models import db, User, Stock, StockInfo, LeaderboardEntry, PortfolioSnapshot
from flask import current_app
import requests
import os
import logging

logger = logging.getLogger(__name__)

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
            
            # NOTE: Do NOT commit here - let caller handle transaction
            # This is called during market close cron atomicity must be preserved
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
    
    # NOTE: Do NOT commit here - let caller handle transaction
    # This is called during market close cron - atomicity must be preserved
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
        
        if total_purchase_value > 0:
            # Calculate proportional value based on purchase weight
            stock_purchase_value = stock.quantity * stock.purchase_price
            stock_current_value = (stock_purchase_value / total_purchase_value) * total_value
            
            if stock_info:
                # Use dynamic market cap classification if available
                cap_category = stock_info.get_market_cap_category() if stock_info.market_cap else stock_info.cap_classification
                
                if cap_category in ['small', 'mid']:
                    small_cap_value += stock_current_value
                else:
                    # Default to large cap for: large, mega, ETFs, mutual funds, and unknown classifications
                    large_cap_value += stock_current_value
            else:
                # No StockInfo record - default to large cap (common for ETFs, mutual funds)
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
    
    # NOTE: Do NOT commit here - let caller handle transaction
    # This function is LEGACY (replaced by update_leaderboard_cache using LeaderboardCache)
    # But if it's still called, it should not break atomic transactions
    return entry

def get_leaderboard_data(period='YTD', limit=20, category='all'):
    """
    Get cached leaderboard data from LeaderboardCache table with chart data
    Returns pre-calculated leaderboard data updated at market close
    """
    import json
    from models import LeaderboardCache, UserPortfolioChartCache
    
    # Create cache key for period + category
    cache_key = f"{period}_{category}"
    
    # Try to get cached data first
    cache_entry = LeaderboardCache.query.filter_by(period=cache_key).first()
    
    if cache_entry:
        # Return cached data with chart data included
        cached_data = json.loads(cache_entry.leaderboard_data)
        
        # Add chart data for each user if available
        for entry in cached_data[:limit]:
            chart_cache = UserPortfolioChartCache.query.filter_by(
                user_id=entry['user_id'], period=period.split('_')[0]  # Use base period for chart lookup
            ).first()
            
            if chart_cache:
                entry['chart_data'] = json.loads(chart_cache.chart_data)
            else:
                entry['chart_data'] = None
        
        return cached_data[:limit]
    
    # Fallback: calculate on-demand if no cache exists
    return calculate_leaderboard_data(period, limit, category)

def get_user_chart_data(user_id, period):
    """
    Get cached chart data for a specific user and period with staleness checks and live fallback
    """
    import json
    import logging
    from datetime import datetime, timedelta
    from models import UserPortfolioChartCache, db
    
    logger = logging.getLogger(__name__)
    
    chart_cache = UserPortfolioChartCache.query.filter_by(
        user_id=user_id, period=period
    ).first()
    
    # PHASE 3: Cache staleness detection
    if chart_cache:
        cache_age = datetime.now() - chart_cache.generated_at
        
        # Define staleness thresholds by period
        staleness_thresholds = {
            '1D': timedelta(minutes=15),    # 15 minutes for intraday
            '5D': timedelta(hours=1),       # 1 hour for short-term
            '1M': timedelta(hours=4),       # 4 hours for medium-term
            '3M': timedelta(hours=12),      # 12 hours for longer-term
            'YTD': timedelta(days=1),       # 1 day for year-to-date
            '1Y': timedelta(days=1),        # 1 day for annual
            '5Y': timedelta(days=7),        # 1 week for long-term
            'MAX': timedelta(days=7)        # 1 week for maximum
        }
        
        threshold = staleness_thresholds.get(period, timedelta(hours=1))
        
        if cache_age <= threshold:
            # Cache is fresh, use it
            try:
                return json.loads(chart_cache.chart_data)
            except (json.JSONDecodeError, TypeError) as e:
                logger.warning(f"Corrupted chart cache for user {user_id}, period {period}: {e}")
                # Fall through to regeneration
        else:
            logger.info(f"Chart cache stale for user {user_id}, period {period} (age: {cache_age})")
            # Fall through to regeneration
    
    # LIVE FALLBACK: Generate fresh chart data
    logger.info(f"Generating fresh chart data for user {user_id}, period {period}")
    fresh_data = generate_user_portfolio_chart(user_id, period)
    
    if fresh_data:
        # Update cache with fresh data
        try:
            if chart_cache:
                chart_cache.chart_data = json.dumps(fresh_data)
                chart_cache.generated_at = datetime.now()
            else:
                chart_cache = UserPortfolioChartCache(
                    user_id=user_id,
                    period=period,
                    chart_data=json.dumps(fresh_data),
                    generated_at=datetime.now()
                )
                db.session.add(chart_cache)
            
            # NOTE: Do NOT commit here - let the market close cron handle atomic commit
            # Committing mid-transaction breaks atomicity and can cause data loss
            logger.info(f"Updated chart cache for user {user_id}, period {period}")
        except Exception as e:
            logger.error(f"Failed to update chart cache: {e}")
            # NOTE: Do NOT rollback here - it would wipe user snapshots and S&P 500 data
            # Just log the error and continue - caller decides whether to rollback entire transaction
            import traceback
            logger.error(f"Chart cache update error traceback: {traceback.format_exc()}")
    
    return fresh_data

def get_last_market_day():
    """Get the last market day (Monday-Friday, excluding weekends)
    
    IMPORTANT: Uses Eastern Time to avoid timezone mismatches.
    Vercel runs in UTC, so we must explicitly use ET for market dates.
    """
    from datetime import date, timedelta
    from zoneinfo import ZoneInfo
    from datetime import datetime
    
    # CRITICAL: Use Eastern Time, not UTC
    MARKET_TZ = ZoneInfo('America/New_York')
    today = datetime.now(MARKET_TZ).date()
    
    # If it's Saturday (5) or Sunday (6), go back to Friday
    if today.weekday() == 5:  # Saturday
        return today - timedelta(days=1)  # Friday
    elif today.weekday() == 6:  # Sunday
        return today - timedelta(days=2)  # Friday
    else:
        return today  # Monday-Friday

def calculate_leaderboard_data(period='YTD', limit=20, category='all'):
    """
    Calculate leaderboard data using CACHED performance from UserPortfolioChartCache
    This ensures leaderboard shows EXACTLY the same performance as user's dashboard
    
    Args:
        period: Time period for performance calculation
        limit: Number of top users to return
        category: 'all', 'small_cap', or 'large_cap' for filtering
    """
    from datetime import datetime, date, timedelta
    import json
    from models import UserPortfolioChartCache
    
    # Get today's date for calculating recent trades
    today = get_last_market_day()
    
    # Get all users
    users = User.query.all()
    leaderboard_data = []
    
    for user in users:
        # Get latest snapshot to verify user has data
        latest_snapshot = PortfolioSnapshot.query.filter_by(user_id=user.id)\
            .order_by(PortfolioSnapshot.date.desc()).first()
        
        if not latest_snapshot:
            continue
        
        # Get performance from UserPortfolioChartCache (SAME SOURCE AS DASHBOARD)
        chart_cache = UserPortfolioChartCache.query.filter_by(
            user_id=user.id, 
            period=period
        ).first()
        
        if not chart_cache:
            # No cached data for this period, skip user
            continue
        
        try:
            # Extract performance from cached chart data (same format as dashboard)
            cached_data = json.loads(chart_cache.chart_data)
            datasets = cached_data.get('datasets', [])
            
            if not datasets or len(datasets) == 0:
                continue
            
            # Portfolio performance is the last value in the first dataset
            portfolio_dataset = datasets[0].get('data', [])
            if not portfolio_dataset:
                continue
            
            # This is the EXACT same value shown on the user's dashboard
            performance_percent = portfolio_dataset[-1] if portfolio_dataset else 0.0
            
        except (json.JSONDecodeError, KeyError, IndexError) as e:
            logger.warning(f"Error parsing chart cache for user {user.id}: {e}")
            continue
        
        # Calculate market cap percentages using existing stock info
        small_cap_percent, large_cap_percent = calculate_portfolio_cap_percentages(user.id)
        
        # Apply category filter
        if category == 'small_cap' and small_cap_percent < 60:  # Must be 60%+ small cap focused
            continue
        elif category == 'large_cap' and large_cap_percent < 60:  # Must be 60%+ large cap focused
            continue
        
        # Calculate subscriber count
        from models import Subscription
        subscriber_count = Subscription.query.filter_by(
            subscribed_to_id=user.id, 
            status='active'
        ).count()
        
        # Calculate average trades per day (last 30 days)
        from models import Transaction
        thirty_days_ago = today - timedelta(days=30)
        recent_trades = Transaction.query.filter(
            Transaction.user_id == user.id,
            Transaction.timestamp >= thirty_days_ago
        ).count()
        avg_trades_per_day = round(recent_trades / 30, 1)
        
        # Convert to trades per week for display
        avg_trades_per_week = round(avg_trades_per_day * 7, 1)
        
        # Get current portfolio value from latest snapshot
        current_value = latest_snapshot.total_value if latest_snapshot else 0.0
        
        # Ensure all numeric values are properly typed - only include users with real data
        if current_value is None or performance_percent is None:
            continue  # Skip users without real portfolio data
            
        portfolio_value = float(current_value)
        performance_percent = float(performance_percent)
        small_cap_percent = float(small_cap_percent) if small_cap_percent is not None else 0.0
        large_cap_percent = float(large_cap_percent) if large_cap_percent is not None else 0.0
        subscription_price = float(user.subscription_price) if user.subscription_price is not None else 4.0
        
        leaderboard_data.append({
            'user_id': user.id,
            'username': user.username,
            'performance_percent': round(performance_percent, 2),
            'small_cap_percent': round(small_cap_percent, 2),
            'large_cap_percent': round(large_cap_percent, 2),
            'portfolio_value': round(portfolio_value, 2),
            'subscription_price': subscription_price,
            'subscriber_count': subscriber_count,
            'avg_trades_per_day': avg_trades_per_day,
            'avg_trades_per_week': avg_trades_per_week,
            'calculated_at': datetime.now().isoformat(),
            'category': category
        })
    
    # Sort by performance and limit results
    leaderboard_data.sort(key=lambda x: x['performance_percent'], reverse=True)
    return leaderboard_data[:limit]

def generate_user_portfolio_chart(user_id, period):
    """
    Generate portfolio chart data for a specific user and period
    Returns chart data in format compatible with Chart.js
    
    IMPORTANT: Uses Eastern Time to avoid UTC/ET date mismatches.
    """
    import json
    from datetime import datetime, date, timedelta
    from portfolio_performance import PortfolioPerformanceCalculator
    from zoneinfo import ZoneInfo
    
    try:
        # CRITICAL: Use Eastern Time for all date operations
        MARKET_TZ = ZoneInfo('America/New_York')
        today = datetime.now(MARKET_TZ).date()
        
        if period == '1D':
            # For 1D charts, use intraday snapshots with proper time formatting
            from models import PortfolioSnapshotIntraday
            from sqlalchemy import func, and_, cast, Date
            
            # CRITICAL: Query intraday snapshots using ET date extraction
            # Timestamps are TZ-aware (ET), so we extract the date portion in ET
            intraday_snapshots = PortfolioSnapshotIntraday.query.filter(
                and_(
                    PortfolioSnapshotIntraday.user_id == user_id,
                    # Cast timestamp to date for comparison (timestamp is already in ET)
                    cast(PortfolioSnapshotIntraday.timestamp, Date) == today
                )
            ).order_by(PortfolioSnapshotIntraday.timestamp.asc()).all()
            
            logger.info(f"Found {len(intraday_snapshots)} intraday snapshots for user {user_id} on {today} (ET)")
            
            if not intraday_snapshots:
                logger.warning(f"No intraday snapshots found for user {user_id} on {today} (ET)")
                # Fallback to daily snapshot if no intraday data
                daily_snapshot = PortfolioSnapshot.query.filter_by(
                    user_id=user_id, 
                    date=today
                ).first()
                
                if daily_snapshot:
                    logger.info(f"Using daily snapshot fallback for user {user_id}")
                    chart_data = {
                        'labels': [today.strftime('%Y-%m-%d')],
                        'datasets': [{
                            'label': 'Portfolio Value',
                            'data': [float(daily_snapshot.total_value)],
                            'borderColor': 'rgb(75, 192, 192)',
                            'backgroundColor': 'rgba(75, 192, 192, 0.2)',
                            'tension': 0.1
                        }],
                        'period': period,
                        'user_id': user_id,
                        'generated_at': datetime.now(MARKET_TZ).isoformat()
                    }
                    return chart_data
                else:
                    logger.warning(f"No daily snapshot found either for user {user_id} on {today} (ET)")
                    return None
            
            # Format intraday chart data with proper time labels (convert to ET)
            # Timestamps are already TZ-aware in ET, just format them
            labels = []
            for snapshot in intraday_snapshots:
                # Ensure timestamp is in ET
                ts_et = snapshot.timestamp.astimezone(MARKET_TZ) if snapshot.timestamp.tzinfo else snapshot.timestamp.replace(tzinfo=MARKET_TZ)
                labels.append(ts_et.strftime('%H:%M'))
            
            chart_data = {
                'labels': labels,
                'datasets': [{
                    'label': 'Portfolio Value',
                    'data': [float(snapshot.total_value) for snapshot in intraday_snapshots],
                    'borderColor': 'rgb(75, 192, 192)',
                    'backgroundColor': 'rgba(75, 192, 192, 0.2)',
                    'tension': 0.1
                }],
                'period': period,
                'user_id': user_id,
                'generated_at': datetime.now().isoformat()
            }
            return chart_data
            
        else:
            # For multi-day periods, use daily snapshots
            if period == '5D':
                start_date = today - timedelta(days=7)  # Get more days to ensure 5 business days
            elif period == '3M':
                start_date = today - timedelta(days=90)
            elif period == 'YTD':
                start_date = date(today.year, 1, 1)
            elif period == '1Y':
                start_date = today - timedelta(days=365)
            elif period == '5Y':
                start_date = today - timedelta(days=1825)
            elif period == 'MAX':
                start_date = date(2020, 1, 1)
            else:
                start_date = date(today.year, 1, 1)
            
            # Get portfolio snapshots for the period
            snapshots = PortfolioSnapshot.query.filter_by(user_id=user_id)\
                .filter(PortfolioSnapshot.date >= start_date)\
                .order_by(PortfolioSnapshot.date.asc()).all()
            
            if not snapshots:
                return None
            
            # Format chart data with proper date labels
            if period == '5D':
                # For 5D, show abbreviated dates (MM/DD)
                labels = [snapshot.date.strftime('%m/%d') for snapshot in snapshots]
            else:
                # For longer periods, show full dates (YYYY-MM-DD)
                labels = [snapshot.date.strftime('%Y-%m-%d') for snapshot in snapshots]
            
            # Fetch S&P 500 benchmark data for the same period
            from models import MarketData
            sp500_data = MarketData.query.filter_by(ticker='SPY_SP500')\
                .filter(MarketData.date >= start_date)\
                .filter(MarketData.date <= today)\
                .order_by(MarketData.date.asc()).all()
            
            # Create S&P 500 performance array aligned with portfolio dates
            sp500_performance = {
                'dates': [],
                'values': []
            }
            
            if sp500_data:
                # Build a date-to-value map for S&P 500
                sp500_map = {data.date: float(data.close_price) for data in sp500_data}
                
                # Align S&P 500 values with portfolio snapshot dates
                for snapshot in snapshots:
                    snapshot_date = snapshot.date
                    if snapshot_date in sp500_map:
                        sp500_performance['dates'].append(snapshot_date.strftime('%Y-%m-%d'))
                        sp500_performance['values'].append(sp500_map[snapshot_date])
                
                print(f"✅ Generated S&P 500 benchmark data: {len(sp500_performance['dates'])} points for {period}")
            else:
                print(f"⚠️ No S&P 500 data found for period {period} (start: {start_date}, end: {today})")
            
            chart_data = {
                'labels': labels,
                'datasets': [{
                    'label': 'Portfolio Value',
                    'data': [float(snapshot.total_value) for snapshot in snapshots],
                    'borderColor': 'rgb(75, 192, 192)',
                    'backgroundColor': 'rgba(75, 192, 192, 0.2)',
                    'tension': 0.1
                }],
                'sp500_performance': sp500_performance,  # ADD S&P 500 BENCHMARK!
                'period': period,
                'user_id': user_id,
                'generated_at': datetime.now().isoformat()
            }
        
        return chart_data
        
    except Exception as e:
        # Fixed: Import logging at module level or use print for errors
        print(f"Error generating chart for user {user_id}, period {period}: {str(e)}")
        return None

def update_leaderboard_cache(periods=None):
    """
    Update cached leaderboard data for specified periods and categories, pre-generate charts for top users
    Called at market close to pre-generate leaderboard data, charts, and HTML
    
    Args:
        periods: List of periods to update (e.g., ['7D', '1D', '5D']). If None, updates all periods.
    """
    import json
    from datetime import datetime
    from models import db, LeaderboardCache, UserPortfolioChartCache
    from flask import render_template
    
    # Use provided periods or default to all periods
    if periods is None:
        periods = ['1D', '5D', '1M', '3M', 'YTD', '1Y', '5Y', 'MAX']
    
    categories = ['all', 'small_cap', 'large_cap']
    updated_count = 0
    charts_generated = 0
    
    # Track all users who make any leaderboard
    leaderboard_users = set()
    
    for period in periods:
        for category in categories:
            try:
                print(f"Processing leaderboard cache for {period}_{category}...")
                
                # Calculate fresh leaderboard data for this period and category
                leaderboard_data = calculate_leaderboard_data(period, 20, category)  # Top 20 for leaderboard
                print(f"  Calculated {len(leaderboard_data)} entries for {period}_{category}")
                
                if not leaderboard_data:
                    print(f"  ⚠ No leaderboard data for {period}_{category} - skipping cache update")
                    continue
                
                # Collect user IDs who made this leaderboard
                for entry in leaderboard_data:
                    leaderboard_users.add(entry['user_id'])
                
                # Create unique cache key for period + category
                cache_key = f"{period}_{category}"
                
                # Update or create cache entry
                # Pre-render HTML for maximum performance (authenticated + anonymous versions)
                auth_html = None
                anon_html = None
                
                try:
                    from flask import current_app
                    from werkzeug.local import LocalProxy
                    
                    # Create mock authenticated user for rendering
                    class MockAuthUser:
                        is_authenticated = True
                        username = "authenticated_user"
                    
                    with current_app.app_context():
                        # Render AUTHENTICATED version (with Dashboard, Logout menu)
                        # We'll temporarily set current_user context
                        auth_html = render_template('leaderboard.html',
                            leaderboard_data=leaderboard_data,
                            current_period=period,
                            current_category=category,
                            periods=['1D', '5D', '1M', '3M', 'YTD', '1Y', '5Y', 'MAX'],
                            categories=[
                                ('all', 'All Portfolios'),
                                ('small_cap', 'Small Cap Focus'),
                                ('large_cap', 'Large Cap Focus')
                            ],
                            now=datetime.now()
                        )
                        
                        # GROK-RECOMMENDED: Use HTML comment markers for robust find/replace
                        # Create ANONYMOUS version by replacing auth nav section
                        # This is faster than re-rendering (~0.06ms vs ~200ms)
                        if auth_html:
                            # Replace authenticated nav items with anonymous ones
                            # Pattern: Dashboard, Leaderboard, Explore, Subscriptions, Logout → Leaderboard, Login
                            anon_html = auth_html.replace(
                                '<li class="nav-item">\n                        <a class="nav-link" href="/dashboard">Dashboard</a>\n                    </li>',
                                ''
                            ).replace(
                                '<li class="nav-item">\n                        <a class="nav-link" href="/explore">Explore</a>\n                    </li>',
                                ''
                            ).replace(
                                '<li class="nav-item">\n                        <a class="nav-link" href="/subscriptions">Subscriptions</a>\n                    </li>',
                                ''
                            ).replace(
                                '<li class="nav-item">\n                        <a class="nav-link" href="/logout">Logout</a>\n                    </li>',
                                '<li class="nav-item">\n                        <a class="nav-link" href="/login">Login</a>\n                    </li>'
                            )
                        
                except Exception as e:
                    print(f"  Warning: HTML pre-rendering failed for {cache_key}: {str(e)}")
                    import traceback
                    print(f"  Traceback: {traceback.format_exc()}")
                
                # Store BOTH versions with different cache keys
                # Authenticated version: {period}_{category}_auth
                auth_cache_key = f"{cache_key}_auth"
                auth_cache = LeaderboardCache.query.filter_by(period=auth_cache_key).first()
                if auth_cache:
                    auth_cache.leaderboard_data = json.dumps(leaderboard_data)
                    auth_cache.rendered_html = auth_html
                    auth_cache.generated_at = datetime.now()
                else:
                    auth_cache = LeaderboardCache(
                        period=auth_cache_key,
                        leaderboard_data=json.dumps(leaderboard_data),
                        rendered_html=auth_html,
                        generated_at=datetime.now()
                    )
                    db.session.add(auth_cache)
                
                # Anonymous version: {period}_{category}_anon
                anon_cache_key = f"{cache_key}_anon"
                anon_cache = LeaderboardCache.query.filter_by(period=anon_cache_key).first()
                if anon_cache:
                    anon_cache.leaderboard_data = json.dumps(leaderboard_data)
                    anon_cache.rendered_html = anon_html
                    anon_cache.generated_at = datetime.now()
                else:
                    anon_cache = LeaderboardCache(
                        period=anon_cache_key,
                        leaderboard_data=json.dumps(leaderboard_data),
                        rendered_html=anon_html,
                        generated_at=datetime.now()
                    )
                    db.session.add(anon_cache)
                
                print(f"  ✓ Cache entries prepared for {auth_cache_key} and {anon_cache_key}")
                
                updated_count += 1
                print(f"  ✓ Cache entry prepared for {cache_key} (count: {updated_count})")
                
            except Exception as e:
                print(f"Error updating leaderboard cache for period {period}, category {category}: {str(e)}")
                import traceback
                print(f"Full traceback: {traceback.format_exc()}")
                # NOTE: Do NOT rollback - let caller handle transaction
                # Just skip this period/category and continue with others
                print(f"Skipping period {period}, category {category} due to error")
                continue
    
    # Generate portfolio charts for ALL users (not just leaderboard users)
    # Use generate_chart_from_snapshots() which includes intraday data for 1D/5D and S&P 500 benchmark
    from models import User
    all_users = User.query.all()
    
    for user in all_users:
        for period in periods:
            try:
                # Generate chart data for this user and period using updated function
                chart_data = generate_chart_from_snapshots(user.id, period)
                
                if chart_data:
                    # Update or create chart cache entry
                    chart_cache = UserPortfolioChartCache.query.filter_by(
                        user_id=user.id, period=period
                    ).first()
                    
                    if chart_cache:
                        chart_cache.chart_data = json.dumps(chart_data)
                        chart_cache.generated_at = datetime.now()
                    else:
                        chart_cache = UserPortfolioChartCache(
                            user_id=user.id,
                            period=period,
                            chart_data=json.dumps(chart_data),
                            generated_at=datetime.now()
                        )
                        db.session.add(chart_cache)
                    
                    charts_generated += 1
                    print(f"✓ Generated chart cache for user {user.id}, period {period}")
                else:
                    print(f"⚠ No chart data generated for user {user.id}, period {period} - insufficient snapshots")
                    
            except Exception as e:
                print(f"Error generating chart cache for user {user.id}, period {period}: {str(e)}")
                continue
    
    print(f"\n=== LEADERBOARD CACHE UPDATE COMPLETE ===")
    print(f"Updated {updated_count} leaderboard cache entries")
    print(f"Generated {charts_generated} chart cache entries")
    print(f"Leaderboard users: {len(leaderboard_users)} - {list(leaderboard_users)}")
    
    # Check what's in the session before commit
    print(f"Session new objects: {len(db.session.new)}")
    print(f"Session dirty objects: {len(db.session.dirty)}")
    for obj in list(db.session.new)[:3]:  # Show first 3 new objects
        print(f"New object: {obj}")
    
    # NOTE: Do NOT commit here - let caller handle transaction
    # This allows atomic commits with other operations (snapshots, S&P 500 data)
    print(f"Leaderboard cache prepared: {updated_count} periods, {charts_generated} charts generated for {len(leaderboard_users)} users")
    print(f"Added {len(db.session.new)} new objects to session - caller must commit")
    
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

def generate_chart_from_snapshots(user_id, period):
    """Generate chart data from snapshots using same logic as leaderboards"""
    from datetime import datetime, date, timedelta
    import json
    from models import PortfolioSnapshotIntraday, MarketData
    from sqlalchemy import func, cast, Date
    
    # Use same date calculation logic as calculate_leaderboard_data
    today = get_last_market_day()
    
    # For 1D and 5D, use intraday snapshots with time labels
    if period in ['1D', '5D']:
        from zoneinfo import ZoneInfo
        from datetime import time as dt_time
        MARKET_TZ = ZoneInfo('America/New_York')
        
        if period == '1D':
            start_date = today
            end_date = today
            
            # CRITICAL FIX: Only include market hours (9:30 AM - 4:00 PM ET)
            market_open_time = dt_time(9, 30)  # 9:30 AM
            market_close_time = dt_time(16, 0)  # 4:00 PM
            
            # Get all intraday snapshots for today
            all_snapshots = PortfolioSnapshotIntraday.query.filter(
                PortfolioSnapshotIntraday.user_id == user_id,
                cast(func.timezone('America/New_York', PortfolioSnapshotIntraday.timestamp), Date) == start_date
            ).order_by(PortfolioSnapshotIntraday.timestamp).all()
            
            # Filter to only include market hours
            intraday_snapshots = []
            for snapshot in all_snapshots:
                et_timestamp = snapshot.timestamp.astimezone(MARKET_TZ)
                snapshot_time = et_timestamp.time()
                if market_open_time <= snapshot_time <= market_close_time:
                    intraday_snapshots.append(snapshot)
            
        else:  # 5D
            # Get last 5 business days (not including today if after hours)
            business_days_back = 0
            check_date = today
            target_days = 5
            
            # If it's after market close today, include today in the 5 days
            # Otherwise start from yesterday
            current_time = datetime.now(MARKET_TZ)
            if current_time.time() >= dt_time(16, 0):  # After 4 PM
                # Include today as one of the 5 days
                pass
            else:
                # Start from yesterday
                check_date = check_date - timedelta(days=1)
                target_days = 4  # Only need 4 more days since today is partial
            
            # Count back to get start date
            while business_days_back < target_days:
                check_date = check_date - timedelta(days=1)
                if check_date.weekday() < 5:  # Monday=0, Friday=4
                    business_days_back += 1
            start_date = check_date
            end_date = today
            
            # Get intraday snapshots for date range
            intraday_snapshots = PortfolioSnapshotIntraday.query.filter(
                PortfolioSnapshotIntraday.user_id == user_id,
                cast(func.timezone('America/New_York', PortfolioSnapshotIntraday.timestamp), Date) >= start_date,
                cast(func.timezone('America/New_York', PortfolioSnapshotIntraday.timestamp), Date) <= end_date
            ).order_by(PortfolioSnapshotIntraday.timestamp).all()
        
        if not intraday_snapshots:
            return None
        
        # Build chart data with formatted time labels
        labels = []
        portfolio_data = []
        first_value = intraday_snapshots[0].total_value
        
        for snapshot in intraday_snapshots:
            # Format label based on period
            et_timestamp = snapshot.timestamp.astimezone(MARKET_TZ)
            if period == '1D':
                # For 1D: "Oct 21 9:30 AM"
                label = et_timestamp.strftime('%b %d %I:%M %p')
            else:  # 5D
                # For 5D: "Oct 21" (date only, but keep all intraday points)
                label = et_timestamp.strftime('%b %d')
            
            labels.append(label)
            
            # Calculate performance percentage
            if first_value > 0:
                performance_pct = ((snapshot.total_value - first_value) / first_value) * 100
            else:
                performance_pct = 0.0
            portfolio_data.append(round(performance_pct, 2))
        
        # Get S&P 500 intraday data
        sp500_data = MarketData.query.filter(
            MarketData.ticker == 'SPY_INTRADAY',
            MarketData.date >= start_date,
            MarketData.date <= end_date,
            MarketData.timestamp.isnot(None)
        ).order_by(MarketData.timestamp).all()
        
        sp500_performance = []
        if sp500_data and len(sp500_data) > 0:
            first_sp500 = sp500_data[0].close_price
            sp500_values = [float(s.close_price) for s in sp500_data]
            
            # Match S&P 500 data to snapshot timestamps
            for snapshot in intraday_snapshots:
                # Find closest S&P 500 value at or before this timestamp
                spy_value = first_sp500
                for spy_point in sp500_data:
                    if spy_point.timestamp <= snapshot.timestamp:
                        spy_value = spy_point.close_price
                    else:
                        break
                
                if first_sp500 > 0:
                    sp500_pct = ((spy_value - first_sp500) / first_sp500) * 100
                else:
                    sp500_pct = 0.0
                sp500_performance.append(round(sp500_pct, 2))
        
    else:
        # For longer periods, use EOD snapshots
        if period == '1M':
            start_date = today - timedelta(days=30)
        elif period == '3M':
            start_date = today - timedelta(days=90)
        elif period == 'YTD':
            start_date = date(today.year, 1, 1)
        elif period == '1Y':
            start_date = today - timedelta(days=365)
        elif period == '5Y':
            start_date = today - timedelta(days=1825)
        elif period == 'MAX':
            start_date = date(2020, 1, 1)
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
        first_value = snapshots[0].total_value
        
        for snapshot in snapshots:
            labels.append(snapshot.date.strftime('%b %d'))
            
            # Calculate performance percentage
            if first_value > 0:
                performance_pct = ((snapshot.total_value - first_value) / first_value) * 100
            else:
                performance_pct = 0.0
            portfolio_data.append(round(performance_pct, 2))
        
        # Get S&P 500 EOD data - MUST align with portfolio snapshot dates!
        from models import MarketData
        sp500_snapshots = MarketData.query.filter(
            MarketData.ticker == 'SPY_SP500',
            MarketData.date >= start_date,
            MarketData.date <= today
        ).order_by(MarketData.date.asc()).all()
        
        sp500_performance = []
        if sp500_snapshots and len(sp500_snapshots) > 0:
            # Build a date-to-value map for S&P 500
            sp500_map = {s.date: float(s.close_price) for s in sp500_snapshots}
            
            # Get first S&P 500 value (from first portfolio snapshot date)
            first_snapshot_date = snapshots[0].date
            start_sp500 = sp500_map.get(first_snapshot_date)
            
            if not start_sp500:
                # If no S&P 500 data for first portfolio date, find closest previous date
                for sp500_record in sp500_snapshots:
                    if sp500_record.date <= first_snapshot_date:
                        start_sp500 = float(sp500_record.close_price)
                    else:
                        break
            
            # CRITICAL: Align S&P 500 performance with portfolio snapshot dates
            # This ensures arrays have same length and values correspond to same dates
            for snapshot in snapshots:
                snapshot_date = snapshot.date
                sp500_value = sp500_map.get(snapshot_date)
                
                if sp500_value and start_sp500 and start_sp500 > 0:
                    sp500_pct = ((sp500_value - start_sp500) / start_sp500) * 100
                    sp500_performance.append(round(sp500_pct, 2))
                elif sp500_performance:
                    # If S&P 500 data missing for this date, repeat last value
                    sp500_performance.append(sp500_performance[-1])
                else:
                    # No data yet, use 0
                    sp500_performance.append(0.0)
    
    # Format as Chart.js compatible data
    # portfolio_data already contains performance percentages calculated above
    chart_data = {
        'labels': labels,
        'datasets': [
            {
                'label': 'Your Portfolio',
                'data': portfolio_data,
                'borderColor': 'rgb(40, 167, 69)',
                'backgroundColor': 'rgba(40, 167, 69, 0.1)',
                'tension': 0.1,
                'fill': False
            }
        ]
    }
    
    # Add S&P 500 dataset if we have data
    if sp500_performance:
        chart_data['datasets'].append({
            'label': 'S&P 500',
            'data': sp500_performance,
            'borderColor': 'rgb(108, 117, 125)',
            'backgroundColor': 'rgba(108, 117, 125, 0.1)',
            'tension': 0.1,
            'fill': False,
            'borderDash': [5, 5]
        })
    
    return chart_data

def update_user_chart_cache(user_id, period):
    """Update chart cache for specific user and period using snapshots"""
    from models import db, UserPortfolioChartCache
    from datetime import datetime
    import json
    
    # Generate fresh chart data from snapshots
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
    
    return True

def get_user_leaderboard_positions(user_id, top_n=20):
    """
    Get a user's leaderboard positions across all time periods (if they're in top N).
    Returns dict of {period: position} for periods where user ranks in top N.
    """
    positions = {}
    periods = ['1D', '5D', '1M', '3M', 'YTD', '1Y']
    
    for period in periods:
        leaderboard_data = get_leaderboard_data(period, limit=top_n)
        
        # Find user's position in this leaderboard
        for idx, entry in enumerate(leaderboard_data, 1):
            if entry.get('user_id') == user_id:
                positions[period] = idx
                break
    
    return positions

def calculate_industry_mix(user_id):
    """
    Calculate industry distribution as percentage of portfolio value
    Returns: {'Technology': 45.2, 'Healthcare': 30.5, ...}
    """
    from models import Stock, StockInfo, PortfolioSnapshot
    
    # Get latest portfolio value
    latest_snapshot = PortfolioSnapshot.query.filter_by(user_id=user_id)\
        .order_by(PortfolioSnapshot.date.desc()).first()
    
    if not latest_snapshot:
        return {}
    
    total_value = latest_snapshot.total_value
    stocks = Stock.query.filter_by(user_id=user_id).all()
    
    if not stocks or total_value == 0:
        return {}
    
    # Calculate industry values
    industry_values = {}
    total_purchase_value = sum(stock.quantity * stock.purchase_price for stock in stocks)
    
    for stock in stocks:
        stock_info = StockInfo.query.filter_by(ticker=stock.ticker.upper()).first()
        
        if total_purchase_value > 0:
            stock_purchase_value = stock.quantity * stock.purchase_price
            stock_current_value = (stock_purchase_value / total_purchase_value) * total_value
            
            # Get industry (default to 'Other' if not available)
            industry = stock_info.industry if stock_info and stock_info.industry else 'Other'
            
            industry_values[industry] = industry_values.get(industry, 0) + stock_current_value
    
    # Convert to percentages
    industry_percentages = {
        industry: round((value / total_value) * 100, 1)
        for industry, value in industry_values.items()
    }
    
    # Sort by percentage (highest first)
    return dict(sorted(industry_percentages.items(), key=lambda x: x[1], reverse=True))

def calculate_user_portfolio_stats(user_id):
    """
    Calculate all portfolio statistics for a user
    Called during market close cron
    Returns dict of stats
    """
    from models import Stock, Transaction, Subscription, StockInfo
    from datetime import datetime, timedelta
    
    stats = {}
    
    # 1. UNIQUE STOCKS COUNT
    stocks = Stock.query.filter_by(user_id=user_id).all()
    stats['unique_stocks_count'] = len(stocks)
    
    # 2. TRADING ACTIVITY
    # Get all transactions
    transactions = Transaction.query.filter_by(user_id=user_id).all()
    stats['total_trades'] = len(transactions)
    
    # Calculate avg trades per week (last 30 days)
    thirty_days_ago = datetime.now() - timedelta(days=30)
    recent_transactions = [t for t in transactions if t.timestamp >= thirty_days_ago]
    avg_trades_per_day = len(recent_transactions) / 30
    stats['avg_trades_per_week'] = round(avg_trades_per_day * 7, 2)
    
    # 3. LARGE CAP %
    small_cap_percent, large_cap_percent = calculate_portfolio_cap_percentages(user_id)
    stats['small_cap_percent'] = small_cap_percent
    stats['large_cap_percent'] = large_cap_percent
    
    # 4. INDUSTRY MIX
    industry_mix = calculate_industry_mix(user_id)
    stats['industry_mix'] = industry_mix
    
    # 5. SUBSCRIBER COUNT
    subscriber_count = Subscription.query.filter_by(
        subscribed_to_id=user_id,
        status='active'
    ).count()
    stats['subscriber_count'] = subscriber_count
    
    stats['last_updated'] = datetime.utcnow()
    
    return stats
