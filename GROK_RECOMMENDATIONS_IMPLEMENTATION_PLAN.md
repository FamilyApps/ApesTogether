# Grok Recommendations - Implementation Plan

## Executive Summary

Grok confirmed our analysis and provided detailed recommendations. Here's the implementation plan:

---

## Grok's Key Decisions

### ✅ Decision 1: Modified Dietz with max_cash_deployed
**Verdict**: Implement Modified Dietz (not simple formula)
- Accounts for timing of capital deployment
- Industry standard for portfolios with internal cash flows
- Matches our intended design from migration
- Example: 28.57% (correct) vs 66.67% (simple, wrong)

### ✅ Decision 2: ONE Unified Function
**Verdict**: Consolidate to single source of truth
- Avoids duplication bugs (our 3 formulas problem)
- Easy to test and maintain
- Use parameters for different needs (`include_chart=True/False`)

### ✅ Decision 3: Layered Caching Architecture
**Verdict**: Different strategies for different contexts
- Public Leaderboard: Pre-render HTML (fastest, stale OK)
- User Dashboard: Per-user JSON cache (fresh per market close)
- Public Portfolios: Summary JSON with watermarks/delays

### ✅ Decision 4: Chart Points Strategy
**Verdict**: Simple per-point formula (not expensive recalculation)
- Compute baseline once, then per-point percentage
- Avoids O(n²) inefficiency (1ms vs 10ms per point)
- Use full Modified Dietz only for summary return

### ✅ Decision 5: Freshness Strategy
**Verdict**: Hybrid approach
- Public/Leaderboard: Market-close only (consistent)
- Dashboard: Market-close + on-demand if stale >1h

---

## Implementation Steps

### Phase 1: Create Unified Calculator (2-3 hours)

**File**: `performance_calculator.py` (NEW)

