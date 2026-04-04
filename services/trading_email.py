"""
Email Trading Service
Handles inbound emails for trade execution via SendGrid Inbound Parse.

Flow:
  1. User sends email to trade@apestogether.ai with subject like "BUY 10 TSLA"
  2. SendGrid POSTs to /api/email/inbound
  3. We parse the command, fetch live price, execute via cash_tracking, notify subscribers
"""
import re
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

# ── Trade command parser ─────────────────────────────────────────────────────
_TRADE_RE = re.compile(
    r'^\s*(buy|sell)\s+(\d+(?:\.\d+)?)\s+([A-Za-z]{1,10})\s*$',
    re.IGNORECASE
)


def parse_trade_command(text):
    """
    Parse a single trade command string like "BUY 10 TSLA" or "sell 5 AAPL".
    Returns dict {action, ticker, quantity} or None.
    """
    if not text:
        return None
    m = _TRADE_RE.match(text.strip())
    if not m:
        return None
    quantity = float(m.group(2))
    if quantity <= 0 or quantity > 1_000_000:
        return None
    return {
        'action': m.group(1).lower(),
        'ticker': m.group(3).upper(),
        'quantity': quantity,
    }


def parse_email_trade(subject, body):
    """
    Try to extract a trade command from the email subject first, then first body line.
    Returns dict or None.
    """
    if subject:
        trade = parse_trade_command(subject.strip())
        if trade:
            return trade
    if body:
        first_line = body.strip().split('\n')[0]
        trade = parse_trade_command(first_line)
        if trade:
            return trade
    return None


# ── Inbound email handler ────────────────────────────────────────────────────

