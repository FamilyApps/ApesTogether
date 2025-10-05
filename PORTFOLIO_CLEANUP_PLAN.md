# 🧹 Portfolio Snapshot Cleanup Plan

## 📋 OVERVIEW

We have corrupted portfolio snapshots from early software development where:
- Snapshots were created BEFORE users had any assets
- Backfill assigned baseline values ($7,279.22) to dates when user owned nothing
- This causes flat 0% gains in charts and misrepresents portfolio history
- Charts show lines going back to dates before the user even started trading

## 🎯 OBJECTIVES

1. **Identify First Real Holdings Date** for each user
2. **Delete Corrupted Snapshots** from before that date
3. **Backfill Accurate Historical Prices** for all user assets
4. **Rebuild Snapshots** with correct values from first holdings date forward
5. **Fix Chart Display** to show no line before user started trading
6. **Recalculate Gains** starting from actual first holdings date

---

## 🚨 CRITICAL DESIGN DECISIONS

### Design Decision 1: End-of-Day Snapshots Only

**Current Design:**
- Portfolio snapshots are taken at **market close** (end of day)
- Snapshot uses closing prices from `MarketData.close_price`
- All transactions during the day are aggregated to determine EOD holdings

**Intraday Trading Handling:**
```
Example: User buys 100 AAPL at 10:05 AM ($150) and sells at 10:15 AM ($151)
- Intraday gain: $100 (captured in Transaction table)
- EOD holdings: 0 shares of AAPL
- EOD snapshot: Portfolio value WITHOUT AAPL
- Impact: Realized gains/losses are reflected in cash balance, not EOD snapshot
```

**Why This Works:**
- Snapshots show "what you own at market close"
- Realized gains become cash (increases buying power for other stocks)
- Matches how traditional brokerages report portfolio value
- Simplifies chart generation (one data point per day)

**What We Capture:**
✅ EOD portfolio value based on holdings × close prices  
✅ Transaction history (all buys/sells with timestamps)  
✅ Realized gains in transaction records  
❌ Intraday portfolio fluctuations  
❌ High-water marks during the day  

**Future Enhancement (Phase 7 - Optional):**
- Add "Realized Gains" field to snapshots
- Calculate cumulative realized gains from all sold positions
- Display alongside unrealized gains in portfolio

### Design Decision 2: Chart Handling of Missing Data

**Problem:** What happens when user has no assets or no snapshot for a date?

**Solution:**
```javascript
// Chart.js handles missing data points gracefully:
// - If data array is empty: Chart shows "No data available"
// - If data array has gaps: Chart skips those dates (no line segment)
// - If labels exist but data is null: Point is skipped

// Example:
{
  labels: ['2025-06-19', '2025-06-20', null, '2025-06-23'],  // null = skip
  data:   [10000,        10200,        null, 10500]           // null = no point
}

// For dates before first holdings:
// Simply don't include them in labels/data arrays at all
// Chart will start from first holdings date automatically
```

**Implementation:**
1. Query snapshots WHERE `date >= first_holdings_date`
2. Filter out weekends and dates with no data
3. Chart automatically shows no line before first data point
4. No crash, no special handling needed

**Cache Safety:**
- Cache is keyed by `(user_id, period)`
- When we delete old snapshots, we invalidate cache: `cache.delete_memoized(get_chart_data, user_id)`
- New cache will be generated with correct date range
- No stale data served

### Design Decision 3: Market Data Timing

**Question:** Were prices fetched when user added assets on 6/19/2025?

**Investigation Needed:**
- Check Transaction table for exact timestamps
- Check if MarketData exists for those tickers on 6/19/2025
- Determine if Alpha Vantage call was made at time of purchase

**Two Scenarios:**

**Scenario A: Real-time prices were fetched**
- User bought at 10:05 AM
- Alpha Vantage called immediately
- `transaction.price` = real-time quote
- `MarketData.close_price` = EOD price (fetched later)
- **For snapshots:** Use `MarketData.close_price` (standardized)

**Scenario B: Prices were backfilled later**
- User bought at 10:05 AM
- `transaction.price` = user-entered or estimated
- `MarketData` was backfilled from yfinance weeks later
- **For snapshots:** Still use `MarketData.close_price` (most accurate)

**Endpoint to Investigate:** `/admin/investigate-first-assets?username=witty-raven`
- Shows first transaction timestamp
- Shows whether market data exists
- Shows intraday trading patterns

---

## 📊 PHASE 1: ASSESSMENT & DISCOVERY

