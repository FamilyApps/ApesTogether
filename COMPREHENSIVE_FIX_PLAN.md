# 🎯 COMPREHENSIVE FIX PLAN
## Synthesis of Claude + Grok Analysis

**Date:** 2025-09-30 20:46 ET  
**Status:** Stock.purchase_date fix deployed ✅  
**Next:** Execute multi-phase repair strategy

---

## 🔍 ROOT CAUSE SUMMARY

### **Primary Issue: Zero-Value Snapshots**
- **190 out of 1,571 snapshots = $0.00**
- Caused by `calculate_portfolio_value()` failing during cron jobs
- Results in 0% or -100% performance calculations
- **Impact:** 4 out of 5 users show 0% gains

### **Secondary Issues:**
1. **PortfolioPerformanceCalculator broken** - TypeError on init
2. **Intraday system not collecting data** - Missing PortfolioSnapshotIntraday entries
3. **Weekend data corruption** - Sunday 9/28 data exists (shouldn't)
4. **Cache fragmentation** - Snapshots, leaderboards, charts update separately
5. **X-axis formatting** - Raw timestamps instead of formatted dates

---

## 📋 PHASE 1: IMMEDIATE ACTIONS (0-30 min)

### **Step 1.1: Run Emergency Cache Rebuild** ✅
**Status:** Ready (Stock.purchase_date fix deployed)

```bash
# Visit URL
https://apestogether.ai/admin/emergency-cache-rebuild
```

**Expected:**
- Chart Caches Fixed: 25+
- Data Points Generated: 500+
- Leaderboards populate (with existing data quality)

**Limitation:** Will still show 0% for users with $0.00 snapshots

---

### **Step 1.2: Diagnose Zero Snapshots** 🔍

**Run diagnostic locally:**
```bash
python diagnose_zero_snapshots.py
```

**This will reveal:**
- Which users have $0.00 snapshots
- Whether they have stocks (expected value)
- Pattern of failures (all users vs specific users)
- Dates affected

**Possible Findings:**
- **If ALL recent snapshots are $0.00:** Alpha Vantage API completely failing
- **If specific users:** Those users' stocks have API issues
- **If specific dates:** API failed on those dates

---

### **Step 1.3: Check Alpha Vantage API** 🔑

**Test API manually:**
```bash
# Check if API key is valid
curl "https://www.alphavantage.co/query?function=GLOBAL_QUOTE&symbol=AAPL&apikey=YOUR_KEY"
```

**Check quotas:**
- Free tier: 25 requests/day
- Premium tier: 75+ requests/minute
- If exceeded: Wait or upgrade

**Common failures:**
- Invalid API key → All snapshots $0.00
- Quota exceeded → Recent snapshots $0.00
- Network timeouts → Sporadic $0.00

---

## 📋 PHASE 2: FIX ZERO-VALUE SNAPSHOTS (30-90 min)

### **Option A: Regenerate Snapshots (If API works now)**

**If diagnostic shows API is working:**

1. **Delete invalid snapshots:**
```sql
-- Backup first!
SELECT * INTO portfolio_snapshot_backup FROM portfolio_snapshot;

-- Delete zero-value snapshots from last 7 days
DELETE FROM portfolio_snapshot 
WHERE total_value = 0 
  AND date >= CURRENT_DATE - INTERVAL '7 days'
  AND user_id IN (SELECT id FROM "user" WHERE id IN (SELECT DISTINCT user_id FROM stock));
```

2. **Regenerate for affected dates:**
```bash
# Create script to backfill
python backfill_snapshots.py --start-date 2025-09-26 --end-date 2025-09-30
```

---

### **Option B: Fix calculate_portfolio_value (If API still failing)**

**Grok's diagnosis:** Function fails silently, falls back to $0.00

**Check `portfolio_performance.py`:**
```python
def calculate_portfolio_value(user_id, as_of_date=None):
    try:
        stocks = Stock.query.filter_by(user_id=user_id).all()
        if not stocks:
            return 0  # Valid $0.00 for users with no stocks
        
        total_value = 0
        for stock in stocks:
            # Get current price from Alpha Vantage
            current_price = get_stock_price(stock.ticker)  # <-- This may be failing
            
            if current_price is None:
                # ⚠️ CRITICAL: What happens here?
                # Bad: return 0  # Makes entire portfolio $0.00
                # Good: Use purchase_price as fallback
                logger.warning(f"Using fallback price for {stock.ticker}")
                current_price = stock.purchase_price
            
            total_value += stock.quantity * current_price
        
        return total_value
    except Exception as e:
        logger.error(f"calculate_portfolio_value failed: {e}")
        # ⚠️ CRITICAL: Don't return 0 silently!
        raise  # Or return None to indicate failure
```

**Fix: Add proper fallback logic and logging**

---

### **Option C: Use Cached Prices (Quick fix)**

**If API is unreliable:**

```python
# Add price caching
from datetime import datetime, timedelta

class StockPriceCache(db.Model):
    ticker = db.Column(db.String(10), primary_key=True)
    price = db.Column(db.Float)
    updated_at = db.Column(db.DateTime)

def get_stock_price_cached(ticker):
    cache = StockPriceCache.query.get(ticker)
    
    # Use cache if less than 1 hour old
    if cache and (datetime.utcnow() - cache.updated_at) < timedelta(hours=1):
        return cache.price
    
    # Fetch fresh price
    price = get_stock_price_from_api(ticker)
    
    if price:
        if cache:
            cache.price = price
            cache.updated_at = datetime.utcnow()
        else:
            cache = StockPriceCache(ticker=ticker, price=price, updated_at=datetime.utcnow())
            db.session.add(cache)
        db.session.commit()
        return price
    
    # Fallback to cached price even if stale
    if cache:
        logger.warning(f"Using stale price for {ticker}")
        return cache.price
    
    return None
```

---

## 📋 PHASE 3: FIX INTRADAY SYSTEM (90-120 min)

### **Step 3.1: Verify IntradayPortfolioSnapshot Table Exists**

**Check models.py:**
```bash
grep -A 10 "class.*Intraday.*Snapshot" models.py
```

**If missing, add to `models.py`:**
```python
class PortfolioSnapshotIntraday(db.Model):
    __tablename__ = 'portfolio_snapshot_intraday'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    timestamp = db.Column(db.DateTime, nullable=False)
    total_value = db.Column(db.Float, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    user = db.relationship('User', backref='intraday_snapshots')
    
    def __repr__(self):
        return f'<IntradaySnapshot {self.user_id} {self.timestamp} ${self.total_value}>'
```

**Create migration:**
```bash
flask db migrate -m "Add PortfolioSnapshotIntraday table"
flask db upgrade
```

---

### **Step 3.2: Fix Intraday Collection Endpoint**

**Update `/api/cron/collect-intraday-data` in `api/index.py`:**

```python
@app.route('/api/cron/collect-intraday-data', methods=['POST'])
def collect_intraday_data():
    """Collect intraday portfolio snapshots (runs every 30 min during market hours)"""
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    if token != os.environ.get('INTRADAY_CRON_TOKEN'):
        logger.error("Invalid INTRADAY_CRON_TOKEN")
        return jsonify({'success': False, 'error': 'Unauthorized'}), 401
    
    try:
        from portfolio_performance import calculate_portfolio_value
        from timezone_utils import is_market_hours, get_market_timezone
        
        # Safety check: Only run during market hours
        now = datetime.now(get_market_timezone())
        if not is_market_hours(now):
            logger.warning(f"Skipping intraday collection outside market hours: {now}")
            return jsonify({'success': True, 'message': 'Outside market hours'})
        
        # Collect for all users
        success_count = 0
        error_count = 0
        
        for user in User.query.all():
            try:
                value = calculate_portfolio_value(user.id)
                
                if value is not None and value > 0:  # Only save valid values
                    snapshot = PortfolioSnapshotIntraday(
                        user_id=user.id,
                        timestamp=now,
                        total_value=value
                    )
                    db.session.add(snapshot)
                    success_count += 1
                else:
                    logger.warning(f"Skipping user {user.id}: value={value}")
                    
            except Exception as e:
                logger.error(f"Failed to create intraday snapshot for user {user.id}: {e}")
                error_count += 1
        
        db.session.commit()
        logger.info(f"Intraday collection: {success_count} snapshots created, {error_count} errors")
        
        return jsonify({
            'success': True,
            'snapshots_created': success_count,
            'errors': error_count,
            'timestamp': now.isoformat()
        })
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Intraday collection failed: {str(e)}")
        import traceback
        return jsonify({
            'success': False,
            'error': str(e),
            'traceback': traceback.format_exc()
        }), 500
```

---

### **Step 3.3: Test Intraday Collection Manually**

```bash
curl -X POST \
  -H "Authorization: Bearer YOUR_INTRADAY_CRON_TOKEN" \
  https://apestogether.ai/api/cron/collect-intraday-data
```

**Expected response:**
```json
{
  "success": true,
  "snapshots_created": 5,
  "errors": 0,
  "timestamp": "2025-09-30T14:30:00-04:00"
}
```

---

## 📋 PHASE 4: FIX WEEKEND DATA (30-60 min)

### **Step 4.1: Improve is_market_hours Function**

**In `timezone_utils.py` or `portfolio_performance.py`:**

```python
from zoneinfo import ZoneInfo

def get_market_timezone():
    """Get US/Eastern timezone with DST support"""
    return ZoneInfo('America/New_York')

def is_market_hours(dt=None):
    """Check if datetime is during market hours (Mon-Fri, 9:30 AM - 4:00 PM ET)"""
    if dt is None:
        dt = datetime.now(get_market_timezone())
    elif dt.tzinfo is None:
        dt = dt.replace(tzinfo=get_market_timezone())
    
    # Check weekday (Monday=0, Friday=4)
    if dt.weekday() >= 5:  # Saturday=5, Sunday=6
        return False
    
    # Check time range
    market_open = dt.replace(hour=9, minute=30, second=0, microsecond=0)
    market_close = dt.replace(hour=16, minute=0, second=0, microsecond=0)
    
    return market_open <= dt <= market_close
```

---

### **Step 4.2: Clean Weekend Data from Database**

```sql
-- Check for weekend data first
SELECT date, COUNT(*) as count
FROM portfolio_snapshot
WHERE EXTRACT(DOW FROM date) IN (0, 6)  -- Sunday=0, Saturday=6
ORDER BY date DESC;

-- If found, delete (backup first!)
DELETE FROM portfolio_snapshot
WHERE EXTRACT(DOW FROM date) IN (0, 6);

-- Same for intraday
DELETE FROM portfolio_snapshot_intraday
WHERE EXTRACT(DOW FROM timestamp) IN (0, 6);
```

---

### **Step 4.3: Add Weekend Filter to Chart Generation**

**In `leaderboard_utils.py`, update `generate_chart_from_snapshots`:**

```python
def generate_chart_from_snapshots(user_id, period):
    start_date = get_period_start(period)
    today = date.today()
    
    # Query snapshots
    snapshots = PortfolioSnapshot.query.filter(
        PortfolioSnapshot.user_id == user_id,
        PortfolioSnapshot.date >= start_date,
        PortfolioSnapshot.date <= today,
        PortfolioSnapshot.total_value > 0  # Exclude zero-value snapshots
    ).order_by(PortfolioSnapshot.date.asc()).all()
    
    # Filter out weekends (safety check)
    snapshots = [s for s in snapshots if s.date.weekday() < 5]
    
    if not snapshots:
        return None
    
    # Generate chart data...
```

---

## 📋 PHASE 5: UNIFIED CACHE UPDATE (60-90 min)

**Grok's recommendation:** Consolidate all cache updates into market-close cron for atomicity.

### **Update `/api/cron/market-close` in `api/index.py`:**

```python
@app.route('/api/cron/market-close', methods=['POST'])
def market_close():
    """
    Unified market close handler:
    1. Create daily snapshots for all users
    2. Update all chart caches
    3. Update all leaderboard caches
    """
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    if token != os.environ.get('INTRADAY_CRON_TOKEN'):
        logger.error("Invalid token for market-close")
        return jsonify({'success': False, 'error': 'Unauthorized'}), 401
    
    try:
        from portfolio_performance import calculate_portfolio_value
        from leaderboard_utils import (
            update_leaderboard_cache,
            generate_chart_from_snapshots,
            generate_intraday_chart
        )
        
        logger.info("🔔 MARKET CLOSE: Starting unified cache update...")
        
        # Use transaction for atomicity
        db.session.begin()
        
        # STEP 1: Create daily snapshots
        logger.info("Step 1: Creating daily snapshots...")
        snapshot_count = 0
        today = date.today()
        
        for user in User.query.all():
            try:
                value = calculate_portfolio_value(user.id)
                
                if value is not None:
                    # Check if snapshot already exists
                    existing = PortfolioSnapshot.query.filter_by(
                        user_id=user.id,
                        date=today
                    ).first()
                    
                    if existing:
                        existing.total_value = value
                    else:
                        snapshot = PortfolioSnapshot(
                            user_id=user.id,
                            date=today,
                            total_value=value
                        )
                        db.session.add(snapshot)
                    
                    snapshot_count += 1
                else:
                    logger.warning(f"User {user.id}: calculate_portfolio_value returned None")
                    
            except Exception as e:
                logger.error(f"Failed to create snapshot for user {user.id}: {e}")
        
        logger.info(f"Created/updated {snapshot_count} daily snapshots")
        
        # STEP 2: Update chart caches for all users/periods
        logger.info("Step 2: Updating chart caches...")
        periods = ['1D', '5D', '1M', '3M', 'YTD', '1Y', '5Y', 'MAX']
        chart_count = 0
        
        for user in User.query.all():
            for period in periods:
                try:
                    # Use intraday for 1D, daily for others
                    if period == '1D':
                        chart_data = generate_intraday_chart(user.id)
                    else:
                        chart_data = generate_chart_from_snapshots(user.id, period)
                    
                    if chart_data:
                        cache = UserPortfolioChartCache.query.filter_by(
                            user_id=user.id,
                            period=period
                        ).first()
                        
                        if cache:
                            cache.chart_data = json.dumps(chart_data)
                            cache.generated_at = datetime.now()
                        else:
                            cache = UserPortfolioChartCache(
                                user_id=user.id,
                                period=period,
                                chart_data=json.dumps(chart_data),
                                generated_at=datetime.now()
                            )
                            db.session.add(cache)
                        
                        chart_count += 1
                        
                except Exception as e:
                    logger.error(f"Failed to generate chart for user {user.id}, period {period}: {e}")
        
        logger.info(f"Updated {chart_count} chart caches")
        
        # STEP 3: Update leaderboard caches
        logger.info("Step 3: Updating leaderboard caches...")
        leaderboard_count = update_leaderboard_cache(periods)
        logger.info(f"Updated {leaderboard_count} leaderboard caches")
        
        # STEP 4: Cleanup stale caches (optional)
        logger.info("Step 4: Cleaning up stale caches...")
        threshold = datetime.now() - timedelta(days=7)
        old_charts = UserPortfolioChartCache.query.filter(
            UserPortfolioChartCache.generated_at < threshold
        ).delete()
        old_leaderboards = LeaderboardCache.query.filter(
            LeaderboardCache.generated_at < threshold
        ).delete()
        logger.info(f"Removed {old_charts} old chart caches, {old_leaderboards} old leaderboard caches")
        
        # Commit all changes atomically
        db.session.commit()
        
        logger.info("✅ MARKET CLOSE: Unified cache update completed successfully")
        
        return jsonify({
            'success': True,
            'snapshots_created': snapshot_count,
            'charts_updated': chart_count,
            'leaderboards_updated': leaderboard_count,
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Market close failed: {str(e)}")
        import traceback
        return jsonify({
            'success': False,
            'error': str(e),
            'traceback': traceback.format_exc()
        }), 500
```

---

## 📋 SUCCESS CRITERIA

### ✅ **Phase 1 Complete:**
- [ ] Emergency cache rebuild runs successfully
- [ ] Chart caches have > 0 data points
- [ ] Leaderboards show 5 users (even with current data quality)

### ✅ **Phase 2 Complete:**
- [ ] Zero-value snapshots identified and root cause found
- [ ] All users with stocks have non-zero snapshots for recent dates
- [ ] Leaderboards show real % gains (not 0% or -100%)

### ✅ **Phase 3 Complete:**
- [ ] PortfolioSnapshotIntraday table exists and populated
- [ ] 1D charts display intraday data
- [ ] 1D leaderboard shows 5 users with real gains

### ✅ **Phase 4 Complete:**
- [ ] No weekend data in database
- [ ] Friday 9/27 data present in all charts
- [ ] Monday 9/30 data present and updating

### ✅ **Phase 5 Complete:**
- [ ] Unified market-close cron working
- [ ] All caches update atomically at end of day
- [ ] No stale or inconsistent cache data

---

## 🚀 IMMEDIATE NEXT STEPS

1. **Run emergency cache rebuild** (2 min wait for deploy)
2. **Run `diagnose_zero_snapshots.py` locally** (reveals zero-value cause)
3. **Check Alpha Vantage API status** (is it working now?)
4. **Based on diagnostic results:**
   - If API works: Regenerate snapshots (Phase 2A)
   - If API broken: Fix fallback logic (Phase 2B)
   - If need quick fix: Implement price caching (Phase 2C)

---

## 📊 MONITORING & VALIDATION

After each phase, check:

```sql
-- Verify non-zero snapshots
SELECT user_id, date, total_value
FROM portfolio_snapshot
WHERE date >= CURRENT_DATE - 7
ORDER BY date DESC, user_id;

-- Verify chart caches populated
SELECT user_id, period, LENGTH(chart_data) as size, generated_at
FROM user_portfolio_chart_cache
ORDER BY generated_at DESC;

-- Verify leaderboard caches
SELECT period, LENGTH(leaderboard_data) as size, generated_at
FROM leaderboard_cache
ORDER BY generated_at DESC;

-- Check for weekend data (should be empty)
SELECT date, COUNT(*)
FROM portfolio_snapshot
WHERE EXTRACT(DOW FROM date) IN (0, 6)
GROUP BY date;
```

---

**Last Updated:** 2025-09-30 20:46 ET  
**Status:** Ready to execute Phase 1
