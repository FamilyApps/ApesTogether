# 🔧 CASCADE'S SOLUTION TO CHART DISPLAY ISSUES

## ISSUE #1: S&P 500 Label Shows +0% (Chart Shows ~13.95%)

### Root Cause Analysis

**Problem Location:** `api/index.py` lines 7310-7311

```python
portfolio_data = datasets[0].get('data', []) if len(datasets) > 0 else []
sp500_data = datasets[1].get('data', []) if len(datasets) > 1 else []
```

**The Bug:**
The cached chart data (from `UserPortfolioChartCache`) uses Chart.js format with `{x: date, y: value}` objects, but the API endpoint is trying to read the data array directly without extracting the `y` values.

**Then at portfolio_performance.py lines 706-707:**
```python
portfolio_return = chart_data[-1]['portfolio']  # Expects a simple number
sp500_return = chart_data[-1]['sp500']         # Expects a simple number
```

But if the cached data has `{x, y}` format, this extraction fails and defaults to 0.

### Solution

**FIX #1: In `api/index.py` around line 7310-7320:**

Instead of just extracting the data arrays, we need to:
1. Extract the `y` values from the Chart.js data points
2. Get the LAST value for the return percentage display
3. Format the chart data correctly for the dashboard

```python
# Extract performance percentages from Chart.js data
datasets = cached_data.get('datasets', [])
if not datasets or len(datasets) < 2:
    logger.warning(f"Insufficient datasets in cached data for user {user_id}, period {period_upper}")
    raise ValueError("Insufficient datasets in cached chart data")

portfolio_dataset = datasets[0].get('data', [])
sp500_dataset = datasets[1].get('data', [])

if not portfolio_dataset or not sp500_dataset:
    logger.warning(f"Missing data in cached chart for user {user_id}, period {period_upper}")
    raise ValueError("Missing data in cached chart")

# Convert Chart.js format {x, y} to dashboard format
chart_data = []
labels = cached_data.get('labels', [])

for i in range(len(portfolio_dataset)):
    chart_point = {}
    
    # Handle both formats: {x, y} objects or simple numbers
    if isinstance(portfolio_dataset[i], dict):
        chart_point['portfolio'] = portfolio_dataset[i].get('y', 0)
        chart_point['sp500'] = sp500_dataset[i].get('y', 0) if i < len(sp500_dataset) else 0
        chart_point['date'] = portfolio_dataset[i].get('x', labels[i] if i < len(labels) else '')
    else:
        # Simple number format
        chart_point['portfolio'] = portfolio_dataset[i]
        chart_point['sp500'] = sp500_dataset[i] if i < len(sp500_dataset) else 0
        chart_point['date'] = labels[i] if i < len(labels) else ''
    
    chart_data.append(chart_point)

# Get last values for display (these are cumulative returns from start)
portfolio_return = chart_data[-1]['portfolio'] if chart_data else 0
sp500_return = chart_data[-1]['sp500'] if chart_data else 0

logger.info(f"Cache conversion successful: portfolio={portfolio_return}%, sp500={sp500_return}%, points={len(chart_data)}")

return jsonify({
    'portfolio_return': round(portfolio_return, 2),
    'sp500_return': round(sp500_return, 2),
    'chart_data': chart_data,
    'period': period_upper,
    'from_cache': True
})
```

---

## ISSUE #2: X-Axis Shows Unix Timestamps (1D and 5D Charts)

### Root Cause Analysis

**Problem Location:** `templates/dashboard.html` lines 557-593

**The Bug:**
- Line 557: `const useLinearScale = !['1D', '5D'].includes(currentPeriod);`
- This means 1D and 5D should use TIME scale, but longer periods use LINEAR scale
- Line 562 for linear scale: `xValue = index;` - Uses array index as x-value
- But line 672 shows: `type: useLinearScale ? 'linear' : 'time'`

**The issue:** For LINEAR scale charts (1M, 3M, YTD, 1Y), the x-axis shows the array index numbers (0, 1, 2, 3...) instead of dates!

