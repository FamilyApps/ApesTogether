# 📋 COMPLETE PORTFOLIO CLEANUP & CASH TRACKING TASK LIST

**Last Updated:** October 5, 2025

---

## 🎯 OVERVIEW

This project fixes fundamental data integrity issues and implements proper cash tracking for accurate performance calculations.

**Key Problems Being Solved:**
1. ❌ Missing transaction records (stocks added without transactions)
2. ❌ No cash balance tracking (day traders show $0 portfolio)
3. ❌ Corrupted snapshots (data before users started trading)
4. ❌ Incorrect performance calculations (ignores cash flows)
5. ❌ Weekend data showing $0 values

---

## 🚀 PHASE 0: Cash Tracking Implementation (CRITICAL - IN PROGRESS)

### ✅ Step 0.1: Create Missing Transaction Records
**Status:** READY TO RUN  
**Script:** `create_initial_transactions.py`

**Purpose:** Create transaction records for stocks that were added during account setup without proper transaction logging.

**Commands:**
```bash
# Dry run (preview what will be created):
python create_initial_transactions.py

# Execute (actually create transactions):
python create_initial_transactions.py --execute
```

**What It Does:**
- Scans all users for stocks without matching transactions
- Creates Transaction records with `type='initial'`
- Uses `Stock.purchase_date` as timestamp (or 4 PM EST if time is midnight)
- Uses `Stock.purchase_price` as transaction price
- Enables historical cash tracking calculations

**Expected Outcome:** witty-raven and all users will have complete transaction history

---

### ✅ Step 0.2: Add Cash Tracking to User Model
**Status:** READY TO RUN  
**Migration:** `migrations/versions/20251005_add_cash_tracking.py`

**Purpose:** Add `max_cash_deployed` and `cash_proceeds` fields to User table.

**SQL Changes:**
```sql
ALTER TABLE user ADD COLUMN max_cash_deployed FLOAT DEFAULT 0.0 NOT NULL;
ALTER TABLE user ADD COLUMN cash_proceeds FLOAT DEFAULT 0.0 NOT NULL;
```

**Fields Explained:**
- `max_cash_deployed`: Cumulative capital user has ever deployed (never decreases)
- `cash_proceeds`: Uninvested cash from stock sales (waiting to be redeployed)

**Command:**
```bash
# Run migration (exact command depends on your migration tool)
# Typically: flask db upgrade or alembic upgrade head
```

---

### ✅ Step 0.3: Backfill Cash Tracking for Existing Users
**Status:** READY TO RUN (after Step 0.2)  
**Script:** `backfill_cash_tracking.py`

**Purpose:** Replay all transactions chronologically to calculate historical cash state.

**Commands:**
```bash
# Dry run (preview calculations):
python backfill_cash_tracking.py

# Execute (update database):
python backfill_cash_tracking.py --execute
```

**What It Does:**
- For each user, gets all transactions in chronological order
- Replays transactions to calculate max_cash_deployed and cash_proceeds
- Updates User records with current cash state
- Shows performance calculations

**Example Output:**
```
witty-raven: max_cash_deployed=$7,279.22, cash_proceeds=$0.00
Portfolio value: $7,642.16
Performance: +5.0%
```

---

### ✅ Step 0.4: Add Cash Tracking to PortfolioSnapshot Model
**Status:** COMPLETED  
**Migration:** `migrations/versions/20251005_add_snapshot_cash_fields.py`

**Purpose:** Add cash tracking fields to snapshots for Modified Dietz calculations.

**SQL Changes:**
```sql
ALTER TABLE portfolio_snapshot ADD COLUMN stock_value FLOAT;
ALTER TABLE portfolio_snapshot ADD COLUMN cash_proceeds FLOAT;
ALTER TABLE portfolio_snapshot ADD COLUMN max_cash_deployed FLOAT;
```

**Why Critical:**
To calculate performance over a period (e.g., 1M), we need:
- **Beginning snapshot:** stock_value, cash_proceeds, max_cash_deployed on day 1
- **Ending snapshot:** stock_value, cash_proceeds, max_cash_deployed on day 30
- **Change in max_cash_deployed** = cash deposits during period

**Modified Dietz Example:**
```
Aug 1: stock=$10, cash=$5, deployed=$10 → Portfolio=$15
Sep 1: stock=$15, cash=$10, deployed=$15 → Portfolio=$25

Capital deployed during month: $5
Return = ($25 - $15 - $5) / ($15 + 0.5*$5) = 28.6% ✅

If we ignored cash flow: ($25 - $15) / $15 = 66.7% ❌ WRONG!
```

