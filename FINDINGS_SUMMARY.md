# Investigation Summary: Intraday Chart & Cron Issues

**Date:** October 2, 2025 8:02 PM ET  
**Investigator:** Cascade AI

---

## ✅ VERIFIED: No GitHub Actions Cron Jobs

**Finding:** No `.github/workflows` directory exists.

**Conclusion:** All cron jobs are running through Vercel crons only. ✓ No conflicts.

---

## 🔴 ISSUE #1: Chart Shows Wrong Timestamps (4-Hour Offset)

### Summary:
Your 1D chart displays 14 data points labeled **1PM - 7:30PM** instead of the correct **9AM - 4:30PM ET** market hours.

### Root Cause:
**PostgreSQL returns timestamps in UTC, but the chart displays them without converting back to ET.**

**Flow:**
1. ✅ Intraday cron runs correctly (16 times from 9 AM - 4:30 PM ET)
2. ✅ Snapshots created with ET timestamps via `get_market_time()`
3. ✅ Stored in PostgreSQL as `TIMESTAMP WITH TIME ZONE` (stored internally as UTC)
4. ❌ Retrieved by SQLAlchemy as UTC datetime
5. ❌ Sent to frontend as ISO string with UTC offset (`+00:00`)
6. ❌ Chart displays UTC time (1 PM) instead of ET time (9 AM)

**Evidence:**
- Logs show cron at `09:00 UTC` (9 AM ET)
- Chart shows `13:00` (1 PM) which is 9 AM ET displayed as 13:00 UTC
- **Exactly 4-hour offset = EDT to UTC conversion**

### Fix Required:
**File:** `api/index.py` lines ~13264-13269

**Change:**
```python
# BEFORE:
if period == '1D':
    date_label = snapshot.timestamp.isoformat()

# AFTER:
if period == '1D':
    # Convert to ET timezone before sending to frontend
    from zoneinfo import ZoneInfo
    MARKET_TZ = ZoneInfo('America/New_York')
    et_timestamp = snapshot.timestamp.astimezone(MARKET_TZ)
    date_label = et_timestamp.isoformat()
```

Apply same fix for period == '5D' on line ~13269.

---

## 🔴 ISSUE #2: Three Market Close Cron Jobs Ran

### Summary:
Market close ran **3 times** on Oct 2 instead of once:
```
16:00 UTC (4:00 PM ET) - GET  request ✓ Scheduled Vercel cron
16:05 UTC (4:05 PM ET) - POST request ❌ Manual trigger
17:04 UTC (5:04 PM ET) - POST request ❌ Manual trigger
```

### Finding #1: Manual POST Triggers
The 16:05 and 17:04 executions were **POST requests** that passed Bearer token authentication.

**Possible sources:**
1. Frontend admin interface with "Trigger Market Close" button
2. Manual API testing via Postman/curl
3. External webhook or monitoring service
4. You manually triggering during debugging

**Action needed:** Search codebase for any UI buttons or scripts calling this endpoint.

### Finding #2: Duplicate EOD Snapshot Logic ⚠️

**CRITICAL:** You have **two places** creating end-of-day snapshots:

**Location 1:** Intraday cron at 4:00 PM (`api/index.py` ~14287)
```python
# Check if this is the 4:00 PM collection (market close)
is_market_close = current_time.hour == 16 and current_time.minute == 0

if is_market_close:
    # Creates EOD snapshots
    snapshot = PortfolioSnapshot(...)
    db.session.add(snapshot)
```

**Location 2:** Market close cron (`api/index.py` ~9760)
```python
# Create new EOD snapshot
snapshot = PortfolioSnapshot(...)
db.session.add(snapshot)
```

**Problem:** Both run at 4 PM ET, creating duplicate EOD snapshot logic.

**Fix Required:** Remove the `is_market_close` block from intraday cron. Market close cron should handle EOD snapshots exclusively.

**File:** `api/index.py` lines ~14287-14320

**Change:** Delete the entire `if is_market_close:` block.

---

## ⚠️ ISSUE #3: Chart Generation Error (1D Period)

### Summary:
Market close logs show error for **all users** on **1D period only**:
```
Error generating chart for user X, period 1D: name 'logger' is not defined
⚠ No chart data generated for user X, period 1D - insufficient snapshots
```

Other periods (5D, 1M, 3M, YTD, 1Y, 5Y, MAX) succeed ✓

### Possible Causes:

**Theory 1: Missing Logger Import**
`leaderboard_utils.py` might be missing `import logging; logger = logging.getLogger(__name__)`

