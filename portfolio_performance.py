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
        self.sp500_symbol = "SPY_SP500"  # S&P 500 proxy using SPY
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
                logger.warning("Alpha Vantage API key not found, using mock data")
                # Mock prices for common stocks
                mock_prices = {
                    'AAPL': 185.92, 'MSFT': 420.45, 'GOOGL': 175.33, 'AMZN': 182.81,
                    'TSLA': 248.29, 'META': 475.12, 'NVDA': 116.64, '^GSPC': 4500.00
                }
                price = mock_prices.get(ticker_upper, 100.00)
                stock_price_cache[ticker_upper] = {'price': price, 'timestamp': current_time}
                return {'price': price}
            
            # Use Alpha Vantage API
            url = f'https://www.alphavantage.co/query?function=GLOBAL_QUOTE&symbol={ticker_symbol}&apikey={api_key}'
            response = requests.get(url, timeout=5)
            data = response.json()
            
            if 'Global Quote' in data and '05. price' in data['Global Quote']:
                price = float(data['Global Quote']['05. price'])
                stock_price_cache[ticker_upper] = {'price': price, 'timestamp': current_time}
                return {'price': price}
            else:
                logger.warning(f"Could not get price for {ticker_symbol}, using fallback")
                # Fallback to cached price or mock data
                mock_prices = {
                    'AAPL': 185.92, 'MSFT': 420.45, 'GOOGL': 175.33, 'AMZN': 182.81,
                    'TSLA': 248.29, 'META': 475.12, 'NVDA': 116.64, '^GSPC': 4500.00
                }
                price = mock_prices.get(ticker_upper, 100.00)
                stock_price_cache[ticker_upper] = {'price': price, 'timestamp': current_time}
                return {'price': price}
                
        except Exception as e:
            logger.error(f"Error fetching data for {ticker_symbol}: {e}")
            # Return cached data if available, otherwise mock data
            if ticker_upper in stock_price_cache:
                return {'price': stock_price_cache[ticker_upper]['price']}
            return {'price': 100.00}

    def calculate_portfolio_value(self, user_id: int, target_date: date = None) -> float:
        """Calculate total portfolio value for a user on a specific date"""
        if target_date is None:
            target_date = date.today()
        
        user = User.query.get(user_id)
        if not user:
            return 0.0
        
        total_value = 0.0
        
        # Get all transactions up to target date
        transactions = Transaction.query.filter(
            and_(
                Transaction.user_id == user_id,
                func.date(Transaction.timestamp) <= target_date
            )
        ).order_by(Transaction.timestamp).all()
        
        # Calculate current holdings
        holdings = {}
        for transaction in transactions:
            ticker = transaction.ticker
            if ticker not in holdings:
                holdings[ticker] = 0
            
            if transaction.transaction_type == 'buy':
                holdings[ticker] += transaction.quantity
            else:  # sell
                holdings[ticker] -= transaction.quantity
        
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
                    # Fallback to last known price from transactions
                    last_transaction = Transaction.query.filter_by(
                        user_id=user_id, ticker=ticker
                    ).order_by(Transaction.timestamp.desc()).first()
                    if last_transaction:
                        total_value += quantity * last_transaction.price
        
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
                            symbol='SPY_SP500',
                            date=data_date
                        ).first()
                        
                        if not existing:
                            market_data = MarketData(
                                symbol='SPY_SP500',
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
                MarketData.symbol == self.sp500_symbol,
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
        
        # Batch fetch missing dates (usually just today's data)
        if missing_dates:
            try:
                # Single API call for SPY price (used for all missing dates)
                stock_data = self.get_stock_data('SPY')
                if stock_data and stock_data.get('price'):
                    sp500_price = stock_data['price'] * 10
                    
                    # Apply to all missing dates (efficient for daily updates)
                    for missing_date in missing_dates:
                        market_data = MarketData(
                            symbol=self.sp500_symbol,
                            date=missing_date,
                            close_price=sp500_price
                        )
                        db.session.add(market_data)
                        cached_dates[missing_date] = sp500_price
                        
            except Exception as e:
                logger.error(f"Error fetching S&P 500 data: {e}")
                # Use forward-fill from most recent cached data
                if cached_dates:
                    latest_price = max(cached_dates.values())
                    for missing_date in missing_dates:
                        cached_dates[missing_date] = latest_price
        
        try:
            db.session.commit()
        except Exception as e:
            logger.error(f"Error committing S&P 500 data: {e}")
        
        return cached_dates
    
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
    
    def get_performance_data(self, user_id: int, period: str) -> Dict:
        """Get performance data for a specific period"""
        end_date = date.today()
        
        # Define period mappings
        period_days = {
            '1D': 1,
            '5D': 5,
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
        
        # Ensure we have snapshots for the period
        self.ensure_snapshots_exist(user_id, start_date, end_date)
        
        # Calculate portfolio return
        portfolio_return = self.calculate_modified_dietz_return(user_id, start_date, end_date)
        
        # Calculate S&P 500 return
        sp500_return = self.calculate_sp500_return(start_date, end_date)
        
        # Get portfolio values for charting
        snapshots = PortfolioSnapshot.query.filter(
            and_(
                PortfolioSnapshot.user_id == user_id,
                PortfolioSnapshot.date >= start_date,
                PortfolioSnapshot.date <= end_date
            )
        ).order_by(PortfolioSnapshot.date).all()
        
        # Get S&P 500 data for charting
        sp500_data = self.get_sp500_data(start_date, end_date)
        
        # Normalize both to percentage change from start
        chart_data = []
        
        if snapshots and sp500_data and len(snapshots) > 1:
            # Both portfolio and S&P 500 data available with multiple snapshots
            start_portfolio_value = snapshots[0].total_value
            start_sp500_value = None
            
            # Find S&P 500 start value
            for snapshot in snapshots:
                if snapshot.date in sp500_data:
                    start_sp500_value = sp500_data[snapshot.date]
                    break
            
            if start_portfolio_value > 0 and start_sp500_value:
                for snapshot in snapshots:
                    portfolio_pct = ((snapshot.total_value - start_portfolio_value) / start_portfolio_value) * 100
                    
                    sp500_pct = 0
                    if snapshot.date in sp500_data:
                        sp500_pct = ((sp500_data[snapshot.date] - start_sp500_value) / start_sp500_value) * 100
                    
                    chart_data.append({
                        'date': snapshot.date.isoformat(),
                        'portfolio': round(portfolio_pct, 2),
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
                            'portfolio': 0,  # No portfolio data yet
                            'sp500': round(sp500_pct, 2)
                        })
        
        return {
            'period': period,
            'portfolio_return': round(portfolio_return * 100, 2),
            'sp500_return': round(sp500_return * 100, 2),
            'chart_data': chart_data,
            'current_value': snapshots[-1].total_value if snapshots else 0
        }
    
    def ensure_snapshots_exist(self, user_id: int, start_date: date, end_date: date):
        """Ensure portfolio snapshots exist for the date range"""
        current_date = start_date
        while current_date <= end_date:
            # Skip weekends for now (markets closed)
            if current_date.weekday() < 5:  # Monday = 0, Friday = 4
                existing = PortfolioSnapshot.query.filter_by(
                    user_id=user_id, date=current_date
                ).first()
                
                if not existing:
                    self.create_daily_snapshot(user_id, current_date)
            
            current_date += timedelta(days=1)

# Global instance
performance_calculator = PortfolioPerformanceCalculator()
