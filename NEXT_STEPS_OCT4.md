# Next Steps - October 4, 2025

**Current Time:** 11:47 AM ET  
**Status:** 3 fixes deployed, 2 investigations needed

---

## ✅ **COMPLETED TODAY**

1. **1D Chart Date Filter** - Exact date query implemented (test Monday)
2. **Navigation Menu Logic** - Fixed logged in/out states
3. **Register Page OAuth** - Added Apple & Google sign-up buttons
4. **5D Chart X-Axis Labels** - Fixed "029" → "Sep 29" format
5. **5D Chart Gap Lines** - Segment styling deployed (awaiting test)

---

## 🔍 **INVESTIGATION #1: Sept 2-10 Baseline Anomaly**

### **Problem:**
- Witty-raven's portfolio value dropped ~7% on Sept 2-10
- This creates artificially low 1M baseline
- Current 1M gain: **14.56%** (math is correct, but baseline is skewed)
- **Impact:** Inflates leaderboard rankings

### **Investigation Script Created:**
`investigate_sept_snapshots.py`

### **What It Will Check:**
1. **Snapshot values** for Sept 2-11
2. **Holdings details** (which stocks, how many shares)
3. **Transactions** during this period (buys/sells)
4. **Market data availability** for each stock
5. **API fetch success** for asset pricing

### **How to Run:**
```bash
# Local (if you have DB access):
python investigate_sept_snapshots.py

# Or deploy to Vercel and run via admin endpoint
```

### **Expected Output:**
- Daily snapshot values showing the drop
- Holdings composition (which stocks were held)
- Whether market data was missing (API failures)
- Transaction history (did user sell stocks?)

### **Possible Root Causes:**
1. **Missing market data** - API didn't fetch prices for certain stocks on Sept 2-10
2. **Portfolio was actually reset** - User started fresh on Sept 3
3. **Data entry issue** - Snapshots created with wrong values
4. **Asset sale** - User sold stocks creating temporary low value

---

## 🔍 **INVESTIGATION #2: 5D Chart Gap Lines**

### **Problem:**
Long diagonal lines connecting across overnight/weekend gaps

### **Fix Attempted:**
Segment styling to make lines transparent when gap > 2 hours

### **Grok Prompt Created:**
`GROK_PROMPT_5D_GAP_LINES.md`

### **Files to Send to Grok:**
1. **`GROK_PROMPT_5D_GAP_LINES.md`** ← Start here (main prompt)
2. **`templates/dashboard.html`** - Lines 602-730 (Chart.js config)
3. **Screenshot** - Your 5D chart showing the gap lines
4. **Console log** (optional) - If segment callback has any errors

### **Questions for Grok:**
1. Is segment styling approach correct?
2. Why might it not be working?
3. Backend (null values) vs frontend (segment) - which is better?
4. Best practice for market hours charts?

---

## 📊 **CLARIFICATION: Modified Dietz vs Chart Calculation**

### **Card Header ("Your Portfolio" %):**
```python
# Line 826 in portfolio_performance.py
portfolio_return = self.calculate_modified_dietz_return(user_id, start_date, end_date)
```
- Uses **Modified Dietz** method
- **Accounts for cash flows** (deposits, withdrawals, buys, sells)
- Returns: `14.56%` for 1M

### **Chart Data Points:**
```python
# Lines 867-899 in portfolio_performance.py
portfolio_pct = ((portfolio_snapshot.total_value - start_portfolio_value) / start_portfolio_value) * 100
```
- Uses **simple percentage change** from first snapshot
- **Does NOT account for cash flows**
- Returns: Same data points that end at `14.56%`

### **Why Do They Match?**
They match (14.56%) because **you likely had no cash flows** during the 1M period. If you had deposits/withdrawals, they would diverge:
- **Modified Dietz:** Adjusts for cash flow timing
- **Simple %:** Treats all value changes as gains/losses

### **Which Is Correct for Leaderboards?**
**Modified Dietz** is the correct method because:
- ✅ Accounts for deposits (doesn't count as "gain")
- ✅ Accounts for withdrawals (doesn't count as "loss")
- ✅ Fair comparison between users
- ✅ Industry standard for performance measurement

**Recommendation:** Charts should also use Modified Dietz for consistency, or at minimum, the card should extract from chart's last point (which we do for S&P 500 now).

---

## 🚀 **IMMEDIATE NEXT STEPS**

### **Step 1: Test 5D Chart (Now)**
1. Refresh dashboard
2. Click "5D" chart
3. Check if diagonal lines are gone
4. Report back results

### **Step 2: Run Sept Investigation Script**
```bash
python investigate_sept_snapshots.py
```
Share the output so we can identify:
- Why Sept 2-10 had low values
- Whether it's a data issue or real portfolio change
- How to fix the leaderboard baseline

### **Step 3: Send to Grok (If 5D Still Broken)**
If diagonal lines persist after testing:
1. Send `GROK_PROMPT_5D_GAP_LINES.md`
2. Send `templates/dashboard.html` (lines 602-730)
3. Attach screenshot of 5D chart
4. Get Grok's recommendations

### **Step 4: Test 1D Chart (Monday)**
- 1D chart fix won't work until Monday
- New snapshots need to be created with correct dates
- Friday's snapshots have old bug (Oct 2 dates)

---

## 📋 **OPEN QUESTIONS**

1. **Sept 2-10 Drop:** What caused the ~7% portfolio value drop?
2. **5D Gap Lines:** Does segment styling work after deploy?
3. **Chart Consistency:** Should charts use Modified Dietz instead of simple %?
4. **Leaderboard Impact:** How do we handle historical anomalies?

---

## 🎯 **SUCCESS CRITERIA**

### **5D Chart Fix:**
- [ ] No diagonal lines between days
- [ ] Data within each day flows smoothly
- [ ] Clear gaps visible overnight/weekend

### **Sept Investigation:**
- [ ] Identify root cause of Sept 2-10 drop
- [ ] Determine if it's data issue or real
- [ ] Fix or explain leaderboard impact

### **Overall:**
- [ ] All chart periods display correctly
- [ ] Leaderboard rankings are fair
- [ ] Documentation complete

---

**Ready to test and investigate!** 🚀
