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
    
    # Batch-load all StockInfo records in ONE query (avoids N+1 per-stock queries)
    tickers = [stock.ticker.upper() for stock in stocks]
    all_stock_info = {si.ticker: si for si in StockInfo.query.filter(StockInfo.ticker.in_(tickers)).all()} if tickers else {}
    
    for stock in stocks:
        stock_info = all_stock_info.get(stock.ticker.upper())
        
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
        elif period == '1M':
            start_date = end_date - timedelta(days=30)
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

def get_leaderboard_data(period='YTD', limit=20, category='all', use_auth_suffix=False):
    """
    Get cached leaderboard data from LeaderboardCache table with chart data
    Returns pre-calculated leaderboard data updated at market close
    
    Args:
        period: Time period (1D, 5D, 1M, etc.)
        limit: Max number of entries to return
        category: Portfolio category (all, small_cap, large_cap)
        use_auth_suffix: If True, looks for _auth/_anon suffixed cache keys (used by route)
    """
    import json
    from models import LeaderboardCache, UserPortfolioChartCache
    
    # Create cache key for period + category
    # MODERN FORMAT: period_category_auth or period_category_anon
    # LEGACY FORMAT: period_category (no suffix)
    cache_key = f"{period}_{category}"
    
    # Try all cache key formats: plain, _auth, _anon
    # The backfill writes _auth/_anon suffixed keys, so we must always check those
    cache_entry = LeaderboardCache.query.filter_by(period=cache_key).first()
    if not cache_entry:
        cache_entry = LeaderboardCache.query.filter_by(period=f"{cache_key}_auth").first()
    if not cache_entry:
        cache_entry = LeaderboardCache.query.filter_by(period=f"{cache_key}_anon").first()
    
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
        # Update cache with fresh data and commit immediately (on-demand generation)
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
            
            db.session.commit()
            logger.info(f"Updated chart cache for user {user_id}, period {period}")
        except Exception as e:
            logger.error(f"Failed to update chart cache: {e}")
            try:
                db.session.rollback()
            except Exception:
                pass
    
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

