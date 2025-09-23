"""
Portfolio performance API with intraday data support.
Combines pre-generated S&P 500 charts with user portfolio overlays.
Updated: 2025-09-22 - Fixed 5D chart distribution
"""
import json
from datetime import datetime, timedelta, date
from flask import request, jsonify
from models import db, PortfolioSnapshotIntraday, SP500ChartCache, MarketData
from portfolio_performance import PortfolioPerformanceCalculator
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def handler(request):
    """Vercel serverless function handler for intraday portfolio performance"""
    try:
        # Extract period from URL path
        path_parts = request.path.split('/')
        if len(path_parts) < 4:
            return jsonify({'error': 'Period parameter required'}), 400
        
        period = path_parts[-1]  # Get last part of path
        user_id = request.args.get('user_id')
        
        if not user_id:
            return jsonify({'error': 'user_id parameter required'}), 400
        
        try:
            user_id = int(user_id)
        except ValueError:
            return jsonify({'error': 'Invalid user_id'}), 400
        
        # Get performance data using intraday system
        performance_data = get_intraday_performance_data(user_id, period)
        
        if 'error' in performance_data:
            return jsonify(performance_data), 400
        
        return jsonify(performance_data), 200
    
    except Exception as e:
        logger.error(f"Error in performance-intraday API: {str(e)}")
        return jsonify({'error': f'Internal server error: {str(e)}'}), 500


def get_intraday_performance_data(user_id: int, period: str):
    """Get performance data combining pre-generated S&P 500 charts with user portfolio overlay"""
    try:
        # Validate period
        valid_periods = ['1D', '5D', '1M', '3M', 'YTD', '1Y', '5Y']
        if period not in valid_periods:
            return {'error': f'Invalid period. Must be one of: {", ".join(valid_periods)}'}
        
        # Get pre-generated S&P 500 chart data
        logger.info(f"Attempting to get cached S&P 500 chart for period {period}")
        sp500_chart = get_cached_sp500_chart(period)
        if not sp500_chart:
            # Fallback to generating chart on-demand
            logger.warning(f"Cache miss for {period}, falling back to live generation (this will make Alpha Vantage API calls)")
            sp500_chart = generate_sp500_chart_fallback(period)
        else:
            logger.info(f"Successfully using cached S&P 500 data for {period} - no API calls needed")
        
        # Get user portfolio data
        portfolio_data = get_user_portfolio_data(user_id, period)
        
        # Combine S&P 500 and portfolio data
        combined_chart_data = combine_chart_data(sp500_chart, portfolio_data, period)
        
        # Calculate overall returns
        portfolio_return = calculate_portfolio_return(portfolio_data)
        sp500_return = calculate_sp500_return(sp500_chart)
        
        return {
            'portfolio_return': round(portfolio_return, 2),
            'sp500_return': round(sp500_return, 2),
            'chart_data': combined_chart_data,
            'period': period,
            'data_source': 'intraday' if period in ['1D', '5D'] else 'daily',
            'last_updated': datetime.now().isoformat()
        }
    
    except Exception as e:
        logger.error(f"Error getting intraday performance data: {str(e)}")
        return {'error': f'Failed to get performance data: {str(e)}'}


def get_cached_sp500_chart(period: str):
    """Get pre-generated S&P 500 chart from cache"""
    try:
        cache_entry = SP500ChartCache.query.filter_by(period=period).first()
        
        if cache_entry:
            logger.info(f"Found S&P 500 cache for {period}: generated={cache_entry.generated_at}, expires={cache_entry.expires_at}")
            if cache_entry.expires_at > datetime.now():
                logger.info(f"Using cached S&P 500 data for {period} (valid until {cache_entry.expires_at})")
                return json.loads(cache_entry.chart_data)
            else:
                logger.warning(f"S&P 500 cache for {period} expired at {cache_entry.expires_at}")
        else:
            logger.warning(f"No S&P 500 cache found for period {period}")
        
        return None
    
    except Exception as e:
        logger.error(f"Error getting cached S&P 500 chart: {str(e)}")
        return None


def generate_sp500_chart_fallback(period: str):
    """Generate S&P 500 chart on-demand as fallback"""
    try:
        from api.cron.collect_intraday_data import SP500ChartGenerator
        generator = SP500ChartGenerator()
        return generator.generate_sp500_chart(period)
    
    except Exception as e:
        logger.error(f"Error generating S&P 500 chart fallback: {str(e)}")
        return None