def handle_inbound_email(from_email, subject, body):
    """
    Full inbound-email trade pipeline.

    Args:
        from_email: sender address (already cleaned of display name)
        subject: email subject line
        body: plain-text body

    Returns:
        dict with 'status' and 'message'
    """
    from models import db, User, Stock, Transaction, QueuedEmailTrade
    from services.notification_utils import send_email, notify_subscribers_via_email
    from cash_tracking import process_transaction
    from timezone_utils import is_market_hours

    # ── 1. Identify user ────────────────────────────────────────────────────
    user = User.query.filter_by(email=from_email).first()
    if not user:
        send_email(
            from_email,
            "Trade Failed – Email Not Registered",
            "This email is not associated with an Apes Together account.\n"
            "Please use the email you signed up with."
        )
        return {'status': 'error', 'message': 'User not found'}

    # ── 2. Parse command ────────────────────────────────────────────────────
    trade = parse_email_trade(subject, body)
    if not trade:
        send_email(
            from_email,
            "Trade Failed – Invalid Format",
            "Could not parse your trade command.\n\n"
            "Format: BUY 10 TSLA  or  SELL 5 AAPL\n"
            "Put the command in the subject line or the first line of the email body."
        )
        return {'status': 'error', 'message': 'Invalid command'}

    action = trade['action']
    ticker = trade['ticker']
    quantity = trade['quantity']

    # ── 2b. Market hours check — queue if after-hours/weekend ────────────
    if not is_market_hours():
        try:
            queued = QueuedEmailTrade(
                user_id=user.id,
                user_email=from_email,
                ticker=ticker,
                action=action,
                quantity=quantity,
            )
            db.session.add(queued)
            db.session.commit()
            logger.info(f"Queued after-hours email trade: {user.username} {action} {quantity} {ticker}")
        except Exception as e:
            db.session.rollback()
            logger.error(f"Failed to queue after-hours trade: {e}")

        send_email(
            from_email,
            f"Trade Queued: {action.upper()} {int(quantity) if quantity == int(quantity) else quantity} {ticker}",
            f"The market is currently closed.\n\n"
            f"Your trade has been queued and will execute automatically at the next market open "
            f"(Mon–Fri, 9:30 AM ET) using the live price at that time.\n\n"
            f"Queued: {action.upper()} {int(quantity) if quantity == int(quantity) else quantity} {ticker}\n\n"
            f"Reply CANCEL to cancel this queued trade."
        )
        return {'status': 'queued', 'message': 'Trade queued for market open'}

    # ── 3. Fetch live price ─────────────────────────────────────────────────
    try:
        from portfolio_performance import get_stock_prices
        prices = get_stock_prices([ticker])
        price = prices.get(ticker)
    except Exception as e:
        logger.error(f"Price fetch failed for {ticker}: {e}")
        price = None

    if not price:
        send_email(
            from_email,
            f"Trade Failed – Price Unavailable for {ticker}",
            f"Unable to fetch a live price for {ticker}. Please try again in a moment."
        )
        return {'status': 'error', 'message': 'Price fetch failed'}

    # ── 4. Validate & execute ───────────────────────────────────────────────
    try:
        existing = Stock.query.filter_by(user_id=user.id, ticker=ticker).first()
        position_before_qty = existing.quantity if existing and action == 'sell' else None

        if action == 'sell':
            if not existing or existing.quantity < quantity:
                available = existing.quantity if existing else 0
                send_email(
                    from_email,
                    f"Trade Failed – Insufficient Shares of {ticker}",
                    f"You tried to sell {quantity} shares of {ticker} but only hold {available}."
                )
                return {'status': 'error', 'message': 'Insufficient shares'}

            existing.quantity -= quantity
            if existing.quantity == 0:
                db.session.delete(existing)
        else:
            # Buy
            if existing:
                total_cost = (existing.purchase_price * existing.quantity) + (price * quantity)
                existing.quantity += quantity
                existing.purchase_price = total_cost / existing.quantity if existing.quantity > 0 else price
            else:
                stock = Stock(ticker=ticker, quantity=quantity, purchase_price=price, user_id=user.id)
                db.session.add(stock)

        # Record transaction + cash tracking
        process_transaction(
            db, user.id, ticker, quantity, price, action,
            timestamp=datetime.utcnow(),
            price_source='email',
            position_before_qty=position_before_qty
        )

        db.session.commit()
        logger.info(f"Email trade executed: {user.username} {action} {quantity} {ticker} @ ${price:.2f}")

    except Exception as e:
        db.session.rollback()
        logger.error(f"Email trade execution failed: {e}")
        send_email(from_email, "Trade Failed", f"An error occurred executing your trade: {e}")
        return {'status': 'error', 'message': str(e)}

    # ── 5. Confirmation email ───────────────────────────────────────────────
    total = quantity * price
    emoji = "📈" if action == 'buy' else "📉"
    position_pct = None
    if action == 'sell' and position_before_qty and position_before_qty > 0:
        position_pct = round((quantity / position_before_qty) * 100, 1)

    send_email(
        from_email,
        f"Trade Confirmed: {action.upper()} {int(quantity) if quantity == int(quantity) else quantity} {ticker}",
        f"{emoji} Trade Confirmed\n\n"
        f"Action: {action.upper()}\n"
        f"Ticker: {ticker}\n"
        f"Quantity: {int(quantity) if quantity == int(quantity) else quantity}\n"
        f"Price: ${price:,.2f}\n"
        f"Total: ${total:,.2f}\n"
        + (f"Position sold: {position_pct}%\n" if position_pct else "")
        + "\nExecuted via email."
    )

    # ── 6. Notify subscribers via email ─────────────────────────────────────
    try:
        notify_subscribers_via_email(
            db, user.id, action, ticker, quantity, price,
            position_pct=position_pct
        )
    except Exception as e:
        logger.warning(f"Subscriber email notification failed: {e}")

    # ── 7. Notify subscribers via push ──────────────────────────────────────
    try:
        from push_notification_service import notify_subscribers_of_trade
        notify_subscribers_of_trade(
            db, user.id, action, ticker, quantity, price,
            position_pct=position_pct
        )
    except Exception as e:
        logger.warning(f"Subscriber push notification failed: {e}")

    return {'status': 'success', 'message': 'Trade executed'}


# ── Market-open queue processor ──────────────────────────────────────────────

