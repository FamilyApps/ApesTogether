# 🚨 CRITICAL: Market Close Snapshots Not Being Created - RECURRING ISSUE

## THE PROBLEM (Happening Every Single Day)

**Expected Behavior:**
- Every weekday at 4:00 PM EDT (market close), snapshots should be created
- These snapshots should have today's date (Sept 30, 2025)
- Snapshots should contain NON-ZERO portfolio values
- Chart caches should be updated with new data
- Leaderboards should reflect today's performance

**What's Actually Happening:**
- Charts show last data point from YESTERDAY (Sept 29, 2025)
- No Sept 30 snapshots visible in charts
- User manually ran `/admin/rebuild-all-caches` at 6:31 PM EDT (2+ hours after market close)
- Rebuild logs show: "User 5 YTD: 74 points" (no new point added)
- Market closed at 4:00 PM EDT today, it's now 6:49 PM EDT
- **The daily market close job DID NOT RUN or DID NOT CREATE SNAPSHOTS**

---

## CONFIGURATION

### vercel.json Cron Configuration:
```json
{
  "crons": [
    {
      "path": "/api/cron/market-open",
      "schedule": "30 13 * * 1-5"
    },
    {
      "path": "/api/cron/collect-intraday-data",
      "schedule": "30 13,14,15,16,17,18,19 * * 1-5"
    },
    {
      "path": "/api/cron/market-close", 
      "schedule": "0 20 * * 1-5"
    }
  ]
}
```

**Schedule "0 20 * * 1-5" means:**
- Minute: 0
- Hour: 20 (8:00 PM UTC)
- Days: Monday-Friday
- **8:00 PM UTC = 4:00 PM EDT** (during daylight saving time)

---

## ENDPOINT IMPLEMENTATION

### /api/cron/market-close Endpoint:
**Location:** `api/index.py` lines 9606-9737

**What it SHOULD do:**
```
PHASE 1: Create Portfolio Snapshots
  - For each user
  - Calculate portfolio value using PortfolioPerformanceCalculator
  - Create or update PortfolioSnapshot with today's date
  - Store in database (NOT committed yet)

PHASE 2: Update Leaderboard Cache
  - Call update_leaderboard_cache()
  - This also triggers chart cache updates
  - Creates UserPortfolioChartCache entries

PHASE 3: Atomic Commit
  - Commit all changes to database
  - If any phase fails, rollback everything
```

**Authentication:**
- GET requests: Allowed (Vercel cron uses GET)
- POST requests: Require `Authorization: Bearer {CRON_SECRET}`
- Logs: "Market close cron triggered via GET from Vercel"

---

## DATA FLOW (What SHOULD Happen)

```
16:00 EDT Daily:
┌─────────────────────────────────────────────────────────────┐
│ 1. Vercel Cron Trigger                                      │
│    - Vercel scheduler fires at 20:00 UTC (16:00 EDT)       │
│    - GET /api/cron/market-close                             │
└──────────────────┬──────────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────────┐
│ 2. PHASE 1: Create Portfolio Snapshots                      │
│    - Calculate portfolio_value for each user                │
│    - Uses PortfolioPerformanceCalculator(user_id)          │
│    - calculate_portfolio_value(today)                       │
│    - Creates PortfolioSnapshot(date=2025-09-30, value=X)   │
│    - db.session.add() but NOT committed yet                 │
└──────────────────┬──────────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────────┐
│ 3. PHASE 2: Update Leaderboard & Chart Caches              │
│    - Calls update_leaderboard_cache()                       │
│    - For each period (1D, 5D, 1M, 3M, YTD, 1Y):           │
│      - Queries PortfolioSnapshot table                      │
│      - Generates chart data points                          │
│      - Creates/updates UserPortfolioChartCache             │
│    - db.session.add() but NOT committed yet                 │
└──────────────────┬──────────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────────┐
│ 4. PHASE 3: Atomic Commit                                   │
│    - db.session.commit()                                    │
│    - ALL changes written to database together               │
│    - Returns 200 OK with results JSON                       │
└──────────────────┬──────────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────────┐
│ 5. User Views Dashboard                                     │
│    - Charts query UserPortfolioChartCache                   │
│    - Should see new data point for Sept 30                  │
│    - Charts update automatically                            │
└─────────────────────────────────────────────────────────────┘
```

