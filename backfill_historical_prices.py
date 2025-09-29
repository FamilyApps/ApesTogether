#!/usr/bin/env python3
"""
Backfill historical stock prices for 9/25/2025 and 9/26/2025 and update ALL caches
"""

import os
import sys
import requests
import time
import json
from datetime import date, datetime
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from models import db, User, Stock, PortfolioSnapshot, MarketData, LeaderboardCache, UserPortfolioChartCache, SP500ChartCache

def get_historical_price(ticker, target_date, api_key):
    """Get historical price for a specific ticker and date from Alpha Vantage"""
    print(f"  📈 Fetching {ticker} for {target_date}...")
    
    # Alpha Vantage TIME_SERIES_DAILY endpoint
    url = f"https://www.alphavantage.co/query"
    params = {
        'function': 'TIME_SERIES_DAILY',
        'symbol': ticker,
        'apikey': api_key,
        'outputsize': 'compact'  # Last 100 days
    }
    
    try:
        response = requests.get(url, params=params)
        data = response.json()
        
        if 'Error Message' in data:
            print(f"    ❌ API Error: {data['Error Message']}")
            return None
            
        if 'Note' in data:
            print(f"    ⚠️  API Limit: {data['Note']}")
            return None
        
        time_series = data.get('Time Series (Daily)', {})
        date_str = target_date.strftime('%Y-%m-%d')
        
        if date_str in time_series:
            close_price = float(time_series[date_str]['4. close'])
            print(f"    ✅ {ticker} on {date_str}: ${close_price:.2f}")
            return close_price
        else:
            print(f"    ❌ No data for {date_str}")
            # Try previous trading day
            available_dates = sorted(time_series.keys(), reverse=True)
            for available_date in available_dates:
                if available_date < date_str:
                    close_price = float(time_series[available_date]['4. close'])
                    print(f"    📅 Using {available_date} price: ${close_price:.2f}")
                    return close_price
            return None
            
    except Exception as e:
        print(f"    ❌ Error fetching {ticker}: {e}")
        return None

