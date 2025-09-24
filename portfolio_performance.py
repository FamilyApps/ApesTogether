"""
Portfolio performance calculation using Modified Dietz method and market benchmarking.
"""
import requests
import os
from datetime import datetime, date, timedelta
from typing import Dict, List, Tuple, Optional
from models import db, PortfolioSnapshot, MarketData, Transaction, Stock, User
from sqlalchemy import func, and_
import logging

logger = logging.getLogger(__name__)

# Cache for stock prices (90-second caching like existing system)
stock_price_cache = {}
cache_duration = 90

class PortfolioPerformanceCalculator:
    """Calculate portfolio performance using Modified Dietz method"""
    
    def __init__(self):
        self.sp500_ticker = "SPY_SP500"  # S&P 500 proxy using SPY
        self.alpha_vantage_api_key = os.environ.get('ALPHA_VANTAGE_API_KEY')
    
    def get_stock_data(self, ticker_symbol: str) -> Dict:
        """Fetches stock data using AlphaVantage API with caching (same as existing system)"""
        # Check cache first
        ticker_upper = ticker_symbol.upper()
        current_time = datetime.now()
        
        if ticker_upper in stock_price_cache:
            cached_data = stock_price_cache[ticker_upper]
            cache_time = cached_data.get('timestamp')
            if cache_time and (current_time - cache_time).total_seconds() < cache_duration:
                return {'price': cached_data['price']}
        
        try:
            api_key = os.environ.get('ALPHA_VANTAGE_API_KEY')
            if not api_key:
                logger.warning("Alpha Vantage API key not found, cannot fetch stock price")
                return None
            
            # Use Alpha Vantage API
            url = f'https://www.alphavantage.co/query?function=GLOBAL_QUOTE&symbol={ticker_symbol}&apikey={api_key}'
            response = requests.get(url, timeout=5)
            data = response.json()
            
            # Log the API call (but don't commit immediately for performance)
            try:
                from models import AlphaVantageAPILog, db
                success = 'Global Quote' in data and '05. price' in data.get('Global Quote', {})
                api_log = AlphaVantageAPILog(
                    endpoint='GLOBAL_QUOTE',
                    symbol=ticker_symbol,
                    response_status='success' if success else 'error',
                    timestamp=current_time
                )
                db.session.add(api_log)
                # Commit will happen at end of batch operation
            except Exception as log_error:
                logger.error(f"Failed to log API call: {log_error}")
            
            if 'Global Quote' in data and '05. price' in data['Global Quote']:
                price = float(data['Global Quote']['05. price'])
                stock_price_cache[ticker_upper] = {'price': price, 'timestamp': current_time}
                return {'price': price}
            else:
                logger.warning(f"Could not get price for {ticker_symbol} from API")
                return None
                
        except Exception as e:
            logger.error(f"Error fetching data for {ticker_symbol}: {e}")
            # Return cached data if available, otherwise None
            if ticker_upper in stock_price_cache:
                return {'price': stock_price_cache[ticker_upper]['price']}
            return None
        finally:
            # Commit any pending API logs
            try:
                from models import db
                db.session.commit()
            except Exception as commit_error:
                logger.error(f"Error committing API logs: {commit_error}")
                try:
                    db.session.rollback()
                except:
                    pass

    def calculate_portfolio_value(self, user_id: int, target_date: date = None) -> float:
        """Calculate total portfolio value for a user on a specific date"""
        if target_date is None:
            target_date = date.today()
        
        user = User.query.get(user_id)
        if not user:
            return 0.0
        
        total_value = 0.0
        
        # Always use Stock table for current portfolio value (most accurate)
        # Transaction table is for historical performance tracking only
        stocks = Stock.query.filter_by(user_id=user_id).all()
        holdings = {}
        for stock in stocks:
            holdings[stock.ticker] = stock.quantity
        
        # Get current prices and calculate value using AlphaVantage
        for ticker, quantity in holdings.items():
            if quantity > 0:  # Only count positive holdings
                try:
                    stock_data = self.get_stock_data(ticker)
                    if stock_data and stock_data.get('price') is not None:
                        price = stock_data['price']
                        total_value += quantity * price
                except Exception as e:
                    logger.error(f"Error fetching price for {ticker}: {e}")
                    # First fallback: try to use any cached price (even if expired)
                    ticker_upper = ticker.upper()
                    if ticker_upper in stock_price_cache and stock_price_cache[ticker_upper].get('price'):
                        cached_price = stock_price_cache[ticker_upper]['price']
                        total_value += quantity * cached_price
                        logger.info(f"Using expired cached price for {ticker}: ${cached_price}")
                    else:
                        # Final fallback: use purchase price from Stock table
                        stock = Stock.query.filter_by(user_id=user_id, ticker=ticker).first()
                        if stock:
                            total_value += quantity * stock.purchase_price
                            logger.info(f"Using purchase price for {ticker}: ${stock.purchase_price}")
        
        return total_value
    
    def create_daily_snapshot(self, user_id: int, target_date: date = None):
        """Create or update daily portfolio snapshot"""
        if target_date is None:
            target_date = date.today()
        
        # Check if snapshot already exists
        existing_snapshot = PortfolioSnapshot.query.filter_by(
            user_id=user_id, date=target_date
        ).first()
        
        portfolio_value = self.calculate_portfolio_value(user_id, target_date)
        
        # Calculate cash flow for the day
        daily_cash_flow = self.calculate_daily_cash_flow(user_id, target_date)
        
        if existing_snapshot:
            existing_snapshot.total_value = portfolio_value
            existing_snapshot.cash_flow = daily_cash_flow
        else:
            snapshot = PortfolioSnapshot(
                user_id=user_id,
                date=target_date,
                total_value=portfolio_value,
                cash_flow=daily_cash_flow
            )
            db.session.add(snapshot)
        
        db.session.commit()
    
    def calculate_daily_cash_flow(self, user_id: int, target_date: date) -> float:
        """Calculate net cash flow (deposits - withdrawals) for a specific date"""
        transactions = Transaction.query.filter(
            and_(
                Transaction.user_id == user_id,
                func.date(Transaction.timestamp) == target_date
            )
        ).all()
        
        cash_flow = 0.0
        for transaction in transactions:
            transaction_value = transaction.quantity * transaction.price
            if transaction.transaction_type == 'buy':
                cash_flow -= transaction_value  # Money out (investment)
            else:  # sell
                cash_flow += transaction_value  # Money in (divestment)
        
        return cash_flow
    
    def calculate_modified_dietz_return(self, user_id: int, start_date: date, end_date: date) -> float:
        """Calculate Modified Dietz return for a period"""
        # Get snapshots for the period
        snapshots = PortfolioSnapshot.query.filter(
            and_(
                PortfolioSnapshot.user_id == user_id,
                PortfolioSnapshot.date >= start_date,
                PortfolioSnapshot.date <= end_date
            )
        ).order_by(PortfolioSnapshot.date).all()
        
        if len(snapshots) < 2:
            return 0.0
        
        beginning_value = snapshots[0].total_value
        ending_value = snapshots[-1].total_value
        
        if beginning_value == 0:
            return 0.0
        
        # Calculate weighted cash flows
        total_days = (end_date - start_date).days
        if total_days == 0:
            return 0.0
        
        weighted_cash_flow = 0.0
        net_cash_flow = 0.0
        
        for snapshot in snapshots[1:]:  # Skip first snapshot
            days_remaining = (end_date - snapshot.date).days
            weight = days_remaining / total_days
            weighted_cash_flow += snapshot.cash_flow * weight
            net_cash_flow += snapshot.cash_flow
        
        # Modified Dietz formula
        denominator = beginning_value + weighted_cash_flow
        if denominator == 0:
            return 0.0
        
        return (ending_value - beginning_value - net_cash_flow) / denominator
    
    def fetch_historical_sp500_data_micro_chunks(self, years_back: int = 5) -> Dict[str, any]:
        """Fetch real historical S&P 500 data in micro chunks to avoid Cloudflare timeouts"""
        logger.info(f"Fetching {years_back} years of S&P 500 data in micro chunks")
        
        total_data_points = 0
        errors = []
        end_date = date.today()
        
        try:
            # Fetch full historical SPY data once (this gets all available data)
            url = f"https://www.alphavantage.co/query"
            params = {
                'function': 'TIME_SERIES_DAILY',
                'symbol': 'SPY',
                'outputsize': 'full',
                'apikey': self.alpha_vantage_api_key
            }
            
            logger.info("Making single AlphaVantage API call for full SPY history...")
            response = requests.get(url, params=params, timeout=20)
            response.raise_for_status()
            data = response.json()
            
            if 'Error Message' in data:
                logger.error(f"AlphaVantage error: {data['Error Message']}")
                return {'success': False, 'error': data['Error Message']}
            
            if 'Time Series (Daily)' not in data:
                logger.error(f"Unexpected AlphaVantage response format: {data.keys()}")
                return {'success': False, 'error': 'Invalid response format'}
            
            time_series = data['Time Series (Daily)']
            logger.info(f"Received {len(time_series)} total data points from AlphaVantage")
            
            # Convert to list and sort by date for processing in chunks
            sorted_data = []
            start_date = end_date - timedelta(days=years_back*365)
            
            for date_str, daily_data in time_series.items():
                try:
                    data_date = datetime.strptime(date_str, '%Y-%m-%d').date()
                    if data_date >= start_date:
                        spy_price = float(daily_data['4. close'])
                        sp500_value = spy_price * 10
                        sorted_data.append((data_date, sp500_value))
                except (ValueError, KeyError) as e:
                    errors.append(f"Error parsing {date_str}: {e}")
                    continue
            
            # Sort by date
            sorted_data.sort(key=lambda x: x[0])
            logger.info(f"Processing {len(sorted_data)} data points in micro chunks")
            
            # Process in very small chunks (50 records at a time)
            chunk_size = 50
            chunks_processed = 0
            
            for i in range(0, len(sorted_data), chunk_size):
                chunk = sorted_data[i:i + chunk_size]
                chunk_data_points = 0
                
                # Process this micro chunk
                for data_date, sp500_value in chunk:
                    try:
                        # Check for existing data
                        existing = MarketData.query.filter_by(
                            ticker='SPY_SP500',
                            date=data_date
                        ).first()
                        
                        if not existing:
                            market_data = MarketData(
                                ticker='SPY_SP500',
                                date=data_date,
                                close_price=sp500_value
                            )
                            db.session.add(market_data)
                            chunk_data_points += 1
                    
                    except Exception as e:
                        errors.append(f"Error processing {data_date}: {e}")
                        continue
                
                # Commit this micro chunk immediately
                try:
                    if chunk_data_points > 0:
                        db.session.commit()
                        total_data_points += chunk_data_points
                        chunks_processed += 1
                        logger.info(f"Committed chunk {chunks_processed}: {chunk_data_points} new data points")
                    else:
                        logger.info(f"Skipped chunk {chunks_processed + 1}: no new data")
                        chunks_processed += 1
                except Exception as e:
                    error_msg = f"Error committing chunk {chunks_processed + 1}: {e}"
                    logger.error(error_msg)
                    errors.append(error_msg)
                    db.session.rollback()
            
            return {
                'success': True,
                'total_data_points': total_data_points,
                'chunks_processed': chunks_processed,
                'years_requested': years_back,
                'errors': errors[:10]  # Limit error list
            }
            
        except Exception as e:
            logger.error(f"Error fetching S&P 500 data: {e}")
            return {'success': False, 'error': str(e)}
    
    def get_sp500_data(self, start_date: date, end_date: date) -> Dict[date, float]:
        """Fetch and cache S&P 500 data using AlphaVantage - optimized for incremental updates"""
        # Check cache first
        cached_data = MarketData.query.filter(
            and_(
                MarketData.ticker == self.sp500_ticker,
                MarketData.date >= start_date,
                MarketData.date <= end_date
            )
        ).all()
        
        cached_dates = {data.date: data.close_price for data in cached_data}
        
        # Only fetch missing dates (incremental approach)
        missing_dates = []
        current_date = start_date
        while current_date <= end_date:
            if current_date not in cached_dates and current_date.weekday() < 5:  # Skip weekends
                missing_dates.append(current_date)
            current_date += timedelta(days=1)
        
        # Only fetch missing recent dates (avoid historical API calls)
        if missing_dates:
            # Only fetch if missing dates are recent (within last 7 days)
            today = date.today()
            recent_missing = [d for d in missing_dates if (today - d).days <= 7]
            
            if recent_missing:
                try:
                    # Single API call for current SPY price (used for all recent missing dates)
                    stock_data = self.get_stock_data('SPY')
                    if stock_data and stock_data.get('price'):
                        sp500_price = stock_data['price'] * 10
                        
                        # Apply to all recent missing dates only
                        for missing_date in recent_missing:
                            market_data = MarketData(
                                ticker=self.sp500_ticker,
                                date=missing_date,
                                close_price=sp500_price
                            )
                            db.session.add(market_data)
                            cached_dates[missing_date] = sp500_price
                            
                except Exception as e:
                    logger.error(f"Error fetching recent S&P 500 data: {e}")
            
            # For older missing dates, use forward-fill from existing data
            old_missing = [d for d in missing_dates if (today - d).days > 7]
            if old_missing and cached_dates:
                # Use the most recent cached price for old missing dates
                recent_prices = [price for date_key, price in cached_dates.items() if (today - date_key).days <= 30]
                if recent_prices:
                    fill_price = recent_prices[-1]  # Most recent price
                    for missing_date in old_missing:
                        cached_dates[missing_date] = fill_price
        
        try:
            db.session.commit()
        except Exception as e:
            logger.error(f"Error committing S&P 500 data: {e}")
        
        return cached_dates
    
    def get_cached_sp500_data(self, start_date: date, end_date: date) -> Dict[date, float]:
        """Get S&P 500 data from cache only - NO API calls for performance charts"""
        try:
            cached_data = MarketData.query.filter(
                and_(
                    MarketData.ticker == self.sp500_ticker,
                    MarketData.date >= start_date,
                    MarketData.date <= end_date
                )
            ).all()
            
            result = {data.date: data.close_price for data in cached_data}
            logger.info(f"Retrieved {len(result)} cached S&P 500 data points for {start_date} to {end_date}")
            return result
            
        except Exception as e:
            logger.error(f"Error retrieving cached S&P 500 data: {e}")
            return {}
    
    def _sample_dates_for_period(self, dates: List[date], period: str) -> List[date]:
        """Sample data points based on period to reduce chart density"""
        if period in ['1D', '5D']:
            return dates  # Show all points for short periods
        elif period == '1M':
            # Show every other day for 1 month
            return dates[::2]
        elif period == '3M':
            # Show weekly points for 3 months
            return dates[::5]
        elif period in ['YTD', '1Y']:
            # Show weekly points for year periods
            return dates[::7]
        elif period == '5Y':
            # Show monthly points for 5 years
            return dates[::20]
        else:
            return dates
    
    def _filter_business_days(self, chart_data: List[dict]) -> List[dict]:
        """Filter out weekend data points for cleaner chart visualization"""
        if not chart_data:
            return chart_data
        
        logger.info(f"WEEKEND FILTER: Processing {len(chart_data)} data points")
        
        business_days_data = []
        weekend_count = 0
        
        for item in chart_data:
            try:
                # Parse the date string to check day of week
                item_date = datetime.strptime(item['date'], '%Y-%m-%d').date()
                weekday = item_date.weekday()
                
                # Monday=0, Sunday=6. Keep Monday-Friday (0-4)
                if weekday < 5:
                    business_days_data.append(item)
                else:
                    weekend_count += 1
                    logger.info(f"WEEKEND FILTER: Removing {item['date']} (weekday={weekday})")
                    
            except (ValueError, KeyError) as e:
                # If date parsing fails, keep the item
                logger.warning(f"WEEKEND FILTER: Date parsing failed for {item}: {e}")
                business_days_data.append(item)
        
        logger.info(f"WEEKEND FILTER: Kept {len(business_days_data)} business days, removed {weekend_count} weekends")
        return business_days_data
    
    def calculate_sp500_return(self, start_date: date, end_date: date) -> float:
        """Calculate S&P 500 return for a period"""
        sp500_data = self.get_sp500_data(start_date, end_date)
        
        if not sp500_data:
            return 0.0
        
        # Get closest dates to start and end
        available_dates = sorted(sp500_data.keys())
        
        start_price = None
        end_price = None
        
        # Find start price (closest date >= start_date)
        for d in available_dates:
            if d >= start_date:
                start_price = sp500_data[d]
                break
        
        # Find end price (closest date <= end_date)
        for d in reversed(available_dates):
            if d <= end_date:
                end_price = sp500_data[d]
                break
        
        if start_price is None or end_price is None or start_price == 0:
            return 0.0
        
        return (end_price - start_price) / start_price
    
    def _sample_dates_for_period(self, dates: List[date], period: str) -> List[date]:
        """Sample dates appropriately for chart display based on period"""
        if not dates:
            return []
        
        # Define target number of points for each period
        target_points = {
            '1D': len(dates),  # Show all points for 1 day
            '5D': len(dates),  # Show all points for 5 days
            '1M': min(len(dates), 30),  # Up to 30 points for 1 month
            '3M': min(len(dates), 60),  # Up to 60 points for 3 months
            'YTD': min(len(dates), 100),  # Up to 100 points for YTD
            '1Y': min(len(dates), 120),  # Up to 120 points for 1 year
            '5Y': min(len(dates), 200)   # Up to 200 points for 5 years
        }
        
        max_points = target_points.get(period, len(dates))
        
        if len(dates) <= max_points:
            return dates
        
        # Sample evenly across the date range
        step = len(dates) // max_points
        sampled = []
        
        for i in range(0, len(dates), step):
            sampled.append(dates[i])
        
        # Always include the last date
        if dates[-1] not in sampled:
            sampled.append(dates[-1])
        
        return sampled
    
    def ensure_snapshots_exist(self, user_id: int, start_date: date, end_date: date):
        """Ensure portfolio snapshots exist for the given period"""
        current_date = start_date
        while current_date <= end_date:
            if current_date.weekday() < 5:  # Only weekdays
                existing = PortfolioSnapshot.query.filter_by(
                    user_id=user_id, date=current_date
                ).first()
                
                if not existing:
                    try:
                        self.create_daily_snapshot(user_id, current_date)
                    except Exception as e:
                        logger.error(f"Error creating snapshot for {current_date}: {e}")
            
            current_date += timedelta(days=1)
    
    def get_intraday_performance_data(self, user_id: int, start_date: date, end_date: date) -> Dict:
        """Get performance data for 1D charts - shows intraday snapshots from today"""
        from models import PortfolioSnapshotIntraday
        
        today = date.today()
        
        # Get all intraday snapshots for today
        intraday_snapshots = PortfolioSnapshotIntraday.query.filter(
            and_(
                PortfolioSnapshotIntraday.user_id == user_id,
                func.date(PortfolioSnapshotIntraday.timestamp) == today
            )
        ).order_by(PortfolioSnapshotIntraday.timestamp.asc()).all()
        
        logger.info(f"Found {len(intraday_snapshots)} intraday snapshots for user {user_id} on {today}")
        
        # If no intraday snapshots, ensure we have at least EOD snapshot
        if not intraday_snapshots:
            self.ensure_snapshots_exist(user_id, today, today)
            # Try to get EOD snapshot as fallback
            eod_snapshot = PortfolioSnapshot.query.filter(
                and_(
                    PortfolioSnapshot.user_id == user_id,
                    PortfolioSnapshot.date == today
                )
            ).first()
            
            if eod_snapshot:
                # Calculate single point performance
                portfolio_return = self.calculate_modified_dietz_return(user_id, today, today)
                sp500_return = self.calculate_sp500_return(today, today)
                
                chart_data = [{
                    'date': today.isoformat(),
                    'portfolio': round(portfolio_return * 100, 2),
                    'sp500': round(sp500_return * 100, 2)
                }]
                
                return {
                    'portfolio_return': round(portfolio_return * 100, 2),
                    'sp500_return': round(sp500_return * 100, 2),
                    'chart_data': chart_data,
                    'period': '1D',
                    'start_date': today.isoformat(),
                    'end_date': today.isoformat()
                }
        
        # Process intraday snapshots for chart
        chart_data = []
        portfolio_start_value = None
        sp500_start_value = None
        
        # Get S&P 500 data for today
        sp500_data = self.get_cached_sp500_data(today, today)
        if sp500_data:
            sp500_start_value = list(sp500_data.values())[0]
        
        # Get user's first snapshot to calculate percentage returns
        if intraday_snapshots:
            portfolio_start_value = intraday_snapshots[0].total_value
        
        for snapshot in intraday_snapshots:
            # Calculate portfolio percentage return from start of day
            portfolio_pct = 0.0
            if portfolio_start_value and portfolio_start_value > 0:
                portfolio_pct = ((snapshot.total_value - portfolio_start_value) / portfolio_start_value) * 100
            
            # Calculate S&P 500 percentage return (use same value for intraday - we collect SPY once per collection)
            sp500_pct = 0.0
            if sp500_start_value and sp500_data:
                current_sp500 = list(sp500_data.values())[0]  # Use today's SPY value
                sp500_pct = ((current_sp500 - sp500_start_value) / sp500_start_value) * 100
            
            chart_data.append({
                'date': snapshot.timestamp.isoformat(),
                'portfolio': round(portfolio_pct, 2),
                'sp500': round(sp500_pct, 2)
            })
        
        # Calculate overall returns for display
        portfolio_return = 0.0
        sp500_return = 0.0
        
        if chart_data:
            portfolio_return = chart_data[-1]['portfolio']  # Last data point
            sp500_return = chart_data[-1]['sp500']
        
        return {
            'portfolio_return': portfolio_return,
            'sp500_return': sp500_return,
            'chart_data': chart_data,
            'period': '1D',
            'start_date': today.isoformat(),
            'end_date': today.isoformat()
        }
    
    def check_portfolio_snapshots_coverage(self, user_id: int) -> Dict:
        """Check portfolio snapshots coverage for a user"""
        try:
            snapshots = PortfolioSnapshot.query.filter_by(user_id=user_id).order_by(PortfolioSnapshot.date).all()
            
            if not snapshots:
                return {
                    'success': False,
                    'message': 'No portfolio snapshots found',
                    'coverage': {
                        'total_snapshots': 0,
                        'earliest_date': None,
                        'latest_date': None,
                        'days_covered': 0
                    }
                }
            
            earliest = snapshots[0].date
            latest = snapshots[-1].date
            days_covered = (latest - earliest).days + 1
            
            # Check for gaps in coverage
            expected_snapshots = []
            current_date = earliest
            while current_date <= latest:
                if current_date.weekday() < 5:  # Only weekdays
                    expected_snapshots.append(current_date)
                current_date += timedelta(days=1)
            
            actual_dates = {s.date for s in snapshots}
            missing_dates = [d for d in expected_snapshots if d not in actual_dates]
            
            return {
                'success': True,
                'coverage': {
                    'total_snapshots': len(snapshots),
                    'earliest_date': earliest.isoformat(),
                    'latest_date': latest.isoformat(),
                    'days_covered': days_covered,
                    'expected_weekday_snapshots': len(expected_snapshots),
                    'missing_snapshots': len(missing_dates),
                    'coverage_percentage': round((len(snapshots) / len(expected_snapshots)) * 100, 1) if expected_snapshots else 0,
                    'sample_recent': [
                        {'date': s.date.isoformat(), 'value': s.total_value}
                        for s in snapshots[-5:]
                    ]
                }
            }
            
        except Exception as e:
            logger.error(f"Error checking portfolio snapshots coverage: {e}")
            return {'success': False, 'error': str(e)}

    def get_performance_data(self, user_id: int, period: str) -> Dict:
        """Get performance data for a specific period"""
        # Use last market day for weekend handling
        from datetime import timedelta
        today = date.today()
        
        # If it's Saturday (5) or Sunday (6), go back to Friday
        if today.weekday() == 5:  # Saturday
            end_date = today - timedelta(days=1)  # Friday
        elif today.weekday() == 6:  # Sunday
            end_date = today - timedelta(days=2)  # Friday
        else:
            end_date = today  # Monday-Friday
        
        # Define period mappings
        period_days = {
            '1D': 1,
            '5D': 5,  # Exactly 5 calendar days
            '1M': 30,
            '3M': 90,
            'YTD': (end_date - date(end_date.year, 1, 1)).days,
            '1Y': 365,
            '5Y': 1825
        }
        
        if period not in period_days:
            return {'error': 'Invalid period'}
        
        if period == 'YTD':
            start_date = date(end_date.year, 1, 1)
        else:
            start_date = end_date - timedelta(days=period_days[period])
        
        # For 1D charts, use intraday data if available
        if period == '1D':
            return self.get_intraday_performance_data(user_id, start_date, end_date)
        
        # Ensure we have snapshots for the period
        self.ensure_snapshots_exist(user_id, start_date, end_date)
        
        # Calculate portfolio return
        portfolio_return = self.calculate_modified_dietz_return(user_id, start_date, end_date)
        
        # Calculate S&P 500 return (cached data only)
        sp500_return = self.calculate_sp500_return(start_date, end_date)
        
        # Get portfolio values for charting (database only)
        snapshots = PortfolioSnapshot.query.filter(
            and_(
                PortfolioSnapshot.user_id == user_id,
                PortfolioSnapshot.date >= start_date,
                PortfolioSnapshot.date <= end_date
            )
        ).order_by(PortfolioSnapshot.date).all()
        
        # Get S&P 500 data for charting (always use cached daily data - updated at 9PM)
        sp500_data = self.get_cached_sp500_data(start_date, end_date)
        
        # Normalize both to percentage change from start
        chart_data = []
        
        # Get user's actual portfolio start date (first snapshot)
        user_first_snapshot = PortfolioSnapshot.query.filter_by(user_id=user_id)\
            .order_by(PortfolioSnapshot.date.asc()).first()
        
        if snapshots and sp500_data:
            # Find S&P 500 data for the full period (always show full S&P line)
            sp500_dates = sorted(sp500_data.keys())
            if sp500_dates:
                period_start_sp500 = None
                for date_key in sp500_dates:
                    if date_key >= start_date:
                        period_start_sp500 = sp500_data[date_key]
                        break
                
                if period_start_sp500:
                    # Sample data points for chart density
                    sampled_dates = self._sample_dates_for_period(sp500_dates, period)
                    
                    for date_key in sampled_dates:
                        if date_key >= start_date and date_key in sp500_data:
                            sp500_pct = ((sp500_data[date_key] - period_start_sp500) / period_start_sp500) * 100
                            
                            # Only include portfolio data from user's actual start date
                            portfolio_pct = None
                            if user_first_snapshot and date_key >= user_first_snapshot.date and len(snapshots) > 0:
                                # Find portfolio snapshot for this date
                                portfolio_snapshot = next((s for s in snapshots if s.date == date_key), None)
                                if portfolio_snapshot and snapshots[0].total_value > 0:
                                    start_portfolio_value = snapshots[0].total_value
                                    portfolio_pct = ((portfolio_snapshot.total_value - start_portfolio_value) / start_portfolio_value) * 100
                            
                            chart_data.append({
                                'date': date_key.isoformat(),
                                'portfolio': round(portfolio_pct, 2) if portfolio_pct is not None else None,
                                'sp500': round(sp500_pct, 2)
                            })
        
        # Always show S&P 500 data if available (even with limited portfolio history)
        if not chart_data and sp500_data:
            # Only S&P 500 data available (show market benchmark even without portfolio history)
            sp500_dates = sorted(sp500_data.keys())
            if sp500_dates:
                start_sp500_value = sp500_data[sp500_dates[0]]
                
                # Sample data points for longer periods to reduce chart density
                sampled_dates = self._sample_dates_for_period(sp500_dates, period)
                
                for date_key in sampled_dates:
                    if date_key in sp500_data:
                        sp500_pct = ((sp500_data[date_key] - start_sp500_value) / start_sp500_value) * 100
                        
                        chart_data.append({
                            'date': date_key.isoformat(),
                            'portfolio': 0,  # No portfolio data available
                            'sp500': round(sp500_pct, 2)
                        })
        
        # Filter out weekends from chart data for cleaner visualization
        chart_data = self._filter_business_days(chart_data)
        
        return {
            'portfolio_return': round(portfolio_return * 100, 2),
            'sp500_return': round(sp500_return * 100, 2),
            'chart_data': chart_data,
            'period': period,
            'start_date': start_date.isoformat(),
            'end_date': end_date.isoformat()
        }

# Global instance
performance_calculator = PortfolioPerformanceCalculator()
