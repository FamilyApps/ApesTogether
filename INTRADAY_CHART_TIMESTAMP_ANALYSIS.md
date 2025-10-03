# Intraday Chart Timestamp Issue Analysis

**Date:** October 2, 2025 8:01 PM ET  
**Issues to Investigate:**
1. Chart showing 14 snapshots labeled 1PM-7:30PM instead of 9:30AM-4:30PM (market hours)
2. Three market close cron jobs ran instead of one
3. Potential timezone display bug in chart labels

---

## 📊 ISSUE #1: Chart Timestamp Labels Wrong

### Expected Behavior:
- Market hours: 9:30 AM - 4:00 PM ET (Monday-Friday)
- Intraday snapshots every 30 minutes during market hours
- Chart should show labels: 9:00 AM, 9:30 AM, 10:00 AM, ..., 4:00 PM, 4:30 PM ET
- Should have 16 data points total

### Actual Behavior:
- Chart shows 14 data points
- Labels: 1:00 PM, 1:30 PM, 2:00 PM, ..., 7:00 PM, 7:30 PM
- **Off by exactly 4 hours** (EDT offset from UTC)
- Missing first 2 data points (9:00 AM, 9:30 AM)

### Evidence from Logs:

**Intraday Cron Execution (Oct 2):**
```
Oct 02 09:00:04 (13:00 UTC = 9:00 AM ET) ✓
Oct 02 09:30:04 (13:30 UTC = 9:30 AM ET) ✓
Oct 02 10:00:04 (14:00 UTC = 10:00 AM ET) ✓
Oct 02 10:30:04 (14:30 UTC = 10:30 AM ET) ✓
Oct 02 11:00:04 (15:00 UTC = 11:00 AM ET) ✓
Oct 02 11:30:04 (15:30 UTC = 11:30 AM ET) ✓
Oct 02 12:00:04 (16:00 UTC = 12:00 PM ET) ✓
Oct 02 12:30:04 (16:30 UTC = 12:30 PM ET) ✓
Oct 02 13:00:04 (17:00 UTC = 1:00 PM ET) ✓
Oct 02 13:30:04 (17:30 UTC = 1:30 PM ET) ✓
Oct 02 14:00:04 (18:00 UTC = 2:00 PM ET) ✓
Oct 02 14:30:04 (18:30 UTC = 2:30 PM ET) ✓
Oct 02 15:00:04 (19:00 UTC = 3:00 PM ET) ✓
Oct 02 15:30:04 (19:30 UTC = 3:30 PM ET) ✓
Oct 02 16:00:04 (20:00 UTC = 4:00 PM ET) ✓
Oct 02 16:30:04 (20:30 UTC = 4:30 PM ET) ✓
```
**Total: 16 runs ✓ Correct!**

**Chart Display:**
- Showing: 1:00 PM, 1:30 PM, ..., 7:30 PM (14 points)
- Expected: 9:00 AM, 9:30 AM, ..., 4:30 PM (16 points)
- **Discrepancy: 4-hour offset + missing 2 points**

### Vercel.json Cron Configuration:
```json
{
  "crons": [
    {
      "path": "/api/cron/market-open",
      "schedule": "30 13 * * 1-5"  // 9:30 AM ET (13:30 UTC)
    },
    {
      "path": "/api/cron/collect-intraday-data",
      "schedule": "0,30 13-20 * * 1-5"  // Every 30 min, 9AM-4:30PM ET
    },
    {
      "path": "/api/cron/market-close",
      "schedule": "0 20 * * 1-5"  // 4:00 PM ET (20:00 UTC)
    }
  ]
}
```
**Cron schedule is CORRECT** ✓

### Root Cause Hypothesis:

**Theory 1: Timestamp Storage Issue**
- Snapshots created with `get_market_time()` (ET timezone-aware)
- Stored in PostgreSQL as `TIMESTAMP WITH TIME ZONE`
- PostgreSQL stores internally as UTC
- When retrieved, timestamps are in UTC but displayed without timezone conversion

**Theory 2: Frontend Timezone Conversion**
- Backend sends ISO timestamps like `2025-10-02T13:00:00-04:00`
- Chart.js or frontend code strips timezone and interprets as local time
- Or converts to UTC and displays UTC time instead of ET

**Theory 3: Query Filter Issue**
- The query using `cast(func.timezone('America/New_York', timestamp), Date)` works for filtering
- But the returned timestamps might still be in UTC format
- Chart displays them as-is without converting back to ET

