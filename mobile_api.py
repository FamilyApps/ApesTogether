"""
Mobile API Endpoints for Apes Together iOS/Android Apps
Phase 1 - Backend Preparation

Endpoints:
- POST /api/mobile/device/register - Register device for push notifications
- DELETE /api/mobile/device/unregister - Remove device token
- POST /api/mobile/purchase/validate - Validate IAP receipt
- GET /api/mobile/subscriptions - Get user's active subscriptions
- POST /api/mobile/subscribe - Subscribe to a portfolio
- DELETE /api/mobile/unsubscribe/<id> - Cancel subscription
- GET /api/mobile/portfolio/<slug> - Get portfolio data for mobile
- GET /api/mobile/leaderboard - Get leaderboard for mobile
- PUT /api/mobile/notifications/settings - Update notification preferences
"""

from flask import Blueprint, request, jsonify, g
from functools import wraps
from datetime import datetime
import logging
import jwt
import os
import secrets
import string

logger = logging.getLogger(__name__)

mobile_api = Blueprint('mobile_api', __name__, url_prefix='/api/mobile')


def require_auth(f):
    """Decorator to require JWT authentication for mobile endpoints"""
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get('Authorization')
        if not auth_header:
            return jsonify({'error': 'missing_authorization_header'}), 401
        
        try:
            # Expect "Bearer <token>"
            parts = auth_header.split()
            if len(parts) != 2 or parts[0].lower() != 'bearer':
                return jsonify({'error': 'invalid_authorization_format'}), 401
            
            token = parts[1]
            secret = os.environ.get('JWT_SECRET', os.environ.get('SECRET_KEY', 'dev-secret'))
            
            payload = jwt.decode(token, secret, algorithms=['HS256'])
            g.user_id = payload.get('user_id')
            g.user_email = payload.get('email')
            
            if not g.user_id:
                return jsonify({'error': 'invalid_token_payload'}), 401
                
        except jwt.ExpiredSignatureError:
            return jsonify({'error': 'token_expired'}), 401
        except jwt.InvalidTokenError as e:
            logger.warning(f"Invalid token: {e}")
            return jsonify({'error': 'invalid_token'}), 401
        
        return f(*args, **kwargs)
    return decorated


def generate_jwt_token(user_id: int, email: str, expires_hours: int = 24 * 7) -> str:
    """Generate JWT token for mobile authentication"""
    from datetime import timedelta
    
    secret = os.environ.get('JWT_SECRET', os.environ.get('SECRET_KEY', 'dev-secret'))
    payload = {
        'user_id': user_id,
        'email': email,
        'iat': datetime.utcnow(),
        'exp': datetime.utcnow() + timedelta(hours=expires_hours)
    }
    return jwt.encode(payload, secret, algorithm='HS256')


def _generate_portfolio_slug():
    """Generate a URL-safe unique slug for portfolio sharing (11 chars, like nanoid)"""
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(11))


# =============================================================================
# Device Registration Endpoints
# =============================================================================

@mobile_api.route('/device/register', methods=['POST'])
@require_auth
def register_device():
    """
    Register a device for push notifications
    
    Request body:
    {
        "token": "fcm_or_apns_token",
        "platform": "ios" or "android",
        "device_id": "unique_device_identifier",
        "app_version": "1.0.0",
        "os_version": "iOS 17.2"
    }
    """
    from models import db, DeviceToken
    
    data = request.get_json()
    if not data:
        return jsonify({'error': 'missing_request_body'}), 400
    
    token = data.get('token')
    platform = data.get('platform')
    device_id = data.get('device_id')
    
    if not token or not platform:
        return jsonify({'error': 'token_and_platform_required'}), 400
    
    if platform not in ['ios', 'android']:
        return jsonify({'error': 'invalid_platform'}), 400
    
    try:
        # Check if device already registered
        existing = None
        if device_id:
            existing = DeviceToken.query.filter_by(
                user_id=g.user_id,
                device_id=device_id
            ).first()
        
        if existing:
            # Update existing token
            existing.token = token
            existing.platform = platform
            existing.app_version = data.get('app_version')
            existing.os_version = data.get('os_version')
            existing.is_active = True
            existing.updated_at = datetime.utcnow()
        else:
            # Create new device token
            device_token = DeviceToken(
                user_id=g.user_id,
                token=token,
                platform=platform,
                device_id=device_id,
                app_version=data.get('app_version'),
                os_version=data.get('os_version'),
                is_active=True
            )
            db.session.add(device_token)
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'device_registered'
        })
        
    except Exception as e:
        logger.error(f"Device registration error: {e}")
        db.session.rollback()
        return jsonify({'error': 'registration_failed'}), 500


