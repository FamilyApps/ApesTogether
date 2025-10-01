# 📦 Files to Send to Grok

## MAIN PROMPT
**`GROK_PROMPT_CHARTS.md`** - Start here! Short overview of the 3 issues

## TECHNICAL DETAILS
**`GROK_CHART_DISPLAY_ISSUES.md`** - Comprehensive analysis with debugging steps

## CODE FILES TO ATTACH

### Backend (Chart Generation)
1. **`leaderboard_utils.py`** - Contains `generate_chart_from_snapshots()` function
   - This is where chart data is created from database snapshots
   - Look for date range calculation bugs

2. **`snapshot_chart_generator.py`** - Alternative chart generation (if used)
   - May have similar logic

### Frontend (Chart Display)  
3. **`templates/dashboard.html`** - Contains Chart.js configuration
   - Look for the `new Chart()` call around line 604
   - Check x-axis scale configuration
   - Check if time adapter is loaded

### Database Queries
4. **`get_chart_cache_sample.sql`** - SQL queries to inspect cached data
   - Run these to see what's actually stored
   - Share results with Grok

## OPTIONAL (If Grok Needs More Context)

### S&P 500 Related
- **`portfolio_performance.py`** - May contain S&P 500 fetching logic
- **`models.py`** - Database schema for MarketData table

### Market Close Cron (For Reference)
- **`api/index.py`** lines 9606-9737 - Market close cron job (now working!)

---

## HOW TO USE

1. **Send to Grok:**
   - `GROK_PROMPT_CHARTS.md` (the prompt)
   - `GROK_CHART_DISPLAY_ISSUES.md` (detailed analysis)
   - `leaderboard_utils.py` (chart generation code)
   - `templates/dashboard.html` (chart display code)

2. **Run SQL queries** from `get_chart_cache_sample.sql` and share results

3. **Take screenshots** of:
   - 1M chart showing missing Sept 30
   - YTD chart showing "S&P 500: +0%"
   - 1D chart showing Unix timestamps on x-axis

4. **Share with Grok** and ask for specific code fixes!

---

## WHAT GROK SHOULD PROVIDE

For each issue:
1. ✅ Root cause explanation
2. ✅ Specific code fix (file path + line numbers)
3. ✅ Verification steps

---

Good luck! The snapshot creation is working perfectly now - these are just display/formatting issues! 🚀
