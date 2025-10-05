# 🎯 Portfolio Snapshot Design Decisions - Q&A

## ❓ **Question 1: Were Prices Fetched When witty-raven Added Assets on 6/19/2025?**

### Investigation Endpoint (LIVE NOW):
```
https://apestogether.ai/admin/investigate-first-assets?username=witty-raven
```

This endpoint reveals:
- **Exact timestamp** when user first bought stocks (not just the date)
- **Whether MarketData exists** for those tickers on 6/19/2025
- **All intraday trading** (buy/sell same day)
- **Transaction prices** (what price was recorded at time of purchase)

### Expected Findings:

**Scenario A: Alpha Vantage Was Called**
```json
{
  "first_transaction": {
    "timestamp": "2025-06-19T10:05:23",
    "ticker": "AAPL",
    "price": 186.45  // Real-time quote from Alpha Vantage
  },
  "market_data_on_first_date": {
    "AAPL": {
      "exists": true,
      "open": 185.50,
      "close": 187.20,  // EOD close price
      "high": 188.00,
      "low": 185.00
    }
  }
}
```

**Scenario B: Prices Were Backfilled Later**
```json
{
  "first_transaction": {
    "timestamp": "2025-06-19T10:05:23",
    "ticker": "AAPL",
    "price": 186.00  // User-entered or estimated
  },
  "market_data_on_first_date": {
    "AAPL": {
      "exists": false  // Was backfilled later with yfinance
    }
  }
}
```

### What We'll Do:
- **For snapshot reconstruction:** Always use `MarketData.close_price` (standardized EOD)
- **For transaction records:** Keep original `transaction.price` (historical record)
- **For backfilling:** Use yfinance to fill gaps in MarketData table

---

## ❓ **Question 2: Will Charts/Caches Crash When We Delete Snapshots?**

### TL;DR: **No, they won't crash.** Here's why:

### Backend Safety (leaderboard_utils.py):

```python
def generate_user_portfolio_chart(user_id, period):
    """Generate chart data - returns None if no data"""
    
    # Query snapshots
    snapshots = PortfolioSnapshot.query.filter_by(user_id=user_id)\
        .filter(PortfolioSnapshot.date >= start_date)\
        .order_by(PortfolioSnapshot.date.asc()).all()
    
    # SAFETY: Return None if no snapshots exist
    if not snapshots:
        return None  # ✅ No crash, just returns None
    
    # Build chart data...
    return chart_data
```

### Frontend Safety (dashboard.html):

```javascript
// Line 485-495 in dashboard.html
if (!data.chart_data || data.chart_data.length === 0) {
    // Show "No data available" message
    if (performanceChart) {
        performanceChart.destroy();
    }
    
    // Display user-friendly message
    document.getElementById('chartMessage').innerHTML = 
        '<p>No portfolio data available for this period.</p>';
    
    return;  // ✅ No crash, graceful degradation
}

// Only create chart if data exists
const chart = new Chart(ctx, chartConfig);
```

### Cache Safety:

```python
# When we delete snapshots, we invalidate cache
from flask_caching import Cache

def delete_corrupted_snapshots(user_id, first_holdings_date):
    # Delete snapshots...
    for snap in corrupted:
        db.session.delete(snap)
    
    db.session.commit()
    
    # SAFETY: Invalidate all chart caches for this user
    cache.delete_memoized(get_user_chart_data, user_id)
    cache.delete_memoized(generate_user_portfolio_chart, user_id)
    
    # ✅ Next chart request will regenerate with correct data
```

### What Happens After Deletion:

**Step 1: Snapshots Deleted**
```
Before: 112 snapshots (5/26 - 9/15)
After:  41 snapshots (9/2 - 9/15) [deleted 71 corrupted snapshots]
```

**Step 2: Chart Request**
```javascript
// User loads dashboard, requests 1M chart
fetch('/api/portfolio/performance/1M')
```

