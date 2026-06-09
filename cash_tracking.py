"""
Cash Tracking Module - Implements max_cash_deployed and cash_proceeds logic

DESIGN PRINCIPLES:
1. max_cash_deployed = cumulative capital user has ever invested
2. cash_proceeds = uninvested cash from sales waiting to be redeployed
3. Portfolio value = stock_value + cash_proceeds
4. Performance = (portfolio_value - max_cash_deployed) / max_cash_deployed

TRANSACTION LOGIC:
- BUY/INITIAL: Use cash_proceeds first, then deploy new capital
- SELL: Add sale proceeds to cash_proceeds

EXAMPLE FLOW:
Day 1: Add 10 TSLA @ $5
  → max_cash_deployed = $50, cash_proceeds = $0

Day 2: Buy 5 AAPL @ $2  
  → max_cash_deployed = $60, cash_proceeds = $0

Day 3: Sell 5 AAPL @ $1
  → max_cash_deployed = $60, cash_proceeds = $5

Day 4: Buy 10 SPY @ $1 (costs $10)
  → Uses $5 cash_proceeds, deploys $5 new
  → max_cash_deployed = $65, cash_proceeds = $0
"""

from models import User, Stock, Transaction
from sqlalchemy import func
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

# Push notification integration flag - set to True when Firebase is configured
PUSH_NOTIFICATIONS_ENABLED = True

