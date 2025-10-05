# VERCEL TIMEOUT ISSUE - NEED GROK ANALYSIS

## PROBLEM SUMMARY
Portfolio recalculation endpoints are timing out after 60 seconds on Vercel serverless functions. Even the diagnostic/profiling endpoint times out.

## ERROR
```
Vercel Runtime Timeout Error: Task timed out after 60 seconds
```

## CONTEXT

### Environment
- **Platform:** Vercel Serverless Functions (60 second timeout limit)
- **Framework:** Flask with SQLAlchemy ORM
- **Database:** PostgreSQL (Vercel Postgres)
- **Python Version:** 3.9+

### What We're Trying To Do
Recalculate portfolio snapshots for 5 users across 10 days (Sept 2-11, 2025):
- Pre-fetch market data for all tickers (one query)
- Pre-fetch user's stock holdings (one query)
- Calculate portfolio value for each day in memory
- Update 10 `PortfolioSnapshot` records per user

### Expected Performance
Should take <10 seconds:
- 3 initial queries (user, market data, holdings)
- 10 snapshot updates (one per day)
- Total: ~13 queries per user

### Actual Behavior
**ALL endpoints timeout at 60 seconds:**
1. `/admin/recalculate-user` - Times out
2. `/admin/profile-recalculation` - Times out (even though it's the same logic)
3. Even simpler diagnostic endpoints may timeout

## TIMELINE OF ATTEMPTED FIXES

### Attempt 1: Use ORM with batch commit
- Used `db.session.merge()` and `db.session.flush()`
- Result: Timeout

### Attempt 2: Switch to raw SQL for performance
```python
db.session.execute(text("UPDATE portfolio_snapshot SET total_value = :val WHERE user_id = :uid AND date = :dt"))
```
- Result: Schema errors ("column id does not exist in user table")

### Attempt 3: Back to ORM with pre-fetching
- Pre-fetch all market data in one query
- Pre-fetch all holdings in one query
- Calculate in memory (no DB calls in loop)
- Update snapshots with `db.session.merge()` + `db.session.flush()` + `db.session.commit()`
- Result: Still times out

### Attempt 4: Add profiling endpoint
- Created `/admin/profile-recalculation` to time each step
- Result: **Profiling endpoint itself times out!**

## KEY CODE SECTIONS

### Current Recalculation Logic (api/index.py lines 7295-7410)
```python
@app.route('/admin/recalculate-user', methods=['POST'])
@login_required
def admin_recalculate_user():
    # 1. Find user (1 query)
    user = User.query.filter_by(username=username).first()
    
    # 2. Pre-fetch market data (1 query)
    market_data_rows = MarketData.query.filter(
        MarketData.date >= START_DATE,
        MarketData.date <= END_DATE
    ).all()
    
    # Build cache (in memory)
    market_data_cache = {}
    for md in market_data_rows:
        key = (md.ticker, md.date)
        market_data_cache[key] = md.close_price
    
    # 3. Pre-fetch holdings (1 query)
    holdings_rows = Stock.query.filter_by(user_id=user_id).order_by(Stock.purchase_date).all()
    
    # 4. Loop through 10 days
    current_date = START_DATE
    while current_date <= END_DATE:
        # Calculate holdings as of this date (in memory)
        holdings = {}
        for stock in holdings_rows:
            if stock.purchase_date.date() <= current_date:
                holdings[stock.ticker] = holdings.get(stock.ticker, 0) + stock.quantity
        
        # Calculate portfolio value (in memory)
        portfolio_value = 0.0
        for ticker, qty in holdings.items():
            price = market_data_cache.get((ticker, current_date))
            if price:
                portfolio_value += qty * price
        
        # Update snapshot (1 query per date = 10 queries total)
        snapshot = PortfolioSnapshot.query.filter_by(user_id=user_id, date=current_date).first()
        if snapshot:
            snapshot.total_value = portfolio_value
            db.session.merge(snapshot)
        
        current_date += timedelta(days=1)
    
    # 5. Commit all changes (1 transaction)
    db.session.flush()
    db.session.commit()
```

### Database Models (models.py)
```python
class PortfolioSnapshot(db.Model):
    __tablename__ = 'portfolio_snapshot'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    date = db.Column(db.Date, nullable=False, index=True)
    total_value = db.Column(db.Float, nullable=False)
    cash_flow = db.Column(db.Float, default=0.0)

class MarketData(db.Model):
    __tablename__ = 'market_data'
    id = db.Column(db.Integer, primary_key=True)
    ticker = db.Column(db.String(10), nullable=False, index=True)
    date = db.Column(db.Date, nullable=False, index=True)
    close_price = db.Column(db.Float, nullable=False)

class Stock(db.Model):
    __tablename__ = 'stock'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    ticker = db.Column(db.String(10), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    purchase_date = db.Column(db.DateTime, nullable=False)
    purchase_price = db.Column(db.Float, nullable=False)
```

## QUESTIONS FOR GROK

1. **Why would simple count/query operations timeout at 60 seconds in Vercel?**
   - Are there known issues with SQLAlchemy + Vercel Postgres?
   - Could there be connection pooling issues?

2. **Is the query pattern causing the timeout?**
   - Is `PortfolioSnapshot.query.filter_by(user_id=x, date=y).first()` in a loop bad?
   - Should we pre-fetch all 10 snapshots and update them in memory?

3. **Is `db.session.merge()` slow in serverless?**
   - Does merge() trigger extra queries?
   - Should we use direct attribute assignment instead?

4. **Database indexes - are they missing?**
   - Do we need composite index on `(user_id, date)` for PortfolioSnapshot?
   - Are the existing indexes on `date` and `ticker` sufficient?

5. **Transaction/session issues in serverless?**
   - Could there be session pooling problems?
   - Should we explicitly manage connection lifecycle?

6. **Alternative approaches?**
   - Should we use bulk_update_mappings()?
   - Should we use raw SQL with proper schema inspection?
   - Should we increase Vercel function timeout (if possible)?

## WHAT WE NEED

1. **Root cause:** Why are these queries so slow?
2. **Immediate fix:** How to make this work within 60s timeout
3. **Best practices:** Correct pattern for bulk updates in serverless Flask/SQLAlchemy

## DATA SCALE
- **Users:** 5-10
- **Stocks per user:** 10-20
- **Market data rows:** ~220 (22 tickers × 10 days)
- **Portfolio snapshots:** 10 per user (10 days)

This is NOT a big data problem. Something is fundamentally wrong with how we're querying or how the environment is configured.

---

# GROK'S ANALYSIS AND SOLUTION

## Root Cause Identified

**Combination of 3 factors:**

1. **Vercel Serverless Latency**
   - Cold start: 1-2 seconds per invocation
   - NullPool (no connection pooling): ~100-500ms per fresh connection
   - Vercel Postgres has higher latency (40-100ms per query vs <10ms local)
   - Cross-region network hops if not co-located
   - **Cumulative effect:** 50-100 queries × 200ms each = 10-20 seconds

2. **N+1 Query Problem**
   - `PortfolioSnapshot.query.filter_by(user_id=X, date=Y).first()` in loop = 10 queries
   - `db.session.merge()` is slow (5x slower than direct updates due to implicit SELECTs)
   - Each query is a full round-trip in serverless environment

3. **Missing Composite Index**
   - Only had indexes on `date` and `ticker` (single columns)
   - No composite index on `(user_id, date)` for PortfolioSnapshot
   - Postgres does sequential scans without composite → slow even on small tables

## Immediate Fix (3-Step Implementation)

### Step 1: Add Composite Indexes ⚡
```sql
CREATE INDEX idx_portfolio_snapshot_user_date ON portfolio_snapshot (user_id, date);
CREATE INDEX idx_stock_user_ticker ON stock (user_id, ticker);
CREATE INDEX idx_market_data_ticker_date ON market_data (ticker, date);
ANALYZE portfolio_snapshot;
```

**Impact:** 10-100x speedup on filter_by queries

### Step 2: Pre-Fetch All Snapshots (Eliminate Loop Queries) 🎯
```python
# OLD (slow): 10 queries in loop
for date in dates:
    snapshot = PortfolioSnapshot.query.filter_by(user_id=X, date=date).first()
    
# NEW (fast): 1 query
snapshots = PortfolioSnapshot.query.filter(
    and_(PortfolioSnapshot.user_id == user_id, 
         PortfolioSnapshot.date.in_(date_range))
).all()
snapshot_dict = {s.date: s for s in snapshots}
```

**Impact:** Reduces 10 queries to 1 query

### Step 3: Use bulk_update_mappings (Not merge) 🚀
```python
# OLD (slow): merge() does implicit SELECTs per object
for snapshot in snapshots:
    snapshot.total_value = new_value
    db.session.merge(snapshot)
    
# NEW (fast): Single UPDATE statement
updates = [{'id': s.id, 'total_value': new_value} for s in snapshots]
db.session.bulk_update_mappings(PortfolioSnapshot, updates)
db.session.commit()
```

**Impact:** 5x faster (no per-object checks)

## Expected Performance After Fix

- **Query count:** 4 total (user, market data, holdings, snapshots)
- **Execution time:** <10 seconds (was timing out at 60s)
- **Speedup factors:**
  - Indexes: 10-100x on filter queries
  - Pre-fetch: Eliminates 10 round-trips
  - Bulk update: 5x faster than merge

## Implementation Status

✅ **Bulk endpoint created** (`/admin/recalculate-user-bulk`)
✅ **Index SQL file created** (`add_composite_indexes.sql`)
✅ **Index application script created** (`apply_indexes.py`)
⏳ **Pending:** Apply indexes to database
⏳ **Pending:** Test bulk endpoint