**Command:**
```bash
# Run migration
```

---

### ⚠️ Step 0.5: Update Snapshot Creation Logic
**Status:** TODO  
**Files:** `portfolio_performance.py`, `cash_tracking.py`

**Purpose:** Update `create_daily_snapshot()` to save cash tracking fields.

**Current Code (WRONG):**
```python
def create_daily_snapshot(user_id, target_date=None):
    portfolio_value = calculate_portfolio_value(user_id, target_date)
    
    snapshot = PortfolioSnapshot(
        user_id=user_id,
        date=target_date,
        total_value=portfolio_value,  # ❌ Only total_value
        cash_flow=0
    )
```

**New Code (CORRECT):**
```python
def create_daily_snapshot(user_id, target_date=None):
    from cash_tracking import calculate_portfolio_value_with_cash
    
    # Get detailed breakdown
    portfolio = calculate_portfolio_value_with_cash(user_id, target_date)
    user = User.query.get(user_id)
    
    snapshot = PortfolioSnapshot(
        user_id=user_id,
        date=target_date,
        stock_value=portfolio['stock_value'],  # ✅ Stock value only
        cash_proceeds=portfolio['cash_proceeds'],  # ✅ Cash from sales
        max_cash_deployed=user.max_cash_deployed,  # ✅ Cumulative deployment
        total_value=portfolio['total_value'],  # ✅ Total (stocks + cash)
        cash_flow=0  # Legacy field
    )
    
    db.session.add(snapshot)
    db.session.commit()
```

**Implementation Steps:**
1. Update `portfolio_performance.py::create_daily_snapshot()`
2. Update market-close cron endpoint to use new logic
3. Test snapshot creation

---

### ⚠️ Step 0.6: Implement Modified Dietz Performance Calculation
**Status:** TODO  
**File:** `portfolio_performance.py` (new function)

**Purpose:** Calculate time-weighted returns accounting for cash flows.

**Implementation:**
```python
def calculate_period_performance_modified_dietz(user_id, start_date, end_date):
    """
    Calculate performance using Modified Dietz method.
    
    Treats increases in max_cash_deployed as cash deposits.
    
    Formula: Return = (V_end - V_start - CF) / (V_start + W * CF)
    
    Where:
    - V_start = beginning portfolio value
    - V_end = ending portfolio value
    - CF = net cash flow (deposits - withdrawals)
    - W = time-weighted factor for cash flows
    """
    
    # Get all snapshots in period (sorted by date)
    snapshots = PortfolioSnapshot.query.filter(
        PortfolioSnapshot.user_id == user_id,
        PortfolioSnapshot.date >= start_date,
        PortfolioSnapshot.date <= end_date
    ).order_by(PortfolioSnapshot.date).all()
    
    if len(snapshots) < 2:
        return 0.0
    
    start_snapshot = snapshots[0]
    end_snapshot = snapshots[-1]
    
    # Beginning and ending portfolio values
    V_start = start_snapshot.total_value
    V_end = end_snapshot.total_value
    
    # Calculate net cash flow and weighted cash flow
    net_cash_flow = 0.0
    weighted_cash_flow = 0.0
    
    total_days = (end_date - start_date).days
    
    for i in range(len(snapshots) - 1):
        current_snap = snapshots[i]
        next_snap = snapshots[i + 1]
        
        # Check if max_cash_deployed increased
        deployment_increase = next_snap.max_cash_deployed - current_snap.max_cash_deployed
        
        if deployment_increase > 0:
            # This is a "deposit"
            net_cash_flow += deployment_increase
            
            # Calculate weight (proportion of period remaining after deposit)
            days_remaining = (end_date - next_snap.date).days
            weight = days_remaining / total_days if total_days > 0 else 0
            
            weighted_cash_flow += deployment_increase * weight
    
    # Modified Dietz formula
    denominator = V_start + weighted_cash_flow
    
    if denominator == 0:
        return 0.0
    
    numerator = V_end - V_start - net_cash_flow
    performance = (numerator / denominator) * 100
    
    return performance
```

