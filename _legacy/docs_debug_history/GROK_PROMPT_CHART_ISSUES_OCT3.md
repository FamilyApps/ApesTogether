# Grok Prompt: Chart Display Issues - Oct 3, 2025

---

## CONTEXT

Stock portfolio Flask app on Vercel. After fixing timezone issues (date.today() → ET) and S&P data source mismatch yesterday, we now have three new chart display issues discovered today (Oct 3, 5:28 PM ET).

**Previous Fixes Successfully Deployed:**
- ✅ All `date.today()` replaced with ET-aware `get_market_date()`
- ✅ S&P return extracted from chart data (card header matches chart)
- ✅ Intraday chart timezone conversion (timestamps converted to ET)

**Current Status:**
- Previous fixes working well
- New issues discovered in chart data display

---

## PROBLEM #1: 1D Chart Showing Yesterday's Data

### User Report:
"The 1D chart is showing a couple data points from yesterday. Of course only data points from today should show up on the 1D chart after the market opens."

### Screenshot Evidence (1D Chart - Oct 3, 5:28 PM ET):
- **Chart Title:** "Portfolio Performance" - "1D" tab selected
- **Card Header:** "Your Portfolio: -3.87%" "S&P 500: +0%"
- **Tooltip Shown:** "Oct 02, 4:30 PM" - Portfolio: +0.00%, S&P 500: +0.00%
- **X-Axis Timeline:** 5:00 PM → 8:00 PM → 11:00 PM → 2:00 AM → 5:00 AM → 8:00 AM → 11:00 AM → 2:00 PM
- **Portfolio Line:** Starts around 5:00 PM (yesterday), continues through overnight, drops to -3.87% by 2 PM today

**Key Issue:** Timeline starts at 5:00 PM which is AFTER market close (4 PM ET). This must be yesterday (Oct 2, 5 PM). Chart should ONLY show today (Oct 3) from 9:30 AM - 4:00 PM ET.

### Code Analysis:

**File:** `api/index.py` lines 13158-13179

```python
if period == '1D':
    start_date = market_day  # Calculated as today (ET)
    end_date = market_day

# Get intraday snapshots using ET timezone conversion
snapshots = PortfolioSnapshotIntraday.query.filter(
    PortfolioSnapshotIntraday.user_id == user_id,
    cast(func.timezone('America/New_York', PortfolioSnapshotIntraday.timestamp), Date) >= start_date,
    cast(func.timezone('America/New_York', PortfolioSnapshotIntraday.timestamp), Date) <= end_date
).order_by(PortfolioSnapshotIntraday.timestamp).all()
```

**File:** `api/index.py` lines 13143-13155 (Date calculation)

```python
# Calculate date range based on period - use last market day for weekends
# CRITICAL: Use Eastern Time, not UTC!
current_time_et = get_market_time()  # datetime.now(ZoneInfo('America/New_York'))
today = current_time_et.date()

# Use last market day for weekend handling (in ET)
if today.weekday() == 5:  # Saturday
    market_day = today - timedelta(days=1)  # Friday
elif today.weekday() == 6:  # Sunday
    market_day = today - timedelta(days=2)  # Friday
else:
    market_day = today  # Monday-Friday
```

### Hypothesis:

**Hypothesis #1: Query uses >= instead of == for 1D**
- For 1D, `start_date == end_date == market_day` (both Oct 3)
- Query uses `>= start_date AND <= end_date`
- This is essentially `>= Oct 3 AND <= Oct 3` which should be fine
- **BUT:** Maybe `func.timezone()` conversion is causing date boundary issues?

**Hypothesis #2: Timestamp timezone storage issue**
- `PortfolioSnapshotIntraday.timestamp` column type: `TIMESTAMP WITH TIME ZONE`
- Stored timestamps might be in UTC or mixed timezones
- `func.timezone('America/New_York', timestamp)` converts to ET
- If timestamp is ALREADY timezone-aware in ET, this could double-convert
- Result: Oct 3 9:30 AM ET → interpreted as Oct 3 9:30 AM UTC → converts to Oct 2 5:30 PM ET

