"""
Backfill cash tracking for all existing users.

Run this AFTER:
1. Running create_initial_transactions.py (to create missing transaction records)
2. Adding max_cash_deployed and cash_proceeds columns to User table

This script replays all transactions in chronological order to rebuild:
- max_cash_deployed: Cumulative capital deployed
- cash_proceeds: Uninvested cash from sales

USAGE:
python backfill_cash_tracking.py           # Dry run (see what would be updated)
python backfill_cash_tracking.py --execute  # Actually update database
"""

import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

from api.index import app, db
from models import User
from cash_tracking import backfill_all_users

def main(dry_run=True):
    """Backfill cash tracking for all users"""
    
    with app.app_context():
        print("="*80)
        print("BACKFILL CASH TRACKING (max_cash_deployed + cash_proceeds)")
        print("="*80)
        
        if dry_run:
            print("\n📋 DRY RUN MODE - No changes will be made")
            print("Run with --execute flag to actually update database\n")
        else:
            print("\n⚠️  EXECUTING FOR REAL - Database will be updated\n")
        
        # Get all users
        users = User.query.all()
        print(f"Found {len(users)} users\n")
        
        if dry_run:
            # Show what would be updated
            from cash_tracking import backfill_cash_tracking_for_user
            
            for user in users:
                print(f"{'='*80}")
                print(f"USER: {user.username} (ID: {user.id})")
                print(f"{'='*80}")
                
                # Get transactions
                from models import Transaction
                transactions = Transaction.query.filter_by(user_id=user.id)\
                    .order_by(Transaction.timestamp).all()
                
                if not transactions:
                    print("  ⚠️  No transactions found - would set both to $0")
                    continue
                
                print(f"\n  Transactions: {len(transactions)}")
                
                # Simulate calculation
                max_cash_deployed = 0.0
                cash_proceeds = 0.0
                
                for txn in transactions:
                    transaction_value = txn.quantity * txn.price
                    
                    print(f"    {txn.timestamp.strftime('%Y-%m-%d %H:%M')} | "
                          f"{txn.transaction_type.upper():8} | "
                          f"{txn.ticker:6} | "
                          f"{txn.quantity:6.2f} @ ${txn.price:7.2f} = ${transaction_value:9.2f}")
                    
                    if txn.transaction_type in ('buy', 'initial'):
                        if cash_proceeds >= transaction_value:
                            cash_proceeds -= transaction_value
                            print(f"      → Used ${transaction_value:.2f} from cash_proceeds")
                        else:
                            new_capital = transaction_value - cash_proceeds
                            cash_proceeds = 0
                            max_cash_deployed += new_capital
                            print(f"      → Deployed ${new_capital:.2f} new capital")
                    
                    elif txn.transaction_type == 'sell':
                        cash_proceeds += transaction_value
                        print(f"      → Added ${transaction_value:.2f} to cash_proceeds")
                
                print(f"\n  WOULD SET:")
                print(f"    max_cash_deployed: ${max_cash_deployed:,.2f}")
                print(f"    cash_proceeds: ${cash_proceeds:,.2f}")
                
                # Calculate portfolio value
                from cash_tracking import calculate_portfolio_value_with_cash
                portfolio = calculate_portfolio_value_with_cash(user.id)
                
                if max_cash_deployed > 0:
                    performance = ((portfolio['total_value'] - max_cash_deployed) / max_cash_deployed) * 100
                    print(f"\n  PERFORMANCE:")
                    print(f"    Portfolio value: ${portfolio['total_value']:,.2f}")
                    print(f"    vs. Deployed capital: ${max_cash_deployed:,.2f}")
                    print(f"    Gain/Loss: {performance:+.2f}%")
                
                print()
        
        else:
            # Actually update database
            print("Backfilling all users...\n")
            results = backfill_all_users(db)
            
            print(f"\n{'='*80}")
            print("BACKFILL COMPLETE")
            print(f"{'='*80}\n")
            
            for result in results:
                if result['success']:
                    print(f"✅ {result['username']:20} | "
                          f"Deployed: ${result['max_cash_deployed']:10,.2f} | "
                          f"Cash: ${result['cash_proceeds']:10,.2f}")
                else:
                    print(f"❌ {result['username']:20} | Error: {result.get('error', 'Unknown')}")
            
            print(f"\n{'='*80}")
            print(f"Successfully updated {sum(1 for r in results if r['success'])}/{len(results)} users")
            print(f"{'='*80}")

if __name__ == "__main__":
    dry_run = True
    if len(sys.argv) > 1 and sys.argv[1] == '--execute':
        dry_run = False
        print("⚠️  EXECUTING FOR REAL")
    else:
        print("📋 DRY RUN MODE (use --execute to actually update)")
    
    main(dry_run=dry_run)