### Code Analysis:

**Intraday Snapshot Creation (api/index.py ~14301):**
```python
current_time = get_market_time()  # Returns datetime with ET timezone
intraday_snapshot = PortfolioSnapshotIntraday(
    user_id=user.id,
    timestamp=current_time,  # TZ-aware ET timestamp
    total_value=portfolio_value
)
```

**Chart Data Generation (api/index.py ~13266):**
```python
if period == '1D':
    # For 1D charts, use full ISO timestamp
    date_label = snapshot.timestamp.isoformat()
```

**Problem:** `snapshot.timestamp.isoformat()` returns the timestamp, but if PostgreSQL returns it as UTC, the ISO string will have `+00:00` offset instead of `-04:00`.

**Potential Fix Location:** Need to convert timestamp back to ET before sending to frontend:
```python
if period == '1D':
    # Convert to ET before sending
    et_time = snapshot.timestamp.astimezone(MARKET_TZ)
    date_label = et_time.isoformat()
```

---

## ⚠️ ISSUE #2: Three Market Close Cron Jobs Ran

### Expected Behavior:
- Market close cron runs once per day at 4:00 PM ET
- Scheduled via Vercel cron: `"schedule": "0 20 * * 1-5"`
- Only one execution per trading day

### Actual Behavior (Oct 2):
```
16:00 UTC (4:00 PM ET) - GET request  ✓ Scheduled cron
16:05 UTC (4:05 PM ET) - POST request ❌ Manual trigger?
17:04 UTC (5:04 PM ET) - POST request ❌ Manual trigger?
```

**Three executions - 2 are unscheduled!**

### Market Close Endpoint Code (api/index.py ~9694):
```python
# Allow GET requests for Vercel cron (bypass auth for cron jobs)
if request.method == 'GET':
    logger.info("Market close cron triggered via GET from Vercel")
else:
    # POST requests require proper authentication
    if not auth_header.startswith('Bearer ') or auth_header[7:] != expected_token:
        logger.warning(f"Unauthorized market close attempt")
        return jsonify({'error': 'Unauthorized'}), 401
```

### Analysis:
- **16:00 execution:** GET request from Vercel cron ✓ Expected
- **16:05 execution:** POST request - authenticated manual trigger
- **17:04 execution:** POST request - authenticated manual trigger

**Questions:**
1. Who/what is triggering the POST requests?
2. Are there any frontend buttons that call this endpoint?
3. Is there a GitHub webhook or external service calling it?
4. Could this be the intraday cron at 4:00 PM calling market close?

### Intraday Endpoint Market Close Logic (api/index.py ~14287):
```python
# Check if this is the 4:00 PM collection (market close)
is_market_close = current_time.hour == 16 and current_time.minute == 0

# If this is market close time, also create EOD snapshot
if is_market_close:
    from models import PortfolioSnapshot
    # ... creates EOD snapshots
```

**FOUND IT!** The intraday cron at 4:00 PM (16:00) creates EOD snapshots itself. Then the market close cron also runs at 16:00. This means:
- 16:00: Intraday cron creates EOD snapshots + market close cron runs
- But there are still 2 POST triggers at 16:05 and 17:04

**Hypothesis:** 
- Someone manually triggered the market close endpoint via POST twice
- OR there's a retry mechanism in Vercel that's re-running failed crons
- OR there's frontend code that calls the market close endpoint

---

## 🔍 ISSUE #3: No Competing GitHub Actions (✓ VERIFIED)

Checked for `.github/workflows/*.yml` - **None found** ✓

No competing cron jobs from GitHub Actions.

---

## 📋 QUESTIONS FOR GROK

### Question 1: Timestamp Display Issue
**Context:**
- PostgreSQL `TIMESTAMP WITH TIME ZONE` column stores snapshots
- Created with `get_market_time()` returning `datetime.now(ZoneInfo('America/New_York'))`
- Sent to frontend as `snapshot.timestamp.isoformat()`
- Chart shows times 4 hours ahead (1PM-7:30PM instead of 9AM-4:30PM)

**Question:** When SQLAlchemy retrieves a `TIMESTAMP WITH TIME ZONE` from PostgreSQL, does it:
a) Return a timezone-aware datetime in the original timezone (ET)?
b) Return a timezone-aware datetime converted to UTC?
c) Return a naive datetime?

And when calling `.isoformat()` on that datetime, what timezone offset does it include?

