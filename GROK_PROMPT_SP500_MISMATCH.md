# Grok Prompt: S&P 500 Return Mismatch & Date Offset Issues

---

## CONTEXT

Stock portfolio Flask app on Vercel with PostgreSQL. After fixing intraday chart timezone issues (converting timestamps to ET), we now have two new problems with longer-period charts (YTD, 1M, 3M, 1Y).

**Previous Fix Applied:**
- Converted intraday timestamps to ET before sending to frontend
- Removed duplicate EOD snapshot logic
- This fixed 1D chart display (now shows 9 AM - 4:30 PM correctly)

**New Issues Discovered:**
1. S&P 500 return percentages don't match between card header and chart data points
2. Today's market close snapshot (Oct 2, 2025) is labeled as tomorrow (10/3/2025) in charts

---

## PROBLEM #1: S&P 500 Return Discrepancies

### User Report (With Screenshots):

**YTD Chart:**
- Card Header: "S&P 500: +0%" ❌
- Chart Data Point (Oct 2): "S&P 500: +14.34%" ✓ (This appears correct for YTD 2025)
- **Discrepancy: 14.34 percentage points**

**1M Chart:**
- Card Header: "S&P 500: +0.83%" ❌
- Chart Data Point (latest): "S&P 500: +1.76%" ✓ (Likely correct)
- **Discrepancy: 0.93 percentage points**

**Portfolio Returns (Minor Issue):**
- Card Header: "Portfolio: +7.48%"
- Chart Data Point: "Portfolio: +7.45%"
- **Discrepancy: 0.03% (acceptable rounding difference?)**

### Code Analysis:

**TWO SEPARATE CALCULATIONS** are happening:

**Calculation #1: Card Header (Top of Chart Card)**  
File: `portfolio_performance.py` lines 515-553

```python
def calculate_sp500_return(self, start_date: date, end_date: date) -> float:
    """Calculate S&P 500 return for a period"""
    sp500_data = self.get_sp500_data(start_date, end_date)  # May fetch from API or cache
    
    # Find start price (first date >= start_date)
    for d in available_dates:
        if d >= start_date:
            start_price = sp500_data[d]
            break
    
    # Find end price (last date <= end_date)
    for d in reversed(available_dates):
        if d <= end_date:
            end_price = sp500_data[d]
            break
    
    sp500_return = (end_price - start_price) / start_price
    logger.info(f"S&P 500 return calculated: {sp500_return:.4f} from {start_price} to {end_price}")
    return sp500_return
```

**Calculation #2: Chart Data Points**  
File: `portfolio_performance.py` lines 838-869

```python
# Get S&P 500 data for charting
sp500_data = self.get_cached_sp500_data(start_date, end_date)

# Find baseline (first available date >= start_date)
period_start_sp500 = None
for date_key in sp500_dates:
    if date_key >= start_date:
        period_start_sp500 = sp500_data[date_key]
        break

# Build chart points
for date_key in sampled_dates:
    if date_key >= start_date and date_key in sp500_data:
        sp500_pct = ((sp500_data[date_key] - period_start_sp500) / period_start_sp500) * 100
        
        chart_data.append({
            'date': date_key.isoformat(),
            'sp500': round(sp500_pct, 2)
        })
```

### Hypothesis:

**Root Cause #1: Different Data Sources**
- Card header: `get_sp500_data()` - May fetch from Alpha Vantage API (live) OR fallback to cache
- Chart data: `get_cached_sp500_data()` - Uses MarketData table only

**Root Cause #2: Missing Data in MarketData Table**
- If MarketData has NO S&P 500 records for YTD period (since Jan 1, 2025):
  - `calculate_sp500_return()` returns 0% (no data found)
  - But chart generation might use fallback or different logic
  
**Root Cause #3: Date Boundary Mismatch**
- Card calculation finds "first date >= start_date"
- Chart calculation also finds "first date >= start_date"
- **But if they're querying different tables, the "first date" might be different!**

### Questions for Grok:

**Q1:** Could the MarketData table be missing S&P 500 records?  
- If yes, `calculate_sp500_return()` would return 0% while chart uses different data
- How should we verify this? Check logs or query database?

**Q2:** Should both calculations use the SAME data source?
- Currently card uses `get_sp500_data()` (API or cache)
- Chart uses `get_cached_sp500_data()` (cache only)
- This inconsistency could explain discrepancies

**Q3:** How should we fix this?
- Option A: Make card header extract percentage from chart last data point
- Option B: Ensure both use `get_cached_sp500_data()` consistently
- Option C: Store S&P return in snapshot at market close, read from there

