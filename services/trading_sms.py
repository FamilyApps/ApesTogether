"""
SMS Trading Service
Handles inbound SMS commands for trade execution
"""
from models import db, User, Stock, Transaction
from portfolio_performance import get_stock_prices
from datetime import datetime
from services.notification_utils import send_sms, notify_subscribers
import re


def parse_trade_command(message):
    """
    Parse SMS trade commands
    
    Supported formats:
    - "BUY 10 TSLA"
    - "SELL 5 AAPL"
    - "BUY MSFT 150"
    - "SELL 20 NVDA"
    
    Returns: dict with action, ticker, quantity or None if invalid
    """
    message = message.strip().upper()
    
    # Pattern 1: ACTION QUANTITY TICKER (e.g., "BUY 10 TSLA")
    pattern1 = r'^(BUY|SELL)\s+(\d+)\s+([A-Z]{1,5})$'
    match = re.match(pattern1, message)
    if match:
        return {
            'action': match.group(1).lower(),
            'quantity': int(match.group(2)),
            'ticker': match.group(3)
        }
    
    # Pattern 2: ACTION TICKER QUANTITY (e.g., "BUY TSLA 10")
    pattern2 = r'^(BUY|SELL)\s+([A-Z]{1,5})\s+(\d+)$'
    match = re.match(pattern2, message)
    if match:
        return {
            'action': match.group(1).lower(),
            'quantity': int(match.group(3)),
            'ticker': match.group(2)
        }
    
    return None


def execute_trade(user_id, ticker, quantity, price, transaction_type, source='sms'):
    """
    Execute a trade and update database
    
    Args:
        user_id: User ID
        ticker: Stock ticker
        quantity: Number of shares
        price: Price per share
        transaction_type: 'buy' or 'sell'
        source: 'sms', 'email', or 'web'
    
    Returns:
        Transaction object or raises exception
    """
    user = User.query.get(user_id)
    if not user:
        raise ValueError("User not found")
    
    # Get current position for position percentage calculation
    current_position = Stock.query.filter_by(
        user_id=user_id,
        ticker=ticker
    ).first()
    
    position_pct = None
    
    # Handle BUY
    if transaction_type == 'buy':
        # Create transaction
        transaction = Transaction(
            user_id=user_id,
            ticker=ticker,
            quantity=quantity,
            price=price,
            transaction_type='buy',
            timestamp=datetime.utcnow()
        )
        db.session.add(transaction)
        
        # Update or create stock holding
        if current_position:
            # Update existing position
            total_cost = (current_position.quantity * current_position.purchase_price) + (quantity * price)
            total_shares = current_position.quantity + quantity
            current_position.purchase_price = total_cost / total_shares
            current_position.quantity = total_shares
            current_position.purchase_date = datetime.utcnow()
        else:
            # Create new position
            stock = Stock(
                user_id=user_id,
                ticker=ticker,
                quantity=quantity,
                purchase_price=price,
                purchase_date=datetime.utcnow()
            )
            db.session.add(stock)
    
    # Handle SELL
    elif transaction_type == 'sell':
        if not current_position:
            raise ValueError(f"You don't own any {ticker}")
        
        if current_position.quantity < quantity:
            raise ValueError(f"Insufficient shares. You own {current_position.quantity} {ticker}")
        
        # Calculate position percentage BEFORE selling
        position_pct = (quantity / current_position.quantity) * 100
        
        # Create transaction
        transaction = Transaction(
            user_id=user_id,
            ticker=ticker,
            quantity=quantity,
            price=price,
            transaction_type='sell',
            timestamp=datetime.utcnow()
        )
        db.session.add(transaction)
        
        # Update stock holding
        current_position.quantity -= quantity
        
        # Remove position if completely sold
        if current_position.quantity == 0:
            db.session.delete(current_position)
    
    else:
        raise ValueError("Invalid transaction type")
    
    # Commit to database
    db.session.commit()
    
    # Return transaction and position percentage
    transaction.position_pct = position_pct
    return transaction


def handle_inbound_sms(from_number, message_body):
    """
    Handle inbound SMS from Twilio
    
    Args:
        from_number: User's phone number (E.164 format)
        message_body: SMS message text
    
    Returns:
        dict with status and message
    """
    # Find user by phone number
    user = User.query.filter_by(phone_number=from_number).first()
    
    if not user:
        send_sms(from_number, "❌ Phone number not registered. Add it in your profile at apestogether.ai")
        return {'status': 'error', 'message': 'User not found'}
    
    # Parse trade command
    trade = parse_trade_command(message_body)
    
    if not trade:
        send_sms(from_number, "❌ Invalid format. Use: BUY 10 TSLA or SELL 5 AAPL")
        return {'status': 'error', 'message': 'Invalid command'}
    
    # Get price using existing 90-second cache
    prices = get_stock_prices([trade['ticker']])
    price = prices.get(trade['ticker'])
    
    if not price:
        send_sms(from_number, f"❌ Unable to get price for {trade['ticker']}")
        return {'status': 'error', 'message': 'Price fetch failed'}
    
    # Execute trade
    try:
        transaction = execute_trade(
            user_id=user.id,
            ticker=trade['ticker'],
            quantity=trade['quantity'],
            price=price,
            transaction_type=trade['action'],
            source='sms'
        )
        
        # Send confirmation SMS to user
        total = trade['quantity'] * price
        action_emoji = "📈" if trade['action'] == 'buy' else "📉"
        
        confirmation_msg = (
            f"{action_emoji} Confirmed: {trade['action'].upper()} "
            f"{trade['quantity']} {trade['ticker']} @ ${price:.2f} = ${total:.2f}"
        )
        
        send_sms(from_number, confirmation_msg)
        
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
        error_msg = f"❌ Trade failed: {str(e)}"
        send_sms(from_number, error_msg)
        return {'status': 'error', 'message': str(e)}
