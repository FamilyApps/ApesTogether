# 🚨 DEEP ANALYSIS: 1D Chart Network Error & Date Labeling Issues

## **CRITICAL FINDINGS**

### **Issue #1: Wrong Date Labels (Oct 2 instead of Oct 1)**

**ROOT CAUSE:** Timezone hell - UTC vs Eastern Time mismatch throughout the codebase

**The Flow:**
1. Vercel runs in **UTC timezone**
2. Market close cron at `schedule: "0 20 * * 1-5"` = **20:00 UTC = 4:00 PM EDT**
3. But `datetime.now()` in Python returns **UTC time**
4. When cron runs at 20:00 UTC Oct 1 (4:00 PM EDT Oct 1), it uses `current_time.date()` which returns **Oct 1**
5. BUT at end of day when cron runs at 01:59 UTC Oct 2 (9:59 PM EDT Oct 1), `datetime.now().date()` returns **Oct 2**!

**Evidence from logs:**
```
2025-10-02T01:59:37.626Z - Market close cron triggered
```
This is **9:59 PM EDT on Oct 1**, but Python sees it as **Oct 2 in UTC**!

**Code Locations:**
- `api/index.py` line 14170: `current_time = datetime.now()` ← NO TIMEZONE!
- `api/index.py` line 14248: `timestamp=current_time` ← Saves UTC timestamp
- `leaderboard_utils.py` line 415: `today = date.today()` ← UTC date!
- `leaderboard_utils.py` line 575: `today = date.today()` ← UTC date for chart generation!

**Result:** Snapshots are labeled with the wrong date (Oct 2 instead of Oct 1)

---

### **Issue #2: 1D Chart Shows "Network Error"**

**ROOT CAUSE:** Chart cache generation queries for snapshots on the wrong date

**The Data Flow:**

```
1. INTRADAY CRON (9:30 AM - 3:30 PM ET)
   ↓
   Creates PortfolioSnapshotIntraday records
   timestamp = datetime.now()  ← UTC time!
   ↓
2. MARKET CLOSE CRON (4:00 PM ET = 20:00 UTC)
   ↓
   Calls update_all_chart_caches()
   ↓
3. CHART CACHE GENERATION
   today = date.today()  ← Gets UTC date (potentially next day!)
   ↓
   Queries: func.date(PortfolioSnapshotIntraday.timestamp) == today
   ↓
4. DATE MISMATCH!
   Intraday snapshots created with Oct 1 dates
   But chart generation queries for Oct 2 dates
   ↓
   No snapshots found → Returns None
   ↓
   Cache entry created with NULL chart_data
   ↓
5. DASHBOARD LOADS
   API endpoint tries to use cache
   Cache has NULL data
   ↓
   Falls back to live calculation
   Live calculation ALSO queries for today's intraday snapshots
   Same date mismatch!
   ↓
   API returns error or empty data
   ↓
   Frontend: "Network Error"
```

**Code Evidence:**

**Intraday Cron (`api/index.py` lines 14170, 14248):**
```python
current_time = datetime.now()  # UTC time on Vercel!
intraday_snapshot = PortfolioSnapshotIntraday(
    user_id=user.id,
    timestamp=current_time,  # Saved with UTC timestamp
    total_value=portfolio_value
)
```

**Chart Generation (`leaderboard_utils.py` lines 575, 583-587):**
```python
today = date.today()  # UTC date!

intraday_snapshots = PortfolioSnapshotIntraday.query.filter(
    and_(
        PortfolioSnapshotIntraday.user_id == user_id,
        func.date(PortfolioSnapshotIntraday.timestamp) == today  # Queries for UTC date!
    )
).order_by(PortfolioSnapshotIntraday.timestamp.asc()).all()
```

**When it breaks:**
- Intraday snapshots at 9:30 AM ET: timestamp = 13:30 UTC Oct 1 ✅
- Chart generation at 4:00 PM ET: today = Oct 1 ✅
- **BUT** if chart generation happens after 8:00 PM ET (00:00 UTC), `today` becomes Oct 2
- Queries for Oct 2 intraday snapshots, but they were all created with Oct 1 timestamps
- **Result:** No snapshots found!

---

### **Issue #3: Intraday Frequency - Every Hour vs Every 30 Minutes**

