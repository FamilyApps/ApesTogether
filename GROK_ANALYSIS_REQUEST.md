# 🤖 GROK AI ANALYSIS REQUEST

## CONTEXT
We have a Flask stock portfolio tracking app deployed on Vercel with persistent data issues affecting charts and leaderboards. Multiple fix attempts have failed to resolve the root causes.

## PERSISTENT ISSUES

### 1. **Leaderboards Show Incorrect Data**
- 1D leaderboard: Only 1 user (should be 5+)
- 5D leaderboard: 4 out of 5 users show +0% gains (should show real performance)
- All other periods (1M, 3M, YTD, 1Y): Most users show +0% gains

### 2. **Charts Missing Data Points**
- **Missing Friday 9/27 data** but **showing Sunday 9/29 data** (markets closed Sunday!)
- **No data for Monday 9/30** despite markets being open
- 1D and 5D charts display but **x-axis shows large numbers** instead of times/dates
- 1Y chart initially shows "Network Error" (API returns HTML instead of JSON)

### 3. **Cache System Completely Broken**
From `/admin/cache-consistency-analysis`:
```json
{
  "data_sources": {
    "portfolio_snapshots": {
      "total_count": 1571,
      "recent_count": 26,
      "zero_value_count": 190
    },
    "sp500_data": {
      "total_count": 1276,
      "problematic_values": 0
    }
  },
  "cache_layers": {
    "user_portfolio_charts": {
      "by_user": {
        "1": {
          "1D": {"data_points": 0, "has_real_portfolio_data": false},
          "5D": {"data_points": 0, "has_real_portfolio_data": false}
          // ALL periods show 0 data points
        }
      }
    }
  }
}
```

**The paradox:** Database has 1,571 snapshots but ALL chart caches have 0 data points!

### 4. **Emergency Cache Rebuild Failed**
Latest attempt output:
```
Chart Caches Fixed: 0
Data Points Generated: 0
```

Error logs revealed:
```
ERROR - Error processing user 4: 'Stock' object has no attribute 'created_at'
```

**BUT** regular leaderboard system worked:
```
✓ Generated chart cache for user 1, period 5D
⚠ No chart data generated for user 1, period 1D - insufficient snapshots
```

## KEY DISCOVERIES

### Discovery 1: Stock Model Schema
```python
class Stock(db.Model):
    purchase_date = db.Column(db.DateTime, default=datetime.utcnow)
    # NO created_at attribute!
```

### Discovery 2: Duplicate Cron Jobs
In `vercel.json`:
```json
{
  "path": "/api/cron/collect-intraday-data",
  "schedule": "0 14,15,16,17,18,19 * * 1-5"
},
{
  "path": "/api/cron/collect-intraday-data",
  "schedule": "30 13,14,15,16,17,18,19 * * 1-5"
}
```
**Fixed:** Consolidated to single DST-aware schedule.

### Discovery 3: Intraday Data Missing
All users show: `"⚠ No chart data generated for user X, period 1D - insufficient snapshots"`

This suggests:
- 1D charts require intraday snapshots (not just daily)
- Intraday snapshot collection may not be working
- Or intraday table doesn't exist/is empty

### Discovery 4: Database Schema Drift
Previous memory indicates `leaderboard_entry` table was missing `period` column in production despite migration defining it.

## ARCHITECTURE

### Deployment
- **Production**: Vercel serverless (uses `api/index.py`)
- **Entry point**: `api/vercel.py` imports from `api/index.py`
- **Database**: PostgreSQL (likely Supabase/Vercel Postgres)
- **Caching**: Two-layer system:
  1. `UserPortfolioChartCache` - Pre-computed chart data
  2. `LeaderboardCache` - Pre-computed leaderboard rankings

### Data Flow
```
1. Cron Jobs (every 30 min during market hours)
   → /api/cron/collect-intraday-data
   → Creates PortfolioSnapshot entries
   → Should create IntradayPortfolioSnapshot (?)

2. Cache Generation (on-demand + scheduled)
   → Queries PortfolioSnapshot + MarketData
   → Generates UserPortfolioChartCache
   → Generates LeaderboardCache

3. API Endpoints
   → /api/portfolio/performance/<period>
   → Returns cached data or generates on-the-fly
   → 1Y endpoint returning HTML instead of JSON!

4. Frontend Dashboard
   → Fetches from API endpoints
   → Renders Chart.js charts
   → Shows leaderboards
```

