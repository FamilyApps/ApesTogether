"""
Check if Sept 30, 2025 snapshots exist and analyze the data flow
"""
import os
from datetime import date, datetime
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

load_dotenv()

# Get database URL
DATABASE_URL = os.environ.get('DATABASE_URL') or os.environ.get('POSTGRES_PRISMA_URL')
if DATABASE_URL.startswith('postgres://'):
    DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql://', 1)

engine = create_engine(DATABASE_URL)
Session = sessionmaker(bind=engine)
session = Session()

print("=" * 80)
print("SEPT 30, 2025 SNAPSHOT ANALYSIS")
print("=" * 80)

# Check for today's snapshots
today = date(2025, 9, 30)
yesterday = date(2025, 9, 29)

print(f"\n📅 Checking for snapshots on {today}...")

result = session.execute(text("""
    SELECT 
        ps.user_id,
        u.username,
        ps.date,
        ps.total_value,
        ps.created_at
    FROM portfolio_snapshot ps
    JOIN "user" u ON u.id = ps.user_id
    WHERE ps.date = :today
    ORDER BY ps.user_id
"""), {"today": today})

today_snapshots = result.fetchall()

if today_snapshots:
    print(f"✅ Found {len(today_snapshots)} snapshots for {today}:\n")
    for snap in today_snapshots:
        print(f"  User {snap.user_id} ({snap.username}): ${snap.total_value:,.2f}")
        print(f"    Created at: {snap.created_at}")
else:
    print(f"❌ NO SNAPSHOTS FOUND FOR {today}")

# Check yesterday for comparison
print(f"\n📅 Checking for snapshots on {yesterday} (for comparison)...")

result = session.execute(text("""
    SELECT 
        ps.user_id,
        u.username,
        ps.date,
        ps.total_value,
        ps.created_at
    FROM portfolio_snapshot ps
    JOIN "user" u ON u.id = ps.user_id
    WHERE ps.date = :yesterday
    ORDER BY ps.user_id
"""), {"yesterday": yesterday})

yesterday_snapshots = result.fetchall()

if yesterday_snapshots:
    print(f"✅ Found {len(yesterday_snapshots)} snapshots for {yesterday}:\n")
    for snap in yesterday_snapshots:
        print(f"  User {snap.user_id} ({snap.username}): ${snap.total_value:,.2f}")
        print(f"    Created at: {snap.created_at}")
else:
    print(f"❌ NO SNAPSHOTS FOUND FOR {yesterday}")

# Check latest snapshot date
print(f"\n📊 LATEST SNAPSHOT INFO:")

result = session.execute(text("""
    SELECT 
        MAX(date) as latest_date,
        COUNT(*) as total_count,
        COUNT(DISTINCT user_id) as user_count
    FROM portfolio_snapshot
"""))

latest = result.fetchone()
print(f"  Latest date: {latest.latest_date}")
print(f"  Total snapshots in DB: {latest.total_count}")
print(f"  Users with snapshots: {latest.user_count}")

# Check for zero-value snapshots
print(f"\n⚠️  ZERO-VALUE SNAPSHOT CHECK:")

result = session.execute(text("""
    SELECT 
        COUNT(*) as zero_count
    FROM portfolio_snapshot
    WHERE total_value = 0
"""))

zero_count = result.fetchone().zero_count
print(f"  Zero-value snapshots: {zero_count}")

# Check chart cache status
print(f"\n📈 CHART CACHE STATUS:")

result = session.execute(text("""
    SELECT 
        user_id,
        period,
        generated_at,
        LENGTH(chart_data) as data_size
    FROM user_portfolio_chart_cache
    WHERE user_id = 5
    ORDER BY 
        CASE period
            WHEN '1D' THEN 1
            WHEN '5D' THEN 2
            WHEN '1M' THEN 3
            WHEN '3M' THEN 4
            WHEN 'YTD' THEN 5
            WHEN '1Y' THEN 6
        END
"""))

caches = result.fetchall()

if caches:
    print(f"  User 5 (witty-raven) chart caches:\n")
    for cache in caches:
        print(f"    {cache.period}: Generated at {cache.generated_at}")
        print(f"      Data size: {cache.data_size:,} bytes")
else:
    print(f"  ❌ No chart caches found for user 5")

# Check if users have stocks
print(f"\n👥 USERS WITH STOCKS:")

result = session.execute(text("""
    SELECT 
        u.id,
        u.username,
        COUNT(s.id) as stock_count,
        SUM(s.quantity) as total_shares
    FROM "user" u
    LEFT JOIN stock s ON s.user_id = u.id
    GROUP BY u.id, u.username
    ORDER BY u.id
"""))

users = result.fetchall()

for user in users:
    if user.stock_count > 0:
        print(f"  User {user.id} ({user.username}): {user.stock_count} stocks, {user.total_shares} shares")

# Final diagnosis
print(f"\n" + "=" * 80)
print("DIAGNOSIS:")
print("=" * 80)

if not today_snapshots:
    print("❌ PROBLEM CONFIRMED: No snapshots created for Sept 30, 2025")
    print("\nPOSSIBLE CAUSES:")
    print("  1. Vercel cron job didn't trigger at 20:00 UTC")
    print("  2. Cron job triggered but endpoint failed")
    print("  3. Endpoint ran but didn't create snapshots (logic bug)")
    print("  4. Snapshots created but immediately deleted/rolled back")
    print("\nNEXT STEPS:")
    print("  - Check Vercel cron logs (already sent to Grok)")
    print("  - Check Vercel function logs around 20:00 UTC today")
    print("  - Manually trigger: https://apestogether.ai/api/cron/market-close")
else:
    print("✅ Snapshots exist for Sept 30!")
    print("\nBUT charts still show old data, which means:")
    print("  - Chart caches weren't updated after snapshots were created")
    print("  - Need to run: /admin/rebuild-all-caches")

session.close()
