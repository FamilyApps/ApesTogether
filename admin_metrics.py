"""
Admin dashboard metrics utilities for tracking platform health
"""
from datetime import datetime, date, timedelta
from models import db, User, Stock, StockInfo, AlphaVantageAPILog, PlatformMetrics, PortfolioSnapshot
from sqlalchemy import func, distinct, and_

def log_alpha_vantage_call(endpoint, symbol=None, response_status='success', response_time_ms=None):
    """
    Log an Alpha Vantage API call for tracking and rate limiting
    
    Args:
        endpoint: API endpoint called (e.g., 'GLOBAL_QUOTE', 'TIME_SERIES_DAILY')
        symbol: Stock symbol if applicable
        response_status: 'success', 'error', 'rate_limited'
        response_time_ms: Response time in milliseconds
    """
    try:
        log_entry = AlphaVantageAPILog(
            endpoint=endpoint,
            symbol=symbol,
            response_status=response_status,
            response_time_ms=response_time_ms
        )
        db.session.add(log_entry)
        db.session.commit()
    except Exception as e:
        print(f"Error logging Alpha Vantage API call: {str(e)}")
        db.session.rollback()

def calculate_unique_stocks_count():
    """Calculate the number of unique stocks being tracked"""
    try:
        # Count distinct stock symbols from both Stock and StockInfo tables
        stock_symbols = db.session.query(distinct(Stock.ticker)).all()
        stock_info_symbols = db.session.query(distinct(StockInfo.symbol)).all()
        
        all_symbols = set()
        for (symbol,) in stock_symbols:
            all_symbols.add(symbol.upper())
        for (symbol,) in stock_info_symbols:
            all_symbols.add(symbol.upper())
            
        return len(all_symbols)
    except Exception as e:
        print(f"Error calculating unique stocks count: {str(e)}")
        return 0

def calculate_active_users(days):
    """Calculate number of active users in the last N days"""
    try:
        cutoff_date = datetime.now() - timedelta(days=days)
        
        # Count users who have portfolio snapshots in the period (indicates activity)
        active_users = db.session.query(distinct(PortfolioSnapshot.user_id)).filter(
            PortfolioSnapshot.date >= cutoff_date.date()
        ).count()
        
        return active_users
    except Exception as e:
        print(f"Error calculating active users for {days} days: {str(e)}")
        return 0

def calculate_api_call_metrics(days=7):
    """
    Calculate Alpha Vantage API call metrics for the last N days
    Returns: (total_calls, avg_per_minute, peak_per_minute, peak_time)
    """
    try:
        cutoff_date = datetime.now() - timedelta(days=days)
        
        # Get all API calls in the period
        api_calls = AlphaVantageAPILog.query.filter(
            AlphaVantageAPILog.timestamp >= cutoff_date
        ).all()
        
        if not api_calls:
            return 0, 0.0, 0, None
        
        total_calls = len(api_calls)
        total_minutes = days * 24 * 60
        avg_per_minute = total_calls / total_minutes if total_minutes > 0 else 0
        
        # Calculate peak calls per minute
        # Group calls by minute and find the highest count
        calls_by_minute = {}
        for call in api_calls:
            minute_key = call.timestamp.replace(second=0, microsecond=0)
            calls_by_minute[minute_key] = calls_by_minute.get(minute_key, 0) + 1
        
        if calls_by_minute:
            peak_minute = max(calls_by_minute, key=calls_by_minute.get)
            peak_per_minute = calls_by_minute[peak_minute]
            peak_time = peak_minute
        else:
            peak_per_minute = 0
            peak_time = None
        
        return total_calls, round(avg_per_minute, 2), peak_per_minute, peak_time
        
    except Exception as e:
        print(f"Error calculating API call metrics: {str(e)}")
        return 0, 0.0, 0, None

