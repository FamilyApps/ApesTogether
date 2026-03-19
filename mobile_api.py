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
    from models import User
    
    period = request.args.get('period', '7D')
    category = request.args.get('category', 'all')
    limit = min(int(request.args.get('limit', 50)), 100)
    
    try:
        from models import LeaderboardEntry, MobileSubscription
        
        # Build query
        query = LeaderboardEntry.query.filter_by(period=period)
        
        try:
            if category == 'large_cap':
                query = query.filter(LeaderboardEntry.large_cap_percent >= 70)
            elif category == 'small_cap':
                query = query.filter(LeaderboardEntry.small_cap_percent >= 50)
            
            entries = query.order_by(LeaderboardEntry.performance_percent.desc()).limit(limit).all()
        except Exception:
            # Fallback if cap columns don't exist in production
            try:
                entries = LeaderboardEntry.query.filter_by(period=period).order_by(
                    LeaderboardEntry.performance_percent.desc()
                ).limit(limit).all()
            except Exception:
                entries = []
        
        leaderboard = []
        for rank, entry in enumerate(entries, start=1):
            user = User.query.get(entry.user_id)
            if user:
                try:
                    sub_count = MobileSubscription.query.filter_by(
                        subscribed_to_id=user.id,
                        status='active'
                    ).count()
                except Exception:
                    sub_count = 0
                    
                leaderboard.append({
                    'rank': rank,
                    'user': {
                        'id': user.id,
                        'username': user.username,
                        'portfolio_slug': user.portfolio_slug
                    },
                    'return_percent': entry.performance_percent,
                    'subscriber_count': sub_count,
                    'subscription_price': 9.00
                })
        
        return jsonify({
            'period': period,
            'category': category,
            'entries': leaderboard
        })
        
    except Exception as e:
        logger.error(f"Get leaderboard error: {e}")
        # Return empty leaderboard instead of 500
        return jsonify({
            'period': period,
            'category': category,
            'entries': []
        })


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


# =============================================================================
# Top Influencers (by Subscriber Count)
# =============================================================================

@mobile_api.route('/top-influencers', methods=['GET'])
@require_auth
def get_top_influencers():
    """
    GET /api/mobile/top-influencers?industry=Technology&limit=20
    Returns users ranked by subscriber count, optionally filtered by industry.
    """
    from models import User, UserPortfolioStats, MobileSubscription
    
    industry = request.args.get('industry', 'all')
    limit = min(int(request.args.get('limit', 20)), 50)
    
    try:
        # Query UserPortfolioStats joined with User, ordered by subscriber_count desc
        query = db.session.query(UserPortfolioStats, User).join(
            User, UserPortfolioStats.user_id == User.id
        ).filter(
            UserPortfolioStats.subscriber_count > 0
        )
        
        # Industry filter: check if the industry appears in the JSON industry_mix
        if industry and industry.lower() != 'all':
            try:
                # Filter users where the industry exists in their industry_mix JSON
                # and represents >= 10% of their portfolio
                query = query.filter(
                    UserPortfolioStats.industry_mix.isnot(None)
                )
            except Exception:
                pass
        
        results = query.order_by(
            UserPortfolioStats.subscriber_count.desc()
        ).limit(limit).all()
        
        entries = []
        rank = 0
        for stats, user in results:
            # If industry filter is active, check the JSON in Python
            if industry and industry.lower() != 'all':
                mix = stats.industry_mix or {}
                # Check if the filtered industry exists with >= 10%
                matched = False
                for ind_name, pct in mix.items():
                    if industry.lower() in ind_name.lower() and pct >= 5:
                        matched = True
                        break
                if not matched:
                    continue
            
            rank += 1
            # Get top industries for display
            top_industries = []
            if stats.industry_mix:
                sorted_industries = sorted(stats.industry_mix.items(), key=lambda x: x[1], reverse=True)
                top_industries = [
                    {'name': name, 'percent': round(pct, 1)}
                    for name, pct in sorted_industries[:3]
                ]
            
            entries.append({
                'rank': rank,
                'user': {
                    'id': user.id,
                    'username': user.username,
                    'portfolio_slug': user.portfolio_slug
                },
                'subscriber_count': stats.subscriber_count or 0,
                'unique_stocks': stats.unique_stocks_count or 0,
                'avg_trades_per_week': round(stats.avg_trades_per_week or 0, 1),
                'top_industries': top_industries
            })
        
        # Get available industries for filter UI
        all_industries = set()
        try:
            all_stats = UserPortfolioStats.query.filter(
                UserPortfolioStats.industry_mix.isnot(None),
                UserPortfolioStats.subscriber_count > 0
            ).all()
            for s in all_stats:
                if s.industry_mix:
                    for ind_name, pct in s.industry_mix.items():
                        if pct >= 5:
                            all_industries.add(ind_name)
        except Exception:
            pass
        
        return jsonify({
            'entries': entries,
            'available_industries': sorted(list(all_industries)),
            'total': len(entries)
        })
        
    except Exception as e:
        logger.error(f"Top influencers error: {e}")
        return jsonify({'entries': [], 'available_industries': [], 'total': 0})


# =============================================================================
# Portfolio Performance / Chart Data
# =============================================================================

