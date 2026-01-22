# Chart Issues Analysis - October 3, 2025

**Date:** October 3, 2025 5:28 PM ET  
**Issues:** 1D showing yesterday's data, 1M scale incorrect, 5D gap lines

---

## 🔴 ISSUE #1: 1D Chart Showing Yesterday's Data

### Symptoms (From Screenshot):
- **Today:** October 3, 2025 5:28 PM ET
- **1D Chart:** Showing data from "Oct 02, 4:30 PM" onwards
- **Expected:** Should ONLY show Oct 3 data (9:30 AM - 4:00 PM ET)
- **Timeline shown:** 5:00 PM → 2:00 PM (spans from yesterday to today)

### Screenshot Evidence:
- Tooltip shows "Oct 02, 4:30 PM" with portfolio +0.00%
- X-axis shows times from 5:00 PM to 2:00 PM
- Portfolio line starts around 5:00 PM (yesterday) and continues through today

### Code Analysis:

**File:** `api/index.py` lines 13158-13179

```python
if period == '1D':
    start_date = market_day  # Should be Oct 3
    end_date = market_day    # Should be Oct 3

# Query snapshots using ET timezone conversion
snapshots = PortfolioSnapshotIntraday.query.filter(
    PortfolioSnapshotIntraday.user_id == user_id,
    cast(func.timezone('America/New_York', PortfolioSnapshotIntraday.timestamp), Date) >= start_date,
    cast(func.timezone('America/New_York', PortfolioSnapshotIntraday.timestamp), Date) <= end_date
).order_by(PortfolioSnapshotIntraday.timestamp).all()
```

### Hypothesis:

**Root Cause #1: Query using >= instead of ==**
- Query uses `>= start_date` and `<= end_date`
- For 1D, start_date = end_date = Oct 3
- Should be using `== market_day` instead of range query
- Currently fetches ANY snapshot on Oct 3, but might also grab Oct 2 if timezone conversion is off

**Root Cause #2: Timestamp timezone issue**
- `PortfolioSnapshotIntraday.timestamp` might be stored in UTC
- `func.timezone('America/New_York', ...)` converts to ET for comparison
- But if timestamp is ALREADY in ET (timezone-aware), this could double-convert
- Result: Oct 3 9:30 AM ET → converted as if UTC → shows as Oct 2

**Root Cause #3: market_day calculation issue**
- `market_day` calculated from `get_market_time().date()`
- Should return Oct 3, but logs show Oct 2 data being returned
- Possible: `market_day` is somehow Oct 2?

### Verification Needed:
1. Check logs for "Date calculation (ET)" message - what is `market_day`?
2. Check "Snapshots by date" log - are snapshots actually dated Oct 2 or Oct 3?
3. Check database: What timezone is `PortfolioSnapshotIntraday.timestamp` stored in?

---

## 🔴 ISSUE #2: 1M Chart Scale Incorrect

### Symptoms (From User Report):
- **1M Chart:** Portfolio values show much higher percentages than expected
- **Example:** If 3M chart shows +3%, 1M might show +6% (approximately doubled)
- **Shape correct:** The line pattern/shape matches other periods
- **Scale wrong:** Only the Y-axis percentage values are off

