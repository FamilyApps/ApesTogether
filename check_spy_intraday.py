"""
Diagnostic script to check SPY_INTRADAY data in the database
Run this to see what intraday S&P 500 data was collected today
"""

from models import db, MarketData
from datetime import date, datetime, timedelta
from sqlalchemy import and_

# Check SPY_INTRADAY data for today
today = date.today()
print(f"\n🔍 Checking SPY_INTRADAY data for {today}...")

spy_intraday_today = MarketData.query.filter(
    and_(
        MarketData.ticker == 'SPY_INTRADAY',
        MarketData.date == today
    )
).order_by(MarketData.timestamp.asc()).all()

print(f"\nFound {len(spy_intraday_today)} SPY_INTRADAY records for {today}")

if spy_intraday_today:
    print("\n📊 SPY_INTRADAY Records:")
    for record in spy_intraday_today:
        print(f"  {record.timestamp} - ${record.close_price:.2f}")
else:
    print("\n❌ NO SPY_INTRADAY data found for today!")
    print("   This explains why 1D/5D charts show flat S&P 500 line")

# Check last 7 days
print(f"\n\n🔍 Checking SPY_INTRADAY data for last 7 days...")
for days_back in range(7):
    check_date = today - timedelta(days=days_back)
    count = MarketData.query.filter(
        and_(
            MarketData.ticker == 'SPY_INTRADAY',
            MarketData.date == check_date
        )
    ).count()
    print(f"  {check_date}: {count} records")

# Check PortfolioSnapshotIntraday for today
print(f"\n\n🔍 Checking PortfolioSnapshotIntraday for today...")
from models import PortfolioSnapshotIntraday
intraday_snapshots = PortfolioSnapshotIntraday.query.filter(
    PortfolioSnapshotIntraday.timestamp >= datetime.combine(today, datetime.min.time())
).order_by(PortfolioSnapshotIntraday.timestamp.asc()).all()

print(f"Found {len(intraday_snapshots)} portfolio intraday snapshots for {today}")

if intraday_snapshots:
    # Group by user
    by_user = {}
    for snap in intraday_snapshots:
        if snap.user_id not in by_user:
            by_user[snap.user_id] = []
        by_user[snap.user_id].append(snap)
    
    for user_id, snaps in by_user.items():
        print(f"\n  User {user_id}: {len(snaps)} snapshots")
        print(f"    First: {snaps[0].timestamp}")
        print(f"    Last: {snaps[-1].timestamp}")