@mobile_api.route('/portfolio/<slug>/chart', methods=['GET'])
@require_auth
def get_portfolio_chart(slug):
    """
    Get portfolio performance chart data with S&P 500 overlay.
    
    Query params:
    - period: 1D, 5D, 7D, 1M, 3M, YTD, 1Y (default: 7D)
    
    Returns chart_data array with {date, portfolio, sp500} points.
    """
    from models import User, PortfolioSnapshot, MarketData
    
    period = request.args.get('period', '7D')
    valid_periods = ['1D', '5D', '7D', '1M', '3M', 'YTD', '1Y']
    if period not in valid_periods:
        return jsonify({'error': f'Invalid period. Must be one of: {", ".join(valid_periods)}'}), 400
    
    try:
        # Find portfolio owner
        owner = User.query.filter_by(portfolio_slug=slug).first()
        if not owner:
            return jsonify({'error': 'portfolio_not_found'}), 404
        
        # Check access: must be owner or subscribed
        is_owner = owner.id == g.user_id
        is_subscribed = False
        if not is_owner:
            try:
                from models import MobileSubscription
                is_subscribed = MobileSubscription.query.filter_by(
                    subscriber_id=g.user_id,
                    subscribed_to_id=owner.id,
                    status='active'
                ).first() is not None
            except Exception:
                pass
        
        if not is_owner and not is_subscribed:
            return jsonify({'error': 'subscription_required'}), 403
        
        # Try to use the unified performance calculator
        chart_data = []
        portfolio_return = 0.0
        sp500_return = 0.0
        
        try:
            from performance_calculator import calculate_portfolio_performance, get_period_dates
            start_date, end_date = get_period_dates(period, user_id=owner.id)
            result = calculate_portfolio_performance(
                owner.id, start_date, end_date,
                include_chart_data=True, period=period
            )
            if result and result.get('chart_data'):
                chart_data = result['chart_data']
                portfolio_return = result.get('portfolio_return', 0.0)
                sp500_return = result.get('sp500_return', 0.0)
        except Exception as e:
            logger.warning(f"Performance calculator failed for user {owner.id}: {e}")
        
        # Fallback: generate basic chart from snapshots
        if not chart_data:
            try:
                from leaderboard_utils import generate_chart_from_snapshots
                chart_result = generate_chart_from_snapshots(owner.id, period)
                if chart_result:
                    # Convert Chart.js format to flat array
                    labels = chart_result.get('labels', [])
                    datasets = chart_result.get('datasets', [])
                    portfolio_vals = datasets[0]['data'] if len(datasets) > 0 else []
                    sp500_vals = datasets[1]['data'] if len(datasets) > 1 else []
                    
                    for i, label in enumerate(labels):
                        chart_data.append({
                            'date': label,
                            'portfolio': portfolio_vals[i] if i < len(portfolio_vals) else None,
                            'sp500': sp500_vals[i] if i < len(sp500_vals) else 0
                        })
                    
                    portfolio_return = chart_result.get('portfolio_return', 0.0)
                    sp500_return = chart_result.get('sp500_return', 0.0)
            except Exception as e:
                logger.warning(f"Chart generation fallback failed: {e}")
        
        # Final fallback: return empty chart with just S&P data
        if not chart_data:
            try:
                from datetime import timedelta, date as dt_date
                today = dt_date.today()
                
                period_days = {'1D': 1, '5D': 5, '7D': 7, '1M': 30, '3M': 90, 'YTD': (today - dt_date(today.year, 1, 1)).days, '1Y': 365}
                days_back = period_days.get(period, 7)
                start = today - timedelta(days=days_back)
                
                sp500_records = MarketData.query.filter(
                    MarketData.ticker == 'SPY_SP500',
                    MarketData.date >= start,
                    MarketData.date <= today
                ).order_by(MarketData.date.asc()).all()
                
                if sp500_records:
                    base_sp500 = float(sp500_records[0].close_price)
                    for rec in sp500_records:
                        sp500_pct = ((float(rec.close_price) - base_sp500) / base_sp500) * 100 if base_sp500 > 0 else 0
                        chart_data.append({
                            'date': rec.date.strftime('%b %d'),
                            'portfolio': None,
                            'sp500': round(sp500_pct, 2)
                        })
            except Exception as e:
                logger.warning(f"S&P fallback failed: {e}")
        
        return jsonify({
            'portfolio_return': round(portfolio_return, 2),
            'sp500_return': round(sp500_return, 2),
            'chart_data': chart_data,
            'period': period
        })
        
    except Exception as e:
        logger.error(f"Get portfolio chart error: {e}")
        return jsonify({
            'portfolio_return': 0,
            'sp500_return': 0,
            'chart_data': [],
            'period': period
        })


# =============================================================================
# Trade Endpoints (Buy / Sell)
# =============================================================================

@mobile_api.route('/portfolio/trade', methods=['POST'])
@require_auth
def execute_trade():
    """
    Execute a buy or sell trade.
    
    Request body:
    {
        "ticker": "AAPL",
        "quantity": 10,
        "price": 175.50,
        "type": "buy" or "sell"
    }
    """
    from models import db, Stock, Transaction
    
    data = request.get_json()
    if not data:
        return jsonify({'error': 'missing_request_body'}), 400
    
    ticker = (data.get('ticker') or '').strip().upper()
    quantity = data.get('quantity')
    price = data.get('price', 0)
    trade_type = (data.get('type') or '').lower()
    
    if not ticker:
        return jsonify({'error': 'ticker_required'}), 400
    if not quantity or quantity <= 0:
        return jsonify({'error': 'positive_quantity_required'}), 400
    if trade_type not in ('buy', 'sell'):
        return jsonify({'error': 'type_must_be_buy_or_sell'}), 400
    
    try:
        existing = Stock.query.filter_by(user_id=g.user_id, ticker=ticker).first()
        
        if trade_type == 'sell':
            if not existing or existing.quantity < quantity:
                available = existing.quantity if existing else 0
                return jsonify({'error': 'insufficient_shares', 'available': available}), 400
            
            existing.quantity -= quantity
            if existing.quantity == 0:
                db.session.delete(existing)
        else:
            # Buy
            if existing:
                # Update average cost
                total_cost = (existing.purchase_price * existing.quantity) + (price * quantity)
                existing.quantity += quantity
                existing.purchase_price = total_cost / existing.quantity if existing.quantity > 0 else price
            else:
                stock = Stock(
                    ticker=ticker,
                    quantity=quantity,
                    purchase_price=price,
                    user_id=g.user_id
                )
                db.session.add(stock)
        
        # Record the transaction
        try:
            transaction = Transaction(
                ticker=ticker,
                quantity=quantity,
                price=price,
                transaction_type=trade_type.upper(),
                user_id=g.user_id,
                timestamp=datetime.utcnow()
            )
            db.session.add(transaction)
        except Exception as tx_err:
            logger.warning(f"Failed to record transaction: {tx_err}")
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'trade': {
                'ticker': ticker,
                'quantity': quantity,
                'price': price,
                'type': trade_type
            }
        })
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Trade execution error: {e}")
        return jsonify({'error': 'trade_failed'}), 500


# =============================================================================
# Admin Bot Backdoor API
# =============================================================================

def require_admin_key(f):
    """Decorator to require admin API key for bot endpoints"""
    @wraps(f)
    def decorated(*args, **kwargs):
        admin_key = request.headers.get('X-Admin-Key')
        expected_key = os.environ.get('ADMIN_API_KEY')
        
        if not expected_key:
            return jsonify({'error': 'admin_api_not_configured'}), 503
        
        if not admin_key or admin_key != expected_key:
            return jsonify({'error': 'invalid_admin_key'}), 403
        
        return f(*args, **kwargs)
    return decorated


