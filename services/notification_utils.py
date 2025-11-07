"""
Notification Utilities
Handles SMS and email notifications with position percentage support
"""
from twilio.rest import Client
from models import db, Subscription, NotificationPreferences, NotificationLog
from concurrent.futures import ThreadPoolExecutor, as_completed
import os


# Twilio configuration
TWILIO_ACCOUNT_SID = os.environ.get('TWILIO_ACCOUNT_SID')
TWILIO_AUTH_TOKEN = os.environ.get('TWILIO_AUTH_TOKEN')
TWILIO_PHONE_NUMBER = os.environ.get('TWILIO_PHONE_NUMBER')

# Initialize Twilio client
if TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN:
    twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
else:
    twilio_client = None
    print("WARNING: Twilio credentials not configured")


def send_sms(to_number, message):
    """
    Send SMS via Twilio
    
    Args:
        to_number: Recipient phone number (E.164 format)
        message: Message text
    
    Returns:
        dict with status, sid, and optional error
    """
    if not twilio_client:
        return {
            'status': 'error',
            'error': 'Twilio not configured'
        }
    
    try:
        sms = twilio_client.messages.create(
            body=message,
            from_=TWILIO_PHONE_NUMBER,
            to=to_number
        )
        
        return {
            'status': 'sent',
            'sid': sms.sid
        }
    
    except Exception as e:
        return {
            'status': 'failed',
            'error': str(e)
        }


def send_email(to_email, subject, body):
    """
    Send email notification via SendGrid
    
    Args:
        to_email: Recipient email
        subject: Email subject
        body: Email body (plain text)
    
    Returns:
        dict with status, message_id, and optional error
    """
    sendgrid_api_key = os.environ.get('SENDGRID_API_KEY')
    from_email = os.environ.get('SENDGRID_FROM_EMAIL', 'notifications@apestogether.ai')
    
    if not sendgrid_api_key:
        print("WARNING: SendGrid API key not configured")
        return {
            'status': 'failed',
            'error': 'SendGrid not configured'
        }
    
    try:
        import requests
        
        # SendGrid API v3
        url = 'https://api.sendgrid.com/v3/mail/send'
        headers = {
            'Authorization': f'Bearer {sendgrid_api_key}',
            'Content-Type': 'application/json'
        }
        
        data = {
            'personalizations': [{
                'to': [{'email': to_email}],
                'subject': subject
            }],
            'from': {'email': from_email},
            'content': [{
                'type': 'text/plain',
                'value': body
            }]
        }
        
        response = requests.post(url, headers=headers, json=data)
        
        if response.status_code == 202:
            # SendGrid returns message ID in X-Message-Id header
            message_id = response.headers.get('X-Message-Id', 'unknown')
            return {
                'status': 'sent',
                'message_id': message_id
            }
        else:
            return {
                'status': 'failed',
                'error': f'SendGrid error: {response.status_code} - {response.text}'
            }
    
    except Exception as e:
        return {
            'status': 'failed',
            'error': str(e)
        }


def format_trade_notification(trade_data):
    """
    Format trade notification message with position percentage
    
    Args:
        trade_data: dict with username, action, quantity, ticker, price, position_pct
    
    Returns:
        Formatted message string
    """
    username = trade_data['username']
    action = trade_data['action']
    quantity = trade_data['quantity']
    ticker = trade_data['ticker']
    price = trade_data['price']
    position_pct = trade_data.get('position_pct')
    
    # Add emoji
    action_emoji = "📈" if action == 'buy' else "📉"
    
    # Format base message
    if position_pct and action == 'sell':
        # Include position percentage for sells
        message = (
            f"{action_emoji} {username} {action}s {quantity} {ticker} "
            f"({position_pct:.1f}% of position) @ ${price:.2f}"
        )
    else:
        # Buy or no position data
        message = (
            f"{action_emoji} {username} {action}s {quantity} {ticker} @ ${price:.2f}"
        )
    
    return message


def send_notification_to_subscriber(subscriber_data, message):
    """
    Send notification to a single subscriber (SMS or email)
    Used by ThreadPoolExecutor for parallel sending
    
    Args:
        subscriber_data: dict with subscriber info and preferences
        message: Formatted notification message
    
    Returns:
        dict with delivery result
    """
    from models import NotificationLog
    
    sub = subscriber_data['subscription']
    pref = subscriber_data['preference']
    user = sub.subscriber
    
    # Determine notification method
    # Priority: 1) Preference on this subscription, 2) User's phone if exists, 3) Email
    if pref and pref.notification_type:
        method = pref.notification_type
    elif user.phone_number and user.default_notification_method == 'sms':
        method = 'sms'
    else:
        method = 'email'
    
    # Send notification
    if method == 'sms' and user.phone_number:
        result = send_sms(user.phone_number, message)
    else:
        # Send email (default)
        result = send_email(
            user.email,
            f"Trade Alert: {subscriber_data['username']}",
            message
        )
        method = 'email'  # Force method to email if SMS unavailable
    
    # Log delivery
    log = NotificationLog(
        user_id=sub.subscriber_id,
        portfolio_owner_id=subscriber_data['portfolio_owner_id'],
        subscription_id=sub.id,
        notification_type=method,
        status=result['status'],
        twilio_sid=result.get('sid'),
        sendgrid_message_id=result.get('message_id'),
        error_message=result.get('error')
    )
    db.session.add(log)
    
    return result


def notify_subscribers(portfolio_owner_id, notification_type, data):
    """
    Send notifications to all active subscribers in parallel
    
    Args:
        portfolio_owner_id: User ID of portfolio owner
        notification_type: 'trade', 'alert', etc.
        data: Notification data (username, action, quantity, ticker, price, position_pct)
    
    Returns:
        dict with sent_count and failed_count
    """
    # Get all REAL subscribers (not ghost subscribers from AdminSubscription)
    subscriptions = Subscription.query.filter_by(
        subscribed_to_id=portfolio_owner_id,
        status='active'
    ).all()
    
    if not subscriptions:
        return {'sent_count': 0, 'failed_count': 0}
    
    # Format message once
    if notification_type == 'trade':
        message = format_trade_notification(data)
    else:
        message = str(data)  # Generic fallback
    
    # Prepare subscriber data for parallel processing
    subscribers_data = []
    for sub in subscriptions:
        # Get notification preference for this subscription
        pref = NotificationPreferences.query.filter_by(
            user_id=sub.subscriber_id,
            subscription_id=sub.id
        ).first()
        
        # Skip if notifications disabled
        if pref and not pref.enabled:
            continue
        
        subscribers_data.append({
            'subscription': sub,
            'preference': pref,
            'portfolio_owner_id': portfolio_owner_id,
            'username': data.get('username', 'User')
        })
    
    # Send notifications in parallel (max 20 concurrent)
    sent_count = 0
    failed_count = 0
    
    with ThreadPoolExecutor(max_workers=20) as executor:
        futures = [
            executor.submit(send_notification_to_subscriber, sub_data, message)
            for sub_data in subscribers_data
        ]
        
        for future in as_completed(futures):
            try:
                result = future.result()
                if result['status'] == 'sent':
                    sent_count += 1
                else:
                    failed_count += 1
            except Exception as e:
                print(f"Notification send error: {e}")
                failed_count += 1
    
    # Commit all logs at once
    db.session.commit()
    
    return {
        'sent_count': sent_count,
        'failed_count': failed_count
    }