**Testing:**
```python
# Example test case
user_id = 1
start_date = date(2025, 8, 1)  # Aug 1
end_date = date(2025, 9, 1)    # Sep 1

# Snapshots:
# Aug 1: stock=$10, cash=$5, deployed=$10 → total=$15
# Aug 15: stock=$12, cash=$5, deployed=$15 → total=$17 (deployed $5 more)
# Sep 1: stock=$15, cash=$10, deployed=$15 → total=$25

performance = calculate_period_performance_modified_dietz(user_id, start_date, end_date)
# Expected: ~28.6% (accounts for $5 deposit on Aug 15)
```

---

### ⚠️ Step 0.7: Update Chart API to Use Modified Dietz
**Status:** TODO  
**File:** `api/index.py`

**Purpose:** Update `/api/portfolio/performance/<period>` endpoint to use Modified Dietz.

**Changes Needed:**
```python
@app.route('/api/portfolio/performance/<period>')
def get_portfolio_performance(period):
    # ... existing date range calculation ...
    
    # OLD: Simple return calculation
    # performance = (end_value - start_value) / start_value * 100
    
    # NEW: Modified Dietz
    from portfolio_performance import calculate_period_performance_modified_dietz
    performance = calculate_period_performance_modified_dietz(
        user_id=current_user.id,
        start_date=period_start,
        end_date=today
    )
    
    # ... rest of response ...
```

---

## 📊 PHASE 1: Assessment & Discovery

### ⚠️ Step 1.1: Find First Real Holdings Date
**Status:** TODO  
**Script:** `find_first_holdings_dates.py` (needs creation)

**Purpose:** Identify when each user actually started trading (not corrupted backfill dates).

**Logic:**
```python
def find_first_real_holdings_date(user_id):
    """
    Find the earliest date when user actually owned stocks.
    
    Methods (in priority order):
    1. First transaction date (if transactions exist)
    2. Earliest Stock.purchase_date
    3. First PortfolioSnapshot with value > 0
    """
    
    # Method 1: First transaction
    first_txn = Transaction.query.filter_by(user_id=user_id)\
        .order_by(Transaction.timestamp).first()
    if first_txn:
        return first_txn.timestamp.date()
    
    # Method 2: First stock purchase
    first_stock = Stock.query.filter_by(user_id=user_id)\
        .order_by(Stock.purchase_date).first()
    if first_stock:
        return first_stock.purchase_date.date()
    
    # Method 3: First non-zero snapshot
    first_snapshot = PortfolioSnapshot.query.filter(
        PortfolioSnapshot.user_id == user_id,
        PortfolioSnapshot.total_value > 0
    ).order_by(PortfolioSnapshot.date).first()
    if first_snapshot:
        return first_snapshot.date
    
    return None
```

---

### ⚠️ Step 1.2: Audit Corrupted Snapshots
**Status:** TODO  
**Tool:** `/admin/debug-portfolio-timeline` endpoint (already exists)

**Purpose:** Identify snapshots that exist before user's first holdings date.

**Process:**
1. For each user, find first_holdings_date
2. Query snapshots WHERE date < first_holdings_date
3. Flag as corrupted
4. Generate report

**Expected Findings:**
```
witty-raven:
  First holdings: 2025-09-02
  Corrupted snapshots: 71 (from 2025-05-26 to 2025-09-01)
  Snapshot values: $7,279.22 (incorrect baseline)
```

---

## 🗑️ PHASE 2: Delete Corrupted Data

### ⚠️ Step 2.1: Delete Pre-First-Holdings Snapshots
**Status:** TODO  
**Script:** `delete_corrupted_snapshots.py` (needs creation)

**Purpose:** Remove snapshots created before user started trading.

**Logic:**
```python
def delete_corrupted_snapshots(user_id, first_holdings_date, dry_run=True):
    """Delete snapshots before first holdings date"""
    
    corrupted = PortfolioSnapshot.query.filter(
        PortfolioSnapshot.user_id == user_id,
        PortfolioSnapshot.date < first_holdings_date
    ).all()
    
    print(f"Found {len(corrupted)} corrupted snapshots for user {user_id}")
    
    if not dry_run:
        for snap in corrupted:
            db.session.delete(snap)
        db.session.commit()
        print(f"Deleted {len(corrupted)} snapshots")
    else:
        print("DRY RUN - no changes made")
    
    return len(corrupted)
```

**Safety:**
- Dry run by default
- Requires explicit --execute flag
- Logs all deletions
- Invalidates chart cache

---

### ⚠️ Step 2.2: Verify Deletion
**Status:** TODO after Step 2.1

