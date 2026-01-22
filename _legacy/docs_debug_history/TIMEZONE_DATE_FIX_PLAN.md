# Complete Timezone Fix Plan: date.today() → ET Date

**Date:** October 2, 2025 10:25 PM ET  
**Issue:** Multiple uses of `date.today()` causing UTC/ET mismatches

---

## 🔍 DIAGNOSIS COMPLETE

Found **7 instances** of `date.today()` in `portfolio_performance.py`:
- Line 128: `calculate_portfolio_value()` default parameter
- Line 182: `create_daily_snapshot()` default parameter
- Line 274: `collect_sp500_historical_data()` end date
- Line 405: `get_sp500_data()` recent date check
- Line 610: `get_intraday_performance_data()` today's snapshots
- Line 777: `get_performance_data()` main entry point

Also found **1 instance** in `leaderboard_utils.py`:
- Line 421: `get_last_market_day()` - **CRITICAL for chart dates!**

---

## 🎯 THE CORE PROBLEM

**Vercel runs in UTC timezone**
- System `date.today()` returns UTC date
- At 8:00 PM ET (midnight UTC), UTC date rolls over to next day
- But market is still on "today" in ET timezone
- This creates **+1 day offset** after 8 PM ET

**Example Timeline:**
```
October 2, 2025:
- 4:00 PM ET (20:00 UTC): Market close
  - Cron creates snapshot with date = Oct 2 (using ET correctly)
  
- 10:00 PM ET (02:00 UTC Oct 3): User views dashboard
  - Portfolio code calls date.today()
  - Returns Oct 3 (UTC date)
  - Mismatch: Snapshot says Oct 2, code thinks Oct 3
  - Result: Today's data labeled as "yesterday" or Oct 3
```

---

## ✅ SOLUTION: Create get_market_date() Helper

### Add to api/index.py (after get_market_time()):

```python
def get_market_date():
    """Get current date in Eastern Time (not UTC)"""
    return datetime.now(MARKET_TZ).date()
```

### Replace ALL date.today() with get_market_date():

1. **portfolio_performance.py**
2. **leaderboard_utils.py**  
3. Any other files using `date.today()`

---

## 📋 DETAILED FIXES

### Fix #1: portfolio_performance.py (7 replacements)

**Location 1 - Line 128:**
```python
# BEFORE:
def calculate_portfolio_value(self, user_id: int, target_date: date = None) -> float:
    if target_date is None:
        target_date = date.today()

# AFTER:
def calculate_portfolio_value(self, user_id: int, target_date: date = None) -> float:
    if target_date is None:
        from api.index import get_market_date
        target_date = get_market_date()
```

**Location 2 - Line 182:**
```python
# BEFORE:
def create_daily_snapshot(self, user_id: int, target_date: date = None):
    if target_date is None:
        target_date = date.today()

# AFTER:
def create_daily_snapshot(self, user_id: int, target_date: date = None):
    if target_date is None:
        from api.index import get_market_date
        target_date = get_market_date()
```

**Location 3 - Line 274:**
```python
# BEFORE:
end_date = date.today()

# AFTER:
from api.index import get_market_date
end_date = get_market_date()
```

**Location 4 - Line 405:**
```python
# BEFORE:
today = date.today()
recent_missing = [d for d in missing_dates if (today - d).days <= 7]

# AFTER:
from api.index import get_market_date
today = get_market_date()
recent_missing = [d for d in missing_dates if (today - d).days <= 7]
```

**Location 5 - Line 610:**
```python
# BEFORE:
today = date.today()

# AFTER:
from api.index import get_market_date
today = get_market_date()
```

**Location 6 - Line 777:**
```python
# BEFORE:
today = date.today()

# AFTER:
from api.index import get_market_date
today = get_market_date()
```

### Fix #2: leaderboard_utils.py (1 critical replacement)

**Location - Lines 420-431:**
```python
# BEFORE:
def get_last_market_day():
    """Get last market day (Friday if weekend)"""
    from datetime import date, timedelta
    today = date.today()
    
    if today.weekday() == 5:  # Saturday
        return today - timedelta(days=1)
    elif today.weekday() == 6:  # Sunday
        return today - timedelta(days=2)
    else:
        return today

# AFTER:
def get_last_market_day():
    """Get last market day in ET (Friday if weekend)"""
    from datetime import timedelta
    from zoneinfo import ZoneInfo
    from datetime import datetime
    
    MARKET_TZ = ZoneInfo('America/New_York')
    today = datetime.now(MARKET_TZ).date()  # Use ET, not UTC!
    
    if today.weekday() == 5:  # Saturday
        return today - timedelta(days=1)
    elif today.weekday() == 6:  # Sunday
        return today - timedelta(days=2)
    else:
        return today
```