## QUESTIONS FOR GROK

### Primary Questions:
1. **Why are chart caches being generated with 0 data points** when 1,571 snapshots exist in the database?

2. **What's the correct data source for 1D charts?** Should they use:
   - IntradayPortfolioSnapshot table (if exists)
   - Regular PortfolioSnapshot with date = today
   - Some other mechanism?

3. **Why is Sunday 9/29 data appearing** when markets are closed Sundays?

4. **Why is Friday 9/27 data missing** from multi-day charts?

5. **What causes the x-axis label issue** (large numbers instead of dates)?

### Secondary Questions:
6. Is there a fundamental mismatch between:
   - How data is stored (DateTime vs Date)
   - How data is queried (date comparisons)
   - How data is cached (serialization)

7. Could timezone handling be causing the weekend data issues?

8. Why does `/api/portfolio/performance/1Y` return HTML instead of JSON?

9. What's the actual database schema vs what the code expects? (Schema drift)

10. Is the cache generation code even running, or failing silently?

## FILES TO ANALYZE

Please analyze these key files for structural issues, logic errors, or mismatches:

### Core Models
- `models.py` - Database models (Stock, PortfolioSnapshot, UserPortfolioChartCache, LeaderboardCache, MarketData)

### Cache Generation
- `api/index.py` - Contains emergency cache rebuild logic (lines 15904-16186)
- `portfolio_performance.py` - Performance calculation logic
- `leaderboard_utils.py` - Leaderboard cache generation

### Data Collection
- `api/index.py` - `/api/cron/collect-intraday-data` endpoint
- `snapshot_chart_generator.py` - Daily snapshot generation

### Configuration
- `vercel.json` - Cron job schedules
- `timezone_utils.py` - DST-aware timezone handling

## WHAT WE'VE TRIED

1. ✅ **Nuclear data fix** - Rebuilt snapshots from scratch (0 rebuilt)
2. ✅ **Cache consistency analysis** - Revealed 0 data points everywhere
3. ✅ **Emergency cache rebuild** - Failed due to `created_at` attribute error
4. ✅ **Fixed duplicate cron jobs** - Consolidated schedules
5. ❌ **Charts still broken** - Same issues persist
6. ❌ **Leaderboards still broken** - Still showing 0% for most users

## HYPOTHESIS

**Primary Theory:** There are two separate but related issues:

**Issue A: Intraday System Not Working**
- 1D charts require intraday snapshots
- Intraday data collection not creating data
- Could be:
  - Table doesn't exist
  - Cron job not running
  - Data being created but not queried correctly

**Issue B: Cache Generation Query Logic**
- Cache generation queries use wrong date filtering
- Or looking in wrong tables
- Or data type mismatches (DateTime vs Date)
- Results in finding 0 snapshots despite data existing

**Issue C: Weekend Data Corruption**
- Sunday data shouldn't exist but does
- Friday data should exist but doesn't
- Suggests timezone or date calculation bug

## EXPECTED BEHAVIOR

### Correct State:
- 1D leaderboard: 5 users with real % gains
- 5D leaderboard: 5 users with real % gains
- All charts: Show data for Friday 9/27, not Sunday 9/29
- All charts: Show data for today (Monday 9/30)
- 1D/5D x-axis: Show times (9:30 AM, 10:00 AM, etc.)
- Other x-axis: Show dates (Sep 27, Sep 28, etc.)
- All caches: Should have > 0 data points

## REQUEST

Please analyze the provided files and:

1. **Identify the root cause(s)** of why cache generation finds 0 data points
2. **Explain the weekend data issue** (Sunday present, Friday missing)
3. **Determine the correct data source for 1D charts**
4. **Identify any schema drift or mismatches**
5. **Provide specific code fixes** for each issue

Focus on finding **structural problems** or **fundamental misunderstandings** in how the system is architected, not just syntax errors.

## ADDITIONAL CONTEXT

- Markets open: Monday-Friday 9:30 AM - 4:00 PM Eastern (EDT = UTC-4)
- Current date: September 30, 2025
- Friday 9/27 was a market day
- Sunday 9/29 was NOT a market day
- Today (Monday 9/30) IS a market day

Thank you for your analysis! 🚀