def _compute_all_user_metrics(period='YTD'):
    """
    Compute performance metrics for ALL users in a single pass.
    
    This is the O(n) single-pass core: loops users once, computes performance,
    cap percentages, subscriber count, and trade frequency for each.
    Returns the full list (unfiltered, unsorted) so callers can filter by category.
    
    ELIGIBILITY FILTER: Users must have been active for the ENTIRE leaderboard
    period to be included. e.g., 3M leaderboard requires 90+ days of activity.
    This prevents artificially high performance from short-lived accounts.
    
    Called once per period by update_leaderboard_cache, then filtered 3x by category.
    """
    from datetime import datetime, date, timedelta
    from performance_calculator import calculate_portfolio_performance, get_period_dates, batch_get_leaderboard_eligibility
    from models import Subscription, Transaction
    import time as _time
    
    _t0 = _time.time()
    today = get_last_market_day()
    thirty_days_ago = today - timedelta(days=30)
    
    # Clean session before starting
    try:
        db.session.rollback()
    except Exception:
        pass
    
    users = User.query.all()
    all_metrics = []
    skipped = []  # Track why users are skipped for diagnostics
    first_error = None
    error_count = 0
    eligibility_skipped = 0
    
    # BATCH eligibility check — single SQL query for ALL users (scales to 10k+)
    try:
        eligibility_map = batch_get_leaderboard_eligibility(period)
        print(f"  Batch eligibility: {len(eligibility_map)} users checked in 1 query")
    except Exception as e:
        logger.warning(f"Batch eligibility check failed: {e}, falling back to no filtering")
        eligibility_map = {}
    
    # ── BATCH pre-fetches: replace per-user queries with bulk loads ──
    from sqlalchemy import func as sqla_func
    from models import UserPortfolioStats, AdminSubscription
    
    # 1) Latest snapshot per user via subquery (efficient at 10k+ scale)
    _latest_snap_map = {}
    try:
        max_dates_sub = db.session.query(
            PortfolioSnapshot.user_id,
            sqla_func.max(PortfolioSnapshot.date).label('max_date')
        ).group_by(PortfolioSnapshot.user_id).subquery()
        
        actual_snaps = PortfolioSnapshot.query.join(
            max_dates_sub,
            (PortfolioSnapshot.user_id == max_dates_sub.c.user_id) &
            (PortfolioSnapshot.date == max_dates_sub.c.max_date)
        ).all()
        _latest_snap_map = {s.user_id: s for s in actual_snaps}
        print(f"  Batch snapshots: {len(_latest_snap_map)} loaded")
    except Exception as e:
        logger.warning(f"Batch snapshot load failed: {e}")
    
    # 2) UserPortfolioStats — cached cap %, subscriber count, trades/wk
    _stats_map = {}
    try:
        all_stats = UserPortfolioStats.query.all()
        _stats_map = {s.user_id: s for s in all_stats}
        print(f"  Batch stats: {len(_stats_map)} loaded")
    except Exception as e:
        logger.warning(f"Batch stats load failed: {e}")
    
    # 3) Subscriber counts (real subscriptions)
    _sub_count_map = {}
    try:
        sub_counts = db.session.query(
            Subscription.subscribed_to_id,
            sqla_func.count(Subscription.id).label('cnt')
        ).filter(Subscription.status == 'active').group_by(Subscription.subscribed_to_id).all()
        _sub_count_map = {uid: cnt for uid, cnt in sub_counts}
    except Exception as e:
        logger.warning(f"Batch subscriber count failed: {e}")
    
    # 4) Admin (gifted) subscriber bonuses
    _admin_bonus_map = {}
    try:
        for asub in AdminSubscription.query.all():
            bonus = asub.bonus_subscriber_count or 0
            if bonus > 0:
                _admin_bonus_map[asub.portfolio_user_id] = bonus
    except Exception as e:
        logger.warning(f"Batch admin sub load failed: {e}")
    
    # 5) Recent trade counts (last 30 days) — single aggregation query
    _trade_count_map = {}
    try:
        trade_counts = db.session.query(
            Transaction.user_id,
            sqla_func.count(Transaction.id).label('cnt')
        ).filter(Transaction.timestamp >= thirty_days_ago).group_by(Transaction.user_id).all()
        _trade_count_map = {uid: cnt for uid, cnt in trade_counts}
    except Exception as e:
        logger.warning(f"Batch trade count failed: {e}")
    
    for user in users:
        # LEADERBOARD ELIGIBILITY CHECK: User must have been active for the full period
        # e.g., 3M leaderboard requires 90+ days of activity
        eligibility = eligibility_map.get(user.id)
        if eligibility and not eligibility['eligible']:
            skipped.append({
                'username': user.username,
                'reason': 'insufficient_activity',
                'days_active': eligibility['days_active'],
                'days_required': eligibility['days_required']
            })
            eligibility_skipped += 1
            continue
        elif not eligibility:
            # User has no snapshots at all — skip
            eligibility_skipped += 1
            continue
        
        # Get latest snapshot from batch-loaded map (no DB query)
        latest_snapshot = _latest_snap_map.get(user.id)
        if not latest_snapshot:
            skipped.append({'username': user.username, 'reason': 'no_snapshots'})
            continue
        
        # Performance calculation (single source of truth)
        try:
            start_date, end_date = get_period_dates(period, user_id=user.id)
            result = calculate_portfolio_performance(
                user.id, start_date, end_date,
                include_chart_data=True, period=period
            )
            if not result:
                skipped.append({'username': user.username, 'reason': 'perf_returned_none', 'dates': f'{start_date} to {end_date}'})
                continue
            
            performance_percent = result.get('portfolio_return', 0.0)
            if performance_percent is None:
                skipped.append({'username': user.username, 'reason': 'portfolio_return_none'})
                continue
            
            # Pre-compute sparkline from chart_data (portfolio % returns)
            # Use ALL points for short periods; evenly sample to ~150 for longer ones.
            # Even sampling preserves shape (unlike [-20:] which clips to tail only).
            chart_pts = result.get('chart_data') or []
            sparkline = []
            if chart_pts:
                all_vals = [round(pt.get('portfolio', 0) or 0, 2) for pt in chart_pts]
                max_sparkline = 150
                if len(all_vals) <= max_sparkline:
                    sparkline = all_vals
                else:
                    step = len(all_vals) / max_sparkline
                    sparkline = [all_vals[int(i * step)] for i in range(max_sparkline - 1)]
                    sparkline.append(all_vals[-1])  # Always include final point
                
        except Exception as e:
            if not first_error:
                first_error = f"Performance calc for user {user.id} period {period}: {e}"
            error_count += 1
            logger.warning(f"Performance calc failed for user {user.id} period {period}: {e}")
            skipped.append({'username': user.username, 'reason': 'exception', 'error': str(e)[:200]})
            try:
                db.session.rollback()
            except Exception:
                pass
            continue
        
        # Cap percentages from batch-loaded UserPortfolioStats (no DB query)
        cached_stats = _stats_map.get(user.id)
        if cached_stats:
            small_cap_percent = cached_stats.small_cap_percent or 0.0
            large_cap_percent = cached_stats.large_cap_percent or 0.0
        else:
            small_cap_percent, large_cap_percent = 0.0, 0.0
        
        # Subscriber count from batch-loaded maps (no DB query)
        subscriber_count = _sub_count_map.get(user.id, 0) + _admin_bonus_map.get(user.id, 0)
        
        # Average trades per week from batch-loaded trade counts (no DB query)
        recent_trades = _trade_count_map.get(user.id, 0)
        avg_trades_per_day = round(recent_trades / 30, 1)
        avg_trades_per_week = round(avg_trades_per_day * 7, 1)
        
        # Portfolio value from latest snapshot
        portfolio_value = float(latest_snapshot.total_value) if latest_snapshot else 0.0
        performance_percent = float(performance_percent)
        small_cap_pct = float(small_cap_percent) if small_cap_percent is not None else 0.0
        large_cap_pct = float(large_cap_percent) if large_cap_percent is not None else 0.0
        subscription_price = float(user.subscription_price) if user.subscription_price is not None else 9.0
        
        all_metrics.append({
            'user_id': user.id,
            'username': user.username,
            'performance_percent': round(performance_percent, 2),
            'sparkline_data': sparkline,
            'small_cap_percent': round(small_cap_pct, 2),
            'large_cap_percent': round(large_cap_pct, 2),
            'portfolio_value': round(portfolio_value, 2),
            'subscription_price': subscription_price,
            'subscriber_count': subscriber_count,
            'avg_trades_per_day': avg_trades_per_day,
            'avg_trades_per_week': avg_trades_per_week,
            'calculated_at': datetime.now().isoformat(),
        })
    
    elapsed = round(_time.time() - _t0, 2)
    print(f"  Computed metrics for {len(all_metrics)}/{len(users)} users in {elapsed}s (eligibility_skipped={eligibility_skipped})")
    if first_error:
        print(f"  \u26a0 FIRST ERROR for {period}: {first_error}")
        print(f"  \u26a0 Total errors: {error_count}/{len(users)} users")
    
    # Attach diagnostics as attribute so callers can inspect
    all_metrics = list(all_metrics)  # Ensure it's a plain list
    _compute_all_user_metrics._last_skipped = skipped
    _compute_all_user_metrics._last_elapsed = elapsed
    
    return all_metrics


