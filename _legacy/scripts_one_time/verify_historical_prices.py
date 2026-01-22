#!/usr/bin/env python3
"""
Verify that historical prices actually vary day-to-day
"""

import os
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app import app, db
from models import MarketData
from sqlalchemy import text

def verify_price_variation():
    """Check that prices vary for each ticker"""
    with app.app_context():
        print("=" * 60)
        print("VERIFYING HISTORICAL PRICE VARIATION")
        print("=" * 60)
        
        # Get unique tickers
        tickers_result = db.session.execute(text("""
            SELECT DISTINCT ticker FROM market_data ORDER BY ticker LIMIT 5
        """))
        
        for ticker_row in tickers_result:
            ticker = ticker_row.ticker
            print(f"\n📊 {ticker}:")
            
            # Get last 10 days of prices
            prices = MarketData.query.filter_by(ticker=ticker).order_by(
                MarketData.date.desc()
            ).limit(10).all()
            
            if not prices:
                print(f"   ❌ No prices found")
                continue
            
            print(f"   Total cached days: {MarketData.query.filter_by(ticker=ticker).count()}")
            print(f"   Last 10 days:")
            
            price_values = []
            for p in prices:
                print(f"      {p.date}: ${p.close_price:.2f}")
                price_values.append(p.close_price)
            
            # Check if all prices are the same (bad)
            unique_prices = len(set(price_values))
            if unique_prices == 1:
                print(f"   🚨 ERROR: All prices identical!")
            else:
                print(f"   ✅ Good: {unique_prices} unique prices in last 10 days")
        
        print("\n" + "=" * 60)

if __name__ == "__main__":
    verify_price_variation()