**Step 3: Backend Response**
```python
# Query snapshots from last 30 days
snapshots = PortfolioSnapshot.query.filter(
    user_id == 123,
    date >= (today - 30 days)  # Only gets 9/2 onwards
).all()

# User started 9/2, so only 13 days of data
if snapshots:
    return {
        'labels': ['9/2', '9/3', ..., '9/15'],  # 13 days
        'data': [7279.22, 6570.12, ...]
    }
else:
    return None  # No data for this period
```

**Step 4: Frontend Renders**
```javascript
if (data && data.chart_data.length > 0) {
    // Show chart with 13 days of data
    renderChart(data);
} else {
    // Show "Portfolio history starts 9/2/2025"
    showNoDataMessage();
}
```

### **Result: NO CRASH** ✅
- Missing data is handled gracefully at every level
- Chart shows data from first holdings date forward
- Empty periods show helpful message
- No errors, no broken pages

---

## ❓ **Question 3: How Do We Handle Intraday Trading (Buy and Sell Same Day)?**

### TL;DR: **We use End-of-Day snapshots. Intraday gains are captured in transactions, not snapshots.**

### The Design:

**Portfolio Snapshots = End of Day Holdings × Close Prices**

```
Example Timeline for 9/19/2025:

9:30 AM  - Market Opens
10:05 AM - User BUYS 100 AAPL @ $150.00
10:07 AM - User BUYS 50 TSLA @ $220.00
11:15 AM - User SELLS 100 AAPL @ $151.00 (realized gain: $100)
2:45 PM  - User BUYS 200 GOOGL @ $140.00
4:00 PM  - Market Closes

EOD Holdings:
- AAPL: 0 shares (bought and sold same day)
- TSLA: 50 shares
- GOOGL: 200 shares

EOD Snapshot (calculated at 4:00 PM):
- AAPL: 0 shares × $151.50 close = $0
- TSLA: 50 shares × $222.00 close = $11,100
- GOOGL: 200 shares × $141.50 close = $28,300
- Total: $39,400

Realized Gains (recorded in Transaction table):
- AAPL: +$100 (sold for $151, bought for $150)
- Cash Balance: Increased by $100
```

### What We Capture:

✅ **Transaction Table** (ALL activity):
```sql
10:05:23 | BUY  | AAPL | 100 | $150.00 | -$15,000
10:07:45 | BUY  | TSLA |  50 | $220.00 | -$11,000
11:15:12 | SELL | AAPL | 100 | $151.00 | +$15,100  [+$100 gain]
14:45:30 | BUY  | GOOGL| 200 | $140.00 | -$28,000
```

✅ **PortfolioSnapshot Table** (EOD only):
```sql
Date       | Total Value | Holdings Snapshot
2025-09-19 | $39,400.00  | TSLA: 50, GOOGL: 200, AAPL: 0
```

❌ **We DON'T Capture:**
- Intraday portfolio high/low watermarks
- Portfolio value at 11:00 AM vs 2:00 PM
- Multiple snapshots per day (except for 1D intraday charts, which we DO have)

### Why This Approach Works:

**1. Matches Traditional Brokerages**
- Fidelity, Schwab, E-Trade all show EOD portfolio value
- Daily charts show one data point per day
- Realized gains are reflected in cash balance

**2. Simplifies Calculations**
- One snapshot per day = clean chart data
- No complex intraday interpolation needed
- Percentage gains are straightforward

**3. Captures What Matters**
- Users see their EOD net worth
- Transaction history shows all trades
- Realized gains are preserved in transaction records

**4. Performance Benefits**
- One snapshot per day vs 14 snapshots per day
- Less database storage
- Faster chart generation

### Intraday Trading Example:

**High Volume Trader (50 trades/day):**
```
Trades on 9/19/2025:
- 9:30 AM: Buy 100 AAPL @ $150
- 9:45 AM: Sell 100 AAPL @ $151 (+$100)
- 10:00 AM: Buy 200 TSLA @ $220
- 10:15 AM: Sell 100 TSLA @ $222 (+$200)
- 10:30 AM: Buy 50 GOOGL @ $140
... 45 more trades throughout the day ...

EOD Holdings:
- TSLA: 100 shares (kept half)
- GOOGL: 50 shares
- AAPL: 0 shares (day traded)

EOD Snapshot:
- Total value based on TSLA + GOOGL holdings at close
- Realized gains: $300+ from day trading (in cash balance)
```

