"""
Stock metadata utilities for populating and maintaining comprehensive stock information
Includes market cap, sector, industry, NAICS codes, and exchange data
"""
import requests
import time
from datetime import datetime, timedelta
import os

def get_alpha_vantage_company_overview(ticker):
    """
    Get comprehensive company data from Alpha Vantage OVERVIEW function
    Returns market cap, sector, industry, exchange, and other metadata
    """
    api_key = os.getenv('ALPHA_VANTAGE_API_KEY')
    if not api_key:
        print("Warning: ALPHA_VANTAGE_API_KEY not found")
        return None
    
    url = f"https://www.alphavantage.co/query"
    params = {
        'function': 'OVERVIEW',
        'symbol': ticker.upper(),
        'apikey': api_key
    }
    
    start_time = time.time()
    
    try:
        response = requests.get(url, params=params, timeout=10)
        response_time_ms = int((time.time() - start_time) * 1000)
        
        if response.status_code == 200:
            data = response.json()
            
            # Check for API limit or error
            if 'Note' in data or 'Error Message' in data:
                try:
                    from admin_metrics import log_alpha_vantage_call
                    log_alpha_vantage_call('OVERVIEW', ticker, 'rate_limited', response_time_ms)
                except ImportError:
                    print(f"API rate limited for {ticker}")
                return None
            
            # Check if we got valid data
            if 'Symbol' not in data or data.get('Symbol') != ticker.upper():
                try:
                    from admin_metrics import log_alpha_vantage_call
                    log_alpha_vantage_call('OVERVIEW', ticker, 'error', response_time_ms)
                except ImportError:
                    print(f"Invalid data for {ticker}")
                return None
            
            try:
                from admin_metrics import log_alpha_vantage_call
                log_alpha_vantage_call('OVERVIEW', ticker, 'success', response_time_ms)
            except ImportError:
                print(f"Successfully fetched data for {ticker}")
            return data
        else:
            try:
                from admin_metrics import log_alpha_vantage_call
                log_alpha_vantage_call('OVERVIEW', ticker, 'error', response_time_ms)
            except ImportError:
                print(f"HTTP error for {ticker}: {response.status_code}")
            return None
            
    except Exception as e:
        response_time_ms = int((time.time() - start_time) * 1000)
        try:
            from admin_metrics import log_alpha_vantage_call
            log_alpha_vantage_call('OVERVIEW', ticker, 'error', response_time_ms)
        except ImportError:
            print(f"Error fetching overview for {ticker}: {str(e)}")
        return None

def classify_market_cap(market_cap_str):
    """
    Classify market cap into categories based on dollar value
    """
    if not market_cap_str or market_cap_str == 'None':
        return 'unknown'
    
    try:
        # Remove commas and convert to integer
        market_cap = int(market_cap_str.replace(',', ''))
        
        if market_cap >= 200_000_000_000:  # $200B+
            return 'mega'
        elif market_cap >= 10_000_000_000:  # $10B+
            return 'large'
        elif market_cap >= 2_000_000_000:   # $2B+
            return 'mid'
        else:
            return 'small'
    except (ValueError, AttributeError):
        return 'unknown'

def get_naics_code_mapping():
    """
    Return a mapping of common industries to NAICS codes
    This is a simplified mapping - in production you'd want a more comprehensive database
    """
    return {
        'Software': '541511',  # Custom Computer Programming Services
        'Biotechnology': '541714',  # Research and Development in Biotechnology
        'Pharmaceuticals': '325412',  # Pharmaceutical Preparation Manufacturing
        'Semiconductors': '334413',  # Semiconductor and Related Device Manufacturing
        'Banking': '522110',  # Commercial Banking
        'Insurance': '524113',  # Direct Life Insurance Carriers
        'Real Estate': '531210',  # Offices of Real Estate Agents and Brokers
        'Retail': '452112',  # Discount Department Stores
        'Automotive': '336111',  # Automobile Manufacturing
        'Aerospace': '336411',  # Aircraft Manufacturing
        'Oil & Gas': '211111',  # Crude Petroleum and Natural Gas Extraction
        'Utilities': '221122',  # Electric Power Distribution
        'Telecommunications': '517311',  # Wired Telecommunications Carriers
        'Media': '515120',  # Television Broadcasting
        'Food & Beverage': '311111',  # Dog and Cat Food Manufacturing
        'Healthcare': '621111',  # Offices of Physicians
        'Technology': '541511',  # Custom Computer Programming Services (default for tech)
    }