def process_queued_trades():
    """
    Execute all queued after-hours email trades.
    Called by the market-open cron job.

    Returns:
        dict with counts: executed, failed, total
    """
    from models import db, QueuedEmailTrade, User, Stock
    from services.notification_utils import send_email, notify_subscribers_via_email
    from cash_tracking import process_transaction

    queued = QueuedEmailTrade.query.filter_by(status='queued').all()
    if not queued:
        logger.info("No queued email trades to process")
        return {'executed': 0, 'failed': 0, 'total': 0}

    # Batch-fetch prices for all unique tickers
    tickers = list({q.ticker for q in queued})
    try:
        from portfolio_performance import get_stock_prices
        prices = get_stock_prices(tickers)
    except Exception as e:
        logger.error(f"Bulk price fetch failed for queued trades: {e}")
        prices = {}

    executed = 0
    failed = 0

    for qt in queued:
        price = prices.get(qt.ticker)
        if not price:
            qt.status = 'failed'
            qt.error_message = 'Price unavailable at market open'
            qt.executed_at = datetime.utcnow()
            failed += 1
            send_email(
                qt.user_email,
                f"Queued Trade Failed – {qt.ticker}",
                f"Your queued trade ({qt.action.upper()} {int(qt.quantity) if qt.quantity == int(qt.quantity) else qt.quantity} {qt.ticker}) "
                f"could not be executed because we were unable to fetch a price for {qt.ticker}.\n\n"
                f"Please try again manually."
            )
            continue

        try:
            user = User.query.get(qt.user_id)
            if not user:
                raise ValueError(f"User {qt.user_id} not found")

            existing = Stock.query.filter_by(user_id=qt.user_id, ticker=qt.ticker).first()
            position_before_qty = existing.quantity if existing and qt.action == 'sell' else None

            if qt.action == 'sell':
                if not existing or existing.quantity < qt.quantity:
                    available = existing.quantity if existing else 0
                    raise ValueError(f"Insufficient shares: have {available}, need {qt.quantity}")
                existing.quantity -= qt.quantity
                if existing.quantity == 0:
                    db.session.delete(existing)
            else:
                if existing:
                    total_cost = (existing.purchase_price * existing.quantity) + (price * qt.quantity)
                    existing.quantity += qt.quantity
                    existing.purchase_price = total_cost / existing.quantity if existing.quantity > 0 else price
                else:
                    stock = Stock(ticker=qt.ticker, quantity=qt.quantity, purchase_price=price, user_id=qt.user_id)
                    db.session.add(stock)

            process_transaction(
                db, qt.user_id, qt.ticker, qt.quantity, price, qt.action,
                timestamp=datetime.utcnow(),
                price_source='queued_email',
                position_before_qty=position_before_qty
            )

            qt.status = 'executed'
            qt.executed_at = datetime.utcnow()
            db.session.commit()
            executed += 1

            # Confirmation email
            total = qt.quantity * price
            emoji = "📈" if qt.action == 'buy' else "📉"
            position_pct = None
            if qt.action == 'sell' and position_before_qty and position_before_qty > 0:
                position_pct = round((qt.quantity / position_before_qty) * 100, 1)

            send_email(
                qt.user_email,
                f"Queued Trade Executed: {qt.action.upper()} {int(qt.quantity) if qt.quantity == int(qt.quantity) else qt.quantity} {qt.ticker}",
                f"{emoji} Your queued trade has been executed at market open.\n\n"
                f"Action: {qt.action.upper()}\n"
                f"Ticker: {qt.ticker}\n"
                f"Quantity: {int(qt.quantity) if qt.quantity == int(qt.quantity) else qt.quantity}\n"
                f"Price: ${price:,.2f}\n"
                f"Total: ${total:,.2f}\n"
                + (f"Position sold: {position_pct}%\n" if position_pct else "")
                + f"\nOriginally queued at {qt.queued_at.strftime('%b %d, %I:%M %p')} UTC."
            )

            # Notify subscribers
            try:
                notify_subscribers_via_email(
                    db, qt.user_id, qt.action, qt.ticker, qt.quantity, price,
                    position_pct=position_pct
                )
            except Exception as e:
                logger.warning(f"Subscriber notification failed for queued trade: {e}")

            try:
                from push_notification_service import notify_subscribers_of_trade
                notify_subscribers_of_trade(
                    db, qt.user_id, qt.action, qt.ticker, qt.quantity, price,
                    position_pct=position_pct
                )
            except Exception as e:
                logger.warning(f"Push notification failed for queued trade: {e}")

            logger.info(f"Queued trade executed: {user.username} {qt.action} {qt.quantity} {qt.ticker} @ ${price:.2f}")

        except Exception as e:
            db.session.rollback()
            qt.status = 'failed'
            qt.error_message = str(e)
            qt.executed_at = datetime.utcnow()
            db.session.commit()
            failed += 1
            logger.error(f"Queued trade failed: {e}")
            send_email(
                qt.user_email,
                f"Queued Trade Failed – {qt.ticker}",
                f"Your queued trade ({qt.action.upper()} {int(qt.quantity) if qt.quantity == int(qt.quantity) else qt.quantity} {qt.ticker}) "
                f"failed: {e}\n\nPlease try again manually."
            )

    result = {'executed': executed, 'failed': failed, 'total': len(queued)}
    logger.info(f"Queued trade processing complete: {result}")
    return result