**Hypothesis #3: market_day calculation timing**
- Code runs at 5:28 PM ET on Oct 3
- `current_time_et = get_market_time()` should return Oct 3 5:28 PM ET
- `today = current_time_et.date()` should return Oct 3
- Oct 3 is Thursday (weekday() = 3), so `market_day = today` = Oct 3
- **This should be correct...**

**Hypothesis #4: Database has stale data**
- Intraday cron failed to clear yesterday's data
- Database has BOTH Oct 2 AND Oct 3 snapshots
- Query fetches Oct 2 snapshots incorrectly

### Questions for Grok:

**Q1:** Is using `>= start_date AND <= end_date` wrong for 1D period?  
Should we use `== market_day` instead for exact date matching?

**Q2:** Could `func.timezone('America/New_York', timestamp)` cause issues if timestamp is already timezone-aware?  
Should we check timezone first or use a different PostgreSQL function?

**Q3:** How should we query for "only today's intraday data" reliably?  
Is there a better date extraction method that's timezone-safe?

**Q4:** Could the issue be that `cast(..., Date)` loses timezone information?  
Should we use `date_trunc('day', timestamp AT TIME ZONE 'America/New_York')` instead?

---

## PROBLEM #2: 1M Chart Scale Incorrect

### User Report:
"The Your Portfolio gains are all consistent and look good on the 3M, YTD, and 1Y charts, but they're wacky in the 1M chart. The shape of the Your Portfolio line looks good in the chart, but the scale appears to be off. It has the same peaks and dips as the 3M, etc. charts but the %s shown are much higher. It's almost as though the snapshots are all multiplied by 2 or something."

### Screenshot Evidence (5D Chart for reference):
- **5D Chart:** "Your Portfolio: +1.18%" "S&P 500: +1.53%"
- Chart shows reasonable scale from +0% to +6%
- Portfolio line peaks around +5%, valleys around +2%

**User's Description of 1M:**
- Shape matches 3M, YTD, 1Y charts (same peaks/dips)
- But Y-axis percentages are approximately DOUBLED
- If 3M shows +3%, 1M shows ~+6%

### Code Analysis:

**File:** `portfolio_performance.py` lines 829-875

```python
# Get portfolio values for charting (database only)
snapshots = PortfolioSnapshot.query.filter(
    and_(
        PortfolioSnapshot.user_id == user_id,
        PortfolioSnapshot.date >= start_date,  # start_date = today - 30 days for 1M
        PortfolioSnapshot.date <= end_date
    )
).order_by(PortfolioSnapshot.date).all()

# Get S&P 500 data for charting (always use cached daily data)
sp500_data = self.get_cached_sp500_data(start_date, end_date)

# Build chart data
if snapshots and sp500_data:
    sp500_dates = sorted(sp500_data.keys())
    if sp500_dates:
        period_start_sp500 = None
        for date_key in sp500_dates:
            if date_key >= start_date:
                period_start_sp500 = sp500_data[date_key]  # First S&P value in range
                break
        
        if period_start_sp500:
            sampled_dates = self._sample_dates_for_period(sp500_dates, period)
            
            for date_key in sampled_dates:
                if date_key >= start_date and date_key in sp500_data:
                    sp500_pct = ((sp500_data[date_key] - period_start_sp500) / period_start_sp500) * 100
                    
                    # Portfolio calculation
                    portfolio_snapshot = next((s for s in snapshots if s.date == date_key), None)
                    if portfolio_snapshot and snapshots[0].total_value > 0:
                        start_portfolio_value = snapshots[0].total_value  # ← BASELINE
                        portfolio_pct = ((portfolio_snapshot.total_value - start_portfolio_value) / start_portfolio_value) * 100
```

### Hypothesis:

**Hypothesis #1: First snapshot baseline is incorrect for 1M**
- Baseline = `snapshots[0].total_value` (first snapshot in 30-day range)
- If first snapshot has ZERO or very LOW value → percentages inflated
- Example: Baseline $100, current $300 → 200% gain ✓
- But if baseline is $1 by mistake → 29,900% gain ❌