**Chart Shows:**
```
Day-over-day portfolio change from market close to market close.
If they ended with $50,000 on 9/18 and $52,000 on 9/19,
the chart shows: +4% gain (including all realized gains from intraday trading).
```

### For Users Who Want Intraday Tracking:

We **do** have intraday snapshots for the 1D chart:
```python
# PortfolioSnapshotIntraday table (collected every 30 minutes)
# Shows portfolio fluctuations during market hours
# But this is OPTIONAL - not required for core functionality
```

---

## ❓ **Question 4: What Happens to Charts Before First Holdings Date?**

### Current Behavior (Broken):
```
User starts trading: 9/2/2025
YTD chart requests: 1/1/2025 - 9/15/2025

Query returns:
- Snapshots from 5/26 - 9/15 (corrupted data before 9/2)
- Chart shows flat 0% from 5/26 - 9/1 (wrong!)
- Chart shows actual gains from 9/2 onwards
```

### Fixed Behavior (After Cleanup):
```
User starts trading: 9/2/2025
YTD chart requests: 1/1/2025 - 9/15/2025

Query returns:
- Snapshots from 9/2 - 9/15 ONLY (no corrupted data)
- Chart labels start from 9/2 (13 data points)
- NO LINE before 9/2 (empty space on chart)
- Message: "Portfolio history starts 9/2/2025"
```

### Implementation:

```python
def generate_user_portfolio_chart(user_id, period):
    """Generate chart starting from first holdings date"""
    
    # Get user's first holdings date
    first_holdings = find_first_real_holdings_date(user_id)
    
    if not first_holdings:
        return None  # User never had holdings
    
    # Calculate period start date
    if period == '1M':
        requested_start = today - timedelta(days=30)
    elif period == 'YTD':
        requested_start = date(today.year, 1, 1)
    # ... etc
    
    # DON'T go back before first holdings date
    actual_start = max(requested_start, first_holdings)
    
    # Query snapshots from actual_start forward
    snapshots = PortfolioSnapshot.query.filter(
        user_id == user_id,
        date >= actual_start  # ✅ No data before first holdings
    ).all()
    
    return {
        'labels': [...],
        'data': [...],
        'note': f'Portfolio history starts {first_holdings}'
    }
```

### Chart Display:

**YTD Chart (user started 9/2):**
```
Jan  Feb  Mar  Apr  May  Jun  Jul  Aug  Sep
                                      |----📈
                                      9/2  9/15

Note: "Portfolio history starts September 2, 2025"
```

**1M Chart (user started 9/2):**
```
Aug 15  Aug 20  Aug 25  Aug 30  Sep 5   Sep 10  Sep 15
                                 |-------📈----------|
                                 9/2              9/15

Shows: 13 days of data (not full 30 days)
```

---

## 🎯 **Summary: Design is Safe and Sound**

### ✅ **Backend Safety:**
- Returns `None` if no snapshots exist
- Queries only from first holdings date forward
- No assumptions about data always existing

### ✅ **Frontend Safety:**
- Checks `if (!data || data.length === 0)` before rendering
- Shows user-friendly "No data" message
- Destroys old chart before creating new one
- No crashes on empty data

### ✅ **Cache Safety:**
- Invalidates caches when snapshots deleted
- Regenerates with correct date range
- No stale data served

### ✅ **Intraday Trading Handling:**
- Transaction table captures ALL trades
- Snapshot table shows EOD holdings only
- Realized gains reflected in cash balance
- Matches traditional brokerage reporting

### ✅ **User Experience:**
- Charts start from when user actually started trading
- No misleading flat 0% periods
- Clear messages about data availability
- Professional, broker-like behavior

---

## 🔧 **Next Step: Run Investigation**

Visit this endpoint to see witty-raven's actual data:
```
https://apestogether.ai/admin/investigate-first-assets?username=witty-raven
```

This will show:
- Exact first transaction timestamp
- Whether market data was fetched
- All intraday trading patterns
- Whether they're a day trader or buy-and-hold

Then we'll know exactly how to handle the cleanup! 📊
