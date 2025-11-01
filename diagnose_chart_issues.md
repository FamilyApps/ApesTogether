# Chart Issues Diagnostic Plan

## Issue 1: 1D Chart Wrong Datapoints
**Expected:** 27 intraday points from 9:30 AM - 4:00 PM EST for Oct 31
**Actual:** Unknown - need to check

### Diagnostic Script:
```javascript
// Check intraday data for Oct 31
fetch('https://apestogether.ai/admin/check-spy-intraday', {
  credentials: 'include'
}).then(r => r.json()).then(d => {
  console.log('=== OCT 31 INTRADAY DATA ===')
  const oct31 = d.daily_breakdown_30d.find(day => day.date === '2025-10-31')
  console.log('Count:', oct31.count, '(expected: 27)')
  console.log('Time range:', oct31.time_range, '(expected: 09:30 to 16:00)')
})

// Check what 1D chart is actually showing
fetch('https://apestogether.ai/api/portfolio/performance/1D', {
  credentials: 'include'
}).then(r => r.json()).then(d => {
  console.log('\n=== 1D CHART DATA ===')
  console.log('Total points:', d.chart_data.length)
  console.log('Times:', d.chart_data.map(pt => pt.date))
})
```

### Likely Root Causes:
1. **Intraday cron hasn't run today** - Friday collection incomplete
2. **Date filtering issue** - `performance_calculator.py` might be filtering out today's data
3. **Timezone issue** - Converting EST to UTC incorrectly

### Fix Strategy:
- Check `performance_calculator.py` lines 100-140 for intraday snapshot inclusion logic
- Verify `include_intraday` flag is set for 1D period
- Check date comparison logic for "today"

---

## Issue 2: 5D Chart Showing Wrong Dates
**Expected:** Only 10/27-10/31 (Mon-Fri this week)
**Actual:** Showing 10/24 data, only 1 point for 10/27

### Diagnostic Script:
```javascript
fetch('https://apestogether.ai/api/portfolio/performance/5D', {
  credentials: 'include'
}).then(r => r.json()).then(d => {
  console.log('=== 5D CHART DATA ===')
  const dates = d.chart_data.map(pt => pt.date)
  const uniqueDates = [...new Set(dates.map(d => d.split(' ')[0]))]
  console.log('Unique dates:', uniqueDates)
  console.log('Expected: ["2025-10-27", "2025-10-28", "2025-10-29", "2025-10-30", "2025-10-31"]')
  
  uniqueDates.forEach(date => {
    const count = dates.filter(d => d.startsWith(date)).length
    console.log(`${date}: ${count} points`)
  })
})
```

### Likely Root Causes:
1. **get_period_dates() miscalculation** - 5D might be calculating "5 calendar days" instead of "5 trading days"
2. **Oct 27 missing intraday** - Our backfill added 15-min intervals, but maybe intraday collector didn't run Monday
3. **Weekend dates included** - Oct 26 (Sat) or Oct 27 (Sun) being counted as trading days

### Fix Strategy:
- Check `performance_calculator.py` `get_period_dates()` function
- Ensure 5D means "last 5 trading days" not "last 5 calendar days"
- Verify Oct 24 is NOT included (it's last Thursday)

---

## Issue 3: 1Y Chart Network Error on First Load
**Expected:** Chart loads immediately
**Actual:** 302 redirect, then works after toggling

### Diagnostic:
Log shows: `"GET /api/portfolio/performance/1Y HTTP/1.1" 302`

A 302 redirect typically means:
- `@login_required` redirecting to login page
- Session cookie not being sent on first request

### Root Cause Analysis:
1. **Session cookie timing issue** - Browser doesn't send session cookie on first AJAX request
2. **CORS/SameSite cookie issue** - Modern browsers block cookies on cross-origin requests
3. **Flask session middleware race** - Session not fully established when first chart loads

### Fix Strategy:
**Option A: Add session check to dashboard render**
```python
# In dashboard route, ensure session is established
if not session.get('user_id'):
    session['user_id'] = current_user.id
    db.session.commit()  # Force session write
```

**Option B: Remove @login_required, check current_user instead**
```python
# In get_portfolio_performance:
if not current_user.is_authenticated:
    return jsonify({'error': 'Not authenticated'}), 401
```

**Option C: Add retry logic to frontend**
```javascript
// In dashboard template, retry failed requests once
fetch(url).then(r => {
  if (r.status === 302) {
    // Retry once after session established
    return fetch(url)
  }
  return r
})
```

---

## Implementation Priority:

1. **Run diagnostics** (Issue 1 & 2) - Confirm root causes
2. **Fix Issue 3** (1Y Network Error) - Quick win, Option B is cleanest
3. **Fix Issue 2** (5D wrong dates) - Likely `get_period_dates()` bug
4. **Fix Issue 1** (1D wrong times) - May already be fixed once we verify data collection

## Next Step:
Run the diagnostic scripts and report back findings.
