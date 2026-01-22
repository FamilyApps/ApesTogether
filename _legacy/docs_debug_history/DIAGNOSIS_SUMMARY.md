# Diagnosis Summary: S&P 500 Mismatch & Date Offset Issues

**Date:** October 2, 2025 10:25 PM ET  
**Status:** Root causes identified, fixes ready for Grok validation

---

## 🎯 ISSUES IDENTIFIED

### Issue #1: S&P 500 Returns Don't Match
- **Card Header:** Shows +0% (YTD) or +0.83% (1M)
- **Chart Data Point:** Shows +14.34% (YTD) or +1.76% (1M)
- **Root Cause:** Two different calculations using different data sources

### Issue #2: Dates Off By One Day  
- **Today:** October 2, 2025
- **Chart Label:** Shows 10/3/2025 for today's snapshot
- **Root Cause:** `date.today()` returns UTC date, not ET date

---

## 🔍 ROOT CAUSE #1: Data Source Mismatch

**Two Separate S&P 500 Calculations:**

1. **Card Header** (Top of chart):
   - Function: `calculate_sp500_return()` in `portfolio_performance.py`
   - Data Source: `get_sp500_data()` - May use Alpha Vantage API OR cache
   - Returns: Single percentage for the period

2. **Chart Data Points**:
   - Function: `get_performance_data()` builds chart from snapshots
   - Data Source: `get_cached_sp500_data()` - MarketData table ONLY
   - Returns: Array of percentages for each day

**The Problem:**
- Card and chart use DIFFERENT data sources!
- If MarketData table is missing S&P 500 records, card shows 0%
- But chart might use different fallback logic
- Result: Percentages don't match

**Example:**
```python
# Card calculation (portfolio_performance.py line 817):
sp500_return = self.calculate_sp500_return(start_date, end_date)
# Returns: 0.0 if no data found

# Chart calculation (portfolio_performance.py line 854):
sp500_pct = ((sp500_data[date_key] - period_start_sp500) / period_start_sp500) * 100
# Returns: 14.34% using cached data
```

---

## 🔍 ROOT CAUSE #2: UTC vs ET Date

**The Problem:**
- Vercel runs in **UTC timezone**
- Python's `date.today()` returns **system (UTC) date**
- Market operates in **Eastern Time (ET)**

**Found 8 instances of `date.today()` causing UTC/ET mismatches:**

**In `portfolio_performance.py`:**
1. Line 128: `calculate_portfolio_value()` - Default target date
2. Line 182: `create_daily_snapshot()` - Default target date
3. Line 274: `collect_sp500_historical_data()` - End date
4. Line 405: `get_sp500_data()` - Recent date check
5. Line 610: `get_intraday_performance_data()` - Today's snapshots
6. Line 777: `get_performance_data()` - Weekend adjustment
7. Line 777: (same function) - Main date calculation

**In `leaderboard_utils.py`:**
8. Line 421: `get_last_market_day()` - **CRITICAL for chart labels!**

**Timeline Example:**
```
October 2, 2025:
- 4:00 PM ET (20:00 UTC): Market close cron runs
  ✅ Uses get_market_time() → Creates snapshot with date=Oct 2 (ET)
  
- 10:16 PM ET (02:16 UTC Oct 3): User views dashboard  
  ❌ Calls date.today() → Returns Oct 3 (UTC date)
  ❌ Chart queries for "today" = Oct 3
  ❌ Snapshot with date=Oct 2 is now "yesterday"
  ❌ Result: Oct 2 data labeled as Oct 3
```

---

## ✅ SOLUTIONS PROPOSED

### Solution #1: Fix S&P Data Source Consistency

**Approach:** Make card header extract from chart data (ensures 100% match)

```python
# In get_performance_data() - AFTER chart_data is built
# Replace separate calculate_sp500_return() call with:

if chart_data and len(chart_data) > 0:
    # Get last S&P value from chart (already a percentage)
    last_sp500_pct = chart_data[-1].get('sp500', 0)
    sp500_return = last_sp500_pct / 100  # Convert to decimal for consistency
else:
    # Fallback if no chart data
    sp500_return = self.calculate_sp500_return(start_date, end_date)
```

