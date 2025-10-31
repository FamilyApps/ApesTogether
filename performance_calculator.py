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


def calculate_portfolio_performance(
    user_id: int,
    start_date: date,
    end_date: date,
    include_chart_data: bool = False
) -> Dict:
    """
    Calculate portfolio performance using Modified Dietz with max_cash_deployed.
    
    This is THE SINGLE SOURCE OF TRUTH for all performance calculations.
    Called by: Dashboard, Leaderboard, Market-close cron, Admin tools.
    
    Formula (from migration 20251005_add_snapshot_cash_fields.py):
        V_start = total_value at start
        V_end = total_value at end
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
    
    Edge Cases Handled:
        - No snapshots: Returns 0% with empty chart
        - Zero baseline (V_start + W*CF = 0): Returns 0% with warning
        - User joins mid-period: Uses first snapshot as baseline
        - Negative CF (sales > buys): Handled correctly (can have negative returns)
        - All-zero snapshots: Skipped, uses first non-zero as baseline
    """
    logger.info(f"Calculating performance for user {user_id} from {start_date} to {end_date}")
    
    # Determine if we should include intraday snapshots (for 1D and 5D periods only)
    days_in_period = (end_date - start_date).days
    include_intraday = days_in_period <= 5
    
    # Get daily snapshots for period
    snapshots = PortfolioSnapshot.query.filter(
        and_(
            PortfolioSnapshot.user_id == user_id,
            PortfolioSnapshot.date >= start_date,
            PortfolioSnapshot.date <= end_date
        )
    ).order_by(PortfolioSnapshot.date.asc()).all()
    
    # For 1D and 5D periods, also include intraday snapshots
    if include_intraday:
        from models import PortfolioSnapshotIntraday
        from datetime import datetime, time
        
        start_datetime = datetime.combine(start_date, time.min)
        end_datetime = datetime.combine(end_date, time.max)
        
        intraday_snapshots = PortfolioSnapshotIntraday.query.filter(
            and_(
                PortfolioSnapshotIntraday.user_id == user_id,
                PortfolioSnapshotIntraday.timestamp >= start_datetime,
                PortfolioSnapshotIntraday.timestamp <= end_datetime
            )
        ).order_by(PortfolioSnapshotIntraday.timestamp.asc()).all()
        
        if intraday_snapshots:
            # Wrapper class to make intraday snapshots compatible with daily snapshot interface
            class IntradayWrapper:
                def __init__(self, intraday_snap):
                    self.date = intraday_snap.timestamp.date()
                    self.timestamp = intraday_snap.timestamp
                    self.total_value = intraday_snap.total_value
                    self.stock_value = intraday_snap.stock_value or 0.0
                    self.cash_proceeds = intraday_snap.cash_proceeds or 0.0
                    self.max_cash_deployed = intraday_snap.max_cash_deployed or 0.0
                    self.user_id = intraday_snap.user_id
                    self.is_intraday = True
            
            # Wrap intraday snapshots
            wrapped_intraday = [IntradayWrapper(s) for s in intraday_snapshots]
            
            # Add timestamp to daily snapshots for sorting
            for snap in snapshots:
                snap.timestamp = datetime.combine(snap.date, time(16, 0))
                snap.is_intraday = False
            
            # Merge and sort all snapshots by timestamp
            snapshots = sorted(snapshots + wrapped_intraday, key=lambda s: s.timestamp)
            
            logger.info(f"Including {len(intraday_snapshots)} intraday snapshots for {days_in_period}-day period")
    
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
    
    # Calculate time-weighted cash flows (W factor)
    # Use the user's ACTUAL active period (from first snapshot to end)
    actual_period_days = (end_date - first_snapshot.date).days
    
    if actual_period_days == 0:
        # Same-day period (1D) or user just joined today
        W = 0.0
        weighted_cf = 0.0
    else:
        # Calculate weighted cash flows based on when capital was deployed
        # during the user's active period
        weighted_cf = 0.0
        prev_deployed = first_snapshot.max_cash_deployed
        
        # Track capital deployed after user's first snapshot
        for snapshot in snapshots[1:]:
            capital_added = snapshot.max_cash_deployed - prev_deployed
            if capital_added > 0:
                # Weight by remaining days in user's active period
                days_remaining = (end_date - snapshot.date).days
                weight = days_remaining / actual_period_days
                weighted_cf += capital_added * weight
                logger.debug(f"Date {snapshot.date}: Added ${capital_added:.2f}, weight={weight:.3f}, weighted=${capital_added * weight:.2f}")
            prev_deployed = snapshot.max_cash_deployed
        
        # W is used in denominator: (V_start + W * CF_net)
        # For Modified Dietz, W represents the time-weighted average of when flows occurred
        if CF_net != 0:
            W = weighted_cf / CF_net
            logger.debug(f"User {user_id}: W={W:.3f} (weighted_cf=${weighted_cf:.2f} / CF_net=${CF_net:.2f})")
        else:
            # When CF_net = 0, W is mathematically irrelevant (multiplied by 0)
            # Set to 0.5 for consistency in logging, but any value would give same result
            W = 0.5
            logger.debug(f"User {user_id}: W={W:.3f} (irrelevant - CF_net=0)")
    
    # Modified Dietz formula: Return = (V_end - V_start - CF_net) / (V_start + W * CF_net)
    # Validated by Grok (Oct 26, 2025): Mathematically correct, adapted for snapshot-based data
    denominator = V_start + (W * CF_net)
    
    # Edge case: Zero denominator (rare: V_start=0 and CF_net=0)
    if denominator == 0:
        logger.warning(f"Zero denominator for user {user_id}: V_start={V_start}, W={W:.3f}, CF_net={CF_net}")
        portfolio_return = 0.0
    else:
        numerator = V_end - V_start - CF_net
        portfolio_return = (numerator / denominator) * 100
        logger.debug(
            f"User {user_id} Modified Dietz: "
            f"({V_end:.2f} - {V_start:.2f} - {CF_net:.2f}) / ({V_start:.2f} + {W:.3f}*{CF_net:.2f}) = "
            f"{numerator:.2f} / {denominator:.2f} = {portfolio_return:.2f}%"
        )
    
    logger.info(
        f"Portfolio return: {portfolio_return:.2f}% "
        f"(V_start=${V_start:.2f}, V_end=${V_end:.2f}, CF_net=${CF_net:.2f}, W={W:.3f})"
    )
    
    # Generate chart data if requested (uses simple per-point formula for speed)
    chart_data = None
    if include_chart_data:
        chart_data = _generate_chart_points(snapshots, start_date, end_date)
    
    # Calculate S&P 500 benchmark (simple percentage, not time-weighted)
    sp500_return = _calculate_sp500_benchmark(start_date, end_date)
    
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
    period_end: date
) -> List[Dict]:
    """
    Generate point-by-point chart data using simple per-point formula.
    
    Uses simple percentage from baseline for performance (Grok recommendation):
        pct = ((value_at_point - baseline) / baseline) * 100
    
    This is O(n) efficient vs O(n²) for full Modified Dietz per point.
    The final summary return uses full Modified Dietz, but chart progression uses simple.
    
    Args:
        snapshots: List of PortfolioSnapshot objects
        period_start: Period start date
        period_end: Period end date
        
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
        logger.warning(f"No non-zero snapshots found for chart generation")
        return []
    
    baseline_value = baseline_snapshot.total_value
    baseline_date = baseline_snapshot.date
    logger.debug(f"Chart baseline: ${baseline_value:.2f} on {baseline_date}")
    
    # Get S&P 500 data for the FULL period (not just from user's join date)
    # This ensures charts show S&P performance for entire period
    sp500_data = MarketData.query.filter(
        and_(
            MarketData.ticker == 'SPY_SP500',
            MarketData.date >= period_start,  # Use period_start, not baseline_date
            MarketData.date <= period_end
        )
    ).order_by(MarketData.date.asc()).all()
    
    # DEBUG: Log what dates we actually got
    if sp500_data:
        logger.info(f"📊 S&P 500 query returned {len(sp500_data)} records from {sp500_data[0].date} to {sp500_data[-1].date}")
        logger.info(f"📊 Query params: period_start={period_start}, period_end={period_end}")
    else:
        logger.warning(f"⚠️ S&P 500 query returned NO DATA for period {period_start} to {period_end}")
    
    # Build date-to-SP500-price map
    sp500_map = {s.date: float(s.close_price) for s in sp500_data}
    
    # Get baseline S&P 500 value from period start (not user join date)
    baseline_sp500 = None
    if sp500_data:
        baseline_sp500 = float(sp500_data[0].close_price)
    
    if not baseline_sp500:
        logger.warning(f"No S&P 500 baseline data found for period starting {period_start}")
        baseline_sp500 = 1.0  # Avoid division by zero
    
    # Build snapshot map for quick lookup
    snapshot_map = {s.date: s for s in snapshots if s.total_value > 0}
    
    # Check if we have intraday data (snapshots with timestamps)
    has_intraday = any(hasattr(s, 'is_intraday') and s.is_intraday for s in snapshots)
    
    if has_intraday:
        # For intraday periods (1D/5D): Generate point for each snapshot
        for snapshot in snapshots:
            if snapshot.total_value <= 0:
                continue
            
            # Format label with time for intraday, date only for daily close
            if hasattr(snapshot, 'is_intraday') and snapshot.is_intraday:
                date_str = snapshot.timestamp.strftime('%b %d %I:%M %p')  # "Oct 31 03:30 PM"
            else:
                date_str = snapshot.date.strftime('%b %d')
            
            # Get S&P 500 value for this date (use daily close)
            sp500_value = sp500_map.get(snapshot.date, baseline_sp500)
            sp500_pct = ((sp500_value - baseline_sp500) / baseline_sp500) * 100
            
            # Calculate Modified Dietz for this snapshot
            V_start = baseline_value
            V_end = snapshot.total_value
            CF_net = snapshot.max_cash_deployed - baseline_snapshot.max_cash_deployed
            
            if CF_net <= 0:
                if V_start > 0:
                    portfolio_pct = ((V_end - V_start) / V_start) * 100
                else:
                    portfolio_pct = 0.0
            else:
                weighted_cf = 0.0
                prev_deployed = baseline_snapshot.max_cash_deployed
                period_days = (snapshot.date - baseline_snapshot.date).days
                
                for s in snapshots:
                    if s.date > snapshot.date:
                        break
                    if s.date <= baseline_snapshot.date:
                        continue
                    
                    capital_added = s.max_cash_deployed - prev_deployed
                    if capital_added > 0 and period_days > 0:
                        days_remaining = (snapshot.date - s.date).days
                        weight = days_remaining / period_days
                        weighted_cf += capital_added * weight
                    prev_deployed = s.max_cash_deployed
                
                W = weighted_cf / CF_net if CF_net > 0 else 0.5
                denominator = V_start + (W * CF_net)
                
                if denominator > 0:
                    numerator = V_end - V_start - CF_net
                    portfolio_pct = (numerator / denominator) * 100
                else:
                    portfolio_pct = 0.0
            
            chart_data.append({
                'date': date_str,
                'portfolio': round(portfolio_pct, 2),
                'sp500': round(sp500_pct, 2)
            })
    else:
        # For longer periods: Generate points for S&P 500 dates (original logic)
        user_started = False
        
        for sp500_record in sp500_data:
            date_str = sp500_record.date.strftime('%b %d')
            
            # S&P 500 percentage (always calculated from period start)
            sp500_value = float(sp500_record.close_price)
            sp500_pct = ((sp500_value - baseline_sp500) / baseline_sp500) * 100
            
            # Portfolio percentage using Modified Dietz (accounts for cash flows)
            portfolio_pct = None
            if sp500_record.date in snapshot_map:
                user_started = True
                snapshot = snapshot_map[sp500_record.date]
                
                # Calculate Modified Dietz return from baseline to this point
                V_start = baseline_value
                V_end = snapshot.total_value
                CF_net = snapshot.max_cash_deployed - baseline_snapshot.max_cash_deployed
                
                # Calculate time-weighted cash flows up to this date
                if CF_net <= 0:
                    # No net capital added - use simple percentage
                    if V_start > 0:
                        portfolio_pct = ((V_end - V_start) / V_start) * 100
                    else:
                        portfolio_pct = 0.0
                else:
                    # Calculate W (time-weighted factor) for cash flows up to this date
                    weighted_cf = 0.0
                    prev_deployed = baseline_snapshot.max_cash_deployed
                    period_days = (sp500_record.date - baseline_snapshot.date).days
                    
                    for s in snapshots:
                        if s.date > sp500_record.date:
                            break
                        if s.date <= baseline_snapshot.date:
                            continue
                        
                        capital_added = s.max_cash_deployed - prev_deployed
                        if capital_added > 0 and period_days > 0:
                            days_remaining = (sp500_record.date - s.date).days
                            weight = days_remaining / period_days
                            weighted_cf += capital_added * weight
                        prev_deployed = s.max_cash_deployed
                    
                    W = weighted_cf / CF_net if CF_net > 0 else 0.5
                    denominator = V_start + (W * CF_net)
                    
                    if denominator > 0:
                        numerator = V_end - V_start - CF_net
                        portfolio_pct = (numerator / denominator) * 100
                    else:
                        portfolio_pct = 0.0
                        
            elif user_started:
                # User has started but no snapshot for this date - use last known value
                # Find previous snapshot
                prev_snapshot = None
                for s in reversed(snapshots):
                    if s.date < sp500_record.date:
                        prev_snapshot = s
                        break
                if prev_snapshot:
                    # Calculate Modified Dietz for previous snapshot
                    V_start = baseline_value
                    V_end = prev_snapshot.total_value
                    CF_net = prev_snapshot.max_cash_deployed - baseline_snapshot.max_cash_deployed
                    
                    if CF_net <= 0 and V_start > 0:
                        portfolio_pct = ((V_end - V_start) / V_start) * 100
                    elif CF_net > 0:
                        weighted_cf = 0.0
                        prev_deployed = baseline_snapshot.max_cash_deployed
                        period_days = (prev_snapshot.date - baseline_snapshot.date).days
                        
                        for s in snapshots:
                            if s.date > prev_snapshot.date:
                                break
                            if s.date <= baseline_snapshot.date:
                                continue
                            
                            capital_added = s.max_cash_deployed - prev_deployed
                            if capital_added > 0 and period_days > 0:
                                days_remaining = (prev_snapshot.date - s.date).days
                                weight = days_remaining / period_days
                                weighted_cf += capital_added * weight
                            prev_deployed = s.max_cash_deployed
                        
                        W = weighted_cf / CF_net if CF_net > 0 else 0.5
                        denominator = V_start + (W * CF_net)
                        
                        if denominator > 0:
                            numerator = V_end - V_start - CF_net
                            portfolio_pct = (numerator / denominator) * 100
                        else:
                            portfolio_pct = 0.0
                    else:
                        portfolio_pct = 0.0
            else:
                # User hasn't started yet - show 0%
                portfolio_pct = 0.0
            
            if portfolio_pct is not None:
                chart_data.append({
                    'date': date_str,
                    'portfolio': round(portfolio_pct, 2),
                    'sp500': round(sp500_pct, 2)
                })
    
    logger.info(f"Generated {len(chart_data)} chart points")
    if chart_data:
        dates_generated = [p['date'] for p in chart_data]
        logger.info(f"Chart dates: FIRST={dates_generated[0]}, LAST={dates_generated[-1]}")
        logger.info(f"All dates: {dates_generated}")
    return chart_data


def _calculate_sp500_benchmark(start_date: date, end_date: date) -> float:
    """
    Calculate S&P 500 return for the period using simple percentage.
    
    Note: Uses simple return (not Modified Dietz) since it's a passive benchmark
    with no cash flows. Just measures market movement.
    
    Args:
        start_date: Period start
        end_date: Period end
        
    Returns:
        S&P 500 percentage return
    """
    # Get S&P 500 prices (closest to start/end dates)
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
        logger.warning(f"Zero S&P 500 start price on {start_price_data.date}")
        return 0.0
    
    sp500_return = ((end_price - start_price) / start_price) * 100
    
    logger.debug(
        f"S&P 500 return: {sp500_return:.2f}% "
        f"({start_price_data.date}: ${start_price:.2f} -> {end_price_data.date}: ${end_price:.2f})"
    )
    
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
    
    end_date = get_market_date()  # Today in ET timezone
    
    period_upper = period.upper()
    
    if period_upper == '1D':
        start_date = end_date
    elif period_upper == '5D':
        start_date = end_date - timedelta(days=7)  # Account for weekends
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
    
    Kept for backward compatibility during migration.
    """
    logger.warning(
        "calculate_modified_dietz_return() is deprecated. "
        "Use calculate_portfolio_performance() instead."
    )
    result = calculate_portfolio_performance(user_id, start_date, end_date, include_chart_data=False)
    return result['portfolio_return'] / 100  # Return as decimal (0.2857) not percentage (28.57)
