"""
One-time script to create transaction records for stocks added during account setup.

PROBLEM:
- Users added stocks during account setup without transaction records
- Stock table has holdings but Transaction table is empty
- Can't calculate cash balance or reconstruct portfolio history

SOLUTION:
- For each stock in Stock table without a matching transaction:
  - Create an 'initial' transaction
  - Timestamp: Stock.purchase_date (or 4 PM EST on that date)
  - Price: Stock.purchase_price (the price we recorded)
  - Type: 'initial' (to distinguish from regular trades)
"""

import os
import sys
from datetime import datetime, time
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

from api.index import app, db
from models import User, Stock, Transaction

def create_initial_transactions(dry_run=True):
    """
    Create transaction records for stocks that were added during account setup.
    
    Args:
        dry_run: If True, only show what would be created (default: True)
    """
    with app.app_context():
        print("="*80)
        print("RETROACTIVE TRANSACTION CREATION")
        print("="*80)
        
        users = User.query.all()
        
        total_transactions_created = 0
        
        for user in users:
            print(f"\n{'='*80}")
            print(f"USER: {user.username} (ID: {user.id})")
            print(f"{'='*80}")
            
            # Get all stocks for this user
            stocks = Stock.query.filter_by(user_id=user.id).all()
            
            if not stocks:
                print("  No stocks found")
                continue
            
            # Get all existing transactions for this user
            existing_transactions = Transaction.query.filter_by(user_id=user.id).all()
            
            # Build set of (ticker, quantity) pairs from transactions
            transacted_stocks = {}
            for txn in existing_transactions:
                key = txn.ticker
                if key not in transacted_stocks:
                    transacted_stocks[key] = 0
                
                if txn.transaction_type == 'buy':
                    transacted_stocks[key] += txn.quantity
                elif txn.transaction_type == 'sell':
                    transacted_stocks[key] -= txn.quantity
            
            print(f"\n  Existing Transactions: {len(existing_transactions)}")
            print(f"  Current Stock Holdings: {len(stocks)}")
            
            # Find stocks without corresponding initial transaction
            missing_transactions = []
            
            for stock in stocks:
                # Check if this stock has a matching transaction
                transacted_qty = transacted_stocks.get(stock.ticker, 0)
                
                if transacted_qty < stock.quantity:
                    # Missing transaction for this stock (or partial)
                    missing_qty = stock.quantity - transacted_qty
                    missing_transactions.append({
                        'stock': stock,
                        'missing_quantity': missing_qty
                    })
            
            if not missing_transactions:
                print("  ✅ All stocks have transaction records")
                continue
            
            print(f"\n  🚨 Found {len(missing_transactions)} stocks WITHOUT transaction records:")
            
            for item in missing_transactions:
                stock = item['stock']
                missing_qty = item['missing_quantity']
                
                # Determine timestamp for the transaction
                if stock.purchase_date:
                    # Use the purchase_date from the stock record
                    # If it has a time component, use it
                    # Otherwise, assume 4 PM EST (market close)
                    stock_datetime = stock.purchase_date
                    
                    # Check if it's just a date (midnight) or has a real time
                    if stock_datetime.hour == 0 and stock_datetime.minute == 0:
                        # Assume market close: 4 PM EST
                        ET = ZoneInfo('America/New_York')
                        date_part = stock_datetime.date()
                        timestamp = datetime.combine(
                            date_part, 
                            time(16, 0, 0),  # 4:00 PM
                            tzinfo=ET
                        )
                    else:
                        timestamp = stock_datetime
                else:
                    # No purchase_date, use today at 4 PM EST as fallback
                    ET = ZoneInfo('America/New_York')
                    timestamp = datetime.now(ET).replace(hour=16, minute=0, second=0, microsecond=0)
                
                print(f"\n    {stock.ticker}:")
                print(f"      Quantity: {missing_qty}")
                print(f"      Price: ${stock.purchase_price}")
                print(f"      Timestamp: {timestamp}")
                print(f"      Total Value: ${missing_qty * stock.purchase_price:,.2f}")
                
                if not dry_run:
                    # Create the transaction
                    transaction = Transaction(
                        user_id=user.id,
                        ticker=stock.ticker,
                        quantity=missing_qty,
                        price=stock.purchase_price,
                        transaction_type='initial',  # Special type for account setup
                        timestamp=timestamp
                    )
                    db.session.add(transaction)
                    total_transactions_created += 1
                    print(f"      ✅ Transaction created")
                else:
                    print(f"      📋 DRY RUN: Would create transaction")
        
        if not dry_run:
            db.session.commit()
            print(f"\n{'='*80}")
            print(f"✅ CREATED {total_transactions_created} TRANSACTIONS")
            print(f"{'='*80}")
        else:
            print(f"\n{'='*80}")
            print(f"📋 DRY RUN COMPLETE")
            print(f"Would create {total_transactions_created} transactions")
            print(f"Run with dry_run=False to actually create them")
            print(f"{'='*80}")

if __name__ == "__main__":
    import sys
    
    # Check for --execute flag
    dry_run = True
    if len(sys.argv) > 1 and sys.argv[1] == '--execute':
        dry_run = False
        print("⚠️  EXECUTING FOR REAL (not a dry run)")
    else:
        print("📋 DRY RUN MODE (use --execute to actually create transactions)")
    
    create_initial_transactions(dry_run=dry_run)