def get_last_market_day_end():
    """Get the end time (4 PM ET) of the last market day"""
    now = datetime.now()
    
    # If it's Saturday (5) or Sunday (6), go back to Friday
    if now.weekday() == 5:  # Saturday
        last_market_day = now - timedelta(days=1)  # Friday
    elif now.weekday() == 6:  # Sunday
        last_market_day = now - timedelta(days=2)  # Friday
    else:
        # Monday-Friday: if it's before 4 PM, use previous day; if after 4 PM, use today
        if now.hour < 16:  # Before 4 PM
            if now.weekday() == 0:  # Monday
                last_market_day = now - timedelta(days=3)  # Previous Friday
            else:
                last_market_day = now - timedelta(days=1)  # Previous day
        else:
            last_market_day = now  # Today after market close
    
    # Set to 4 PM ET (market close)
    return last_market_day.replace(hour=16, minute=0, second=0, microsecond=0)


def get_user_portfolio_data(user_id: int, period: str):
    """Get user portfolio snapshots for the specified period"""
    try:
        # For 1D and 5D, use current time (market may be open today)
        if period in ['1D', '5D']:
            end_time = datetime.now()
            if period == '1D':
                # For 1D, show today if market day, otherwise last market day
                if datetime.now().weekday() < 5:  # Monday-Friday
                    start_time = end_time.replace(hour=9, minute=30, second=0, microsecond=0)  # Today's market open
                else:
                    # Weekend: use last Friday
                    last_friday = get_last_market_day_end()
                    start_time = last_friday.replace(hour=9, minute=30, second=0, microsecond=0)
                    end_time = last_friday
            else:
                # For 5D, go back 5 market days
                start_time = end_time - timedelta(days=7)  # Go back a week to catch 5 market days
        else:
            # For longer periods, use current time
            end_time = datetime.now()
            
            # Define period mappings
            period_hours = {
                '1M': 720,  # 30 days
                '3M': 2160,  # 90 days
                'YTD': None,  # Special handling
                '1Y': 8760,  # 365 days
                '5Y': 43800   # 5 years
            }
            
            if period == 'YTD':
                start_time = datetime(end_time.year, 1, 1)
            else:
                hours_back = period_hours.get(period, 24)
                start_time = end_time - timedelta(hours=hours_back)
        
        # Get intraday snapshots for short periods, daily for longer periods
        if period in ['1D', '5D']:
            snapshots = PortfolioSnapshotIntraday.query.filter(
                PortfolioSnapshotIntraday.user_id == user_id,
                PortfolioSnapshotIntraday.timestamp >= start_time,
                PortfolioSnapshotIntraday.timestamp <= end_time
            ).order_by(PortfolioSnapshotIntraday.timestamp).all()
            
            logger.info(f"Found {len(snapshots)} intraday snapshots for user {user_id} period {period} ({start_time} to {end_time})")
            if snapshots:
                logger.info(f"Intraday snapshot range: {snapshots[0].timestamp} to {snapshots[-1].timestamp}")
                logger.info(f"Sample values: {[s.total_value for s in snapshots[:3]]}")
                
                # Check if we have today's data specifically
                today = datetime.now().date()
                today_snapshots = [s for s in snapshots if s.timestamp.date() == today]
                logger.info(f"Snapshots for today ({today}): {len(today_snapshots)}")
                if today_snapshots:
                    logger.info(f"Today's snapshot times: {[s.timestamp.strftime('%H:%M') for s in today_snapshots[:5]]}")
            else:
                logger.warning(f"No intraday snapshots found for user {user_id} in period {period}")
                
                # Check if ANY intraday snapshots exist for this user
                total_snapshots = PortfolioSnapshotIntraday.query.filter_by(user_id=user_id).count()
                logger.info(f"Total intraday snapshots for user {user_id}: {total_snapshots}")
            
            # Keep all snapshots - Chart.js will handle the distribution
            return [(s.timestamp, s.total_value) for s in snapshots]
        else:
            # Use daily snapshots for longer periods
            calculator = PortfolioPerformanceCalculator()
            daily_data = calculator.get_performance_data(user_id, period)
            
            # Convert to timestamp, value format
            portfolio_data = []
            if 'chart_data' in daily_data:
                for point in daily_data['chart_data']:
                    date_obj = datetime.fromisoformat(point['date'])
                    # We need actual portfolio value, not percentage
                    # This is a limitation - we may need to store absolute values
                    portfolio_data.append((date_obj, 0))  # Placeholder
            
            return portfolio_data
    
    except Exception as e:
        logger.error(f"Error getting user portfolio data: {str(e)}")
        return []


