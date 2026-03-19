"""
Dividend Tracker — Automatic dividend detection and recording.

Checks for ex-dividend dates daily and credits dividend income to users'
cash_proceeds. This increases portfolio value (V_end in Modified Dietz)
without increasing max_cash_deployed (CF_net), correctly attributing
dividend income as investment return.

Called by: market-close cron job (daily)
API: AlphaVantage DIVIDENDS endpoint (1 call per ticker)
"""
import os
import logging
import requests
from datetime import date, datetime, timedelta

logger = logging.getLogger(__name__)

ALPHA_VANTAGE_KEY = os.environ.get('ALPHA_VANTAGE_API_KEY', '')


def fetch_recent_dividends(ticker: str, lookback_days: int = 7) -> list:
    """
    Fetch recent dividend events for a ticker from AlphaVantage.
    
    Returns list of dicts: [{'ex_date': date, 'amount': float, 'pay_date': date|None}]
    """
    if not ALPHA_VANTAGE_KEY:
        logger.warning("ALPHA_VANTAGE_API_KEY not set — skipping dividend fetch")
        return []
    
    try:
        url = f"https://www.alphavantage.co/query?function=DIVIDENDS&symbol={ticker}&apikey={ALPHA_VANTAGE_KEY}"
        resp = requests.get(url, timeout=10)
        data = resp.json()
        
        if 'data' not in data:
            # Try alternative: OVERVIEW endpoint has dividend_per_share
            logger.debug(f"No dividend data for {ticker}")
            return []
        
        cutoff = date.today() - timedelta(days=lookback_days)
        results = []
        
        for entry in data['data']:
            try:
                ex_date = datetime.strptime(entry['ex_dividend_date'], '%Y-%m-%d').date()
                if ex_date >= cutoff:
                    pay_date = None
                    if entry.get('payment_date') and entry['payment_date'] != 'None':
                        try:
                            pay_date = datetime.strptime(entry['payment_date'], '%Y-%m-%d').date()
                        except (ValueError, TypeError):
                            pass
                    
                    results.append({
                        'ex_date': ex_date,
                        'amount': float(entry.get('amount', 0)),
                        'pay_date': pay_date,
                        'declaration_date': entry.get('declaration_date'),
                    })
            except (ValueError, KeyError) as e:
                logger.debug(f"Skipping dividend entry for {ticker}: {e}")
                continue
        
        return results
        
    except Exception as e:
        logger.error(f"Error fetching dividends for {ticker}: {e}")
        return []


def process_dividends_for_date(db, target_date: date = None) -> dict:
    """
    Check all held tickers for ex-dividend dates and credit users.
    
    Called daily by market-close cron. For each ticker with an ex-date
    matching target_date, finds all users holding that stock and records
    the dividend payment.
    
    Args:
        db: SQLAlchemy database session
        target_date: Date to check (default: today)
    
    Returns:
        dict with counts and details of dividends processed
    """
    from models import User, Stock, Dividend
    from cash_tracking import process_transaction
    
    if target_date is None:
        target_date = date.today()
    
    logger.info(f"🔍 Checking dividends for {target_date}")
    
    # Get all unique tickers currently held by any user
    held_tickers = set()
    all_stocks = Stock.query.filter(Stock.quantity > 0).all()
    for stock in all_stocks:
        held_tickers.add(stock.ticker.upper())
    
    if not held_tickers:
        logger.info("No stocks held by any user — skipping dividend check")
        return {'tickers_checked': 0, 'dividends_found': 0, 'dividends_recorded': 0}
    
    logger.info(f"📊 Checking {len(held_tickers)} tickers for dividends: {', '.join(sorted(held_tickers)[:20])}")
    
    results = {
        'tickers_checked': len(held_tickers),
        'dividends_found': 0,
        'dividends_recorded': 0,
        'total_amount': 0.0,
        'details': [],
        'errors': []
    }
    
    # Check each ticker for recent dividends
    for ticker in sorted(held_tickers):
        try:
            dividends = fetch_recent_dividends(ticker, lookback_days=3)
            
            for div in dividends:
                if div['ex_date'] != target_date:
                    continue
                
                if div['amount'] <= 0:
                    continue
                
                results['dividends_found'] += 1
                amount_per_share = div['amount']
                
                logger.info(f"💰 Dividend found: {ticker} ${amount_per_share}/share (ex-date: {target_date})")
                
                # Find all users holding this stock
                holders = Stock.query.filter(
                    Stock.ticker == ticker,
                    Stock.quantity > 0
                ).all()
                
                for stock in holders:
                    user_id = stock.user_id
                    shares = stock.quantity
                    total = round(amount_per_share * shares, 2)
                    
                    # Skip if already recorded
                    existing = Dividend.query.filter_by(
                        user_id=user_id, ticker=ticker, ex_date=target_date
                    ).first()
                    if existing:
                        logger.debug(f"  Already recorded for user {user_id}")
                        continue
                    
                    # Record dividend
                    dividend = Dividend(
                        user_id=user_id,
                        ticker=ticker,
                        amount_per_share=amount_per_share,
                        shares_held=shares,
                        total_amount=total,
                        ex_date=target_date,
                        pay_date=div.get('pay_date')
                    )
                    db.session.add(dividend)
                    
                    # Process as dividend transaction
                    try:
                        process_transaction(
                            db, user_id, ticker, shares, amount_per_share,
                            'dividend',
                            timestamp=datetime.combine(target_date, datetime.min.time())
                        )
                        results['dividends_recorded'] += 1
                        results['total_amount'] += total
                        results['details'].append({
                            'user_id': user_id,
                            'ticker': ticker,
                            'shares': shares,
                            'amount_per_share': amount_per_share,
                            'total': total
                        })
                        logger.info(f"  ✅ User {user_id}: {shares} shares × ${amount_per_share} = ${total}")
                    except Exception as e:
                        error = f"Error recording dividend for user {user_id} {ticker}: {e}"
                        results['errors'].append(error)
                        logger.error(error)
        
        except Exception as e:
            error = f"Error checking dividends for {ticker}: {e}"
            results['errors'].append(error)
            logger.error(error)
    
    logger.info(
        f"📊 Dividend check complete: {results['dividends_found']} found, "
        f"{results['dividends_recorded']} recorded, ${results['total_amount']:.2f} total"
    )
    
    return results
