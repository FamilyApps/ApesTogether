#!/usr/bin/env python3
"""
Debug script to audit YTD S&P 500 calculation vs 3M and 1Y periods
"""

import os
import sys
from datetime import datetime, date, timedelta
from sqlalchemy import create_engine, text, func, and_
from sqlalchemy.orm import sessionmaker

# Add the project root to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from models import db, MarketData
from portfolio_performance import PortfolioPerformanceCalculator

def get_db_connection():
    """Get database connection using environment variables."""
    database_url = os.getenv('DATABASE_URL')
    if not database_url:
        print("ERROR: DATABASE_URL environment variable not set")
        return None
    
    # Handle postgres:// vs postgresql:// URL format
    if database_url.startswith('postgres://'):
        database_url = database_url.replace('postgres://', 'postgresql://', 1)
    
    try:
        engine = create_engine(database_url)
        Session = sessionmaker(bind=engine)
        return Session()
    except Exception as e:
        print(f"ERROR: Could not connect to database: {str(e)}")
        return None

def debug_period_calculations():
    """Debug YTD vs 3M vs 1Y period calculations"""
    print("🔍 DEBUGGING S&P 500 PERIOD CALCULATIONS")
    print("=" * 60)
    
    session = get_db_connection()
    if not session:
        return
    
    calculator = PortfolioPerformanceCalculator()
    today = date.today()
    
    # Calculate end_date (same logic as portfolio_performance.py)
    if today.weekday() == 5:  # Saturday
        end_date = today - timedelta(days=1)  # Friday
    elif today.weekday() == 6:  # Sunday
        end_date = today - timedelta(days=2)  # Friday
    else:
        end_date = today  # Monday-Friday
    
    print(f"📅 Today: {today} ({today.strftime('%A')})")
    print(f"📅 End Date: {end_date} ({end_date.strftime('%A')})")
    print()
    
    # Define periods to compare
    periods = {
        'YTD': {
            'start_date': date(end_date.year, 1, 1),
            'description': f"January 1, {end_date.year} to {end_date}"
        },
        '3M': {
            'start_date': end_date - timedelta(days=90),
            'description': f"{end_date - timedelta(days=90)} to {end_date} (90 days)"
        },
        '1Y': {
            'start_date': end_date - timedelta(days=365),
            'description': f"{end_date - timedelta(days=365)} to {end_date} (365 days)"
        }
    }
    
    # Analyze each period
    for period_name, period_info in periods.items():
        print(f"\n🔍 ANALYZING {period_name} PERIOD")
        print("-" * 40)
        print(f"📅 Date Range: {period_info['description']}")
        print(f"📅 Start Date: {period_info['start_date']}")
        print(f"📅 End Date: {end_date}")
        print(f"📅 Days: {(end_date - period_info['start_date']).days}")
        
        # Check available S&P 500 data
        sp500_data = session.query(MarketData).filter(
            and_(
                MarketData.ticker == 'SPY_SP500',
                MarketData.date >= period_info['start_date'],
                MarketData.date <= end_date
            )
        ).order_by(MarketData.date).all()
        
        print(f"📊 Available S&P 500 data points: {len(sp500_data)}")
        
        if sp500_data:
            first_data = sp500_data[0]
            last_data = sp500_data[-1]
            
            print(f"📈 First data point: {first_data.date} = ${first_data.close_price:.2f}")
            print(f"📈 Last data point: {last_data.date} = ${last_data.close_price:.2f}")
            
            # Check for data gaps
            expected_days = (end_date - period_info['start_date']).days
            business_days = sum(1 for i in range(expected_days + 1) 
                              if (period_info['start_date'] + timedelta(days=i)).weekday() < 5)
            
            print(f"📊 Expected business days: {business_days}")
            print(f"📊 Actual data points: {len(sp500_data)}")
            print(f"📊 Data coverage: {len(sp500_data)/business_days*100:.1f}%")
            
            # Calculate return using the same logic as portfolio_performance.py
            available_dates = [data.date for data in sp500_data]
            sp500_dict = {data.date: data.close_price for data in sp500_data}
            
            start_price = None
            end_price = None
            
            # Find start price (closest date >= start_date)
            for d in sorted(available_dates):
                if d >= period_info['start_date']:
                    start_price = sp500_dict[d]
                    start_date_found = d
                    break
            
            # Find end price (closest date <= end_date)
            for d in reversed(sorted(available_dates)):
                if d <= end_date:
                    end_price = sp500_dict[d]
                    end_date_found = d
                    break
            
            print(f"💰 Start price: ${start_price:.2f} on {start_date_found if start_price else 'NOT FOUND'}")
            print(f"💰 End price: ${end_price:.2f} on {end_date_found if end_price else 'NOT FOUND'}")
            
            if start_price and end_price and start_price > 0:
                sp500_return = (end_price - start_price) / start_price
                print(f"📈 S&P 500 Return: {sp500_return:.4f} ({sp500_return*100:.2f}%)")
                
                # Check if start_price is suspiciously low
                if start_price < 100:
                    print(f"⚠️  WARNING: Start price ${start_price:.2f} seems unusually low for S&P 500")
                
                # Check for zero or negative returns
                if sp500_return == 0:
                    print(f"🚨 ZERO RETURN DETECTED!")
                    print(f"   Start price: ${start_price:.2f}")
                    print(f"   End price: ${end_price:.2f}")
                    print(f"   Difference: ${end_price - start_price:.2f}")
            else:
                print(f"❌ CALCULATION FAILED:")
                print(f"   Start price: {start_price}")
                print(f"   End price: {end_price}")
                print(f"   Start price > 0: {start_price > 0 if start_price else False}")
        else:
            print("❌ NO S&P 500 DATA FOUND FOR THIS PERIOD")
        
        # Test using calculator method
        print(f"\n🧮 TESTING CALCULATOR METHOD:")
        try:
            calc_return = calculator.calculate_sp500_return(period_info['start_date'], end_date)
            print(f"📈 Calculator result: {calc_return:.4f} ({calc_return*100:.2f}%)")
        except Exception as e:
            print(f"❌ Calculator error: {str(e)}")
    
    # Check for data quality issues
    print(f"\n🔍 DATA QUALITY ANALYSIS")
    print("-" * 40)
    
    # Check for duplicate dates
    all_sp500_data = session.query(MarketData).filter(
        MarketData.ticker == 'SPY_SP500'
    ).all()
    
    dates_seen = {}
    duplicates = []
    for data in all_sp500_data:
        if data.date in dates_seen:
            duplicates.append(data.date)
        dates_seen[data.date] = data.close_price
    
    if duplicates:
        print(f"⚠️  Found {len(duplicates)} duplicate dates in S&P 500 data")
        for dup_date in duplicates[:5]:  # Show first 5
            print(f"   Duplicate: {dup_date}")
    else:
        print("✅ No duplicate dates found")
    
    # Check for zero prices
    zero_prices = session.query(MarketData).filter(
        and_(
            MarketData.ticker == 'SPY_SP500',
            MarketData.close_price == 0
        )
    ).all()
    
    if zero_prices:
        print(f"⚠️  Found {len(zero_prices)} zero prices in S&P 500 data")
        for zero_data in zero_prices[:5]:  # Show first 5
            print(f"   Zero price: {zero_data.date}")
    else:
        print("✅ No zero prices found")
    
    # Check for suspiciously low prices
    low_prices = session.query(MarketData).filter(
        and_(
            MarketData.ticker == 'SPY_SP500',
            MarketData.close_price < 100,
            MarketData.close_price > 0
        )
    ).all()
    
    if low_prices:
        print(f"⚠️  Found {len(low_prices)} suspiciously low prices (< $100)")
        for low_data in low_prices[:5]:  # Show first 5
            print(f"   Low price: {low_data.date} = ${low_data.close_price:.2f}")
    else:
        print("✅ No suspiciously low prices found")
    
    session.close()

if __name__ == "__main__":
    debug_period_calculations()