def sample_intraday_data_for_5d(snapshots):
    """Sample intraday data to create smoother 5D charts with evenly distributed points"""
    from collections import defaultdict
    
    # Group snapshots by day
    daily_snapshots = defaultdict(list)
    for snapshot in snapshots:
        day_key = snapshot.timestamp.date()
        daily_snapshots[day_key].append(snapshot)
    
    sampled_snapshots = []
    
    # For each day, take key snapshots: market open, mid-day, market close
    for day, day_snapshots in daily_snapshots.items():
        if not day_snapshots:
            continue
            
        # Sort by time
        day_snapshots.sort(key=lambda s: s.timestamp)
        
        # Take market open (first), mid-day (middle), and market close (last)
        if len(day_snapshots) == 1:
            sampled_snapshots.extend(day_snapshots)
        elif len(day_snapshots) == 2:
            sampled_snapshots.extend(day_snapshots)
        elif len(day_snapshots) >= 3:
            # Take first, middle, and last
            mid_index = len(day_snapshots) // 2
            sampled_snapshots.extend([
                day_snapshots[0],      # Market open
                day_snapshots[mid_index],  # Mid-day
                day_snapshots[-1]      # Market close
            ])
    
    # Sort by timestamp
    sampled_snapshots.sort(key=lambda s: s.timestamp)
    return sampled_snapshots


def combine_chart_data(sp500_chart, portfolio_data, period):
    """Combine S&P 500 and portfolio data into unified chart format"""
    try:
        if not sp500_chart or 'data' not in sp500_chart:
            return []
        
        sp500_data = sp500_chart['data']
        combined_data = []
        
        # Create lookup for portfolio data
        portfolio_lookup = {}
        for timestamp, value in portfolio_data:
            # Round timestamp to nearest 30 minutes for matching
            rounded_time = round_to_nearest_30min(timestamp)
            portfolio_lookup[rounded_time] = value
        
        # Calculate portfolio percentage changes
        portfolio_start_value = None
        if portfolio_data:
            portfolio_start_value = portfolio_data[0][1]
        
        for sp500_point in sp500_data:
            try:
                point_date = datetime.fromisoformat(sp500_point['date'])
                rounded_time = round_to_nearest_30min(point_date)
                
                # Get portfolio value for this time
                portfolio_value = portfolio_lookup.get(rounded_time, 0)
                portfolio_pct = 0
                
                if portfolio_start_value and portfolio_start_value > 0 and portfolio_value > 0:
                    portfolio_pct = ((portfolio_value - portfolio_start_value) / portfolio_start_value) * 100
                
                # Format date label based on period
                if period == '1D':
                    # For 1D charts, show time only
                    time_label = point_date.strftime('%I:%M %p')
                elif period == '5D':
                    # For 5D charts, show day name or date
                    time_label = point_date.strftime('%a %m/%d')
                else:
                    # For longer periods, use the original date
                    time_label = sp500_point['date']
                
                combined_data.append({
                    'date': time_label,
                    'portfolio': round(portfolio_pct, 2),
                    'sp500': sp500_point['pct_change']
                })
            
            except Exception as e:
                logger.error(f"Error processing chart point: {str(e)}")
                continue
        
        return combined_data
    
    except Exception as e:
        logger.error(f"Error combining chart data: {str(e)}")
        return []


def round_to_nearest_30min(dt):
    """Round datetime to nearest 30-minute interval"""
    minutes = dt.minute
    if minutes < 15:
        rounded_minutes = 0
    elif minutes < 45:
        rounded_minutes = 30
    else:
        rounded_minutes = 0
        dt = dt + timedelta(hours=1)
    
    return dt.replace(minute=rounded_minutes, second=0, microsecond=0)


def calculate_portfolio_return(portfolio_data):
    """Calculate overall portfolio return from data points"""
    if len(portfolio_data) < 2:
        return 0.0
    
    start_value = portfolio_data[0][1]
    end_value = portfolio_data[-1][1]
    
    if start_value <= 0:
        return 0.0
    
    return ((end_value - start_value) / start_value) * 100


def calculate_sp500_return(sp500_chart):
    """Calculate overall S&P 500 return from chart data"""
    if not sp500_chart or 'data' not in sp500_chart or len(sp500_chart['data']) < 2:
        return 0.0
    
    data_points = sp500_chart['data']
    start_value = data_points[0]['value']
    end_value = data_points[-1]['value']
    
    if start_value <= 0:
        return 0.0
    
    return ((end_value - start_value) / start_value) * 100
