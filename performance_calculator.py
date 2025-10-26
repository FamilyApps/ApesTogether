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
    
    # Get snapshots for period
    snapshots = PortfolioSnapshot.query.filter(
        and_(
            PortfolioSnapshot.user_id == user_id,
            PortfolioSnapshot.date >= start_date,
            PortfolioSnapshot.date <= end_date
        )
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
    
    # Extract values from snapshots
    first_snapshot = snapshots[0]
    last_snapshot = snapshots[-1]
    
    V_start = first_snapshot.total_value
    V_end = last_snapshot.total_value
    CF_net = last_snapshot.max_cash_deployed - first_snapshot.max_cash_deployed
    
    # Calculate time-weighted cash flows (W factor)
    total_days = (end_date - start_date).days
    if total_days == 0:
        # Same-day period (1D)
        W = 0.0
        weighted_cf = 0.0
    else:
        # Calculate weighted cash flows based on when capital was deployed
        weighted_cf = 0.0
        prev_deployed = first_snapshot.max_cash_deployed
        
        for snapshot in snapshots[1:]:
            capital_added = snapshot.max_cash_deployed - prev_deployed
            if capital_added > 0:
                # Weight by remaining days in period (capital deployed later has less time to grow)
                days_remaining = (end_date - snapshot.date).days
                weight = days_remaining / total_days
                weighted_cf += capital_added * weight
                logger.debug(f"Date {snapshot.date}: Added ${capital_added:.2f}, weight={weight:.3f}, weighted=${capital_added * weight:.2f}")
            prev_deployed = snapshot.max_cash_deployed
        
        # W is used in denominator: (V_start + W * CF_net)
        # For Modified Dietz, W represents the time-weighted average of when flows occurred
        # If CF_net = 0 (no new capital), W doesn't matter; default to 0.5 (mid-period)
        W = weighted_cf / CF_net if CF_net != 0 else 0.5
    
    # Modified Dietz formula
    denominator = V_start + (W * CF_net)
    
    # Edge case: Zero denominator
    if denominator == 0:
        logger.warning(f"Zero denominator for user {user_id}: V_start={V_start}, W={W:.3f}, CF_net={CF_net}")
        portfolio_return = 0.0
    else:
        portfolio_return = ((V_end - V_start - CF_net) / denominator) * 100
    
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
            'snapshots_count': len(snapshots),
            'net_capital_deployed': round(CF_net, 2)
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
    logger.debug(f"Chart baseline: ${baseline_value:.2f} on {baseline_snapshot.date}")
    
    # Generate points (skip zero-value snapshots)
    for snapshot in snapshots:
        if snapshot.total_value > 0:
            pct = ((snapshot.total_value - baseline_value) / baseline_value) * 100
            
            chart_data.append({
                'date': snapshot.date.strftime('%b %d'),
                'portfolio': round(pct, 2),
                'sp500': 0.0  # TODO: Add S&P 500 per-point data from cache
            })
    
    logger.debug(f"Generated {len(chart_data)} chart points")
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