**Verification:**
```python
# Check that no snapshots exist before first holdings date
for user in User.query.all():
    first_date = find_first_real_holdings_date(user.id)
    if first_date:
        pre_snapshots = PortfolioSnapshot.query.filter(
            PortfolioSnapshot.user_id == user.id,
            PortfolioSnapshot.date < first_date
        ).count()
        
        assert pre_snapshots == 0, f"User {user.username} still has {pre_snapshots} pre-holdings snapshots!"
```

---

## 📈 PHASE 3: Backfill Historical Data

### ⚠️ Step 3.1: Backfill Market Data
**Status:** TODO  
**Script:** `backfill_historical_prices.py` (already exists, may need updates)

**Purpose:** Fill gaps in MarketData table (stock closing prices).

**Process:**
1. Get all unique tickers from Stock and Transaction tables
2. For each ticker, find date range needed
3. Check for gaps in MarketData
4. Fetch missing data from Alpha Vantage or yfinance
5. Populate MarketData table

**Command:**
```bash
python backfill_historical_prices.py
```

---

### ⚠️ Step 3.2: Backfill S&P 500 Data
**Status:** TODO  
**Script:** `populate_sp500_data.py` (already exists)

**Purpose:** Fill gaps in SPY (S&P 500 proxy) data.

**Process:**
1. Find earliest first_holdings_date across all users
2. Fetch SPY daily data from that date to today
3. Populate MarketData table with SPY data

**Command:**
```bash
python populate_sp500_data.py
```

---

## 🔄 PHASE 4: Rebuild Snapshots with Cash Tracking

### ⚠️ Step 4.1: Rebuild All Snapshots
**Status:** TODO  
**Script:** `rebuild_snapshots_with_cash.py` (needs creation)

**Purpose:** Recreate all snapshots with complete cash tracking data.

**Logic:**
```python
def rebuild_snapshots_for_user(user_id, first_holdings_date):
    """
    Rebuild snapshots from first holdings date to today.
    
    For each trading day:
    1. Calculate stock_value at market close
    2. Calculate cash_proceeds as of that date
    3. Get max_cash_deployed as of that date
    4. Create PortfolioSnapshot with all fields
    """
    
    from cash_tracking import calculate_cash_proceeds_as_of_date
    from portfolio_performance import calculate_stock_value
    
    current_date = first_holdings_date
    today = date.today()
    
    while current_date <= today:
        # Skip weekends
        if current_date.weekday() >= 5:
            current_date += timedelta(days=1)
            continue
        
        # Calculate values as of this date
        stock_value = calculate_stock_value(user_id, current_date)
        cash_proceeds = calculate_cash_proceeds_as_of_date(user_id, current_date)
        max_deployed = calculate_max_deployed_as_of_date(user_id, current_date)
        
        total_value = stock_value + cash_proceeds
        
        # Create or update snapshot
        snapshot = PortfolioSnapshot.query.filter_by(
            user_id=user_id,
            date=current_date
        ).first()
        
        if snapshot:
            snapshot.stock_value = stock_value
            snapshot.cash_proceeds = cash_proceeds
            snapshot.max_cash_deployed = max_deployed
            snapshot.total_value = total_value
        else:
            snapshot = PortfolioSnapshot(
                user_id=user_id,
                date=current_date,
                stock_value=stock_value,
                cash_proceeds=cash_proceeds,
                max_cash_deployed=max_deployed,
                total_value=total_value
            )
            db.session.add(snapshot)
        
        current_date += timedelta(days=1)
    
    db.session.commit()
```

**Command:**
```bash
python rebuild_snapshots_with_cash.py --execute
```

---

### ⚠️ Step 4.2: Verify Rebuilt Snapshots
**Status:** TODO after Step 4.1

**Verification Checks:**
1. **No gaps:** Every trading day has a snapshot
2. **All fields populated:** stock_value, cash_proceeds, max_cash_deployed not NULL
3. **Math checks:** total_value = stock_value + cash_proceeds
4. **No pre-holdings snapshots:** All snapshots >= first_holdings_date
5. **Weekend filter:** No Saturday/Sunday snapshots

---

## 📉 PHASE 5: Fix Chart Display

### ⚠️ Step 5.1: Update Chart API
**Status:** Partially done (needs Modified Dietz integration)

**Files:** `api/index.py`, `portfolio_performance.py`

**Changes:**
- Use Modified Dietz for performance calculations
- Filter out weekend data
- Return proper date labels

---

### ⚠️ Step 5.2: Test All Chart Periods
**Status:** TODO after Step 5.1

