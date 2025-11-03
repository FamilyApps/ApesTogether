"""
Leaderboard routes for displaying performance rankings and subscription buttons
"""
from flask import Blueprint, render_template, jsonify, request, current_app
from flask_login import login_required, current_user
from models import db, User, Subscription
from leaderboard_utils import get_leaderboard_data, update_leaderboard_entry, update_all_user_leaderboards
from subscription_utils import get_subscription_tier_info
from datetime import datetime

leaderboard_bp = Blueprint('leaderboard', __name__, url_prefix='/leaderboard')

@leaderboard_bp.route('/')
def leaderboard_home():
    """
    Main leaderboard page - optimized for 10,000+ concurrent users
    
    Strategy:
    1. Serve pre-rendered HTML from cache (CDN edge cached, <100ms response)
    2. Single HTML variant for all users (auth overlay done client-side)
    3. Chart data embedded in HTML (no API calls, lazy-loaded client-side)
    """
    period = request.args.get('period', 'YTD')  # Default to YTD
    category = request.args.get('category', 'all')  # all, small_cap, large_cap
    
    # ============================================
    # STEP 1: Try to serve pre-rendered HTML from cache
    # ============================================
    from models import LeaderboardCache, UserPortfolioChartCache
    from flask import Response, make_response
    
    # Single cache key (no auth suffix - client-side overlay handles auth)
    cache_key = f"{period}_{category}"
    cache_entry = LeaderboardCache.query.filter_by(period=cache_key).first()
    
    if cache_entry and cache_entry.rendered_html:
        # Serve pre-rendered HTML with aggressive CDN caching
        response = make_response(cache_entry.rendered_html)
        
        # CDN caching headers for 10k+ concurrent users
        response.headers['Cache-Control'] = 'public, max-age=3600, s-maxage=3600'  # 1 hour
        response.headers['CDN-Cache-Control'] = 'max-age=86400'  # 24h at CDN edge
        response.headers['Vary'] = 'Accept-Encoding'  # Only vary on compression
        response.headers['X-Cache-Source'] = 'pre-rendered'
        
        return response
    
    # ============================================
    # STEP 2: Fallback - Dynamic rendering (should rarely happen)
    # ============================================
    from leaderboard_utils import calculate_leaderboard_data
    
    leaderboard_data = calculate_leaderboard_data(period, limit=20, category=category)
    
    # Embed chart JSON data for each user (no API calls needed)
    for entry in leaderboard_data:
        chart_cache = UserPortfolioChartCache.query.filter_by(
            user_id=entry['user_id'],
            period=period
        ).first()
        
        entry['chart_json'] = chart_cache.chart_data if chart_cache else None
    
    # Render template (auth state available for SSR, but client will handle overlay)
    response = make_response(render_template('leaderboard.html',
                                            leaderboard_data=leaderboard_data,
                                            current_period=period,
                                            current_category=category,
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