def process_transaction(db, user_id, ticker, quantity, price, transaction_type, timestamp=None, position_before_qty=None, price_source=None, suppress_notifications=False, suppress_trader_email=False):
    """
    Process a transaction and update user's cash tracking fields.
    
    Args:
        db: SQLAlchemy db session
        user_id: User ID
        ticker: Stock ticker symbol
        quantity: Number of shares
        price: Price per share
        transaction_type: 'buy', 'sell', or 'initial'
        timestamp: Transaction timestamp (default: now)
        price_source: Where the price came from ('cached', 'bulk_api', 'single_api', 'manual', 'email')
        suppress_notifications: If True, skip push + email notifications and
            the daily-trade-cap check. Used by admin bulk migrations
            (e.g. /admin/migrate-bot-holdings) so we don't spam every
            subscriber when the migration emits 20+ trades back-to-back.
        suppress_trader_email: If True, skip ONLY the trader's own confirmation
            email (subscriber push + subscriber emails still fire). Used by the
            queued-trade path, which sends its own richer "Queued Trade Executed"
            email — without this the trader would receive two emails per fill.
    
    Returns:
        dict with updated max_cash_deployed and cash_proceeds
    """
    # CRITICAL: Use SELECT ... FOR UPDATE to prevent race conditions when
    # multiple trades execute concurrently (e.g., rapid-fire buys/sells).
    # Without this lock, concurrent reads of cash_proceeds/max_cash_deployed
    # can cause stale values, leading to incorrect capital tracking.
    from sqlalchemy import text as _text
    user = db.session.query(User).filter(User.id == user_id).with_for_update().first()
    if not user:
        raise ValueError(f"User {user_id} not found")
    
    transaction_value = quantity * price

    # Normalize transaction_type to canonical lowercase. The cash-tracking replay
    # and drift audits match lowercase only ('buy'/'initial'/'sell'/'dividend'), so
    # a stray uppercase record (e.g. 'SELL' from a legacy/admin path) would be
    # silently ignored by the replay and diverge from holdings. Normalizing every
    # write here keeps the ledger canonical and prevents that landmine.
    transaction_type = (transaction_type or '').strip().lower()

    if transaction_type in ('buy', 'initial'):
        # BUYING STOCK
        logger.info(f"Processing {transaction_type}: {quantity} {ticker} @ ${price} = ${transaction_value}")
        logger.info(f"Before: max_cash_deployed=${user.max_cash_deployed}, cash_proceeds=${user.cash_proceeds}")
        
        if user.cash_proceeds >= transaction_value:
            # Have enough cash proceeds to cover entire purchase
            user.cash_proceeds -= transaction_value
            logger.info(f"Used ${transaction_value} from cash_proceeds")
        else:
            # Use all available cash proceeds, then deploy new capital
            cash_used = user.cash_proceeds
            new_capital_needed = transaction_value - cash_used
            
            user.cash_proceeds = 0
            user.max_cash_deployed += new_capital_needed
            
            logger.info(f"Used ${cash_used} cash_proceeds + deployed ${new_capital_needed} new capital")
        
        logger.info(f"After: max_cash_deployed=${user.max_cash_deployed}, cash_proceeds=${user.cash_proceeds}")
    
    elif transaction_type == 'sell':
        # SELLING STOCK
        logger.info(f"Processing sell: {quantity} {ticker} @ ${price} = ${transaction_value}")
        logger.info(f"Before: max_cash_deployed=${user.max_cash_deployed}, cash_proceeds=${user.cash_proceeds}")
        
        # Add sale proceeds to cash_proceeds
        user.cash_proceeds += transaction_value
        
        logger.info(f"Added ${transaction_value} to cash_proceeds")
        logger.info(f"After: max_cash_deployed=${user.max_cash_deployed}, cash_proceeds=${user.cash_proceeds}")
    
    elif transaction_type == 'dividend':
        # DIVIDEND RECEIVED — adds to cash_proceeds (income), does NOT increase max_cash_deployed
        # This correctly flows through Modified Dietz: increases V_end without increasing CF_net
        logger.info(f"Processing dividend: {ticker} ${transaction_value} ({quantity} shares @ ${price}/share)")
        logger.info(f"Before: max_cash_deployed=${user.max_cash_deployed}, cash_proceeds=${user.cash_proceeds}")
        
        user.cash_proceeds += transaction_value
        
        logger.info(f"Added ${transaction_value} dividend to cash_proceeds")
        logger.info(f"After: max_cash_deployed=${user.max_cash_deployed}, cash_proceeds=${user.cash_proceeds}")
    
    else:
        raise ValueError(f"Invalid transaction_type: {transaction_type}")
    
    # Create transaction record
    transaction = Transaction(
        user_id=user_id,
        ticker=ticker,
        quantity=quantity,
        price=price,
        transaction_type=transaction_type,
        timestamp=timestamp or datetime.utcnow(),
        price_source=price_source
    )
    db.session.add(transaction)
    
    # CRITICAL: Merge user to handle cross-session scenarios (Vercel serverless)
    # merge() updates the session's copy of the user with our changes
    db.session.merge(user)
    
    # Calculate position percentage for sell notifications (shared by push + email)
    position_pct = None
    if transaction_type == 'sell' and position_before_qty and position_before_qty > 0:
        position_pct = round((quantity / position_before_qty) * 100, 1)

    # Send push notifications to subscribers (Phase 1 - Mobile App).
    # Suppressed for admin bulk migrations so subscribers don't get spammed
    # when we emit 20+ rebalancing trades in one shot.
    if not suppress_notifications and PUSH_NOTIFICATIONS_ENABLED and transaction_type in ('buy', 'sell'):
        try:
            from push_notification_service import notify_subscribers_of_trade
            notification_result = notify_subscribers_of_trade(
                db=db,
                trader_user_id=user_id,
                action=transaction_type,
                ticker=ticker,
                quantity=quantity,
                price=price,
                position_pct=position_pct
            )
            logger.info(f"Push notifications sent: {notification_result.get('success_count', 0)} success, {notification_result.get('failure_count', 0)} failures")
        except Exception as e:
            # Don't fail the trade if notifications fail
            logger.warning(f"Failed to send trade notifications: {e}")

    # Send email trade confirmation to trader + email notifications to subscribers
    if not suppress_notifications and transaction_type in ('buy', 'sell'):
        try:
            from services.notification_utils import send_trade_confirmation_email, notify_subscribers_via_email
            # Email confirmation to the trader (if they have email notifications on).
            # Skipped when the caller sends its own trader email (queued-trade path)
            # so the trader doesn't get two emails for a single execution.
            if not suppress_trader_email and getattr(user, 'email_notifications_enabled', True):
                conf_result = send_trade_confirmation_email(user, transaction_type, ticker, quantity, price, position_pct)
                logger.info(f"Trade confirmation email: {conf_result.get('status')}")
            # Email notifications to subscribers
            email_result = notify_subscribers_via_email(db, user_id, transaction_type, ticker, quantity, price, position_pct)
            logger.info(f"Subscriber emails: {email_result.get('sent', 0)} sent, {email_result.get('failed', 0)} failed, {email_result.get('rate_limited', 0)} rate-limited")
        except Exception as e:
            logger.warning(f"Failed to send email notifications: {e}")

    # Check daily trade frequency cap (non-blocking, best-effort).
    # Also skipped under suppress_notifications since bulk migrations will
    # blow past the cap immediately and the alert isn't actionable.
    if not suppress_notifications and transaction_type in ('buy', 'sell'):
        try:
            _check_daily_trade_cap(db, user_id, user)
        except Exception as e:
            logger.debug(f"Trade cap check failed (non-fatal): {e}")

    return {
        'max_cash_deployed': user.max_cash_deployed,
        'cash_proceeds': user.cash_proceeds,
        'transaction_value': transaction_value
    }


