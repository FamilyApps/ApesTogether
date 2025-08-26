"""
Intraday data collection endpoint for GitHub Actions cron jobs.
Collects SPY data and calculates portfolio values for all users every 30 minutes.
"""
import os
import json
from datetime import datetime, timedelta
from flask import Flask, request, jsonify
from models import db, User, PortfolioSnapshotIntraday, MarketData, SP500ChartCache
from portfolio_performance import PortfolioPerformanceCalculator
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def handler(request):
    """Vercel serverless function handler"""
    try:
        # Verify authorization token
        auth_header = request.headers.get('Authorization', '')
        expected_token = os.environ.get('INTRADAY_CRON_TOKEN')
        
        if not expected_token:
            logger.error("INTRADAY_CRON_TOKEN not configured")
            return jsonify({'error': 'Server configuration error'}), 500
        
        if not auth_header.startswith('Bearer ') or auth_header[7:] != expected_token:
            logger.warning(f"Unauthorized intraday collection attempt from {request.remote_addr}")
            return jsonify({'error': 'Unauthorized'}), 401
        
        # Check if market is open (9:30 AM - 4:00 PM ET, Monday-Friday)
        if not is_market_open():
            logger.info("Market is closed, skipping intraday collection")
            return jsonify({'message': 'Market closed, no data collected'}), 200
        
        # Initialize performance calculator
        calculator = PortfolioPerformanceCalculator()
        current_time = datetime.now()
        
        results = {
            'timestamp': current_time.isoformat(),
            'spy_data_collected': False,
            'users_processed': 0,
            'snapshots_created': 0,
            'charts_generated': 0,
            'errors': []
        }
        
        # Step 1: Collect SPY data
        try:
            spy_data = calculator.get_stock_data('SPY')
            if spy_data and spy_data.get('price'):
                spy_price = spy_data['price']
                sp500_value = spy_price * 10  # Convert SPY to S&P 500 approximation
                
                # Store intraday SPY data
                market_data = MarketData(
                    ticker='SPY_INTRADAY',
                    date=current_time.date(),
                    timestamp=current_time,
                    close_price=sp500_value
                )
                db.session.add(market_data)
                results['spy_data_collected'] = True
                logger.info(f"SPY data collected: ${spy_price} (S&P 500: ${sp500_value})")
            else:
                results['errors'].append("Failed to fetch SPY data")
                logger.error("Failed to fetch SPY data from AlphaVantage")
        
        except Exception as e:
            error_msg = f"Error collecting SPY data: {str(e)}"
            results['errors'].append(error_msg)
            logger.error(error_msg)
        
        # Step 2: Calculate portfolio values for all users
        try:
            users = User.query.all()
            results['users_processed'] = len(users)
            results['user_details'] = []
            
            logger.info(f"Found {len(users)} users to process")
            
            for user in users:
                user_result = {
                    'user_id': user.id,
                    'username': getattr(user, 'username', 'unknown'),
                    'success': False,
                    'portfolio_value': 0,
                    'error': None
                }
                
                try:
                    # Calculate current portfolio value
                    portfolio_value = calculator.calculate_portfolio_value(user.id)
                    user_result['portfolio_value'] = portfolio_value
                    
                    # Create intraday snapshot
                    snapshot = PortfolioSnapshotIntraday(
                        user_id=user.id,
                        timestamp=current_time,
                        total_value=portfolio_value
                    )
                    db.session.add(snapshot)
                    results['snapshots_created'] += 1
                    user_result['success'] = True
                    
                    logger.info(f"Created snapshot for user {user.id} ({user_result['username']}): ${portfolio_value}")
                    
                except Exception as e:
                    error_msg = f"Error processing user {user.id} ({user_result['username']}): {str(e)}"
                    user_result['error'] = str(e)
                    results['errors'].append(error_msg)
                    logger.error(error_msg)
                
                results['user_details'].append(user_result)
        
        except Exception as e:
            error_msg = f"Error querying users: {str(e)}"
            results['errors'].append(error_msg)
            logger.error(error_msg)
        
        # Step 3: Generate S&P 500 charts for all periods
        try:
            chart_generator = SP500ChartGenerator()
            periods = ['1D', '5D', '1M', '3M', 'YTD', '1Y', '5Y']
            
            for period in periods:
                try:
                    chart_data = chart_generator.generate_sp500_chart(period)
                    if chart_data:
                        # Store in cache
                        expires_at = current_time + timedelta(minutes=30)
                        
                        # Update or create cache entry
                        cache_entry = SP500ChartCache.query.filter_by(period=period).first()
                        if cache_entry:
                            cache_entry.chart_data = json.dumps(chart_data)
                            cache_entry.generated_at = current_time
                            cache_entry.expires_at = expires_at
                        else:
                            cache_entry = SP500ChartCache(
                                period=period,
                                chart_data=json.dumps(chart_data),
                                generated_at=current_time,
                                expires_at=expires_at
                            )
                            db.session.add(cache_entry)
                        
                        results['charts_generated'] += 1
                        logger.info(f"Generated S&P 500 chart for {period}")
                
                except Exception as e:
                    error_msg = f"Error generating {period} chart: {str(e)}"
                    results['errors'].append(error_msg)
                    logger.error(error_msg)
        
        except Exception as e:
            error_msg = f"Error in chart generation: {str(e)}"
            results['errors'].append(error_msg)
            logger.error(error_msg)
        
        # Commit all changes
        try:
            db.session.commit()
            logger.info(f"Intraday collection completed: {results['snapshots_created']} snapshots, {results['charts_generated']} charts")
        except Exception as e:
            db.session.rollback()
            error_msg = f"Database commit failed: {str(e)}"
            results['errors'].append(error_msg)
            logger.error(error_msg)
            return jsonify({'error': error_msg, 'results': results}), 500
        
        return jsonify({
            'success': True,
            'results': results
        }), 200
    
    except Exception as e:
        logger.error(f"Unexpected error in intraday collection: {str(e)}")
        return jsonify({'error': f'Unexpected error: {str(e)}'}), 500