@mobile_api.route('/admin/bot/create-user', methods=['POST'])
@require_admin_key
def bot_create_user():
    """
    Create a bot user account.
    
    Request body:
    {
        "username": "trader_bot_1",
        "email": "bot1@apestogether.ai"
    }
    """
    from models import db, User
    
    data = request.get_json()
    if not data:
        return jsonify({'error': 'missing_request_body'}), 400
    
    username = data.get('username')
    email = data.get('email')
    
    if not username or not email:
        return jsonify({'error': 'username_and_email_required'}), 400
    
    try:
        # Check for existing
        existing = User.query.filter(
            (User.username == username) | (User.email == email)
        ).first()
        if existing:
            return jsonify({'error': 'user_already_exists', 'user_id': existing.id}), 409
        
        industry = data.get('industry', 'General')
        
        user = User(
            username=username,
            email=email,
            portfolio_slug=_generate_portfolio_slug(),
            role='agent',
            created_by='system',
            subscription_price=9.00,
            extra_data={
                'industry': industry,
                'bot_active': True,
                'bot_created_at': datetime.utcnow().isoformat()
            }
        )
        db.session.add(user)
        db.session.commit()
        
        # Generate a long-lived token for the bot
        token = generate_jwt_token(user.id, user.email, expires_hours=24 * 365)
        
        return jsonify({
            'success': True,
            'user': {
                'id': user.id,
                'username': user.username,
                'email': user.email,
                'portfolio_slug': user.portfolio_slug,
                'role': user.role,
                'industry': industry
            },
            'token': token
        })
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Bot create user error: {e}")
        return jsonify({'error': 'create_failed'}), 500


@mobile_api.route('/admin/bot/add-stocks', methods=['POST'])
@require_admin_key
def bot_add_stocks():
    """
    Add stocks to a bot user's portfolio.
    
    Request body:
    {
        "user_id": 123,
        "stocks": [
            {"ticker": "AAPL", "quantity": 50, "purchase_price": 175.00},
            {"ticker": "TSLA", "quantity": 25, "purchase_price": 250.00}
        ]
    }
    """
    from models import db, User, Stock
    
    data = request.get_json()
    if not data:
        return jsonify({'error': 'missing_request_body'}), 400
    
    user_id = data.get('user_id')
    stocks_list = data.get('stocks', [])
    
    if not user_id or not stocks_list:
        return jsonify({'error': 'user_id_and_stocks_required'}), 400
    
    try:
        user = User.query.get(user_id)
        if not user:
            return jsonify({'error': 'user_not_found'}), 404
        
        added = 0
        for item in stocks_list:
            ticker = (item.get('ticker') or '').strip().upper()
            quantity = item.get('quantity', 0)
            price = item.get('purchase_price', 0)
            
            if not ticker or quantity <= 0:
                continue
            
            existing = Stock.query.filter_by(user_id=user_id, ticker=ticker).first()
            if existing:
                existing.quantity += quantity
            else:
                stock = Stock(
                    ticker=ticker,
                    quantity=quantity,
                    purchase_price=price,
                    user_id=user_id
                )
                db.session.add(stock)
            added += 1
        
        db.session.commit()
        return jsonify({'success': True, 'added_count': added})
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Bot add stocks error: {e}")
        return jsonify({'error': 'add_stocks_failed'}), 500


@mobile_api.route('/admin/bot/set-cash', methods=['POST'])
@require_admin_key
def bot_set_cash():
    """
    Set cash tracking values for a bot user (used during portfolio seeding).
    
    Request body:
    {
        "user_id": 123,
        "max_cash_deployed": 10000.00,
        "cash_proceeds": 50.00
    }
    """
    from models import db, User
    
    data = request.get_json()
    if not data:
        return jsonify({'error': 'missing_request_body'}), 400
    
    user_id = data.get('user_id')
    if not user_id:
        return jsonify({'error': 'user_id_required'}), 400
    
    try:
        user = User.query.get(user_id)
        if not user:
            return jsonify({'error': 'user_not_found'}), 404
        
        if 'max_cash_deployed' in data:
            user.max_cash_deployed = float(data['max_cash_deployed'])
        if 'cash_proceeds' in data:
            user.cash_proceeds = float(data['cash_proceeds'])
        if 'extra_data' in data and isinstance(data['extra_data'], dict):
            if not user.extra_data or not isinstance(user.extra_data, dict):
                user.extra_data = {}
            user.extra_data = {**user.extra_data, **data['extra_data']}
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'user_id': user_id,
            'max_cash_deployed': user.max_cash_deployed,
            'cash_proceeds': user.cash_proceeds
        })
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Bot set cash error: {e}")
        return jsonify({'error': 'set_cash_failed'}), 500


@mobile_api.route('/admin/bot/scale-holdings', methods=['POST'])
@require_admin_key
def bot_scale_holdings():
    """
    Scale all holdings and cash values for a bot user by a multiplier.
    Used to obfuscate portfolio values so they don't match source accounts.
    
    Request body:
    {
        "user_id": 123,
        "multiplier": 1.37
    }
    """
    from models import db, User, Stock
    
    data = request.get_json()
    if not data:
        return jsonify({'error': 'missing_request_body'}), 400
    
    user_id = data.get('user_id')
    multiplier = data.get('multiplier')
    
    if not user_id or not multiplier:
        return jsonify({'error': 'user_id_and_multiplier_required'}), 400
    
    if multiplier <= 0:
        return jsonify({'error': 'multiplier_must_be_positive'}), 400
    
    try:
        user = User.query.get(user_id)
        if not user:
            return jsonify({'error': 'user_not_found'}), 404
        
        # Scale all stock quantities
        stocks = Stock.query.filter_by(user_id=user_id).all()
        scaled_stocks = []
        for stock in stocks:
            old_qty = stock.quantity
            stock.quantity = round(old_qty * multiplier, 6)
            scaled_stocks.append({
                'ticker': stock.ticker,
                'old_quantity': old_qty,
                'new_quantity': stock.quantity
            })
        
        # Scale cash tracking values
        old_cash = user.cash_proceeds or 0
        old_deployed = user.max_cash_deployed or 0
        user.cash_proceeds = round(old_cash * multiplier, 2)
        user.max_cash_deployed = round(old_deployed * multiplier, 2)
        
        # Store the cumulative trade multiplier so future email trades get scaled too
        if not user.extra_data or not isinstance(user.extra_data, dict):
            user.extra_data = {}
        existing_multiplier = float(user.extra_data.get('trade_multiplier', 1.0))
        user.extra_data = {**user.extra_data, 'trade_multiplier': round(existing_multiplier * multiplier, 6)}
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'user_id': user_id,
            'multiplier': multiplier,
            'stocks_scaled': len(scaled_stocks),
            'cash_proceeds': {'old': old_cash, 'new': user.cash_proceeds},
            'max_cash_deployed': {'old': old_deployed, 'new': user.max_cash_deployed},
            'stocks': scaled_stocks
        })
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Bot scale holdings error: {e}")
        return jsonify({'error': 'scale_holdings_failed'}), 500


