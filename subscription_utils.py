"""
Subscription tier utilities for dynamic pricing and trade limits
"""
from datetime import datetime, date, timedelta
from models import db, SubscriptionTier, TradeLimit, Stock, User
from flask import current_app
import logging

def get_user_trade_count(user_id, days=1):
    """Get trade count for a user over the specified number of days"""
    start_date = date.today() - timedelta(days=days-1)
    
    trade_count = Stock.query.filter(
        Stock.user_id == user_id,
        Stock.purchase_date >= datetime.combine(start_date, datetime.min.time())
    ).count()
    
    return trade_count

def get_user_avg_trades_per_day(user_id, days=7):
    """Get average trades per day over the specified period"""
    total_trades = get_user_trade_count(user_id, days)
    return total_trades / days

def determine_subscription_tier(user_id, lookback_days=7):
    """
    Determine the appropriate subscription tier based on recent trading activity
    Uses 7-day average to prevent gaming the system with single-day spikes
    """
    avg_trades_per_day = get_user_avg_trades_per_day(user_id, lookback_days)
    
    # Tier thresholds based on average daily trades
    if avg_trades_per_day <= 3:
        tier_name = 'Light'
    elif avg_trades_per_day <= 6:
        tier_name = 'Standard'
    elif avg_trades_per_day <= 12:
        tier_name = 'Active'
    elif avg_trades_per_day <= 25:
        tier_name = 'Pro'
    else:
        tier_name = 'Elite'
    
    tier = SubscriptionTier.query.filter_by(tier_name=tier_name).first()
    return tier, avg_trades_per_day

def update_user_subscription_price(user_id):
    """
    Update user's subscription price based on their recent trading activity
    Returns True if price was updated, False otherwise
    """
    user = User.query.get(user_id)
    if not user:
        return False
    
    tier, avg_trades = determine_subscription_tier(user_id)
    if not tier:
        current_app.logger.error(f"No tier found for user {user_id}")
        return False
    
    # Only update if the price has changed
    if user.subscription_price != tier.price:
        old_price = user.subscription_price
        user.subscription_price = tier.price
        user.stripe_price_id = tier.stripe_price_id
        
        db.session.commit()
        
        current_app.logger.info(f"Updated user {user_id} subscription price from ${old_price} to ${tier.price} (tier: {tier.tier_name})")
        return True
    
    return False

def update_trade_limit_count(user_id):
    """Update or create today's trade limit count for a user"""
    today = date.today()
    
    # Get or create today's trade limit record
    trade_limit = TradeLimit.query.filter_by(user_id=user_id, date=today).first()
    if not trade_limit:
        trade_limit = TradeLimit(user_id=user_id, date=today, trade_count=0)
        db.session.add(trade_limit)
    
    # Count today's trades
    today_start = datetime.combine(today, datetime.min.time())
    trades_today = Stock.query.filter(
        Stock.user_id == user_id,
        Stock.purchase_date >= today_start
    ).count()
    
    trade_limit.trade_count = trades_today
    db.session.commit()
    
    return trades_today

def check_trade_limit_exceeded(user_id):
    """
    Check if user has exceeded their daily trade limit based on their current tier
    Returns (exceeded: bool, current_count: int, limit: int, tier_name: str)
    """
    user = User.query.get(user_id)
    if not user:
        return False, 0, 0, "Unknown"
    
    # Get current tier based on subscription price
    tier = SubscriptionTier.query.filter_by(price=user.subscription_price).first()
    if not tier:
        # Default to Light tier if no tier found
        tier = SubscriptionTier.query.filter_by(tier_name='Light').first()
    
    trades_today = get_user_trade_count(user_id, 1)
    exceeded = trades_today > tier.max_trades_per_day
    
    return exceeded, trades_today, tier.max_trades_per_day, tier.tier_name

def get_subscription_tier_info():
    """Get all subscription tier information for display"""
    tiers = SubscriptionTier.query.order_by(SubscriptionTier.price).all()
    return tiers
