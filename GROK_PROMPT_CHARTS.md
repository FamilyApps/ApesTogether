# 🎯 GROK: Help Fix Chart Display Issues

## CONTEXT

We just fixed the market close cron job - it now successfully creates daily snapshots for all users! 🎉

**But** the charts still have 3 display issues that need fixing.

---

## THE ISSUES

### ~~1. Missing Today's Data (Sept 30) in Charts~~ ✅ FIXED!
**This is now resolved!** Sept 30 shows up correctly in all charts.

---

### 1. **S&P 500 Shows +0% for YTD** (CRITICAL - SEE SCREENSHOT)
- YTD chart header shows "S&P 500: +0.00%"
- Should show actual YTD return (around +13%)
- Suggests S&P 500 data isn't being fetched or calculated correctly

**CRITICAL INSIGHT FROM SCREENSHOT:**
The chart itself renders the S&P 500 line correctly showing ~13.95% gain! This means:
- ✅ Backend data is correct
- ✅ Chart rendering works
- ❌ The LABEL above the chart is calculated incorrectly (shows 0% instead of reading the actual data)

This is likely a frontend JavaScript bug where the label calculation is separate from the chart data.

---

### 2. **X-Axis Shows Unix Timestamps Instead of Dates**
- 1D and 5D charts show numbers like "1727712000000"
- Should show readable times/dates like "9:30 AM" or "Sep 30"
- Chart.js formatting issue

---

## FILES ATTACHED

1. **`GROK_CHART_DISPLAY_ISSUES.md`** - Detailed technical analysis
2. **`leaderboard_utils.py`** - Backend chart generation code
3. **`templates/dashboard.html`** - Frontend Chart.js rendering code
4. **Screenshot** - YTD chart showing S&P 500 line at ~13.95% but label showing +0%

---

## WHAT I NEED

**For each issue, please provide:**
1. Root cause explanation
2. Specific code fix with file path and line numbers
3. Any database queries needed to verify the fix

---

## KEY QUESTIONS

1. **Why is S&P 500 label showing 0%?**
   - The chart renders correctly (shows ~13.95%)
   - But the label above shows "+0.00%"
   - Where is this label calculated in the JavaScript?
   - Why isn't it reading the actual chart data?

2. **How to fix x-axis formatting?**
   - Need Chart.js time adapter?
   - Backend should format labels differently?
   - Frontend configuration missing?

---

## SUCCESS CRITERIA

When fixed:
- ✅ Charts show Sept 30 as the last data point (ALREADY WORKS!)
- ❌ S&P 500 label shows actual return like "+13.95%" (not "+0.00%")
- ❌ X-axis shows readable dates/times (not Unix timestamps)

---

**Please analyze the attached technical document and provide specific fixes!**

Thank you! 🚀
