"""
Single source of truth for portfolio performance calculations.
Uses Modified Dietz method with max_cash_deployed.

Based on:
- Migration design: 20251005_add_snapshot_cash_fields.py
- Grok recommendations: Modified Dietz with time-weighting
- Formula: Return = (V_end - V_start - CF_net) / (V_start + W * CF_net)

Where:
- V_start, V_end = Portfolio values (stock_value + cash_proceeds or total_value)
- CF_net = max_cash_deployed_end - max_cash_deployed_start (net capital deployed)
- W = Time-weighted factor for when capital was deployed

VALIDATED by Grok (Oct 26, 2025):
✓ Mathematically correct Modified Dietz implementation
✓ Time-weighting appropriate for paper trading (internal flows)
✓ "Actual return" approach correct for leaderboards (non-extrapolated)
✓ CF_net calculation correctly tracks only NEW capital deployment
✓ Edge cases handled (CF_net=0 simplifies to simple %, zero denominator)

Key Design Decisions:
1. Actual Return (not time-adjusted): Users show performance from their join date,
   not extrapolated to full period. Prevents gaming leaderboards with hot streaks.
2. CF_net floored at 0: Handles rare edge case where sells > buys (negative CF).
3. W = 0.5 when CF_net = 0: Standard mid-period assumption (doesn't affect result).
4. Baseline = first snapshot: Shows return from when user actually started trading.
"""

from datetime import date, timedelta, datetime
from typing import Dict, List, Optional, Tuple
from models import PortfolioSnapshot, MarketData
from sqlalchemy import and_
import logging

logger = logging.getLogger(__name__)


def get_user_first_activity_date(user_id: int) -> Optional[date]:
    """
    Get the date a user first had assets (first non-zero portfolio snapshot).
    
    This is the canonical way to determine when a user became "active" for:
    - Leaderboard eligibility (must be active for full period)
    - S&P 500 comparison alignment (benchmark starts from user's active date)
    - Chart data start date (charts begin from first activity)
    
    Returns None if user has never had a portfolio snapshot.
    """
    first_snapshot = PortfolioSnapshot.query.filter(
        and_(
            PortfolioSnapshot.user_id == user_id,
            PortfolioSnapshot.total_value > 0
        )
    ).order_by(PortfolioSnapshot.date.asc()).first()
    
    return first_snapshot.date if first_snapshot else None


def batch_get_first_activity_dates() -> Dict[int, date]:
    """
    Batch-fetch first activity dates for ALL users in a single SQL query.
    Returns {user_id: first_activity_date} for users with non-zero snapshots.
    
    This is O(1) queries vs O(n) for get_user_first_activity_date per user.
    Used by leaderboard computation to scale to 10k+ users.
    """
    from sqlalchemy import func as sqla_func
    from models import db
    
    rows = db.session.query(
        PortfolioSnapshot.user_id,
        sqla_func.min(PortfolioSnapshot.date).label('first_date')
    ).filter(
        PortfolioSnapshot.total_value > 0
    ).group_by(PortfolioSnapshot.user_id).all()
    
    return {uid: first_date for uid, first_date in rows}


def batch_get_leaderboard_eligibility(period: str) -> Dict[int, dict]:
    """
    Batch-check leaderboard eligibility for ALL users in a single SQL query.
    Returns {user_id: eligibility_dict} — same format as get_leaderboard_eligibility.
    
    Scales to 10k+ users with O(1) database queries instead of O(n).
    """
    first_dates = batch_get_first_activity_dates()
    
    try:
        from portfolio_performance import get_market_date
    except ImportError:
        from zoneinfo import ZoneInfo
        MARKET_TZ = ZoneInfo('America/New_York')
        def get_market_date():
            return datetime.now(MARKET_TZ).date()
    
    today = get_market_date()
    
    period_requirements = {
        '1D': 0, '5D': 0, '1W': 0, '1M': 30, '3M': 90,
        'YTD': (today - date(today.year, 1, 1)).days,
        '1Y': 365, '5Y': 365 * 5, 'MAX': 0,
    }
    days_required = period_requirements.get(period.upper(), 0)
    
    results = {}
    for uid, first_activity in first_dates.items():
        days_active = (today - first_activity).days
        eligible = days_active >= days_required
        eligible_date = None
        if not eligible and days_required > 0:
            eligible_date = first_activity + timedelta(days=days_required)
        
        results[uid] = {
            'eligible': eligible,
            'first_activity_date': first_activity,
            'days_active': days_active,
            'days_required': days_required,
            'eligible_date': eligible_date
        }
    
    return results


def get_leaderboard_eligibility(user_id: int, period: str) -> dict:
    """
    Check if a user is eligible for a specific leaderboard period.
    
    Rules:
    - User must have been active (had assets) for the ENTIRE duration of the period.
    - e.g., 3M leaderboard requires 90+ days of activity.
    - 1D and 5D have no minimum (anyone with data qualifies).
    
    Returns:
        {
            'eligible': bool,
            'first_activity_date': date or None,
            'days_active': int,
            'days_required': int,
            'eligible_date': date or None  # When user WILL be eligible (if not yet)
        }
    """
    first_activity = get_user_first_activity_date(user_id)
    
    if not first_activity:
        return {
            'eligible': False,
            'first_activity_date': None,
            'days_active': 0,
            'days_required': 0,
            'eligible_date': None
        }
    
    try:
        from portfolio_performance import get_market_date
    except ImportError:
        from zoneinfo import ZoneInfo
        MARKET_TZ = ZoneInfo('America/New_York')
        def get_market_date():
            return datetime.now(MARKET_TZ).date()
    
    today = get_market_date()
    days_active = (today - first_activity).days
    
    # Minimum days required for each leaderboard period
    period_requirements = {
        '1D': 0,    # No minimum
        '5D': 0,    # No minimum
        '1W': 0,    # No minimum (alias for 5D)
        '1M': 30,
        '3M': 90,
        'YTD': (today - date(today.year, 1, 1)).days,  # Must have been active since Jan 1
        '1Y': 365,
        '5Y': 365 * 5,
        'MAX': 0,   # No minimum for MAX
    }
    
    days_required = period_requirements.get(period.upper(), 0)
    eligible = days_active >= days_required
    
    # Calculate when user will become eligible
    eligible_date = None
    if not eligible and days_required > 0:
        eligible_date = first_activity + timedelta(days=days_required)
    
    return {
        'eligible': eligible,
        'first_activity_date': first_activity,
        'days_active': days_active,
        'days_required': days_required,
        'eligible_date': eligible_date
    }


