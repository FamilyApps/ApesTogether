# 📋 ACTION PLAN: Fixing Dashboard & Leaderboard Issues

## CURRENT STATUS (as of 2025-09-30 20:34 ET)

### ✅ **Fixed:**
1. Duplicate cron jobs consolidated
2. `Stock.created_at` → `Stock.purchase_date` correction
3. Cache consistency analysis deployed
4. Emergency cache rebuild deployed (with fix pending)

### ❌ **Still Broken:**
1. 1D leaderboard: Only 1 user visible
2. 5D leaderboard: 4/5 users show 0% gains
3. All leaderboards: Mostly 0% performance
4. Charts: Missing Friday 9/27, showing Sunday 9/29
5. Charts: No data for today (Monday 9/30)
6. 1D/5D x-axis: Large numbers instead of times/dates

## ROOT CAUSE IDENTIFIED

**From Latest Logs:**
```
ERROR - Error processing user 4: 'Stock' object has no attribute 'created_at'
```

**The Issue:** Emergency rebuild used `stock.created_at` but Stock model has `purchase_date`

**Impact:** ALL chart cache generation failed → 0 data points generated

**Status:** ✅ FIXED in code, needs deployment

## IMMEDIATE NEXT STEPS

### STEP 1: Deploy the `created_at` Fix 🚀
**Action:** Commit and push the fix to production

**Expected Result:**
- Chart caches will populate with real data
- Leaderboards will show real performance percentages
- 5D, 1M, 3M, YTD, 1Y charts should work

**Timeline:** ~2 minutes (Vercel deploy + cache rebuild)

---

### STEP 2: Run Emergency Cache Rebuild Again 🔄
**Action:** Visit `https://apestogether.ai/admin/emergency-cache-rebuild`

**Expected Output:**
```
Chart Caches Fixed: 25-30
Data Points Generated: 500+
```

**What This Will Fix:**
- ✅ Leaderboards showing real % gains
- ✅ 5D, 1M, 3M, YTD, 1Y charts with data
- ❌ 1D charts still broken (needs intraday data)

**Timeline:** ~5 minutes

---

### STEP 3: Diagnose 1D Chart Issue 🔍
**Observed:** All users show "insufficient snapshots" for 1D period

**Possible Causes:**
1. **Intraday table missing/empty**
   - Test: Check if `intraday_portfolio_snapshot` table exists
   - Solution: Create table or update 1D logic to use daily snapshots

2. **Today's data not collected**
   - Test: Check PortfolioSnapshot for date = 2025-09-30
   - Solution: Manually trigger cron or wait for next collection

3. **1D logic requires multiple snapshots**
   - Test: Check how many snapshots exist for today
   - Solution: Adjust 1D cache generation to handle single daily snapshot

**Action:** Run `comprehensive_database_diagnostic.py` locally to see actual data

---

### STEP 4: Fix Weekend Data Issue 📅
**Problem:** Sunday 9/29 data exists, Friday 9/27 missing

**Hypothesis:** Either:
- Timezone bug (EDT/EST confusion causing date shift)
- Manual data entry created Sunday snapshots
- Date calculation error in snapshot generation

**Action:** Query database directly:
```sql
SELECT date, COUNT(*) as snapshot_count
FROM portfolio_snapshot
WHERE date >= '2025-09-27' AND date <= '2025-09-30'
GROUP BY date
ORDER BY date;
```

**Expected:** Should see 9/27 and 9/30, NOT 9/29

---

### STEP 5: Fix X-Axis Label Issue 📊
**Problem:** 1D/5D charts show large numbers instead of times/dates

**Likely Cause:** Frontend receiving Unix timestamps as numbers instead of formatted dates

**Diagnosis:**
1. Check API response format for `/api/portfolio/performance/1D`
2. Verify chart_data contains `date` field in ISO format
3. Check dashboard.js Chart.js configuration

**Solution:** Ensure chart data includes properly formatted date strings:
```json
{
  "chart_data": [
    {"date": "2025-09-30T09:30:00", "portfolio": 10000, "sp500": 5000}
  ]
}
```

---

## PARALLEL ACTIONS

### Action A: Get Grok's Analysis 🤖
**Files to Share with Grok:**
1. `GROK_ANALYSIS_REQUEST.md` (the prompt)
2. `models.py` (database schema)
3. `api/index.py` (emergency rebuild logic, lines 15904-16186)
4. `portfolio_performance.py` (if exists)
5. `leaderboard_utils.py` (if exists)
6. `vercel.json` (cron configuration)