**Hypothesis #2: Date sampling skips true first snapshot**
- `_sample_dates_for_period()` limits 1M to 30 points
- If it samples unevenly and skips the first snapshot → baseline shifts forward
- Example: True first = Sept 3, but sampled first = Sept 5 → baseline off by 2 days
- This would change percentage scale while preserving relative shape

**Hypothesis #3: User started portfolio mid-period**
- User's actual portfolio start date might be within the 1M window
- Code uses `snapshots[0]` which could be the user's very first snapshot ever
- For 3M, YTD, 1Y → first snapshot is further back, more stable baseline
- For 1M → first snapshot is at portfolio inception with low/zero value?

**Hypothesis #4: Data integrity issue specific to 1M date range**
- Could be a duplicate snapshot, incorrect value, or data migration issue
- Only affects Sept 3 - Oct 3 range (1M), not earlier periods

### Questions for Grok:

**Q5:** Should we adjust the baseline for 1M if user's portfolio start is within the period?  
Example: Use user's actual first snapshot globally, not period's first snapshot?

**Q6:** Could `_sample_dates_for_period()` be causing this by shifting the baseline?  
Should we ensure the first and last dates are ALWAYS included in sampled data?

**Q7:** How should we debug this?  
What logging would reveal the baseline value and help identify the issue?

**Q8:** Is there a better baseline calculation method?  
Should we use a "common baseline date" across all periods for consistency?

---

## PROBLEM #3: 5D Chart Long Gap Lines

### User Report:
"In the 5D chart there are long lines between each day. The data points don't flow smoothly from one day's market close data point to the following day's market open data point. Instead there is a long line between each day followed by many data points crammed together, followed by another long line to the next day."

### Screenshot Evidence (5D Chart):
- **Dates shown:** 026, 027, 028, 029, 030, 001, 002, 003 (Sept 26 - Oct 3)
- **Visual Pattern:** Long line → Dense cluster of points → Long line → Dense cluster → ...
- **Issue:** Lines connecting across overnight gaps (16:00 close → 09:30 open next day)
- **Within-day data:** Points are densely packed (intraday snapshots every 30 min)

### Code Analysis:

**Backend:** `api/index.py` lines 13273-13289

```python
# For 5D charts, use full ISO timestamp in ET timezone
elif period == '5D':
    et_timestamp = snapshot.timestamp.astimezone(MARKET_TZ)
    date_label = et_timestamp.isoformat()

chart_data.append({
    'date': date_label,  # ISO timestamp: "2025-09-26T16:00:00-04:00"
    'portfolio': round(portfolio_return, 2),
    'sp500': round(sp500_return, 2)
})
```

**Frontend (Chart.js):** Likely default line chart configuration

```javascript
{
    type: 'line',
    data: {
        labels: ['2025-09-26T09:30:00-04:00', '2025-09-26T10:00:00-04:00', ..., 
                 '2025-09-26T16:00:00-04:00', '2025-09-27T09:30:00-04:00', ...],
        datasets: [{
            data: [1.5, 1.7, ..., 2.1, 2.3, ...]
        }]
    },
    options: {
        spanGaps: true  // Default: connects points across gaps
    }
}
```

### Hypothesis:

**Root Cause: Chart.js connects points across time gaps**
- Market closes at 4:00 PM (16:00)
- Next market opens at 9:30 AM next day (09:30)
- **Gap:** 17.5 hours with no data
- Chart.js draws a straight line from 16:00 to 09:30 (next day)
- Result: Long diagonal/horizontal lines across overnight gaps

**This is expected behavior** for continuous line charts with time series data that has gaps.

### Solutions:

**Solution A: Use `spanGaps: false` in Chart.js**
```javascript
options: {
    elements: {
        line: {
            spanGaps: false  // Don't connect points across null values
        }
    }
}
```
Requires inserting `null` values in data for non-market hours.

