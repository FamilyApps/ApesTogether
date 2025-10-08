#!/usr/bin/env python3
"""
Backfill missing recent S&P 500 data (last 7 days)
Uses Alpha Vantage API to fetch SPY data and store as SPY_SP500
"""

import os
import sys
import requests
import time
from datetime import datetime, date, timedelta
from decimal import Decimal

def backfill_recent_sp500():
    """Fetch and backfill missing S&P 500 data for last 7 days"""
    
    try:
        from models import db, MarketData
        from sqlalchemy import and_
        
        print("🔄 Backfilling Recent S&P 500 Data (Last 7 Days)")
        print("=" * 60)
        
        # Get Alpha Vantage API key
        api_key = os.environ.get('ALPHA_VANTAGE_API_KEY')
        if not api_key:
            print("❌ Error: ALPHA_VANTAGE_API_KEY not found in environment")
            return {'success': False, 'error': 'Missing API key'}
        
        print(f"✅ Alpha Vantage API key found")
        
        # Check what dates we need
        today = date.today()
        dates_to_check = [today - timedelta(days=i) for i in range(7)]
        
        print(f"\n📅 Checking last 7 days: {dates_to_check[0]} to {dates_to_check[-1]}")
        
        sp500_ticker = "SPY_SP500"
        missing_dates = []
        
        for check_date in dates_to_check:
            # Skip weekends
            if check_date.weekday() >= 5:
                continue
                
            existing = MarketData.query.filter_by(
                ticker=sp500_ticker,
                date=check_date
            ).first()
            
            if existing:
                print(f"  ✓ {check_date} - exists (${existing.close_price:.2f})")
            else:
                print(f"  ✗ {check_date} - MISSING")
                missing_dates.append(check_date)
        
        if not missing_dates:
            print(f"\n🎉 No missing dates! All recent S&P 500 data is up to date.")
            return {
                'success': True,
                'new_records': 0,
                'message': 'No missing dates found'
            }
        
        print(f"\n📥 Need to fetch {len(missing_dates)} missing dates")
        print("-" * 50)
        
        # Fetch SPY data from Alpha Vantage
        url = "https://www.alphavantage.co/query"
        params = {
            'function': 'TIME_SERIES_DAILY',
            'symbol': 'SPY',
            'outputsize': 'compact',  # Last 100 days
            'apikey': api_key
        }
        
        print(f"🌐 Fetching SPY data from Alpha Vantage...")
        response = requests.get(url, params=params, timeout=30)
        
        if response.status_code != 200:
            print(f"❌ API request failed: HTTP {response.status_code}")
            return {'success': False, 'error': f'HTTP {response.status_code}'}
        
        data = response.json()
        
        if 'Error Message' in data:
            print(f"❌ Alpha Vantage error: {data['Error Message']}")
            return {'success': False, 'error': data['Error Message']}
        
        if 'Time Series (Daily)' not in data:
            print(f"❌ Unexpected response format: {list(data.keys())}")
            return {'success': False, 'error': 'Invalid response format'}
        
        time_series = data['Time Series (Daily)']
        print(f"✅ Received {len(time_series)} data points from Alpha Vantage")
        
        # Insert missing dates
        inserted_count = 0
        
        for missing_date in missing_dates:
            date_str = missing_date.isoformat()
            
            if date_str in time_series:
                daily_data = time_series[date_str]
                close_price = float(daily_data['4. close'])
                
                # Insert into database
                market_data = MarketData(
                    ticker=sp500_ticker,
                    date=missing_date,
                    open_price=float(daily_data['1. open']),
                    high_price=float(daily_data['2. high']),
                    low_price=float(daily_data['3. low']),
                    close_price=close_price,
                    volume=int(daily_data['5. volume'])
                )
                
                db.session.add(market_data)
                inserted_count += 1
                print(f"  ✅ Inserted {missing_date}: ${close_price:.2f}")
            else:
                print(f"  ⚠️  {missing_date} not in API response (market closed?)")
        
        db.session.commit()
        
        print(f"\n✅ Successfully inserted {inserted_count} records")
        
        return {
            'success': True,
            'new_records': inserted_count,
            'missing_dates': len(missing_dates),
            'message': f'Backfilled {inserted_count} missing S&P 500 data points'
        }
        
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")
        return {'success': False, 'error': str(e)}

if __name__ == '__main__':
    # Load environment if running standalone
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass
    
    # Set up Flask app context
    try:
        from app import app
        with app.app_context():
            result = backfill_recent_sp500()
            print(f"\n📊 Final Result: {result}")
            sys.exit(0 if result.get('success', False) else 1)
    except ImportError:
        # Try api/index.py context
        try:
            sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'api'))
            from index import app
            with app.app_context():
                result = backfill_recent_sp500()
                print(f"\n📊 Final Result: {result}")
                sys.exit(0 if result.get('success', False) else 1)
        except ImportError:
            print("❌ Error: Could not import Flask app")
            sys.exit(1)
