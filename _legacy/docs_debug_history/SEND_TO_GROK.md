# 📤 SEND THIS TO GROK

## 🎯 THE PROMPT

Hi Grok! I need help fixing 2 remaining chart display issues in my Flask stock portfolio app.

**GOOD NEWS:** The market close cron job is now working perfectly! ✅
- Daily snapshots created for all users
- Sept 30 data shows up in all charts
- No errors in execution

**BAD NEWS:** Two display bugs remain ❌

---

## 🐛 ISSUE #1: S&P 500 Label Shows +0% (CRITICAL - SEE SCREENSHOT)

**The Problem:**
- YTD chart header displays "S&P 500: +0.00%"
- But the chart itself clearly shows the S&P 500 line ending at ~13.95%!

**This means:**
- ✅ Backend data is correct
- ✅ Chart renders correctly
- ❌ The LABEL calculation is broken

**Screenshot attached** showing this discrepancy.

---

## 🐛 ISSUE #2: X-Axis Shows Unix Timestamps

**The Problem:**
- 1D and 5D charts show numbers like "1727712000000" on x-axis
- Should show readable times/dates like "9:30 AM" or "Sep 30"

**This is a Chart.js formatting issue.**

---

## 📎 FILES ATTACHED

1. **`GROK_CHART_DISPLAY_ISSUES.md`** - Comprehensive technical analysis
2. **`GROK_PROMPT_CHARTS.md`** - This prompt with more details
3. **`leaderboard_utils.py`** - Backend chart generation code
4. **`templates/dashboard.html`** - Frontend Chart.js code
5. **Screenshot** - YTD chart showing the S&P 500 label bug

---

## 🎯 WHAT I NEED FROM YOU

For each issue:
1. **Root cause** - Why is this happening?
2. **Code fix** - Specific changes with file paths and line numbers
3. **Verification** - How to test the fix works

---

## 🔍 KEY INSIGHT

For Issue #1 (S&P 500 label):
- The chart data is CORRECT (I can see the line at 13.95%)
- So the label must be calculated separately in JavaScript
- Likely reading from wrong data source or using wrong calculation
- Need to find where the label is set and fix it to read from the actual chart data

---

## ✅ ALREADY FIXED

- ✅ Snapshot creation (all 5 users get daily snapshots)
- ✅ Sept 30 data appears in charts
- ✅ Cache generation works
- ✅ No cron errors

**These 2 display issues are the LAST problems!**

---

Please analyze the attached files and screenshot to identify the exact code causing these bugs. Thank you! 🙏