**Current State:**
```json
{
  "schedule": "30 13,14,15,16,17,18,19 * * 1-5"
}
```
This runs at **:30 past each hour** from 9:30 AM - 3:30 PM ET = **7 data points per day**

**Expected:**
User wants **every 30 minutes** = 9:30, 10:00, 10:30, 11:00, 11:30, 12:00, 12:30, 1:00, 1:30, 2:00, 2:30, 3:00, 3:30, 4:00 PM = **14 data points per day**

**Required Change:**
```json
{
  "schedule": "0,30 13-20 * * 1-5"
}
```
This runs at **:00 and :30** from 13:00-20:00 UTC (9:00 AM - 4:00 PM ET)

---

## **COMPREHENSIVE FIX REQUIRED**

### **1. Timezone Standardization**

**Problem:** Mixing UTC and ET throughout codebase

**Solution:** Use `pytz` to convert all times to Eastern Time

```python
from datetime import datetime
import pytz

eastern = pytz.timezone('America/New_York')
current_time_et = datetime.now(eastern)
today_et = current_time_et.date()
```

### **2. Code Changes Required**

**File: `api/index.py`**
```python
# Line 14170 - BEFORE:
current_time = datetime.now()

# AFTER:
import pytz
eastern = pytz.timezone('America/New_York')
current_time = datetime.now(eastern)
```

**File: `leaderboard_utils.py`**
```python
# Line 415 & 575 - BEFORE:
today = date.today()

# AFTER:
import pytz
eastern = pytz.timezone('America/New_York')
today = datetime.now(eastern).date()
```

**File: `vercel.json`**
```json
// BEFORE:
"schedule": "30 13,14,15,16,17,18,19 * * 1-5"

// AFTER (every 30 minutes):
"schedule": "0,30 13-20 * * 1-5"
```

### **3. Why Chart Cache is Empty**

**The Logs Show:**
```
✓ Generated chart cache for user 5, period YTD
✓ Generated chart cache for user 5, period 1Y
⚠ No chart data generated for user 5, period 1D - insufficient snapshots
```

**Translation:**
- Market close cron ran at 01:59 UTC Oct 2 (9:59 PM EDT Oct 1)
- `today = date.today()` returned **Oct 2**
- Queried for intraday snapshots on **Oct 2**
- But all intraday snapshots were created earlier in the day with **Oct 1** timestamps
- **No snapshots found** → Chart cache marked as "insufficient snapshots"
- Cache entry created but with NULL or empty chart_data

### **4. Why Dashboard Shows "Network Error"**

**Dashboard Load Flow:**
1. Browser requests `/api/portfolio/performance/1D`
2. API checks chart cache → Finds cache entry but chart_data is NULL
3. Falls back to live calculation
4. Live calculation queries intraday snapshots for "today" (Oct 2 in UTC)
5. No snapshots found for Oct 2
6. Returns error or empty data
7. Frontend displays "Network Error"

---

## **DATA VERIFICATION NEEDED**

Check actual database timestamps for Oct 1 intraday snapshots:

```sql
SELECT 
    id, 
    user_id, 
    timestamp, 
    DATE(timestamp) as snapshot_date,
    total_value
FROM portfolio_snapshot_intraday
WHERE DATE(timestamp) >= '2025-10-01'
ORDER BY timestamp;
```

Expected: All timestamps should be Oct 1, but queried as if they're Oct 2

---

## **IMMEDIATE NEXT STEPS**

1. **Verify timezone issue** - Check actual database timestamps
2. **Fix timezone handling** - Add pytz and convert all datetime operations to ET
3. **Update cron schedule** - Change to every 30 minutes
4. **Regenerate chart caches** - Run market close cron again after fixes
5. **Test 1D chart** - Verify it displays correctly

---

## **WHY THIS WASN'T CAUGHT EARLIER**

- System worked fine during regular market hours (before 8 PM ET)
- Issue only manifests when:
  - Market close cron runs late (after 8 PM ET = midnight UTC)
  - OR next day when UTC date has rolled over
  - Chart cache generated with wrong "today" date
  - Queries fail to find snapshots created earlier

**Classic timezone bug:** Works in some scenarios, breaks in others based on time of day