@mobile_api.route('/admin/bot/subscribe', methods=['POST'])
@require_admin_key
def bot_subscribe():
    """
    Create a subscription from one user to another.
    
    Request body:
    {
        "subscriber_id": 123,
        "subscribed_to_id": 456
    }
    """
    from models import db, MobileSubscription
    
    data = request.get_json()
    if not data:
        return jsonify({'error': 'missing_request_body'}), 400
    
    subscriber_id = data.get('subscriber_id')
    subscribed_to_id = data.get('subscribed_to_id')
    
    if not subscriber_id or not subscribed_to_id:
        return jsonify({'error': 'subscriber_id_and_subscribed_to_id_required'}), 400
    
    try:
        # Check for existing subscription
        existing = MobileSubscription.query.filter_by(
            subscriber_id=subscriber_id,
            subscribed_to_id=subscribed_to_id,
            status='active'
        ).first()
        
        if existing:
            return jsonify({'error': 'already_subscribed', 'subscription_id': existing.id}), 409
        
        from datetime import timedelta
        sub = MobileSubscription(
            subscriber_id=subscriber_id,
            subscribed_to_id=subscribed_to_id,
            platform='admin_bot',
            status='active',
            expires_at=datetime.utcnow() + timedelta(days=365),
            push_notifications_enabled=False
        )
        db.session.add(sub)
        db.session.commit()
        
        return jsonify({'success': True, 'subscription_id': sub.id})
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Bot subscribe error: {e}")
        return jsonify({'error': 'subscribe_failed'}), 500


@mobile_api.route('/admin/bot/execute-trade', methods=['POST'])
@require_admin_key
def bot_execute_trade():
    """
    Execute a trade for a bot user.
    
    Request body:
    {
        "user_id": 123,
        "ticker": "AAPL",
        "quantity": 10,
        "price": 175.50,
        "type": "buy" or "sell"
    }
    """
    from models import db, Stock, Transaction
    
    data = request.get_json()
    if not data:
        return jsonify({'error': 'missing_request_body'}), 400
    
    user_id = data.get('user_id')
    ticker = (data.get('ticker') or '').strip().upper()
    quantity = data.get('quantity', 0)
    price = data.get('price', 0)
    trade_type = (data.get('type') or '').lower()
    
    if not user_id or not ticker or quantity <= 0:
        return jsonify({'error': 'user_id_ticker_quantity_required'}), 400
    if trade_type not in ('buy', 'sell'):
        return jsonify({'error': 'type_must_be_buy_or_sell'}), 400
    
    try:
        existing = Stock.query.filter_by(user_id=user_id, ticker=ticker).first()
        
        if trade_type == 'sell':
            if not existing or existing.quantity < quantity:
                return jsonify({'error': 'insufficient_shares'}), 400
            existing.quantity -= quantity
            if existing.quantity == 0:
                db.session.delete(existing)
        else:
            if existing:
                total_cost = (existing.purchase_price * existing.quantity) + (price * quantity)
                existing.quantity += quantity
                existing.purchase_price = total_cost / existing.quantity if existing.quantity > 0 else price
            else:
                stock = Stock(ticker=ticker, quantity=quantity, purchase_price=price, user_id=user_id)
                db.session.add(stock)
        
        try:
            transaction = Transaction(
                ticker=ticker, quantity=quantity, price=price,
                transaction_type=trade_type.upper(), user_id=user_id,
                timestamp=datetime.utcnow()
            )
            db.session.add(transaction)
        except Exception:
            pass
        
        db.session.commit()
        return jsonify({'success': True})
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Bot trade error: {e}")
        return jsonify({'error': 'trade_failed'}), 500


@mobile_api.route('/admin/bot/list-users', methods=['GET'])
@require_admin_key
def bot_list_users():
    """List all users with their portfolio info, filterable by role"""
    from models import User, Stock, Transaction, MobileSubscription
    
    try:
        role_filter = request.args.get('role')  # 'agent', 'user', or None for all
        query = User.query
        if role_filter:
            query = query.filter(User.role == role_filter)
        
        users = query.order_by(User.created_at.desc()).all()
        user_list = []
        for u in users:
            stock_count = Stock.query.filter_by(user_id=u.id).count()
            trade_count = Transaction.query.filter_by(user_id=u.id).count()
            subscriber_count = MobileSubscription.query.filter_by(
                subscribed_to_id=u.id, status='active'
            ).count()
            
            extra = u.extra_data or {}
            industry = extra.get('industry', 'General')
            bot_active = extra.get('bot_active', True) if u.role == 'agent' else None
            
            user_list.append({
                'id': u.id,
                'username': u.username,
                'email': u.email,
                'portfolio_slug': u.portfolio_slug,
                'role': u.role or 'user',
                'created_by': u.created_by or 'human',
                'created_at': u.created_at.isoformat() if u.created_at else None,
                'industry': industry,
                'bot_active': bot_active,
                'stock_count': stock_count,
                'trade_count': trade_count,
                'subscriber_count': subscriber_count
            })
        return jsonify({'users': user_list, 'total': len(user_list)})
    except Exception as e:
        logger.error(f"Bot list users error: {e}")
        return jsonify({'error': 'list_failed'}), 500


@mobile_api.route('/admin/bot/dashboard', methods=['GET'])
@require_admin_key
def bot_dashboard():
    """Get summary stats for the admin dashboard"""
    from models import User, Stock, Transaction, MobileSubscription
    
    try:
        total_users = User.query.count()
        bot_users = User.query.filter(User.role == 'agent').count()
        human_users = total_users - bot_users
        
        # Active bots (bot_active=True in extra_data)
        active_bots = 0
        inactive_bots = 0
        bots = User.query.filter(User.role == 'agent').all()
        industry_counts = {}
        for b in bots:
            extra = b.extra_data or {}
            if extra.get('bot_active', True):
                active_bots += 1
            else:
                inactive_bots += 1
            ind = extra.get('industry', 'General')
            industry_counts[ind] = industry_counts.get(ind, 0) + 1
        
        total_stocks = Stock.query.count()
        total_trades = Transaction.query.count()
        total_subscriptions = MobileSubscription.query.filter_by(status='active').count()
        
        # Gifted subscriptions (platform='admin_gift')
        gifted_subs = MobileSubscription.query.filter_by(
            platform='admin_gift', status='active'
        ).count()
        
        return jsonify({
            'total_users': total_users,
            'human_users': human_users,
            'bot_users': bot_users,
            'active_bots': active_bots,
            'inactive_bots': inactive_bots,
            'industry_breakdown': industry_counts,
            'total_stocks': total_stocks,
            'total_trades': total_trades,
            'total_subscriptions': total_subscriptions,
            'gifted_subscriptions': gifted_subs
        })
    except Exception as e:
        logger.error(f"Bot dashboard error: {e}")
        return jsonify({'error': 'dashboard_failed'}), 500