@mobile_api.route('/device/unregister', methods=['DELETE'])
@require_auth
def unregister_device():
    """
    Unregister a device from push notifications
    
    Request body:
    {
        "device_id": "unique_device_identifier"
    }
    or
    {
        "token": "fcm_or_apns_token"
    }
    """
    from models import db, DeviceToken
    
    data = request.get_json()
    device_id = data.get('device_id') if data else None
    token = data.get('token') if data else None
    
    if not device_id and not token:
        return jsonify({'error': 'device_id_or_token_required'}), 400
    
    try:
        query = DeviceToken.query.filter_by(user_id=g.user_id)
        if device_id:
            query = query.filter_by(device_id=device_id)
        elif token:
            query = query.filter_by(token=token)
        
        device = query.first()
        if device:
            device.is_active = False
            db.session.commit()
        
        return jsonify({'success': True, 'message': 'device_unregistered'})
        
    except Exception as e:
        logger.error(f"Device unregistration error: {e}")
        return jsonify({'error': 'unregistration_failed'}), 500


# =============================================================================
# Purchase/Subscription Endpoints
# =============================================================================

@mobile_api.route('/purchase/validate', methods=['POST'])
@require_auth
def validate_purchase():
    """
    Validate an In-App Purchase and create subscription
    
    Request body:
    {
        "platform": "apple" or "google",
        "receipt_data": "base64_receipt_for_apple",
        "purchase_token": "token_for_google",
        "subscribed_to_id": 123  // Portfolio owner's user ID
    }
    """
    import asyncio
    from models import db
    from iap_validation_service import validate_and_save_purchase
    
    data = request.get_json()
    if not data:
        return jsonify({'error': 'missing_request_body'}), 400
    
    platform = data.get('platform')
    subscribed_to_id = data.get('subscribed_to_id')
    
    if not platform or not subscribed_to_id:
        return jsonify({'error': 'platform_and_subscribed_to_id_required'}), 400
    
    if platform not in ['apple', 'google']:
        return jsonify({'error': 'invalid_platform'}), 400
    
    receipt_data = data.get('receipt_data')
    purchase_token = data.get('purchase_token')
    
    if platform == 'apple' and not receipt_data:
        return jsonify({'error': 'receipt_data_required_for_apple'}), 400
    if platform == 'google' and not purchase_token:
        return jsonify({'error': 'purchase_token_required_for_google'}), 400
    
    try:
        # Run async validation
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        success, result = loop.run_until_complete(
            validate_and_save_purchase(
                db=db,
                subscriber_id=g.user_id,
                subscribed_to_id=subscribed_to_id,
                platform=platform,
                receipt_data=receipt_data,
                purchase_token=purchase_token
            )
        )
        loop.close()
        
        if success:
            return jsonify({
                'success': True,
                'purchase_id': result.get('purchase_id'),
                'subscription_status': result.get('status'),
                'expires_date': result.get('expires_date').isoformat() if result.get('expires_date') else None
            })
        else:
            return jsonify({
                'success': False,
                'error': result.get('error', 'validation_failed')
            }), 400
            
    except Exception as e:
        logger.error(f"Purchase validation error: {e}")
        return jsonify({'error': 'validation_failed'}), 500