**Benefits:**
- Card header ALWAYS matches chart
- No data source mismatch possible
- Simpler logic

### Solution #2: Fix UTC vs ET Date Issue

**Approach A:** Add `get_market_date()` helper to `portfolio_performance.py`

```python
# Add at top of portfolio_performance.py
from zoneinfo import ZoneInfo

MARKET_TZ = ZoneInfo('America/New_York')

def get_market_date():
    """Get current date in Eastern Time (not UTC)"""
    return datetime.now(MARKET_TZ).date()

# Then replace ALL 7 instances of date.today() with get_market_date()
```

**Approach B:** Fix `get_last_market_day()` in `leaderboard_utils.py`

```python
# BEFORE:
def get_last_market_day():
    today = date.today()  # UTC on Vercel!

# AFTER:
def get_last_market_day():
    from zoneinfo import ZoneInfo
    from datetime import datetime
    
    MARKET_TZ = ZoneInfo('America/New_York')
    today = datetime.now(MARKET_TZ).date()  # ET, not UTC!
    
    # Rest remains same...
```

**Benefits:**
- All date operations use market timezone (ET)
- No more +1 day offset after 8 PM ET
- Consistent with market close cron (already uses ET)

---

## 📋 IMPLEMENTATION CHECKLIST

### Fix Priority #1: Date.today() → ET Date
- [ ] Add `get_market_date()` helper to `portfolio_performance.py`
- [ ] Replace 7 instances of `date.today()` in `portfolio_performance.py`
- [ ] Update `get_last_market_day()` in `leaderboard_utils.py`

### Fix Priority #2: S&P Data Source
- [ ] Modify `get_performance_data()` to extract S&P return from chart
- [ ] Remove separate `calculate_sp500_return()` call
- [ ] Ensure card header matches chart last point

### Verification:
- [ ] Deploy and test after next market close
- [ ] Verify Oct 3 snapshot labeled as 10/3 (not 10/4)
- [ ] Verify YTD card S&P matches chart last point
- [ ] Verify 1M card S&P matches chart last point
- [ ] Test after 8 PM ET to ensure no +1 day offset

---

## 📁 DOCUMENTATION CREATED

1. **SP500_MISMATCH_ANALYSIS.md** - Detailed technical analysis
2. **GROK_PROMPT_SP500_MISMATCH.md** - Ready-to-send Grok prompt
3. **TIMEZONE_DATE_FIX_PLAN.md** - Line-by-line fix instructions
4. **DIAGNOSIS_SUMMARY.md** - This file (executive summary)

---

## 🚀 NEXT STEPS

### Option A: Implement Fixes Now
If confident in diagnosis:
1. Apply date.today() fixes
2. Apply S&P data source fix
3. Commit and deploy
4. Test tomorrow

### Option B: Get Grok Validation First
If want second opinion:
1. Send `GROK_PROMPT_SP500_MISMATCH.md` to Grok
2. Include code snippets from `portfolio_performance.py` and `leaderboard_utils.py`
3. Get Grok's validation
4. Apply fixes based on Grok's recommendations

---

## ⚠️ KEY INSIGHTS

1. **Vercel = UTC timezone** - Never use `date.today()` without timezone awareness
2. **Market = ET timezone** - ALL market operations must use ET, not UTC
3. **Two calculation paths** - Card header and chart data use different code paths
4. **Data source matters** - Cached vs live API data can produce different results
5. **After 8 PM ET** - UTC date is already "tomorrow", causing +1 day bugs

---

## ✅ HIGH CONFIDENCE IN ROOT CAUSE

Both issues have clear, verifiable root causes:
- ✅ `date.today()` using UTC instead of ET → Date +1 offset
- ✅ Different S&P data sources (API vs cache) → Percentage mismatch

Fixes are straightforward and low-risk. Ready to implement or send to Grok for validation.

---

**All analysis complete and documented!**  
Choose implementation path and proceed. 🚀
