# Performance Calculation Fix - Implementation Recommendation

## TL;DR - What We Found

You were RIGHT - we discussed and designed Modified Dietz with max_cash_deployed, but **it was never actually implemented**. Instead, we have 3 different wrong formulas scattered across the codebase, none matching the intended design.

## My Strong Recommendation: Option 1 + Consolidation

**Implement Modified Dietz with max_cash_deployed in ONE unified function that everything calls.**

### Why Modified Dietz (Not Simple Formula)?

1. **The design was thoughtful** - Migration shows clear reasoning
2. **Time-weighting matters** - Even for paper trading:
   - User adds $10k NVDA on Jan 1 (has 10 months to perform)
   - User adds $5k TSLA on Oct 1 (has 1 month to perform)
   - Fair comparison requires time-weighting the Oct addition
3. **Academically sound** - Industry standard for portfolio performance
4. **Explains better** - Users can understand "your returns adjusted for when you deployed capital"

### Why Consolidation?

**Current waste**:
- 3 functions calculate performance
- Dashboard, leaderboard, public pages all duplicate logic
- Bug fixes need 3 changes
- Impossible to keep consistent

**Single source of truth**:
- ONE function everyone calls
- Fix once, works everywhere
- Easier to test, debug, maintain
- Guaranteed consistency

---

## Proposed Implementation

### New File: `performance_calculator.py`

```python
"""
Single source of truth for all portfolio performance calculations.
Uses Modified Dietz method with max_cash_deployed as specified in migration 20251005.
"""

def calculate_portfolio_performance(user_id, start_date, end_date, include_chart_data=False):
    """
    Calculate portfolio performance using Modified Dietz with max_cash_deployed.
    
    Formula (from migration 20251005_add_snapshot_cash_fields.py):
        V_start = stock_value_start + cash_proceeds_start
        V_end = stock_value_end + cash_proceeds_end
        CF = max_cash_deployed_end - max_cash_deployed_start
        Return = (V_end - V_start - CF) / (V_start + W * CF)
    
    Where W is the time-weighted factor for when capital was deployed.
    
    Args:
        user_id: User ID to calculate for
        start_date: Period start (e.g., Jan 1 for YTD)
        end_date: Period end (e.g., today)
        include_chart_data: If True, returns point-by-point chart progression
        
    Returns:
        {
            'portfolio_return': float,  # Final % return (e.g., 28.66)
            'sp500_return': float,      # Benchmark % return
            'chart_data': [...] if include_chart_data else None,
            'metadata': {
                'start_date': date,
                'end_date': date,
                'total_capital_deployed': float,
                'current_value': float
            }
        }
    """
    # Implementation of correct Modified Dietz formula
    # See PERFORMANCE_CALCULATION_AUDIT.md for full details
    pass

def _calculate_chart_points(snapshots, start_date):
    """
    Generate point-by-point chart data showing progressive performance.
    
    Strategy: Use simple formula per point for speed
        chart_value = (snapshot.total_value - snapshot.max_cash_deployed) / snapshot.max_cash_deployed
    
    This is fast and shows progression clearly. Final return uses full Modified Dietz.
    """
    pass

def _calculate_sp500_benchmark(start_date, end_date):
    """
    Calculate S&P 500 return for comparison.
    Uses simple percentage (not time-weighted) since it's a passive benchmark.
    """
    pass
```

### Update All Callers

**1. Dashboard** (`api/index.py` line 13075)
```python
@app.route('/api/portfolio/performance/<period>')
def get_portfolio_performance(period):
    from performance_calculator import calculate_portfolio_performance
    
    # Try cache first (will have correct formula after regeneration)
    chart_cache = UserPortfolioChartCache.query.filter_by(user_id=user_id, period=period_upper).first()
    
    if chart_cache:
        return serve_from_cache(chart_cache)
    
    # Fallback: Live calculation with correct formula
    start_date, end_date = get_period_dates(period_upper)
    result = calculate_portfolio_performance(user_id, start_date, end_date, include_chart_data=True)
    return jsonify(result)
```

**2. Chart Cache Generation** (`leaderboard_utils.py`)
```python
def generate_chart_from_snapshots(user_id, period):
    from performance_calculator import calculate_portfolio_performance
    
    start_date, end_date = get_period_dates(period)
    result = calculate_portfolio_performance(user_id, start_date, end_date, include_chart_data=True)
    
    # Convert to Chart.js format
    return format_for_chartjs(result['chart_data'])
```