@mobile_api.route('/subscriptions', methods=['GET'])
@require_auth
def get_subscriptions():
    """
    Get user's active subscriptions (both as subscriber and as portfolio owner)
    """
    from models import MobileSubscription, User, InAppPurchase
    
    try:
        # Subscriptions user has made
        made_subs = MobileSubscription.query.filter_by(
            subscriber_id=g.user_id
        ).all()
        
        # Users subscribed to this user
        received_subs = MobileSubscription.query.filter_by(
            subscribed_to_id=g.user_id
        ).all()
        
        subscriptions_made = []
        for sub in made_subs:
            owner = User.query.get(sub.subscribed_to_id)
            subscriptions_made.append({
                'id': sub.id,
                'portfolio_owner': {
                    'id': owner.id,
                    'username': owner.username,
                    'portfolio_slug': owner.portfolio_slug
                } if owner else None,
                'status': sub.status,
                'expires_at': sub.expires_at.isoformat() if sub.expires_at else None,
                'push_notifications_enabled': sub.push_notifications_enabled
            })
        
        subscribers = []
        for sub in received_subs:
            subscriber = User.query.get(sub.subscriber_id)
            subscribers.append({
                'id': sub.id,
                'subscriber': {
                    'id': subscriber.id,
                    'username': subscriber.username
                } if subscriber else None,
                'status': sub.status,
                'created_at': sub.created_at.isoformat()
            })
        
        return jsonify({
            'subscriptions_made': subscriptions_made,
            'subscribers': subscribers,
            'subscriber_count': len([s for s in received_subs if s.status == 'active'])
        })
        
    except Exception as e:
        logger.error(f"Get subscriptions error: {e}")
        return jsonify({'error': 'failed_to_get_subscriptions'}), 500


@mobile_api.route('/unsubscribe/<int:subscription_id>', methods=['DELETE'])
@require_auth
def unsubscribe(subscription_id):
    """Cancel a subscription"""
    from models import db, MobileSubscription
    
    try:
        subscription = MobileSubscription.query.filter_by(
            id=subscription_id,
            subscriber_id=g.user_id
        ).first()
        
        if not subscription:
            return jsonify({'error': 'subscription_not_found'}), 404
        
        # Note: This just marks it as canceled in our system
        # The actual subscription cancellation happens in the app store
        subscription.status = 'canceled'
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'subscription_canceled'})
        
    except Exception as e:
        logger.error(f"Unsubscribe error: {e}")
        return jsonify({'error': 'unsubscribe_failed'}), 500


# =============================================================================
# Portfolio Endpoints
# =============================================================================

@mobile_api.route('/portfolio/<slug>', methods=['GET'])
@require_auth
def get_portfolio(slug):
    """
    Get portfolio data for mobile app
    
    Returns full data if user is subscribed, limited data otherwise
    """
    from models import User, Stock, MobileSubscription, Transaction
    
    try:
        # Find portfolio owner by slug
        owner = User.query.filter_by(portfolio_slug=slug).first()
        if not owner:
            return jsonify({'error': 'portfolio_not_found'}), 404
        
        # Check if user is subscribed or is the owner
        is_owner = owner.id == g.user_id
        is_subscribed = False
        
        if not is_owner:
            subscription = MobileSubscription.query.filter_by(
                subscriber_id=g.user_id,
                subscribed_to_id=owner.id,
                status='active'
            ).first()
            is_subscribed = subscription is not None
        
        # Get basic portfolio info (always visible)
        response = {
            'owner': {
                'id': owner.id,
                'username': owner.username,
                'portfolio_slug': owner.portfolio_slug
            },
            'is_owner': is_owner,
            'is_subscribed': is_subscribed,
            'subscription_price': 9.00
        }
        
        # Get subscriber count
        subscriber_count = MobileSubscription.query.filter_by(
            subscribed_to_id=owner.id,
            status='active'
        ).count()
        response['subscriber_count'] = subscriber_count
        
        # If subscribed or owner, show full portfolio
        if is_owner or is_subscribed:
            stocks = Stock.query.filter_by(user_id=owner.id).all()
            response['holdings'] = [
                {
                    'ticker': stock.ticker,
                    'quantity': stock.quantity,
                    'purchase_price': stock.purchase_price,
                    'purchase_date': stock.purchase_date.isoformat() if stock.purchase_date else None
                }
                for stock in stocks
            ]
            
            # Get recent transactions
            recent_trades = Transaction.query.filter_by(
                user_id=owner.id
            ).order_by(Transaction.timestamp.desc()).limit(20).all()
            
            response['recent_trades'] = [
                {
                    'ticker': trade.ticker,
                    'quantity': trade.quantity,
                    'price': trade.price,
                    'type': trade.transaction_type,
                    'timestamp': trade.timestamp.isoformat()
                }
                for trade in recent_trades
            ]
        else:
            # Limited preview for non-subscribers
            response['holdings'] = None  # Blurred in app
            response['preview_message'] = 'Subscribe to view full portfolio holdings'
        
        return jsonify(response)
        
    except Exception as e:
        logger.error(f"Get portfolio error: {e}")
        return jsonify({'error': 'failed_to_get_portfolio'}), 500


