"""Check if snapshots were created for today (Sept 30, 2025)"""
import os
from datetime import date
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

load_dotenv()

# Get database URL
DATABASE_URL = os.environ.get('DATABASE_URL') or os.environ.get('POSTGRES_PRISMA_URL')
if DATABASE_URL.startswith('postgres://'):
    DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql://', 1)

engine = create_engine(DATABASE_URL)
Session = sessionmaker(bind=engine)
session = Session()

# Check for today's snapshots
today = date(2025, 9, 30)

result = session.execute(f"""
SELECT 
    user_id,
    date,
    total_value,
    created_at
FROM portfolio_snapshot
WHERE date = '{today}'
ORDER BY user_id
""")

snapshots = result.fetchall()

print(f"\n=== SNAPSHOTS FOR {today} ===")
print(f"Found: {len(snapshots)} snapshots\n")

if snapshots:
    for snap in snapshots:
        print(f"User {snap[0]}: ${snap[2]:,.2f} (created: {snap[3]})")
else:
    print("❌ NO SNAPSHOTS CREATED FOR TODAY!")
    
# Check latest snapshot date
result = session.execute("""
SELECT 
    MAX(date) as latest_date,
    COUNT(*) as count
FROM portfolio_snapshot
""")

latest = result.fetchone()
print(f"\n=== LATEST SNAPSHOT INFO ===")
print(f"Latest date: {latest[0]}")
print(f"Total snapshots: {latest[1]}")

# Check yesterday for comparison
yesterday = date(2025, 9, 29)
result = session.execute(f"""
SELECT COUNT(*) FROM portfolio_snapshot WHERE date = '{yesterday}'
""")
yesterday_count = result.fetchone()[0]
print(f"Yesterday ({yesterday}): {yesterday_count} snapshots")

session.close()