**3. Market-Close Cron** (`api/index.py` line 15542)
```python
# PHASE 2: Update Chart Cache with correct formula
from performance_calculator import calculate_portfolio_performance

for user in users:
    for period in periods:
        start_date, end_date = get_period_dates(period)
        result = calculate_portfolio_performance(user.id, start_date, end_date, include_chart_data=True)
        
        # Store in cache
        chart_cache = UserPortfolioChartCache.query.filter_by(user_id=user.id, period=period).first()
        if chart_cache:
            chart_cache.chart_data = json.dumps(result['chart_data'])
            chart_cache.generated_at = datetime.now()
        else:
            # Create new cache entry
            ...
```

**4. Deprecate Old Functions**
- `calculate_modified_dietz_return()` → Add deprecation warning, redirect to new function
- `calculate_performance()` → Delete (unused)
- `generate_chart_from_snapshots()` → Rewrite to call new function

---

## Implementation Steps (Ordered)

### Step 1: Create New Unified Function (2-3 hours)
- Create `performance_calculator.py`
- Implement Modified Dietz with max_cash_deployed
- Implement chart point generation
- Add comprehensive docstrings

### Step 2: Write Tests (1 hour)
- Test with known user data
- Verify formula matches migration example
- Test edge cases (no snapshots, mid-period join, etc.)

### Step 3: Update Market-Close Cron (1 hour)
- Change to use new function
- Test locally to verify chart cache generation

### Step 4: Deploy & Regenerate Caches (30 min)
- Deploy new code
- Run `/admin/force-regenerate-all-caches` with new formula
- Verify 40 chart caches + 48 leaderboard caches regenerate

### Step 5: Update Dashboard Route (30 min)
- Change to use new function for fallback
- Test that dashboard shows correct values

### Step 6: Update Leaderboard Routes (30 min)
- Change to use new function
- Verify leaderboard values match dashboard

### Step 7: Cleanup (1 hour)
- Add deprecation warnings to old functions
- Update documentation
- Create regression tests

**Total estimated time**: 7-8 hours

---

## Success Criteria

After implementation:
1. ✅ Dashboard and leaderboard show SAME performance values
2. ✅ YTD calculation correct (uses Jan 1 baseline with Modified Dietz time-weighting)
3. ✅ Charts show smooth progression
4. ✅ Only ONE function calculates performance
5. ✅ All caches contain correct formula results
6. ✅ Tests verify formula correctness

---

## Questions for Grok

See `GROK_PROMPT_PERFORMANCE_CALCULATION.md` for complete list, but key ones:

1. **Chart point strategy**: Recalculate Modified Dietz per point? Or simple formula per point with Modified Dietz final value?
2. **Edge cases**: How to handle user joining mid-period for YTD?
3. **S&P 500 comparison**: Should benchmark use time-weighting or simple percentage?
4. **Caching strategy**: Keep pre-rendered cache or calculate on-demand?

---

## Risk Assessment

**LOW RISK**: 
- Formula is well-defined in migration
- We have good test data (5 users with real transactions)
- Can verify against current "dashboard live calc" for sanity check
- Caches can be regenerated anytime

**MEDIUM EFFORT**:
- 7-8 hours total work
- Can be done incrementally
- No database schema changes needed

**HIGH IMPACT**:
- Fixes major bug (wrong performance values)
- Eliminates code duplication
- Makes future maintenance easy
- Builds confidence in the system

---

## Files to Create/Modify

**NEW:**
1. `performance_calculator.py` - Single source of truth
2. `test_performance_calculator.py` - Comprehensive tests
3. `PERFORMANCE_CALCULATION_DESIGN.md` - Document the formula

**MODIFY:**
4. `api/index.py` - Dashboard route uses new function
5. `leaderboard_utils.py` - Leaderboard uses new function
6. `api/index.py` - Market-close cron uses new function

**DEPRECATE (eventual cleanup):**
7. `portfolio_performance.py` calculate_modified_dietz_return() - Add warning
8. `cash_tracking.py` calculate_performance() - Delete

---

## My Personal Take

I apologize - I apparently told you Modified Dietz with max_cash_deployed was implemented, but it wasn't. The migration documented the DESIGN, but the code uses wrong formulas.

**This is a critical bug that needs fixing**. Option 1 (implement the design) + consolidation is the right path. It's more work than a simple fix, but it's the engineering-sound approach that will serve you long-term.

The good news: The design is solid, the data is there (snapshots have all required fields), and we have a clear path forward.

Let's implement it correctly once and be done with it.