```python
"""
Single source of truth for portfolio performance calculations.
Uses Modified Dietz method with max_cash_deployed.

Based on migration design (20251005_add_cash_tracking.py) and Grok recommendations.
"""

from datetime import date, timedelta
from typing import Dict, List, Optional
from models import PortfolioSnapshot
import logging

logger = logging.getLogger(__name__)


def calculate_portfolio_performance(
    user_id: int,
    start_date: date,
    end_date: date,
    include_chart_data: bool = False
) -> Dict:
    """
    Calculate portfolio performance using Modified Dietz with max_cash_deployed.
    
    Formula (from migration 20251005_add_snapshot_cash_fields.py):
        V_start = stock_value_start + cash_proceeds_start (or total_value)
        V_end = stock_value_end + cash_proceeds_end (or total_value)
        CF_net = max_cash_deployed_end - max_cash_deployed_start
        W = weighted average (based on timing of CF)
        Return = (V_end - V_start - CF_net) / (V_start + W * CF_net)
    
    Args:
        user_id: User ID to calculate performance for
        start_date: Period start (e.g., Jan 1 for YTD)
        end_date: Period end (e.g., today)
        include_chart_data: If True, returns point-by-point chart progression
        
    Returns:
        {
            'portfolio_return': float,  # % return (e.g., 28.57)
            'sp500_return': float,      # Benchmark % return
            'chart_data': List[Dict] if include_chart_data else None,
            'metadata': {
                'start_date': str,
                'end_date': str,
                'snapshots_count': int,
                'net_capital_deployed': float
            }
        }
    
    Edge Cases:
        - No snapshots: Returns 0% with empty chart
        - Zero baseline (V_start + W*CF = 0): Returns 0% with warning
        - User joins mid-period: Uses first snapshot as baseline
        - Negative CF (sales > buys): Handled correctly (can have negative returns)
    """
    logger.info(f"Calculating performance for user {user_id} from {start_date} to {end_date}")
    
    # Get snapshots for period
    snapshots = PortfolioSnapshot.query.filter(
        PortfolioSnapshot.user_id == user_id,
        PortfolioSnapshot.date >= start_date,
        PortfolioSnapshot.date <= end_date
    ).order_by(PortfolioSnapshot.date.asc()).all()
    
    # Edge case: No snapshots
    if not snapshots:
        logger.warning(f"No snapshots found for user {user_id} in period {start_date} to {end_date}")
        return {
            'portfolio_return': 0.0,
            'sp500_return': 0.0,
            'chart_data': [] if include_chart_data else None,
            'metadata': {
                'start_date': start_date.isoformat(),
                'end_date': end_date.isoformat(),
                'snapshots_count': 0,
                'net_capital_deployed': 0.0
            }
        }
    
    # Extract values
    first_snapshot = snapshots[0]
    last_snapshot = snapshots[-1]
    
    V_start = first_snapshot.total_value
    V_end = last_snapshot.total_value
    CF_net = last_snapshot.max_cash_deployed - first_snapshot.max_cash_deployed
    
    # Calculate time-weighted CF (W)
    total_days = (end_date - start_date).days
    if total_days == 0:
        W = 0.0
    else:
        # Calculate weighted cash flows
        weighted_cf = 0.0
        prev_deployed = first_snapshot.max_cash_deployed
        
        for snapshot in snapshots[1:]:
            capital_added = snapshot.max_cash_deployed - prev_deployed
            if capital_added > 0:
                # Weight by remaining days in period
                days_remaining = (end_date - snapshot.date).days
                weight = days_remaining / total_days
                weighted_cf += capital_added * weight
            prev_deployed = snapshot.max_cash_deployed
        
        # W is the ratio: weighted_cf / CF_net (if CF_net > 0)
        W = weighted_cf / CF_net if CF_net > 0 else 0.5  # Default to mid-period if no CF
    
    # Modified Dietz formula
    denominator = V_start + (W * CF_net)
    
    # Edge case: Zero denominator
    if denominator == 0:
        logger.warning(f"Zero denominator for user {user_id}: V_start={V_start}, W={W}, CF_net={CF_net}")
        portfolio_return = 0.0
    else:
        portfolio_return = ((V_end - V_start - CF_net) / denominator) * 100
    
    logger.info(f"Portfolio return: {portfolio_return:.2f}% (V_start={V_start}, V_end={V_end}, CF_net={CF_net}, W={W:.3f})")
    
    # Generate chart data if requested
    chart_data = None
    if include_chart_data:
        chart_data = _generate_chart_points(snapshots, start_date)
    
    # Calculate S&P 500 benchmark
    sp500_return = _calculate_sp500_benchmark(start_date, end_date)
    
    return {
        'portfolio_return': round(portfolio_return, 2),
        'sp500_return': round(sp500_return, 2),
        'chart_data': chart_data,
        'metadata': {
            'start_date': start_date.isoformat(),
            'end_date': end_date.isoformat(),
            'snapshots_count': len(snapshots),
            'net_capital_deployed': round(CF_net, 2)
        }
    }


def _generate_chart_points(snapshots: List[PortfolioSnapshot], period_start: date) -> List[Dict]:
    """
    Generate point-by-point chart data using simple per-point formula.
    
    Uses simple percentage from baseline for performance (Grok recommendation):
        pct = ((value_at_point - baseline) / baseline) * 100
    
    This is O(n) efficient vs O(n²) for full Modified Dietz per point.
    
    Args:
        snapshots: List of PortfolioSnapshot objects
        period_start: Period start date for context
        
    Returns:
        List of chart points: [{'date': 'Oct 25', 'portfolio': 28.57, 'sp500': 15.32}, ...]
    """
    chart_data = []
    
    # Find first non-zero snapshot as baseline
    baseline_snapshot = None
    for snapshot in snapshots:
        if snapshot.total_value > 0:
            baseline_snapshot = snapshot
            break
    
    if not baseline_snapshot:
        return []
    
    baseline_value = baseline_snapshot.total_value
    
    # Generate points
    for snapshot in snapshots:
        if snapshot.total_value > 0:  # Skip zero-value snapshots
            pct = ((snapshot.total_value - baseline_value) / baseline_value) * 100
            
            chart_data.append({
                'date': snapshot.date.strftime('%b %d'),
                'portfolio': round(pct, 2),
                'sp500': 0.0  # TODO: Add S&P 500 per-point data
            })
    
    return chart_data


def _calculate_sp500_benchmark(start_date: date, end_date: date) -> float:
    """
    Calculate S&P 500 return for the period using simple percentage.
    
    Note: Uses simple return (not Modified Dietz) since it's a passive benchmark
    with no cash flows.
    
    Args:
        start_date: Period start
        end_date: Period end
        
    Returns:
        S&P 500 percentage return
    """
    from models import MarketData
    
    # Get S&P 500 prices
    start_price_data = MarketData.query.filter(
        MarketData.date >= start_date
    ).order_by(MarketData.date.asc()).first()
    
    end_price_data = MarketData.query.filter(
        MarketData.date <= end_date
    ).order_by(MarketData.date.desc()).first()
    
    if not start_price_data or not end_price_data:
        logger.warning(f"Missing S&P 500 data for period {start_date} to {end_date}")
        return 0.0
    
    start_price = start_price_data.close_price
    end_price = end_price_data.close_price
    
    if start_price == 0:
        return 0.0
    
    sp500_return = ((end_price - start_price) / start_price) * 100
    
    return sp500_return


# Utility functions for period date calculations
def get_period_dates(period: str) -> tuple:
    """
    Calculate start and end dates for a given period.
    
    Args:
        period: Period string ('1D', '5D', '1M', '3M', 'YTD', '1Y', '5Y', 'MAX')
        
    Returns:
        (start_date, end_date) tuple
    """
    from datetime import datetime
    from utils import get_market_date  # Assumes this exists
    
    end_date = get_market_date()  # Today in ET
    
    if period == '1D':
        start_date = end_date
    elif period == '5D':
        start_date = end_date - timedelta(days=7)  # Account for weekends
    elif period == '1M':
        start_date = end_date - timedelta(days=30)
    elif period == '3M':
        start_date = end_date - timedelta(days=90)
    elif period == 'YTD':
        start_date = date(end_date.year, 1, 1)
    elif period == '1Y':
        start_date = end_date - timedelta(days=365)
    elif period == '5Y':
        start_date = end_date - timedelta(days=365 * 5)
    elif period == 'MAX':
        # Get first snapshot date for this user
        first_snapshot = PortfolioSnapshot.query.order_by(PortfolioSnapshot.date.asc()).first()
        start_date = first_snapshot.date if first_snapshot else end_date
    else:
        raise ValueError(f"Invalid period: {period}")
    
    return start_date, end_date
```

