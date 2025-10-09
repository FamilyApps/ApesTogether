"""
Portfolio performance calculation using Modified Dietz method and market benchmarking.
"""
import requests
import os
from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo
import logging
from typing import Dict, List
from models import PortfolioSnapshot, MarketData, Stock, Transaction, User, db
from sqlalchemy import func, and_, or_
try:
    from timezone_utils import get_market_timezone, is_market_hours
except ImportError:
    # Fallback if timezone_utils not available
    def get_market_timezone():
        try:
            import pytz
            return pytz.timezone('US/Eastern')
        except ImportError:
            from datetime import timezone
            return timezone.utc
    
    def is_market_hours(dt=None):
        return True  # Fallback - assume always market hours

logger = logging.getLogger(__name__)

# Market timezone configuration (Eastern Time for US Stock Market)
MARKET_TZ = ZoneInfo('America/New_York')

def get_market_date():
    """Get current date in Eastern Time (not UTC)
    
    CRITICAL: Vercel runs in UTC. date.today() returns UTC date which causes
    +1 day offset after 8 PM ET (midnight UTC). Always use this for market dates.
    """
    return datetime.now(MARKET_TZ).date()

# Cache for stock prices (90-second caching like existing system)
stock_price_cache = {}
cache_duration = 90

class PortfolioPerformanceCalculator:
    """Calculate portfolio performance using Modified Dietz method"""
    
    def __init__(self):
        self.sp500_ticker = "SPY_SP500"  # S&P 500 proxy using SPY
        self.alpha_vantage_api_key = os.environ.get('ALPHA_VANTAGE_API_KEY')
        self.historical_price_cache = {}  # Cache for historical prices during batch operations
    
    def get_stock_data(self, ticker_symbol: str) -> Dict:
        """Fetches stock data using AlphaVantage API with caching (same as existing system)"""
        # Check if it's weekend - don't make API calls on weekends
        current_time = datetime.now()
        if current_time.weekday() >= 5:  # Saturday = 5, Sunday = 6
            logger.info(f"Weekend detected - skipping API call for {ticker_symbol}, using cache only")
            # Return cached data if available, otherwise return None
            ticker_upper = ticker_symbol.upper()
            if ticker_upper in stock_price_cache:
                cached_data = stock_price_cache[ticker_upper]
                return {'price': cached_data['price']}
            return None
        
        # Check cache first
        ticker_upper = ticker_symbol.upper()
        
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
            
            # Use Alpha Vantage API with real-time entitlement and slight delay to avoid rate limiting
            import time
            time.sleep(0.1)  # 100ms delay between API calls
            
            url = f'https://www.alphavantage.co/query?function=GLOBAL_QUOTE&symbol={ticker_symbol}&entitlement=realtime&apikey={api_key}'
            response = requests.get(url, timeout=5)
            data = response.json()
            
            # Log the API call (but don't commit immediately for performance)
            try:
                from models import AlphaVantageAPILog, db
                success = 'Global Quote' in data and '05. price' in data.get('Global Quote', {})
                
                # Add extra logging for weekend API calls to track source
                if current_time.weekday() >= 5:
                    logger.warning(f"WEEKEND API CALL DETECTED: {ticker_symbol} - This should not happen!")
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
                
                # Enhanced logging for debugging stale data
                logger.info(f"✅ Alpha Vantage API: {ticker_symbol} = ${price} at {current_time.strftime('%H:%M:%S')}")
                logger.debug(f"Full API response for {ticker_symbol}: {data}")
                
                return {'price': price}
            else:
                logger.warning(f"❌ Could not get price for {ticker_symbol} from API - Response: {data}")
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
    
    def get_historical_price(self, ticker: str, target_date: date, force_fetch: bool = False) -> float:
        """
        Get historical closing price for a ticker on a specific date.
        
        Order of precedence:
        1. Local cache (for batch operations)
        2. MarketData table (database cache) - unless force_fetch=True
        3. Alpha Vantage TIME_SERIES_DAILY API
        
        Args:
            ticker: Stock ticker symbol
            target_date: Date to get price for
            force_fetch: If True, skip cache and fetch from API to populate all dates
        
        Returns None if price cannot be found.
        """
        ticker_upper = ticker.upper()
        cache_key = f"{ticker_upper}_{target_date.isoformat()}"
        
        # Check local cache first (for batch operations)
        if not force_fetch and cache_key in self.historical_price_cache:
            logger.info(f"Using local cache for {ticker} on {target_date}: ${self.historical_price_cache[cache_key]}")
            return self.historical_price_cache[cache_key]
        
        # Check MarketData table (unless forced to fetch)
        if not force_fetch:
            market_data = MarketData.query.filter_by(
                ticker=ticker_upper,
                date=target_date
            ).first()
            
            if market_data and market_data.close_price:
                price = float(market_data.close_price)
                self.historical_price_cache[cache_key] = price
                logger.info(f"Using database cache for {ticker} on {target_date}: ${price}")
                return price
        
        # Fetch from Alpha Vantage API
        logger.info(f"Fetching historical price from API for {ticker} on {target_date}")
        
        try:
            if not self.alpha_vantage_api_key:
                logger.warning("Alpha Vantage API key not found")
                return None
            
            import time
            time.sleep(0.15)  # Rate limit: ~7 calls per second
            
            # Use compact (100 days) which should cover our date range and works on all API tiers
            url = f'https://www.alphavantage.co/query?function=TIME_SERIES_DAILY&symbol={ticker}&outputsize=compact&apikey={self.alpha_vantage_api_key}'
            response = requests.get(url, timeout=10)
            data = response.json()
            
            # Log API call
            try:
                from models import AlphaVantageAPILog
                api_log = AlphaVantageAPILog(
                    endpoint='TIME_SERIES_DAILY',
                    symbol=ticker_upper,
                    response_status='success' if 'Time Series (Daily)' in data else 'error',
                    timestamp=datetime.now()
                )
                db.session.add(api_log)
            except Exception as log_error:
                logger.error(f"Failed to log API call: {log_error}")
            
            if 'Time Series (Daily)' not in data:
                logger.warning(f"No time series data for {ticker}: {data.get('Note', data.get('Error Message', 'Unknown error'))}")
                return None
            
            time_series = data['Time Series (Daily)']
            
            # Log how many days the API actually returned
            total_days_in_response = len(time_series)
            logger.info(f"📊 API returned {total_days_in_response} days for {ticker}")
            
            # CRITICAL: Store ALL dates from the API response (100+ days), not just the requested date
            stored_count = 0
            for date_str, price_data in time_series.items():
                try:
                    date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
                    close_price = float(price_data['4. close'])
                    
                    # Check if already exists
                    existing = MarketData.query.filter_by(
                        ticker=ticker_upper,
                        date=date_obj
                    ).first()
                    
                    if not existing:
                        new_market_data = MarketData(
                            ticker=ticker_upper,
                            date=date_obj,
                            close_price=close_price
                        )
                        db.session.add(new_market_data)
                        stored_count += 1
                        
                        # Cache locally
                        local_cache_key = f"{ticker_upper}_{date_obj.isoformat()}"
                        self.historical_price_cache[local_cache_key] = close_price
                    
                except Exception as e:
                    logger.error(f"Error storing price for {ticker} on {date_str}: {e}")
                    continue
            
            try:
                db.session.commit()
                logger.info(f"✅ Stored {stored_count} NEW days of data for {ticker} (API returned {total_days_in_response} total days)")
            except Exception as db_error:
                logger.error(f"❌ Failed to commit historical prices for {ticker}: {db_error}")
                import traceback
                logger.error(traceback.format_exc())
                db.session.rollback()
            
            # Now return the price for the requested date
            target_date_str = target_date.isoformat()
            if target_date_str in time_series:
                return float(time_series[target_date_str]['4. close'])
            else:
                # Find nearest previous trading day
                available_dates = sorted(time_series.keys(), reverse=True)
                for date_str in available_dates:
                    if date_str <= target_date_str:
                        return float(time_series[date_str]['4. close'])
                
                logger.error(f"No historical data found for {ticker} before {target_date}")
                return None
                
        except Exception as e:
            logger.error(f"Error fetching historical price for {ticker} on {target_date}: {e}")
            return None

    def calculate_portfolio_value(self, user_id: int, target_date: date = None) -> float:
        """
        Calculate total portfolio value for a user on a specific date.
        
        For current date: Uses Stock table + live prices
        For historical dates: Reconstructs holdings from transactions + historical prices
        """
        if target_date is None:
            target_date = get_market_date()  # Use ET date, not UTC
        
        user = User.query.get(user_id)
        if not user:
            return 0.0
        
        today = get_market_date()
        is_historical = target_date < today
        
        total_value = 0.0
        holdings = {}
        
        if is_historical:
            # For historical dates: Reconstruct holdings from transaction history
            logger.info(f"Calculating HISTORICAL portfolio value for user {user_id} on {target_date}")
            
            transactions = Transaction.query.filter(
                Transaction.user_id == user_id,
                func.date(Transaction.timestamp) <= target_date
            ).order_by(Transaction.timestamp).all()
            
            # Replay transactions to get holdings as of target_date
            for txn in transactions:
                ticker = txn.ticker
                if ticker not in holdings:
                    holdings[ticker] = 0.0
                
                if txn.transaction_type in ('buy', 'initial'):
                    holdings[ticker] += txn.quantity
                elif txn.transaction_type == 'sell':
                    holdings[ticker] -= txn.quantity
            
            # Get historical prices for each holding
            for ticker, quantity in holdings.items():
                if quantity > 0:
                    price = self.get_historical_price(ticker, target_date)
                    
                    if price is None:
                        logger.warning(f"No historical price for {ticker} on {target_date}, skipping")
                        continue
                    
                    value = quantity * price
                    total_value += value
                    logger.info(f"  {ticker}: {quantity} shares × ${price} = ${value:.2f}")
        
        else:
            # For current date: Use Stock table (most accurate) + live prices
            logger.info(f"Calculating CURRENT portfolio value for user {user_id}")
            
            stocks = Stock.query.filter_by(user_id=user_id).all()
            for stock in stocks:
                holdings[stock.ticker] = stock.quantity
            
            # Get current prices
            for ticker, quantity in holdings.items():
                if quantity > 0:
                    price = None
                    
                    try:
                        stock_data = self.get_stock_data(ticker)
                        if stock_data and stock_data.get('price') is not None:
                            price = stock_data['price']
                    except Exception as e:
                        logger.error(f"Error fetching price for {ticker}: {e}")
                    
                    # Fallback logic
                    if price is None:
                        ticker_upper = ticker.upper()
                        if ticker_upper in stock_price_cache and stock_price_cache[ticker_upper].get('price'):
                            cached_price = stock_price_cache[ticker_upper]['price']
                            price = cached_price
                            logger.info(f"Using expired cached price for {ticker}: ${cached_price}")
                        else:
                            stock = Stock.query.filter_by(user_id=user_id, ticker=ticker).first()
                            if stock and stock.purchase_price:
                                price = stock.purchase_price
                                logger.warning(f"API and cache failed for {ticker}, using purchase price: ${stock.purchase_price}")
                            else:
                                logger.error(f"No price available for {ticker} (quantity {quantity}) - skipping stock!")
                                continue
                    
                    if price and price > 0:
                        total_value += quantity * price
        
        logger.info(f"Total portfolio value for user {user_id} on {target_date}: ${total_value:.2f}")
        return total_value
    
    def create_daily_snapshot(self, user_id: int, target_date: date = None):
        """Create or update daily portfolio snapshot with cash tracking"""
        if target_date is None:
            target_date = get_market_date()  # Use ET date, not UTC
        
        # DEFENSIVE FIX: Check if user has any holdings on or before target_date
        # Don't create bogus $0 snapshots before user's first transaction
        first_transaction = Transaction.query.filter(
            Transaction.user_id == user_id,
            func.date(Transaction.timestamp) <= target_date
        ).order_by(Transaction.timestamp.asc()).first()
        
        if not first_transaction:
            logger.info(f"Skipping snapshot for user {user_id} on {target_date} - no holdings yet")
            return  # No holdings on this date, don't create snapshot
        
        # Check if snapshot already exists
        existing_snapshot = PortfolioSnapshot.query.filter_by(
            user_id=user_id, date=target_date
        ).first()
        
        # Calculate portfolio value with cash breakdown
        from cash_tracking import calculate_portfolio_value_with_cash
        portfolio_breakdown = calculate_portfolio_value_with_cash(user_id, target_date)
        
        # Get user's max_cash_deployed
        user = User.query.get(user_id)
        max_cash_deployed = user.max_cash_deployed if user else 0.0
        
        # Calculate cash flow for the day
        daily_cash_flow = self.calculate_daily_cash_flow(user_id, target_date)
        
        if existing_snapshot:
            # Update existing snapshot with all cash tracking fields
            existing_snapshot.total_value = portfolio_breakdown['total_value']
            existing_snapshot.stock_value = portfolio_breakdown['stock_value']
            existing_snapshot.cash_proceeds = portfolio_breakdown['cash_proceeds']
            existing_snapshot.max_cash_deployed = max_cash_deployed
            existing_snapshot.cash_flow = daily_cash_flow
        else:
            # Create new snapshot with all cash tracking fields
            snapshot = PortfolioSnapshot(
                user_id=user_id,
                date=target_date,
                total_value=portfolio_breakdown['total_value'],
                stock_value=portfolio_breakdown['stock_value'],
                cash_proceeds=portfolio_breakdown['cash_proceeds'],
                max_cash_deployed=max_cash_deployed,
                cash_flow=daily_cash_flow
            )
            db.session.add(snapshot)
        
        db.session.commit()
    
    def calculate_daily_cash_flow(self, user_id: int, target_date: date) -> float:
        """Calculate net cash flow (external deposits/withdrawals) for a specific date
        
        CRITICAL FIX (Grok-validated): In a stock-only portfolio where users don't deposit/withdraw cash,
        stock purchases = EXTERNAL DEPOSITS (adding value to portfolio)
        stock sales = EXTERNAL WITHDRAWALS (removing value from portfolio)
        
        Modified Dietz formula: return = (end_value - start_value - net_cash_flow) / (start_value + weighted_cash_flow)
        If buy/sell were treated as internal reallocations (cash_flow = 0), the formula would be wrong.
        """
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
                cash_flow += transaction_value  # ✅ External deposit (user adds stock to portfolio)
            else:  # sell
                cash_flow -= transaction_value  # ✅ External withdrawal (user removes stock from portfolio)
        
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
        end_date = get_market_date()  # Use ET date, not UTC
        
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
                        # Log successful API call with timestamp for debugging
                        current_time = datetime.now().strftime('%H:%M:%S')
                        logger.info(f"Successfully fetched {ticker_symbol} price: ${price} from Alpha Vantage at {current_time}")
                        logger.debug(f"Alpha Vantage raw response for {ticker_symbol}: {data}")
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
            today = get_market_date()  # Use ET date, not UTC
            recent_missing = [d for d in missing_dates if (today - d).days <= 7]
            
            # Don't make API calls on weekends
            if recent_missing and today.weekday() < 5:  # Monday-Friday only
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
            
            if result:
                sorted_dates = sorted(result.keys())
                logger.info(f"S&P 500 date range: {sorted_dates[0]} to {sorted_dates[-1]}")
                # Check for recent dates
                from datetime import timedelta
                today = get_market_date()
                for i in range(5):
                    check_date = today - timedelta(days=i)
                    if check_date in result:
                        logger.info(f"  ✓ S&P data exists for {check_date}")
                    else:
                        logger.warning(f"  ✗ S&P data MISSING for {check_date}")
            
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
                # Parse the date string - support both 'Oct 03' and '2025-10-03' formats
                date_str = item['date']
                try:
                    # Try ISO format first
                    item_date = datetime.strptime(date_str, '%Y-%m-%d').date()
                except ValueError:
                    # Try short format like 'Oct 03'
                    current_year = datetime.now().year
                    item_date = datetime.strptime(f"{current_year} {date_str}", '%Y %b %d').date()
                
                weekday = item_date.weekday()
                
                # Monday=0, Sunday=6. Keep Monday-Friday (0-4)
                if weekday < 5:
                    business_days_data.append(item)
                else:
                    weekend_count += 1
                    logger.debug(f"WEEKEND FILTER: Removing {date_str} (weekend)")
                    
            except (ValueError, KeyError) as e:
                # If date parsing fails, keep the item (shouldn't happen now)
                logger.warning(f"WEEKEND FILTER: Date parsing failed for {item}: {e}")
                business_days_data.append(item)
        
        logger.info(f"WEEKEND FILTER: Kept {len(business_days_data)} business days, removed {weekend_count} weekends")
        return business_days_data
    
    def calculate_sp500_return(self, start_date: date, end_date: date) -> float:
        """Calculate S&P 500 return for a period"""
        # Use cached data only on weekends to avoid API call issues
        current_time = datetime.now()
        if current_time.weekday() >= 5:  # Weekend
            sp500_data = self.get_cached_sp500_data(start_date, end_date)
        else:
            sp500_data = self.get_sp500_data(start_date, end_date)
        
        if not sp500_data:
            logger.warning(f"No S&P 500 data found for period {start_date} to {end_date}")
            return 0.0
        
        # Get closest dates to start and end
        available_dates = sorted(sp500_data.keys())
        
        start_price = None
        end_price = None
        
        # Find start price (closest date >= start_date)
        for d in available_dates:
            if d >= start_date:
                start_price = sp500_data[d]
                logger.info(f"YTD S&P 500 start price: {start_price} on {d}")
                break
        
        # Find end price (closest date <= end_date)
        for d in reversed(available_dates):
            if d <= end_date:
                end_price = sp500_data[d]
                break
        
        if start_price is None or end_price is None or start_price == 0:
            logger.warning(f"S&P 500 calculation failed: start_price={start_price}, end_price={end_price}, available_dates={len(available_dates)} dates from {available_dates[0] if available_dates else 'None'} to {available_dates[-1] if available_dates else 'None'}")
            return 0.0
        
        sp500_return = (end_price - start_price) / start_price
        logger.info(f"S&P 500 return calculated: {sp500_return:.4f} ({sp500_return*100:.2f}%) from {start_price:.2f} to {end_price:.2f}")
        return sp500_return
    
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
        
        today = get_market_date()  # Use ET date, not UTC
        
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
        
        # Get S&P 500 intraday data for today
        sp500_intraday_data = MarketData.query.filter(
            and_(
                MarketData.ticker == 'SPY_INTRADAY',
                MarketData.date == today
            )
        ).order_by(MarketData.timestamp.asc()).all()
        
        logger.info(f"Found {len(sp500_intraday_data)} SPY intraday data points for {today}")
        
        sp500_start_value = None
        if sp500_intraday_data:
            sp500_start_value = sp500_intraday_data[0].close_price
        
        # Get user's first snapshot to calculate percentage returns
        if intraday_snapshots:
            portfolio_start_value = intraday_snapshots[0].total_value
        
        for i, snapshot in enumerate(intraday_snapshots):
            # Calculate portfolio percentage return from start of day
            portfolio_pct = 0.0
            if portfolio_start_value and portfolio_start_value > 0:
                portfolio_pct = ((snapshot.total_value - portfolio_start_value) / portfolio_start_value) * 100
            
            # Calculate S&P 500 percentage return using matching intraday data
            sp500_pct = 0.0
            if sp500_start_value and sp500_start_value > 0:
                if i < len(sp500_intraday_data):
                    current_sp500 = sp500_intraday_data[i].close_price
                    sp500_pct = ((current_sp500 - sp500_start_value) / sp500_start_value) * 100
                elif sp500_intraday_data:
                    # Fallback to latest SPY data if we don't have matching timestamp
                    current_sp500 = sp500_intraday_data[-1].close_price
                    sp500_pct = ((current_sp500 - sp500_start_value) / sp500_start_value) * 100
            
            logger.debug(f"Snapshot {i}: Portfolio {portfolio_pct:.2f}%, S&P500 {sp500_pct:.2f}% (start: {sp500_start_value}, current: {sp500_intraday_data[i].close_price if i < len(sp500_intraday_data) else 'N/A'})")
            
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
        """Get performance data"""
        # Calculate date range based on period - use last market day for weekends
        # Use timezone-aware calculations for DST handling
        from datetime import timezone, timedelta
        eastern_tz = get_market_timezone()
        today = get_market_date()  # Use ET date, not UTC
        
        # If it's Saturday (5) or Sunday (6), go back to Friday
        if today.weekday() == 5:  # Saturday
            end_date = today - timedelta(days=1)  # Friday
        elif today.weekday() == 6:  # Sunday
            end_date = today - timedelta(days=2)  # Friday
        else:
            end_date = today  # Monday-Friday
        
        logger.info(f"Chart generation: today={today} ({today.strftime('%A')}), end_date={end_date} ({end_date.strftime('%A')})")
        
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
        
        # Get user's first snapshot to handle partial period data
        user_first_snapshot = PortfolioSnapshot.query.filter_by(user_id=user_id)\
            .order_by(PortfolioSnapshot.date.asc()).first()
        
        # Ensure we have snapshots for dates when user actually had holdings
        # (Don't try to create snapshots before user's first holdings date)
        if user_first_snapshot:
            snapshot_start = max(start_date, user_first_snapshot.date)
            self.ensure_snapshots_exist(user_id, snapshot_start, end_date)
        else:
            # No holdings yet, still ensure today's snapshot exists
            self.ensure_snapshots_exist(user_id, end_date, end_date)
        
        # Calculate portfolio return
        # If user's first holdings is after period start, calculate return from first holdings date
        portfolio_calc_start = start_date
        if user_first_snapshot and user_first_snapshot.date > start_date:
            portfolio_calc_start = user_first_snapshot.date
            logger.info(f"User's first holdings {user_first_snapshot.date} is after period start {start_date}. Calculating return from first holdings.")
        
        portfolio_return = self.calculate_modified_dietz_return(user_id, portfolio_calc_start, end_date)
        
        # Get portfolio values for charting (database only)
        snapshots = PortfolioSnapshot.query.filter(
            and_(
                PortfolioSnapshot.user_id == user_id,
                PortfolioSnapshot.date >= start_date,
                PortfolioSnapshot.date <= end_date
            )
        ).order_by(PortfolioSnapshot.date).all()
        
        logger.info(f"Retrieved {len(snapshots)} snapshots for period {period}: {start_date} to {end_date}")
        if snapshots:
            logger.info(f"First snapshot: {snapshots[0].date}, Last snapshot: {snapshots[-1].date}")
        
        # Get S&P 500 data for charting (always use cached daily data - updated at 9PM)
        sp500_data = self.get_cached_sp500_data(start_date, end_date)
        
        # Normalize both to percentage change from start
        chart_data = []
        
        # Note: user_first_snapshot already retrieved above (line 1021-1022)
        
        # DIAGNOSTIC LOGGING for 1M scale issue (investigate, don't change logic yet)
        if period == '1M' and snapshots:
            logger.info(f"=== 1M CHART DIAGNOSTIC ===")
            logger.info(f"Period: {period}, User: {user_id}")
            logger.info(f"Query date range: {start_date} to {end_date}")
            logger.info(f"Total snapshots retrieved: {len(snapshots)}")
            logger.info(f"First snapshot in period: date={snapshots[0].date}, value=${snapshots[0].total_value:.2f}")
            logger.info(f"Last snapshot in period: date={snapshots[-1].date}, value=${snapshots[-1].total_value:.2f}")
            logger.info(f"User's first ever snapshot: date={user_first_snapshot.date if user_first_snapshot else 'None'}, value=${user_first_snapshot.total_value if user_first_snapshot else 0:.2f}")
            if snapshots[0].total_value > 0:
                period_based_return = ((snapshots[-1].total_value - snapshots[0].total_value) / snapshots[0].total_value) * 100
                logger.info(f"Expected 1M return (from period baseline): {period_based_return:.2f}%")
            logger.info(f"This should match the 1M percentage displayed on the card and chart")
        
        if snapshots and sp500_data:
            # Find S&P 500 data for the full period (always show full S&P line)
            sp500_dates = sorted(sp500_data.keys())
            if sp500_dates:
                period_start_sp500 = None
                for date_key in sp500_dates:
                    if date_key >= start_date:
                        period_start_sp500 = sp500_data[date_key]
                        if period == '1M':
                            logger.info(f"S&P baseline for 1M: date={date_key}, value=${period_start_sp500:.2f}")
                        break
                
                if period_start_sp500:
                    # Sample data points for chart density
                    sampled_dates = self._sample_dates_for_period(sp500_dates, period)
                    
                    # DEFENSIVE FIX: Find first non-zero snapshot as baseline (handles bogus $0 snapshots)
                    start_portfolio_value = None
                    start_portfolio_index = None
                    for i, s in enumerate(snapshots):
                        if s.total_value > 0:
                            start_portfolio_value = s.total_value
                            start_portfolio_index = i
                            break
                    
                    if start_portfolio_value is None:
                        # All snapshots are $0 (no holdings in period) - skip portfolio line
                        logger.warning(f"No non-zero snapshots for user {user_id} in period {period} - portfolio line will be null")
                    
                    for date_key in sampled_dates:
                        if date_key >= start_date and date_key in sp500_data:
                            sp500_pct = ((sp500_data[date_key] - period_start_sp500) / period_start_sp500) * 100
                            
                            # Only include portfolio data from user's actual holdings date
                            portfolio_pct = None
                            if start_portfolio_value is not None and user_first_snapshot and date_key >= user_first_snapshot.date and len(snapshots) > 0:
                                # Find portfolio snapshot for this date
                                portfolio_snapshot = next((s for s in snapshots if s.date == date_key), None)
                                # Calculate percentage from first non-zero snapshot (defensive against bogus $0 snapshots)
                                if portfolio_snapshot and portfolio_snapshot.total_value > 0:
                                    portfolio_pct = ((portfolio_snapshot.total_value - start_portfolio_value) / start_portfolio_value) * 100
                            
                            # FIX (Grok-validated): Use short date format for category scale (multi-day periods)
                            # Category scale needs discrete labels like 'Sep 26', not ISO dates
                            # Ensure we're working with date object, not datetime with time component
                            date_only = date_key.date() if hasattr(date_key, 'date') else date_key
                            date_label = date_only.strftime('%b %d') if period != '1D' else date_key.isoformat()
                            
                            chart_data.append({
                                'date': date_label,
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
                        
                        # Use short date format for category scale (multi-day periods)
                        date_only = date_key.date() if hasattr(date_key, 'date') else date_key
                        date_label = date_only.strftime('%b %d') if period != '1D' else date_key.isoformat()
                        
                        chart_data.append({
                            'date': date_label,
                            'portfolio': 0,  # No portfolio data available
                            'sp500': round(sp500_pct, 2)
                        })
        
        # Filter out weekends from chart data for cleaner visualization
        chart_data = self._filter_business_days(chart_data)
        
        # FIX: Extract S&P return from chart data for consistency (Grok-approved)
        # This ensures card header ALWAYS matches chart's last data point
        # Previously used separate calculate_sp500_return() which could use different data source
        sp500_return = 0.0
        if chart_data and len(chart_data) > 0:
            # Get last S&P value from chart (already a percentage)
            last_sp500_pct = chart_data[-1].get('sp500', 0)
            sp500_return = last_sp500_pct / 100  # Convert back to decimal for consistency
            logger.info(f"S&P 500 return extracted from chart: {sp500_return*100:.2f}% (last point: {last_sp500_pct}%)")
        else:
            # Fallback if no chart data (shouldn't happen, but defensive)
            sp500_return = self.calculate_sp500_return(start_date, end_date)
            logger.warning(f"No chart data available, using fallback S&P calculation: {sp500_return*100:.2f}%")
        
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
