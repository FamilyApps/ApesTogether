# Performance Calculation - Access Patterns & Architecture Impact

## Different Use Cases = Different Requirements

### Use Case 1: Public Leaderboard Homepage (apestogether.ai/leaderboard)

**Access Pattern:**
- Public traffic (no login required)
- Potentially HIGH traffic (marketing landing page)
- Shows top 20 performers across all users
- Multiple time periods (1D, 5D, 7D, 1M, 3M, YTD, 1Y, 5Y, MAX)
- Multiple categories (All, Large-cap, Small-cap)

**Performance Requirements:**
- ⚡ MUST BE FAST: Target <100ms response time
- 🔄 Can serve stale data (updates daily at market close is fine)
- 👥 Same data for all visitors (perfect for caching)
- 📊 Needs chart data for visual leaderboard

**Current Implementation:**
- Uses LeaderboardCache table (48 entries: 8 periods × 3 categories × 2 auth variants)
- Tries to serve pre-rendered HTML (but NULL - never generated)
- Falls back to get_leaderboard_data() → uses chart cache

**Issues:**
- ❌ Pre-rendered HTML not working
- ❌ Cache contains wrong formula results
- ✅ Architecture is correct (aggressive caching for public page)

**Ideal Implementation:**
```
Public request → 
├─ TRY: Pre-rendered HTML from LeaderboardCache (~5ms)
├─ FALLBACK 1: JSON data from LeaderboardCache + render template (~50ms)
└─ FALLBACK 2: Live calculation + cache result (~500ms, rare)
```

---

### Use Case 2: Logged-In User Dashboard (Private)

**Access Pattern:**
- Private to logged-in user
- Moderate traffic (5 active users currently)
- Personal performance data
- Multiple time periods
- Real-time chart visualization

**Performance Requirements:**
- 🎯 Good UX: Target <500ms response time
- 🔄 Can use cached data from market close
- 👤 User-specific data (cache per user)
- 📈 Needs detailed chart data for visualization

**Current Implementation:**
- Route: `/api/portfolio/performance/<period>`
- Flow:
  1. Try UserPortfolioChartCache (5 users × 8 periods = 40 entries)
  2. Fallback to session cache (5 min TTL)
  3. Last resort: Live calculation

**Issues:**
- ❌ Chart cache contains wrong formula
- ❌ Session cache unnecessary complexity
- ✅ Per-user caching is appropriate

**Ideal Implementation:**
```
User dashboard request →
├─ TRY: UserPortfolioChartCache from market close (~100ms)
└─ FALLBACK: Live calculation + cache in session (~500ms)
```

---

### Use Case 3: Public Portfolio Pages - Subscribers

**Access Pattern:**
- Subscribers viewing portfolios they pay for
- Medium-low traffic (depends on subscriber base)
- Want to see detailed performance of trader they follow
- Expect real-time or near-real-time data

**Performance Requirements:**
- 💰 Subscribers expect quality: Target <300ms
- ⏰ Somewhat fresh data (market close updates OK)
- 🔐 Access control (must verify subscription)
- 📊 Detailed charts and statistics

**Current Implementation:**
- ❓ Need to verify if this exists
- Likely uses same chart cache as dashboard

**Issues:**
- ❓ Unknown if implemented
- Need to consider subscription verification overhead

**Ideal Implementation:**
```
Subscriber views portfolio →
├─ Verify subscription (cached, ~10ms)
├─ TRY: UserPortfolioChartCache (~100ms)
└─ FALLBACK: Live calculation (~500ms)
```

---

### Use Case 4: Public Portfolio Pages - Non-Subscribers (Preview)

**Access Pattern:**
- Anonymous users previewing portfolios (marketing)
- Potentially HIGH traffic (viral potential)
- Limited data shown (prevent free-riding)
- Used to drive subscriptions

**Performance Requirements:**
- ⚡ MUST BE FAST: Same as leaderboard (~100ms)
- 🔄 Can serve very stale data (daily updates fine)
- 🔓 No auth required (public)
- 📊 Limited/watermarked data

**Current Implementation:**
- ❓ Unknown if implemented
- Should leverage same cache as leaderboard

**Ideal Implementation:**
```
Anonymous preview →
├─ TRY: Public cache (shared across all viewers)
└─ Show limited/watermarked version of chart cache
```

---

## Architecture Impact on Implementation

### Caching Strategy Must Support Different Patterns

