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


def parse_email_trades(subject, body):
    """
    Extract one or more trade commands from the email.
    Checks subject first, then every non-blank line of the body.
    Returns list of dicts [{action, ticker, quantity}, ...] (may be empty).
    """
    trades = []
    seen = set()
    # Subject line first
    if subject:
        t = parse_trade_command(subject.strip())
        if t:
            key = (t['action'], t['ticker'], t['quantity'])
            if key not in seen:
                trades.append(t)
                seen.add(key)
    # Then every body line
    if body:
        for line in body.strip().split('\n'):
            line = line.strip()
            if not line:
                continue
            t = parse_trade_command(line)
            if t:
                key = (t['action'], t['ticker'], t['quantity'])
                if key not in seen:
                    trades.append(t)
                    seen.add(key)
    return trades


_CANCEL_RE = re.compile(r'^\s*cancel\s*$', re.IGNORECASE)


def is_cancel_request(subject, body):
    """Check if the email is a CANCEL request for queued trades."""
    if subject and _CANCEL_RE.match(subject.strip()):
        return True
    if body:
        first_line = body.strip().split('\n')[0].strip()
        if _CANCEL_RE.match(first_line):
            return True
    return False


# ── Inbound email handler ────────────────────────────────────────────────────

def handle_inbound_email(from_email, subject, body):
    """
    Full inbound-email trade pipeline.
    Supports:
      - Single trade in subject: "BUY 10 TSLA"
      - Multiple trades in body (one per line)
      - CANCEL command to cancel all queued after-hours trades

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

    # ── 1b. Check for CANCEL command ─────────────────────────────────────
    if is_cancel_request(subject, body):
        return _handle_cancel(db, user, from_email, send_email)

    # ── 2. Parse commands (supports multiple trades) ─────────────────────
    trades = parse_email_trades(subject, body)
    if not trades:
        send_email(
            from_email,
            "Trade Failed – Invalid Format",
            "Could not parse your trade command.\n\n"
            "Supported formats (one trade per line):\n"
            "  BUY 10 TSLA\n"
            "  SELL 5 AAPL\n"
            "  BUY 20 MSFT\n\n"
            "Put a single trade in the subject line, or multiple trades "
            "in the email body (one per line).\n\n"
            "To cancel queued after-hours trades, reply with CANCEL."
        )
        return {'status': 'error', 'message': 'Invalid command'}

    # ── 2b. Market hours check — queue if after-hours/weekend ────────────
    if not is_market_hours():
        return _handle_after_hours(db, user, from_email, trades, send_email)

    # ── 3. Fetch live prices for all tickers ─────────────────────────────
    tickers = list({t['ticker'] for t in trades})
    try:
        from portfolio_performance import get_stock_prices
        prices = get_stock_prices(tickers)
    except Exception as e:
        logger.error(f"Price fetch failed: {e}")
        prices = {}

    # ── 4. Execute each trade ────────────────────────────────────────────
    results = []
    for trade in trades:
        result = _execute_single_trade(
            db, user, from_email, trade, prices, process_transaction,
            notify_subscribers_via_email, send_email
        )
        results.append(result)

    # ── 5. Summary confirmation email ────────────────────────────────────
    succeeded = [r for r in results if r['status'] == 'success']
    failed = [r for r in results if r['status'] != 'success']

    if len(trades) == 1 and succeeded:
        # Single trade — already sent individual confirmation
        pass
    elif len(trades) > 1:
        lines = []
        for r in results:
            t = r['trade']
            qty_str = f"{int(t['quantity'])}" if t['quantity'] == int(t['quantity']) else f"{t['quantity']}"
            if r['status'] == 'success':
                lines.append(f"  ✅ {t['action'].upper()} {qty_str} {t['ticker']} @ ${r.get('price', 0):,.2f}")
            else:
                lines.append(f"  ❌ {t['action'].upper()} {qty_str} {t['ticker']} — {r.get('error', 'failed')}")
        send_email(
            from_email,
            f"Batch Trade Results: {len(succeeded)} executed, {len(failed)} failed",
            f"Your email contained {len(trades)} trades.\n\n"
            + "\n".join(lines)
            + "\n\n— Apes Together"
        )

    return {
        'status': 'success' if succeeded else 'error',
        'message': f'{len(succeeded)} executed, {len(failed)} failed',
        'executed': len(succeeded),
        'failed': len(failed),
    }


def _handle_cancel(db, user, from_email, send_email):
    """Cancel all queued (pending) after-hours trades for this user."""
    from models import QueuedEmailTrade

    queued = QueuedEmailTrade.query.filter_by(
        user_id=user.id, status='queued'
    ).all()

    if not queued:
        send_email(
            from_email,
            "No Queued Trades to Cancel",
            "You don't have any pending queued trades.\n\n— Apes Together"
        )
        return {'status': 'ok', 'message': 'No queued trades'}

    cancelled = []
    for qt in queued:
        qt.status = 'cancelled'
        qty_str = f"{int(qt.quantity)}" if qt.quantity == int(qt.quantity) else f"{qt.quantity}"
        cancelled.append(f"  • {qt.action.upper()} {qty_str} {qt.ticker}")

    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logger.error(f"Cancel queued trades failed: {e}")
        send_email(from_email, "Cancel Failed", f"An error occurred: {e}")
        return {'status': 'error', 'message': str(e)}

    send_email(
        from_email,
        f"Cancelled {len(cancelled)} Queued Trade{'s' if len(cancelled) != 1 else ''}",
        f"The following queued trades have been cancelled:\n\n"
        + "\n".join(cancelled)
        + "\n\nThey will NOT execute at market open.\n\n— Apes Together"
    )
    logger.info(f"Cancelled {len(cancelled)} queued trades for {user.username}")
    return {'status': 'cancelled', 'message': f'{len(cancelled)} trades cancelled'}


def _handle_after_hours(db, user, from_email, trades, send_email):
    """Queue multiple trades for after-hours execution."""
    from models import QueuedEmailTrade

    queued_lines = []
    for trade in trades:
        action, ticker, quantity = trade['action'], trade['ticker'], trade['quantity']
        try:
            queued = QueuedEmailTrade(
                user_id=user.id,
                user_email=from_email,
                ticker=ticker,
                action=action,
                quantity=quantity,
            )
            db.session.add(queued)
            qty_str = f"{int(quantity)}" if quantity == int(quantity) else f"{quantity}"
            queued_lines.append(f"  • {action.upper()} {qty_str} {ticker}")
            logger.info(f"Queued after-hours email trade: {user.username} {action} {quantity} {ticker}")
        except Exception as e:
            logger.error(f"Failed to queue after-hours trade: {e}")

    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to commit queued trades: {e}")

    send_email(
        from_email,
        f"{'Trade' if len(trades) == 1 else f'{len(trades)} Trades'} Queued for Market Open",
        f"The market is currently closed.\n\n"
        f"Your {'trade has' if len(trades) == 1 else 'trades have'} been queued and will "
        f"execute automatically at the next market open "
        f"(Mon–Fri, 9:30 AM ET) using live prices at that time.\n\n"
        f"Queued:\n"
        + "\n".join(queued_lines)
        + "\n\nReply CANCEL to cancel all queued trades.\n\n— Apes Together"
    )
    return {'status': 'queued', 'message': f'{len(trades)} trades queued for market open'}


def _execute_single_trade(db, user, from_email, trade, prices, process_transaction,
                          notify_subscribers_via_email, send_email):
    """Execute one trade and send notifications. Returns result dict."""
    from models import Stock

    action = trade['action']
    ticker = trade['ticker']
    quantity = trade['quantity']
    price = prices.get(ticker)

    if not price:
        return {'status': 'error', 'trade': trade, 'error': f'Price unavailable for {ticker}'}

    try:
        existing = Stock.query.filter_by(user_id=user.id, ticker=ticker).first()
        position_before_qty = existing.quantity if existing and action == 'sell' else None

        if action == 'sell':
            if not existing or existing.quantity < quantity:
                available = existing.quantity if existing else 0
                return {'status': 'error', 'trade': trade, 'error': f'Insufficient shares ({available} held)'}
            existing.quantity -= quantity
            if existing.quantity == 0:
                db.session.delete(existing)
        else:
            if existing:
                total_cost = (existing.purchase_price * existing.quantity) + (price * quantity)
                existing.quantity += quantity
                existing.purchase_price = total_cost / existing.quantity if existing.quantity > 0 else price
            else:
                stock = Stock(ticker=ticker, quantity=quantity, purchase_price=price, user_id=user.id)
                db.session.add(stock)

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
        return {'status': 'error', 'trade': trade, 'error': str(e)}

    # Confirmation + notifications
    total = quantity * price
    emoji = "📈" if action == 'buy' else "📉"
    position_pct = None
    if action == 'sell' and position_before_qty and position_before_qty > 0:
        position_pct = round((quantity / position_before_qty) * 100, 1)

    qty_str = f"{int(quantity)}" if quantity == int(quantity) else f"{quantity}"
    send_email(
        from_email,
        f"Trade Confirmed: {action.upper()} {qty_str} {ticker}",
        f"{emoji} Trade Confirmed\n\n"
        f"Action: {action.upper()}\n"
        f"Ticker: {ticker}\n"
        f"Quantity: {qty_str}\n"
        f"Price: ${price:,.2f}\n"
        f"Total: ${total:,.2f}\n"
        + (f"Position sold: {position_pct}%\n" if position_pct else "")
        + "\nExecuted via email.\n\n— Apes Together"
    )

    try:
        notify_subscribers_via_email(
            db, user.id, action, ticker, quantity, price,
            position_pct=position_pct
        )
    except Exception as e:
        logger.warning(f"Subscriber email notification failed: {e}")

    try:
        from push_notification_service import notify_subscribers_of_trade
        notify_subscribers_of_trade(
            db, user.id, action, ticker, quantity, price,
            position_pct=position_pct
        )
    except Exception as e:
        logger.warning(f"Subscriber push notification failed: {e}")

    return {'status': 'success', 'trade': trade, 'price': price}


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