### 1.1 Create User Assessment Tool

**Purpose:** Find the REAL first holdings date for each user

**Logic:**
```python
def find_first_real_holdings_date(user_id):
    """
    Find the first date when user actually held stocks.
    
    Rules:
    - Check Stock table for earliest purchase_date
    - Check Transaction table for earliest BUY timestamp
    - If user bought AND sold same day, that still counts as first holdings date
    - Return None if user never had holdings
    """
    
    # Method 1: Check Stock table (current holdings)
    first_stock = Stock.query.filter_by(user_id=user_id)\
        .order_by(Stock.purchase_date.asc()).first()
    
    # Method 2: Check Transaction table (includes sold positions)
    first_transaction = Transaction.query.filter_by(user_id=user_id)\
        .filter_by(type='buy')\
        .order_by(Transaction.timestamp.asc()).first()
    
    # Take the earlier of the two
    dates = []
    if first_stock:
        dates.append(first_stock.purchase_date)
    if first_transaction:
        dates.append(first_transaction.timestamp.date())
    
    return min(dates) if dates else None
```

### 1.2 Generate Assessment Report

**Endpoint:** `/admin/assess-portfolio-data`

**Output:**
```
USER PORTFOLIO DATA ASSESSMENT
==============================

witty-raven:
  First Holdings Date: 2025-09-02
  Earliest Snapshot:   2025-05-26
  Corrupted Days:      70 (snapshots before first holdings)
  Action Required:     DELETE 70 snapshots

wise-buffalo:
  First Holdings Date: 2025-08-15
  Earliest Snapshot:   2025-06-01
  Corrupted Days:      52
  Action Required:     DELETE 52 snapshots

wild-bronco:
  First Holdings Date: 2025-07-10
  Earliest Snapshot:   2025-07-10
  Corrupted Days:      0
  Action Required:     NONE (data is clean!)

testing2:
  First Holdings Date: Never had holdings
  Earliest Snapshot:   2025-05-26
  Corrupted Days:      ALL (112 snapshots)
  Action Required:     DELETE ALL snapshots

SUMMARY:
- Total Users: 5
- Clean Users: 1
- Users Needing Cleanup: 4
- Total Corrupted Snapshots: 234
```

---

## 🗑️ PHASE 2: DELETE CORRUPTED SNAPSHOTS

### 2.1 Create Deletion Script

**Purpose:** Remove snapshots from before user's first holdings date

**Safety:**
- DRY RUN mode to preview deletions
- Requires explicit confirmation
- Backs up deleted snapshot data to JSON file
- Can be reversed if needed

**Script:** `delete_corrupted_snapshots.py`

```python
def delete_corrupted_snapshots(user_id, first_holdings_date, dry_run=True):
    """
    Delete portfolio snapshots from before user had any holdings.
    
    Args:
        user_id: User to clean up
        first_holdings_date: First date user had stocks
        dry_run: If True, only show what would be deleted
    
    Returns:
        Number of snapshots deleted
    """
    
    # Find corrupted snapshots
    corrupted = PortfolioSnapshot.query.filter(
        PortfolioSnapshot.user_id == user_id,
        PortfolioSnapshot.date < first_holdings_date
    ).all()
    
    if dry_run:
        print(f"DRY RUN: Would delete {len(corrupted)} snapshots")
        for snap in corrupted:
            print(f"  - {snap.date}: ${snap.total_value}")
        return 0
    
    # Backup before deletion
    backup = [{
        'date': snap.date.isoformat(),
        'total_value': float(snap.total_value),
        'percentage_gain': float(snap.percentage_gain)
    } for snap in corrupted]
    
    backup_file = f'snapshot_backup_{user_id}_{datetime.now():%Y%m%d_%H%M%S}.json'
    with open(backup_file, 'w') as f:
        json.dump(backup, f, indent=2)
    
    print(f"Backed up {len(corrupted)} snapshots to {backup_file}")
    
    # Delete
    for snap in corrupted:
        db.session.delete(snap)
    
    db.session.commit()
    
    print(f"✅ Deleted {len(corrupted)} corrupted snapshots")
    return len(corrupted)
```

### 2.2 Admin Interface for Deletion

**Add to admin page:**

```html
<div class="batch">
    <h3>🗑️ Phase 2: Delete Corrupted Snapshots</h3>
    <p>Run DRY RUN first to see what would be deleted</p>
    
    <button onclick="deleteCorruptedSnapshots('witty-raven', true)">
        👁️ DRY RUN: witty-raven
    </button>
    <button onclick="deleteCorruptedSnapshots('witty-raven', false)">
        🗑️ DELETE: witty-raven
    </button>
    
    <!-- Repeat for other users -->
</div>
```

