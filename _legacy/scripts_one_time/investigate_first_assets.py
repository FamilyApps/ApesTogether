"""
Investigate witty-raven's first assets on 6/19/2025

Questions:
1. What time were assets added?
2. Do we have market data for those stocks on that date?
3. Were prices fetched at the time of asset addition?
"""

import os
import sys
from datetime import date, datetime

# Add the current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

from api.index import app, db
from models import User, Stock, Transaction, MarketData, PortfolioSnapshot

def investigate():
    with app.app_context():
        # Find witty-raven
        user = User.query.filter_by(username='witty-raven').first()
        if not user:
            print("❌ User not found")
            return
        
        print("="*80)
        print("INVESTIGATION: witty-raven's First Assets (6/19/2025)")
        print("="*80)
        
        # Check transactions on 6/19/2025
        target_date = date(2025, 6, 19)
        transactions = Transaction.query.filter_by(user_id=user.id).filter(
            db.func.date(Transaction.timestamp) == target_date
        ).order_by(Transaction.timestamp).all()
        
        print(f"\n📈 TRANSACTIONS ON {target_date}:")
        print("-" * 80)
        
        if not transactions:
            print("No transactions found")
        else:
            for txn in transactions:
                print(f"  {txn.timestamp.strftime('%Y-%m-%d %H:%M:%S')}: "
                      f"{txn.type.upper()} {txn.quantity} shares of {txn.ticker} @ ${txn.price}")
        
        # Check stocks (current holdings with purchase_date = 6/19)
        stocks = Stock.query.filter_by(user_id=user.id).filter_by(purchase_date=target_date).all()
        
        print(f"\n📊 STOCKS WITH PURCHASE DATE = {target_date}:")
        print("-" * 80)
        
        if not stocks:
            print("No stocks found")
        else:
            for stock in stocks:
                print(f"  {stock.ticker}: {stock.quantity} shares @ ${stock.purchase_price}")
        
        # Check market data for those tickers on that date
        all_tickers = set()
        if transactions:
            all_tickers.update([t.ticker for t in transactions])
        if stocks:
            all_tickers.update([s.ticker for s in stocks])
        
        print(f"\n💰 MARKET DATA ON {target_date}:")
        print("-" * 80)
        
        for ticker in sorted(all_tickers):
            market_data = MarketData.query.filter_by(ticker=ticker, date=target_date).first()
            if market_data:
                print(f"  ✅ {ticker}: Open=${market_data.open_price:.2f}, "
                      f"Close=${market_data.close_price:.2f}, "
                      f"High=${market_data.high_price:.2f}, "
                      f"Low=${market_data.low_price:.2f}")
            else:
                print(f"  ❌ {ticker}: NO MARKET DATA")
        
        # Check snapshot for that date
        snapshot = PortfolioSnapshot.query.filter_by(user_id=user.id, date=target_date).first()
        
        print(f"\n📸 PORTFOLIO SNAPSHOT ON {target_date}:")
        print("-" * 80)
        
        if snapshot:
            print(f"  Total Value: ${snapshot.total_value:,.2f}")
            print(f"  Percentage Gain: {snapshot.percentage_gain:.2f}%")
        else:
            print("  No snapshot found")
        
        # Check all transactions for this user to understand trading pattern
        all_transactions = Transaction.query.filter_by(user_id=user.id).order_by(Transaction.timestamp).all()
        
        print(f"\n📅 ALL TRANSACTIONS FOR {user.username}:")
        print("-" * 80)
        print(f"Total: {len(all_transactions)} transactions")
        
        if all_transactions:
            print(f"\nFirst transaction: {all_transactions[0].timestamp}")
            print(f"Last transaction:  {all_transactions[-1].timestamp}")
            
            # Group by date to see intraday activity
            from collections import defaultdict
            by_date = defaultdict(list)
            for txn in all_transactions:
                by_date[txn.timestamp.date()].append(txn)
            
            print(f"\nDates with multiple transactions (intraday trading):")
            for txn_date, txns in sorted(by_date.items()):
                if len(txns) > 1:
                    print(f"  {txn_date}: {len(txns)} transactions")
                    for txn in txns:
                        print(f"    {txn.timestamp.strftime('%H:%M:%S')}: "
                              f"{txn.type.upper()} {txn.quantity} {txn.ticker} @ ${txn.price}")
        
        # Check current holdings
        current_stocks = Stock.query.filter_by(user_id=user.id).all()
        
        print(f"\n📦 CURRENT HOLDINGS:")
        print("-" * 80)
        
        if not current_stocks:
            print("No current holdings")
        else:
            for stock in current_stocks:
                print(f"  {stock.ticker}: {stock.quantity} shares "
                      f"(purchased {stock.purchase_date} @ ${stock.purchase_price})")

if __name__ == "__main__":
    investigate()
