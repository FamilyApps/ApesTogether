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

def process_transaction(db, user_id, ticker, quantity, price, transaction_type, timestamp=None):
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
    
    Returns:
        dict with updated max_cash_deployed and cash_proceeds
    """
    user = User.query.get(user_id)
    if not user:
        raise ValueError(f"User {user_id} not found")
    
    transaction_value = quantity * price
    
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
    
    else:
        raise ValueError(f"Invalid transaction_type: {transaction_type}")
    
    # Create transaction record
    transaction = Transaction(
        user_id=user_id,
        ticker=ticker,
        quantity=quantity,
        price=price,
        transaction_type=transaction_type,
        timestamp=timestamp or datetime.utcnow()
    )
    db.session.add(transaction)
    
    return {
        'max_cash_deployed': user.max_cash_deployed,
        'cash_proceeds': user.cash_proceeds,
        'transaction_value': transaction_value
    }

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
    
    # Calculate stock value (using existing logic)
    from portfolio_performance import PortfolioPerformanceCalculator
    calculator = PortfolioPerformanceCalculator()
    stock_value = calculator.calculate_portfolio_value(user_id, target_date)
    
    # Get cash proceeds (if target_date specified, need to recalculate from transactions)
    if target_date:
        cash_proceeds = calculate_cash_proceeds_as_of_date(user_id, target_date)
    else:
        cash_proceeds = user.cash_proceeds
    
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