---

## 💰 PHASE 3: BACKFILL HISTORICAL MARKET DATA

### 3.1 Identify Missing Historical Prices

**Purpose:** Ensure we have market data for all dates we need to recreate snapshots

**Logic:**
```python
def identify_missing_market_data(user_id, first_holdings_date):
    """
    Find which historical prices we need to backfill.
    
    For each stock the user has EVER owned (current + sold):
    - Get the date they first owned it
    - Check if we have daily market_data from that date to today
    - Report missing date ranges
    """
    
    # Get all stocks user has ever owned
    current_stocks = Stock.query.filter_by(user_id=user_id).all()
    
    # Get stocks from transactions (includes sold positions)
    transactions = Transaction.query.filter_by(user_id=user_id).all()
    all_tickers = set([s.ticker for s in current_stocks])
    all_tickers.update([t.ticker for t in transactions])
    
    missing_data = {}
    
    for ticker in all_tickers:
        # Find first date user owned this ticker
        first_buy = Transaction.query.filter_by(
            user_id=user_id, 
            ticker=ticker, 
            type='buy'
        ).order_by(Transaction.timestamp.asc()).first()
        
        if not first_buy:
            continue
        
        start_date = first_buy.timestamp.date()
        end_date = date.today()
        
        # Check for missing market data
        existing_dates = set([
            md.date for md in MarketData.query.filter_by(ticker=ticker)
            .filter(MarketData.date >= start_date)
            .filter(MarketData.date <= end_date)
            .all()
        ])
        
        # Generate expected weekdays
        expected_dates = []
        current = start_date
        while current <= end_date:
            if current.weekday() < 5:  # Weekday
                expected_dates.append(current)
            current += timedelta(days=1)
        
        missing = [d for d in expected_dates if d not in existing_dates]
        
        if missing:
            missing_data[ticker] = {
                'first_needed': start_date,
                'missing_dates': missing,
                'count': len(missing)
            }
    
    return missing_data
```

### 3.2 Backfill Script

**Script:** `backfill_user_historical_prices.py`

```python
def backfill_user_historical_prices(user_id, first_holdings_date):
    """
    Backfill historical prices for all stocks user has owned.
    
    Uses yfinance to fetch missing historical data.
    Only fetches data from user's first holdings date forward.
    """
    
    missing_data = identify_missing_market_data(user_id, first_holdings_date)
    
    for ticker, info in missing_data.items():
        print(f"Backfilling {ticker}: {info['count']} missing dates")
        
        # Fetch from yfinance
        stock = yf.Ticker(ticker)
        hist = stock.history(
            start=info['first_needed'],
            end=date.today()
        )
        
        # Insert into database
        for date_idx, row in hist.iterrows():
            market_date = date_idx.date()
            
            # Only insert if missing
            existing = MarketData.query.filter_by(
                ticker=ticker,
                date=market_date
            ).first()
            
            if not existing:
                md = MarketData(
                    ticker=ticker,
                    date=market_date,
                    open_price=row['Open'],
                    close_price=row['Close'],
                    high_price=row['High'],
                    low_price=row['Low'],
                    volume=row['Volume']
                )
                db.session.add(md)
        
        db.session.commit()
        print(f"  ✅ Backfilled {ticker}")
```

---

## 🔄 PHASE 4: REBUILD PORTFOLIO SNAPSHOTS

### 4.1 Snapshot Rebuild Logic

**Purpose:** Create accurate snapshots from first holdings date to today

**Key Points:**
- Only create snapshots for dates when user had holdings
- Use actual market data for each date
- Calculate correct portfolio value based on holdings × prices
- Properly handle same-day buy/sell scenarios

**Script:** `rebuild_user_snapshots.py`