DAILY_TRADE_CAP = 50  # Notify user when they hit this many trades/day
_trade_cap_notified = set()  # In-memory set of (user_id, date_str) already notified

def _check_daily_trade_cap(db, user_id, user):
    """Send a one-time email when a user hits the daily trade cap."""
    from datetime import date as date_type
    today_str = date_type.today().isoformat()
    key = (user_id, today_str)
    if key in _trade_cap_notified:
        return

    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    trade_count = Transaction.query.filter(
        Transaction.user_id == user_id,
        Transaction.timestamp >= today_start,
        Transaction.transaction_type.in_(['buy', 'sell'])
    ).count()

    if trade_count >= DAILY_TRADE_CAP:
        _trade_cap_notified.add(key)
        email = getattr(user, 'email', None)
        if email and getattr(user, 'email_notifications_enabled', True):
            try:
                from services.notification_utils import send_email
                send_email(
                    email,
                    f"Heads up: {trade_count} trades today",
                    f"Hey {user.username or 'there'},\n\n"
                    f"You've placed {trade_count} trades today. Here are a few things to keep in mind:\n\n"
                    f"• Rate limit: 20 trades per minute. Requests beyond this will be temporarily blocked.\n"
                    f"• Stock prices are cached for 90 seconds, so rapid trades on the same ticker "
                    f"will use the same price.\n"
                    f"• Each trade generates a notification to all of your subscribers.\n\n"
                    f"— ApesTogether"
                )
                logger.info(f"Daily trade cap email sent to user {user_id} ({trade_count} trades)")
            except Exception as e:
                logger.debug(f"Trade cap email failed: {e}")


def calculate_portfolio_value_with_cash(user_id, target_date=None):
    """
    Calculate total portfolio value = stock_value + cash_proceeds.
    
    Args:
        user_id: User ID
        target_date: Calculate value as of this date (default: today)
    
    Returns:
        dict with stock_value, cash_proceeds, and total_value
    """
    user = User.query.get(user_id)
    if not user:
        return {'stock_value': 0, 'cash_proceeds': 0, 'total_value': 0}

    from portfolio_performance import PortfolioPerformanceCalculator
    calculator = PortfolioPerformanceCalculator()

    if target_date:
        # Historical path: holdings AND cash are both reconstructed from the
        # transaction history as of target_date, so they are internally consistent.
        stock_value = calculator.calculate_portfolio_value(user_id, target_date)
        cash_proceeds = calculate_cash_proceeds_as_of_date(user_id, target_date)
    else:
        # LIVE path read-skew guard. stock_value comes from the Stock holdings table
        # while cash_proceeds comes from the denormalized User.cash_proceeds field —
        # TWO separate reads. A bot trade updates both atomically, but if it commits
        # BETWEEN these reads the intraday snapshot stores post-trade holdings with
        # pre-trade cash (phantom spike on a buy) or pre-trade holdings with post-trade
        # cash (phantom dip on a sell) — a one-tick artifact that snaps back on the next
        # collection. Eliminate it: read cash, compute stock_value, then re-read cash;
        # if cash moved, a trade landed mid-read, so recompute holdings so BOTH sides
        # reflect the same committed state. Converges on the first iteration whenever no
        # trade is concurrently committing (one extra lightweight SELECT, no recompute).
        from models import db
        db.session.refresh(user)
        cash_proceeds = user.cash_proceeds
        stock_value = calculator.calculate_portfolio_value(user_id, None)
        for _attempt in range(3):
            db.session.refresh(user)
            if user.cash_proceeds == cash_proceeds:
                break
            cash_proceeds = user.cash_proceeds
            stock_value = calculator.calculate_portfolio_value(user_id, None)

    total_value = stock_value + cash_proceeds

    return {
        'stock_value': stock_value,
        'cash_proceeds': cash_proceeds,
        'total_value': total_value
    }