def calculate_portfolio_performance(
    user_id: int,
    start_date: date,
    end_date: date,
    include_chart_data: bool = False,
    period: str = None
) -> Dict:
    """
    Calculate portfolio performance using chain-linked TWR over snapshots.
    
    This is THE SINGLE SOURCE OF TRUTH for all performance calculations.
    Called by: Dashboard, Leaderboard, Market-close cron, Admin tools.
    
    METHODOLOGY (owner-approved switch 2026-08-31, Session 47):
        Headline + chart points = chain-linked TWR (calculate_twr_return) — the
        return a day-one copy-trading subscriber actually experiences. Replaced
        window Modified Dietz, which mis-stated the copier experience around
        large mid-window capital deploys (fleet compare 8/31: chart1658 YTD
        +44.39% Dietz vs +37.42% TWR; zero-flow users bit-identical).
        Dietz preserved in calculate_dietz_return for /admin/compare-dietz-twr.
    
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
    
    Edge Cases Handled:
        - No snapshots: Returns 0% with empty chart
        - Zero baseline (V_start + W*CF = 0): Returns 0% with warning
        - User joins mid-period: Uses first snapshot as baseline
        - Negative CF (sales > buys): Handled correctly (can have negative returns)
        - All-zero snapshots: Skipped, uses first non-zero as baseline
    """
    import time as _time
    _t0 = _time.time()
    logger.info(f"Calculating performance for user {user_id} from {start_date} to {end_date}")
    
    # Determine if we should include intraday snapshots (for 1D and 5D periods only)
    # Check period name directly rather than day count since 5D can span 7 calendar days
    include_intraday = period in ['1D', '5D'] if period else False
    
    # Get daily snapshots for period
    _tq = _time.time()
    snapshots = PortfolioSnapshot.query.filter(
        and_(
            PortfolioSnapshot.user_id == user_id,
            PortfolioSnapshot.date >= start_date,
            PortfolioSnapshot.date <= end_date
        )
    ).order_by(PortfolioSnapshot.date.asc()).all()
    logger.info(f"[PERF-TIMING] user={user_id} daily_snapshots_query: {round(_time.time()-_tq,2)}s, got {len(snapshots)} rows")
    
    # For 1D and 5D periods, also include intraday snapshots
    if include_intraday:
        from models import PortfolioSnapshotIntraday
        from datetime import datetime, time
        from zoneinfo import ZoneInfo
        
        start_datetime = datetime.combine(start_date, time.min)
        end_datetime = datetime.combine(end_date, time.max)
        
        _tq2 = _time.time()
        intraday_snapshots = PortfolioSnapshotIntraday.query.filter(
            and_(
                PortfolioSnapshotIntraday.user_id == user_id,
                PortfolioSnapshotIntraday.timestamp >= start_datetime,
                PortfolioSnapshotIntraday.timestamp <= end_datetime
            )
        ).order_by(PortfolioSnapshotIntraday.timestamp.asc()).all()
        logger.info(f"[PERF-TIMING] user={user_id} intraday_query: {round(_time.time()-_tq2,2)}s, got {len(intraday_snapshots)} rows")
        
        # Filter to only valid 15-minute market intervals (9:30 AM - 4:00 PM EST)
        # Valid times: 09:30, 09:45, 10:00, ..., 15:45, 16:00 (27 intervals)
        valid_minutes = set()
        for hour in range(9, 17):  # 9 AM to 4 PM
            for minute in [0, 15, 30, 45]:
                # Skip 9:00 AM and 9:15 AM (market opens at 9:30)
                if hour == 9 and minute < 30:
                    continue
                # Skip times after 4:00 PM
                if hour == 16 and minute > 0:
                    continue
                valid_minutes.add((hour, minute))
        
        # Filter snapshots to only valid intervals in ET
        MARKET_TZ = ZoneInfo('America/New_York')
        UTC_TZ = ZoneInfo('UTC')
        filtered_intraday = []
        filtered_out = []
        
        for snap in intraday_snapshots:
            # Convert timestamp to ET
            # IMPORTANT: PostgreSQL DateTime (without timezone) stores UTC when given
            # a timezone-aware datetime. get_market_time() returns ET-aware, but
            # psycopg2 converts to UTC before storing in a naive column.
            # So naive timestamps here are UTC — must convert to ET.
            if snap.timestamp.tzinfo is None:
                # Treat as UTC-naive, convert to ET
                snap_time_est = snap.timestamp.replace(tzinfo=UTC_TZ).astimezone(MARKET_TZ)
            else:
                snap_time_est = snap.timestamp.astimezone(MARKET_TZ)
            
            # Check if this is within market hours (9:30 AM - 4:00 PM ET)
            # Allow +/- 3 min tolerance for cron timing variance and force calls
            snap_h, snap_m = snap_time_est.hour, snap_time_est.minute
            in_market_hours = (
                (snap_h == 9 and snap_m >= 27) or  # 9:27+ (tolerance for 9:30)
                (10 <= snap_h <= 15) or             # 10:00 AM - 3:59 PM
                (snap_h == 16 and snap_m <= 3)      # Up to 4:03 PM (tolerance for 4:00)
            )
            
            if in_market_hours:
                filtered_intraday.append(snap)
            else:
                filtered_out.append(f"{snap_time_est.strftime('%H:%M ET')} (stored as {snap.timestamp.strftime('%H:%M UTC')})")
        
        logger.info(f"Filtered {len(intraday_snapshots)} intraday snapshots to {len(filtered_intraday)} valid market-hours snapshots")
        if filtered_out:
            logger.info(f"Filtered OUT these times: {', '.join(filtered_out[:10])}")
        
        intraday_snapshots = filtered_intraday
        
        if intraday_snapshots:
            # Wrapper class to make intraday snapshots compatible with daily snapshot interface
            class IntradayWrapper:
                def __init__(self, intraday_snap):
                    # Timestamps are stored in UTC; convert to ET for date extraction
                    ts = intraday_snap.timestamp
                    if ts.tzinfo is None:
                        ts_et = ts.replace(tzinfo=ZoneInfo('UTC')).astimezone(MARKET_TZ)
                    else:
                        ts_et = ts.astimezone(MARKET_TZ)
                    self.date = ts_et.date()
                    self.timestamp = intraday_snap.timestamp
                    self.total_value = intraday_snap.total_value
                    self.stock_value = intraday_snap.stock_value or 0.0
                    self.cash_proceeds = intraday_snap.cash_proceeds or 0.0
                    self.max_cash_deployed = intraday_snap.max_cash_deployed or 0.0
                    self.user_id = intraday_snap.user_id
                    self.is_intraday = True
            
            # Wrap intraday snapshots
            wrapped_intraday = [IntradayWrapper(s) for s in intraday_snapshots]
            
            # For 1D and 5D periods, ONLY use intraday snapshots (exclude daily snapshots to avoid duplicates)
            # For longer periods (1M+), merge daily snapshots with intraday snapshots
            if period in ['1D', '5D']:
                snapshots = wrapped_intraday
                logger.info(f"Using ONLY {len(intraday_snapshots)} intraday snapshots for {period} period (excluding daily)")
            else:
                # Add timestamp to daily snapshots for sorting
                for snap in snapshots:
                    snap.timestamp = datetime.combine(snap.date, time(16, 0))
                    snap.is_intraday = False
                
                # Merge and sort all snapshots by timestamp
                snapshots = sorted(snapshots + wrapped_intraday, key=lambda s: s.timestamp)
                logger.info(f"Including {len(intraday_snapshots)} intraday + {len(snapshots) - len(intraday_snapshots)} daily snapshots for {period} period")
    
    # For 1D: if we only have 0 or 1 snapshot (e.g. market closed, no intraday),
    # expand to include the previous trading day's daily close as a baseline
    if period == '1D' and len(snapshots) <= 1:
        prev_day = start_date - timedelta(days=1)
        while prev_day.weekday() >= 5:
            prev_day = prev_day - timedelta(days=1)
        
        prev_snapshots = PortfolioSnapshot.query.filter(
            and_(
                PortfolioSnapshot.user_id == user_id,
                PortfolioSnapshot.date >= prev_day,
                PortfolioSnapshot.date <= end_date
            )
        ).order_by(PortfolioSnapshot.date.asc()).all()
        
        if len(prev_snapshots) >= 2:
            snapshots = prev_snapshots
            start_date = prev_day
            logger.info(f"1D fallback: expanded to {prev_day} -> {end_date} ({len(snapshots)} daily snapshots)")
    
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
    
    # Extract values from snapshots
    first_snapshot = snapshots[0]
    last_snapshot = snapshots[-1]
    
    # Use first snapshot as baseline (regardless of when user joined)
    # This shows ACTUAL return from when they started, not time-adjusted
    V_start = first_snapshot.total_value
    V_end = last_snapshot.total_value
    
    # Calculate CF_net (net new capital deployed during user's active period)
    # NOTE: In our system, max_cash_deployed only increases (never decreases), so CF_net >= 0 always.
    # The max(0, ...) is defensive programming for theoretical edge case.
    CF_net = max(0.0, last_snapshot.max_cash_deployed - first_snapshot.max_cash_deployed)
    
    # Log if user joined mid-period (for informational purposes)
    if first_snapshot.date > start_date:
        logger.info(
            f"User {user_id} joined mid-period on {first_snapshot.date}. "
            f"Showing actual return from {first_snapshot.date} to {end_date}, not time-adjusted."
        )
    
    logger.debug(f"User {user_id}: V_start=${V_start:.2f}, V_end=${V_end:.2f}, CF_net=${CF_net:.2f}")
    
    # Use the user's ACTUAL active period (from first snapshot to end)
    actual_period_days = (end_date - first_snapshot.date).days
    
    # ── METHODOLOGY SWITCH (owner-approved 2026-08-31, Session 47) ──
    # Chain-linked TWR: the return a day-one copy-trading subscriber actually
    # experiences (full rationale in calculate_twr_return's docstring). The
    # retired window Modified Dietz lives on in calculate_dietz_return, used
    # only by the read-only /admin/compare-dietz-twr diff tool.
    twr_result = calculate_twr_return(snapshots)
    if twr_result is None:
        logger.warning(f"No usable baseline for user {user_id}: all snapshots zero-value")
        portfolio_return = 0.0
        twr_series = None
    else:
        portfolio_return = twr_result['twr_return']
        twr_series = twr_result['series']
    
    logger.info(
        f"Portfolio TWR: {portfolio_return:.2f}% "
        f"(V_start=${V_start:.2f}, V_end=${V_end:.2f}, CF_net=${CF_net:.2f}, "
        f"flow_days={twr_result['flow_days'] if twr_result else 0})"
    )
    
    # Generate chart data if requested (per-point cumulative TWR — the chart's
    # final point equals the headline portfolio_return by construction)
    chart_data = None
    if include_chart_data:
        _tc = _time.time()
        chart_data = _generate_chart_points(snapshots, start_date, end_date, period, twr_series=twr_series)
        logger.info(f"[PERF-TIMING] user={user_id} chart_points: {round(_time.time()-_tc,2)}s, {len(chart_data) if chart_data else 0} points")
    
    # Calculate S&P 500 benchmark (simple percentage, not time-weighted)
    # IMPORTANT: Use user's actual start date (first snapshot), not period start.
    # This ensures apples-to-apples comparison — if user has only been active 3 weeks,
    # S&P return is also calculated over those same 3 weeks, not the full 3-month period.
    sp500_start = first_snapshot.date if first_snapshot.date > start_date else start_date
    _ts = _time.time()
    sp500_return = _calculate_sp500_benchmark(sp500_start, end_date)
    logger.info(f"[PERF-TIMING] user={user_id} sp500_benchmark: {round(_time.time()-_ts,2)}s (sp500_start={sp500_start})")
    logger.info(f"[PERF-TIMING] user={user_id} TOTAL: {round(_time.time()-_t0,2)}s")
    
    return {
        'portfolio_return': round(portfolio_return, 2),
        'sp500_return': round(sp500_return, 2),
        'chart_data': chart_data,
        'metadata': {
            'start_date': start_date.isoformat(),
            'end_date': end_date.isoformat(),
            'actual_start_date': first_snapshot.date.isoformat(),  # When user actually started (may differ from period start)
            'snapshots_count': len(snapshots),
            'net_capital_deployed': round(CF_net, 2),
            'days_active': actual_period_days,  # Days user was actually trading (useful for UI context)
            'joined_mid_period': first_snapshot.date > start_date  # Flag for UI to show "Active since X"
        }
    }