---

## WHAT'S ACTUALLY HAPPENING (Evidence)

### 1. User Ran Manual Cache Rebuild at 6:31 PM EDT:
**Vercel logs from `/admin/rebuild-user-cache/5` (witty-raven):**
```
2025-09-30 22:31:05,565 - index - INFO - User 5 1D: 1 points, 0.00% return
2025-09-30 22:31:05,580 - index - INFO - User 5 5D: 6 points, 1.16% return
2025-09-30 22:31:05,594 - index - INFO - User 5 1M: 22 points, 8.09% return
2025-09-30 22:31:05,612 - index - INFO - User 5 3M: 65 points, 8.09% return
2025-09-30 22:31:05,628 - index - INFO - User 5 YTD: 74 points, 8.09% return
2025-09-30 22:31:05,643 - index - INFO - User 5 1Y: 74 points, 8.09% return
```

**Key Observations:**
- **YTD: 74 points** - No new point added today
- If a Sept 30 snapshot existed, there would be 75 points (one more)
- Cache rebuild uses existing snapshots - doesn't create new ones
- This confirms: **No Sept 30 snapshot exists in database**

### 2. Charts Show Yesterday's Data:
- User reports: "last data point is STILL yesterday"
- Market closed 2+ hours ago
- Expected: New data point for Sept 30
- Actual: Last data point is Sept 29

### 3. User Cleaned Corrupted Snapshots Yesterday:
- Sept 23-24: Deleted 8 zero-value snapshots
- This was AFTER our fix to `calculate_portfolio_value()` fallback logic
- The fix was deployed and should prevent zero-value snapshots
- But the market close job still isn't running

---

## CRITICAL QUESTIONS FOR DEBUGGING

### 1. **Is Vercel Cron Actually Running?**
**Check in Vercel Dashboard:**
- Go to: Project → Cron → Logs
- Look for executions around 20:00 UTC (16:00 EDT) today
- Expected: Entry showing `/api/cron/market-close` execution

**Possible Issues:**
- Vercel cron not enabled for this project
- Cron schedule misconfigured (timezone issues)
- Cron job exceeding 60-second timeout
- Cron endpoint returning error (job marked as failed)

### 2. **Is the Endpoint Being Called?**
**Check in Vercel Deployment Logs:**
- Go to: Project → Deployments → Latest Deployment → Logs
- Filter for: "market-close" or "market close cron"
- Expected: Log entry "Market close cron triggered via GET from Vercel"

**If NO logs found:**
- Cron is not triggering the endpoint
- Check Vercel cron configuration
- Verify project has cron enabled (paid feature)

**If logs found BUT errors:**
- Look for error messages
- Check if phases completed
- Look for database errors

### 3. **Is CRON_SECRET Configured?**
**Check in Vercel Environment Variables:**
- Go to: Project → Settings → Environment Variables
- Look for: `CRON_SECRET`
- Should be: Set for Production environment

**If missing:**
- Endpoint returns 500: "CRON_SECRET not configured"
- Cron job fails silently
- No snapshots created

### 4. **Is PortfolioPerformanceCalculator Working?**
**The calculate_portfolio_value() fix we made:**
```python
# OLD (BROKEN):
if current_price is None:
    return 0  # Returns $0 for entire portfolio!

# NEW (FIXED):
if current_price is None:
    logger.warning(f"API failed for {stock.ticker}, using purchase_price fallback")
    current_price = stock.purchase_price  # Fallback to purchase price
```