def is_market_open():
    """Check if the stock market is currently open (9:30 AM - 4:00 PM ET, Monday-Friday)"""
    now = datetime.now()
    
    # Check if it's a weekday (Monday=0, Sunday=6)
    if now.weekday() >= 5:  # Saturday or Sunday
        return False
    
    # Convert to ET (approximate - doesn't handle DST perfectly)
    # For production, consider using pytz for proper timezone handling
    et_hour = now.hour - 4  # Assuming UTC, adjust for your server timezone
    if et_hour < 0:
        et_hour += 24
    
    # Market hours: 9:30 AM - 4:00 PM ET
    market_open_hour = 9
    market_open_minute = 30
    market_close_hour = 16
    market_close_minute = 0
    
    current_minutes = et_hour * 60 + now.minute
    market_open_minutes = market_open_hour * 60 + market_open_minute
    market_close_minutes = market_close_hour * 60 + market_close_minute
    
    return market_open_minutes <= current_minutes <= market_close_minutes


class SP500ChartGenerator:
    """Generate pre-computed S&P 500 charts for all time periods"""
    
    def __init__(self):
        self.calculator = PortfolioPerformanceCalculator()
    
    def generate_sp500_chart(self, period: str):
        """Generate S&P 500 chart data for a specific period"""
        try:
            end_date = datetime.now().date()
            
            # Define period mappings
            period_days = {
                '1D': 1,
                '5D': 5,
                '1M': 30,
                '3M': 90,
                'YTD': (end_date - datetime(end_date.year, 1, 1).date()).days,
                '1Y': 365,
                '5Y': 1825
            }
            
            if period not in period_days:
                return None
            
            if period == 'YTD':
                start_date = datetime(end_date.year, 1, 1).date()
            else:
                start_date = end_date - timedelta(days=period_days[period])
            
            # Get S&P 500 data
            if period in ['1D', '5D']:
                # Use intraday data for short periods
                sp500_data = self._get_intraday_sp500_data(start_date, end_date)
            else:
                # Use daily data for longer periods
                sp500_data = self.calculator.get_cached_sp500_data(start_date, end_date)
            
            if not sp500_data:
                return None
            
            # Convert to chart format
            chart_data = []
            sorted_dates = sorted(sp500_data.keys())
            
            if sorted_dates:
                start_value = sp500_data[sorted_dates[0]]
                
                for date_key in sorted_dates:
                    value = sp500_data[date_key]
                    pct_change = ((value - start_value) / start_value) * 100 if start_value > 0 else 0
                    
                    chart_data.append({
                        'date': date_key.isoformat() if hasattr(date_key, 'isoformat') else str(date_key),
                        'value': round(value, 2),
                        'pct_change': round(pct_change, 2)
                    })
            
            return {
                'period': period,
                'data': chart_data,
                'start_date': start_date.isoformat(),
                'end_date': end_date.isoformat()
            }
        
        except Exception as e:
            logger.error(f"Error generating S&P 500 chart for {period}: {str(e)}")
            return None
    
    def _get_intraday_sp500_data(self, start_date, end_date):
        """Get intraday S&P 500 data from MarketData table"""
        try:
            intraday_data = MarketData.query.filter(
                MarketData.ticker == 'SPY_INTRADAY',
                MarketData.date >= start_date,
                MarketData.date <= end_date,
                MarketData.timestamp.isnot(None)
            ).order_by(MarketData.timestamp).all()
            
            return {data.timestamp: data.close_price for data in intraday_data}
        
        except Exception as e:
            logger.error(f"Error fetching intraday S&P 500 data: {str(e)}")
            return {}