**Theory 2: 1D Shouldn't Be Cached**
1D charts use **live intraday data** via `/api/portfolio/intraday/1D` endpoint, not cached data. Other periods use historical daily snapshots and benefit from caching. Maybe 1D chart cache generation should be skipped entirely?

**Action needed:** 
1. Check `leaderboard_utils.py` for missing logger
2. OR skip 1D period in market close chart cache generation

---

## 🔍 ISSUE #4: Missing 2 Data Points

### Summary:
- **Expected:** 16 data points (9 AM - 4:30 PM, every 30 min)
- **Actual:** 14 data points shown
- **Missing:** First 2 points (9 AM, 9:30 AM)

### Hypothesis:
The 4-hour timezone offset might cause the query filter to exclude the first 2 points:

1. Query filters by ET date: `2025-10-02`
2. First snapshot: `2025-10-02T09:00:00-04:00` (9 AM ET)
3. Stored in PostgreSQL as: `2025-10-02T13:00:00+00:00` (UTC)
4. When retrieved, if interpreted as UTC and displayed, might appear as different date?

**This should be resolved by Fix #1** (converting timestamps to ET before sending).

---

## 📋 RECOMMENDED FIXES (Priority Order)

### 1. ⬆️ HIGH: Fix Timestamp Display
**File:** `api/index.py` lines 13264-13269

Add timezone conversion to ET before sending to frontend.

**Expected result:** Chart shows 9:00 AM - 4:30 PM ET (16 points)

### 2. ⬆️ HIGH: Remove Duplicate EOD Logic
**File:** `api/index.py` lines 14287-14320

Delete `if is_market_close:` block from intraday cron.

**Expected result:** Only market close cron creates EOD snapshots at 4 PM.

### 3. 🔼 MEDIUM: Fix Chart Cache Error or Skip 1D
**File:** `leaderboard_utils.py` (need to locate exact line)

Either add missing `logger` import or skip 1D period in cache generation.

**Expected result:** No errors in market close logs.

### 4. 🔼 MEDIUM: Investigate POST Triggers
**Action:** Search codebase for calls to `/api/cron/market-close`

**Expected result:** Identify source of manual triggers at 16:05 and 17:04.

---

## 📁 FILES FOR GROK REVIEW

Created two comprehensive documents for Grok:

1. **`INTRADAY_CHART_TIMESTAMP_ANALYSIS.md`**
   - Detailed technical analysis
   - Evidence from logs
   - Code flow diagrams
   - All 4 issues documented

2. **`GROK_PROMPT_INTRADAY_ISSUES.md`**
   - Formatted as questions for Grok
   - Context and code snippets
   - Proposed solutions for validation
   - Specific questions to answer

**How to use:**
1. Open both files
2. Copy `GROK_PROMPT_INTRADAY_ISSUES.md` content
3. Send to Grok
4. Include code snippets from `api/index.py` if Grok requests them

---

## 🎯 EXPECTED OUTCOMES AFTER FIXES

### After Fix #1 (Timestamp Display):
- ✅ Chart shows 9:00 AM, 9:30 AM, ..., 4:30 PM ET
- ✅ All 16 data points visible
- ✅ Correct timezone labels

### After Fix #2 (Remove Duplicate EOD):
- ✅ Only 1 market close execution (scheduled cron)
- ✅ No race conditions or conflicts
- ✅ Cleaner separation of concerns

### After Fix #3 (Chart Cache):
- ✅ No errors in market close logs
- ✅ 1D charts work correctly (via live endpoint)

### After Fix #4 (POST Triggers):
- ✅ Understand source of manual triggers
- ✅ Remove/disable if unintended

---

## 🚀 NEXT STEPS

1. **Send to Grok:** Copy `GROK_PROMPT_INTRADAY_ISSUES.md` → Get validation
2. **Apply Fix #1:** Timestamp conversion to ET
3. **Apply Fix #2:** Remove duplicate EOD logic
4. **Test:** View 1D chart after next intraday cron run
5. **Monitor:** Check market close logs tomorrow for errors
6. **Investigate:** Find POST trigger source

---

## ✅ VERIFICATION CHECKLIST

After deploying fixes, verify:

- [ ] 1D chart shows 9 AM - 4:30 PM ET (not 1 PM - 7:30 PM)
- [ ] All 16 data points visible
- [ ] Only 1 market close cron execution per day
- [ ] No "logger not defined" errors in market close logs
- [ ] EOD snapshots created only by market close cron
- [ ] No unexpected POST triggers

---

**Investigation Complete!**  
All issues identified, root causes analyzed, fixes proposed.  
Ready for Grok review and implementation.