**This fix should prevent zero-value snapshots, BUT:**
- Is the market close job even calling this function?
- Or is the cron job not running at all?

### 5. **Timezone Issues?**
**Current configuration:**
- `schedule: "0 20 * * 1-5"` = 20:00 UTC
- Today is Sept 30, 2025 - **Is EDT or EST active?**
- EDT: UTC-4 → 20:00 UTC = 16:00 EDT ✅ (market close time)
- EST: UTC-5 → 20:00 UTC = 15:00 EST ❌ (before market close)

**Check:**
- What timezone was active today?
- Did DST end recently, causing schedule shift?
- Is Vercel using UTC correctly?

### 6. **Vercel Pro Plan Active?**
**Important Context:**
- User is on **Vercel Pro plan** (paid subscription)
- Specifically upgraded to support multiple cron jobs
- Cron Jobs feature requires Pro plan
- Should have 3 active cron jobs configured

---

## CRITICAL DATA AVAILABLE

### ✅ USER HAS VERCEL CRON LOGS (ATTACHED)

**Logs provided (last 24 hours only - Vercel plan limitation):**
1. **Market Close Cron Log** - All executions of `/api/cron/market-close` from past day
2. **Intraday Cron Log** - All executions of `/api/cron/collect-intraday-data` from past day
3. **Market Open Cron Log** - All executions of `/api/cron/market-open` from past day

**These logs will reveal:**
- ✅ If cron jobs are actually triggering
- ✅ Success/failure status of each execution
- ✅ Execution timestamps (confirm timezone is correct)
- ✅ Duration of each execution (check for timeouts)
- ✅ Error messages if jobs are failing

**Key Context:**
- Market closed today (Sept 30, 2025) at 4:00 PM EDT (20:00 UTC)
- Expected: Market close cron should have run at 20:00 UTC
- Actual: Charts show last data point from Sept 29 (yesterday)
- User manually ran cache rebuild at 22:31 UTC - no new data points added

**THIS IS THE SMOKING GUN we need to diagnose the issue!**

---

## WHAT TO CHECK & SCREENSHOT

### In Vercel Dashboard:

1. **Cron Jobs Page:**
   - Screenshot: Project → Cron → Shows all cron jobs
   - Look for: `/api/cron/market-close` with "0 20 * * 1-5" schedule
   - Check: "Enabled" status

2. **Cron Execution Logs:**
   - Screenshot: Recent executions of market-close job
   - Look for: Today's (Sept 30) execution around 20:00 UTC
   - Check: Status (Success/Failed/Not Run)
   - Check: Duration (should be < 60s)

3. **Deployment Logs:**
   - Screenshot: Latest deployment → Function logs
   - Filter: "market-close" or time range 20:00-20:05 UTC
   - Look for: "Market close cron triggered"
   - Look for: Error messages

4. **Environment Variables:**
   - Screenshot: Settings → Environment Variables
   - Verify: `CRON_SECRET` exists (redact the value!)
   - Verify: `DATABASE_URL` or `POSTGRES_PRISMA_URL` exists
   - Verify: `ALPHA_VANTAGE_API_KEY` exists

5. **Project Settings:**
   - Screenshot: Project settings overview
   - Confirm: **Vercel Pro plan** is active (user has paid subscription)
   - Check: Build & Development Settings
   - Check: Function timeout settings (should be 60s max)

---

## DEBUGGING STEPS TO TRY

### Step 1: Check If Snapshots Exist in Database
**Run this SQL query:**
```sql
SELECT user_id, date, total_value, created_at
FROM portfolio_snapshot
WHERE date = '2025-09-30'
ORDER BY user_id;
```

**Expected if job ran:** 5 rows (one per user)
**Expected if job didn't run:** 0 rows

### Step 2: Manually Trigger Market Close
**Visit this URL:**
```
https://apestogether.ai/api/cron/market-close
```

