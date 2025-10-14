# COMPLETE CHART DATA FLOW DIAGNOSTIC

## Current State
- Database: First snapshot = 6/19/2025 ✅
- Cache: First label = "2025-06-19" ✅
- Rendered 1Y chart: First point = 6/23/2025 ❌
- Rendered YTD chart: First point = 6/20/2025 ❌

**Problem: Data exists but gets filtered out during rendering**

## Data Flow to Trace

### 1. DATABASE → CACHE GENERATION
**File:** `leaderboard_utils.py` - `generate_user_portfolio_chart()`
**Question:** Does this function include 6/19 in the sampled dates?

**Need to check:**
- Does it query snapshots >= 6/19?
- Does the sampling logic skip 6/19?
- What dates does it actually select?

### 2. CACHE → API RESPONSE
**File:** `api/index.py` - Chart data endpoint (need to find which one!)
**Question:** What endpoint serves chart data to the frontend?

**Need to check:**
- Does it return cached data or live calculation?
- If cache format is wrong, does it fall back to live calculation?
- What does the API actually return for 1Y period?

### 3. API RESPONSE → FRONTEND RENDERING
**File:** `templates/profile.html` or similar
**Question:** What JavaScript receives the data and renders it?

**Need to check:**
- Does Chart.js filter out any points?
- Are there any date range filters applied?
- Does the sampling logic in JS skip dates?

## Diagnostic Endpoint Needed

Create `/admin/trace-chart-data-flow/<username>/<period>` that returns:

```json
{
  "step1_database": {
    "all_snapshot_dates": ["2025-06-19", "2025-06-20", ...],
    "total_count": 81
  },
  "step2_cache_generation": {
    "cache_exists": true,
    "cache_format": "dollar_values",  // or "percentage_returns"
    "cached_labels": ["2025-06-19", "2025-06-23", ...],  // EXACT labels in cache
    "cached_first_value": 6206.49,
    "labels_count": 50
  },
  "step3_api_returns": {
    "uses_cache": true,  // or falls back to live?
    "returned_labels": ["Jun 23", "Jun 27", ...],  // EXACT labels sent to frontend
    "returned_first_portfolio_value": 4.97,  // percentage or dollar?
    "labels_count": 45
  },
  "step4_sampling_logic": {
    "original_snapshot_count": 81,
    "after_sampling_count": 45,
    "sampling_method": "pick_every_nth" or "smart_sampling",
    "skipped_dates": ["2025-06-19", "2025-06-20", "2025-06-21"]  // What got filtered
  }
}
```

## Root Cause Hypotheses

1. **Cache sampling logic skips first date** - `leaderboard_utils.py` might skip 6/19 when sampling
2. **API rejects cache, falls back to live calc** - Live calc has different sampling that skips 6/19
3. **Frontend filtering** - Chart.js or JS code filters out early dates
4. **Date range calculation** - "1Y ago" calculation might be 10/9/2024, excluding 6/19/2025

## Action Plan

1. Find the API endpoint that serves chart data to frontend
2. Add comprehensive logging to show EXACT dates at each step
3. Create diagnostic endpoint that traces full flow
4. Identify WHERE 6/19 gets filtered out
5. Fix the filtering/sampling logic