---

## 🚨 WAIT - Better Approach!

Instead of adding import statements everywhere, let's create a proper helper module.

### Create: utils/market_time.py

```python
"""
Market time utilities for handling Eastern Time operations
"""
from datetime import datetime, date
from zoneinfo import ZoneInfo

MARKET_TZ = ZoneInfo('America/New_York')

def get_market_time():
    """Get current time in Eastern Time (handles DST automatically)"""
    return datetime.now(MARKET_TZ)

def get_market_date():
    """Get current date in Eastern Time (not UTC)"""
    return datetime.now(MARKET_TZ).date()

def get_last_market_day():
    """Get last market day in ET (Friday if weekend)"""
    from datetime import timedelta
    
    today = get_market_date()
    
    if today.weekday() == 5:  # Saturday
        return today - timedelta(days=1)
    elif today.weekday() == 6:  # Sunday
        return today - timedelta(days=2)
    else:
        return today
```

### Then update all files to import from utils:

```python
from utils.market_time import get_market_date, get_last_market_day
```

**BUT WAIT** - `api/index.py` already has these functions! So just use those.

---

## 🎯 ACTUAL IMPLEMENTATION PLAN

Since `api/index.py` already has:
- `MARKET_TZ = ZoneInfo('America/New_York')` (line 64)
- `get_market_time()` (line 66)
- `get_market_date()` (line 70)

**We should:**
1. Update `get_last_market_day()` in `leaderboard_utils.py` to use ET
2. Replace ALL `date.today()` in `portfolio_performance.py` with ET-aware version
3. Import from `api.index` OR add to `portfolio_performance.py` directly

**Simplest approach:** Add helper functions to `portfolio_performance.py` at the top:

```python
# Add at top of portfolio_performance.py after imports
from zoneinfo import ZoneInfo

MARKET_TZ = ZoneInfo('America/New_York')

def get_market_date():
    """Get current date in Eastern Time"""
    return datetime.now(MARKET_TZ).date()
```

Then replace all `date.today()` with `get_market_date()` in that file.

---

## 📁 FILES TO MODIFY

1. **portfolio_performance.py** - Add helper, replace 7 instances
2. **leaderboard_utils.py** - Update `get_last_market_day()` to use ET

---

##  S&P 500 Data Source Issue

This is SEPARATE from the date issue. Two problems:

### Problem: Card header shows +0% but chart shows +14.34%

**Root Cause:** `calculate_sp500_return()` uses `get_sp500_data()` which may:
- Return empty dict if API fails
- Use different date boundaries
- Pull from different data source than charts

**Chart generation** uses `get_cached_sp500_data()` which:
- Only reads from MarketData table
- Different data set than live API

### Solution Options:

**Option A: Use cached data consistently**
```python
# In calculate_sp500_return() line 519-522
# BEFORE:
if current_time.weekday() >= 5:  # Weekend
    sp500_data = self.get_cached_sp500_data(start_date, end_date)
else:
    sp500_data = self.get_sp500_data(start_date, end_date)

# AFTER:
# Always use cached data for consistency with charts
sp500_data = self.get_cached_sp500_data(start_date, end_date)
```

**Option B: Extract from chart data**
```python
# In get_performance_data() after chart_data is built (line 892)
# Instead of separate calculate_sp500_return() call:

# Calculate S&P 500 return from chart data for consistency
if chart_data and len(chart_data) > 0:
    # Find first and last non-None S&P values
    sp500_values = [point['sp500'] for point in chart_data if point.get('sp500') is not None]
    if sp500_values:
        # Chart stores percentage changes, so last value IS the total return
        sp500_return = sp500_values[-1] / 100  # Convert percentage back to decimal
    else:
        sp500_return = 0.0
else:
    # Fallback to calculation if no chart data
    sp500_return = self.calculate_sp500_return(start_date, end_date)
```

**Recommendation:** Option B is safer - ensures card matches chart exactly!

---

## 🚀 DEPLOYMENT ORDER

1. **Fix date.today() issues** (Fixes +1 day offset)
2. **Fix S&P data source mismatch** (Fixes +0% card header)
3. **Test tomorrow after market close**
4. **Verify dates and percentages match**

---

## ✅ VALIDATION CHECKLIST

After fixes:
- [ ] Oct 2 snapshot labeled as 10/2/2025 (not 10/3/2025)
- [ ] YTD card header S&P = chart last point S&P
- [ ] 1M card header S&P = chart last point S&P
- [ ] Portfolio % matches between card and chart
- [ ] Works correctly after 8 PM ET (midnight UTC)

---

**Ready to implement!**