**Expected result:**
- Success: JSON response with results
- Creates snapshots for today
- Updates caches

**If this works:**
- Problem: Vercel cron not triggering endpoint
- Solution: Fix Vercel cron configuration

**If this fails:**
- Problem: Endpoint itself is broken
- Check: Error message in response
- Check: Vercel logs for stack trace

### Step 3: Check Vercel Cron Status
**In Vercel Dashboard:**
```
Project → Cron → market-close job → View Details
```

**Look for:**
- Last execution time
- Execution history (successes/failures)
- Error logs

### Step 4: Enable More Logging
**Add to market_close_cron endpoint (temporarily):**
```python
logger.info(f"=== MARKET CLOSE CRON STARTED ===")
logger.info(f"Method: {request.method}")
logger.info(f"Headers: {dict(request.headers)}")
logger.info(f"Current time: {datetime.now()}")
logger.info(f"Today's date: {date.today()}")
```

**Then wait for tomorrow's execution and check logs.**

---

## PREVIOUS FIXES THAT DIDN'T SOLVE THIS

1. **✅ Fixed `calculate_portfolio_value()` fallback logic**
   - Prevents $0.00 snapshots when API fails
   - But doesn't help if cron job isn't running at all

2. **✅ Added per-user cache rebuild (Grok's Option B)**
   - Avoids timeout issues
   - But rebuilds only work if snapshots exist
   - Doesn't create new snapshots

3. **✅ Cleaned corrupted zero-value snapshots**
   - Removed bad data from Sept 23-24
   - But doesn't fix the root issue of snapshots not being created daily

---

## THE CORE ISSUE

**The fundamental problem is:**
```
Market close cron job → NOT RUNNING or FAILING SILENTLY
  ↓
No snapshots created for today
  ↓
Cache rebuilds have no new data to work with
  ↓
Charts show yesterday's data as the last point
  ↓
Happens EVERY SINGLE DAY
```

**We've fixed downstream issues (zero-values, cache generation, timeouts) but the UPSTREAM issue remains:**
- **Either Vercel cron isn't triggering the endpoint**
- **Or the endpoint is running but silently failing**
- **Or snapshots are created but immediately deleted/overwritten**

---

## QUESTIONS FOR GROK

1. **Why would Vercel cron jobs silently fail or not run?**
   - Configuration issues?
   - Billing/plan limitations?
   - Timezone bugs?

2. **How to debug Vercel cron execution?**
   - Where to find execution logs?
   - How to test cron jobs manually?
   - How to verify cron is enabled?

3. **Could there be a race condition?**
   - Multiple systems trying to create snapshots?
   - GitHub Actions vs Vercel cron?
   - Conflicting writes causing rollbacks?

4. **Database transaction issues?**
   - Could the atomic commit be failing silently?
   - Would Vercel logs show transaction rollbacks?
   - Connection pool exhaustion?

5. **Alternative approaches?**
   - Should we abandon Vercel cron and use GitHub Actions?
   - Should we use a dedicated cron service (EasyCron, cron-job.org)?
   - Should we add a monitoring service to alert when jobs don't run?

---

## SUCCESS CRITERIA

**When this is fixed, we should see:**
1. ✅ Vercel cron logs show daily execution at 20:00 UTC
2. ✅ Database has new snapshots created every weekday
3. ✅ Charts show today's data (Sept 30) as the latest point
4. ✅ Manual cache rebuilds show increased point counts (75 instead of 74)
5. ✅ No manual intervention needed - works automatically every day

---

## CURRENT STATUS

- **Market closed:** 4:00 PM EDT today (Sept 30)
- **Current time:** 6:49 PM EDT (2 hours 49 minutes after market close)
- **Expected:** Sept 30 snapshots should exist
- **Actual:** Sept 29 is the last data point
- **User frustration level:** HIGH (this happens EVERY day)

**This is not a one-time issue. This is a systematic failure of the daily data collection pipeline.**
