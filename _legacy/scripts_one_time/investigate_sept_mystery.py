"""
Deep investigation into Sept 2-11 portfolio value anomaly
Checking if 6.87% drop is real or data corruption
"""
import os
import sys
from datetime import date, datetime, timedelta

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from models import db, User, PortfolioSnapshot, Stock, MarketData, Transaction
from sqlalchemy import and_, func
import json

def investigate_sept_mystery():
    """Investigate the mysterious Sept 3-10 portfolio value freeze"""
    
    START_DATE = date(2025, 9, 2)
    END_DATE = date(2025, 9, 11)
    
    print("=" * 80)
    print("SEPT 2-11 PORTFOLIO VALUE MYSTERY INVESTIGATION")
    print("=" * 80)
    
    # QUESTION 1: What happened to ALL users during this period?
    print("\n🔍 QUESTION 1: Did ALL users experience similar issues?")
    print("-" * 80)
    
    all_users = User.query.all()
    user_anomalies = {}
    
    for user in all_users:
        snapshots = PortfolioSnapshot.query.filter(
            and_(
                PortfolioSnapshot.user_id == user.id,
                PortfolioSnapshot.date >= START_DATE,
                PortfolioSnapshot.date <= END_DATE
            )
        ).order_by(PortfolioSnapshot.date).all()
        
        if len(snapshots) > 0:
            # Check for frozen values (identical values for consecutive days)
            frozen_days = 0
            prev_value = None
            daily_values = []
            
            for snapshot in snapshots:
                daily_values.append({
                    'date': str(snapshot.date),
                    'value': round(snapshot.total_value, 2)
                })
                
                if prev_value is not None and abs(snapshot.total_value - prev_value) < 0.01:
                    frozen_days += 1
                prev_value = snapshot.total_value
            
            # Calculate max drop
            values = [s.total_value for s in snapshots]
            max_value = max(values)
            min_value = min(values)
            max_drop_pct = ((min_value - max_value) / max_value * 100) if max_value > 0 else 0
            
            user_anomalies[user.username] = {
                'user_id': user.id,
                'snapshots_count': len(snapshots),
                'frozen_days': frozen_days,
                'max_drop_pct': round(max_drop_pct, 2),
                'daily_values': daily_values,
                'suspicious': frozen_days > 3 or max_drop_pct < -5
            }
    
    # Print summary
    suspicious_users = {k: v for k, v in user_anomalies.items() if v['suspicious']}
    print(f"\nTotal users with Sept data: {len(user_anomalies)}")
    print(f"Users with suspicious patterns: {len(suspicious_users)}")
    
    for username, data in suspicious_users.items():
        print(f"\n  👤 {username} (ID: {data['user_id']})")
        print(f"     - Frozen days: {data['frozen_days']}")
        print(f"     - Max drop: {data['max_drop_pct']}%")
        print(f"     - Daily values: {json.dumps(data['daily_values'], indent=8)}")
    
    # QUESTION 2: What market data exists for this period?
    print("\n\n🔍 QUESTION 2: What market data exists for Sept 2-11?")
    print("-" * 80)
    
    # Check for the stocks in witty-raven's portfolio
    tickers = ['AAPL', 'SSPY', 'TSLA', 'SPY']  # Added SPY in case SSPY is typo
    
    for ticker in tickers:
        market_data = MarketData.query.filter(
            and_(
                MarketData.ticker == ticker,
                MarketData.date >= START_DATE,
                MarketData.date <= END_DATE
            )
        ).order_by(MarketData.date).all()
        
        print(f"\n  📊 {ticker}:")
        if len(market_data) > 0:
            print(f"     ✅ {len(market_data)} data points found")
            for md in market_data:
                print(f"        {md.date}: ${md.close_price:.2f}")
        else:
            print(f"     ❌ NO DATA FOUND")
    
    # QUESTION 3: What was the actual S&P 500 movement during this period?
    print("\n\n🔍 QUESTION 3: What was the S&P 500's actual performance Sept 2-11, 2025?")
    print("-" * 80)
    print("  Note: Checking if we have SPY or ^GSPC data for reference")
    
    sp500_tickers = ['SPY', 'SPY_SP500', '^GSPC', 'SSPY']
    sp500_data = None
    
    for ticker in sp500_tickers:
        data = MarketData.query.filter(
            and_(
                MarketData.ticker == ticker,
                MarketData.date >= START_DATE,
                MarketData.date <= END_DATE
            )
        ).order_by(MarketData.date).all()
        
        if len(data) > 0:
            sp500_data = data
            print(f"\n  ✅ Found data for {ticker}:")
            if len(data) >= 2:
                first_price = data[0].close_price
                for md in data:
                    pct_change = ((md.close_price - first_price) / first_price * 100)
                    print(f"     {md.date}: ${md.close_price:.2f} ({pct_change:+.2f}%)")
            break
    
    if not sp500_data:
        print("  ❌ No S&P 500 data found for this period")
    
    # QUESTION 4: Can we backfill with Alpha Vantage?
    print("\n\n🔍 QUESTION 4: Can we backfill missing data with Alpha Vantage?")
    print("-" * 80)
    
    print("  Alpha Vantage Historical Data Capabilities:")
    print("  ✅ TIME_SERIES_DAILY - Up to 20+ years of historical data")
    print("  ✅ TIME_SERIES_DAILY_ADJUSTED - Includes dividends/splits")
    print("  ✅ Free tier: 25 API calls/day (5 calls/minute)")
    print("  ✅ Premium tier: 1200 calls/day (75 calls/minute)")
    
    print("\n  Missing tickers that need backfill:")
    for ticker in ['AAPL', 'SSPY', 'TSLA']:
        count = MarketData.query.filter(
            and_(
                MarketData.ticker == ticker,
                MarketData.date >= START_DATE,
                MarketData.date <= END_DATE
            )
        ).count()
        
        if count == 0:
            print(f"    ❌ {ticker}: 0 data points (needs 7 days = 1 API call)")
    
    # QUESTION 5: Detailed witty-raven investigation
    print("\n\n🔍 QUESTION 5: Deep dive into witty-raven's Sept 2-3 drop")
    print("-" * 80)
    
    witty_raven = User.query.filter_by(username='witty-raven').first()
    if witty_raven:
        print(f"\n  User ID: {witty_raven.id}")
        
        # Get Sept 2 and Sept 3 snapshots
        sept2 = PortfolioSnapshot.query.filter_by(
            user_id=witty_raven.id,
            date=date(2025, 9, 2)
        ).first()
        
        sept3 = PortfolioSnapshot.query.filter_by(
            user_id=witty_raven.id,
            date=date(2025, 9, 3)
        ).first()
        
        if sept2 and sept3:
            print(f"\n  Sept 2: ${sept2.total_value:.2f}")
            print(f"  Sept 3: ${sept3.total_value:.2f}")
            print(f"  Change: ${sept3.total_value - sept2.total_value:.2f}")
            print(f"  % Change: {((sept3.total_value - sept2.total_value) / sept2.total_value * 100):.2f}%")
            
            # Get holdings as of Sept 2
            holdings_sept2 = db.session.query(
                Stock.ticker,
                func.sum(Stock.quantity).label('net_quantity')
            ).filter(
                Stock.user_id == witty_raven.id,
                Stock.purchase_date <= date(2025, 9, 2)
            ).group_by(Stock.ticker).having(
                func.sum(Stock.quantity) > 0
            ).all()
            
            print(f"\n  Holdings on Sept 2:")
            for ticker, qty in holdings_sept2:
                print(f"    {ticker}: {qty} shares")
                
                # Try to find market prices for Sept 2 and Sept 3
                sept2_price = MarketData.query.filter_by(
                    ticker=ticker,
                    date=date(2025, 9, 2)
                ).first()
                
                sept3_price = MarketData.query.filter_by(
                    ticker=ticker,
                    date=date(2025, 9, 3)
                ).first()
                
                if sept2_price and sept3_price:
                    price_change = ((sept3_price.close_price - sept2_price.close_price) / sept2_price.close_price * 100)
                    position_value_change = qty * (sept3_price.close_price - sept2_price.close_price)
                    print(f"      Sept 2 price: ${sept2_price.close_price:.2f}")
                    print(f"      Sept 3 price: ${sept3_price.close_price:.2f}")
                    print(f"      Price change: {price_change:+.2f}%")
                    print(f"      Position impact: ${position_value_change:+.2f}")
                elif sept2_price:
                    print(f"      Sept 2 price: ${sept2_price.close_price:.2f}")
                    print(f"      Sept 3 price: ❌ MISSING")
                elif sept3_price:
                    print(f"      Sept 2 price: ❌ MISSING")
                    print(f"      Sept 3 price: ${sept3_price.close_price:.2f}")
                else:
                    print(f"      ❌ NO MARKET DATA FOR EITHER DATE")
    
    # RECOMMENDATIONS
    print("\n\n📋 RECOMMENDATIONS:")
    print("=" * 80)
    
    if len(suspicious_users) > 1:
        print("✅ SYSTEMIC ISSUE CONFIRMED - Multiple users affected")
        print("   → This was NOT isolated to witty-raven")
    
    print("\n🔧 PROPOSED FIX:")
    print("   1. Backfill missing market data using Alpha Vantage")
    print("      - API call: TIME_SERIES_DAILY for AAPL, SSPY, TSLA")
    print("      - Date range: Sept 2-11, 2025")
    print("      - Cost: 3 API calls (well within free tier)")
    print("")
    print("   2. Recalculate portfolio snapshots for Sept 2-11")
    print("      - Use backfilled market data")
    print("      - Apply to ALL affected users")
    print("      - Preserve original snapshots in backup table")
    print("")
    print("   3. Regenerate chart cache for affected users")
    print("      - Clear UserPortfolioChartCache for Sept dates")
    print("      - Charts will auto-regenerate with corrected data")
    
    print("\n" + "=" * 80)
    print("END OF INVESTIGATION")
    print("=" * 80)

if __name__ == '__main__':
    from app import app
    with app.app_context():
        investigate_sept_mystery()
