"""
Leaderboard routes for displaying performance rankings and subscription buttons
"""
from flask import Blueprint, render_template, jsonify, request
from flask_login import login_required, current_user
from models import db, User, Subscription
from leaderboard_utils import get_leaderboard_data, update_leaderboard_entry, update_all_user_leaderboards
from subscription_utils import get_subscription_tier_info

leaderboard_bp = Blueprint('leaderboard', __name__, url_prefix='/leaderboard')

@leaderboard_bp.route('/')
@login_required
def leaderboard_home():
    """Main leaderboard page"""
    period = request.args.get('period', 'YTD')
    category = request.args.get('category', 'all')  # all, small_cap, large_cap
    
    # Get leaderboard data
    leaderboard_data = get_leaderboard_data(period, limit=50)
    
    # Filter by category if specified
    if category == 'small_cap':
        leaderboard_data = [entry for entry in leaderboard_data if entry['small_cap_percent'] > 50]
    elif category == 'large_cap':
        leaderboard_data = [entry for entry in leaderboard_data if entry['large_cap_percent'] > 50]
    
    # Check which users current user is already subscribed to
    subscribed_to_ids = set()
    if current_user.is_authenticated:
        subscriptions = Subscription.query.filter_by(
            subscriber_id=current_user.id, 
            status='active'
        ).all()
        subscribed_to_ids = {sub.subscribed_to_id for sub in subscriptions}
    
    # Add subscription status to leaderboard data
    for entry in leaderboard_data:
        entry['is_subscribed'] = entry['user_id'] in subscribed_to_ids
        entry['is_current_user'] = entry['user_id'] == current_user.id
    
    return render_template('leaderboard.html', 
                         leaderboard_data=leaderboard_data,
                         current_period=period,
                         current_category=category,
                         periods=['1D', '5D', '3M', 'YTD', '1Y', '5Y', 'MAX'],
                         categories=[
                             ('all', 'All Portfolios'),
                             ('small_cap', 'Small Cap Focus'),
                             ('large_cap', 'Large Cap Focus')
                         ])

@leaderboard_bp.route('/api/data')
def api_leaderboard_data():
    """API endpoint for leaderboard data - no login required for public leaderboard"""
    period = request.args.get('period', 'YTD')
    limit = int(request.args.get('limit', 50))
    
    leaderboard_data = get_leaderboard_data(period, limit)
    return jsonify({
        'period': period,
        'data': leaderboard_data,
        'count': len(leaderboard_data)
    })

@leaderboard_bp.route('/update/<period>')
@login_required
def update_period(period):
    """Update leaderboard for specific period (admin/debug use)"""
    # Check if user is admin using the same logic as other admin routes
    from flask import session
    import os
    ADMIN_EMAIL = os.environ.get('ADMIN_EMAIL', 'admin@apestogether.ai')
    
    email = session.get('email', '')
    if email != ADMIN_EMAIL and current_user.email != ADMIN_EMAIL and current_user.username != 'admin':
        return jsonify({'error': 'Admin access required'}), 403
    
    users = User.query.all()
    updated_count = 0
    
    for user in users:
        update_leaderboard_entry(user.id, period)
        updated_count += 1
    
    return jsonify({
        'success': True,
        'period': period,
        'updated_count': updated_count
    })

@leaderboard_bp.route('/update-all')
@login_required
def update_all():
    """No longer needed - leaderboard calculates directly from snapshots"""
    return jsonify({
        'success': True,
        'message': 'Leaderboard now calculates directly from portfolio snapshots - no update needed',
        'updated_count': 0
    })