@mobile_api.route('/portfolio/stocks', methods=['POST'])
@require_auth
def add_stocks():
    """
    Add stocks to the authenticated user's portfolio
    
    Request body:
    {
        "stocks": [
            {"ticker": "AAPL", "quantity": 10},
            {"ticker": "TSLA", "quantity": 5}
        ]
    }
    """
    from models import db, Stock
    
    data = request.get_json()
    if not data or 'stocks' not in data:
        return jsonify({'error': 'stocks_required'}), 400
    
    stocks_list = data['stocks']
    if not isinstance(stocks_list, list) or len(stocks_list) == 0:
        return jsonify({'error': 'stocks_must_be_non_empty_list'}), 400
    
    added_count = 0
    errors = []
    
    for item in stocks_list:
        ticker = item.get('ticker', '').strip().upper()
        quantity = item.get('quantity')
        
        if not ticker or not quantity:
            errors.append(f"Missing ticker or quantity")
            continue
        
        try:
            quantity = float(quantity)
            if quantity <= 0:
                errors.append(f"Invalid quantity for {ticker}")
                continue
        except (ValueError, TypeError):
            errors.append(f"Invalid quantity for {ticker}")
            continue
        
        try:
            # Check if user already has this stock
            existing = Stock.query.filter_by(user_id=g.user_id, ticker=ticker).first()
            if existing:
                existing.quantity += quantity
            else:
                stock = Stock(
                    ticker=ticker,
                    quantity=quantity,
                    purchase_price=0.0,
                    user_id=g.user_id
                )
                db.session.add(stock)
            added_count += 1
        except Exception as e:
            logger.error(f"Error adding stock {ticker}: {e}")
            errors.append(f"Failed to add {ticker}")
    
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error committing stocks: {e}")
        return jsonify({'error': 'failed_to_save_stocks'}), 500
    
    return jsonify({
        'success': True,
        'added_count': added_count,
        'errors': errors if errors else None
    })


@mobile_api.route('/leaderboard', methods=['GET'])
def get_leaderboard():
    """
    Get leaderboard for mobile app
    
    Query params:
    - period: 1D, 5D, 7D, 1M, 3M, YTD, 1Y (default: 7D)
    - category: all, large_cap, small_cap (default: all)
    - limit: number of entries (default: 50, max: 100)
    """
    from models import LeaderboardEntry, User
    
    try:
        period = request.args.get('period', '7D')
        category = request.args.get('category', 'all')
        limit = min(int(request.args.get('limit', 50)), 100)
        
        # Build query
        query = LeaderboardEntry.query.filter_by(period=period)
        
        if category == 'large_cap':
            query = query.filter(LeaderboardEntry.large_cap_percent >= 70)
        elif category == 'small_cap':
            query = query.filter(LeaderboardEntry.small_cap_percent >= 50)
        
        entries = query.order_by(LeaderboardEntry.performance_percent.desc()).limit(limit).all()
        
        leaderboard = []
        for rank, entry in enumerate(entries, start=1):
            user = User.query.get(entry.user_id)
            if user:
                leaderboard.append({
                    'rank': rank,
                    'user': {
                        'id': user.id,
                        'username': user.username,
                        'portfolio_slug': user.portfolio_slug
                    },
                    'return_percent': entry.performance_percent,
                    'subscriber_count': MobileSubscription.query.filter_by(
                        subscribed_to_id=user.id,
                        status='active'
                    ).count() if hasattr(MobileSubscription, 'query') else 0,
                    'subscription_price': 9.00
                })
        
        return jsonify({
            'period': period,
            'category': category,
            'entries': leaderboard
        })
        
    except Exception as e:
        logger.error(f"Get leaderboard error: {e}")
        return jsonify({'error': 'failed_to_get_leaderboard'}), 500


