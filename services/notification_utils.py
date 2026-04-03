"""
Email notification service via SendGrid API v3.
Includes BCC monitoring, per-user daily rate limiting, and global circuit breaker.
Designed for 10K users scale.
"""
import os
import logging
import time
from datetime import datetime, timedelta
from threading import Lock

logger = logging.getLogger(__name__)

# ── Rate limiting (in-memory, resets on deploy) ─────────────────────────────
_user_send_counts = {}  # {user_email: {'count': N, 'reset_at': timestamp}}
_global_lock = Lock()
_global_sends_this_hour = 0
_global_hour_reset = 0

MAX_EMAILS_PER_USER_PER_DAY = 50
MAX_EMAILS_PER_HOUR_GLOBAL = 1600  # SendGrid Essentials 50K/mo ≈ 1,667/day ≈ safe hourly burst
CIRCUIT_BREAKER_FAILURES = 5       # consecutive failures before tripping
_consecutive_failures = 0
_circuit_open_until = 0

BCC_EMAIL = 'fordutilityapps@gmail.com'
FROM_EMAIL_DEFAULT = 'notifications@apestogether.ai'
FROM_NAME_DEFAULT = 'Apes Together'


def _check_rate_limit(to_email):
    """Returns True if sending is allowed, False if rate-limited."""
    global _global_sends_this_hour, _global_hour_reset

    now = time.time()

    # Global hourly limit
    with _global_lock:
        if now > _global_hour_reset:
            _global_sends_this_hour = 0
            _global_hour_reset = now + 3600
        if _global_sends_this_hour >= MAX_EMAILS_PER_HOUR_GLOBAL:
            logger.warning("Global email rate limit hit")
            return False
        _global_sends_this_hour += 1

    # Per-user daily limit
    entry = _user_send_counts.get(to_email)
    if entry and now < entry['reset_at']:
        if entry['count'] >= MAX_EMAILS_PER_USER_PER_DAY:
            logger.warning(f"Per-user email rate limit hit for {to_email[:8]}...")
            return False
        entry['count'] += 1
    else:
        _user_send_counts[to_email] = {'count': 1, 'reset_at': now + 86400}

    return True


def _check_circuit_breaker():
    """Returns True if circuit is closed (OK to send), False if open."""
    global _circuit_open_until
    if time.time() < _circuit_open_until:
        logger.warning("Email circuit breaker is OPEN — skipping send")
        return False
    return True


def _record_success():
    global _consecutive_failures
    _consecutive_failures = 0


def _record_failure():
    global _consecutive_failures, _circuit_open_until
    _consecutive_failures += 1
    if _consecutive_failures >= CIRCUIT_BREAKER_FAILURES:
        _circuit_open_until = time.time() + 300  # open for 5 minutes
        logger.error(f"Email circuit breaker OPENED after {_consecutive_failures} consecutive failures")