```python
def rebuild_user_snapshots(user_id, first_holdings_date):
    """
    Rebuild portfolio snapshots from first holdings date to today.
    
    Strategy:
    1. Get all transactions to reconstruct holdings over time
    2. For each weekday from first_holdings_date to today:
       - Calculate what stocks user owned at end of that day
       - Get market prices for that day
       - Calculate total portfolio value
       - Create/update snapshot
    """
    
    # Get all transactions
    transactions = Transaction.query.filter_by(user_id=user_id)\
        .order_by(Transaction.timestamp.asc()).all()
    
    # Starting point
    current_date = first_holdings_date
    end_date = date.today()
    
    # Track holdings over time
    holdings = {}  # {ticker: quantity}
    
    while current_date <= end_date:
        if current_date.weekday() >= 5:  # Skip weekends
            current_date += timedelta(days=1)
            continue
        
        # Apply transactions up to end of this day
        for txn in transactions:
            if txn.timestamp.date() <= current_date:
                if txn.type == 'buy':
                    holdings[txn.ticker] = holdings.get(txn.ticker, 0) + txn.quantity
                elif txn.type == 'sell':
                    holdings[txn.ticker] = holdings.get(txn.ticker, 0) - txn.quantity
                    if holdings[txn.ticker] <= 0:
                        del holdings[txn.ticker]
        
        # Calculate portfolio value
        total_value = 0
        all_prices_available = True
        
        for ticker, quantity in holdings.items():
            market_data = MarketData.query.filter_by(
                ticker=ticker,
                date=current_date
            ).first()
            
            if not market_data:
                all_prices_available = False
                print(f"⚠️  Missing market data for {ticker} on {current_date}")
                continue
            
            total_value += quantity * market_data.close_price
        
        # Only create snapshot if we have all prices
        if holdings and all_prices_available:
            # Calculate percentage gain
            if current_date == first_holdings_date:
                percentage_gain = 0.0  # First day is baseline
            else:
                first_snapshot = PortfolioSnapshot.query.filter_by(
                    user_id=user_id,
                    date=first_holdings_date
                ).first()
                
                if first_snapshot:
                    baseline = first_snapshot.total_value
                    percentage_gain = ((total_value - baseline) / baseline) * 100
                else:
                    percentage_gain = 0.0
            
            # Create or update snapshot
            snapshot = PortfolioSnapshot.query.filter_by(
                user_id=user_id,
                date=current_date
            ).first()
            
            if snapshot:
                snapshot.total_value = total_value
                snapshot.percentage_gain = percentage_gain
            else:
                snapshot = PortfolioSnapshot(
                    user_id=user_id,
                    date=current_date,
                    total_value=total_value,
                    percentage_gain=percentage_gain
                )
                db.session.add(snapshot)
        
        current_date += timedelta(days=1)
    
    db.session.commit()
    print(f"✅ Rebuilt snapshots for user {user_id}")
```

---

## 📈 PHASE 5: FIX CHART DISPLAY

### 5.1 Update Chart Data Generation

**File:** `leaderboard_utils.py`

**Current Issue:** Charts show lines back to dates before user had assets

**Fix:**

```python
def get_chart_data(user_id, period='1M'):
    """
    Generate chart data, handling dates before user started trading.
    
    NEW BEHAVIOR:
    - If period goes back further than user's first holdings date,
      only show data from first holdings date forward
    - Chart will have empty space (no line) before user started
    - Labels start from first holdings date
    """
    
    # Get user's first holdings date
    user = User.query.get(user_id)
    first_holdings = find_first_real_holdings_date(user_id)
    
    if not first_holdings:
        return None  # User never had holdings
    
    # Calculate date range for chart
    end_date = datetime.now().date()
    
    if period == '5D':
        start_date = end_date - timedelta(days=5)
    elif period == '1M':
        start_date = end_date - timedelta(days=30)
    elif period == '3M':
        start_date = end_date - timedelta(days=90)
    elif period == '1Y':
        start_date = end_date - timedelta(days=365)
    else:  # ALL
        start_date = first_holdings  # Start from first holdings
    
    # Don't go back before first holdings date
    if start_date < first_holdings:
        start_date = first_holdings
    
    # Get snapshots
    snapshots = PortfolioSnapshot.query.filter(
        PortfolioSnapshot.user_id == user_id,
        PortfolioSnapshot.date >= start_date,
        PortfolioSnapshot.date <= end_date
    ).order_by(PortfolioSnapshot.date.asc()).all()
    
    # Filter out weekends (keep existing logic)
    trading_day_snapshots = [s for s in snapshots if s.total_value > 0]
    
    if not trading_day_snapshots:
        return None
    
    # Generate chart data
    labels = [s.date.strftime('%Y-%m-%d') for s in trading_day_snapshots]
    values = [float(s.total_value) for s in trading_day_snapshots]
    
    return {
        'labels': labels,
        'datasets': [{
            'label': 'Portfolio Value',
            'data': values,
            'borderColor': 'rgb(75, 192, 192)',
            'backgroundColor': 'rgba(75, 192, 192, 0.2)',
            'tension': 0.1
        }],
        'period': period,
        'user_id': user_id,
        'first_holdings_date': first_holdings.isoformat(),
        'note': f'Data starts from {first_holdings} (first holdings date)'
    }
```

