"""
Diagnose Zero-Value Snapshot Issue
Identifies why snapshots have $0.00 values
"""
import os
import sys
from datetime import date, datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from api.index import app, db
from models import PortfolioSnapshot, Stock, User

def diagnose_zero_snapshots():
    """Check for zero-value snapshots and diagnose cause"""
    with app.app_context():
        print("\n" + "="*80)
        print("ZERO-VALUE SNAPSHOT DIAGNOSTIC")
        print("="*80)
        
        # Get recent zero-value snapshots
        recent_date = date.today() - timedelta(days=7)
        zero_snapshots = PortfolioSnapshot.query.filter(
            PortfolioSnapshot.total_value == 0,
            PortfolioSnapshot.date >= recent_date
        ).order_by(PortfolioSnapshot.date.desc()).all()
        
        print(f"\n📊 Found {len(zero_snapshots)} zero-value snapshots in last 7 days")
        
        # Group by date
        by_date = {}
        for snap in zero_snapshots:
            if snap.date not in by_date:
                by_date[snap.date] = []
            by_date[snap.date].append(snap)
        
        print("\n🗓️  Zero-value snapshots by date:")
        for snap_date in sorted(by_date.keys(), reverse=True):
            snaps = by_date[snap_date]
            print(f"\n  {snap_date} ({snap_date.strftime('%A')}): {len(snaps)} users")
            
            for snap in snaps[:5]:  # Show first 5
                user = User.query.get(snap.user_id)
                stocks = Stock.query.filter_by(user_id=snap.user_id).all()
                
                print(f"    User {snap.user_id} ({user.username if user else 'unknown'}):")
                print(f"      Stocks: {len(stocks)}")
                
                if stocks:
                    print(f"      Stock symbols: {', '.join([s.ticker for s in stocks[:5]])}")
                    print(f"      Quantities: {', '.join([str(s.quantity) for s in stocks[:5]])}")
                    print(f"      Purchase prices: {', '.join([f'${s.purchase_price:.2f}' for s in stocks[:5]])}")
                    
                    # Calculate expected value using purchase prices
                    fallback_value = sum(s.quantity * s.purchase_price for s in stocks)
                    print(f"      Expected value (purchase prices): ${fallback_value:,.2f}")
                else:
                    print(f"      No stocks found!")
        
        # Check for users with ALL zero snapshots
        print("\n\n👥 Users with ALL zero snapshots:")
        users = User.query.all()
        
        for user in users:
            recent_snaps = PortfolioSnapshot.query.filter(
                PortfolioSnapshot.user_id == user.id,
                PortfolioSnapshot.date >= recent_date
            ).all()
            
            if recent_snaps:
                zero_count = sum(1 for s in recent_snaps if s.total_value == 0)
                non_zero_count = len(recent_snaps) - zero_count
                
                if zero_count == len(recent_snaps):
                    print(f"  ⚠️  {user.username} (ID {user.id}): ALL {len(recent_snaps)} snapshots are $0.00")
                    
                    # Check if they have stocks
                    stocks = Stock.query.filter_by(user_id=user.id).all()
                    if stocks:
                        print(f"      But has {len(stocks)} stocks!")
                        print(f"      Symbols: {', '.join([s.ticker for s in stocks[:5]])}")
                    else:
                        print(f"      Has no stocks (expected)")
                
                elif zero_count > 0:
                    print(f"  ⚠️  {user.username} (ID {user.id}): {zero_count}/{len(recent_snaps)} snapshots are $0.00")
        
        # Check non-zero snapshots for comparison
        print("\n\n✅ Users with NON-ZERO snapshots:")
        non_zero_snapshots = PortfolioSnapshot.query.filter(
            PortfolioSnapshot.total_value > 0,
            PortfolioSnapshot.date >= recent_date
        ).order_by(PortfolioSnapshot.date.desc()).limit(10).all()
        
        for snap in non_zero_snapshots:
            user = User.query.get(snap.user_id)
            print(f"  {snap.date} - {user.username if user else 'unknown'} (ID {snap.user_id}): ${snap.total_value:,.2f}")
        
        print("\n" + "="*80)
        print("DIAGNOSTIC COMPLETE")
        print("="*80)
        print("\n💡 RECOMMENDATIONS:")
        print("  1. If users have stocks but $0.00 snapshots:")
        print("     → calculate_portfolio_value is failing to fetch prices")
        print("     → Check Alpha Vantage API errors in logs")
        print("     → Verify API key is valid and has quota")
        print("\n  2. If zero-value pattern is recent:")
        print("     → Likely a recent API failure or code change")
        print("     → Need to regenerate snapshots with working API")
        print("\n  3. For users with no stocks:")
        print("     → $0.00 snapshots are expected")
        print("     → They shouldn't appear in leaderboards")

if __name__ == "__main__":
    diagnose_zero_snapshots()