def backfill_historical_snapshots():
    """Backfill snapshots with correct historical prices and update ALL caches"""
    api_key = os.environ.get('ALPHA_VANTAGE_API_KEY')
    if not api_key:
        print("❌ ALPHA_VANTAGE_API_KEY not found in environment variables")
        return
    
    print("=== BACKFILLING HISTORICAL PRICES & UPDATING ALL CACHES ===")
    print(f"🔑 Using Alpha Vantage API Key: {api_key[:8]}...")
    
    target_dates = [date(2025, 9, 25), date(2025, 9, 26)]
    
    # Get all unique tickers from all users
    all_stocks = Stock.query.all()
    unique_tickers = list(set(stock.ticker for stock in all_stocks))
    print(f"\n🏢 Found {len(unique_tickers)} unique tickers: {unique_tickers}")
    
    # Also need S&P 500 data
    sp500_ticker = "SPY"  # S&P 500 ETF as proxy
    unique_tickers.append(sp500_ticker)
    
    # Fetch historical prices for each date
    historical_prices = {}
    
    for target_date in target_dates:
        print(f"\n📅 Fetching prices for {target_date}:")
        historical_prices[target_date] = {}
        
        for ticker in unique_tickers:
            price = get_historical_price(ticker, target_date, api_key)
            if price:
                historical_prices[target_date][ticker] = price
            
            # Rate limiting - Alpha Vantage allows 5 calls per minute for free tier
            time.sleep(12)  # 12 seconds between calls = 5 calls per minute
    
    print(f"\n💾 Historical prices collected:")
    for date_key, prices in historical_prices.items():
        print(f"  {date_key}: {len(prices)} prices")
        for ticker, price in prices.items():
            print(f"    {ticker}: ${price:.2f}")
    
    # STEP 1: Update Portfolio Snapshots
    print(f"\n🔧 STEP 1: Updating Portfolio Snapshots...")
    
    for target_date in target_dates:
        date_prices = historical_prices.get(target_date, {})
        if not date_prices:
            print(f"  ❌ No prices available for {target_date}")
            continue
            
        snapshots = PortfolioSnapshot.query.filter_by(date=target_date).all()
        print(f"  📸 Found {len(snapshots)} snapshots for {target_date}")
        
        for snapshot in snapshots:
            user = User.query.get(snapshot.user_id)
            username = user.username if user else f"User {snapshot.user_id}"
            
            # Calculate correct portfolio value using historical prices
            user_stocks = Stock.query.filter_by(user_id=snapshot.user_id).all()
            correct_value = 0
            
            for stock in user_stocks:
                if stock.quantity > 0 and stock.ticker in date_prices:
                    historical_price = date_prices[stock.ticker]
                    stock_value = stock.quantity * historical_price
                    correct_value += stock_value
                    print(f"    {stock.ticker}: {stock.quantity} × ${historical_price:.2f} = ${stock_value:.2f}")
            
            if correct_value > 0:
                old_value = snapshot.total_value
                snapshot.total_value = correct_value
                print(f"  🔧 {username}: ${old_value:.2f} → ${correct_value:.2f}")
    
    # STEP 2: Update Market Data (S&P 500)
    print(f"\n📊 STEP 2: Updating S&P 500 Market Data...")
    for target_date in target_dates:
        if sp500_ticker in historical_prices.get(target_date, {}):
            sp500_price = historical_prices[target_date][sp500_ticker]
            
            # Check if market data exists
            existing_data = MarketData.query.filter_by(
                ticker="SPY_SP500", 
                date=target_date
            ).first()
            
            if existing_data:
                old_price = existing_data.close_price
                existing_data.close_price = sp500_price
                print(f"  🔧 S&P 500 {target_date}: ${old_price:.2f} → ${sp500_price:.2f}")
            else:
                new_data = MarketData(
                    ticker="SPY_SP500",
                    date=target_date,
                    close_price=sp500_price,
                    volume=0  # We don't need volume for this
                )
                db.session.add(new_data)
                print(f"  ➕ S&P 500 {target_date}: ${sp500_price:.2f} (new)")
    
    # STEP 3: Clear Stale Caches (they'll be regenerated with correct data)
    print(f"\n🗑️  STEP 3: Clearing Stale Caches...")
    
    # Clear LeaderboardCache
    stale_leaderboard_caches = LeaderboardCache.query.all()
    for cache in stale_leaderboard_caches:
        db.session.delete(cache)
    print(f"  🗑️  Cleared {len(stale_leaderboard_caches)} leaderboard cache entries")
    
    # Clear UserPortfolioChartCache
    stale_chart_caches = UserPortfolioChartCache.query.all()
    for cache in stale_chart_caches:
        db.session.delete(cache)
    print(f"  🗑️  Cleared {len(stale_chart_caches)} user chart cache entries")
    
    # Clear SP500ChartCache
    stale_sp500_caches = SP500ChartCache.query.all()
    for cache in stale_sp500_caches:
        db.session.delete(cache)
    print(f"  🗑️  Cleared {len(stale_sp500_caches)} S&P 500 chart cache entries")
    
    # Commit all changes
    try:
        db.session.commit()
        print(f"\n✅ All data changes committed successfully!")
    except Exception as e:
        print(f"❌ Error committing changes: {e}")
        db.session.rollback()
        return
    
    # STEP 4: Regenerate All Caches
    print(f"\n🔄 STEP 4: Regenerating All Caches...")
    
    try:
        # Regenerate leaderboard cache (this also triggers chart cache generation)
        from leaderboard_utils import update_leaderboard_cache
        updated_count = update_leaderboard_cache()
        print(f"  ✅ Regenerated {updated_count} leaderboard entries")
        
        # Regenerate user chart caches for all periods
        from leaderboard_utils import generate_user_portfolio_chart
        users = User.query.all()
        periods = ['1D', '5D', '1M', '3M', 'YTD', '1Y', '5Y', 'MAX']
        
        chart_count = 0
        for user in users:
            for period in periods:
                try:
                    chart_data = generate_user_portfolio_chart(user.id, period)
                    if chart_data:
                        # Cache will be automatically created by the function
                        chart_count += 1
                        print(f"    📊 Generated {period} chart for {user.username}")
                except Exception as e:
                    print(f"    ❌ Error generating {period} chart for {user.username}: {e}")
        
        print(f"  ✅ Regenerated {chart_count} user chart caches")
        
        # Regenerate S&P 500 chart caches
        from stock_data_manager import generate_sp500_chart_data
        sp500_count = 0
        for period in periods:
            try:
                sp500_data = generate_sp500_chart_data(period)
                if sp500_data:
                    sp500_count += 1
                    print(f"    📈 Generated S&P 500 {period} chart")
            except Exception as e:
                print(f"    ❌ Error generating S&P 500 {period} chart: {e}")
        
        print(f"  ✅ Regenerated {sp500_count} S&P 500 chart caches")
        
    except Exception as e:
        print(f"❌ Error regenerating caches: {e}")
        import traceback
        traceback.print_exc()
    
    print(f"\n🎉 BACKFILL COMPLETE!")
    print(f"📊 Portfolio snapshots updated with historical prices")
    print(f"🏆 Leaderboard caches regenerated")
    print(f"📈 Chart caches regenerated for all users and periods")
    print(f"💹 S&P 500 benchmark data updated")
    print(f"\n✨ Your dashboard should now show correct data for 9/25 and 9/26!")

if __name__ == "__main__":
    backfill_historical_snapshots()