def send_email(to_email, subject, body, html_body=None, bcc=True):
    """
    Send email via SendGrid API v3 with BCC and rate limiting.

    Args:
        to_email: Recipient email address
        subject: Email subject line
        body: Plain-text body
        html_body: Optional HTML body (sent alongside plain text)
        bcc: Whether to BCC the monitoring address (default True)

    Returns:
        dict with 'status' ('sent'|'rate_limited'|'circuit_open'|'failed'),
        optional 'message_id' and 'error'
    """
    sendgrid_api_key = os.environ.get('SENDGRID_API_KEY')
    from_email = os.environ.get('SENDGRID_FROM_EMAIL', FROM_EMAIL_DEFAULT)

    if not sendgrid_api_key:
        logger.warning("SendGrid API key not configured — email not sent")
        return {'status': 'failed', 'error': 'SendGrid not configured'}

    if not _check_circuit_breaker():
        return {'status': 'circuit_open', 'error': 'Circuit breaker is open'}

    if not _check_rate_limit(to_email):
        return {'status': 'rate_limited', 'error': 'Rate limit exceeded'}

    try:
        import requests

        personalizations = {
            'to': [{'email': to_email}],
            'subject': subject,
        }
        if bcc:
            personalizations['bcc'] = [{'email': BCC_EMAIL}]

        content = [{'type': 'text/plain', 'value': body}]
        if html_body:
            content.append({'type': 'text/html', 'value': html_body})

        data = {
            'personalizations': [personalizations],
            'from': {'email': from_email, 'name': FROM_NAME_DEFAULT},
            'content': content,
        }

        response = requests.post(
            'https://api.sendgrid.com/v3/mail/send',
            headers={
                'Authorization': f'Bearer {sendgrid_api_key}',
                'Content-Type': 'application/json',
            },
            json=data,
            timeout=10,
        )

        if response.status_code == 202:
            message_id = response.headers.get('X-Message-Id', 'unknown')
            _record_success()
            logger.info(f"Email sent to {to_email[:8]}... subj='{subject[:40]}' id={message_id}")
            return {'status': 'sent', 'message_id': message_id}
        else:
            _record_failure()
            err = f'SendGrid {response.status_code}: {response.text[:200]}'
            logger.error(f"Email send failed: {err}")
            return {'status': 'failed', 'error': err}

    except Exception as e:
        _record_failure()
        logger.error(f"Email send exception: {e}")
        return {'status': 'failed', 'error': str(e)}


def format_trade_notification(username, action, ticker, quantity, price, position_pct=None):
    """
    Build the rich trade notification message.
    Example: "TraderJoe just sold 15 shares of AAPL (25% of their position) at $182.50 per share"
    """
    action_word = 'bought' if action.lower() == 'buy' else 'sold'
    qty_str = f"{int(quantity)}" if quantity == int(quantity) else f"{quantity}"

    if position_pct is not None and action.lower() == 'sell':
        pct_str = f"{int(position_pct)}" if position_pct == int(position_pct) else f"{position_pct:.1f}"
        msg = f"{username} just {action_word} {qty_str} shares of {ticker} ({pct_str}% of their position) at ${price:,.2f} per share"
    else:
        msg = f"{username} just {action_word} {qty_str} shares of {ticker} at ${price:,.2f} per share"

    return msg


def send_trade_confirmation_email(user, action, ticker, quantity, price, position_pct=None):
    """
    Send trade confirmation email to the trader themselves.
    """
    action_upper = action.upper()
    emoji = "🟢" if action.lower() == 'buy' else "🔴"
    total = quantity * price
    qty_str = f"{int(quantity)}" if quantity == int(quantity) else f"{quantity}"

    subject = f"{emoji} Trade Confirmed: {action_upper} {qty_str} {ticker}"

    body = (
        f"Trade Confirmed\n\n"
        f"Action: {action_upper}\n"
        f"Ticker: {ticker}\n"
        f"Quantity: {qty_str}\n"
        f"Price: ${price:,.2f}\n"
        f"Total: ${total:,.2f}\n"
    )
    if position_pct is not None and action.lower() == 'sell':
        body += f"Position sold: {position_pct:.1f}%\n"
    body += f"\nYour trade has been executed successfully.\n\n— Apes Together"

    html_body = (
        f"<div style='font-family:sans-serif;max-width:480px;margin:0 auto;padding:24px'>"
        f"<h2 style='margin:0 0 16px'>{emoji} Trade Confirmed</h2>"
        f"<table style='width:100%;border-collapse:collapse;font-size:15px'>"
        f"<tr><td style='padding:6px 0;color:#888'>Action</td><td style='padding:6px 0;font-weight:600'>{action_upper}</td></tr>"
        f"<tr><td style='padding:6px 0;color:#888'>Ticker</td><td style='padding:6px 0;font-weight:600'>{ticker}</td></tr>"
        f"<tr><td style='padding:6px 0;color:#888'>Quantity</td><td style='padding:6px 0;font-weight:600'>{qty_str}</td></tr>"
        f"<tr><td style='padding:6px 0;color:#888'>Price</td><td style='padding:6px 0;font-weight:600'>${price:,.2f}</td></tr>"
        f"<tr><td style='padding:6px 0;color:#888'>Total</td><td style='padding:6px 0;font-weight:600'>${total:,.2f}</td></tr>"
    )
    if position_pct is not None and action.lower() == 'sell':
        html_body += f"<tr><td style='padding:6px 0;color:#888'>Position sold</td><td style='padding:6px 0;font-weight:600'>{position_pct:.1f}%</td></tr>"
    html_body += (
        f"</table>"
        f"<p style='margin:20px 0 0;color:#888;font-size:13px'>Your trade has been executed successfully.</p>"
        f"<p style='color:#888;font-size:12px'>— Apes Together</p>"
        f"</div>"
    )

    if not user.email:
        return {'status': 'failed', 'error': 'User has no email'}

    return send_email(user.email, subject, body, html_body=html_body)