def map_industry_to_naics(industry):
    """
    Map Alpha Vantage industry to NAICS code
    """
    if not industry:
        return None
    
    naics_mapping = get_naics_code_mapping()
    
    # Try exact match first
    if industry in naics_mapping:
        return naics_mapping[industry]
    
    # Try partial matches for common patterns
    industry_lower = industry.lower()
    
    if 'software' in industry_lower or 'technology' in industry_lower:
        return naics_mapping['Technology']
    elif 'biotech' in industry_lower or 'biotechnology' in industry_lower:
        return naics_mapping['Biotechnology']
    elif 'pharma' in industry_lower or 'pharmaceutical' in industry_lower:
        return naics_mapping['Pharmaceuticals']
    elif 'semiconductor' in industry_lower or 'chip' in industry_lower:
        return naics_mapping['Semiconductors']
    elif 'bank' in industry_lower:
        return naics_mapping['Banking']
    elif 'insurance' in industry_lower:
        return naics_mapping['Insurance']
    elif 'real estate' in industry_lower:
        return naics_mapping['Real Estate']
    elif 'retail' in industry_lower:
        return naics_mapping['Retail']
    elif 'automotive' in industry_lower or 'auto' in industry_lower:
        return naics_mapping['Automotive']
    elif 'aerospace' in industry_lower:
        return naics_mapping['Aerospace']
    elif 'oil' in industry_lower or 'gas' in industry_lower or 'energy' in industry_lower:
        return naics_mapping['Oil & Gas']
    elif 'utility' in industry_lower or 'utilities' in industry_lower:
        return naics_mapping['Utilities']
    elif 'telecom' in industry_lower or 'telecommunications' in industry_lower:
        return naics_mapping['Telecommunications']
    elif 'media' in industry_lower or 'broadcasting' in industry_lower:
        return naics_mapping['Media']
    elif 'food' in industry_lower or 'beverage' in industry_lower:
        return naics_mapping['Food & Beverage']
    elif 'healthcare' in industry_lower or 'health' in industry_lower:
        return naics_mapping['Healthcare']
    
    return None

def populate_stock_info(ticker, force_update=False):
    """
    Populate or update stock info for a given ticker
    """
    # Import models locally to avoid circular dependencies
    from models import db, StockInfo
    
    ticker_upper = ticker.upper()
    
    # Check if we already have recent data
    stock_info = StockInfo.query.filter_by(ticker=ticker_upper).first()
    
    if stock_info and not force_update:
        # Skip if updated within last 7 days
        if stock_info.last_updated > datetime.now() - timedelta(days=7):
            print(f"Stock info for {ticker_upper} is recent, skipping")
            return stock_info
    
    print(f"Fetching stock info for {ticker_upper}...")
    
    # Get data from Alpha Vantage
    overview_data = get_alpha_vantage_company_overview(ticker_upper)
    
    if not overview_data:
        print(f"Failed to get overview data for {ticker_upper}")
        return None
    
    # Create or update stock info
    if not stock_info:
        stock_info = StockInfo(ticker=ticker_upper)
        db.session.add(stock_info)
    
    # Update fields from Alpha Vantage data
    stock_info.company_name = overview_data.get('Name', ticker_upper)
    stock_info.sector = overview_data.get('Sector')
    stock_info.industry = overview_data.get('Industry')
    stock_info.exchange = overview_data.get('Exchange')
    stock_info.country = overview_data.get('Country', 'US')
    
    # Handle market cap
    market_cap_str = overview_data.get('MarketCapitalization')
    if market_cap_str and market_cap_str != 'None':
        try:
            stock_info.market_cap = int(market_cap_str)
            stock_info.cap_classification = classify_market_cap(market_cap_str)
        except (ValueError, TypeError):
            stock_info.market_cap = None
            stock_info.cap_classification = 'unknown'
    else:
        stock_info.market_cap = None
        stock_info.cap_classification = 'unknown'
    
    # Map industry to NAICS code
    stock_info.naics_code = map_industry_to_naics(stock_info.industry)
    
    stock_info.last_updated = datetime.now()
    
    try:
        db.session.commit()
        print(f"✓ Updated stock info for {ticker_upper}: {stock_info.company_name} ({stock_info.cap_classification} cap, {stock_info.sector})")
        return stock_info
    except Exception as e:
        db.session.rollback()
        print(f"Error saving stock info for {ticker_upper}: {str(e)}")
        return None

def populate_all_user_stocks():
    """
    Populate stock info for all stocks held by users
    """
    # Import models locally to avoid circular dependencies
    from models import db, Stock
    
    # Get all unique tickers from user portfolios
    unique_tickers = db.session.query(Stock.ticker).distinct().all()
    tickers = [ticker[0] for ticker in unique_tickers]
    
    print(f"Found {len(tickers)} unique tickers to populate")
    
    success_count = 0
    failed_count = 0
    
    for i, ticker in enumerate(tickers, 1):
        print(f"\n[{i}/{len(tickers)}] Processing {ticker}...")
        
        result = populate_stock_info(ticker)
        
        if result:
            success_count += 1
        else:
            failed_count += 1
        
        # Rate limiting - Alpha Vantage allows 5 calls per minute for free tier
        if i < len(tickers):  # Don't sleep after the last one
            print("Waiting 12 seconds for API rate limit...")
            time.sleep(12)
    
    print(f"\n=== STOCK INFO POPULATION COMPLETE ===")
    print(f"Successfully populated: {success_count}")
    print(f"Failed: {failed_count}")
    print(f"Total processed: {len(tickers)}")
    
    return success_count, failed_count

def get_stocks_by_industry(naics_code=None, industry_name=None):
    """
    Get stocks filtered by NAICS code or industry name
    Useful for creating industry-specific leaderboards
    """
    # Import models locally to avoid circular dependencies
    from models import StockInfo
    
    query = StockInfo.query.filter(StockInfo.is_active == True)
    
    if naics_code:
        query = query.filter(StockInfo.naics_code == naics_code)
    elif industry_name:
        query = query.filter(StockInfo.industry.ilike(f'%{industry_name}%'))
    
    return query.all()

def get_biotech_stocks():
    """
    Get all biotechnology stocks for biotech leaderboard
    """
    return get_stocks_by_industry(naics_code='541714')

def get_tech_stocks():
    """
    Get all technology/software stocks
    """
    return get_stocks_by_industry(naics_code='541511')