### Screenshot Evidence (5D Chart for reference):
- 5D chart shows Your Portfolio: +1.18%
- 1M chart likely shows inflated value (user reports it's multiplied by ~2)

### Code Analysis:

**File:** `portfolio_performance.py` lines 829-875

```python
# Get portfolio values for charting
snapshots = PortfolioSnapshot.query.filter(
    and_(
        PortfolioSnapshot.user_id == user_id,
        PortfolioSnapshot.date >= start_date,
        PortfolioSnapshot.date <= end_date
    )
).order_by(PortfolioSnapshot.date).all()

# ... build chart data ...
for date_key in sampled_dates:
    if date_key >= start_date and date_key in sp500_data:
        # ...
        portfolio_snapshot = next((s for s in snapshots if s.date == date_key), None)
        if portfolio_snapshot and snapshots[0].total_value > 0:
            start_portfolio_value = snapshots[0].total_value  # ← BASELINE
            portfolio_pct = ((portfolio_snapshot.total_value - start_portfolio_value) / start_portfolio_value) * 100
```

### Hypothesis:

**Root Cause #1: First snapshot baseline incorrect for 1M**
- Baseline = `snapshots[0].total_value` (first snapshot in queried range)
- For 1M: start_date = today - 30 days
- If first snapshot in that range has ZERO or very LOW value → percentages inflated
- If first snapshot is missing and defaults to some wrong value → scale off

**Root Cause #2: Data sampling issue**
- `_sample_dates_for_period()` samples 30 points for 1M
- If sampling skips the true "first" snapshot and starts from a later one → wrong baseline
- Shape correct because relative changes are preserved, but absolute scale wrong

**Root Cause #3: Duplicate snapshots or data issue**
- If there are duplicate snapshots for the same date with different values
- First one might have incorrect value → throws off entire calculation

### Verification Needed:
1. Query database: What is `snapshots[0].total_value` for the 1M period?
2. Check logs: What does "S&P 500 return extracted from chart" show for 1M?
3. Compare: First snapshot value vs actual portfolio value 30 days ago

---

## 🔴 ISSUE #3: 5D Chart Long Gap Lines

### Symptoms (From Screenshot):
- **5D Chart:** Shows data from Sept 26 (026) to Oct 3 (003)
- **Gap Lines:** Long horizontal/diagonal lines connecting end of one day to start of next
- **Data Clustering:** Each day's data points are clustered together
- **Visual Pattern:** Line → Cluster → Line → Cluster → Line

### Screenshot Evidence:
- Clear visual pattern of long lines between days
- Data points for each day are tightly clustered
- Lines span overnight gaps (market closed)

### Code Analysis:

**Chart.js Configuration** (Frontend)

The issue is that Chart.js connects data points with continuous lines by default. When there are gaps in time (overnight, weekends), it draws a straight line from the last point of one day to the first point of the next day.

**Current behavior:**
```javascript
{
    type: 'line',
    data: {
        labels: ['2025-09-26T16:00:00-04:00', '2025-09-27T09:30:00-04:00', ...],
        datasets: [{
            data: [1.5, 2.1, ...]
        }]
    },
    options: {
        spanGaps: true  // ← Default: connects across gaps
    }
}
```

### Hypothesis:

**Root Cause: Time-series data with gaps not handled**
- Chart.js treats data as continuous time series
- No indication that 16:00 (market close) to 09:30 (next market open) is a "gap"
- Result: Draws line connecting across 17.5 hour gap

### Solutions:

**Option A: Use `spanGaps: false`**
```javascript
options: {
    elements: {
        line: {
            spanGaps: false  // Don't connect across null values
        }
    }
}
```
But requires inserting `null` values for non-market hours.

**Option B: Use time-series scale with proper gaps**
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
            ticks: {
                source: 'auto',
                autoSkip: true
            }
        }
    }
}
```
This shows gaps as actual gaps in the X-axis.

**Option C: Segment data by day**
Insert `null` between days:
```python
# In chart data generation
for date_key in sampled_dates:
    # Check if this is a new day
    if previous_date and date_key != previous_date:
        # Insert gap marker
        chart_data.append({
            'date': None,  # null value creates gap
            'portfolio': None,
            'sp500': None
        })
```

---

## 🎯 PROPOSED FIXES

### Fix #1: 1D Chart - Query for Exact Date Only

**File:** `api/index.py` lines 13175-13179

**BEFORE:**
```python
snapshots = PortfolioSnapshotIntraday.query.filter(
    PortfolioSnapshotIntraday.user_id == user_id,
    cast(func.timezone('America/New_York', PortfolioSnapshotIntraday.timestamp), Date) >= start_date,
    cast(func.timezone('America/New_York', PortfolioSnapshotIntraday.timestamp), Date) <= end_date
).order_by(PortfolioSnapshotIntraday.timestamp).all()
```

**AFTER:**
```python
if period == '1D':
    # For 1D, query for EXACT date only (not range)
    snapshots = PortfolioSnapshotIntraday.query.filter(
        PortfolioSnapshotIntraday.user_id == user_id,
        cast(func.timezone('America/New_York', PortfolioSnapshotIntraday.timestamp), Date) == market_day
    ).order_by(PortfolioSnapshotIntraday.timestamp).all()
else:
    # For 5D, use date range
    snapshots = PortfolioSnapshotIntraday.query.filter(
        PortfolioSnapshotIntraday.user_id == user_id,
        cast(func.timezone('America/New_York', PortfolioSnapshotIntraday.timestamp), Date) >= start_date,
        cast(func.timezone('America/New_York', PortfolioSnapshotIntraday.timestamp), Date) <= end_date
    ).order_by(PortfolioSnapshotIntraday.timestamp).all()