**Expected:** Fresh perspective on structural issues we're missing

---

### Action B: Database Schema Validation 🗄️
**Check for Schema Drift:**

```sql
-- Check if intraday table exists
SELECT table_name 
FROM information_schema.tables 
WHERE table_name LIKE '%intraday%';

-- Check portfolio_snapshot columns
SELECT column_name, data_type 
FROM information_schema.columns 
WHERE table_name = 'portfolio_snapshot';

-- Check for Sunday snapshots (shouldn't exist)
SELECT * FROM portfolio_snapshot WHERE date = '2025-09-29';

-- Check for missing Friday snapshots (should exist)
SELECT * FROM portfolio_snapshot WHERE date = '2025-09-27';
```

---

## SUCCESS CRITERIA

### ✅ **Phase 1: Basic Functionality** (After Step 1-2)
- [ ] All leaderboards show 5 users
- [ ] 5D leaderboard shows real % gains (not all 0%)
- [ ] 5D, 1M, 3M, YTD, 1Y charts display data
- [ ] Chart caches have > 0 data points

### ✅ **Phase 2: 1D Charts** (After Step 3)
- [ ] 1D leaderboard shows 5 users
- [ ] 1D chart displays intraday data
- [ ] X-axis shows times (9:30 AM, 10:00 AM, etc.)

### ✅ **Phase 3: Data Accuracy** (After Step 4-5)
- [ ] Friday 9/27 data present in all charts
- [ ] Sunday 9/29 data removed/absent
- [ ] Monday 9/30 data present and updating
- [ ] X-axis labels formatted correctly

## ESTIMATED TIMELINE

- **Phase 1:** 10 minutes (deploy + rebuild)
- **Phase 2:** 30-60 minutes (diagnose + fix 1D)
- **Phase 3:** 30-60 minutes (diagnose + fix weekend/labels)

**Total:** 1-2 hours to full resolution

## RISK MITIGATION

### If Emergency Rebuild Fails Again:
**Plan B:** Use regular cache regeneration endpoint
- `/admin/regenerate-caches` (if exists)
- Or trigger leaderboard update which generates chart caches as side effect

### If 1D Charts Can't Be Fixed:
**Plan C:** Hide 1D period temporarily
- Remove "1D" from period selector in frontend
- Focus on getting 5D+ working perfectly
- Add 1D back after intraday system fixed

### If Weekend Data Can't Be Cleaned:
**Plan D:** Frontend filtering
- Dashboard filters out weekend dates before rendering
- Show only weekday data in charts
- Add note: "Markets closed on weekends"

## MONITORING

### After Each Fix:
1. **Check `/admin/cache-consistency-analysis`** - Should show data_points > 0
2. **Check dashboard directly** - Verify charts render
3. **Check leaderboards** - Verify real percentages
4. **Check browser console** - Verify no API errors

### Validation Queries:
```sql
-- Verify chart caches populated
SELECT period, COUNT(*) 
FROM user_portfolio_chart_cache 
GROUP BY period;

-- Verify non-zero data points
SELECT user_id, period, LENGTH(chart_data) as data_size
FROM user_portfolio_chart_cache
LIMIT 10;

-- Verify leaderboard data
SELECT period, generated_at, LENGTH(leaderboard_data) as data_size
FROM leaderboard_cache
ORDER BY generated_at DESC;
```

---

## NOTES FOR FUTURE

### Prevent Similar Issues:
1. **Add model validation tests** - Catch `created_at` vs `purchase_date` issues
2. **Add cache generation monitoring** - Alert if 0 data points generated
3. **Add weekend data validation** - Prevent snapshot creation on Sat/Sun
4. **Add schema migration checks** - Verify migrations applied to production
5. **Add integration tests** - Test full data flow from cron → cache → API → frontend

### Documentation Needs:
1. **Data flow diagram** - Visual representation of cron → cache → API
2. **Schema documentation** - Document all models and relationships
3. **Cache strategy docs** - When/how caches are generated and invalidated
4. **Troubleshooting guide** - Common issues and solutions

---

**Last Updated:** 2025-09-30 20:34 ET
**Status:** Ready to execute Step 1