**Testing**: Create `test_performance_calculator.py` with edge cases

---

### Phase 2: Update Dashboard Route (1 hour)

**File**: `api/index.py` (MODIFY)

```python
@app.route('/api/portfolio/performance/<period>')
@login_required
def get_portfolio_performance(period):
    """
    Get portfolio performance data - uses unified calculator.
    
    Strategy: Try cache first (UserPortfolioChartCache), fallback to live calculation.
    """
    from performance_calculator import calculate_portfolio_performance, get_period_dates
    import json
    
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': 'User not authenticated'}), 401
    
    period_upper = period.upper()
    
    # Try cache first (updated by market-close cron)
    chart_cache = UserPortfolioChartCache.query.filter_by(
        user_id=user_id, period=period_upper
    ).first()
    
    # Check if cache is fresh (< 1 hour old)
    from datetime import datetime, timedelta
    cache_is_fresh = (
        chart_cache and 
        chart_cache.generated_at and 
        (datetime.now() - chart_cache.generated_at) < timedelta(hours=1)
    )
    
    if cache_is_fresh:
        logger.info(f"Using cached data for user {user_id}, period {period_upper}")
        cached_data = json.loads(chart_cache.chart_data)
        return jsonify(cached_data)
    
    # Fallback: Live calculation with new unified function
    logger.info(f"Cache miss or stale - calculating live for user {user_id}, period {period_upper}")
    start_date, end_date = get_period_dates(period_upper)
    result = calculate_portfolio_performance(user_id, start_date, end_date, include_chart_data=True)
    
    # Update cache for next request
    if chart_cache:
        chart_cache.chart_data = json.dumps(result)
        chart_cache.generated_at = datetime.now()
    else:
        chart_cache = UserPortfolioChartCache(
            user_id=user_id,
            period=period_upper,
            chart_data=json.dumps(result),
            generated_at=datetime.now()
        )
        db.session.add(chart_cache)
    
    db.session.commit()
    
    return jsonify(result)
```

---

### Phase 3: Update Leaderboard Calculation (1 hour)

**File**: `leaderboard_utils.py` (MODIFY)

Replace `generate_chart_from_snapshots()` to call unified calculator:

```python
def generate_chart_from_snapshots(user_id, period):
    """
    Generate chart data using unified calculator.
    
    DEPRECATED: This function now wraps the unified calculator.
    Direct calls should migrate to performance_calculator.calculate_portfolio_performance()
    """
    from performance_calculator import calculate_portfolio_performance, get_period_dates
    
    start_date, end_date = get_period_dates(period)
    result = calculate_portfolio_performance(user_id, start_date, end_date, include_chart_data=True)
    
    # Convert to old format for backward compatibility (if needed)
    # Otherwise, return new format and update callers
    return result
```

---

### Phase 4: Update Market-Close Cron (1-2 hours)

**File**: `api/index.py` (MODIFY market_close_cron function)