# =============================================================================
# Notification Settings
# =============================================================================

@mobile_api.route('/notifications/settings', methods=['PUT'])
@require_auth
def update_notification_settings():
    """
    Update notification preferences for a subscription
    
    Request body:
    {
        "subscription_id": 123,
        "push_notifications_enabled": true
    }
    """
    from models import db, MobileSubscription
    
    data = request.get_json()
    if not data:
        return jsonify({'error': 'missing_request_body'}), 400
    
    subscription_id = data.get('subscription_id')
    enabled = data.get('push_notifications_enabled')
    
    if subscription_id is None or enabled is None:
        return jsonify({'error': 'subscription_id_and_enabled_required'}), 400
    
    try:
        subscription = MobileSubscription.query.filter_by(
            id=subscription_id,
            subscriber_id=g.user_id
        ).first()
        
        if not subscription:
            return jsonify({'error': 'subscription_not_found'}), 404
        
        subscription.push_notifications_enabled = bool(enabled)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'push_notifications_enabled': subscription.push_notifications_enabled
        })
        
    except Exception as e:
        logger.error(f"Update notification settings error: {e}")
        return jsonify({'error': 'update_failed'}), 500


# =============================================================================
# Authentication Endpoints
# =============================================================================

@mobile_api.route('/auth/token', methods=['POST'])
def get_auth_token():
    """
    Exchange OAuth credentials for a JWT token
    
    Request body:
    {
        "provider": "apple" or "google",
        "id_token": "oauth_id_token",
        "email": "user@example.com"  // Optional, for new users
    }
    """
    from models import db, User
    
    data = request.get_json()
    if not data:
        return jsonify({'error': 'missing_request_body'}), 400
    
    provider = data.get('provider')
    id_token = data.get('id_token')
    
    if not provider or not id_token:
        return jsonify({'error': 'provider_and_id_token_required'}), 400
    
    try:
        # Verify the OAuth token
        # In production, you would validate the token with Apple/Google
        # For now, we'll decode it and trust the payload
        
        # This is a simplified version - production should validate properly
        if provider == 'apple':
            # Apple ID token validation would go here
            # For now, just decode without verification for development
            import jwt as pyjwt
            try:
                # Decode without verification (development only!)
                payload = pyjwt.decode(id_token, options={"verify_signature": False})
                oauth_id = payload.get('sub')
                email = payload.get('email') or data.get('email')
            except Exception:
                return jsonify({'error': 'invalid_apple_token'}), 400
                
        elif provider == 'google':
            # Google ID token validation
            try:
                import jwt as pyjwt
                payload = pyjwt.decode(id_token, options={"verify_signature": False})
                oauth_id = payload.get('sub')
                email = payload.get('email') or data.get('email')
            except Exception:
                return jsonify({'error': 'invalid_google_token'}), 400
        else:
            return jsonify({'error': 'invalid_provider'}), 400
        
        if not oauth_id:
            return jsonify({'error': 'oauth_id_not_found'}), 400
        
        # Find or create user
        user = User.query.filter_by(oauth_provider=provider, oauth_id=oauth_id).first()
        
        if not user and email:
            # Check if user exists with this email
            user = User.query.filter_by(email=email).first()
            if user:
                # Link OAuth to existing account
                user.oauth_provider = provider
                user.oauth_id = oauth_id
                db.session.commit()
        
        if not user:
            # Create new user
            if not email:
                return jsonify({'error': 'email_required_for_new_user'}), 400
            
            username = email.split('@')[0]
            # Ensure unique username
            base_username = username
            counter = 1
            while User.query.filter_by(username=username).first():
                username = f"{base_username}{counter}"
                counter += 1
            
            user = User(
                email=email,
                username=username,
                oauth_provider=provider,
                oauth_id=oauth_id,
                portfolio_slug=_generate_portfolio_slug()
            )
            db.session.add(user)
            db.session.commit()
        
        # Generate slug for existing users who don't have one
        if not user.portfolio_slug:
            user.portfolio_slug = _generate_portfolio_slug()
            db.session.commit()
        
        # Generate JWT token
        token = generate_jwt_token(user.id, user.email)
        
        return jsonify({
            'success': True,
            'token': token,
            'user': {
                'id': user.id,
                'email': user.email,
                'username': user.username,
                'portfolio_slug': user.portfolio_slug
            }
        })
        
    except Exception as e:
        import traceback
        logger.error(f"Auth token error: {e}")
        logger.error(f"Auth token traceback: {traceback.format_exc()}")
        return jsonify({'error': f'authentication_failed: {str(e)}'}), 500