### 5.2 Chart Frontend Updates

**Show message when data range is limited:**

```javascript
// In chart rendering code
if (chartData.first_holdings_date) {
    const note = document.createElement('div');
    note.className = 'chart-note';
    note.innerHTML = `📊 Portfolio history starts ${chartData.first_holdings_date}`;
    chartContainer.appendChild(note);
}
```

---

## 🎯 PHASE 6: EXECUTION PLAN

### Step-by-Step Execution

**DO THIS IN ORDER:**

1. **Assessment** (1 hour)
   - ✅ Deploy enhanced debug tool (DONE!)
   - ⏳ Create `/admin/assess-portfolio-data` endpoint
   - ⏳ Run assessment for all users
   - ⏳ Review results and confirm approach

2. **Backup Current State** (30 min)
   - ⏳ Export all snapshots to JSON backup
   - ⏳ Export all transactions to JSON backup
   - ⏳ Store backups in `backups/` directory

3. **Delete Corrupted Snapshots** (1 hour)
   - ⏳ DRY RUN for each user
   - ⏳ Review what will be deleted
   - ⏳ Execute deletion (with confirmation)
   - ⏳ Verify deletions

4. **Backfill Historical Prices** (2-3 hours)
   - ⏳ Identify missing market data
   - ⏳ Fetch from yfinance
   - ⏳ Bulk insert into database
   - ⏳ Verify coverage

5. **Rebuild Snapshots** (2-3 hours)
   - ⏳ Rebuild each user's snapshots
   - ⏳ Verify values match holdings × prices
   - ⏳ Check percentage gains make sense
   - ⏳ Compare new vs old snapshots

6. **Fix Chart Display** (1 hour)
   - ⏳ Update `leaderboard_utils.py`
   - ⏳ Test charts for each period
   - ⏳ Verify empty space before first holdings
   - ⏳ Check gains calculations

7. **Validation** (1 hour)
   - ⏳ Spot-check each user's timeline
   - ⏳ Verify charts look correct
   - ⏳ Confirm leaderboard rankings
   - ⏳ Test edge cases (same-day buy/sell)

**Total Time Estimate: 9-11 hours**

---

## 🧪 TESTING CHECKLIST

Before deployment:
- [ ] DRY RUN all deletions
- [ ] Backup all data
- [ ] Test on one user first (testing2 - has no real holdings)
- [ ] Verify snapshots match manual calculations
- [ ] Check charts display correctly
- [ ] Confirm leaderboard unchanged (if assets unchanged)
- [ ] Test all chart periods (5D, 1M, 3M, 1Y, ALL)
- [ ] Verify weekend filtering still works
- [ ] Check transaction timeline in debug tool

---

## 🚨 RISKS & MITIGATION

**Risk 1:** Delete too many snapshots
- **Mitigation:** DRY RUN first, review carefully, backup before deletion

**Risk 2:** Missing historical market data
- **Mitigation:** Use multiple data sources, handle gaps gracefully

**Risk 3:** Incorrect portfolio value calculations
- **Mitigation:** Compare against manual calculations, spot-check

**Risk 4:** Same-day buy/sell scenarios
- **Mitigation:** Use end-of-day snapshot, ensure transactions applied in order

**Risk 5:** Timezone issues with transaction timestamps
- **Mitigation:** Convert all to same timezone, use `.date()` for snapshots

---

## 📝 NEXT IMMEDIATE STEPS

1. **Review enhanced debug tool** (deployed now)
   - Look at witty-raven timeline
   - Identify first REAL holdings date
   - Count corrupted snapshot days

2. **Create assessment endpoint**
   - Build `/admin/assess-portfolio-data`
   - Generate report for all users
   - Confirm cleanup targets

3. **Build deletion script**
   - Create DRY RUN mode
   - Add backup functionality
   - Test on testing2 user first

---

## ✅ SUCCESS CRITERIA

We'll know cleanup is successful when:
- ✅ No snapshots exist before user's first holdings date
- ✅ All snapshots match holdings × market prices
- ✅ Charts show no line before user started trading
- ✅ Percentage gains start at 0% on first holdings date
- ✅ Leaderboard rankings are accurate
- ✅ Debug tool shows no corruption warnings
- ✅ All market data is available for user holdings
- ✅ Weekend filtering still works correctly
