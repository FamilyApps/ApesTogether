# Critical Database Transaction Issue - Grok Review Request

## Problem Summary
Market close cron job creates S&P 500 data (MarketData record), flushes it to session, commits successfully, but the data doesn't persist to the database. Verification query immediately after commit finds no data.

## Evidence from Logs (10/21/2025)
```
✅ Created S&P 500 data for 2025-10-21: $6712.30
✅ Flushed S&P 500 data to session
✅ PHASE 3 Complete: All changes committed successfully
❌ VERIFICATION FAILED: S&P 500 data NOT found in DB for 2025-10-21
```

## Suspicious Finding
Phase 2.5 has a bug that throws an exception AFTER MarketData is added but BEFORE commit:
```
WARNING - HTML pre-rendering error: 'category' is an invalid keyword argument for LeaderboardCache
```

This exception is caught and doesn't stop execution, but might corrupt session state.

## Transaction Flow
1. **Phase 1**: Create PortfolioSnapshot objects → `db.session.add(snapshot)`
2. **Phase 1.5**: Create MarketData object → `db.session.add(market_data)` → `db.session.flush()`
3. **Phase 2**: Call `update_leaderboard_cache()` (adds LeaderboardCache & UserPortfolioChartCache objects)
4. **Phase 2.5**: Try to create LeaderboardCache with invalid `category` parameter → **EXCEPTION CAUGHT**
5. **Phase 3**: `db.session.commit()` → **Reports success**
6. **Phase 3.5**: `db.session.expire_all()` → Query for MarketData → **NOT FOUND**

## Key Questions
1. Could the Phase 2.5 exception corrupt the session state even though it's caught?
2. Could `update_leaderboard_cache()` be doing something that detaches/expunges the MarketData object?
3. Is there a transaction isolation or replication lag issue?
4. Why do PortfolioSnapshot objects persist but MarketData doesn't, when they're in the same transaction?

## Database Details
- PostgreSQL database (Vercel Postgres)
- Flask-SQLAlchemy ORM
- Single atomic transaction for all phases
- Commit reports success but data vanishes

## Files to Review
1. `api/index.py` - Lines 14737-15065 (market_close_cron function)
2. `leaderboard_utils.py` - Lines 726-935 (update_leaderboard_cache function)
3. `models.py` - Lines 158-172 (LeaderboardCache model definition)

## Specific Code Locations

### Phase 1.5 - MarketData Creation (api/index.py:14891-14900)
```python
market_data = MarketData(
    ticker='SPY_SP500',
    date=today_et,
    close_price=sp500_value
)
db.session.add(market_data)
logger.info(f"Created S&P 500 data for {today_et}: ${sp500_value:.2f}")

db.session.flush()
logger.info(f"Flushed S&P 500 data to session")
```

### Phase 2.5 - Exception Location (api/index.py:14983-14990)
```python
cache_entry = LeaderboardCache.query.filter_by(period=cache_key).first()
if not cache_entry:
    cache_entry = LeaderboardCache(
        period=cache_key,
        category=category,  # ❌ FIELD DOESN'T EXIST!
        leaderboard_data={}
    )
    db.session.add(cache_entry)
```

### LeaderboardCache Model (models.py:158-172)
```python
class LeaderboardCache(db.Model):
    __tablename__ = 'leaderboard_cache'
    
    id = db.Column(db.Integer, primary_key=True)
    period = db.Column(db.String(20), nullable=False)
    leaderboard_data = db.Column(db.Text, nullable=False)
    rendered_html = db.Column(db.Text, nullable=True)
    generated_at = db.Column(db.DateTime, nullable=False)
    # NO category FIELD!
```

### Phase 3 - Commit (api/index.py:15009-15016)
```python
logger.info("PHASE 3: Committing all changes atomically...")
results['pipeline_phases'].append('commit_started')

db.session.commit()

results['pipeline_phases'].append('commit_completed')
logger.info("PHASE 3 Complete: All changes committed successfully")
```

### Phase 3.5 - Verification Failure (api/index.py:15018-15038)
```python
logger.info("PHASE 3.5: Verifying S&P 500 data persistence...")
from models import MarketData

# Force a new query outside the transaction to verify persistence
db.session.expire_all()  # Clear any cached objects

verify_sp500 = MarketData.query.filter_by(
    ticker='SPY_SP500',
    date=today_et
).first()

if verify_sp500:
    logger.info(f"✅ VERIFIED: S&P 500 data exists")
else:
    logger.error(f"❌ VERIFICATION FAILED: S&P 500 data NOT found")
```

## What We've Tried
1. ✅ Fixed endpoint name conflicts
2. ✅ Removed db.session.commit() from API logging (cascade timeout issue)
3. ✅ Added force_fetch=True for historical price fetching
4. ✅ Manual backfill using `/admin/backfill-sp500/2025-10-21` works perfectly
5. ❌ Automated market close cron consistently fails to persist S&P 500 data

## Working vs Broken
- **Manual backfill** (`/admin/backfill-sp500/<date>`): Creates MarketData, commits → ✅ WORKS
- **Automated cron** (market_close_cron): Creates MarketData, commits → ❌ DATA VANISHES

The manual backfill is simpler (no Phase 2.5, no leaderboard cache update), which might be the key difference.

## Request for Grok
Please review the entire transaction flow and identify:
1. Why MarketData disappears after commit
2. How the Phase 2.5 exception might affect session state
3. Whether `update_leaderboard_cache()` could be detaching objects
4. Any Flask-SQLAlchemy session management issues
5. Best practices for fixing this atomic transaction

Thank you!
