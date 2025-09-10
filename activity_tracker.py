"""
User activity tracking utilities for accurate active user metrics
"""
from datetime import datetime
from models import db, UserActivity
from flask import request

def log_user_activity(user_id, activity_type, ip_address=None, user_agent=None):
    """
    Log user activity for accurate active user tracking
    
    Args:
        user_id: ID of the user performing the activity
        activity_type: Type of activity ('login', 'add_stock', 'view_dashboard', 'add_transaction', etc.)
        ip_address: User's IP address (optional)
        user_agent: User's browser/device info (optional)
    """
    try:
        # Get IP and user agent from request if not provided
        if ip_address is None and request:
            ip_address = request.remote_addr
        if user_agent is None and request:
            user_agent = request.headers.get('User-Agent', '')[:255]  # Truncate to fit column
        
        activity = UserActivity(
            user_id=user_id,
            activity_type=activity_type,
            ip_address=ip_address,
            user_agent=user_agent
        )
        
        db.session.add(activity)
        db.session.commit()
        
    except Exception as e:
        print(f"Error logging user activity: {str(e)}")
        db.session.rollback()

def log_login_activity(user_id):
    """Log user login activity"""
    log_user_activity(user_id, 'login')

def log_dashboard_view(user_id):
    """Log user viewing dashboard"""
    log_user_activity(user_id, 'view_dashboard')

def log_stock_addition(user_id):
    """Log user adding a stock"""
    log_user_activity(user_id, 'add_stock')

def log_transaction_addition(user_id):
    """Log user adding a transaction"""
    log_user_activity(user_id, 'add_transaction')

def log_portfolio_view(user_id):
    """Log user viewing portfolio"""
    log_user_activity(user_id, 'view_portfolio')

def log_leaderboard_view(user_id):
    """Log user viewing leaderboard"""
    log_user_activity(user_id, 'view_leaderboard')

def log_sms_settings_view(user_id):
    """Log user viewing SMS settings"""
    log_user_activity(user_id, 'view_sms_settings')

def log_subscription_activity(user_id):
    """Log user subscription-related activity"""
    log_user_activity(user_id, 'subscription_activity')
