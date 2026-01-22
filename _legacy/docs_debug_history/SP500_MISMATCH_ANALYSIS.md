# S&P 500 Return Mismatch & Date Labeling Issues

**Date:** October 2, 2025 10:16 PM ET  
**Issues:** S&P 500 returns don't match between card header and chart data points; dates off by 1 day

---

## 🔴 ISSUE #1: S&P 500 Return Discrepancies

### Symptoms (User Reports):

**YTD Chart:**
- **Card Header:** S&P 500 gains = **+0%** ❌
- **Chart Data Point (Oct 2):** S&P 500 = **+14.34%** ✓ (appears correct)
- **Discrepancy:** 14.34 percentage points!

**1M Chart:**
- **Card Header:** S&P 500 gains = **+0.83%** ❌
- **Chart Data Point (latest):** S&P 500 = **+1.76%** ✓ (likely correct)
- **Discrepancy:** 0.93 percentage points

**Portfolio Returns (Minor Discrepancy):**
- **Card Header:** Portfolio = **+7.48%**
- **Chart Data Point:** Portfolio = **+7.45%**
- **Discrepancy:** 0.03 percentage points (acceptable rounding difference)

---

## 🔴 ISSUE #2: Date Labeling Off By One Day

### Symptoms:
- Today is **October 2, 2025**
- Market close snapshot was created at **4:00 PM ET on Oct 2**
- **BUT** charts (1M, 3M, 1Y) show today's snapshot labeled as **10/3/2025** ❌
- This is a **+1 day offset error**

---

## 🔍 ROOT CAUSE ANALYSIS

### Where the Data Flows:

1. **Market Close Cron** (4:00 PM ET) → Creates EOD snapshots with `today_et` date
2. **Cache Generation** → `update_leaderboard_cache()` → `generate_user_portfolio_chart()`  
3. **Frontend Request** → `/api/portfolio/performance/<period>` endpoint
4. **Response Path A (Cached):** Uses pre-generated chart cache from market close
5. **Response Path B (Live):** Calls `PortfolioPerformanceCalculator.get_performance_data()`

### The Fork: Two Separate Calculations

**Path A: Card Header Percentages**
- Source: `calculate_sp500_return(start_date, end_date)` in `portfolio_performance.py`
- Method: Finds start/end prices from `MarketData` table
- Formula: `(end_price - start_price) / start_price`
- Returns: Single percentage value for the period

**Path B: Chart Data Points**
- Source: Chart data built from `PortfolioSnapshot` records
- Method: Iterates through snapshots, calculates percentage relative to FIRST snapshot
- Formula: `((snapshot_value - first_value) / first_value) * 100`
- Returns: Array of {date, portfolio%, sp500%} for each day

**THE PROBLEM:** These two calculations use DIFFERENT base values!

---

## 📊 DETAILED CODE ANALYSIS

### Issue #1: S&P 500 Return Calculation Mismatch

**Location 1: Card Header Calculation**  
File: `portfolio_performance.py` lines 515-553

```python
def calculate_sp500_return(self, start_date: date, end_date: date) -> float:
    """Calculate S&P 500 return for a period"""
    sp500_data = self.get_sp500_data(start_date, end_date)  # Gets MarketData records
    
    # Find start price (closest date >= start_date)
    for d in available_dates:
        if d >= start_date:
            start_price = sp500_data[d]
            break
    
    # Find end price (closest date <= end_date)
    for d in reversed(available_dates):
        if d <= end_date:
            end_price = sp500_data[d]
            break
    
    sp500_return = (end_price - start_price) / start_price
    return sp500_return
```

**Location 2: Chart Data Calculation**  
File: `portfolio_performance.py` lines 838-869

```python
# Find S&P 500 data for the full period
period_start_sp500 = None
for date_key in sp500_dates:
    if date_key >= start_date:
        period_start_sp500 = sp500_data[date_key]  # FIRST available date >= start_date
        break

# Build chart data
for date_key in sampled_dates:
    if date_key >= start_date and date_key in sp500_data:
        sp500_pct = ((sp500_data[date_key] - period_start_sp500) / period_start_sp500) * 100
```