@mobile_api.route('/auth/user', methods=['GET'])
@require_auth
def get_current_user():
    """Get the authenticated user's profile data"""
    from models import db, User
    
    try:
        user = User.query.get(g.user_id)
        if not user:
            return jsonify({'error': 'user_not_found'}), 404
        
        # Generate slug if missing
        if not user.portfolio_slug:
            user.portfolio_slug = _generate_portfolio_slug()
            db.session.commit()
        
        return jsonify({
            'id': user.id,
            'email': user.email,
            'username': user.username,
            'portfolio_slug': user.portfolio_slug
        })
        
    except Exception as e:
        logger.error(f"Get current user error: {e}")
        return jsonify({'error': 'failed_to_get_user'}), 500


@mobile_api.route('/auth/account', methods=['DELETE'])
@require_auth
def delete_account():
    """Delete the authenticated user's account and all associated data"""
    from models import db, User, Stock, Transaction, DeviceToken, MobileSubscription
    
    try:
        user = User.query.get(g.user_id)
        if not user:
            return jsonify({'error': 'user_not_found'}), 404
        
        # Delete associated data
        Stock.query.filter_by(user_id=g.user_id).delete()
        Transaction.query.filter_by(user_id=g.user_id).delete()
        DeviceToken.query.filter_by(user_id=g.user_id).delete()
        MobileSubscription.query.filter(
            (MobileSubscription.subscriber_id == g.user_id) |
            (MobileSubscription.subscribed_to_id == g.user_id)
        ).delete(synchronize_session='fetch')
        
        db.session.delete(user)
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'account_deleted'})
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Delete account error: {e}")
        return jsonify({'error': 'delete_failed'}), 500


@mobile_api.route('/auth/refresh', methods=['POST'])
@require_auth
def refresh_token():
    """Refresh the JWT token"""
    from models import User
    
    try:
        user = User.query.get(g.user_id)
        if not user:
            return jsonify({'error': 'user_not_found'}), 404
        
        token = generate_jwt_token(user.id, user.email)
        
        return jsonify({
            'success': True,
            'token': token
        })
        
    except Exception as e:
        logger.error(f"Token refresh error: {e}")
        return jsonify({'error': 'refresh_failed'}), 500


# =============================================================================
# Health Check Endpoint
# =============================================================================

@mobile_api.route('/health', methods=['GET'])
def health_check():
    """
    Health check endpoint for mobile API
    Returns status of all required services
    """
    import os
    
    health = {
        'status': 'ok',
        'api_version': '1.0.0',
        'services': {}
    }
    
    # Check Firebase
    try:
        from push_notification_service import get_push_service
        push_service = get_push_service()
        health['services']['firebase'] = {
            'available': push_service.is_available,
            'status': 'configured' if push_service.is_available else 'not_configured'
        }
    except Exception as e:
        health['services']['firebase'] = {
            'available': False,
            'status': 'error',
            'error': str(e)
        }
    
    # Check IAP service config
    apple_configured = bool(os.environ.get('APPLE_SHARED_SECRET'))
    google_configured = bool(os.environ.get('GOOGLE_PLAY_CREDENTIALS_JSON'))
    health['services']['iap'] = {
        'apple': 'configured' if apple_configured else 'not_configured',
        'google': 'configured' if google_configured else 'not_configured'
    }
    
    # Check JWT config
    jwt_configured = bool(os.environ.get('JWT_SECRET') or os.environ.get('SECRET_KEY'))
    health['services']['jwt'] = {
        'status': 'configured' if jwt_configured else 'using_default'
    }
    
    # Overall status
    if not push_service.is_available:
        health['status'] = 'degraded'
        health['message'] = 'Push notifications not available - Firebase not configured'
    
    return jsonify(health)