@mobile_api.route('/admin/bot/trade', methods=['POST'])
@require_admin_key
def bot_trade_cron():
    """
    Trigger bot trading for a specific wave. Designed to be called by an external
    scheduler (GitHub Actions, cron) at staggered times during market hours.
    
    POST body (JSON):
        wave: int (1-4) — which trading wave to execute
        dry_run: bool (optional, default false)
    
    Wave schedule (ET):
        Wave 1: ~9:45 AM   (market open traders)
        Wave 2: ~10:45 AM  (mid-morning traders)
        Wave 3: ~1:15 PM   (afternoon traders)
        Wave 4: ~3:30 PM   (close traders)
    
    Each bot is assigned preferred waves in its strategy profile.
    Not all bots trade every day (frequency + patience controls).
    """
    import random
    from datetime import timedelta
    
    data = request.get_json() or {}
    wave = data.get('wave')
    dry_run = data.get('dry_run', False)
    
    if not wave or wave not in [1, 2, 3, 4]:
        return jsonify({'error': 'wave required (1-4)'}), 400
    
    try:
        from models import db, User, Stock
        
        # Get active bot users
        bots = User.query.filter_by(role='agent', bot_active=True).all()
        if not bots:
            return jsonify({'success': True, 'message': 'No active bots', 'trades': 0})
        
        results = {
            'wave': wave,
            'dry_run': dry_run,
            'bots_checked': len(bots),
            'bots_traded': 0,
            'trades_executed': 0,
            'decisions': [],
            'errors': []
        }
        
        # Lazy-import bot modules (heavy dependencies)
        try:
            from bot_strategies import generate_strategy_profile, generate_trade_decisions, compute_signal_score
            from bot_behaviors import should_trade_today, get_trade_wave, apply_human_biases, apply_fomo_trades
            from bot_data_hub import MarketDataHub
        except ImportError as e:
            return jsonify({'error': f'Bot modules not available: {e}'}), 500
        
        # Refresh market data once for all bots
        hub = MarketDataHub()
        hub.refresh(include_extras=True)
        
        if not hub.is_core_available():
            return jsonify({'error': 'Market data unavailable'}), 503
        
        for bot in bots:
            try:
                # Load or generate profile
                import json, os
                profile_path = os.path.join('.bot_profiles', f'{bot.id}.json')
                if os.path.exists(profile_path):
                    with open(profile_path) as f:
                        profile = json.load(f)
                else:
                    profile = generate_strategy_profile('balanced', bot.industry or 'General')
                
                # Check if bot should trade today
                if not should_trade_today(profile):
                    continue
                
                # Check if bot is in this wave
                bot_wave = get_trade_wave(profile)
                if bot_wave != wave:
                    continue
                
                # Get holdings
                holdings = []
                stocks = Stock.query.filter_by(user_id=bot.id).all()
                for s in stocks:
                    if s.quantity > 0:
                        holdings.append({
                            'ticker': s.ticker,
                            'quantity': s.quantity,
                            'purchase_price': float(s.purchase_price) if s.purchase_price else 0
                        })
                
                # Generate decisions
                decisions = generate_trade_decisions(profile, hub, holdings)
                decisions = apply_human_biases(decisions, profile)
                fomo = apply_fomo_trades(profile, hub, decisions)
                if fomo:
                    decisions.extend(fomo)
                
                if not decisions:
                    continue
                
                results['bots_traded'] += 1
                
                for d in decisions:
                    decision_info = {
                        'bot_id': bot.id,
                        'username': bot.username,
                        'action': d['action'],
                        'ticker': d['ticker'],
                        'score': round(d['score'], 3)
                    }
                    
                    if dry_run:
                        decision_info['status'] = 'dry_run'
                        results['decisions'].append(decision_info)
                        continue
                    
                    # Execute trade via the existing bot execute-trade endpoint logic
                    try:
                        action = d['action']
                        ticker = d['ticker']
                        quantity = d.get('quantity', 1)
                        price = d.get('price', 0)
                        
                        if action == 'buy':
                            from models import Transaction
                            stock = Stock.query.filter_by(user_id=bot.id, ticker=ticker).first()
                            if stock:
                                stock.quantity += quantity
                                stock.purchase_price = price
                            else:
                                stock = Stock(user_id=bot.id, ticker=ticker, quantity=quantity, purchase_price=price)
                                db.session.add(stock)
                            
                            tx = Transaction(user_id=bot.id, ticker=ticker, quantity=quantity,
                                           price=price, type='buy', notes=f'Bot wave {wave}')
                            db.session.add(tx)
                            
                        elif action == 'sell':
                            stock = Stock.query.filter_by(user_id=bot.id, ticker=ticker).first()
                            if stock and stock.quantity >= quantity:
                                stock.quantity -= quantity
                                tx = Transaction(user_id=bot.id, ticker=ticker, quantity=quantity,
                                               price=price, type='sell', notes=f'Bot wave {wave}')
                                db.session.add(tx)
                            else:
                                decision_info['status'] = 'skipped_insufficient_shares'
                                results['decisions'].append(decision_info)
                                continue
                        
                        db.session.commit()
                        decision_info['status'] = 'executed'
                        results['trades_executed'] += 1
                        
                    except Exception as e:
                        db.session.rollback()
                        decision_info['status'] = f'error: {str(e)}'
                        results['errors'].append(str(e))
                    
                    results['decisions'].append(decision_info)
                    
            except Exception as e:
                results['errors'].append(f'Bot {bot.id}: {str(e)}')
                logger.error(f"Bot trade error for {bot.id}: {e}")
        
        return jsonify(results)
        
    except Exception as e:
        logger.error(f"Bot trade cron error: {e}")
        return jsonify({'error': str(e)}), 500