**Test Matrix:**
| Period | Expected Data Points | Performance Calc | Status |
|--------|---------------------|------------------|--------|
| 1D | ~14 (intraday) | Intraday snapshots | TODO |
| 5D | ~70 (intraday) | Intraday snapshots | TODO |
| 1M | ~22 (trading days) | Modified Dietz | TODO |
| 3M | ~65 (trading days) | Modified Dietz | TODO |
| YTD | ~180 (trading days) | Modified Dietz | TODO |
| 1Y | ~252 (trading days) | Modified Dietz | TODO |
| 5Y | ~1260 (trading days) | Modified Dietz | TODO |
| MAX | All history | Modified Dietz | TODO |

---

## 🎯 PHASE 6: Final Touches

### ⚠️ Step 6.1: Weekend Display Fix
**Status:** Partially done

**Changes:**
- Backend filters weekends from data
- Frontend shows only weekdays on x-axis
- Tooltips show proper dates

---

### ⚠️ Step 6.2: Default Chart Period
**Status:** TODO

**Change:** Default from 1Y to 1D or 5D for better UX

---

### ⚠️ Step 6.3: Leaderboard Integration
**Status:** TODO

**Updates:**
- Use Modified Dietz for leaderboard rankings
- Ensure all users show correct performance %
- Fix 0% performance bugs

---

## 📝 EXECUTION ORDER

### **IMMEDIATE (Today):**
1. ✅ Run `create_initial_transactions.py --execute`
2. ✅ Run migration for User cash tracking fields
3. ✅ Run `backfill_cash_tracking.py --execute`
4. ✅ Run migration for PortfolioSnapshot cash fields

### **SHORT-TERM (This Week):**
5. ⚠️ Update `create_daily_snapshot()` to save cash fields
6. ⚠️ Implement Modified Dietz calculation
7. ⚠️ Update chart API to use Modified Dietz
8. ⚠️ Test on development

### **MEDIUM-TERM (Next Week):**
9. ⚠️ Create `find_first_holdings_dates.py`
10. ⚠️ Create `delete_corrupted_snapshots.py`
11. ⚠️ Run corruption cleanup
12. ⚠️ Backfill market data gaps

### **LONG-TERM (Following Week):**
13. ⚠️ Create `rebuild_snapshots_with_cash.py`
14. ⚠️ Rebuild all snapshots
15. ⚠️ Comprehensive testing
16. ⚠️ Deploy to production

---

## ✅ COMPLETION CRITERIA

**Phase 0 Complete When:**
- [x] All users have transaction records
- [x] User table has max_cash_deployed, cash_proceeds
- [x] Users' cash tracking is backfilled
- [x] PortfolioSnapshot model has cash fields
- [ ] Snapshots are created with cash tracking
- [ ] Modified Dietz is implemented
- [ ] Charts use Modified Dietz

**Phase 1-6 Complete When:**
- [ ] No corrupted snapshots exist
- [ ] All gaps in market data filled
- [ ] All snapshots have cash tracking fields
- [ ] All chart periods work correctly
- [ ] Performance calculations match expectations
- [ ] Leaderboard shows correct rankings
- [ ] Weekend data handled properly

---

## 📊 SUCCESS METRICS

**Data Quality:**
- 100% of stocks have matching transactions
- 0 snapshots before first holdings date
- 0 gaps in trading day snapshots
- 100% of snapshots have cash tracking fields

**Performance Accuracy:**
- Day traders show correct portfolio values (not $0)
- 1M performance accounts for mid-month deposits
- All users show on leaderboard (not just 1)
- Performance % matches manual calculations

**User Experience:**
- Charts load without errors
- No $0 weekends displayed
- Smooth business-day progression
- Accurate gain/loss percentages

---

## 🚨 CRITICAL NOTES

1. **Modified Dietz is Essential:** Without it, performance calculations are wrong when users deploy new capital mid-period.

2. **Cash Tracking Must Be in Snapshots:** We can't recalculate historical cash states without snapshots because we need max_cash_deployed at specific points in time.

3. **Transaction History is Foundation:** Everything depends on having complete transaction records. Step 0.1 must succeed.

4. **Order Matters:** Can't backfill cash tracking without transactions. Can't rebuild snapshots without cash tracking.

5. **Test Thoroughly:** Use witty-raven as primary test case. Verify math by hand before deploying.

---

**Status Legend:**
- ✅ Complete and tested
- ⚠️ TODO / Not started
- 🔄 In progress
- ❌ Blocked (waiting on dependency)