```

**Why:** Using `==` instead of range ensures ONLY today's data is fetched.

### Fix #2: 1M Chart - Investigate Baseline Issue

**Approach:** Add logging to diagnose baseline calculation

**File:** `portfolio_performance.py` after line 850

```python
if snapshots and sp500_data:
    # Log first snapshot for debugging
    logger.info(f"Period {period}: First snapshot date={snapshots[0].date}, value={snapshots[0].total_value}")
    logger.info(f"Period {period}: Last snapshot date={snapshots[-1].date}, value={snapshots[-1].total_value}")
    logger.info(f"Period {period}: Total snapshots={len(snapshots)}, date range={start_date} to {end_date}")
```

**Then check logs to see:**
1. Is first snapshot value correct?
2. Are all snapshots in correct date range?
3. Is there a data issue specific to 1M?

**Potential Fix:** If baseline is wrong, recalculate from user's actual start:
```python
# Use user's actual portfolio start date, not arbitrary period start
user_first_snapshot = PortfolioSnapshot.query.filter_by(user_id=user_id)\
    .order_by(PortfolioSnapshot.date.asc()).first()

if user_first_snapshot and start_date < user_first_snapshot.date:
    # Adjust start_date to actual portfolio start
    start_date = user_first_snapshot.date
    logger.info(f"Adjusted start_date to user's actual portfolio start: {start_date}")
```

### Fix #3: 5D Chart - Handle Time Gaps

**Option A: Frontend Chart.js Config Change**

Update chart options to better handle time gaps:
```javascript
options: {
    scales: {
        x: {
            type: 'time',
            time: {
                unit: 'hour',
                displayFormats: {
                    hour: 'h:mm A'
                },
                tooltipFormat: 'MMM DD, h:mm A'
            },
            adapters: {
                date: {
                    zone: 'America/New_York'
                }
            }
        }
    },
    elements: {
        line: {
            spanGaps: false  // Don't connect across large gaps
        },
        point: {
            radius: 2  // Smaller points for better density
        }
    }
}
```

**Option B: Backend - Insert Null Values**

**File:** `api/index.py` after line 13285

```python
# After building chart_data, insert nulls between days
processed_chart_data = []
previous_date = None

for point in chart_data:
    current_timestamp = datetime.fromisoformat(point['date'])
    current_date = current_timestamp.date()
    
    # If date changed and it's not the first point, insert a gap
    if previous_date and current_date != previous_date:
        # Check if gap is > 1 hour (indicates overnight/weekend)
        if previous_timestamp and (current_timestamp - previous_timestamp).seconds > 3600:
            processed_chart_data.append({
                'date': None,
                'portfolio': None,
                'sp500': None
            })
    
    processed_chart_data.append(point)
    previous_date = current_date
    previous_timestamp = current_timestamp

chart_data = processed_chart_data
```

---

## 📋 DIAGNOSTIC QUERIES

### Check 1D Chart Data:
```sql
-- See what dates are in PortfolioSnapshotIntraday for today
SELECT 
    (timestamp AT TIME ZONE 'America/New_York')::date as et_date,
    (timestamp AT TIME ZONE 'America/New_York')::time as et_time,
    total_value
FROM portfolio_snapshot_intraday
WHERE user_id = <USER_ID>
  AND (timestamp AT TIME ZONE 'America/New_York')::date >= '2025-10-02'
ORDER BY timestamp;
```

### Check 1M Baseline:
```sql
-- See first snapshot in 1M range
SELECT date, total_value
FROM portfolio_snapshot
WHERE user_id = <USER_ID>
  AND date >= (CURRENT_DATE - INTERVAL '30 days')
ORDER BY date ASC
LIMIT 5;
```

---

## ✅ TESTING PLAN

1. **Fix 1D Chart**
   - Deploy fix
   - Test: View 1D chart after market hours (> 4 PM ET)
   - Verify: Only shows today's data (9:30 AM - 4:00 PM ET)
   - Check logs: "Snapshots by date" should show ONLY today

2. **Fix 1M Chart**
   - Add logging
   - Check logs after next market close
   - Identify baseline issue
   - Apply appropriate fix
   - Verify: 1M percentages match 3M scale

3. **Fix 5D Chart**
   - Implement gap handling (frontend or backend)
   - Test: View 5D chart
   - Verify: No long lines between days, or proper time gaps shown

---

**Ready for Grok validation and implementation!**