@mobile_api.route('/admin/dividend', methods=['POST'])
@require_admin_key
def admin_record_dividend():
    """
    Record a dividend payment for a user.
    
    POST body (JSON):
        user_id: int — user who received the dividend
        ticker: str — stock ticker
        amount_per_share: float — dividend per share
        ex_date: str — ex-dividend date (YYYY-MM-DD)
        pay_date: str (optional) — payment date (YYYY-MM-DD)
    
    The endpoint automatically calculates total_amount from shares held.
    Dividends add to cash_proceeds (increasing portfolio value) without
    increasing max_cash_deployed (they are return, not new capital).
    """
    from models import db, User, Stock, Dividend
    from cash_tracking import process_transaction
    
    data = request.get_json() or {}
    user_id = data.get('user_id')
    ticker = data.get('ticker', '').upper()
    amount_per_share = data.get('amount_per_share')
    ex_date_str = data.get('ex_date')
    pay_date_str = data.get('pay_date')
    
    if not all([user_id, ticker, amount_per_share, ex_date_str]):
        return jsonify({'error': 'user_id, ticker, amount_per_share, and ex_date required'}), 400
    
    try:
        from datetime import date as dt_date
        ex_date = datetime.strptime(ex_date_str, '%Y-%m-%d').date()
        pay_date = datetime.strptime(pay_date_str, '%Y-%m-%d').date() if pay_date_str else None
        
        user = User.query.get(user_id)
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        # Get shares held for this ticker
        stock = Stock.query.filter_by(user_id=user_id, ticker=ticker).first()
        if not stock or stock.quantity <= 0:
            return jsonify({'error': f'User {user_id} does not hold {ticker}'}), 400
        
        shares_held = stock.quantity
        total_amount = round(amount_per_share * shares_held, 2)
        
        # Check for duplicate
        existing = Dividend.query.filter_by(user_id=user_id, ticker=ticker, ex_date=ex_date).first()
        if existing:
            return jsonify({'error': 'Dividend already recorded', 'existing_id': existing.id}), 409
        
        # Record dividend in Dividend table
        dividend = Dividend(
            user_id=user_id,
            ticker=ticker,
            amount_per_share=amount_per_share,
            shares_held=shares_held,
            total_amount=total_amount,
            ex_date=ex_date,
            pay_date=pay_date
        )
        db.session.add(dividend)
        
        # Process as a dividend transaction (adds to cash_proceeds, not max_cash_deployed)
        result = process_transaction(
            db, user_id, ticker, shares_held, amount_per_share,
            'dividend', timestamp=datetime.combine(pay_date or ex_date, datetime.min.time())
        )
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'dividend_id': dividend.id,
            'ticker': ticker,
            'amount_per_share': amount_per_share,
            'shares_held': shares_held,
            'total_amount': total_amount,
            'ex_date': ex_date_str,
            'cash_proceeds_after': result['cash_proceeds'],
            'max_cash_deployed': result['max_cash_deployed']
        })
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Dividend recording error: {e}")
        return jsonify({'error': str(e)}), 500


@mobile_api.route('/admin/bot/email-trade', methods=['POST'])
@require_admin_key
def bot_email_trade():
    """
    Process a trade notification forwarded from Public.com email.
    Used for the Grok Portfolio and Wolff's Flagship Fund copy-trading bots.
    
    POST body (JSON):
        bot_username: str — username of the copy-trading bot
        trades: list of {action: 'buy'|'sell', ticker: str, quantity: float, price: float}
        source: str — 'grok_portfolio' or 'wolffs_flagship'
        notes: str (optional) — raw email text or description
    
    Or for simple single-trade format:
        bot_username: str
        action: 'buy' or 'sell'
        ticker: str
        quantity: float
        price: float (optional — will fetch current price if omitted)
        source: str
    """
    from models import db, User, Stock, Transaction
    from cash_tracking import process_transaction
    
    data = request.get_json() or {}
    bot_username = data.get('bot_username')
    source = data.get('source', 'public_email')
    notes = data.get('notes', '')
    
    if not bot_username:
        return jsonify({'error': 'bot_username required'}), 400
    
    try:
        # Auto-detect which bot this email is for by matching tickers
        if bot_username == 'auto':
            trades_list = data.get('trades', [])
            if not trades_list and data.get('ticker'):
                trades_list = [{'ticker': data.get('ticker', '')}]
            
            email_tickers = set(t.get('ticker', '').upper() for t in trades_list if t.get('ticker'))
            
            if not email_tickers:
                return jsonify({'error': 'No tickers found for auto-detection'}), 400
            
            # Find all copytrade bot users
            copytrade_bots = User.query.filter_by(role='agent').all()
            best_bot = None
            best_overlap = -1
            match_details = []
            
            for candidate in copytrade_bots:
                held_tickers = set(
                    s.ticker.upper() for s in Stock.query.filter_by(user_id=candidate.id).all()
                    if s.quantity > 0
                )
                overlap = len(email_tickers & held_tickers)
                match_details.append({
                    'username': candidate.username,
                    'user_id': candidate.id,
                    'held_tickers': len(held_tickers),
                    'overlap': overlap,
                    'matching_tickers': sorted(email_tickers & held_tickers)
                })
                if overlap > best_overlap:
                    best_overlap = overlap
                    best_bot = candidate
            
            if not best_bot or best_overlap == 0:
                logger.warning(f"Auto-detect: no bot matched tickers {email_tickers}. Details: {match_details}")
                return jsonify({
                    'error': 'auto_detect_failed',
                    'message': 'No bot holdings match the traded tickers',
                    'email_tickers': sorted(email_tickers),
                    'candidates': match_details
                }), 404
            
            bot = best_bot
            bot_username = bot.username
            source = f'auto_{source}' if not source.startswith('auto_') else source
            logger.info(f"Auto-detect: matched {email_tickers} to {bot_username} (overlap={best_overlap}). Details: {match_details}")
        else:
            # Find the bot user by explicit username
            bot = User.query.filter_by(username=bot_username, role='agent').first()
            if not bot:
                return jsonify({'error': f'Bot user "{bot_username}" not found'}), 404
        
        # Check if bot has a trade multiplier for obfuscation
        # (stored in extra_data['trade_multiplier'] by the scale-holdings endpoint)
        trade_multiplier = 1.0
        if bot.extra_data and isinstance(bot.extra_data, dict):
            trade_multiplier = float(bot.extra_data.get('trade_multiplier', 1.0))
        
        # Parse trades — support both single-trade and batch format
        trades = data.get('trades', [])
        if not trades and data.get('action'):
            trades = [{
                'action': data['action'],
                'ticker': data.get('ticker', '').upper(),
                'quantity': data.get('quantity', 1),
                'price': data.get('price')
            }]
        
        if not trades:
            return jsonify({'error': 'No trades specified'}), 400
        
        results = []
        for trade in trades:
            action = trade.get('action', '').lower()
            ticker = trade.get('ticker', '').upper()
            quantity = float(trade.get('quantity', 1))
            price = trade.get('price')
            
            # Scale quantity by bot's trade multiplier for obfuscation
            if trade_multiplier != 1.0:
                original_qty = quantity
                quantity = round(quantity * trade_multiplier, 6)
                logger.info(f"Scaled {ticker} qty: {original_qty} -> {quantity} (x{trade_multiplier})")
            
            if action not in ('buy', 'sell'):
                results.append({'ticker': ticker, 'error': f'Invalid action: {action}'})
                continue
            
            if not ticker:
                results.append({'error': 'ticker required'})
                continue
            
            # Fetch current price if not provided
            if not price:
                try:
                    from portfolio_performance import PortfolioPerformanceCalculator
                    calc = PortfolioPerformanceCalculator()
                    price_data = calc.get_stock_data(ticker)
                    if price_data and price_data.get('price'):
                        price = price_data['price']
                    else:
                        results.append({'ticker': ticker, 'error': 'Could not fetch price'})
                        continue
                except Exception as e:
                    results.append({'ticker': ticker, 'error': f'Price fetch failed: {e}'})
                    continue
            
            price = float(price)
            
            try:
                # Process transaction through cash tracking
                tx_result = process_transaction(
                    db, bot.id, ticker, quantity, price, action,
                    timestamp=datetime.utcnow()
                )
                
                # Update Stock table
                stock = Stock.query.filter_by(user_id=bot.id, ticker=ticker).first()
                if action == 'buy':
                    if stock:
                        # Weighted average purchase price
                        total_cost = (stock.quantity * stock.purchase_price) + (quantity * price)
                        stock.quantity += quantity
                        stock.purchase_price = total_cost / stock.quantity if stock.quantity > 0 else price
                    else:
                        stock = Stock(user_id=bot.id, ticker=ticker, quantity=quantity, purchase_price=price)
                        db.session.add(stock)
                elif action == 'sell':
                    if stock and stock.quantity >= quantity:
                        stock.quantity -= quantity
                    else:
                        results.append({'ticker': ticker, 'error': 'Insufficient shares'})
                        continue
                
                results.append({
                    'ticker': ticker,
                    'action': action,
                    'quantity': quantity,
                    'price': price,
                    'total_value': round(quantity * price, 2),
                    'status': 'executed',
                    'source': source
                })
                
            except Exception as e:
                db.session.rollback()
                results.append({'ticker': ticker, 'error': str(e)})
        
        db.session.commit()
        
        executed = [r for r in results if r.get('status') == 'executed']
        
        return jsonify({
            'success': True,
            'bot_username': bot_username,
            'bot_id': bot.id,
            'source': source,
            'trades_submitted': len(trades),
            'trades_executed': len(executed),
            'results': results
        })
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Bot email trade error: {e}")
        return jsonify({'error': str(e)}), 500


