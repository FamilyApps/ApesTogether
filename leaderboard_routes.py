"""
Leaderboard routes for displaying performance rankings and subscription buttons
"""
from flask import Blueprint, render_template, jsonify, request, current_app
from flask_login import current_user
from admin_auth import admin_required
from models import db, User, Subscription
from leaderboard_utils import get_leaderboard_data, update_leaderboard_entry, update_all_user_leaderboards
from subscription_utils import get_subscription_tier_info
from datetime import datetime

leaderboard_bp = Blueprint('leaderboard', __name__, url_prefix='/leaderboard')

@leaderboard_bp.route('/')
def leaderboard_home():
    """
    Main leaderboard page - dynamically rendered with cached chart data
    Chart data embedded in HTML (no API calls, lazy-loaded client-side)
    """
    period = request.args.get('period', 'YTD')  # Default to YTD
    category = request.args.get('category', 'all')  # all, small_cap, large_cap
    
    from models import UserPortfolioChartCache
    from flask import make_response
    from leaderboard_utils import calculate_leaderboard_data
    
    leaderboard_data = calculate_leaderboard_data(period, limit=20, category=category)
    
    # Embed chart JSON data for each user (no API calls needed)
    import json
    from leaderboard_utils import calculate_chart_y_axis_range
    
    chart_data_list = []
    for entry in leaderboard_data:
        chart_cache = UserPortfolioChartCache.query.filter_by(
            user_id=entry['user_id'],
            period=period
        ).first()
        
        # Parse JSON string from database to dict for template
        if chart_cache and chart_cache.chart_data:
            try:
                chart_data = json.loads(chart_cache.chart_data)
                entry['chart_json'] = chart_data
                chart_data_list.append(chart_data)
            except (json.JSONDecodeError, TypeError):
                entry['chart_json'] = None
        else:
            entry['chart_json'] = None
    
    # Calculate consistent y-axis range for visual comparison
    y_axis_range = calculate_chart_y_axis_range(chart_data_list)
    
    # Render template (auth state available for SSR, but client will handle overlay)
    response = make_response(render_template('leaderboard.html',
                                            leaderboard_data=leaderboard_data,
                                            current_period=period,
                                            current_category=category,
                                            y_axis_range=y_axis_range,  # Consistent scale for visual comparison
                                            periods=['1D', '5D', '1M', '3M', 'YTD', '1Y', '5Y', 'MAX'],
                                            categories=[
                                                ('all', 'All Portfolios'),
                                                ('small_cap', 'Small Cap Focus'),
                                                ('large_cap', 'Large Cap Focus')
                                            ],
                                            now=datetime.now()))
    
    # Shorter cache for fallback (trigger regeneration)
    response.headers['Cache-Control'] = 'public, max-age=300'  # 5 min for fallback
    response.headers['X-Cache-Source'] = 'fallback-dynamic'
    
    return response

@leaderboard_bp.route('/api/data')
def api_leaderboard_data():
    """API endpoint for leaderboard data - no login required for public leaderboard"""
    period = request.args.get('period', 'YTD')
    category = request.args.get('category', 'all')
    limit = int(request.args.get('limit', 20))
    
    leaderboard_data = get_leaderboard_data(period, limit, category, use_auth_suffix=True)
    return jsonify({
        'period': period,
        'category': category,
        'data': leaderboard_data,
        'count': len(leaderboard_data)
    })

@leaderboard_bp.route('/update/<period>')
@admin_required
def update_period(period):
    """Update leaderboard for specific period (admin/debug use)"""
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
@admin_required
def update_all():
    """No longer needed - leaderboard calculates directly from snapshots"""
    return jsonify({
        'success': True,
        'message': 'Leaderboard now calculates directly from portfolio snapshots - no update needed',
        'updated_count': 0
    })
