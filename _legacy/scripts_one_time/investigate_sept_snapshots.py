"""
Investigate witty-raven's snapshots from Sept 2-10, 2025
Check for asset changes, API fetch issues, or data anomalies
"""
import os
from datetime import date, datetime
from models import db, PortfolioSnapshot, Transaction, Stock, MarketData, User
from sqlalchemy import and_

# User ID 5 = witty-raven
USER_ID = 5
START_DATE = date(2025, 9, 2)
END_DATE = date(2025, 9, 11)  # Include Sept 11 to see the jump

print(f"\n{'='*80}")
print(f"INVESTIGATING WITTY-RAVEN (USER {USER_ID}) SNAPSHOTS")
print(f"Date Range: {START_DATE} to {END_DATE}")
print(f"{'='*80}\n")

# Get user info
user = User.query.get(USER_ID)
if user:
    print(f"User: {user.username} (ID: {user.id})")
    print(f"Email: {user.email}")
    print(f"Created: {user.created_at}")
else:
    print(f"ERROR: User {USER_ID} not found!")
    exit(1)

# Get all snapshots for this period
snapshots = PortfolioSnapshot.query.filter(
    and_(
        PortfolioSnapshot.user_id == USER_ID,
        PortfolioSnapshot.date >= START_DATE,
        PortfolioSnapshot.date <= END_DATE
    )
).order_by(PortfolioSnapshot.date).all()

print(f"\n{'='*80}")
print(f"SNAPSHOTS FOUND: {len(snapshots)}")
print(f"{'='*80}\n")

if not snapshots:
    print("No snapshots found for this period!")
    exit(1)

# Display snapshot details
print(f"{'Date':<12} {'Total Value':<15} {'Holdings':<40}")
print(f"{'-'*80}")

for snapshot in snapshots:
    holdings_str = f"{snapshot.holdings}" if snapshot.holdings else "None"
    if len(holdings_str) > 37:
        holdings_str = holdings_str[:37] + "..."
    print(f"{snapshot.date} ${snapshot.total_value:>12.2f}  {holdings_str}")

# Calculate percentage changes
print(f"\n{'='*80}")
print(f"PERCENTAGE CHANGES (from first snapshot)")
print(f"{'='*80}\n")

if snapshots and snapshots[0].total_value > 0:
    baseline = snapshots[0].total_value
    print(f"Baseline (Sept 2): ${baseline:.2f}\n")
    print(f"{'Date':<12} {'Value':<15} {'Change':<15} {'Pct Change':<15}")
    print(f"{'-'*80}")
    
    for snapshot in snapshots:
        change = snapshot.total_value - baseline
        pct_change = (change / baseline) * 100 if baseline > 0 else 0
        print(f"{snapshot.date} ${snapshot.total_value:>12.2f}  ${change:>12.2f}  {pct_change:>12.2f}%")

# Get all transactions for this user
print(f"\n{'='*80}")
print(f"TRANSACTIONS DURING THIS PERIOD")
print(f"{'='*80}\n")

transactions = Transaction.query.filter(
    and_(
        Transaction.user_id == USER_ID,
        Transaction.date >= START_DATE,
        Transaction.date <= END_DATE
    )
).order_by(Transaction.date).all()

if transactions:
    print(f"{'Date':<12} {'Type':<10} {'Symbol':<8} {'Shares':<10} {'Price':<12} {'Total':<12}")
    print(f"{'-'*80}")
    for txn in transactions:
        stock = Stock.query.get(txn.stock_id)
        symbol = stock.symbol if stock else "Unknown"
        total = txn.shares * txn.price
        print(f"{txn.date} {txn.transaction_type:<10} {symbol:<8} {txn.shares:<10.4f} ${txn.price:<10.2f} ${total:<10.2f}")
else:
    print("No transactions found during this period")

# Check holdings details for each snapshot
print(f"\n{'='*80}")
print(f"DETAILED HOLDINGS ANALYSIS")
print(f"{'='*80}\n")

for snapshot in snapshots:
    print(f"\n{snapshot.date} - Total Value: ${snapshot.total_value:.2f}")
    print(f"{'-'*60}")
    
    if snapshot.holdings:
        holdings = snapshot.holdings
        print(f"Holdings: {holdings}")
        
        # Try to parse holdings as dict
        try:
            import json
            if isinstance(holdings, str):
                holdings_dict = json.loads(holdings.replace("'", '"'))
            else:
                holdings_dict = holdings
            
            for symbol, data in holdings_dict.items():
                print(f"  {symbol}: {data.get('shares', 0)} shares @ ${data.get('price', 0):.2f} = ${data.get('value', 0):.2f}")
        except Exception as e:
            print(f"  (Could not parse holdings: {e})")
    else:
        print("  No holdings data")

# Check market data availability for each stock
print(f"\n{'='*80}")
print(f"MARKET DATA AVAILABILITY CHECK")
print(f"{'='*80}\n")

# Get unique stocks from snapshots
all_stocks = set()
for snapshot in snapshots:
    if snapshot.holdings:
        try:
            import json
            if isinstance(snapshot.holdings, str):
                holdings_dict = json.loads(snapshot.holdings.replace("'", '"'))
            else:
                holdings_dict = snapshot.holdings
            
            for symbol in holdings_dict.keys():
                all_stocks.add(symbol)
        except:
            pass

print(f"Stocks in portfolio during this period: {', '.join(sorted(all_stocks))}\n")

for symbol in sorted(all_stocks):
    stock = Stock.query.filter_by(symbol=symbol).first()
    if not stock:
        print(f"{symbol}: NOT FOUND IN DATABASE!")
        continue
    
    print(f"\n{symbol} (Stock ID: {stock.id})")
    print(f"{'-'*60}")
    
    market_data = MarketData.query.filter(
        and_(
            MarketData.stock_id == stock.id,
            MarketData.date >= START_DATE,
            MarketData.date <= END_DATE
        )
    ).order_by(MarketData.date).all()
    
    if market_data:
        print(f"{'Date':<12} {'Close Price':<15} {'Volume':<15}")
        print(f"{'-'*60}")
        for md in market_data:
            print(f"{md.date} ${md.close_price:>12.2f}  {md.volume:>12,}")
    else:
        print(f"NO MARKET DATA FOUND for {symbol} during this period!")
        print(f"This could explain valuation issues!")

print(f"\n{'='*80}")
print(f"INVESTIGATION COMPLETE")
print(f"{'='*80}\n")