@mobile_api.route('/admin/bot/sp500-backfill', methods=['POST'])
@require_admin_key
def bot_sp500_backfill():
    """
    Backfill S&P 500 historical data from AlphaVantage SPY daily prices.
    Uses the full outputsize to get 20+ years of data and stores SPY*10 as SPY_SP500.
    Query param: years (default 5)
    """
    from models import db, MarketData
    from datetime import timedelta
    import os
    
    years = int(request.args.get('years', 5))
    av_key = os.environ.get('ALPHA_VANTAGE_API_KEY')
    if not av_key:
        return jsonify({'error': 'ALPHA_VANTAGE_API_KEY not configured'}), 500
    
    try:
        import requests as req
        url = 'https://www.alphavantage.co/query'
        params = {
            'function': 'TIME_SERIES_DAILY',
            'symbol': 'SPY',
            'outputsize': 'full',
            'apikey': av_key
        }
        
        resp = req.get(url, params=params, timeout=30)
        data = resp.json()
        
        if 'Error Message' in data:
            return jsonify({'error': data['Error Message']}), 500
        if 'Time Series (Daily)' not in data:
            return jsonify({'error': 'Invalid response', 'keys': list(data.keys())}), 500
        
        time_series = data['Time Series (Daily)']
        today = datetime.utcnow().date()
        start_date = today - timedelta(days=years * 365)
        
        inserted = 0
        updated = 0
        skipped = 0
        errors = []
        
        for date_str, daily in time_series.items():
            try:
                data_date = datetime.strptime(date_str, '%Y-%m-%d').date()
                if data_date < start_date:
                    continue
                
                spy_close = float(daily['4. close'])
                sp500_value = round(spy_close * 10, 2)
                
                existing = MarketData.query.filter_by(
                    ticker='SPY_SP500', date=data_date
                ).first()
                
                if existing:
                    if abs(existing.close_price - sp500_value) > 0.01:
                        existing.close_price = sp500_value
                        updated += 1
                    else:
                        skipped += 1
                else:
                    db.session.add(MarketData(
                        ticker='SPY_SP500', date=data_date, close_price=sp500_value
                    ))
                    inserted += 1
            except Exception as e:
                errors.append(f"{date_str}: {str(e)}")
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'total_api_records': len(time_series),
            'inserted': inserted,
            'updated': updated,
            'skipped': skipped,
            'errors': errors[:10],
            'years_requested': years
        })
    except Exception as e:
        db.session.rollback()
        logger.error(f"SP500 backfill error: {e}")
        return jsonify({'error': str(e)}), 500


@mobile_api.route('/admin/bot/sp500-check', methods=['GET'])
@require_admin_key
def bot_sp500_check():
    """Check S&P 500 data coverage in the database for diagnostics."""
    from models import MarketData
    from datetime import timedelta
    
    try:
        today = datetime.utcnow().date()
        
        # Count total records
        total = MarketData.query.filter(MarketData.ticker == 'SPY_SP500').count()
        
        # Get date range
        earliest = MarketData.query.filter(
            MarketData.ticker == 'SPY_SP500'
        ).order_by(MarketData.date.asc()).first()
        
        latest = MarketData.query.filter(
            MarketData.ticker == 'SPY_SP500'
        ).order_by(MarketData.date.desc()).first()
        
        # Check last 30 days
        thirty_ago = today - timedelta(days=30)
        recent = MarketData.query.filter(
            MarketData.ticker == 'SPY_SP500',
            MarketData.date >= thirty_ago
        ).order_by(MarketData.date.desc()).all()
        
        recent_dates = [{'date': r.date.isoformat(), 'price': round(r.close_price, 2)} for r in recent]
        
        # Check key periods
        periods = {'1M': 30, '3M': 90, 'YTD': (today - today.replace(month=1, day=1)).days, '1Y': 365, '5Y': 1825}
        coverage = {}
        for label, days in periods.items():
            start = today - timedelta(days=days)
            count = MarketData.query.filter(
                MarketData.ticker == 'SPY_SP500',
                MarketData.date >= start,
                MarketData.date <= today
            ).count()
            coverage[label] = count
        
        return jsonify({
            'total_records': total,
            'earliest_date': earliest.date.isoformat() if earliest else None,
            'earliest_price': round(earliest.close_price, 2) if earliest else None,
            'latest_date': latest.date.isoformat() if latest else None,
            'latest_price': round(latest.close_price, 2) if latest else None,
            'period_coverage': coverage,
            'last_30_days': recent_dates
        })
    except Exception as e:
        logger.error(f"SP500 check error: {e}")
        return jsonify({'error': str(e)}), 500