def _generate_chart_points(
    snapshots: List[PortfolioSnapshot],
    period_start: date,
    period_end: date,
    period: Optional[str] = None,
    twr_series: Optional[List] = None
) -> List[Dict]:
    """
    Generate point-by-point chart data using cumulative chain-linked TWR
    (Session 47 methodology switch — rationale in calculate_twr_return).
    Each point is the compounded flow-adjusted return from the window baseline,
    so the last chart point equals the headline portfolio_return exactly.
    O(n): the whole progression falls out of one pass.
    
    Args:
        snapshots: List of PortfolioSnapshot objects
        period_start: Period start date
        period_end: Period end date
        period: Period label (drives sampling + axis labels)
        twr_series: Optional precomputed calculate_twr_return(snapshots)['series']
                    (aligned to snapshots); computed here if not supplied
        
    Returns:
        List of chart points: [{'date': 'Oct 25', 'portfolio': 28.57, 'sp500': 15.32}, ...]
    """
    import time as _time
    _tcp0 = _time.time()
    chart_data = []
    
    if twr_series is None:
        _twr = calculate_twr_return(snapshots)
        twr_series = _twr['series'] if _twr else None
    if not twr_series:
        logger.warning("No TWR series computable for chart generation")
        return []
    
    # Find first non-zero snapshot as baseline
    baseline_snapshot = None
    for snapshot in snapshots:
        if snapshot.total_value > 0:
            baseline_snapshot = snapshot
            break
    
    if not baseline_snapshot:
        logger.warning(f"No non-zero snapshots found for chart generation")
        return []
    
    baseline_value = baseline_snapshot.total_value
    baseline_date = baseline_snapshot.date
    logger.debug(f"Chart baseline: ${baseline_value:.2f} on {baseline_date}")
    logger.info(f"[CHART-TIMING] snapshots_count={len(snapshots)}, baseline={baseline_date}")
    
    # S&P 500 data starts from user's baseline_date (not period_start) so the chart
    # only shows data points since the user had assets. Both lines start at 0%.
    sp500_baseline_date = baseline_date  # User's first non-zero snapshot date
    _tsp = _time.time()
    if period in ['1D', '5D']:
        # Query intraday S&P 500 data from user's baseline
        sp500_data = MarketData.query.filter(
            and_(
                MarketData.ticker == 'SPY_INTRADAY',
                MarketData.date >= sp500_baseline_date,
                MarketData.date <= period_end,
                MarketData.timestamp.isnot(None)
            )
        ).order_by(MarketData.timestamp.asc()).all()
        
        # FALLBACK: If no intraday S&P 500 data, use daily close
        if not sp500_data:
            logger.warning(f"No SPY_INTRADAY data found for {period}, falling back to daily SPY_SP500")
            sp500_data = MarketData.query.filter(
                and_(
                    MarketData.ticker == 'SPY_SP500',
                    MarketData.date >= sp500_baseline_date,
                    MarketData.date <= period_end
                )
            ).order_by(MarketData.date.asc()).all()
    else:
        # Query daily S&P 500 data from user's baseline date
        sp500_data = MarketData.query.filter(
            and_(
                MarketData.ticker == 'SPY_SP500',
                MarketData.date >= sp500_baseline_date,
                MarketData.date <= period_end
            )
        ).order_by(MarketData.date.asc()).all()
    
    logger.info(f"[CHART-TIMING] sp500_query: {round(_time.time()-_tsp,2)}s, got {len(sp500_data)} rows")
    
    # DEBUG: Log what dates we actually got
    if sp500_data:
        logger.info(f"📊 S&P 500 query returned {len(sp500_data)} records from {sp500_data[0].date} to {sp500_data[-1].date}")
        logger.info(f"📊 Query params: sp500_baseline_date={sp500_baseline_date}, period_end={period_end}")
    else:
        logger.warning(f"⚠️ S&P 500 query returned NO DATA for {sp500_baseline_date} to {period_end}")
    
    # Build S&P 500 lookup map (by date for daily, by timestamp for intraday)
    if period in ['1D', '5D']:
        # For intraday: build map by timestamp for precise matching
        # SPY_INTRADAY is already stored as spy_price * 10, do NOT multiply again
        sp500_map_timestamp = {}
        for s in sp500_data:
            if hasattr(s, 'timestamp') and s.timestamp:
                sp500_map_timestamp[s.timestamp] = float(s.close_price)
        # Also keep a date map for fallback
        sp500_map = {s.date: float(s.close_price) for s in sp500_data}
    else:
        # For daily: build map by date only
        sp500_map = {s.date: float(s.close_price) for s in sp500_data}
        sp500_map_timestamp = {}
    
    # Get baseline S&P 500 value from user's first snapshot date (apples-to-apples)
    # Find the S&P record closest to (on or after) the user's baseline date
    baseline_sp500 = None
    if sp500_data:
        for sp_rec in sp500_data:
            if sp_rec.date >= sp500_baseline_date:
                baseline_sp500 = float(sp_rec.close_price)
                break
        # Fallback to first available if none found on/after baseline
        if baseline_sp500 is None:
            baseline_sp500 = float(sp500_data[0].close_price)
    
    if not baseline_sp500:
        logger.warning(f"No S&P 500 baseline data found for user baseline {sp500_baseline_date}")
        baseline_sp500 = 1.0  # Avoid division by zero
    
    logger.info(f"S&P 500 baseline: ${baseline_sp500:.2f} from user start {sp500_baseline_date} (period_start={period_start})")
    
    # Track which chart points are before user's first activity (for S&P-only rendering)
    # Points before the user's baseline show S&P from the baseline perspective (will be 0 or slightly off)
    
    # Build snapshot map for quick lookup
    snapshot_map = {s.date: s for s in snapshots if s.total_value > 0}
    
    # Check if we have intraday data (snapshots with timestamps)
    has_intraday = any(hasattr(s, 'is_intraday') and s.is_intraday for s in snapshots)
    
    if has_intraday:
        # For intraday periods (1D/5D): Generate point for each snapshot
        from zoneinfo import ZoneInfo as _ZoneInfo

        # Use proper ZoneInfo for DST-safe ET conversion
        ET = _ZoneInfo('America/New_York')
        UTC_TZ = _ZoneInfo('UTC')

        # Sparse-axis-label strategy: only label "boundary" points; non-boundary
        # points get empty string. iOS xAxisTickValues filters by non-empty.
        # - 1D: label fixed market hours (10 AM, 12 PM, 2 PM) + always-last point
        # - 5D/1W: label first point of each new ET day with "Mon 5/5"-style label
        labeled_1d_hours = set()  # Track which 1D hour boundaries we've already labeled
        prev_5d_day = None        # Track which ET dates we've already labeled in 5D mode
        last_snapshot_index = len(snapshots) - 1

        def _format_1d_hour_label(h_24, m):
            """Format an hour boundary as '10 AM', '12 PM', '2 PM', or '4 PM'."""
            h12 = h_24 % 12 if h_24 % 12 != 0 else 12
            ampm = 'AM' if h_24 < 12 else 'PM'
            if m == 0:
                return f"{h12} {ampm}"
            # Off-the-hour fallback (e.g., last point at 3:45 PM)
            return f"{h12}:{m:02d} {ampm}"

        _tloop = _time.time()
        for idx, snapshot in enumerate(snapshots):
            if snapshot.total_value <= 0:
                continue

            # Format label with time for intraday (ensure Eastern Time), date only for daily close
            if hasattr(snapshot, 'is_intraday') and snapshot.is_intraday:
                ts = snapshot.timestamp
                if ts.tzinfo is None:
                    ts_et = ts.replace(tzinfo=UTC_TZ).astimezone(ET)
                else:
                    ts_et = ts.astimezone(ET)
                h, m = ts_et.hour, ts_et.minute

                if period == '1D':
                    # Label at 10/12/14 boundaries (when minute close to :00) + always last point
                    is_last = (idx == last_snapshot_index)
                    is_hour_boundary = (h in (10, 12, 14) and m <= 14 and h not in labeled_1d_hours)
                    if is_hour_boundary:
                        labeled_1d_hours.add(h)
                        date_str = _format_1d_hour_label(h, 0)
                    elif is_last:
                        # Always label last actual data point so user sees end time
                        date_str = _format_1d_hour_label(h, m)
                    else:
                        date_str = ""
                else:
                    # 5D / 1W: label first point of each new ET day as "Mon 5/5"
                    et_day = ts_et.date()
                    if et_day != prev_5d_day:
                        prev_5d_day = et_day
                        date_str = f"{ts_et.strftime('%a')} {ts_et.month}/{ts_et.day}"
                    else:
                        date_str = ""
            else:
                # Daily snapshot mixed in (multi-day periods that include daily)
                date_str = snapshot.date.strftime('%b %d')
            
            # Get S&P 500 value for this timestamp/date
            # For intraday: find closest S&P 500 point at or before this timestamp
            if hasattr(snapshot, 'is_intraday') and snapshot.is_intraday and sp500_map_timestamp:
                # Find closest S&P 500 value at or before this timestamp
                sp500_value = baseline_sp500
                for spy_ts, spy_price in sorted(sp500_map_timestamp.items()):
                    if spy_ts <= snapshot.timestamp:
                        sp500_value = spy_price
                    else:
                        break
            else:
                # For daily: use date-based lookup
                sp500_value = sp500_map.get(snapshot.date, baseline_sp500)
            
            sp500_pct = ((sp500_value - baseline_sp500) / baseline_sp500) * 100
            
            # Cumulative chain-linked TWR up to this snapshot (Session 47)
            pct = twr_series[idx] if idx < len(twr_series) else None
            portfolio_pct = pct if pct is not None else 0.0
            
            chart_data.append({
                'date': date_str,
                'portfolio': round(portfolio_pct, 2),
                'sp500': round(sp500_pct, 2)
            })
        logger.info(f"[CHART-TIMING] intraday_loop: {round(_time.time()-_tloop,2)}s for {len(chart_data)} points from {len(snapshots)} snapshots")
    else:
        # For longer periods: Generate points for S&P 500 dates
        # Sample data to avoid overcrowded charts on mobile screens
        if period in ['5Y']:
            # ~5 years: show ~60 monthly points (every ~21 trading days)
            step = max(1, len(sp500_data) // 60)
        elif period in ['1Y']:
            # ~1 year: show ~50 weekly points (every ~5 trading days)
            step = max(1, len(sp500_data) // 50)
        elif period in ['YTD', '3M']:
            # 3-6 months: every 2-3 trading days for ~30-40 points
            step = max(1, len(sp500_data) // 40)
        else:
            step = 1  # 1M and shorter: every trading day
        
        sampled_sp500 = sp500_data[::step]
        # Always include the last data point
        if sp500_data and sampled_sp500[-1] != sp500_data[-1]:
            sampled_sp500.append(sp500_data[-1])
        
        # Cumulative TWR per snapshot date (Session 47): series is aligned to
        # `snapshots`; later duplicates for a date win (matches snapshot_map).
        twr_by_date = {}
        for _i, _s in enumerate(snapshots):
            if _i < len(twr_series) and twr_series[_i] is not None:
                twr_by_date[_s.date] = twr_series[_i]
        twr_dates_desc = sorted(twr_by_date.keys(), reverse=True)
        
        last_known_pct = 0.0  # Track last known portfolio % for gap-filling

        # Sparse boundary labels for longer periods (matches industry-standard charts):
        # - 1M:  first point of each ISO week (Monday-style boundary)
        # - 3M / YTD: first point of each calendar month
        # - 1Y / 5Y: first point of each calendar month, year suffix when crossing years
        labeled_months = set()    # (year, month) tuples already labeled
        labeled_iso_weeks = set() # (year, iso_week) tuples already labeled
        last_idx = len(sampled_sp500) - 1
        crosses_year = False
        if sampled_sp500:
            crosses_year = sampled_sp500[0].date.year != sampled_sp500[-1].date.year

        for idx, sp500_record in enumerate(sampled_sp500):
            d = sp500_record.date
            is_last = (idx == last_idx)

            if period == '1M':
                wk = (d.isocalendar()[0], d.isocalendar()[1])
                if wk not in labeled_iso_weeks or is_last:
                    labeled_iso_weeks.add(wk)
                    date_str = f"{d.month}/{d.day}"  # "5/5"
                else:
                    date_str = ""
            elif period in ('3M', 'YTD'):
                ym = (d.year, d.month)
                if ym not in labeled_months or is_last:
                    labeled_months.add(ym)
                    # YTD-style: month name only ("Jan", "Feb", ...). Last point may be mid-month.
                    if is_last and d.day > 7:
                        date_str = d.strftime('%b %d')  # "May 8" for the actual last point
                    else:
                        date_str = d.strftime('%b')      # "May"
                else:
                    date_str = ""
            elif period in ('1Y', '5Y'):
                ym = (d.year, d.month)
                if ym not in labeled_months or is_last:
                    labeled_months.add(ym)
                    if crosses_year:
                        date_str = d.strftime("%b '%y")  # "Mar '26"
                    else:
                        date_str = d.strftime('%b')       # "Mar"
                else:
                    date_str = ""
            else:
                # Fallback for any unforeseen period
                date_str = f"{d.month}/{d.day}"
            
            # S&P 500 percentage from user's baseline (both lines start at 0%)
            sp500_value = float(sp500_record.close_price)
            sp500_pct = ((sp500_value - baseline_sp500) / baseline_sp500) * 100
            
            # Portfolio percentage: cumulative chain-linked TWR (flow-adjusted)
            if sp500_record.date in twr_by_date:
                last_known_pct = twr_by_date[sp500_record.date]
            else:
                # No snapshot for this date — gap-fill from most recent prior date
                for s_date in twr_dates_desc:
                    if s_date < sp500_record.date:
                        last_known_pct = twr_by_date[s_date]
                        break
            
            chart_data.append({
                'date': date_str,
                'portfolio': round(last_known_pct, 2),
                'sp500': round(sp500_pct, 2)
            })
    
    logger.info(f"Generated {len(chart_data)} chart points")
    if chart_data:
        dates_generated = [p['date'] for p in chart_data]
        logger.info(f"Chart dates: FIRST={dates_generated[0]}, LAST={dates_generated[-1]}")
        logger.info(f"All dates: {dates_generated}")
    return chart_data


def calculate_dietz_return(snapshots: List[PortfolioSnapshot], end_date: date) -> float:
    """
    RETIRED window Modified Dietz (production headline until 2026-08-31,
    Session 47). Kept ONLY for the read-only /admin/compare-dietz-twr diff
    tool; production charts/headline/leaderboard use calculate_twr_return
    (TWR = the day-one copier's experienced return — see its docstring).
    Formula: (V_end - V_start - CF_net) / (V_start + W * CF_net), W =
    day-weighted average timing of max_cash_deployed increases.
    """
    if not snapshots:
        return 0.0
    first_snapshot = snapshots[0]
    last_snapshot = snapshots[-1]
    V_start = first_snapshot.total_value
    V_end = last_snapshot.total_value
    CF_net = max(0.0, last_snapshot.max_cash_deployed - first_snapshot.max_cash_deployed)
    actual_period_days = (end_date - first_snapshot.date).days

    if actual_period_days == 0:
        W = 0.0
    elif CF_net == 0:
        W = 0.5
    else:
        weighted_cf = 0.0
        prev_deployed = first_snapshot.max_cash_deployed
        for snapshot in snapshots[1:]:
            capital_added = snapshot.max_cash_deployed - prev_deployed
            if capital_added > 0:
                days_remaining = (end_date - snapshot.date).days
                weight = days_remaining / actual_period_days
                weighted_cf += capital_added * weight
            prev_deployed = snapshot.max_cash_deployed
        W = weighted_cf / CF_net

    denominator = V_start + (W * CF_net)
    if denominator == 0:
        return 0.0
    return round(((V_end - V_start - CF_net) / denominator) * 100, 2)


def calculate_twr_return(snapshots) -> Optional[Dict]:
    """
    Chain-linked time-weighted return (TWR) over ordered snapshot-like objects
    (requires .total_value and .max_cash_deployed).

    DECISION (owner, 2026-08-31 Session 47): TWR is the number a copy-trading
    subscriber actually experiences, and matching the subscriber's experience to
    the advertised % is the product promise. A day-one copier mirrors the
    creator's ALLOCATION with their own fixed pot, so their gain is the
    creator's daily portfolio returns compounded — the creator's deposits never
    enter the copier's math. Modified Dietz (current headline) instead answers
    "what did the CREATOR earn on their average deployed capital"; with our
    bots' large mid-window deploys the two diverge exactly like the AutoPilot
    "+80% shown / +60% received" criticism. Worked example: $100k flat for 10
    weeks, +$100k deployed, whole book +10% over the final 2 weeks ->
    copier +10%, TWR +10%, Dietz (220k-100k-100k)/(100k + (2/12)*100k) = +17.1%.

    Math: r_t = (V_t - V_{t-1} - F_t) / (V_{t-1} + F_t), compounded; F_t = that
    day's INCREASE in max_cash_deployed (only-increases invariant = new outside
    capital; redeploying internal cash_proceeds is not a flow). The flow gets
    start-of-day weight (denominator includes F_t): deploys execute intraday,
    so the new capital was at work during day t, and this keeps day-t itself
    from overstating gains earned by the new money.

    Robustness: zero/None total_value rows are skipped (pre-activity);
    None/zero max_cash_deployed carries the previous value forward (unknown,
    flow 0) so one unbackfilled row cannot fabricate a phantom flow.

    Returns {'twr_return': pct, 'points': n, 'flow_days': n, 'flows_total': $,
    'series': cumulative pct aligned to snapshots (None = unusable row)}
    or None if no usable (positive-value) baseline exists.
    PRODUCTION as of Session 47: this IS the headline + chart methodology.
    """
    baseline = None
    baseline_idx = -1
    for idx, s in enumerate(snapshots):
        if s.total_value and s.total_value > 0:
            baseline = s
            baseline_idx = idx
            break
    if baseline is None:
        return None

    series: List[Optional[float]] = [None] * len(snapshots)
    series[baseline_idx] = 0.0
    prev_v = float(baseline.total_value)
    prev_mcd = float(baseline.max_cash_deployed or 0.0)
    cumulative = 1.0
    points = 1
    flow_days = 0
    flows_total = 0.0

    for i in range(baseline_idx + 1, len(snapshots)):
        s = snapshots[i]
        if not s.total_value or s.total_value <= 0:
            continue
        raw_mcd = s.max_cash_deployed
        mcd = float(raw_mcd) if (raw_mcd and raw_mcd > 0) else prev_mcd
        flow = max(0.0, mcd - prev_mcd)
        denom = prev_v + flow
        if denom > 0:
            cumulative *= 1.0 + ((float(s.total_value) - prev_v - flow) / denom)
            points += 1
            if flow > 0:
                flow_days += 1
                flows_total += flow
        series[i] = round((cumulative - 1.0) * 100, 2)
        prev_v = float(s.total_value)
        prev_mcd = mcd

    return {
        'twr_return': round((cumulative - 1.0) * 100, 2),
        'points': points,
        'flow_days': flow_days,
        'flows_total': round(flows_total, 2),
        'series': series,
    }


_sp500_benchmark_cache: Dict[tuple, float] = {}

def _calculate_sp500_benchmark(start_date: date, end_date: date) -> float:
    """
    Calculate S&P 500 return for the period using simple percentage.
    
    Note: Uses simple return (not Modified Dietz) since it's a passive benchmark
    with no cash flows. Just measures market movement.
    
    Cached in-memory: many users share the same start/end dates during bulk
    leaderboard computation, avoiding redundant DB queries at 10k scale.
    
    Args:
        start_date: Period start
        end_date: Period end
        
    Returns:
        S&P 500 percentage return
    """
    cache_key = (start_date, end_date)
    if cache_key in _sp500_benchmark_cache:
        return _sp500_benchmark_cache[cache_key]
    # For 1D periods (start_date == end_date), try intraday data first, fall back to daily
    if start_date == end_date:
        # Query intraday SPY data for this date
        intraday_data = MarketData.query.filter(
            and_(
                MarketData.ticker == 'SPY_INTRADAY',
                MarketData.date == start_date,
                MarketData.timestamp.isnot(None)
            )
        ).order_by(MarketData.timestamp.asc()).all()
        
        if not intraday_data or len(intraday_data) < 2:
            # Fallback: use previous trading day close vs this day close from daily data
            prev_day = start_date - timedelta(days=1)
            while prev_day.weekday() >= 5:
                prev_day = prev_day - timedelta(days=1)
            
            prev_sp500 = MarketData.query.filter(
                and_(MarketData.ticker == 'SPY_SP500', MarketData.date == prev_day)
            ).first()
            curr_sp500 = MarketData.query.filter(
                and_(MarketData.ticker == 'SPY_SP500', MarketData.date == end_date)
            ).first()
            
            if prev_sp500 and curr_sp500 and float(prev_sp500.close_price) > 0:
                result = ((float(curr_sp500.close_price) - float(prev_sp500.close_price)) / float(prev_sp500.close_price)) * 100
                _sp500_benchmark_cache[cache_key] = result
                return result
            
            logger.warning(f"Missing SPY data for 1D: intraday and daily fallback both failed for {start_date}")
            _sp500_benchmark_cache[cache_key] = 0.0
            return 0.0
        
        # SPY_INTRADAY already contains S&P 500 value (spy_price * 10 from intraday cron)
        # Do NOT multiply by 10 again or you'll get ~900% gains!
        start_price = intraday_data[0].close_price
        end_price = intraday_data[-1].close_price
        
        if start_price == 0:
            logger.warning(f"Zero SPY_INTRADAY start price on {start_date}")
            _sp500_benchmark_cache[cache_key] = 0.0
            return 0.0
        
        sp500_return = ((end_price - start_price) / start_price) * 100
        
        logger.debug(
            f"S&P 500 intraday return: {sp500_return:.2f}% "
            f"({start_date} 9:30 AM: ${start_price:.2f} -> 4:00 PM: ${end_price:.2f})"
        )
        
        _sp500_benchmark_cache[cache_key] = sp500_return
        return sp500_return
    
    # For multi-day periods, use daily SPY_SP500 data
    start_price_data = MarketData.query.filter(
        and_(
            MarketData.ticker == 'SPY_SP500',
            MarketData.date >= start_date
        )
    ).order_by(MarketData.date.asc()).first()
    
    end_price_data = MarketData.query.filter(
        and_(
            MarketData.ticker == 'SPY_SP500',
            MarketData.date <= end_date
        )
    ).order_by(MarketData.date.desc()).first()
    
    if not start_price_data or not end_price_data:
        logger.warning(f"Missing SPY_SP500 data for period {start_date} to {end_date}")
        _sp500_benchmark_cache[cache_key] = 0.0
        return 0.0
    
    start_price = start_price_data.close_price
    end_price = end_price_data.close_price
    
    if start_price == 0:
        logger.warning(f"Zero S&P 500 start price on {start_price_data.date}")
        _sp500_benchmark_cache[cache_key] = 0.0
        return 0.0
    
    sp500_return = ((end_price - start_price) / start_price) * 100
    
    logger.debug(
        f"S&P 500 return: {sp500_return:.2f}% "
        f"({start_price_data.date}: ${start_price:.2f} -> {end_price_data.date}: ${end_price:.2f})"
    )
    
    _sp500_benchmark_cache[cache_key] = sp500_return
    return sp500_return


def get_period_dates(period: str, user_id: Optional[int] = None) -> Tuple[date, date]:
    """
    Calculate start and end dates for a given period.
    
    Handles special cases like user joining mid-period (e.g., June for YTD).
    
    Args:
        period: Period string ('1D', '5D', '1M', '3M', 'YTD', '1Y', '5Y', 'MAX')
        user_id: Optional user ID (for MAX period to get first snapshot date)
        
    Returns:
        (start_date, end_date) tuple
        
    Raises:
        ValueError: If period is invalid
    """
    # Import here to avoid circular dependency
    try:
        from portfolio_performance import get_market_date
    except ImportError:
        # Fallback: define inline if portfolio_performance not available
        from zoneinfo import ZoneInfo
        MARKET_TZ = ZoneInfo('America/New_York')
        def get_market_date():
            return datetime.now(MARKET_TZ).date()
    
    today = get_market_date()  # Today in ET timezone
    
    # Find most recent market day (Mon-Fri) - important for weekends
    end_date = today
    while end_date.weekday() >= 5:  # Saturday=5, Sunday=6
        end_date = end_date - timedelta(days=1)
    
    period_upper = period.upper()
    
    if period_upper == '1D':
        # Show most recent market day's intraday data
        start_date = end_date
    elif period_upper == '5D':
        # Get last 5 trading days (Mon-Fri), skipping weekends
        # Start from the day before end_date and count back 4 more trading days
        trading_days_needed = 4  # We already have end_date
        current_date = end_date - timedelta(days=1)
        
        while trading_days_needed > 0:
            # Skip weekends (Saturday=5, Sunday=6)
            if current_date.weekday() < 5:
                trading_days_needed -= 1
            current_date = current_date - timedelta(days=1)
        
        # current_date is now 1 day before the start date, so add 1 day
        start_date = current_date + timedelta(days=1)
    elif period_upper == '1M':
        start_date = end_date - timedelta(days=30)
    elif period_upper == '3M':
        start_date = end_date - timedelta(days=90)
    elif period_upper == 'YTD':
        start_date = date(end_date.year, 1, 1)  # Jan 1 of current year
    elif period_upper == '1Y':
        start_date = end_date - timedelta(days=365)
    elif period_upper == '5Y':
        start_date = end_date - timedelta(days=365 * 5)
    elif period_upper == 'MAX':
        # Get first snapshot date for this user (or all users if user_id not provided)
        if user_id:
            first_snapshot = PortfolioSnapshot.query.filter_by(
                user_id=user_id
            ).order_by(PortfolioSnapshot.date.asc()).first()
        else:
            first_snapshot = PortfolioSnapshot.query.order_by(
                PortfolioSnapshot.date.asc()
            ).first()
        
        start_date = first_snapshot.date if first_snapshot else end_date
    else:
        raise ValueError(f"Invalid period: {period}")
    
    logger.debug(f"Period {period_upper}: {start_date} to {end_date}")
    return start_date, end_date


# Backward compatibility wrappers for gradual migration
def calculate_modified_dietz_return(user_id: int, start_date: date, end_date: date) -> float:
    """
    DEPRECATED: Use calculate_portfolio_performance() instead.
    
    Kept for backward compatibility during migration. NOTE (Session 47): the
    headline this wraps is now chain-linked TWR, no longer Modified Dietz —
    the name is historical. For actual window Dietz use calculate_dietz_return.
    """
    logger.warning(
        "calculate_modified_dietz_return() is deprecated. "
        "Use calculate_portfolio_performance() instead."
    )
    result = calculate_portfolio_performance(user_id, start_date, end_date, include_chart_data=False)
    return result['portfolio_return'] / 100  # Return as decimal (0.2857) not percentage (28.57)