```python
# In market_close_cron():

# PHASE 2: Update chart cache with CORRECT formula
from performance_calculator import calculate_portfolio_performance, get_period_dates

periods = ['1D', '5D', '1M', '3M', 'YTD', '1Y', '5Y', 'MAX']
users = User.query.all()

for user in users:
    for period in periods:
        try:
            start_date, end_date = get_period_dates(period)
            result = calculate_portfolio_performance(user.id, start_date, end_date, include_chart_data=True)
            
            # Update UserPortfolioChartCache
            chart_cache = UserPortfolioChartCache.query.filter_by(
                user_id=user.id, period=period
            ).first()
            
            if chart_cache:
                chart_cache.chart_data = json.dumps(result)
                chart_cache.generated_at = datetime.now()
            else:
                chart_cache = UserPortfolioChartCache(
                    user_id=user.id,
                    period=period,
                    chart_data=json.dumps(result),
                    generated_at=datetime.now()
                )
                db.session.add(chart_cache)
        except Exception as e:
            logger.error(f"Error updating chart cache for user {user.id}, period {period}: {e}")
    
    db.session.commit()
```

---

### Phase 5: Pre-render HTML for Leaderboard (2 hours)

**Implement HTML pre-rendering** in LeaderboardCache:

```python
def update_leaderboard_cache(period='YTD', category='all'):
    """Update leaderboard cache with pre-rendered HTML"""
    from flask import render_template_string
    
    # Calculate leaderboard data
    leaderboard_data = calculate_leaderboard_data(period, category)
    
    # Pre-render HTML
    template = """
    {% for entry in leaderboard_data %}
    <div class="leaderboard-entry">
        <span class="rank">{{ entry.rank }}</span>
        <span class="username">{{ entry.username }}</span>
        <span class="return">{{ entry.portfolio_return }}%</span>
    </div>
    {% endfor %}
    """
    rendered_html = render_template_string(template, leaderboard_data=leaderboard_data)
    
    # Store in cache
    cache_key = f"{period}_{category}_auth"
    cache_entry = LeaderboardCache.query.filter_by(period=cache_key).first()
    
    if cache_entry:
        cache_entry.leaderboard_data = json.dumps(leaderboard_data)
        cache_entry.rendered_html = rendered_html
        cache_entry.generated_at = datetime.now()
    else:
        cache_entry = LeaderboardCache(
            period=cache_key,
            leaderboard_data=json.dumps(leaderboard_data),
            rendered_html=rendered_html,
            generated_at=datetime.now()
        )
        db.session.add(cache_entry)
    
    db.session.commit()
```

---

## Testing Plan

### Unit Tests (`test_performance_calculator.py`)

```python
def test_modified_dietz_basic():
    """Test basic Modified Dietz calculation"""
    # Use example from migration: Aug 1 -> Sep 1
    # Expected: 28.57%
    
def test_zero_baseline():
    """Test edge case: zero denominator"""
    # Should return 0% with warning
    
def test_no_snapshots():
    """Test edge case: no snapshots in period"""
    # Should return 0% with empty chart
    
def test_mid_period_join():
    """Test user who joined mid-period (e.g., June for YTD)"""
    # Should use first snapshot as baseline
    
def test_negative_cf():
    """Test case where user sells more than buys (negative CF)"""
    # Should handle correctly
```

### Integration Tests

1. **Manual verification**: Use witty-raven's data
   - Expected YTD: ~28.66% (from dashboard)
   - After fix: Dashboard and leaderboard should match

2. **Admin diagnostic route**: `/admin/compare-live-vs-cache`
   - Compare new calculator vs cached values
   - Verify all match

---

## Deployment & Cutover Plan

### Step 1: Deploy New Code (Non-breaking)
- Add `performance_calculator.py`
- Add tests
- Deploy (old code still works)

### Step 2: Regenerate All Caches
- Run `/admin/force-regenerate-all-caches`
- Uses new calculator to update all 40 + 48 cache entries

### Step 3: Update Routes (Breaking change)
- Dashboard route uses new calculator
- Leaderboard uses new calculator
- Test thoroughly

### Step 4: Verify Consistency
- Check dashboard vs leaderboard values match
- Monitor logs for errors
- Check performance (should be <500ms)

### Step 5: Cleanup
- Add deprecation warnings to old functions
- Plan eventual removal

---

## Success Criteria

After implementation:
1. ✅ Dashboard and leaderboard show SAME values
2. ✅ YTD calculation uses Jan 1 baseline (not first snapshot)
3. ✅ Modified Dietz formula matches migration design
4. ✅ Charts show smooth progression
5. ✅ Only ONE function calculates performance
6. ✅ All caches updated with correct formula
7. ✅ Leaderboard HTML pre-rendering works
8. ✅ Response times: <100ms (leaderboard), <500ms (dashboard)

---

## Timeline Estimate

- Phase 1 (Calculator): 2-3 hours
- Phase 2 (Dashboard): 1 hour
- Phase 3 (Leaderboard): 1 hour
- Phase 4 (Cron): 1-2 hours
- Phase 5 (Pre-render): 2 hours
- Testing: 1-2 hours

**Total: 8-11 hours**

Can be split across 2-3 work sessions.