@mobile_api.route('/admin/bot/holdings', methods=['GET'])
@require_admin_key
def bot_holdings():
    """
    Get a user's current stock holdings.
    Query param: user_id
    Returns list of {ticker, quantity, purchase_price}
    """
    from models import Stock
    
    user_id = request.args.get('user_id')
    if not user_id:
        return jsonify({'error': 'user_id_required'}), 400
    
    try:
        stocks = Stock.query.filter_by(user_id=int(user_id)).all()
        holdings = [{
            'ticker': s.ticker,
            'quantity': s.quantity,
            'purchase_price': round(float(s.purchase_price), 2) if s.purchase_price else 0,
        } for s in stocks if s.quantity > 0]
        return jsonify({'holdings': holdings, 'count': len(holdings)})
    except Exception as e:
        logger.error(f"Bot holdings error: {e}")
        return jsonify({'error': 'holdings_failed'}), 500


@mobile_api.route('/admin/bot/gift-subscribers', methods=['POST'])
@require_admin_key
def bot_gift_subscribers():
    """
    Gift subscriber count to a user (creates fake subscriptions).
    Also updates UserPortfolioStats.subscriber_count.
    
    Request body:
    {
        "user_id": 123,
        "count": 5
    }
    """
    from models import db, User, MobileSubscription, UserPortfolioStats
    
    data = request.get_json()
    if not data:
        return jsonify({'error': 'missing_request_body'}), 400
    
    user_id = data.get('user_id')
    count = data.get('count', 1)
    
    if not user_id or count <= 0:
        return jsonify({'error': 'user_id_and_positive_count_required'}), 400
    
    try:
        user = User.query.get(user_id)
        if not user:
            return jsonify({'error': 'user_not_found'}), 404
        
        from datetime import timedelta
        created = 0
        for i in range(count):
            sub = MobileSubscription(
                subscriber_id=user_id,  # Self-referential placeholder
                subscribed_to_id=user_id,
                platform='admin_gift',
                status='active',
                expires_at=datetime.utcnow() + timedelta(days=365 * 10),
                push_notifications_enabled=False
            )
            db.session.add(sub)
            created += 1
        
        # Update UserPortfolioStats subscriber_count
        stats = UserPortfolioStats.query.filter_by(user_id=user_id).first()
        if stats:
            stats.subscriber_count = (stats.subscriber_count or 0) + count
        else:
            stats = UserPortfolioStats(
                user_id=user_id,
                subscriber_count=count
            )
            db.session.add(stats)
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'gifted': created,
            'new_subscriber_count': stats.subscriber_count
        })
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Gift subscribers error: {e}")
        return jsonify({'error': 'gift_failed'}), 500


@mobile_api.route('/admin/bot/deactivate', methods=['POST'])
@require_admin_key
def bot_deactivate():
    """
    Deactivate a bot user (hide from leaderboards, stop trading).
    
    Request body: {"user_id": 123}
    """
    from models import db, User
    
    data = request.get_json()
    if not data:
        return jsonify({'error': 'missing_request_body'}), 400
    
    user_id = data.get('user_id')
    if not user_id:
        return jsonify({'error': 'user_id_required'}), 400
    
    try:
        user = User.query.get(user_id)
        if not user:
            return jsonify({'error': 'user_not_found'}), 404
        
        extra = user.extra_data or {}
        extra['bot_active'] = False
        extra['deactivated_at'] = datetime.utcnow().isoformat()
        user.extra_data = extra
        user.leaderboard_eligible = False
        
        db.session.commit()
        return jsonify({'success': True, 'user_id': user_id, 'bot_active': False})
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Bot deactivate error: {e}")
        return jsonify({'error': 'deactivate_failed'}), 500


@mobile_api.route('/admin/bot/reactivate', methods=['POST'])
@require_admin_key
def bot_reactivate():
    """
    Reactivate a previously deactivated bot user.
    
    Request body: {"user_id": 123}
    """
    from models import db, User
    
    data = request.get_json()
    if not data:
        return jsonify({'error': 'missing_request_body'}), 400
    
    user_id = data.get('user_id')
    if not user_id:
        return jsonify({'error': 'user_id_required'}), 400
    
    try:
        user = User.query.get(user_id)
        if not user:
            return jsonify({'error': 'user_not_found'}), 404
        
        extra = user.extra_data or {}
        extra['bot_active'] = True
        extra.pop('deactivated_at', None)
        user.extra_data = extra
        user.leaderboard_eligible = True
        
        db.session.commit()
        return jsonify({'success': True, 'user_id': user_id, 'bot_active': True})
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Bot reactivate error: {e}")
        return jsonify({'error': 'reactivate_failed'}), 500


@mobile_api.route('/admin/bot/update-config', methods=['POST'])
@require_admin_key
def bot_update_config():
    """
    Update bot configuration (industry, trading style, etc.)
    
    Request body:
    {
        "user_id": 123,
        "industry": "Technology",
        "trading_style": "active",
        "trade_frequency": "daily",
        "trade_time_range": {"start_hour": 9, "end_hour": 16},
        "max_stocks": 15
    }
    """
    from models import db, User
    
    data = request.get_json()
    if not data:
        return jsonify({'error': 'missing_request_body'}), 400
    
    user_id = data.get('user_id')
    if not user_id:
        return jsonify({'error': 'user_id_required'}), 400
    
    try:
        user = User.query.get(user_id)
        if not user:
            return jsonify({'error': 'user_not_found'}), 404
        
        extra = user.extra_data or {}
        
        # Update configurable fields
        for key in ['industry', 'trading_style', 'trade_frequency', 
                     'trade_time_range', 'max_stocks', 'notes']:
            if key in data:
                extra[key] = data[key]
        
        user.extra_data = extra
        db.session.commit()
        
        return jsonify({'success': True, 'extra_data': extra})
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Bot update config error: {e}")
        return jsonify({'error': 'update_failed'}), 500


@mobile_api.route('/admin/bot/remove-subscribers', methods=['POST'])
@require_admin_key
def bot_remove_subscribers():
    """
    Remove gifted subscribers from a user.
    
    Request body:
    {
        "user_id": 123,
        "count": 3
    }
    """
    from models import db, MobileSubscription, UserPortfolioStats
    
    data = request.get_json()
    if not data:
        return jsonify({'error': 'missing_request_body'}), 400
    
    user_id = data.get('user_id')
    count = data.get('count', 1)
    
    if not user_id or count <= 0:
        return jsonify({'error': 'user_id_and_positive_count_required'}), 400
    
    try:
        # Find and remove gifted subscriptions
        gifted = MobileSubscription.query.filter_by(
            subscribed_to_id=user_id,
            platform='admin_gift',
            status='active'
        ).limit(count).all()
        
        removed = 0
        for sub in gifted:
            sub.status = 'canceled'
            removed += 1
        
        # Update stats
        stats = UserPortfolioStats.query.filter_by(user_id=user_id).first()
        if stats:
            stats.subscriber_count = max(0, (stats.subscriber_count or 0) - removed)
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'removed': removed,
            'new_subscriber_count': stats.subscriber_count if stats else 0
        })
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Remove subscribers error: {e}")
        return jsonify({'error': 'remove_failed'}), 500