def update_daily_metrics():
    """
    Update daily platform metrics - called once per day
    """
    try:
        today = date.today()
        
        # Check if metrics already exist for today
        existing_metrics = PlatformMetrics.query.filter_by(date=today).first()
        
        # Calculate all metrics
        unique_stocks = calculate_unique_stocks_count()
        active_1d = calculate_active_users(1)
        active_7d = calculate_active_users(7)
        active_30d = calculate_active_users(30)
        active_90d = calculate_active_users(90)
        
        total_calls, avg_per_min, peak_per_min, peak_time = calculate_api_call_metrics(7)
        
        if existing_metrics:
            # Update existing metrics
            existing_metrics.unique_stocks_count = unique_stocks
            existing_metrics.active_users_1d = active_1d
            existing_metrics.active_users_7d = active_7d
            existing_metrics.active_users_30d = active_30d
            existing_metrics.active_users_90d = active_90d
            existing_metrics.api_calls_total = total_calls
            existing_metrics.api_calls_avg_per_minute = avg_per_min
            existing_metrics.api_calls_peak_per_minute = peak_per_min
            existing_metrics.api_calls_peak_time = peak_time
        else:
            # Create new metrics entry
            metrics = PlatformMetrics(
                date=today,
                unique_stocks_count=unique_stocks,
                active_users_1d=active_1d,
                active_users_7d=active_7d,
                active_users_30d=active_30d,
                active_users_90d=active_90d,
                api_calls_total=total_calls,
                api_calls_avg_per_minute=avg_per_min,
                api_calls_peak_per_minute=peak_per_min,
                api_calls_peak_time=peak_time
            )
            db.session.add(metrics)
        
        db.session.commit()
        return True
        
    except Exception as e:
        print(f"Error updating daily metrics: {str(e)}")
        db.session.rollback()
        return False

def get_admin_dashboard_metrics():
    """
    Get current platform metrics for admin dashboard
    """
    try:
        # Get latest metrics
        latest_metrics = PlatformMetrics.query.order_by(PlatformMetrics.date.desc()).first()
        
        if not latest_metrics:
            # Calculate on-demand if no cached metrics
            unique_stocks = calculate_unique_stocks_count()
            active_1d = calculate_active_users(1)
            active_7d = calculate_active_users(7)
            active_30d = calculate_active_users(30)
            active_90d = calculate_active_users(90)
            total_calls, avg_per_min, peak_per_min, peak_time = calculate_api_call_metrics(7)
            
            return {
                'date': date.today().isoformat(),
                'unique_stocks_count': unique_stocks,
                'active_users': {
                    '1_day': active_1d,
                    '7_days': active_7d,
                    '30_days': active_30d,
                    '90_days': active_90d
                },
                'api_calls': {
                    'total_last_7_days': total_calls,
                    'avg_per_minute_7_days': avg_per_min,
                    'peak_per_minute_7_days': peak_per_min,
                    'peak_time': peak_time.isoformat() if peak_time else None
                },
                'cached': False
            }
        
        return {
            'date': latest_metrics.date.isoformat(),
            'unique_stocks_count': latest_metrics.unique_stocks_count,
            'active_users': {
                '1_day': latest_metrics.active_users_1d,
                '7_days': latest_metrics.active_users_7d,
                '30_days': latest_metrics.active_users_30d,
                '90_days': latest_metrics.active_users_90d
            },
            'api_calls': {
                'total_last_7_days': latest_metrics.api_calls_total,
                'avg_per_minute_7_days': latest_metrics.api_calls_avg_per_minute,
                'peak_per_minute_7_days': latest_metrics.api_calls_peak_per_minute,
                'peak_time': latest_metrics.api_calls_peak_time.isoformat() if latest_metrics.api_calls_peak_time else None
            },
            'cached': True,
            'last_updated': latest_metrics.created_at.isoformat()
        }
        
    except Exception as e:
        print(f"Error getting admin dashboard metrics: {str(e)}")
        return {
            'error': str(e),
            'date': date.today().isoformat(),
            'cached': False
        }