**Solution B: Use Chart.js time scale with proper configuration**
```javascript
options: {
    scales: {
        x: {
            type: 'time',
            time: {
                unit: 'hour',
                displayFormats: {
                    hour: 'MMM DD h:mm A'
                }
            },
            adapters: {
                date: {
                    zone: 'America/New_York'  // Use ET timezone
                }
            }
        }
    }
}
```
This allows Chart.js to understand time gaps and render them appropriately.

**Solution C: Backend - Insert null markers between days**
```python
# After building chart_data, insert gaps
processed_chart_data = []
previous_timestamp = None

for point in chart_data:
    current_timestamp = datetime.fromisoformat(point['date'])
    
    if previous_timestamp:
        gap_hours = (current_timestamp - previous_timestamp).total_seconds() / 3600
        
        # If gap > 1 hour (indicates overnight/weekend), insert null
        if gap_hours > 1:
            processed_chart_data.append({
                'date': None,
                'portfolio': None,
                'sp500': None
            })
    
    processed_chart_data.append(point)
    previous_timestamp = current_timestamp

chart_data = processed_chart_data
```

### Questions for Grok:

**Q9:** Which solution is best for handling time gaps in 5D chart?  
- Frontend (Chart.js config) or Backend (insert nulls)?

**Q10:** If we use time scale, will Chart.js properly show gaps in X-axis?  
- Should we use `time` scale or `timeseries` scale?

**Q11:** Should we also apply this fix to 1D chart for consistency?  
- 1D has 30-min intervals but no overnight gaps (single day)

**Q12:** Are there any Chart.js plugins or settings to auto-detect market hours gaps?  
- Would be cleaner than manual null insertion

---

## CRITICAL QUESTIONS SUMMARY

**1D Chart Issues (Q1-Q4):**
1. Should 1D use `== market_day` instead of date range query?
2. Is `func.timezone()` causing double-conversion issues?
3. What's the most reliable way to query "today only" in PostgreSQL with timezone?
4. Should we use `date_trunc()` or `AT TIME ZONE` instead of `cast()`?

**1M Chart Issues (Q5-Q8):**
5. Should we use user's global first snapshot as baseline, not period's first?
6. Does sampling shift the baseline and cause scale issues?
7. What logging would help diagnose the baseline value problem?
8. Is there a better baseline calculation for consistency across periods?

**5D Chart Issues (Q9-Q12):**
9. Frontend (Chart.js config) or Backend (null insertion) for gap handling?
10. Will `time` scale properly show gaps in X-axis?
11. Should 1D also get gap handling for consistency?
12. Any Chart.js plugins/settings for auto-detecting market hours gaps?

---

## DEPLOYMENT CONTEXT

- **Platform:** Vercel (serverless, UTC timezone)
- **Database:** PostgreSQL (Vercel Postgres)
- **Market Hours:** 9:30 AM - 4:00 PM ET (Mon-Fri)
- **Current Time:** Oct 3, 2025 5:28 PM ET (after market close)
- **Previous Fixes:** Date timezone (✓), S&P data source (✓), Intraday timezone (✓)

---

## FILES FOR REVIEW

Please review these specific sections:

1. **`api/index.py`**
   - Lines 13143-13155: `market_day` calculation
   - Lines 13158-13179: 1D query with timezone conversion
   - Lines 13273-13289: 5D timestamp formatting
   - Look for: Date query logic, timezone handling

2. **`portfolio_performance.py`**
   - Lines 783-875: `get_performance_data()` method
   - Lines 829-875: Snapshot query and baseline calculation
   - Lines 555-587: `_sample_dates_for_period()` method
   - Look for: Baseline calculation, sampling logic, 1M specific issues

3. **Frontend Chart.js Configuration** (if accessible)
   - Chart type and options
   - Time scale configuration
   - Gap handling settings

---

Please provide:
1. **Validation** of root cause hypotheses for all three issues
2. **Recommended fixes** with specific code changes
3. **Priority order** - which issue to fix first?
4. **Testing approach** - how to verify fixes work correctly?

Thank you!