**THE BUG:**
- **Card header:** Uses `calculate_sp500_return()` which finds start/end prices
- **Chart data:** Uses FIRST available snapshot in chart as baseline
- **If data is missing or sampled differently, the baselines don't match!**

### Issue #2: Date Labeling Off By One Day

**Hypothesis 1: UTC vs ET Date Extraction**

Market close cron creates snapshots at 4 PM ET with correct ET date:
```python
# api/index.py line 9714-9769
current_time = get_market_time()  # ET timezone-aware
today_et = current_time.date()  # Oct 2, 2025

snapshot = PortfolioSnapshot(
    user_id=user.id,
    date=today_et,  # Should be Oct 2, 2025
    total_value=portfolio_value
)
```

**But when querying for chart generation:**
```python
# leaderboard_utils.py line 587
today = datetime.now(MARKET_TZ).date()  # Should be Oct 2, 2025
```

**Then when formatting labels:**
```python
# leaderboard_utils.py line 688
labels = [snapshot.date.strftime('%Y-%m-%d') for snapshot in snapshots]
```

**QUESTION:** Is `snapshot.date` being stored correctly or is there a timezone conversion happening?

**Hypothesis 2: Weekend/Market Day Calculation**

```python
# leaderboard_utils.py line 420-431
def get_last_market_day():
    today = date.today()  # Uses system date (could be UTC on Vercel?)
    
    if today.weekday() == 5:  # Saturday
        return today - timedelta(days=1)  # Friday
    elif today.weekday() == 6:  # Sunday
        return today - timedelta(days=2)  # Friday
    else:
        return today
```

**THE BUG:** `date.today()` uses system timezone (UTC on Vercel), not ET!
- If queried after 8 PM ET (midnight UTC), `date.today()` returns Oct 3 in UTC
- But market close ran at 4 PM ET (8 PM UTC) on Oct 2
- This creates a mismatch where today's snapshot (Oct 2) is labeled as tomorrow (Oct 3)

---

## 🎯 PROPOSED FIXES

### Fix #1: Align S&P 500 Return Calculations

**Option A:** Use consistent baseline for both calculations
```python
# In get_performance_data(), use the SAME sp500_data baseline for both:
sp500_return_value = calculate_sp500_return(start_date, end_date)

# But also store the baseline used in chart data generation
chart_baseline_sp500 = period_start_sp500  # First available date
chart_end_sp500 = sp500_data[end_date]

# Ensure card header uses same calculation as chart last point
sp500_return_for_card = ((chart_end_sp500 - chart_baseline_sp500) / chart_baseline_sp500) * 100
```

**Option B:** Fix `calculate_sp500_return()` to use consistent data source
- Ensure it queries the SAME MarketData records as chart generation
- Use the SAME date filtering logic

**Root Issue:** There are TWO S&P 500 data sources:
1. `get_sp500_data()` - May fetch from Alpha Vantage API
2. `get_cached_sp500_data()` - Uses MarketData table

Chart uses `get_cached_sp500_data()` but card header may use live API data!

### Fix #2: Date Labeling (Use ET Consistently)

**File:** `leaderboard_utils.py` line 420-431

```python
# BEFORE:
def get_last_market_day():
    today = date.today()  # Uses system timezone (UTC on Vercel!)

# AFTER:
def get_last_market_day():
    from zoneinfo import ZoneInfo
    from datetime import datetime
    MARKET_TZ = ZoneInfo('America/New_York')
    today = datetime.now(MARKET_TZ).date()  # Use ET, not UTC
```

**Also check:** `generate_user_portfolio_chart()` line 587
```python
# Currently uses ET correctly:
today = datetime.now(MARKET_TZ).date()

# But ensure ALL date comparisons use ET!
```

---

## 🔬 DIAGNOSTIC QUERIES

### Check S&P 500 Data Sources:

```sql
-- Check MarketData table for S&P 500
SELECT ticker, date, close_price, timestamp
FROM market_data
WHERE ticker IN ('SPY_SP500', 'SPY_INTRADAY')
  AND date >= '2025-01-01'
ORDER BY date DESC
LIMIT 20;
```

### Check Portfolio Snapshot Dates:

```sql
-- Check if dates are stored correctly
SELECT user_id, date, total_value, 
       EXTRACT(DOW FROM date) as day_of_week
FROM portfolio_snapshot
WHERE date >= '2025-10-01'
ORDER BY date DESC, user_id;
```

### Check Cached Chart Data:

```sql
-- Check what's in the chart cache
SELECT user_id, period, 
       LENGTH(chart_data) as data_size,
       generated_at
FROM user_portfolio_chart_cache
WHERE period IN ('YTD', '1M', '3M')
ORDER BY generated_at DESC;
```

---

## 🚨 CRITICAL QUESTIONS FOR GROK

### Question #1: S&P 500 Data Source Mismatch
The card header and chart data use different calculations for S&P 500 returns:
- **Card:** `calculate_sp500_return()` which may use live API data
- **Chart:** Built from `get_cached_sp500_data()` MarketData table

**Could the card header be pulling stale/missing data from MarketData while the chart has correct data?**

If MarketData has no records for YTD period, `calculate_sp500_return()` would return 0%, but chart generation might skip S&P line entirely or use fallback data.

### Question #2: Date.today() vs datetime.now(MARKET_TZ).date()
`get_last_market_day()` uses `date.today()` which reads system timezone (UTC on Vercel):
- Market close runs at 4 PM ET = 8 PM UTC
- If accessed after 8 PM ET (midnight UTC), `date.today()` returns next day
- Creates +1 day offset

**Should ALL date operations use `datetime.now(ZoneInfo('America/New_York')).date()` instead?**

### Question #3: Cached vs Live Data Consistency
The endpoint `/api/portfolio/performance/<period>` can return:
1. Cached chart data (from market close generation)
2. Live calculation (via `PortfolioPerformanceCalculator`)

**Are these two paths guaranteed to produce identical results?**

If cached data uses different date boundaries or S&P data sources, results will differ.

### Question #4: Missing S&P 500 Data?
User reports S&P gains = +0% but chart shows +14.34%.

**Could MarketData table be missing S&P 500 records?**

Check if:
- MarketData has SPY_SP500 records for Jan 1, 2025 (YTD start)
- Market close cron is collecting S&P 500 data daily
- Data collection is working but not being queried correctly

---

## 📋 VERIFICATION CHECKLIST

After fixes are applied, verify:

- [ ] YTD chart: Card header S&P = chart last data point S&P
- [ ] 1M chart: Card header S&P = chart last data point S&P  
- [ ] 3M chart: Card header S&P = chart last data point S&P
- [ ] Today's snapshot (Oct 2) labeled as 10/2/2025 (not 10/3/2025)
- [ ] Portfolio percentage matches between card and chart (within 0.01%)
- [ ] MarketData table has S&P 500 records for all dates
- [ ] `get_last_market_day()` returns correct ET date, not UTC date

---

## 📁 FILES TO REVIEW

1. **`portfolio_performance.py`**
   - Lines 515-553: `calculate_sp500_return()` - Card header calculation
   - Lines 771-901: `get_performance_data()` - Main calculation entry point
   - Lines 838-869: Chart data generation logic

2. **`leaderboard_utils.py`**
   - Lines 420-431: `get_last_market_day()` - **Uses `date.today()` instead of ET!**
   - Lines 433-570: `calculate_leaderboard_data()` - Performance calculations
   - Lines 572-709: `generate_user_portfolio_chart()` - Chart cache generation

3. **`api/index.py`**
   - Lines 7318-7420: `/api/portfolio/performance/<period>` endpoint
   - Lines 7345-7391: Cached data return path
   - Lines 9714-9775: Market close snapshot creation

---

**Next Steps:**
1. Send this analysis to Grok for validation
2. Get Grok's recommendations on root cause
3. Implement fixes for both issues
4. Test with tomorrow's market close data