**Actually wait** - you said 1D and 5D show timestamps. Let me re-read...

Oh! The problem is the TIME scale is receiving dates but not formatting them properly. Let me check line 678-692:

```javascript
time: useLinearScale ? undefined : {
    displayFormats: {
        hour: 'h:mm a',
        day: 'MMM dd',
        ...
```

**The issue is line 687-692:** There's a DUPLICATE `time:` configuration! Line 678 and line 687 both set `time:`, so line 687 overrides line 678.

### Solution

**FIX #2: In `templates/dashboard.html` around line 678-695:**

Remove the duplicate `time` configuration:

```javascript
scales: {
    x: {
        type: useLinearScale ? 'linear' : 'time',
        display: true,
        title: {
            display: true,
            text: currentPeriod === '1D' ? 'Time (ET)' : 'Date'
        },
        // SINGLE time configuration for time scale
        time: useLinearScale ? undefined : {
            unit: currentPeriod === '1D' ? 'hour' : (currentPeriod === '5D' ? 'day' : 'day'),
            displayFormats: {
                hour: 'h:mm a',
                day: currentPeriod === '5D' ? 'ddd' : 'MMM dd',
                week: 'MMM dd',
                month: 'MMM yyyy'
            },
            tooltipFormat: currentPeriod === '1D' ? 'MMM dd, h:mm a' : 'MMM dd, yyyy'
        },
        // For linear scale charts, show dates on x-axis using ticks callback
        ticks: useLinearScale ? {
            callback: function(value, index) {
                // value is the array index, we need to get the actual date
                const dataIndex = Math.floor(value);
                if (data.chart_data && data.chart_data[dataIndex]) {
                    const date = new Date(data.chart_data[dataIndex].date);
                    // Format based on period
                    if (currentPeriod === '1M') {
                        return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
                    } else if (currentPeriod === '3M' || currentPeriod === 'YTD') {
                        return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
                    } else {
                        return date.toLocaleDateString('en-US', { month: 'short', year: '2-digit' });
                    }
                }
                return '';
            },
            maxTicksLimit: 10
        } : undefined,
```

---

## ALTERNATIVE SIMPLER FIX FOR ISSUE #2

**Just use TIME scale for everything!**

Change line 557:
```javascript
// OLD:
const useLinearScale = !['1D', '5D'].includes(currentPeriod);

// NEW:
const useLinearScale = false;  // Always use time scale for proper date formatting
```

And remove the `xValue = index` logic entirely (lines 559-593), replacing with:

```javascript
const portfolioDataPoints = data.chart_data.map((item) => {
    const dateStr = item.date;
    let xValue;
    if (dateStr.includes('T')) {
        // Already has time component
        xValue = new Date(dateStr);
    } else {
        // Add time component to avoid timezone issues
        xValue = new Date(dateStr + 'T12:00:00');
    }
    return { x: xValue, y: item.portfolio };
});

const sp500DataPoints = data.chart_data.map((item) => {
    const dateStr = item.date;
    let xValue;
    if (dateStr.includes('T')) {
        xValue = new Date(dateStr);
    } else {
        xValue = new Date(dateStr + 'T12:00:00');
    }
    return { x: xValue, y: item.sp500 };
});
```

This way Chart.js handles ALL date formatting automatically!

---

## SUMMARY

**Issue #1 (S&P 500 0%):**
- Backend API not properly extracting values from cached Chart.js data
- Fix: Properly parse `{x, y}` format and extract `y` values
- File: `api/index.py` lines 7300-7320

**Issue #2 (Timestamps on x-axis):**
- Option A: Fix ticks callback for linear scale
- Option B (SIMPLER): Use time scale for all periods
- File: `templates/dashboard.html` lines 557-600

---

## TESTING

After fixes:
1. S&P 500 label should show "+13.95%" (or actual value)
2. X-axis should show "Sep 26", "Sep 30" etc. (not numbers)
3. Chart should still render correctly