---

## PROBLEM #2: Date Labeling Off By One Day

### User Report:
- Today is **October 2, 2025** (market closed at 4 PM ET)
- Market close cron ran successfully, created EOD snapshots
- **BUT** charts show today's snapshot labeled as **10/3/2025** ❌
- This affects 1M, 3M, and 1Y charts (longer periods)

### Code Analysis:

**Market Close Snapshot Creation (CORRECT):**  
File: `api/index.py` lines 9714-9775

```python
# Use Eastern Time for market operations
current_time = get_market_time()  # datetime.now(ZoneInfo('America/New_York'))
today_et = current_time.date()  # Oct 2, 2025

# Create snapshot with ET date
snapshot = PortfolioSnapshot(
    user_id=user.id,
    date=today_et,  # Should be Oct 2, 2025
    total_value=portfolio_value
)
db.session.add(snapshot)
```

**Chart Generation Date Calculation:**  
File: `leaderboard_utils.py` lines 420-431

```python
def get_last_market_day():
    """Get last market day (adjusts for weekends)"""
    today = date.today()  # ⚠️ USES SYSTEM TIMEZONE (UTC on Vercel!)
    
    if today.weekday() == 5:  # Saturday
        return today - timedelta(days=1)
    elif today.weekday() == 6:  # Sunday
        return today - timedelta(days=2)
    else:
        return today  # Monday-Friday
```

**THE BUG:**
- `date.today()` uses **system timezone** = UTC on Vercel
- Market close runs at **4:00 PM ET** = **8:00 PM UTC**
- If chart is accessed after **8:00 PM ET** = **12:00 AM UTC (next day)**
- `date.today()` in UTC returns **Oct 3** instead of **Oct 2**!

### Timeline Example:

```
Oct 2, 2025:
- 4:00 PM ET (20:00 UTC): Market close cron runs
  - Creates snapshot with date = Oct 2, 2025 (ET)
  
- 10:00 PM ET (02:00 UTC Oct 3): User views dashboard
  - Chart generation calls get_last_market_day()
  - date.today() returns Oct 3, 2025 (UTC)
  - Snapshot with date=Oct 2 is labeled as "yesterday" or filtered out
  - OR queries use Oct 3 as "today" causing +1 day shift
```

### Hypothesis:

**Root Cause:** Inconsistent timezone usage
- Market close: Uses `datetime.now(ZoneInfo('America/New_York')).date()` ✓
- Chart generation: Uses `date.today()` (system UTC) ❌

**Also affects:** `generate_user_portfolio_chart()` line 587
```python
today = datetime.now(MARKET_TZ).date()  # Correctly uses ET
```
But then calls `get_last_market_day()` elsewhere which uses UTC!

### Questions for Grok:

**Q4:** Is `date.today()` the culprit?
- Should ALL date operations use `datetime.now(ZoneInfo('America/New_York')).date()`?
- Are there other places using `date.today()` or `datetime.now()` without timezone?

**Q5:** Why +1 day specifically?
- User accessed dashboard at 10:11 PM ET (02:11 AM UTC Oct 3)
- Snapshot created at 4 PM ET (20:00 UTC Oct 2) with date=Oct 2
- But displayed as Oct 3 because query logic uses UTC "today"?

**Q6:** How are snapshot dates being formatted for chart labels?
```python
# leaderboard_utils.py line 688
labels = [snapshot.date.strftime('%Y-%m-%d') for snapshot in snapshots]
```
- `snapshot.date` is a DATE field (no timezone)
- Strftime should just return the stored date
- So the issue must be in the QUERY logic, not formatting

---

## PROPOSED FIXES

### Fix #1: Align S&P 500 Data Sources

**Approach A: Use Cached Data Consistently**

```python
# In calculate_sp500_return() - line 515
def calculate_sp500_return(self, start_date: date, end_date: date) -> float:
    """Calculate S&P 500 return for a period"""
    # CHANGE: Always use cached data for consistency with charts
    sp500_data = self.get_cached_sp500_data(start_date, end_date)  # Not get_sp500_data()
    
    if not sp500_data:
        logger.warning(f"No cached S&P 500 data for {start_date} to {end_date}")
        return 0.0
    
    # Rest of calculation remains same
    ...
```

**Approach B: Extract from Chart Data**

```python
# In get_performance_data() - after building chart_data
# Instead of separate calculate_sp500_return() call:

if chart_data and len(chart_data) > 0:
    # Card header should match chart's last data point
    sp500_return = chart_data[-1]['sp500'] / 100  # Convert back to decimal
else:
    sp500_return = self.calculate_sp500_return(start_date, end_date)
```