**Expected fix:** Should we convert back to ET before sending to frontend?
```python
et_time = snapshot.timestamp.astimezone(ZoneInfo('America/New_York'))
date_label = et_time.isoformat()
```

### Question 2: Duplicate Market Close Executions
**Context:**
- Market close cron scheduled for `0 20 * * 1-5` (4 PM ET)
- Intraday cron runs at same time (16:00) and has logic to create EOD snapshots
- Three executions observed: GET at 16:00, POST at 16:05, POST at 17:04

**Questions:**
a) Is it redundant to have both intraday cron creating EOD snapshots at 4 PM AND a separate market close cron?
b) Could the POST triggers be from a frontend admin interface or webhook?
c) Should we remove the EOD snapshot creation from the intraday cron and rely solely on market close cron?

### Question 3: Chart Generation in Market Close
**Context:**
- Market close cron generates chart caches for all users/periods
- Logs show: `Error generating chart for user X, period 1D: name 'logger' is not defined`
- This happens in `leaderboard_utils.py` during chart cache generation
- 1D charts fail, but other periods (5D, 1M, etc.) succeed

**Question:** Should 1D chart cache generation be skipped during market close since 1D uses live intraday data via the `/api/portfolio/intraday/1D` endpoint? Or is there a missing `logger` import in `leaderboard_utils.py`?

### Question 4: Missing First 2 Data Points
**Context:**
- 16 intraday snapshots created (9 AM - 4:30 PM)
- Chart only shows 14 points (1 PM - 7:30 PM in wrong timezone)
- Missing points would be 9 AM and 9:30 AM

**Question:** Could the 4-hour offset cause the query to filter out the first 2 points? For example:
- If backend filters by ET date (Oct 2)
- But timestamps are returned as UTC
- First 2 snapshots (9 AM, 9:30 AM ET = 13:00, 13:30 UTC) might be on date Oct 2
- But when displayed as UTC-4, they appear as Oct 1 9 AM/9:30 AM and get filtered?

---

## 🎯 RECOMMENDED FIXES

### Fix #1: Timestamp Display (HIGH PRIORITY)
**File:** `api/index.py` line ~13264-13269

**Change:**
```python
# BEFORE:
if period == '1D':
    date_label = snapshot.timestamp.isoformat()

# AFTER:
if period == '1D':
    # Convert to ET timezone before sending to frontend
    et_timestamp = snapshot.timestamp.astimezone(MARKET_TZ)
    date_label = et_timestamp.isoformat()
```

### Fix #2: Remove Duplicate EOD Snapshot Logic (MEDIUM PRIORITY)
**File:** `api/index.py` line ~14287-14320

**Change:** Remove EOD snapshot creation from intraday cron since market close cron handles it:
```python
# REMOVE THIS ENTIRE BLOCK:
# If this is market close time, also create EOD snapshot
if is_market_close:
    from models import PortfolioSnapshot
    # ... EOD snapshot creation code
```

**Reason:** Market close cron already creates EOD snapshots. Duplication causes conflicts.

### Fix #3: Fix Missing Logger in Chart Generation (LOW PRIORITY)
**File:** `leaderboard_utils.py` (need to check)

**Change:** Add logger import or remove logger call causing the error.

### Fix #4: Investigate POST Triggers (MEDIUM PRIORITY)
- Search codebase for any API calls to `/api/cron/market-close` via POST
- Check frontend admin interface
- Review Vercel deployment logs for webhook triggers

---

## 📁 FILES TO SHARE WITH GROK

1. **vercel.json** - Cron configuration
2. **api/index.py** lines 13120-13300 - Intraday chart endpoint
3. **api/index.py** lines 14200-14350 - Intraday data collection
4. **api/index.py** lines 9690-9770 - Market close cron endpoint
5. **This analysis document**

---

## 🔬 DEBUGGING STEPS TAKEN

1. ✓ Verified no GitHub Actions workflows
2. ✓ Analyzed Vercel cron configuration - CORRECT
3. ✓ Confirmed intraday cron ran 16 times - CORRECT
4. ✓ Identified 4-hour timezone offset in chart labels
5. ✓ Found duplicate EOD snapshot logic in intraday cron
6. ✓ Discovered 3 market close executions (1 scheduled, 2 manual)
7. ✓ Located missing logger error in chart generation

---

**Next Steps:**
1. Get Grok's validation on root cause analysis
2. Apply recommended fixes
3. Test chart display with corrected timestamps
4. Remove duplicate EOD logic
5. Find source of manual POST triggers
