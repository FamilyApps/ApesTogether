"""
Batch fetch historical prices for all tickers used in transactions.

This script populates the MarketData table so snapshot creation can be fast
and won't timeout. Run this ONCE before re-backfilling snapshots.

With 150 calls/minute limit, this should complete in < 1 minute for typical portfolios.
"""

import os
import sys
from datetime import datetime, date, timedelta
from sqlalchemy import text
from models import db, Transaction, MarketData, User
from portfolio_performance import PortfolioPerformanceCalculator, get_market_date
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def fetch_all_historical_prices():
    """Fetch historical prices for all tickers from earliest transaction to today"""
    
    # Get date range
    end_date = get_market_date()
    
    # Find earliest transaction date
    earliest_result = db.session.execute(text("""
        SELECT MIN(DATE(timestamp)) as earliest
        FROM transaction
    """))
    earliest_row = earliest_result.fetchone()
    start_date = earliest_row.earliest if earliest_row and earliest_row.earliest else end_date - timedelta(days=120)
    
    logger.info(f"Fetching historical prices from {start_date} to {end_date}")
    
    # Get all unique tickers
    tickers_result = db.session.execute(text("""
        SELECT DISTINCT ticker FROM transaction ORDER BY ticker
    """))
    tickers = [row.ticker.upper() for row in tickers_result]
    
    if not tickers:
        logger.error("No tickers found in transactions")
        return
    
    logger.info(f"Found {len(tickers)} unique tickers: {', '.join(tickers)}")
    
    calculator = PortfolioPerformanceCalculator()
    
    for i, ticker in enumerate(tickers, 1):
        logger.info(f"[{i}/{len(tickers)}] Processing {ticker}...")
        
        # Check if we already have data
        cached_count = MarketData.query.filter(
            MarketData.ticker == ticker,
            MarketData.date >= start_date,
            MarketData.date <= end_date
        ).count()
        
        days_span = (end_date - start_date).days
        
        if cached_count >= days_span * 0.7:
            logger.info(f"  ✅ {ticker}: Already have {cached_count} days cached (skip)")
            continue
        
        try:
            # Fetch historical price for start_date
            # The TIME_SERIES_DAILY API returns 100+ days at once and caches all of them
            price = calculator.get_historical_price(ticker, start_date)
            
            if price:
                # Check how many we cached
                new_cached_count = MarketData.query.filter(
                    MarketData.ticker == ticker,
                    MarketData.date >= start_date,
                    MarketData.date <= end_date
                ).count()
                
                logger.info(f"  ✅ {ticker}: Fetched and cached {new_cached_count} days of data")
            else:
                logger.warning(f"  ❌ {ticker}: Failed to fetch data")
        
        except Exception as e:
            logger.error(f"  ❌ {ticker}: Error - {e}")
    
    logger.info(f"\n{'='*60}")
    logger.info(f"Historical price fetch complete!")
    logger.info(f"Date range: {start_date} → {end_date}")
    logger.info(f"Tickers processed: {len(tickers)}")
    
    # Show total cached records
    total_cached = MarketData.query.filter(
        MarketData.date >= start_date,
        MarketData.date <= end_date
    ).count()
    logger.info(f"Total MarketData records: {total_cached}")
    logger.info(f"{'='*60}\n")

if __name__ == '__main__':
    # For local testing
    from flask import Flask
    app = Flask(__name__)
    app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL')
    db.init_app(app)
    
    with app.app_context():
        fetch_all_historical_prices()