def _filter_and_sort(all_metrics, category='all', limit=20):
    """
    Filter precomputed user metrics by category and return top N sorted by performance.
    O(n) filter + O(n log n) sort — no DB queries.
    """
    if category == 'small_cap':
        filtered = [m for m in all_metrics if m['small_cap_percent'] >= 60]
    elif category == 'large_cap':
        filtered = [m for m in all_metrics if m['large_cap_percent'] >= 60]
    else:
        filtered = list(all_metrics)
    
    # Tag with category for backward compatibility
    for entry in filtered:
        entry = {**entry, 'category': category}
    
    filtered.sort(key=lambda x: x['performance_percent'], reverse=True)
    return filtered[:limit]


def calculate_leaderboard_data(period='YTD', limit=20, category='all'):
    """
    Calculate leaderboard data using calculate_portfolio_performance (single source of truth).
    
    LEGACY wrapper — kept for backward compatibility.
    For efficient multi-category builds, use _compute_all_user_metrics + _filter_and_sort.
    """
    all_metrics = _compute_all_user_metrics(period)
    return _filter_and_sort(all_metrics, category, limit)

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
            from models import PortfolioSnapshotIntraday, MarketData
            from sqlalchemy import func, and_, cast, Date
            
            # Try today first, then fall back to last trading day with data
            target_date = today
            intraday_snapshots = []
            for attempt in range(5):  # Check up to 5 days back (covers weekends + holidays)
                intraday_snapshots = PortfolioSnapshotIntraday.query.filter(
                    and_(
                        PortfolioSnapshotIntraday.user_id == user_id,
                        cast(PortfolioSnapshotIntraday.timestamp, Date) == target_date
                    )
                ).order_by(PortfolioSnapshotIntraday.timestamp.asc()).all()
                
                if intraday_snapshots:
                    break
                target_date -= timedelta(days=1)
            
            logger.info(f"Found {len(intraday_snapshots)} intraday snapshots for user {user_id} on {target_date} (ET)")
            
            if not intraday_snapshots:
                logger.warning(f"No intraday snapshots found for user {user_id} in last 5 days")
                return None
            
            # Build percentage-return chart (same format as backfill cache)
            first_value = float(intraday_snapshots[0].total_value)
            labels = []
            portfolio_pcts = []
            from zoneinfo import ZoneInfo as _ZI
            _UTC = _ZI('UTC')
            for snapshot in intraday_snapshots:
                # Timestamps stored in UTC; convert to ET for display
                ts_et = snapshot.timestamp.astimezone(MARKET_TZ) if snapshot.timestamp.tzinfo else snapshot.timestamp.replace(tzinfo=_UTC).astimezone(MARKET_TZ)
                labels.append(ts_et.strftime('%I:%M %p'))
                if first_value > 0:
                    pct = ((float(snapshot.total_value) - first_value) / first_value) * 100
                else:
                    pct = 0.0
                portfolio_pcts.append(round(pct, 2))
            
            # Get S&P 500 intraday data for same date
            sp500_pcts = []
            spy_data = MarketData.query.filter(
                MarketData.ticker == 'SPY_INTRADAY',
                MarketData.date == target_date,
                MarketData.timestamp.isnot(None)
            ).order_by(MarketData.timestamp.asc()).all()
            
            if spy_data:
                spy_base = float(spy_data[0].close_price)
                if spy_base > 0:
                    spy_all = [round(((float(s.close_price) - spy_base) / spy_base) * 100, 2) for s in spy_data]
                    # Resample to match portfolio point count
                    if len(spy_all) >= len(labels):
                        step = max(1, len(spy_all) // max(1, len(labels)))
                        sp500_pcts = [spy_all[i * step] for i in range(len(labels))]
                    else:
                        sp500_pcts = spy_all + [spy_all[-1]] * (len(labels) - len(spy_all))
            
            if not sp500_pcts:
                sp500_pcts = [0.0] * len(labels)
            
            chart_data = {
                'labels': labels,
                'datasets': [
                    {
                        'label': 'Your Portfolio',
                        'data': portfolio_pcts,
                        'borderColor': 'rgb(40, 167, 69)',
                        'backgroundColor': 'rgba(40, 167, 69, 0.1)',
                        'tension': 0.1,
                        'fill': False
                    },
                    {
                        'label': 'S&P 500',
                        'data': sp500_pcts,
                        'borderColor': 'rgb(108, 117, 125)',
                        'backgroundColor': 'rgba(108, 117, 125, 0.1)',
                        'tension': 0.1,
                        'fill': False,
                        'borderDash': [5, 5]
                    }
                ],
                'period': period,
                'user_id': user_id,
                'generated_at': datetime.now().isoformat()
            }
            return chart_data
            
        else:
            # For multi-day periods, use daily snapshots
            if period == '5D':
                start_date = today - timedelta(days=7)  # Get more days to ensure 5 business days
            elif period == '1M':
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
    Update cached leaderboard JSON data for specified periods and categories.
    Called at market close. Charts are NOT pre-generated here — they are generated
    on-demand via get_user_chart_data() when users view them.
    
    OPTIMIZED: Computes user metrics ONCE per period, then filters by category.
    Previous version computed metrics 3x per period (once per category).
    
    Args:
        periods: List of periods to update. If None, updates all periods.
    """
    import json
    import time as _time
    from datetime import datetime
    from models import db, LeaderboardCache
    from sqlalchemy import text
    
    if periods is None:
        periods = ['1D', '5D', '1M', '3M', 'YTD', '1Y']
    
    categories = ['all', 'small_cap', 'large_cap']
    updated_count = 0
    _lb_errors = []
    
    for period in periods:
        _tp = _time.time()
        print(f"\n--- Computing metrics for period {period} ---")
        
        # Compute ALL user metrics ONCE per period
        try:
            try:
                db.session.rollback()
            except Exception:
                pass
            
            all_metrics = _compute_all_user_metrics(period)
        except Exception as e:
            err_msg = f"{period}_compute: {str(e)[:200]}"
            _lb_errors.append(err_msg)
            print(f"Error computing metrics for {period}: {str(e)}")
            import traceback
            print(f"Full traceback: {traceback.format_exc()}")
            try:
                db.session.rollback()
            except Exception:
                pass
            continue
        
        # Filter by category and save to cache (no recomputation)
        for category in categories:
            try:
                leaderboard_data = _filter_and_sort(all_metrics, category, 20)
                print(f"  {period}_{category}: {len(leaderboard_data)} entries")
                
                if not leaderboard_data:
                    print(f"  ⚠ No leaderboard data for {period}_{category} - skipping")
                    continue
                
                cache_key = f"{period}_{category}"
                leaderboard_data_json = json.dumps(leaderboard_data)
                now = datetime.now()
                
                # Store JSON-only cache
                with db.engine.connect() as primary_conn:
                    with primary_conn.begin():
                        select_sql = text("SELECT id FROM leaderboard_cache WHERE period = :period")
                        result = primary_conn.execute(select_sql, {'period': cache_key})
                        existing_id = result.scalar()
                        
                        if existing_id:
                            update_sql = text("""
                                UPDATE leaderboard_cache 
                                SET leaderboard_data = :data, generated_at = :time
                                WHERE id = :id
                            """)
                            primary_conn.execute(update_sql, {
                                'id': existing_id,
                                'data': leaderboard_data_json,
                                'time': now
                            })
                        else:
                            insert_sql = text("""
                                INSERT INTO leaderboard_cache (period, leaderboard_data, generated_at)
                                VALUES (:period, :data, :time)
                            """)
                            primary_conn.execute(insert_sql, {
                                'period': cache_key,
                                'data': leaderboard_data_json,
                                'time': now
                            })
                
                updated_count += 1
                print(f"  ✓ Leaderboard cache saved for {cache_key}")
                
            except Exception as e:
                err_msg = f"{period}_{category}: {str(e)[:200]}"
                _lb_errors.append(err_msg)
                print(f"Error saving leaderboard cache for {period}_{category}: {str(e)}")
                import traceback
                print(f"Full traceback: {traceback.format_exc()}")
                try:
                    db.session.rollback()
                except Exception:
                    pass
                continue
        
        print(f"  Period {period} complete in {round(_time.time() - _tp, 2)}s")
    
    print(f"\n=== LEADERBOARD CACHE UPDATE COMPLETE ===")
    print(f"Updated {updated_count} leaderboard cache entries (JSON only, no chart pre-gen)")
    if _lb_errors:
        print(f"Leaderboard errors: {_lb_errors}")
    
    # Attach errors as attribute so caller can inspect
    update_leaderboard_cache._last_errors = _lb_errors
    
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
    """
    Generate chart data using unified calculator.
    
    This replaces the old snapshot-based logic with the new Modified Dietz calculator
    to ensure consistency across dashboard, leaderboard, and API endpoints.
    """
    from performance_calculator import calculate_portfolio_performance, get_period_dates
    
    try:
        # Get date range for period
        start_date, end_date = get_period_dates(period, user_id=user_id)
        
        # Calculate performance using unified calculator
        result = calculate_portfolio_performance(
            user_id, 
            start_date, 
            end_date, 
            include_chart_data=True,
            period=period
        )
        
        if not result:
            from flask import current_app
            current_app.logger.error(f"calculate_portfolio_performance returned None for user {user_id}, period {period}")
            return None
            
        if not result.get('chart_data'):
            from flask import current_app
            current_app.logger.error(f"No chart_data in result for user {user_id}, period {period}. Result keys: {list(result.keys())}")
            return None
        
        # Transform calculator output (list of points) to Chart.js format
        raw_chart_data = result['chart_data']
        
        # Extract labels and data arrays
        labels = [point['date'] for point in raw_chart_data]
        portfolio_data = [point['portfolio'] for point in raw_chart_data]
        sp500_data = [point['sp500'] for point in raw_chart_data]
        
        # Build Chart.js compatible structure
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
                },
                {
                    'label': 'S&P 500',
                    'data': sp500_data,
                    'borderColor': 'rgb(108, 117, 125)',
                    'backgroundColor': 'rgba(108, 117, 125, 0.1)',
                    'tension': 0.1,
                    'fill': False,
                    'borderDash': [5, 5]
                }
            ],
            'portfolio_return': result.get('portfolio_return'),
            'sp500_return': result.get('sp500_return')
        }
        
        from flask import current_app
        current_app.logger.info(f"✓ Chart generated for user {user_id}, period {period}: {result.get('portfolio_return')}% return, {len(labels)} points")
        
        return chart_data
        
    except Exception as e:
        from flask import current_app
        import traceback
        current_app.logger.error(f"ERROR generating chart for user {user_id}, period {period}: {str(e)}")
        current_app.logger.error(traceback.format_exc())
        # Re-raise in development, return None in production to avoid breaking cache generation
        raise


def generate_chart_from_snapshots_OLD_DEPRECATED(user_id, period):
    """
    OLD DEPRECATED VERSION - Keep for reference only.
    This uses snapshot-based logic which gave inconsistent results.
    DO NOT USE - Use generate_chart_from_snapshots() instead.
    """
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
    Applies Active Edge filtering to match mobile leaderboard rankings.
    """
    from models import Transaction
    from datetime import datetime, timedelta
    
    positions = {}
    # Display labels: use 1W instead of 5D to match mobile convention
    period_map = {'1D': '1D', '5D': '1W', '1M': '1M', '3M': '3M', 'YTD': 'YTD', '1Y': '1Y'}
    
    # Period-aware minimum account age (same as mobile Active Edge)
    min_age_for_period = {
        '1D': 1, '5D': 5, '1M': 7, '3M': 14, 'YTD': 14, '1Y': 30
    }
    
    for period, display_label in period_map.items():
        leaderboard_data = get_leaderboard_data(period, limit=100)
        if not leaderboard_data:
            continue
        
        # Apply Active Edge filtering (same logic as mobile_api.py)
        filtered = []
        for entry in leaderboard_data:
            uid = entry.get('user_id')
            if not uid:
                continue
            
            # Must have traded within last 60 days
            last_trade = Transaction.query.filter_by(user_id=uid)\
                .order_by(Transaction.timestamp.desc()).first()
            if not last_trade or (datetime.utcnow() - last_trade.timestamp).days > 60:
                continue
            
            # Must have at least 2 trades total
            total_trades = Transaction.query.filter_by(user_id=uid).count()
            if total_trades < 2:
                continue
            
            # Period-aware minimum age
            u = User.query.get(uid)
            if u and u.created_at:
                account_age = (datetime.utcnow() - u.created_at).days
                min_age = min_age_for_period.get(period, 1)
                if account_age < min_age:
                    continue
            
            filtered.append(entry)
        
        # Sort filtered entries by performance descending
        filtered.sort(key=lambda x: x.get('performance_percent', 0), reverse=True)
        
        # Find user's position in filtered list
        for idx, entry in enumerate(filtered, 1):
            if entry.get('user_id') == user_id:
                if idx <= top_n:
                    positions[display_label] = idx
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
    
    # Batch-load all StockInfo records in ONE query (avoids N+1 per-stock queries)
    tickers = [stock.ticker.upper() for stock in stocks]
    all_stock_info = {si.ticker: si for si in StockInfo.query.filter(StockInfo.ticker.in_(tickers)).all()} if tickers else {}
    
    for stock in stocks:
        stock_info = all_stock_info.get(stock.ticker.upper())
        
        if total_purchase_value > 0:
            stock_purchase_value = stock.quantity * stock.purchase_price
            stock_current_value = (stock_purchase_value / total_purchase_value) * total_value
            
            # Use GICS sector (e.g. 'Technology', 'Healthcare') not sub-industry
            raw_sector = stock_info.sector if stock_info and stock_info.sector else None
            if raw_sector:
                from stock_metadata_utils import normalize_sector_name
                sector = normalize_sector_name(raw_sector)
            else:
                from stock_metadata_utils import get_etf_sector_fallback
                sector = get_etf_sector_fallback(stock.ticker) or 'Other'
            
            industry_values[sector] = industry_values.get(sector, 0) + stock_current_value
    
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
    
    # Calculate avg trades per week (last 14 days)
    fourteen_days_ago = datetime.now() - timedelta(days=14)
    recent_transactions = [t for t in transactions if t.timestamp >= fourteen_days_ago]
    avg_trades_per_day = len(recent_transactions) / 14
    stats['avg_trades_per_week'] = round(avg_trades_per_day * 7, 2)
    
    # 3. LARGE CAP %
    small_cap_percent, large_cap_percent = calculate_portfolio_cap_percentages(user_id)
    stats['small_cap_percent'] = small_cap_percent
    stats['large_cap_percent'] = large_cap_percent
    
    # 4. INDUSTRY MIX
    industry_mix = calculate_industry_mix(user_id)
    stats['industry_mix'] = industry_mix
    
    # 5. SUBSCRIBER COUNT (real + gifted from all sources)
    subscriber_count = Subscription.query.filter_by(
        subscribed_to_id=user_id,
        status='active'
    ).count()
    try:
        from models import MobileSubscription
        subscriber_count += MobileSubscription.query.filter_by(
            subscribed_to_id=user_id,
            status='active'
        ).count()
    except Exception:
        pass
    try:
        from models import AdminSubscription
        admin_sub = AdminSubscription.query.filter_by(portfolio_user_id=user_id).first()
        if admin_sub:
            subscriber_count += admin_sub.bonus_subscriber_count or 0
    except Exception:
        pass
    stats['subscriber_count'] = subscriber_count
    
    stats['last_updated'] = datetime.utcnow()
    
    return stats

def calculate_chart_y_axis_range(chart_data_list):
    """
    Calculate consistent y-axis min/max range across all charts for visual comparison
    Uses actual data range with minimal padding to avoid wasted chart space
    
    Args:
        chart_data_list: List of chart data dicts with 'datasets' containing portfolio and S&P 500 values
        
    Returns:
        dict with 'min' and 'max' values, with 10-15% padding for visual clarity
    """
    if not chart_data_list:
        return {'min': -10, 'max': 10}
    
    all_values = []
    
    # Extract ALL values from both portfolio AND S&P 500 datasets
    for chart_data in chart_data_list:
        if not chart_data or 'datasets' not in chart_data:
            continue
        
        for dataset in chart_data['datasets']:
            # Include both Portfolio and S&P 500 data
            if 'data' in dataset:
                all_values.extend([v for v in dataset['data'] if v is not None])
    
    if not all_values:
        return {'min': -10, 'max': 10}
    
    min_val = min(all_values)
    max_val = max(all_values)
    
    # Add 10-15% padding to the actual range for visual clarity
    range_size = max_val - min_val
    padding = max(range_size * 0.15, 2)  # At least 2% padding
    
    y_min = min_val - padding
    y_max = max_val + padding
    
    # Round to clean intervals (1% increments for readability)
    import math
    y_min = math.floor(y_min)
    y_max = math.ceil(y_max)
    
    # Ensure minimum range of 5% for very tight clusters
    if y_max - y_min < 5:
        center = (y_min + y_max) / 2
        y_min = center - 2.5
        y_max = center + 2.5
    
    return {'min': y_min, 'max': y_max}

