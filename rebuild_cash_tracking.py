"""
Admin script to rebuild max_cash_deployed and cash_proceeds for all users.

This fixes historical data where transactions were added without updating cash tracking.
"""

from models import User, Transaction, db
import logging

logger = logging.getLogger(__name__)


def rebuild_user_cash_tracking(user_id):
    """
    Rebuild max_cash_deployed and cash_proceeds for a single user.
    
    Replays all transactions in chronological order to recalculate correct values.
    
    Args:
        user_id: User ID to rebuild
        
    Returns:
        dict with old and new values
    """
    user = User.query.get(user_id)
    if not user:
        raise ValueError(f"User {user_id} not found")
    
    # Get all transactions in chronological order
    transactions = Transaction.query.filter_by(user_id=user_id).order_by(Transaction.timestamp).all()
    
    if not transactions:
        logger.info(f"User {user_id} has no transactions")
        return {
            'user_id': user_id,
            'transactions_count': 0,
            'old_max_deployed': user.max_cash_deployed,
            'old_cash_proceeds': user.cash_proceeds,
            'new_max_deployed': 0.0,
            'new_cash_proceeds': 0.0,
            'changed': False
        }
    
    # Store old values
    old_max_deployed = user.max_cash_deployed
    old_cash_proceeds = user.cash_proceeds
    
    # Rebuild from scratch
    max_cash_deployed = 0.0
    cash_proceeds = 0.0
    
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
    
    # Update user
    user.max_cash_deployed = max_cash_deployed
    user.cash_proceeds = cash_proceeds
    
    # Ensure changes are tracked by the session
    db.session.add(user)
    
    changed = (old_max_deployed != max_cash_deployed or old_cash_proceeds != cash_proceeds)
    
    logger.info(
        f"User {user_id}: "
        f"max_deployed ${old_max_deployed:.2f} → ${max_cash_deployed:.2f}, "
        f"cash_proceeds ${old_cash_proceeds:.2f} → ${cash_proceeds:.2f}"
    )
    
    return {
        'user_id': user_id,
        'transactions_count': len(transactions),
        'old_max_deployed': old_max_deployed,
        'old_cash_proceeds': old_cash_proceeds,
        'new_max_deployed': max_cash_deployed,
        'new_cash_proceeds': cash_proceeds,
        'changed': changed
    }


def rebuild_all_users_cash_tracking():
    """
    Rebuild cash tracking for ALL users.
    
    Returns:
        dict with summary statistics
    """
    users = User.query.all()
    
    results = []
    users_changed = 0
    
    for user in users:
        result = rebuild_user_cash_tracking(user.id)
        results.append(result)
        if result['changed']:
            users_changed += 1
    
    # Commit all changes
    db.session.commit()
    
    return {
        'total_users': len(users),
        'users_changed': users_changed,
        'users_unchanged': len(users) - users_changed,
        'results': results
    }
