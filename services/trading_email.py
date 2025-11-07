"""
Email Trading Service
Handles inbound emails for trade execution
"""
from models import db, User
from services.trading_sms import parse_trade_command, execute_trade
from services.notification_utils import send_email
import re


def parse_email_trade(subject, body):
    """
    Parse trade command from email subject or body
    
    Tries subject first, then body
    
    Returns: dict with action, ticker, quantity or None if invalid
    """
    # Try subject first
    if subject:
        trade = parse_trade_command(subject.strip())
        if trade:
            return trade
    
    # Try first line of body
    if body:
        first_line = body.strip().split('\n')[0]
        trade = parse_trade_command(first_line)
        if trade:
            return trade
    
    return None


def handle_inbound_email(from_email, subject, body):
    """
    Handle inbound email for trade execution
    
    Args:
        from_email: User's email address
        subject: Email subject
        body: Email body
    
    Returns:
        dict with status and message
    """
    # Find user by email
    user = User.query.filter_by(email=from_email).first()
    
    if not user:
        send_email(from_email, 
                  "Trade Failed - Email Not Registered", 
                  "❌ This email is not registered. Please use the email associated with your apestogether.ai account.")
        return {'status': 'error', 'message': 'User not found'}
    
    # Parse trade command from subject or body
    trade = parse_email_trade(subject, body)
    
    if not trade:
        send_email(from_email,
                  "Trade Failed - Invalid Format",
                  "❌ Invalid format. Use: BUY 10 TSLA or SELL 5 AAPL in the subject line or first line of email.")
        return {'status': 'error', 'message': 'Invalid command'}
    
    # Get price using existing 90-second cache
    from portfolio_performance import get_stock_prices
    prices = get_stock_prices([trade['ticker']])
    price = prices.get(trade['ticker'])
    
    if not price:
        send_email(from_email,
                  f"Trade Failed - Price Unavailable",
                  f"❌ Unable to get price for {trade['ticker']}")
        return {'status': 'error', 'message': 'Price fetch failed'}
    
    # Execute trade
    try:
        from services.notification_utils import notify_subscribers
        
        transaction = execute_trade(
            user_id=user.id,
            ticker=trade['ticker'],
            quantity=trade['quantity'],
            price=price,
            transaction_type=trade['action'],
            source='email'
        )
        
        # Send confirmation email to user
        total = trade['quantity'] * price
        action_emoji = "📈" if trade['action'] == 'buy' else "📉"
        
        confirmation_subject = f"Trade Confirmed: {trade['action'].upper()} {trade['quantity']} {trade['ticker']}"
        confirmation_body = (
            f"{action_emoji} Trade Confirmed\n\n"
            f"Action: {trade['action'].upper()}\n"
            f"Quantity: {trade['quantity']}\n"
            f"Ticker: {trade['ticker']}\n"
            f"Price: ${price:.2f}\n"
            f"Total: ${total:.2f}\n\n"
            f"Your trade has been executed successfully."
        )
        
        send_email(from_email, confirmation_subject, confirmation_body)
        
        # Notify subscribers (with position percentage for sells)
        notify_subscribers(user.id, 'trade', {
            'username': user.username,
            'action': trade['action'],
            'quantity': trade['quantity'],
            'ticker': trade['ticker'],
            'price': price,
            'position_pct': transaction.position_pct  # None for buys, percentage for sells
        })
        
        return {
            'status': 'success',
            'message': 'Trade executed',
            'transaction_id': transaction.id
        }
        
    except Exception as e:
        error_subject = "Trade Failed"
        error_body = f"❌ Trade failed: {str(e)}"
        send_email(from_email, error_subject, error_body)
        return {'status': 'error', 'message': str(e)}