def send_trade_notification_to_subscriber(subscriber_email, trader_username, action, ticker, quantity, price, position_pct=None):
    """
    Send trade alert email to a subscriber about a trader's activity.
    """
    msg = format_trade_notification(trader_username, action, ticker, quantity, price, position_pct)
    emoji = "🟢" if action.lower() == 'buy' else "🔴"
    qty_str = f"{int(quantity)}" if quantity == int(quantity) else f"{quantity}"

    subject = f"{emoji} {trader_username} {action.upper()} {qty_str} {ticker}"

    body = f"Trade Alert\n\n{msg}\n\n— Apes Together"

    html_body = (
        f"<div style='font-family:sans-serif;max-width:480px;margin:0 auto;padding:24px'>"
        f"<h2 style='margin:0 0 12px'>{emoji} Trade Alert</h2>"
        f"<p style='font-size:16px;line-height:1.5'>{msg}</p>"
        f"<p style='color:#888;font-size:12px;margin-top:20px'>— Apes Together</p>"
        f"</div>"
    )

    return send_email(subscriber_email, subject, body, html_body=html_body)


def notify_subscribers_via_email(db, trader_user_id, action, ticker, quantity, price, position_pct=None):
    """
    Fan-out email notifications to all subscribers of a trader who have email notifications enabled.
    Returns summary dict.
    """
    from models import User, MobileSubscription

    trader = User.query.get(trader_user_id)
    if not trader:
        return {'sent': 0, 'failed': 0, 'error': 'trader_not_found'}

    active_subs = MobileSubscription.query.filter_by(
        subscribed_to_id=trader_user_id,
        status='active',
    ).all()

    if not active_subs:
        return {'sent': 0, 'failed': 0, 'skipped': 'no_subscribers'}

    sent = 0
    failed = 0
    rate_limited = 0

    for sub in active_subs:
        subscriber = User.query.get(sub.subscriber_id)
        if not subscriber or not subscriber.email:
            continue

        # Check user-level email preference
        if hasattr(subscriber, 'email_notifications_enabled') and not subscriber.email_notifications_enabled:
            continue

        result = send_trade_notification_to_subscriber(
            subscriber.email, trader.username, action, ticker, quantity, price, position_pct,
        )
        if result['status'] == 'sent':
            sent += 1
        elif result['status'] == 'rate_limited':
            rate_limited += 1
        else:
            failed += 1

        # Log to NotificationLog
        try:
            from models import NotificationLog
            log = NotificationLog(
                user_id=subscriber.id,
                portfolio_owner_id=trader_user_id,
                subscription_id=sub.id if hasattr(sub, 'id') else None,
                notification_type='email',
                status=result['status'],
                sendgrid_message_id=result.get('message_id'),
                error_message=result.get('error'),
            )
            db.session.add(log)
        except Exception as log_err:
            logger.warning(f"Failed to log notification: {log_err}")

    try:
        db.session.commit()
    except Exception:
        pass

    return {'sent': sent, 'failed': failed, 'rate_limited': rate_limited}
