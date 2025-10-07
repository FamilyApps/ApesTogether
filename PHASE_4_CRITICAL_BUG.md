# 🚨 CRITICAL BUG: Historical Snapshots Using Current Prices

**Date Discovered:** October 6, 2025 (11 PM)
**Status:** CONFIRMED - All 374 snapshots are invalid
**Priority:** HIGH - Must fix before charts/performance calculations are accurate

---

## 🔍 **The Bug**

### **What's Wrong:**
The `calculate_portfolio_value()` function in `portfolio_performance.py` accepts a `target_date` parameter but **IGNORES IT** when fetching stock prices.

**Code Location:** `portfolio_performance.py`, lines 137-189

```python
def calculate_portfolio_value(self, user_id: int, target_date: date = None) -> float:
    """Calculate total portfolio value for a user on a specific date"""
    if target_date is None:
        target_date = get_market_date()
    
    # ... gets holdings ...
    
    for ticker, quantity in holdings.items():
        # ❌ BUG: Always gets CURRENT price, ignores target_date!
        stock_data = self.get_stock_data(ticker)
        price = stock_data['price']  # Current price, not historical!
```

### **Impact:**
- **374 snapshots** created with identical values
- June 19, 2025 snapshot uses October 6, 2025 prices
- All historical data shows 0% change (impossible!)
- Charts will show flat lines
- Performance calculations are meaningless

### **Proof:**
Testing2 user inspection shows:
- 73 snapshots from June 19 → Oct 6 (109 days)
- ALL have value: $5,254.56 (identical)
- 72/73 days with 0% change
- Total return: 0.0%

---

## ✅ **What We Accomplished Tonight**

### **Phase 0: Foundation (COMPLETE)**
- ✅ Added `max_cash_deployed` and `cash_proceeds` to User model
- ✅ Added cash tracking fields to PortfolioSnapshot model
- ✅ Backfilled all 5 users with correct cash tracking data
- ✅ Created 34 transaction records

### **Phase 1: Implementation (COMPLETE)**
- ✅ Updated snapshot creation to populate cash fields
- ✅ Verified Modified Dietz calculation works
- ✅ Created comprehensive test routes

### **Phase 2: Data Cleanup (COMPLETE)**
- ✅ Identified first transaction dates for all users
- ✅ Deleted 1,430 corrupted snapshots (89% of data!)
- ✅ Database now clean of pre-transaction snapshots

### **Phase 3: Rebuild Existing (COMPLETE - BUT FLAWED)**
- ✅ Rebuilt 172 existing snapshots with cash tracking
- ❌ All using current prices (bug not yet known)

### **Phase 4: Historical Backfill (COMPLETE - BUT FLAWED)**
- ✅ Created beautiful dashboard interface
- ✅ Backfilled 202 missing snapshots:
  - testing2: 53 snapshots
  - testing3: 53 snapshots
  - wild-bronco: 53 snapshots
  - wise-buffalo: 43 snapshots
  - witty-raven: 0 (already complete)
- ✅ Rebuilt all 374 snapshots with cash tracking
- ❌ ALL using current prices (bug discovered at end)

### **Phase 5: Bug Discovery (COMPLETE)**
- ✅ Created inspection route to analyze snapshot quality
- ✅ Confirmed all snapshots use current prices
- ✅ Identified root cause in `calculate_portfolio_value()`

---

## 🔧 **The Fix Needed (Tomorrow)**

### **Phase 5: Historical Price Integration**

#### **1. Fetch Historical Prices**
Update `calculate_portfolio_value()` to:
- Accept and USE the `target_date` parameter
- Fetch historical prices for that specific date
- Use Alpha Vantage TIME_SERIES_DAILY API
- Cache historical prices in database

#### **2. Historical Price Storage**
Create `MarketData` table usage (already exists in models.py):
```python
class MarketData(db.Model):
    ticker = db.Column(db.String(20), nullable=False)
    date = db.Column(db.Date, nullable=False)
    close_price = db.Column(db.Float, nullable=False)
```

Store historical prices so we don't re-fetch.

#### **3. Delete Corrupted Snapshots**
Delete all 374 snapshots that use current prices:
```sql
DELETE FROM portfolio_snapshot WHERE date < '2025-10-06';
```

#### **4. Re-Backfill With Historical Prices**
- Run Phase 4 dashboard again
- Backfill 202 snapshots (June-Sept)
- Rebuild 172 snapshots (Sept-Oct)
- Total: 374 snapshots with REAL historical prices

#### **5. Verification**
Use inspection route to verify:
- Portfolio values vary day-to-day
- Realistic daily percentage changes
- No flat periods
- Accurate performance tracking

---

## 📊 **Current Database State**

### **Snapshots:**
- **Total:** 374 (ALL INVALID - using current prices)
- **To Delete:** All 374
- **To Recreate:** 374 with historical prices

### **Users:**
| User | Snapshots | Date Range | Status |
|------|-----------|------------|--------|
| testing2 | 73 | June 19 → Oct 6 | ❌ Invalid |
| testing3 | 73 | June 19 → Oct 6 | ❌ Invalid |
| wild-bronco | 72 | June 19 → Oct 6 | ❌ Invalid |
| wise-buffalo | 78 | June 13 → Oct 6 | ❌ Invalid |
| witty-raven | 78 | June 19 → Oct 6 | ❌ Invalid |

---

## 🎯 **Tomorrow's Action Plan**

### **Step 1: Update Price Fetching**
File: `portfolio_performance.py`
- Modify `calculate_portfolio_value()` to use `target_date`
- Add `get_historical_price(ticker, date)` method
- Integrate with Alpha Vantage TIME_SERIES_DAILY
- Cache results in `MarketData` table

### **Step 2: Delete Invalid Snapshots**
Create route:
```
/admin/phase5/delete-invalid-snapshots?execute=true
```

### **Step 3: Re-Backfill Everything**
Use Phase 4 dashboard:
- Backfill each user (now with historical prices)
- Verify with inspection route
- Confirm realistic daily variations

### **Step 4: Test & Verify**
- Run Modified Dietz calculations
- Check charts show realistic data
- Verify performance calculations

---

## 📝 **Technical Notes**

### **Alpha Vantage Historical Price API:**
```
https://www.alphavantage.co/query?
  function=TIME_SERIES_DAILY
  &symbol=NVDA
  &apikey=YOUR_API_KEY
```

Returns up to 100 days of historical close prices.

### **Rate Limits:**
- Free tier: 25 requests/day
- Need to cache aggressively to avoid hitting limits
- Consider upgrading if needed

### **MarketData Table:**
Already exists, just needs to be populated:
- Unique constraint on (ticker, date)
- Store close_price for each ticker/date
- Check cache before API call

---

## 🚀 **Expected Outcome**

After tomorrow's fix:
- ✅ All snapshots use accurate historical prices
- ✅ Portfolio values show realistic daily variation
- ✅ Charts display meaningful performance trends
- ✅ Modified Dietz calculations accurate
- ✅ Performance tracking works correctly

---

## 📂 **Files to Modify Tomorrow**

1. `portfolio_performance.py` - Update price fetching
2. `admin_phase_5_routes.py` - Create deletion/re-backfill routes
3. Existing Phase 4 dashboard - Reuse for re-backfill

---

## ⏰ **Estimated Time: 30-60 minutes**

- Update code: 20 min
- Delete snapshots: 2 min
- Re-backfill: 10-15 min
- Testing: 10-20 min

---

**Status:** Ready to resume tomorrow with Option B (Proper Fix)
**Next Session:** Start with updating `calculate_portfolio_value()` for historical prices