### Fix #2: Use ET Consistently for All Date Operations

**File:** `leaderboard_utils.py` lines 420-431

```python
# BEFORE:
def get_last_market_day():
    today = date.today()  # UTC on Vercel!

# AFTER:
def get_last_market_day():
    from zoneinfo import ZoneInfo
    from datetime import datetime
    MARKET_TZ = ZoneInfo('America/New_York')
    today = datetime.now(MARKET_TZ).date()  # ET, not UTC
    
    if today.weekday() == 5:  # Saturday
        return today - timedelta(days=1)
    elif today.weekday() == 6:  # Sunday
        return today - timedelta(days=2)
    else:
        return today
```

**Also check:** All other uses of `date.today()` or `datetime.now()` without timezone

### Fix #3: Populate Missing S&P 500 Data (If Needed)

If MarketData table is missing S&P 500 records:
- Backfill historical data from Alpha Vantage
- Ensure market close cron is collecting S&P 500 data daily
- Verify SPY_SP500 ticker records exist for Jan 1, 2025 onwards

---

## VERIFICATION QUERIES

To help diagnose, please validate:

### Check S&P 500 Data Availability:

```sql
-- Check if MarketData has S&P 500 for YTD period
SELECT COUNT(*), MIN(date), MAX(date)
FROM market_data
WHERE ticker = 'SPY_SP500'
  AND date >= '2025-01-01';

-- Should return: count > 0, min_date = 2025-01-01 (or close to it)
```

### Check Snapshot Dates:

```sql
-- Verify Oct 2 snapshots exist with correct date
SELECT user_id, date, total_value
FROM portfolio_snapshot
WHERE date = '2025-10-02';

-- Should return 5 users with Oct 2 snapshots
```

### Check System vs ET Date:

```python
# Test in Python console or debug endpoint
from datetime import date, datetime
from zoneinfo import ZoneInfo

system_date = date.today()  # What Vercel sees (UTC)
et_date = datetime.now(ZoneInfo('America/New_York')).date()  # Market time

print(f"System UTC date: {system_date}")
print(f"Market ET date: {et_date}")
print(f"Difference: {(system_date - et_date).days} days")

# If accessed after 8 PM ET, difference should be +1
```

---

## CRITICAL QUESTIONS SUMMARY

1. **Q1:** Is MarketData missing S&P 500 records for YTD? (Would explain +0% in card)
2. **Q2:** Should both card and chart use `get_cached_sp500_data()` for consistency?
3. **Q3:** Best approach - extract from chart last point OR fix data source?
4. **Q4:** Is `date.today()` causing +1 day offset due to UTC vs ET timezone?
5. **Q5:** Should ALL date operations use `datetime.now(ZoneInfo('America/New_York')).date()`?
6. **Q6:** Are there other timezone-naive date operations we're missing?

---

## DEPLOYMENT CONTEXT

- **Platform:** Vercel (serverless, runs in UTC)
- **Database:** PostgreSQL (Vercel Postgres)
- **Market Hours:** 9:30 AM - 4:00 PM ET
- **Current Time:** 10:16 PM ET = 2:16 AM UTC (Oct 3)
- **Previous Fixes:** Intraday timezone conversion (working), duplicate cron removal (working)

---

## FILES FOR REVIEW

Please review these specific sections:

1. **`portfolio_performance.py`**
   - Lines 515-553: `calculate_sp500_return()` method
   - Lines 771-901: `get_performance_data()` method
   - Lines 838-869: Chart data generation logic
   - Look for: Data source inconsistencies, date boundary issues

2. **`leaderboard_utils.py`**
   - Lines 420-431: `get_last_market_day()` - **KEY SUSPECT for date offset**
   - Lines 433-570: `calculate_leaderboard_data()` 
   - Lines 656-709: Chart generation for cached data
   - Look for: `date.today()` usage, timezone-naive operations

3. **`api/index.py`**
   - Lines 7318-7420: `/api/portfolio/performance/<period>` endpoint
   - Lines 7345-7391: Cached chart data extraction
   - Lines 9714-9775: Market close snapshot creation (uses ET correctly)

---

Please provide:
1. **Validation** of root cause hypotheses (S&P data source mismatch, UTC vs ET dates)
2. **Recommended fixes** for both issues
3. **Any additional edge cases** or issues you spot
4. **Implementation priority** - which fix should be applied first?

Thank you!