def calculate_cash_proceeds_as_of_date(user_id, target_date):
    """
    Calculate cash_proceeds as of a specific date by replaying transaction history.
    
    This is needed for historical snapshots and charts.
    """
    transactions = Transaction.query.filter(
        Transaction.user_id == user_id,
        func.date(Transaction.timestamp) <= target_date
    ).order_by(Transaction.timestamp).all()
    
    cash_proceeds = 0.0
    max_cash_deployed = 0.0
    
    for txn in transactions:
        transaction_value = txn.quantity * txn.price
        
        if txn.transaction_type in ('buy', 'initial'):
            # Use cash proceeds first, then deploy new capital
            if cash_proceeds >= transaction_value:
                cash_proceeds -= transaction_value
            else:
                new_capital = transaction_value - cash_proceeds
                cash_proceeds = 0
                max_cash_deployed += new_capital
        
        elif txn.transaction_type == 'sell':
            cash_proceeds += transaction_value
        
        elif txn.transaction_type == 'dividend':
            cash_proceeds += transaction_value
    
    return cash_proceeds

def calculate_performance(user_id):
    """
    Calculate user's performance percentage.
    
    Formula: (current_value - max_cash_deployed) / max_cash_deployed * 100
    
    Returns:
        float: Performance percentage (e.g., 8.33 for +8.33%)
    """
    user = User.query.get(user_id)
    if not user or user.max_cash_deployed == 0:
        return 0.0
    
    portfolio_data = calculate_portfolio_value_with_cash(user_id)
    current_value = portfolio_data['total_value']
    
    performance = ((current_value - user.max_cash_deployed) / user.max_cash_deployed) * 100
    
    return performance

def backfill_cash_tracking_for_user(db, user_id):
    """
    Backfill max_cash_deployed and cash_proceeds for existing user.
    
    Replays all transactions in chronological order to rebuild cash state.
    """
    user = User.query.get(user_id)
    if not user:
        raise ValueError(f"User {user_id} not found")
    
    # Get all transactions in chronological order
    transactions = Transaction.query.filter_by(user_id=user_id)\
        .order_by(Transaction.timestamp).all()
    
    if not transactions:
        logger.warning(f"No transactions found for user {user_id}")
        return
    
    # Reset to zero
    user.max_cash_deployed = 0.0
    user.cash_proceeds = 0.0
    
    # Replay all transactions
    for txn in transactions:
        transaction_value = txn.quantity * txn.price
        
        if txn.transaction_type in ('buy', 'initial'):
            if user.cash_proceeds >= transaction_value:
                user.cash_proceeds -= transaction_value
            else:
                new_capital = transaction_value - user.cash_proceeds
                user.cash_proceeds = 0
                user.max_cash_deployed += new_capital
        
        elif txn.transaction_type == 'sell':
            user.cash_proceeds += transaction_value
        
        elif txn.transaction_type == 'dividend':
            user.cash_proceeds += transaction_value
    
    logger.info(f"Backfilled user {user.username}: max_cash_deployed=${user.max_cash_deployed}, cash_proceeds=${user.cash_proceeds}")
    
    return {
        'max_cash_deployed': user.max_cash_deployed,
        'cash_proceeds': user.cash_proceeds
    }

def backfill_all_users(db):
    """
    Backfill cash tracking for all users.
    
    Run this once after adding max_cash_deployed and cash_proceeds fields.
    """
    from models import User
    
    users = User.query.all()
    results = []
    
    for user in users:
        try:
            result = backfill_cash_tracking_for_user(db, user.id)
            results.append({
                'user_id': user.id,
                'username': user.username,
                'success': True,
                **result
            })
        except Exception as e:
            logger.error(f"Error backfilling user {user.id}: {e}")
            results.append({
                'user_id': user.id,
                'username': user.username,
                'success': False,
                'error': str(e)
            })
    
    db.session.commit()
    return results
