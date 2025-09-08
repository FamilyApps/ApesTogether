"""
Debug routes for testing subscription tiers, SMS, and leaderboard functionality
"""
from flask import Blueprint, jsonify, request, render_template_string, flash, redirect, url_for
from flask_login import login_required, current_user
from models import db, User, SubscriptionTier, TradeLimit, SMSNotification, StockInfo, LeaderboardEntry, Stock
from subscription_utils import (
    get_user_trade_count, 
    get_user_avg_trades_per_day, 
    determine_subscription_tier,
    update_user_subscription_price,
    check_trade_limit_exceeded,
    get_subscription_tier_info
)
from datetime import datetime, date, timedelta
import json

debug_bp = Blueprint('debug', __name__, url_prefix='/debug')

@debug_bp.route('/')
@login_required
def debug_home():
    """Debug dashboard showing all available debug routes"""
    debug_template = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Debug Dashboard</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 40px; }
            .section { margin: 20px 0; padding: 20px; border: 1px solid #ddd; }
            .route { margin: 10px 0; }
            .route a { color: #007bff; text-decoration: none; }
            .route a:hover { text-decoration: underline; }
            .method { color: #28a745; font-weight: bold; }
            .description { color: #666; font-style: italic; }
        </style>
    </head>
    <body>
        <h1>Debug Dashboard</h1>
        <p>Current User: {{ current_user.username }} (ID: {{ current_user.id }})</p>
        
        <div class="section">
            <h2>Subscription Tier Debug Routes</h2>
            <div class="route">
                <span class="method">GET</span> 
                <a href="{{ url_for('debug.subscription_tiers') }}">/debug/subscription-tiers</a>
                <div class="description">View all subscription tiers</div>
            </div>
            <div class="route">
                <span class="method">GET</span> 
                <a href="{{ url_for('debug.user_tier_info') }}">/debug/user-tier-info</a>
                <div class="description">View current user's tier information</div>
            </div>
            <div class="route">
                <span class="method">POST</span> 
                <a href="{{ url_for('debug.simulate_trades') }}">/debug/simulate-trades</a>
                <div class="description">Simulate trades to test tier changes</div>
            </div>
            <div class="route">
                <span class="method">GET</span> 
                <a href="{{ url_for('debug.trade_limits') }}">/debug/trade-limits</a>
                <div class="description">View trade limits and counts</div>
            </div>
        </div>
        
        <div class="section">
            <h2>SMS Debug Routes</h2>
            <div class="route">
                <span class="method">GET</span> 
                <a href="{{ url_for('debug.sms_settings') }}">/debug/sms-settings</a>
                <div class="description">View SMS notification settings</div>
            </div>
            <div class="route">
                <span class="method">POST</span> 
                <a href="{{ url_for('debug.test_sms') }}">/debug/test-sms</a>
                <div class="description">Test SMS functionality (mock)</div>
            </div>
        </div>
        
        <div class="section">
            <h2>Leaderboard Debug Routes</h2>
            <div class="route">
                <span class="method">GET</span> 
                <a href="{{ url_for('debug.leaderboard_data') }}">/debug/leaderboard-data</a>
                <div class="description">View leaderboard calculations</div>
            </div>
            <div class="route">
                <span class="method">POST</span> 
                <a href="{{ url_for('debug.calculate_performance') }}">/debug/calculate-performance</a>
                <div class="description">Trigger performance calculations</div>
            </div>
        </div>
        
        <div class="section">
            <h2>Database Debug Routes</h2>
            <div class="route">
                <span class="method">GET</span> 
                <a href="{{ url_for('debug.database_status') }}">/debug/database-status</a>
                <div class="description">Check database table status</div>
            </div>
            <div class="route">
                <span class="method">POST</span> 
                <a href="{{ url_for('debug.reset_user_data') }}">/debug/reset-user-data</a>
                <div class="description">Reset current user's debug data</div>
            </div>
        </div>
    </body>
    </html>
    """
    return render_template_string(debug_template)

@debug_bp.route('/subscription-tiers')
@login_required
def subscription_tiers():
    """View all subscription tiers"""
    tiers = get_subscription_tier_info()
    return jsonify({
        'tiers': [{
            'id': tier.id,
            'tier_name': tier.tier_name,
            'price': tier.price,
            'max_trades_per_day': tier.max_trades_per_day,
            'stripe_price_id': tier.stripe_price_id
        } for tier in tiers]
    })

@debug_bp.route('/user-tier-info')
@login_required
def user_tier_info():
    """Get current user's tier information and trading stats"""
    user_id = current_user.id
    
    # Get trading stats
    trades_today = get_user_trade_count(user_id, 1)
    trades_7day = get_user_trade_count(user_id, 7)
    avg_trades_per_day = get_user_avg_trades_per_day(user_id, 7)
    
    # Get current tier
    tier, calculated_avg = determine_subscription_tier(user_id)
    
    # Check trade limits
    exceeded, current_count, limit, tier_name = check_trade_limit_exceeded(user_id)
    
    return jsonify({
        'user_id': user_id,
        'username': current_user.username,
        'current_subscription_price': current_user.subscription_price,
        'current_stripe_price_id': current_user.stripe_price_id,
        'trading_stats': {
            'trades_today': trades_today,
            'trades_7day': trades_7day,
            'avg_trades_per_day': avg_trades_per_day,
            'calculated_avg': calculated_avg
        },
        'recommended_tier': {
            'tier_name': tier.tier_name if tier else None,
            'price': tier.price if tier else None,
            'max_trades_per_day': tier.max_trades_per_day if tier else None
        },
        'trade_limit_status': {
            'exceeded': exceeded,
            'current_count': current_count,
            'limit': limit,
            'tier_name': tier_name
        }
    })

@debug_bp.route('/simulate-trades', methods=['GET', 'POST'])
@login_required
def simulate_trades():
    """Simulate trades to test tier changes"""
    if request.method == 'GET':
        form_html = """
        <form method="POST">
            <h3>Simulate Trades</h3>
            <label>Number of trades to simulate: <input type="number" name="trade_count" value="5" min="1" max="50"></label><br><br>
            <label>Days to spread over: <input type="number" name="days" value="1" min="1" max="30"></label><br><br>
            <button type="submit">Simulate Trades</button>
        </form>
        <a href="/debug/">Back to Debug Dashboard</a>
        """
        return render_template_string(form_html)
    
    trade_count = int(request.form.get('trade_count', 5))
    days = int(request.form.get('days', 1))
    
    # Create simulated trades spread over the specified days
    for i in range(trade_count):
        day_offset = i % days
        trade_date = datetime.now() - timedelta(days=day_offset)
        
        stock = Stock(
            ticker=f'TEST{i}',
            quantity=1,
            purchase_price=100.0,
            purchase_date=trade_date,
            user_id=current_user.id
        )
        db.session.add(stock)
    
    db.session.commit()
    
    # Update subscription price
    price_updated = update_user_subscription_price(current_user.id)
    
    return jsonify({
        'success': True,
        'trades_created': trade_count,
        'days_spread': days,
        'price_updated': price_updated,
        'new_price': current_user.subscription_price
    })

@debug_bp.route('/trade-limits')
@login_required
def trade_limits():
    """View trade limits and counts for current user"""
    user_id = current_user.id
    
    # Get recent trade limits
    recent_limits = TradeLimit.query.filter_by(user_id=user_id).order_by(TradeLimit.date.desc()).limit(7).all()
    
    return jsonify({
        'user_id': user_id,
        'recent_trade_limits': [{
            'date': limit.date.isoformat(),
            'trade_count': limit.trade_count,
            'created_at': limit.created_at.isoformat() if limit.created_at else None
        } for limit in recent_limits]
    })

@debug_bp.route('/sms-settings')
@login_required
def sms_settings():
    """View SMS notification settings"""
    sms_setting = SMSNotification.query.filter_by(user_id=current_user.id).first()
    
    return jsonify({
        'user_id': current_user.id,
        'sms_notification': {
            'phone_number': sms_setting.phone_number if sms_setting else None,
            'is_verified': sms_setting.is_verified if sms_setting else False,
            'sms_enabled': sms_setting.sms_enabled if sms_setting else True,
            'created_at': sms_setting.created_at.isoformat() if sms_setting and sms_setting.created_at else None
        } if sms_setting else None
    })

@debug_bp.route('/test-sms', methods=['POST'])
@login_required
def test_sms():
    """Test SMS functionality (mock implementation)"""
    phone_number = request.form.get('phone_number', '+1234567890')
    message = request.form.get('message', 'Test SMS from debug route')
    
    # Mock SMS sending
    return jsonify({
        'success': True,
        'message': 'SMS sent successfully (mock)',
        'phone_number': phone_number,
        'message_content': message,
        'timestamp': datetime.now().isoformat()
    })

@debug_bp.route('/leaderboard-data')
@login_required
def leaderboard_data():
    """View leaderboard calculations"""
    entries = LeaderboardEntry.query.filter_by(user_id=current_user.id).all()
    
    return jsonify({
        'user_id': current_user.id,
        'leaderboard_entries': [{
            'period': entry.period,
            'performance_percent': entry.performance_percent,
            'small_cap_percent': entry.small_cap_percent,
            'large_cap_percent': entry.large_cap_percent,
            'avg_trades_per_week': entry.avg_trades_per_week,
            'portfolio_value': entry.portfolio_value,
            'calculated_at': entry.calculated_at.isoformat() if entry.calculated_at else None
        } for entry in entries]
    })

@debug_bp.route('/calculate-performance', methods=['POST'])
@login_required
def calculate_performance():
    """Trigger performance calculations for current user"""
    periods = ['1D', '5D', '3M', 'YTD', '1Y', '5Y', 'MAX']
    
    # Mock performance calculation
    for period in periods:
        # Check if entry exists
        entry = LeaderboardEntry.query.filter_by(user_id=current_user.id, period=period).first()
        if not entry:
            entry = LeaderboardEntry(user_id=current_user.id, period=period)
            db.session.add(entry)
        
        # Mock performance data
        entry.performance_percent = 5.5  # Mock 5.5% return
        entry.small_cap_percent = 30.0
        entry.large_cap_percent = 70.0
        entry.avg_trades_per_week = get_user_avg_trades_per_day(current_user.id, 7) * 7
        entry.portfolio_value = 10000.0  # Mock portfolio value
        entry.calculated_at = datetime.now()
    
    db.session.commit()
    
    return jsonify({
        'success': True,
        'message': f'Performance calculated for {len(periods)} periods',
        'periods': periods
    })

@debug_bp.route('/database-status')
@login_required
def database_status():
    """Check database table status"""
    try:
        # Check if tables exist and get counts
        tables_status = {}
        
        tables_status['subscription_tier'] = SubscriptionTier.query.count()
        tables_status['trade_limit'] = TradeLimit.query.count()
        tables_status['sms_notification'] = SMSNotification.query.count()
        tables_status['stock_info'] = StockInfo.query.count()
        tables_status['leaderboard_entry'] = LeaderboardEntry.query.count()
        tables_status['users'] = User.query.count()
        tables_status['stocks'] = Stock.query.count()
        
        return jsonify({
            'success': True,
            'tables_status': tables_status,
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        })

@debug_bp.route('/reset-user-data', methods=['POST'])
@login_required
def reset_user_data():
    """Reset current user's debug data (trade limits, leaderboard entries)"""
    user_id = current_user.id
    
    # Delete trade limits
    TradeLimit.query.filter_by(user_id=user_id).delete()
    
    # Delete leaderboard entries
    LeaderboardEntry.query.filter_by(user_id=user_id).delete()
    
    # Delete SMS notification settings
    SMSNotification.query.filter_by(user_id=user_id).delete()
    
    # Delete test stocks (those with ticker starting with 'TEST')
    Stock.query.filter(Stock.user_id == user_id, Stock.ticker.like('TEST%')).delete()
    
    # Reset subscription price to default
    current_user.subscription_price = 8.00  # Default to Light tier
    light_tier = SubscriptionTier.query.filter_by(tier_name='Light').first()
    if light_tier:
        current_user.stripe_price_id = light_tier.stripe_price_id
    
    db.session.commit()
    
    return jsonify({
        'success': True,
        'message': 'User debug data reset successfully',
        'user_id': user_id
    })