**Current Problem**: One-size-fits-all approach doesn't work

**Pattern 1: Aggressive Public Caching**
- Leaderboard, public previews
- Can be stale (market close updates)
- Shared across all users
- Needs pre-rendering for speed

**Pattern 2: Per-User Caching**
- Dashboard, subscriber portfolio views
- User-specific data
- Updated at market close
- Live calculation fallback acceptable

**Pattern 3: No Caching**
- Admin/diagnostic tools
- Real-time accuracy needed
- Low traffic, speed less critical

---

## Impact on Function Design

### Option A: Single Function with Caching Logic Inside (BAD)

```python
def calculate_portfolio_performance(user_id, period, use_cache=True, cache_type='user'):
    if use_cache:
        if cache_type == 'leaderboard':
            # Check leaderboard cache
        elif cache_type == 'user':
            # Check user cache
    # Otherwise calculate...
```

**Problems:**
- ❌ Function becomes bloated with caching logic
- ❌ Mixing concerns (calculation + caching)
- ❌ Hard to test calculation independently

---

### Option B: Pure Calculation + Separate Caching Layer (GOOD)

```python
# Pure calculation function (NO caching logic)
def calculate_portfolio_performance(user_id, start_date, end_date, include_chart_data=False):
    """Pure calculation - always calculates, never caches"""
    # Just do the math
    return {
        'portfolio_return': ...,
        'sp500_return': ...,
        'chart_data': ...
    }

# Separate caching strategies for different use cases
def get_leaderboard_performance(period, category='all'):
    """Public leaderboard - aggressive caching"""
    cache_key = f"{period}_{category}_anon"
    cached = LeaderboardCache.query.filter_by(period=cache_key).first()
    
    if cached and is_fresh(cached):
        return cached.data
    
    # Recalculate for all users
    data = calculate_leaderboard_data(period, category)
    cache_result(cache_key, data)
    return data

def get_user_dashboard_performance(user_id, period):
    """Private dashboard - per-user caching"""
    chart_cache = UserPortfolioChartCache.query.filter_by(user_id=user_id, period=period).first()
    
    if chart_cache and is_fresh(chart_cache):
        return chart_cache.data
    
    # Recalculate
    start_date, end_date = get_period_dates(period)
    data = calculate_portfolio_performance(user_id, start_date, end_date, include_chart_data=True)
    update_cache(user_id, period, data)
    return data

def get_public_portfolio_performance(username, period, is_subscriber=False):
    """Public portfolio view - conditional caching"""
    user = User.query.filter_by(username=username).first()
    
    if is_subscriber:
        # Subscribers get fresher data
        return get_user_dashboard_performance(user.id, period)
    else:
        # Anonymous get public cache (can be stale)
        return get_limited_preview(user.id, period)
```

**Benefits:**
- ✅ Separation of concerns
- ✅ Easy to test calculation logic
- ✅ Different caching strategies for different needs
- ✅ Can optimize each use case independently

---

## Recommended Architecture

### Layer 1: Pure Calculation (performance_calculator.py)
```python
def calculate_portfolio_performance(user_id, start_date, end_date, include_chart_data=False):
    """Pure function - no caching, no side effects"""
    # Implement Modified Dietz with max_cash_deployed
    # Return results
```

### Layer 2: Caching Strategies (cache_strategies.py)
```python
class PerformanceCacheStrategy:
    """Abstract base for different caching strategies"""
    
class LeaderboardCacheStrategy(PerformanceCacheStrategy):
    """Aggressive caching for public leaderboard"""
    # Pre-render HTML
    # Update at market close
    # Serve stale data rather than calculate
    
class UserDashboardCacheStrategy(PerformanceCacheStrategy):
    """Per-user caching for dashboards"""
    # Cache per user
    # Update at market close
    # Fallback to live calculation
    
class PublicPortfolioCacheStrategy(PerformanceCacheStrategy):
    """Conditional caching for public portfolios"""
    # Use user cache for subscribers
    # Use public cache for anonymous
    # Watermark/limit data for free preview
```

### Layer 3: Route Handlers (api/index.py, leaderboard_routes.py)
```python
# Leaderboard route
@app.route('/leaderboard')
def leaderboard_home():
    strategy = LeaderboardCacheStrategy()
    data = strategy.get_performance(period, category)
    return render_template('leaderboard.html', data=data)

# Dashboard route
@app.route('/api/portfolio/performance/<period>')
def get_portfolio_performance(period):
    strategy = UserDashboardCacheStrategy()
    data = strategy.get_performance(current_user.id, period)
    return jsonify(data)

# Public portfolio route
@app.route('/portfolio/<username>')
def public_portfolio(username):
    is_subscriber = check_subscription(current_user, username)
    strategy = PublicPortfolioCacheStrategy()
    data = strategy.get_performance(username, period, is_subscriber)
    return render_template('public_portfolio.html', data=data)
```

---

## Performance Requirements Summary

| Use Case | Traffic | Speed Requirement | Freshness | Caching Strategy |
|----------|---------|-------------------|-----------|------------------|
| Leaderboard Homepage | HIGH | <100ms | Daily | Aggressive, pre-render HTML |
| User Dashboard | MEDIUM | <500ms | Daily + live fallback | Per-user, market close |
| Subscriber Portfolio | MEDIUM-LOW | <300ms | Daily + live fallback | Same as dashboard |
| Public Preview | HIGH | <100ms | Daily (can be stale) | Shared, limited data |
| Admin Tools | LOW | No limit | Real-time | No cache |

---

## Questions for Grok

### Question 7: Caching Architecture (NEW)

**Should we use different caching strategies for different access patterns?**

**Current approach**: All use cases try to use same cache (UserPortfolioChartCache)
- Public leaderboard reads chart cache
- Dashboard reads chart cache
- Public pages (if they exist) likely read chart cache

**Problems with one-size-fits-all**:
- Leaderboard needs pre-rendered HTML (public, high traffic)
- Dashboard can tolerate live calculation (private, low traffic)
- Public pages need different data limits for subscribers vs non-subscribers

**Proposed approach**: Layer caching strategies
- Pure calculation function (no caching logic)
- Different strategy classes for different use cases
- Each optimizes for its traffic/speed/freshness requirements

**Is this over-engineering or appropriate architecture?**

### Question 8: Pre-rendering Decision

**Where should we pre-render HTML vs serve JSON?**

**Public leaderboard**:
- Pre-render full HTML? (fastest, ~5ms)
- Or JSON + template render? (slower, ~50ms)
- Current: Tries HTML but fails, falls back to JSON

**Dashboard**:
- JSON only (frontend renders with Chart.js)
- No HTML pre-rendering needed

**Public portfolios**:
- Pre-render for anonymous users? (high traffic potential)
- JSON for subscribers? (personalized experience)

**Trade-offs**:
- Pre-rendered HTML: Fastest but inflexible (can't personalize)
- JSON + render: Slower but can customize per user

### Question 9: Cache Update Strategy

**When should caches be updated?**

**Current**: Market close cron updates all caches daily (4PM EDT)

**Should we also**:
- Update on-demand when user views their dashboard? (fresher data)
- Lazy-load cache (calculate and cache on first request)? (simpler)
- Keep market-close only? (consistent snapshot time)

**Trade-offs**:
- Market-close only: Consistent, but stale during trading hours
- On-demand: Fresher, but inconsistent timing across users
- Hybrid: Market-close for public, on-demand for dashboard?

### Question 10: Public Portfolio Pages

**What data should non-subscribers see?**

**Options**:
- Limited time periods only (e.g., only 1M and YTD)
- Watermarked charts (low resolution, branded)
- Delayed data (yesterday's close, not today's)
- Summary stats only (no chart)

**This affects**:
- Whether public preview needs separate cache
- Or can just filter/watermark user cache

---

## Impact on Implementation Plan

**Phase 1**: Implement pure calculation function
- No caching logic
- Just correct Modified Dietz formula

**Phase 2**: Implement caching strategies
- LeaderboardCacheStrategy for public pages
- UserDashboardCacheStrategy for logged-in users
- PublicPortfolioCacheStrategy for portfolio views

**Phase 3**: Update market-close cron
- Use pure calculation function
- Update all cache types with correct formula

**Phase 4**: Update route handlers
- Each uses appropriate caching strategy
- Clear separation of concerns

**Phase 5**: Implement pre-rendering
- HTML pre-render for leaderboard
- Test and optimize

This architecture supports:
- ✅ Different performance requirements
- ✅ Different traffic patterns
- ✅ Different data freshness needs
- ✅ Future features (subscriptions, public portfolios)
- ✅ Easy testing and maintenance
