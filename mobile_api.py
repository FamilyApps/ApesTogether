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
from datetime import datetime, date, timedelta
from collections import defaultdict
import logging
import jwt
import os
import requests
import secrets
import string
import time as _time

logger = logging.getLogger(__name__)

mobile_api = Blueprint('mobile_api', __name__, url_prefix='/api/mobile')


# ---------------------------------------------------------------------------
# DB session hygiene for serverless (Vercel)
# NullPool gives us a fresh connection per DB call, but if that call fails
# (SSL drop, PgBouncer kill, etc.) the SQLAlchemy session is left in an
# invalid state. These handlers ensure every request starts and ends clean.
# ---------------------------------------------------------------------------

@mobile_api.before_request
def _clean_db_session():
    """Remove any leftover session state from a previous invocation."""
    try:
        from models import db
        db.session.remove()
    except Exception:
        pass


@mobile_api.teardown_request
def _teardown_db_session(exc=None):
    """Rollback on error, then remove session so connections are returned."""
    try:
        from models import db
        if exc:
            db.session.rollback()
        db.session.remove()
    except Exception:
        pass


def _is_transient_db_error(e):
    """Return True if the exception looks like a recoverable DB/SSL error."""
    err_str = str(e).lower()
    return (
        'ssl connection has been closed' in err_str or
        'connection has been closed' in err_str or
        'invalid transaction' in err_str or
        'could not connect' in err_str or
        'connection refused' in err_str or
        'server closed the connection' in err_str or
        'closed the connection unexpectedly' in err_str or
        'connection timed out' in err_str or
        'queuepool limit' in err_str
    )


def _reset_db_session():
    """Roll back, remove session, and dispose engine for a completely fresh start."""
    from models import db
    try:
        db.session.rollback()
    except Exception:
        pass
    try:
        db.session.remove()
    except Exception:
        pass
    try:
        db.engine.dispose()
    except Exception:
        pass


def db_retry(fn, max_retries=2):
    """Execute fn(), retrying on transient DB/SSL errors with a fresh session."""
    last_error = None
    for attempt in range(max_retries + 1):
        try:
            return fn()
        except Exception as e:
            last_error = e
            if _is_transient_db_error(e) and attempt < max_retries:
                logger.warning(f"DB transient error (attempt {attempt+1}/{max_retries+1}): {e}")
                _reset_db_session()
                continue
            raise last_error


def with_db_retry(f):
    """Decorator: wrap an entire Flask endpoint in db_retry.

    Usage::

        @mobile_api.route('/admin/bot/dashboard')
        @require_admin_2fa
        @with_db_retry
        def bot_dashboard():
            ...
    """
    @wraps(f)
    def wrapper(*args, **kwargs):
        last_error = None
        for attempt in range(3):  # up to 3 attempts (initial + 2 retries)
            try:
                return f(*args, **kwargs)
            except Exception as e:
                last_error = e
                if _is_transient_db_error(e) and attempt < 2:
                    logger.warning(f"DB retry on {f.__name__} (attempt {attempt+1}/3): {e}")
                    _reset_db_session()
                    continue
                raise
        raise last_error
    return wrapper


# In-memory sliding window rate limiter (serverless-safe, resets on cold start)
_rate_limit_store = defaultdict(list)


def rate_limit(max_requests, per_seconds=60):
    """Rate limit decorator using in-memory sliding window.
    
    Args:
        max_requests: Maximum number of requests allowed in the window
        per_seconds: Window size in seconds (default 60 = per minute)
    
    Returns 429 with Retry-After header when limit exceeded.
    """
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            # Key by IP + endpoint (or admin key for admin endpoints)
            admin_key = request.headers.get('X-Admin-Key')
            if admin_key:
                client_id = f"admin:{admin_key[:8]}"
            elif hasattr(g, 'user_id') and g.user_id:
                client_id = f"user:{g.user_id}"
            else:
                client_id = f"ip:{request.remote_addr}"
            
            key = f"{client_id}:{f.__name__}"
            now = _time.time()
            window_start = now - per_seconds
            
            # Clean old entries and count recent ones
            _rate_limit_store[key] = [t for t in _rate_limit_store[key] if t > window_start]
            
            if len(_rate_limit_store[key]) >= max_requests:
                retry_after = int(per_seconds - (now - _rate_limit_store[key][0])) + 1
                return jsonify({
                    'error': 'rate_limit_exceeded',
                    'message': f'Too many requests. Limit: {max_requests} per {per_seconds}s.',
                    'retry_after': retry_after
                }), 429, {'Retry-After': str(retry_after)}
            
            _rate_limit_store[key].append(now)
            return f(*args, **kwargs)
        return wrapper
    return decorator


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
            secret = os.environ.get('JWT_SECRET') or os.environ.get('SECRET_KEY')
            if not secret:
                return jsonify({'error': 'server_misconfigured'}), 500
            
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
    
    secret = os.environ.get('JWT_SECRET') or os.environ.get('SECRET_KEY')
    if not secret:
        raise RuntimeError('JWT_SECRET or SECRET_KEY must be set')
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


def _utc_iso(dt):
    """Serialize a naive UTC datetime as ISO-8601 with explicit 'Z' suffix.

    Why this exists
    ---------------
    All our DB datetimes are stored as naive UTC (set via datetime.utcnow()).
    Calling .isoformat() on a naive datetime omits any timezone marker,
    producing strings like '2026-05-20T16:00:50.123456'. The browser's
    `new Date()` then parses datetime-only strings as LOCAL time per the
    modern ECMAScript spec — so a 16:00 UTC timestamp displays as
    '4:00 PM' regardless of the user's actual zone, instead of being
    converted to the local zone (e.g., 12:00 PM ET).

    Appending 'Z' makes the parse unambiguous (= UTC), allowing
    toLocaleString()/toLocaleTimeString() in the admin panel to do the
    right thing and convert to the viewer's local zone.

    Use this for any endpoint surfaced by templates/admin_panel.html or
    the mobile clients (which expect ISO-with-Z). Returns None if dt is
    None so call-sites can keep their `if x else None` patterns concise.
    """
    if dt is None:
        return None
    return dt.isoformat() + 'Z'


# ── Phase D: portfolio resizer helpers ───────────────────────────────────────
# These helpers underpin the `scale_factor` math used by the subscribed-
# portfolio view. The model columns live on MobileSubscription; the user
# preference lives in User.extra_data['prefer_fractional'] (JSON-backed,
# no schema migration). Keeping the helpers small + pure makes them easy
# to unit-test if we add tests later.

def _get_prefer_fractional(user):
    """Read User.extra_data['prefer_fractional']. Default True.

    True  → scaled views show up to 5 decimals (rounded, trailing zeros
            stripped client-side by the iOS/Android share formatters)
    False → scaled views floor to whole shares + "below 1 share" footnote
    """
    if not user:
        return True
    extra = user.extra_data or {}
    val = extra.get('prefer_fractional')
    if val is None:
        return True
    return bool(val)


def _scale_qty(qty, scale, prefer_fractional):
    """Apply scale_factor to a share quantity for display.

    Args:
        qty: raw share count from the creator's portfolio (float)
        scale: subscription.scale_factor (float, >0; caller must validate)
        prefer_fractional: bool from _get_prefer_fractional(subscriber)

    Returns:
        float when prefer_fractional is True (max 5 decimals, e.g. 0.30357)
        float with integer value when prefer_fractional is False (floor)
    """
    if not scale or scale <= 0 or qty <= 0:
        return 0.0
    scaled = qty * scale
    if prefer_fractional:
        return round(scaled, 5)
    # Floor to whole shares — never round up (we don't want the user to
    # think they hold more than the scale-math actually grants them).
    return float(int(scaled))


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
    product_id = data.get('product_id')  # client hint; used for pricing/accounting
    
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
                purchase_token=purchase_token,
                product_id=product_id
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
                    'display_name': owner.public_name,
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
                    'username': subscriber.username,
                    'display_name': subscriber.public_name
                } if subscriber else None,
                'status': sub.status,
                'created_at': sub.created_at.isoformat()
            })
        
        active_real_subs = len([s for s in received_subs if s.status == 'active'])
        gifted_subs_count = 0
        try:
            from models import AdminSubscription
            admin_sub = AdminSubscription.query.filter_by(portfolio_user_id=g.user_id).first()
            if admin_sub:
                gifted_subs_count = admin_sub.bonus_subscriber_count or 0
        except Exception:
            pass
        
        return jsonify({
            'subscriptions_made': subscriptions_made,
            'subscribers': subscribers,
            'subscriber_count': active_real_subs + gifted_subs_count
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
@rate_limit(60)
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
        
        # Check if user is subscribed or is the owner. Capture the
        # subscription object (not just the bool) so we can read the
        # Phase D scale_factor / target_dollars further down when
        # rendering holdings.
        is_owner = owner.id == g.user_id
        is_subscribed = False
        subscription = None

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
                'display_name': owner.public_name,
                'portfolio_slug': owner.portfolio_slug
            },
            'is_owner': is_owner,
            'is_subscribed': is_subscribed,
            # Phase D: expose subscription_id so mobile clients can call
            # POST/DELETE /subscriptions/<id>/scale without first making
            # a round-trip to /subscriptions to look it up.
            'subscription_id': subscription.id if subscription else None,
            'subscription_price': 9.00
        }
        
        # Get subscriber count (real + gifted)
        subscriber_count = MobileSubscription.query.filter_by(
            subscribed_to_id=owner.id,
            status='active'
        ).count()
        try:
            from models import AdminSubscription
            admin_sub = AdminSubscription.query.filter_by(portfolio_user_id=owner.id).first()
            if admin_sub:
                subscriber_count += admin_sub.bonus_subscriber_count or 0
        except Exception:
            pass
        response['subscriber_count'] = subscriber_count
        
        # Leaderboard badges — check if user ranks in top 20 for any period
        leaderboard_badges = []
        try:
            from models import LeaderboardCache
            import json as json_lb
            
            badge_periods = {'1D': '1D', '5D': '1W', '1M': '1M', '3M': '3M', 'YTD': 'YTD', '1Y': '1Y'}
            for cache_period, display_period in badge_periods.items():
                for suffix in ['_auth', '_anon', '']:
                    cache_key = f"{cache_period}_all{suffix}"
                    cache_entry = LeaderboardCache.query.filter_by(period=cache_key).first()
                    if cache_entry:
                        entries = json_lb.loads(cache_entry.leaderboard_data)
                        # Sort and find user's rank
                        entries.sort(key=lambda x: x.get('performance_percent', 0), reverse=True)
                        for idx, e in enumerate(entries[:20]):
                            if e.get('user_id') == owner.id:
                                leaderboard_badges.append({
                                    'period': display_period,
                                    'rank': idx + 1,
                                    'type': 'overall'
                                })
                        break  # Found cache for this period, no need to try other suffixes
            
            # Also check industry-specific ranking from the user's top sector
            try:
                stats = UserPortfolioStats.query.filter_by(user_id=owner.id).first()
                if stats and stats.industry_mix and isinstance(stats.industry_mix, dict):
                    top_sector = max(stats.industry_mix, key=stats.industry_mix.get) if stats.industry_mix else None
                    if top_sector:
                        # Check if user would be top 3 in their dominant sector
                        # Use the YTD overall leaderboard and filter by sector
                        for suffix in ['_auth', '_anon', '']:
                            ytd_key = f"YTD_all{suffix}"
                            ytd_cache = LeaderboardCache.query.filter_by(period=ytd_key).first()
                            if ytd_cache:
                                all_entries = json_lb.loads(ytd_cache.leaderboard_data)
                                all_entries.sort(key=lambda x: x.get('performance_percent', 0), reverse=True)
                                # Filter to users who have this sector in their mix
                                sector_rank = 0
                                for e in all_entries:
                                    uid = e.get('user_id')
                                    u_stats = UserPortfolioStats.query.filter_by(user_id=uid).first()
                                    if u_stats and u_stats.industry_mix and top_sector in u_stats.industry_mix:
                                        sector_rank += 1
                                        if uid == owner.id:
                                            if sector_rank <= 20:
                                                leaderboard_badges.append({
                                                    'period': 'YTD',
                                                    'rank': sector_rank,
                                                    'type': 'sector',
                                                    'sector': top_sector
                                                })
                                            break
                                break
            except Exception:
                pass
        except Exception as e:
            logger.warning(f"Leaderboard badge lookup failed: {e}")
        
        response['leaderboard_badges'] = leaderboard_badges
        
        # Portfolio stats (always visible — public info for the profile)
        # Industry mix
        industry_mix = {}
        large_cap_pct = 0.0
        try:
            stats = UserPortfolioStats.query.filter_by(user_id=owner.id).first()
            if stats:
                if stats.industry_mix and isinstance(stats.industry_mix, dict):
                    industry_mix = stats.industry_mix
                large_cap_pct = float(stats.large_cap_percent) if stats.large_cap_percent else 0.0
        except Exception:
            pass
        if not industry_mix:
            try:
                from leaderboard_utils import calculate_industry_mix, calculate_portfolio_cap_percentages
                industry_mix = calculate_industry_mix(owner.id) or {}
                _, large_cap_pct = calculate_portfolio_cap_percentages(owner.id)
                large_cap_pct = float(large_cap_pct) if large_cap_pct else 0.0
            except Exception:
                pass
        response['industry_mix'] = industry_mix
        response['large_cap_pct'] = round(large_cap_pct, 1)
        
        # Account age
        account_age_days = 0
        if owner.created_at:
            account_age_days = (datetime.utcnow() - owner.created_at).days
        response['account_age_days'] = account_age_days
        
        # Trades per week (last 30 days). Exclude dividends — they are income
        # events, not trades. Seeds ('initial') ARE counted: a seed is the bot
        # buying its entry position.
        thirty_days_ago = datetime.utcnow() - timedelta(days=30)
        recent_trade_count = Transaction.query.filter(
            Transaction.user_id == owner.id,
            Transaction.timestamp >= thirty_days_ago,
            Transaction.transaction_type != 'dividend',
        ).count()
        response['avg_trades_per_week'] = round(recent_trade_count / 4.3, 1)
        
        # Load all stocks once (reuse for value calc, holdings, and count)
        all_stocks = Stock.query.filter_by(user_id=owner.id).all()
        response['num_stocks'] = len(all_stocks)
        
        # Single bulk API call for ALL stock prices (premium tier: 150 calls/min)
        batch_prices = {}
        try:
            from portfolio_performance import PortfolioPerformanceCalculator
            calc = PortfolioPerformanceCalculator()
            tickers = [s.ticker for s in all_stocks if s.ticker and s.quantity > 0]
            if tickers:
                batch_prices = calc.get_batch_stock_data(tickers)
        except Exception as e:
            logger.warning(f"Bulk price fetch failed: {e}")
        
        # Display-layer price fallback: when the live bulk quote
        # (REALTIME_BULK_QUOTES) doesn't return a ticker, fall back to the most
        # recent real daily close from market_data instead of purchase_price --
        # otherwise current_price == purchase_price and Holdings render ~+0%
        # gains (the bug). get_batch_stock_data itself is intentionally left
        # unchanged so trade-execution paths never transact on a stale close.
        latest_close = {}
        try:
            from models import MarketData
            held_upper = [s.ticker.upper() for s in all_stocks
                          if s.ticker and s.quantity and s.quantity > 0]
            if held_upper:
                for tk, close in (
                    MarketData.query
                    .with_entities(MarketData.ticker, MarketData.close_price)
                    .filter(MarketData.ticker.in_(held_upper),
                            MarketData.timestamp.is_(None))
                    .order_by(MarketData.ticker, MarketData.date.desc())
                    .all()
                ):
                    if tk and close and close > 0:
                        u = tk.upper()
                        if u not in latest_close:
                            latest_close[u] = float(close)
        except Exception as e:
            logger.warning(f"Holdings latest-close fallback lookup failed: {e}")

        def _resolve_current_price(stock):
            u = stock.ticker.upper()
            live = batch_prices.get(u)
            if live and live > 0:
                return float(live)
            close = latest_close.get(u)
            if close and close > 0:
                return float(close)
            return float(stock.purchase_price or 0)

        # Portfolio value (live bulk quote -> latest close -> purchase price)
        portfolio_value = 0.0
        for stock in all_stocks:
            if stock.quantity > 0:
                portfolio_value += _resolve_current_price(stock) * stock.quantity
        cash_balance = float(getattr(owner, 'cash_proceeds', 0.0) or 0.0)
        portfolio_value += cash_balance
        response['portfolio_value'] = round(portfolio_value, 2)
        # Expose cash separately so the iOS Holdings list can render a
        # dedicated cash line (Phase B). Only included when there's
        # meaningful cash on hand to avoid clutter for fully-invested users.
        if cash_balance > 0.005:
            response['cash_balance'] = round(cash_balance, 2)

        # ── Phase D: portfolio resizer ────────────────────────────────────
        # If the viewer is a subscriber AND has set a scale on this
        # subscription, scale the displayed quantities + portfolio_value.
        # The owner viewing their own portfolio NEVER sees scaling.
        scale = None
        prefer_fractional = True
        if is_subscribed and subscription is not None:
            sf = getattr(subscription, 'scale_factor', None)
            if sf and sf > 0:
                scale = float(sf)
                # The subscriber's preference (not the owner's) controls
                # how scaled fractions render.
                viewer = User.query.get(g.user_id)
                prefer_fractional = _get_prefer_fractional(viewer)

                # Scale portfolio_value + cash_balance for display.
                # The dollar amount the subscriber sees should match the
                # target_dollars they set, modulo subsequent market drift.
                scaled_value = round(portfolio_value * scale, 2)
                response['portfolio_value'] = scaled_value
                response['scale'] = {
                    'scale_factor': round(scale, 6),
                    'target_dollars': round(float(subscription.target_dollars or 0), 2),
                    'scale_set_at': _utc_iso(getattr(subscription, 'scale_set_at', None)),
                    'unscaled_portfolio_value': round(portfolio_value, 2),
                }
                if 'cash_balance' in response:
                    response['cash_balance'] = round(cash_balance * scale, 2)
        
        # If subscribed or owner, show full portfolio.
        # ── Filter out zombie 0-share Stock rows ───────────────────────────
        # Several bot trade paths (mobile_api.py:3955/4691/4839/4988) do
        # `stock.quantity -= qty` on sells without deleting the row when it
        # hits zero, so a user can accumulate Stock rows like PANW/PSN/BWXT
        # with quantity=0 that still showed up in the holdings list. The
        # render here now matches the price-fetch filter at line 706, which
        # already skipped 0-quantity rows. Use `/admin/cleanup-zero-share-stocks`
        # to garbage-collect existing zombies.
        if is_owner or is_subscribed:
            holdings_list = []
            below_one_share_count = 0  # tracks Phase D "below 1 share" footer
            for stock in all_stocks:
                if not (stock.quantity and stock.quantity > 0):
                    continue
                qty = stock.quantity
                if scale is not None:
                    qty = _scale_qty(stock.quantity, scale, prefer_fractional)
                    # In floor mode (prefer_fractional=False), drop holdings
                    # that round to 0 shares but keep a count for the UI
                    # to surface "N positions below 1 share at this scale".
                    if qty <= 0:
                        below_one_share_count += 1
                        continue
                holdings_list.append({
                    'ticker': stock.ticker,
                    'quantity': qty,
                    'purchase_price': stock.purchase_price or 0,
                    'current_price': round(_resolve_current_price(stock), 2),
                    'purchase_date': stock.purchase_date.isoformat() if stock.purchase_date else None
                })
            response['holdings'] = holdings_list
            if scale is not None and below_one_share_count > 0:
                # iOS/Android render this as "+N positions below 1 share at
                # this scale — toggle 'Show fractional' in settings to see".
                response['below_one_share_count'] = below_one_share_count
            
            # Get recent transactions. Quantities are intentionally NOT
            # scaled in the recent_trades feed — the feed is a historical
            # log of the creator's actual trades, and scaling individual
            # historical share counts would be misleading (they don't
            # add up to the displayed scaled holdings).
            recent_trades = Transaction.query.filter_by(
                user_id=owner.id
            ).order_by(Transaction.timestamp.desc()).limit(20).all()
            
            executed_entries = [
                {
                    'ticker': trade.ticker,
                    'quantity': trade.quantity,
                    'price': trade.price,
                    'type': trade.transaction_type,
                    'status': 'executed',
                    # Use _utc_iso (Z-suffixed, no microseconds) so iOS
                    # ISO8601DateFormatter parses cleanly. Python's raw
                    # isoformat() produces '2026-05-14T13:43:27.989841'
                    # which both Swift and JS reject as a UTC datetime.
                    'timestamp': _utc_iso(trade.timestamp)
                }
                for trade in recent_trades
            ]
            
            # Pending (after-hours) trades the OWNER has queued for the next
            # market open. Shown only to the owner — we don't broadcast a
            # creator's unsettled intentions to subscribers (they get notified
            # when the trade actually executes at open). `price` is null until
            # the open price is established by the market-open cron.
            pending_entries = []
            if is_owner:
                from models import QueuedEmailTrade
                pending = QueuedEmailTrade.query.filter_by(
                    user_id=owner.id, status='queued'
                ).order_by(QueuedEmailTrade.queued_at.desc()).all()
                pending_entries = [
                    {
                        'pending_id': p.id,
                        'ticker': p.ticker,
                        'quantity': p.quantity,
                        'price': None,
                        'type': p.action,
                        'status': 'pending',
                        'timestamp': _utc_iso(p.queued_at)
                    }
                    for p in pending
                ]
            
            response['recent_trades'] = pending_entries + executed_entries
        else:
            # Limited preview for non-subscribers
            response['holdings'] = None  # Blurred in app
            response['preview_message'] = 'Subscribe to view full portfolio holdings'
        
        return jsonify(response)
        
    except Exception as e:
        logger.error(f"Get portfolio error: {e}")
        return jsonify({'error': 'failed_to_get_portfolio'}), 500


def _add_stocks_as_buys(stocks_list):
    """Handle `POST /portfolio/stocks` with intent='buy' — i.e. the in-app
    "Buy" sheet, as opposed to onboarding's "declare existing holdings".

    - Market OPEN:  fetch live prices, execute real buys (Stock + Transaction +
                    cash tracking via process_transaction).
    - Market CLOSED: queue each row as a PENDING QueuedEmailTrade('buy'); the
                     market-open cron settles them at the open price.
    """
    from models import db, Stock, QueuedEmailTrade, User
    from cash_tracking import process_transaction
    from timezone_utils import is_market_hours

    # Normalize + validate
    items = []
    errors = []
    for item in stocks_list:
        ticker = (item.get('ticker') or '').strip().upper()
        try:
            quantity = float(item.get('quantity'))
        except (ValueError, TypeError):
            quantity = 0
        if not ticker or len(ticker) > 10 or quantity <= 0:
            errors.append("Missing or invalid ticker/quantity")
            continue
        items.append((ticker, quantity))

    if not items:
        return jsonify({'error': 'no_valid_stocks', 'errors': errors or None}), 400

    trader = User.query.get(g.user_id)

    # ── Market closed → queue all as PENDING buys ───────────────────────────
    if not is_market_hours():
        for ticker, quantity in items:
            db.session.add(QueuedEmailTrade(
                user_id=g.user_id,
                user_email=(getattr(trader, 'email', None) or ''),
                ticker=ticker,
                action='buy',
                quantity=quantity,
                status='queued',
            ))
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error queuing after-hours buys: {e}")
            return jsonify({'error': 'failed_to_queue'}), 500
        logger.info(f"Queued {len(items)} after-hours app buys for user={g.user_id}")
        return jsonify({
            'success': True,
            'pending': True,
            'queued_count': len(items),
            'added_count': 0,
            'message': 'Market closed — your purchase is queued and will execute at the next market open.',
            'errors': errors or None,
        })

    # ── Market open → fetch live prices and execute real buys ───────────────
    tickers = list({t for t, _ in items})
    try:
        from portfolio_performance import PortfolioPerformanceCalculator
        prices = PortfolioPerformanceCalculator().get_batch_stock_data(tickers)
    except Exception as e:
        logger.error(f"Live price fetch failed for buy: {e}")
        prices = {}

    added_count = 0
    for ticker, quantity in items:
        price = prices.get(ticker) or prices.get(ticker.upper()) or 0
        if not price or price <= 0:
            errors.append(f"Price unavailable for {ticker}")
            continue
        try:
            existing = Stock.query.filter_by(user_id=g.user_id, ticker=ticker).first()
            if existing:
                total_cost = (existing.purchase_price * existing.quantity) + (price * quantity)
                existing.quantity += quantity
                existing.purchase_price = total_cost / existing.quantity if existing.quantity > 0 else price
            else:
                db.session.add(Stock(ticker=ticker, quantity=quantity, purchase_price=price, user_id=g.user_id))
            process_transaction(
                db, g.user_id, ticker, quantity, price, 'buy',
                timestamp=datetime.utcnow()
            )
            added_count += 1
        except Exception as e:
            logger.error(f"Error buying stock {ticker}: {e}")
            errors.append(f"Failed to buy {ticker}")

    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error committing buys: {e}")
        return jsonify({'error': 'failed_to_save_stocks'}), 500

    return jsonify({
        'success': True,
        'added_count': added_count,
        'errors': errors or None,
    })


@mobile_api.route('/portfolio/stocks', methods=['POST'])
@require_auth
@rate_limit(20)
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
    if len(stocks_list) > 50:
        return jsonify({'error': 'batch_too_large', 'max_stocks_per_request': 50}), 400
    
    # 'buy'  → a real market purchase: fetch a live price, create a Transaction,
    #          and (after hours) queue as a PENDING trade that settles at open.
    # 'seed' → declare already-owned holdings (onboarding / "Add Your Stocks").
    #          Recorded immediately at the cost basis provided (legacy behavior).
    intent = (data.get('intent') or 'seed').strip().lower()
    if intent == 'buy':
        return _add_stocks_as_buys(stocks_list)
    
    from cash_tracking import process_transaction
    
    added_count = 0
    errors = []
    
    for item in stocks_list:
        ticker = item.get('ticker', '').strip().upper()
        quantity = item.get('quantity')
        price = item.get('purchase_price') or item.get('price') or 0
        
        if not ticker or not quantity:
            errors.append(f"Missing ticker or quantity")
            continue
        
        try:
            quantity = float(quantity)
            price = float(price)
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
            
            # Track cash deployed
            if price > 0:
                process_transaction(
                    db, g.user_id, ticker, quantity, price, 'initial',
                    timestamp=datetime.utcnow()
                )
            
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
@rate_limit(60)
def get_leaderboard():
    """
    Get leaderboard for mobile app.
    
    Query params:
    - period: 1D, 1W, 1M, 3M, YTD, 1Y (default: 1W)
    - category: all, large_cap, small_cap (default: all)
    - limit: number of entries (default: 50, max: 100)
    - active_edge: 1/0 — filter removing inactive/one-hit accounts (default: 1)
    - industry: filter by industry name (default: all)
    - frequency: day_trader, moderate, any (default: any)
    - hide_fractional: 1/0 — Phase E: hide portfolios with any fractional
      share position. Default 0 (show everyone). NULL flags treated as
      "unknown / show" so users mid-rollout don't disappear before the
      market-close cron has populated user_portfolio_stats.
    """
    from models import db, User, Stock, Transaction, UserPortfolioStats, PortfolioSnapshot, MarketData, Subscription
    from datetime import datetime, timedelta, date as dt_date
    import json as json_module
    
    period = request.args.get('period', '1W')
    # Backward compat: map old period names
    if period == '5D' or period == '7D':
        period = '1W'
    category = request.args.get('category', 'all')
    limit = min(int(request.args.get('limit', 20)), 20)
    active_edge = request.args.get('active_edge', '1') == '1'
    industry_filter = request.args.get('industry', 'all')
    frequency_filter = request.args.get('frequency', 'any')
    hide_fractional = request.args.get('hide_fractional', '0') == '1'
    
    try:
        from leaderboard_utils import get_leaderboard_data, calculate_leaderboard_data, calculate_performance_metrics
        
        # Map 1W -> 5D for backend cache lookup (cache uses 5D key)
        cache_period = '5D' if period == '1W' else period
        
        # ── Cache-first architecture (scales to thousands of users) ──
        # 1) Try pre-computed LeaderboardCache (populated at market close)
        raw_data = get_leaderboard_data(period=cache_period, limit=100, category=category)
        
        # 2) Fallback: recompute from UserPortfolioChartCache (still cached, O(n) read)
        if not raw_data:
            raw_data = calculate_leaderboard_data(period=cache_period, limit=100, category=category)
        
        # 3) Thin fallback for brand-new users not yet in any cache
        # Only runs if caches are completely empty (first deploy or cache wipe)
        if not raw_data:
            raw_data = []
            all_users = User.query.filter(User.deleted_at.is_(None)).all()
            for u in all_users:
                snap = PortfolioSnapshot.query.filter_by(user_id=u.id)\
                    .order_by(PortfolioSnapshot.date.desc()).first()
                if snap:
                    perf = calculate_performance_metrics(u.id, cache_period)
                    raw_data.append({
                        'user_id': u.id,
                        'username': u.username,
                        'performance_percent': perf,
                        'subscriber_count': 0,
                        'subscription_price': 9.00,
                        'large_cap_percent': 0.0,
                        'avg_trades_per_week': 0.0,
                        'chart_data': None
                    })
        
        # Fetch previous cron's cached leaderboard for rank-change comparison
        prev_rank_map = {}
        try:
            from models import LeaderboardCache
            import json as json_module_lb
            prev_cache_key = f"{cache_period}_all_auth"
            prev_cache = LeaderboardCache.query.filter_by(period=prev_cache_key).first()
            if not prev_cache:
                prev_cache_key = f"{cache_period}_all_anon"
                prev_cache = LeaderboardCache.query.filter_by(period=prev_cache_key).first()
            if not prev_cache:
                prev_cache_key = f"{cache_period}_all"
                prev_cache = LeaderboardCache.query.filter_by(period=prev_cache_key).first()
            if prev_cache:
                prev_entries = json_module_lb.loads(prev_cache.leaderboard_data)
                prev_entries.sort(key=lambda x: x.get('performance_percent', 0), reverse=True)
                for idx, pe in enumerate(prev_entries):
                    prev_rank_map[pe.get('user_id')] = idx + 1
        except Exception:
            pass
        
        # ── Compute S&P 500 return for this period directly from MarketData ──
        # Uses the SAME date range as the performance calculator so sparklines align
        sp500_return_for_period = 0.0
        sp500_sparkline_global = []
        try:
            from performance_calculator import get_period_dates
            sp_start, sp_end = get_period_dates(cache_period)
            
            if cache_period in ('1D', '5D'):
                # For intraday periods: use SPY_INTRADAY (collected every 15 min)
                sp500_records = MarketData.query.filter(
                    MarketData.ticker == 'SPY_INTRADAY',
                    MarketData.date >= sp_start,
                    MarketData.date <= sp_end,
                    MarketData.timestamp.isnot(None)
                ).order_by(MarketData.timestamp.asc()).all()
                
                if sp500_records and len(sp500_records) >= 2:
                    base_val = float(sp500_records[0].close_price)
                    if base_val > 0:
                        sp500_sparkline_global = [
                            round(((float(r.close_price) - base_val) / base_val) * 100, 2)
                            for r in sp500_records
                        ]
                        sp500_return_for_period = sp500_sparkline_global[-1]
                elif sp500_records and len(sp500_records) == 1:
                    # Only 1 intraday point — use previous close as baseline
                    prev_day = sp_start - timedelta(days=1)
                    while prev_day.weekday() >= 5:
                        prev_day -= timedelta(days=1)
                    prev_close = MarketData.query.filter(
                        MarketData.ticker == 'SPY_SP500',
                        MarketData.date == prev_day
                    ).first()
                    if prev_close and float(prev_close.close_price) > 0:
                        base_val = float(prev_close.close_price)
                        curr_val = float(sp500_records[0].close_price)
                        sp500_return_for_period = round(((curr_val - base_val) / base_val) * 100, 2)
                        sp500_sparkline_global = [0.0, sp500_return_for_period]
                
                # Fallback to daily SPY_SP500 if no intraday data
                if not sp500_sparkline_global:
                    sp500_records = MarketData.query.filter(
                        MarketData.ticker == 'SPY_SP500',
                        MarketData.date >= sp_start,
                        MarketData.date <= sp_end
                    ).order_by(MarketData.date.asc()).all()
                    if sp500_records and len(sp500_records) >= 2:
                        base_val = float(sp500_records[0].close_price)
                        if base_val > 0:
                            sp500_sparkline_global = [
                                round(((float(r.close_price) - base_val) / base_val) * 100, 2)
                                for r in sp500_records
                            ]
                            sp500_return_for_period = sp500_sparkline_global[-1]
            else:
                # For longer periods: use daily SPY_SP500 close
                sp500_records = MarketData.query.filter(
                    MarketData.ticker == 'SPY_SP500',
                    MarketData.date >= sp_start,
                    MarketData.date <= sp_end
                ).order_by(MarketData.date.asc()).all()
                
                if sp500_records and len(sp500_records) >= 2:
                    base_val = float(sp500_records[0].close_price)
                    if base_val > 0:
                        sp500_sparkline_global = [
                            round(((float(r.close_price) - base_val) / base_val) * 100, 2)
                            for r in sp500_records
                        ]
                        sp500_return_for_period = sp500_sparkline_global[-1]
        except Exception as e:
            logger.warning(f"S&P 500 lookup failed: {e}")
        
        # Build enriched entries
        leaderboard = []
        available_industries = set()
        
        # Period-aware age thresholds for Active Edge
        # Keep low — 2-trade minimum + 60-day recency are the real quality filters
        min_age_for_period = {
            '1D': 0, '1W': 1, '1M': 1, '3M': 14,
            'YTD': 14, '1Y': 30
        }
        
        # ── Pre-fetch data in bulk to avoid N+1 queries at scale ──
        # Batch-load users, industry stats, and last trades for all raw_data entries
        raw_user_ids = [e.get('user_id') for e in (raw_data or []) if e.get('user_id')]
        
        # Batch load users (single query)
        users_map = {}
        if raw_user_ids:
            users_list = User.query.filter(User.id.in_(raw_user_ids)).all()
            users_map = {u.id: u for u in users_list}
        
        # Batch load industry mix + fractional flag from UserPortfolioStats
        # (single query feeds both the industry filter and the Phase E
        # hide_fractional toggle).
        industry_stats_map = {}
        has_fractional_map = {}
        if raw_user_ids:
            stats_list = UserPortfolioStats.query.filter(UserPortfolioStats.user_id.in_(raw_user_ids)).all()
            for s in stats_list:
                if s.industry_mix and isinstance(s.industry_mix, dict):
                    industry_stats_map[s.user_id] = s.industry_mix
                # NULL stays NULL on purpose: see filter below.
                has_fractional_map[s.user_id] = s.has_fractional_holdings
        
        # Batch load last trade dates (single query using subquery)
        from sqlalchemy import func as sqla_func
        last_trade_map = {}
        if raw_user_ids:
            last_trades = db.session.query(
                Transaction.user_id,
                sqla_func.max(Transaction.timestamp).label('last_ts')
            ).filter(
                Transaction.user_id.in_(raw_user_ids)
            ).group_by(Transaction.user_id).all()
            last_trade_map = {uid: ts for uid, ts in last_trades}
        
        # Batch load total trade counts for Active Edge (single query)
        total_trade_map = {}
        if active_edge and raw_user_ids:
            trade_counts = db.session.query(
                Transaction.user_id,
                sqla_func.count(Transaction.id).label('cnt')
            ).filter(
                Transaction.user_id.in_(raw_user_ids)
            ).group_by(Transaction.user_id).all()
            total_trade_map = {uid: cnt for uid, cnt in trade_counts}
        
        # Batch load unique stock counts (single query)
        stock_count_map = {}
        if raw_user_ids:
            stock_counts = db.session.query(
                Stock.user_id,
                sqla_func.count(Stock.id).label('cnt')
            ).filter(
                Stock.user_id.in_(raw_user_ids)
            ).group_by(Stock.user_id).all()
            stock_count_map = {uid: cnt for uid, cnt in stock_counts}
        
        # Batch load subscriber counts (real + gifted)
        sub_count_map = {}
        if raw_user_ids:
            sub_counts = db.session.query(
                Subscription.subscribed_to_id,
                sqla_func.count(Subscription.id).label('cnt')
            ).filter(
                Subscription.subscribed_to_id.in_(raw_user_ids),
                Subscription.status == 'active'
            ).group_by(Subscription.subscribed_to_id).all()
            sub_count_map = {uid: cnt for uid, cnt in sub_counts}
            # Add gifted (admin) subscribers
            try:
                from models import AdminSubscription
                for asub in AdminSubscription.query.filter(AdminSubscription.portfolio_user_id.in_(raw_user_ids)).all():
                    bonus = asub.bonus_subscriber_count or 0
                    if bonus > 0:
                        sub_count_map[asub.portfolio_user_id] = sub_count_map.get(asub.portfolio_user_id, 0) + bonus
            except Exception:
                pass
        
        # API-time eligibility filter: ensure users have enough history for this period.
        # This catches stale cache entries that were computed before eligibility checks existed.
        eligibility_map_api = {}
        try:
            from performance_calculator import batch_get_leaderboard_eligibility
            eligibility_map_api = batch_get_leaderboard_eligibility(cache_period)
        except Exception as e:
            logger.warning(f"API-time eligibility check failed: {e}")
        
        for entry in (raw_data or []):
            user_id = entry.get('user_id')
            user = users_map.get(user_id)
            if not user:
                continue
            
            # Skip users ineligible for this period (e.g., 3M requires 90 days of data)
            if eligibility_map_api:
                elig = eligibility_map_api.get(user_id)
                if elig and not elig['eligible']:
                    continue
                elif not elig:
                    continue  # No snapshot data at all
            
            # Prefer cached values from calculate_leaderboard_data; fallback to live
            avg_trades_per_week = entry.get('avg_trades_per_week')
            if avg_trades_per_week is None:
                thirty_days_ago = datetime.utcnow() - timedelta(days=30)
                recent_trade_count = Transaction.query.filter(
                    Transaction.user_id == user_id,
                    Transaction.timestamp >= thirty_days_ago
                ).count()
                avg_trades_per_week = round((recent_trade_count / 30.0) * 7, 1)
            
            # Unique stock count (from batch-loaded map)
            unique_stocks = stock_count_map.get(user_id, 0)
            
            # Large cap percent (from cache)
            large_cap_pct = entry.get('large_cap_percent', 0.0)
            
            # Account age (computed from user object — no extra query)
            account_age_days = 0
            if user.created_at:
                account_age_days = (datetime.utcnow() - user.created_at).days
            
            # Industry mix (from batch-loaded stats)
            industry_mix = industry_stats_map.get(user_id, {})
            if not industry_mix:
                try:
                    from leaderboard_utils import calculate_industry_mix
                    industry_mix = calculate_industry_mix(user_id) or {}
                except Exception:
                    pass
            
            for ind_name in industry_mix.keys():
                available_industries.add(ind_name)
            
            # Last trade (from batch-loaded map)
            last_trade_ts = last_trade_map.get(user_id)
            last_trade_date = last_trade_ts.isoformat() if last_trade_ts else None
            
            # Subscriber count (prefer cached, then batch-loaded map)
            sub_count = entry.get('subscriber_count', 0)
            if sub_count == 0:
                sub_count = sub_count_map.get(user_id, 0)
            
            # Use pre-computed sparkline from cache (populated by calculate_leaderboard_data
            # using the same calculate_portfolio_performance as the portfolio chart endpoint)
            sparkline_points = entry.get('sparkline_data') or []
            
            # Fallback: extract from chart_data if sparkline not pre-computed
            if not sparkline_points:
                chart_data_raw = entry.get('chart_data')
                if chart_data_raw:
                    datasets = chart_data_raw.get('datasets', [])
                    if datasets and len(datasets) > 0:
                        raw_vals = datasets[0].get('data', [])
                        if raw_vals and len(raw_vals) >= 2:
                            sparkline_points = [round(float(v), 2) for v in raw_vals]
            
            # NOTE: sparkline data comes from calculate_portfolio_performance which
            # already computes returns relative to the first snapshot (baseline = 0%).
            # No normalization needed — shifting would cause mismatch with portfolio chart.
            
            # Sample S&P sparkline to same length as portfolio for consistent alignment.
            # Both start at 0% on the y-axis with matching x-axis density.
            portfolio_len = len([v for v in sparkline_points if v is not None]) if sparkline_points else 0
            if portfolio_len > 0 and sp500_sparkline_global:
                sp_step = max(1, len(sp500_sparkline_global) // max(portfolio_len, 1))
                sp500_sparkline_points = sp500_sparkline_global[::sp_step][-portfolio_len:]
                # Normalize S&P to also start at 0 from the sampled window
                if sp500_sparkline_points:
                    sp_base = sp500_sparkline_points[0]
                    sp500_sparkline_points = [round(v - sp_base, 2) for v in sp500_sparkline_points]
            else:
                sp500_sparkline_points = sp500_sparkline_global
            
            # ── Active Edge filter ──
            if active_edge:
                # Must have traded within last 60 days
                if not last_trade_ts or (datetime.utcnow() - last_trade_ts).days > 60:
                    continue
                # Must have at least 2 trades total
                total_trades = total_trade_map.get(user_id, 0)
                if total_trades < 2:
                    continue
                # Period-aware minimum age
                min_age = min_age_for_period.get(period, 1)
                if account_age_days < min_age:
                    continue
            
            # ── Sector filter (supports comma-separated multi-select) ──
            # Per user requirement (May 2026): only show portfolios ENTIRELY
            # composed of the selected sectors. The previous semantics was
            # "any portfolio that contains at least one position in any of
            # the selected sectors" \u2014 which is way too loose (e.g. picking
            # 'Energy' showed every diversified portfolio that happens to
            # own one oil stock).
            #
            # New semantics: the share of the portfolio invested across the
            # selected sectors must be \u2265 99% (1% slack for floating-point
            # rounding + unclassified tickers). Anything meaningfully
            # diversified outside the selection is excluded.
            if industry_filter and industry_filter != 'all':
                requested_sectors = {s.strip() for s in industry_filter.split(',')}
                in_selection_pct = sum(
                    pct for sector, pct in industry_mix.items()
                    if sector in requested_sectors
                )
                if in_selection_pct < 99.0:
                    continue
            
            # ── Frequency filter ──
            if frequency_filter == 'day_trader' and avg_trades_per_week < 5:
                continue
            elif frequency_filter == 'moderate' and (avg_trades_per_week >= 5 or avg_trades_per_week < 0.5):
                continue

            # ── Hide-fractional filter (Phase E) ──
            # Only hide when the flag is explicitly True. NULL = unknown
            # (user not yet processed by the cron) is treated as "show" to
            # avoid mass-hiding mid-rollout. Backfill via
            # /admin/portfolio-stats/recompute-fractional flips NULLs to
            # the correct True/False.
            if hide_fractional and has_fractional_map.get(user_id) is True:
                continue
            
            user_return = entry.get('performance_percent', 0.0)
            alpha_vs_sp500 = round(user_return - sp500_return_for_period, 2)
            
            leaderboard.append({
                'rank': 0,
                'user': {
                    'id': user_id,
                    'username': user.username,  # Live DB is source of truth (avoids stale cached usernames after renames)
                    'display_name': user.public_name,
                    'portfolio_slug': user.portfolio_slug
                },
                'return_percent': user_return,
                'sp500_return': round(sp500_return_for_period, 2),
                'alpha_vs_sp500': alpha_vs_sp500,
                'subscriber_count': sub_count,
                'subscription_price': entry.get('subscription_price', 9.00),
                'sparkline_data': sparkline_points if sparkline_points else [],
                'sp500_sparkline_data': sp500_sparkline_points if sp500_sparkline_points else [],
                'avg_trades_per_week': avg_trades_per_week,
                'unique_stocks': unique_stocks,
                'large_cap_pct': round(large_cap_pct, 1),
                'account_age_days': account_age_days,
                'industry_mix': industry_mix,
                'last_trade_date': last_trade_date
            })
        
        # Sort by performance descending, then re-rank
        leaderboard.sort(key=lambda x: x['return_percent'], reverse=True)
        
        for i, e in enumerate(leaderboard):
            e['rank'] = i + 1
            # rank_change: positive = moved up, negative = moved down, 0 = same/new
            prev_rank = prev_rank_map.get(e['user']['id'])
            if prev_rank is not None:
                e['rank_change'] = prev_rank - e['rank']  # e.g. was 5, now 3 → +2
            else:
                e['rank_change'] = 0  # new entry or no previous data
        
        return jsonify({
            'period': period,
            'category': category,
            'sp500_return': round(sp500_return_for_period, 2),
            'available_industries': sorted(list(available_industries)),
            'entries': leaderboard[:limit]
        })
        
    except Exception as e:
        logger.error(f"Get leaderboard error: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return jsonify({
            'period': period,
            'category': category,
            'sp500_return': 0.0,
            'available_industries': [],
            'entries': []
        })


# =============================================================================
# Notification Settings
# =============================================================================

# ── Phase D: portfolio resizer endpoints ────────────────────────────────────
# UX flow (per gameplan 2026-05-20):
#   1. Subscriber opens a subscribed portfolio's detail view.
#   2. Taps a "Set your investment size" button.
#   3. Enters a dollar amount (e.g. $10,000).
#   4. Mobile POSTs /subscriptions/<id>/scale with {target_dollars: 10000}.
#   5. Backend computes scale_factor at the moment of the call (FROZEN).
#   6. Subsequent GET /portfolio/<slug> calls return scaled holdings.
#   7. To clear scaling, mobile sends DELETE /subscriptions/<id>/scale.
#
# Why "frozen" scale_factor: if we recomputed scale on every view, a
# creator's price drift would change the subscriber's share counts —
# weird UX. Frozen at set-time mirrors how brokerages copy-trade.

def _compute_portfolio_value(user_id):
    """Calculate a user's current portfolio value (holdings + cash).

    Used by /subscriptions/<id>/scale to compute scale_factor at set-time.
    Reuses the same batch-price logic as get_portfolio so the dollar
    targets are consistent between "what the subscriber sees" and "what
    we used to compute scale_factor".

    Returns 0.0 on any failure (caller should reject the scale request
    with a clear error rather than silently writing scale=infinity).
    """
    from models import Stock
    try:
        stocks = Stock.query.filter_by(user_id=user_id).all()
        stocks = [s for s in stocks if s.quantity and s.quantity > 0]
        if not stocks:
            # Cash-only portfolios are unusual but valid — fall through to
            # the cash_balance read below.
            pass

        # Batch price fetch (premium tier: 150 calls/min)
        batch_prices = {}
        try:
            from portfolio_performance import PortfolioPerformanceCalculator
            calc = PortfolioPerformanceCalculator()
            tickers = [s.ticker for s in stocks if s.ticker]
            if tickers:
                batch_prices = calc.get_batch_stock_data(tickers)
        except Exception as e:
            logger.warning(f"_compute_portfolio_value: batch price failed: {e}")

        total = 0.0
        for s in stocks:
            price = batch_prices.get((s.ticker or '').upper(), s.purchase_price or 0)
            total += float(price or 0) * float(s.quantity or 0)

        # Cash component
        from models import User
        owner = User.query.get(user_id)
        cash = float(getattr(owner, 'cash_proceeds', 0.0) or 0.0) if owner else 0.0
        total += cash

        return round(total, 2)
    except Exception as e:
        logger.error(f"_compute_portfolio_value failed for user_id={user_id}: {e}")
        return 0.0


@mobile_api.route('/subscriptions/<int:sub_id>/scale', methods=['POST'])
@require_auth
def set_subscription_scale(sub_id):
    """Set or update a subscription's scale (Phase D portfolio resizer).

    Request body:
        { "target_dollars": 10000.00 }

    The server computes scale_factor = target_dollars / current_target_value
    using the SAME batch-pricing path GET /portfolio/<slug> uses, so the
    scale will faithfully render the requested dollar size.

    Auth: subscriber must own the subscription. Owner-of-portfolio cannot
    set scale on their own creation (would be meaningless — the field
    is for copy-trader subscribers).

    Response:
        {
          "success": true,
          "scale_factor": 0.1234,
          "target_dollars": 10000.00,
          "scale_set_at": "<iso>",
          "target_portfolio_value": 81037.00  // what was scaled FROM
        }

    Common errors:
        404 subscription_not_found       — sub_id doesn't exist or isn't theirs
        400 target_dollars_required      — missing or non-positive
        400 target_portfolio_empty       — creator has $0 portfolio, can't scale
    """
    from models import db, MobileSubscription

    data = request.get_json() or {}
    try:
        target_dollars = float(data.get('target_dollars') or 0)
    except (TypeError, ValueError):
        return jsonify({'error': 'target_dollars_must_be_number'}), 400
    if target_dollars <= 0:
        return jsonify({'error': 'target_dollars_required'}), 400

    try:
        sub = MobileSubscription.query.filter_by(
            id=sub_id, subscriber_id=g.user_id, status='active'
        ).first()
        if not sub:
            return jsonify({'error': 'subscription_not_found'}), 404

        target_value = _compute_portfolio_value(sub.subscribed_to_id)
        if target_value <= 0:
            return jsonify({'error': 'target_portfolio_empty'}), 400

        scale = target_dollars / target_value
        now = datetime.utcnow()
        sub.scale_factor = scale
        sub.target_dollars = target_dollars
        sub.scale_set_at = now
        db.session.commit()

        return jsonify({
            'success': True,
            'scale_factor': round(scale, 6),
            'target_dollars': round(target_dollars, 2),
            'scale_set_at': _utc_iso(now),
            'target_portfolio_value': target_value,
        })
    except Exception as e:
        logger.error(f"set_subscription_scale failed: {e}")
        db.session.rollback()
        return jsonify({'error': 'scale_update_failed'}), 500


@mobile_api.route('/subscriptions/<int:sub_id>/scale', methods=['DELETE'])
@require_auth
def clear_subscription_scale(sub_id):
    """Clear a subscription's scale, returning to the unscaled (full
    portfolio) view. NULLs scale_factor, target_dollars, scale_set_at."""
    from models import db, MobileSubscription

    try:
        sub = MobileSubscription.query.filter_by(
            id=sub_id, subscriber_id=g.user_id, status='active'
        ).first()
        if not sub:
            return jsonify({'error': 'subscription_not_found'}), 404

        sub.scale_factor = None
        sub.target_dollars = None
        sub.scale_set_at = None
        db.session.commit()

        return jsonify({'success': True})
    except Exception as e:
        logger.error(f"clear_subscription_scale failed: {e}")
        db.session.rollback()
        return jsonify({'error': 'scale_clear_failed'}), 500


@mobile_api.route('/settings/portfolio-preferences', methods=['GET'])
@require_auth
def get_portfolio_preferences():
    """Read the current user's portfolio display preferences.

    Currently exposes `prefer_fractional` (default True). The field
    drives the Phase D scaled-view share formatter and may eventually
    drive other display options too — return them as a single dict so
    we can grow without bumping the endpoint.
    """
    from models import User
    user = User.query.get(g.user_id)
    if not user:
        return jsonify({'error': 'user_not_found'}), 404
    return jsonify({
        'prefer_fractional': _get_prefer_fractional(user),
    })


@mobile_api.route('/settings/portfolio-preferences', methods=['PUT'])
@require_auth
def update_portfolio_preferences():
    """Update portfolio display preferences.

    Request body (all fields optional, only provided ones are changed):
        { "prefer_fractional": true }

    Stored in User.extra_data (JSON) so adding fields later doesn't
    require a schema migration.
    """
    from models import db, User
    data = request.get_json() or {}
    user = User.query.get(g.user_id)
    if not user:
        return jsonify({'error': 'user_not_found'}), 404

    extra = dict(user.extra_data or {})
    if 'prefer_fractional' in data:
        extra['prefer_fractional'] = bool(data['prefer_fractional'])

    user.extra_data = extra
    # SQLAlchemy doesn't always detect in-place JSON mutations; force the
    # ORM to mark the column dirty with flag_modified so the change
    # actually hits the DB.
    try:
        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(user, 'extra_data')
    except Exception:
        pass
    db.session.commit()
    return jsonify({
        'success': True,
        'prefer_fractional': _get_prefer_fractional(user),
    })


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


@mobile_api.route('/notifications/history', methods=['GET'])
@require_auth
def notification_history():
    """
    Trade Alerts feed for the Subscriptions tab.

    Sourced from the TRANSACTIONS of every portfolio the user actively
    subscribes to — NOT from delivery logs. This guarantees exactly ONE alert
    per trade regardless of whether the subscriber has push on, email on, both,
    or NEITHER.

    The previous implementation merged NotificationLog (email) +
    PushNotificationLog (push), which (a) double-counted every trade when both
    channels were enabled, and (b) showed nothing when neither was. Delivery
    logs are the wrong source of truth for "what trades happened" — the
    subscribed trader's Transaction ledger is.

    Only trades AT/AFTER each subscription's start (MobileSubscription.created_at)
    are shown, and 'initial'/seed rows are excluded — alerts are real buy/sell
    trades. Query params: ?limit=50&offset=0
    """
    from models import MobileSubscription, Transaction, User
    from sqlalchemy import and_, or_, desc

    limit = min(int(request.args.get('limit', 50)), 100)
    offset = int(request.args.get('offset', 0))

    try:
        subs = MobileSubscription.query.filter_by(
            subscriber_id=g.user_id, status='active'
        ).all()
        if not subs:
            return jsonify({'notifications': [], 'total': 0,
                            'limit': limit, 'offset': offset})

        # trader_id -> earliest active subscription start. Alerts only surface
        # trades made on/after the user subscribed to that portfolio.
        sub_start = {}
        for s in subs:
            tid = s.subscribed_to_id
            start = s.created_at or datetime(1970, 1, 1)
            if tid not in sub_start or start < sub_start[tid]:
                sub_start[tid] = start
        trader_ids = list(sub_start.keys())

        # Per-trader "trades since I subscribed" predicate, OR'd together so a
        # single query covers all of the user's subscriptions.
        per_trader = [
            and_(Transaction.user_id == tid, Transaction.timestamp >= start)
            for tid, start in sub_start.items()
        ]
        base_q = Transaction.query.filter(
            Transaction.user_id.in_(trader_ids),
            Transaction.transaction_type.in_(('buy', 'sell')),
            or_(*per_trader),
        )

        total = base_q.count()
        txns = (base_q.order_by(desc(Transaction.timestamp))
                .limit(limit).offset(offset).all())

        traders = {u.id: u for u in
                   User.query.filter(User.id.in_(trader_ids)).all()}

        items = []
        for t in txns:
            trader = traders.get(t.user_id)
            trader_name = (getattr(trader, 'public_name', None)
                           or (trader.username if trader else 'A portfolio'))
            action = (t.transaction_type or '').upper()
            emoji = '🟢' if action == 'BUY' else '🔴'
            verb = 'bought' if action == 'BUY' else 'sold'
            qty = t.quantity or 0
            qty_str = f"{int(qty)}" if qty == int(qty) else f"{qty:g}"
            price = t.price or 0
            items.append({
                'id': f'trade-{t.id}',
                'type': 'trade',
                'trader_username': trader_name,
                'status': 'executed',
                'created_at': _utc_iso(t.timestamp) if t.timestamp else None,
                'title': f"{emoji} {trader_name} {action}",
                'body': f"{trader_name} {verb} {qty_str} {t.ticker} @ ${price:,.2f}",
            })

        return jsonify({
            'notifications': items,
            'total': total,
            'limit': limit,
            'offset': offset,
        })
    except Exception as e:
        logger.error(f"Trade alerts feed error: {e}")
        return jsonify({'error': 'fetch_failed'}), 500


@mobile_api.route('/user/preferences', methods=['GET'])
@require_auth
def get_user_preferences():
    """Get user-level notification preferences and profile info."""
    from models import db, User
    try:
        user = User.query.get(g.user_id)
        if not user:
            return jsonify({'error': 'user_not_found'}), 404
        return jsonify({
            'username': user.username,
            'display_name': user.public_name,
            'email': user.email,
            'email_notifications_enabled': getattr(user, 'email_notifications_enabled', True),
            'push_notifications_enabled': getattr(user, 'push_notifications_enabled', True),
        })
    except Exception as e:
        logger.error(f"Get user preferences error: {e}")
        return jsonify({'error': 'fetch_failed'}), 500


@mobile_api.route('/user/preferences', methods=['PUT'])
@require_auth
def update_user_preferences():
    """
    Update user-level notification preferences.
    Request body (all fields optional):
    {
        "email_notifications_enabled": true/false,
        "push_notifications_enabled": true/false
    }
    """
    from models import db, User
    data = request.get_json()
    if not data:
        return jsonify({'error': 'missing_request_body'}), 400

    try:
        user = User.query.get(g.user_id)
        if not user:
            return jsonify({'error': 'user_not_found'}), 404

        if 'email_notifications_enabled' in data:
            user.email_notifications_enabled = bool(data['email_notifications_enabled'])
        if 'push_notifications_enabled' in data:
            user.push_notifications_enabled = bool(data['push_notifications_enabled'])

        db.session.commit()
        return jsonify({
            'success': True,
            'email_notifications_enabled': user.email_notifications_enabled,
            'push_notifications_enabled': user.push_notifications_enabled,
        })
    except Exception as e:
        logger.error(f"Update user preferences error: {e}")
        return jsonify({'error': 'update_failed'}), 500


# =============================================================================
# Tax Info Status (Xero handles W-9 collection natively)
# =============================================================================

@mobile_api.route('/user/tax-status', methods=['GET'])
@require_auth
def get_tax_status():
    """Check if this creator's tax info is on file in Xero.
    
    Xero collects W-9 / tax info directly from contractors in the
    '1099 Contractors' contact group. This endpoint tells the user
    whether Xero has their TIN so payouts aren't held.
    """
    try:
        import xero_service
        from models import User
        user = User.query.get(g.user_id)
        if not user:
            return jsonify({'error': 'user_not_found'}), 404
        
        has_tax_info = xero_service.contact_has_tax_number(user.username)
        
        if has_tax_info:
            return jsonify({
                'tax_info_on_file': True,
                'status': 'complete',
                'message': 'Your tax information is on file. Payouts are enabled.'
            })
        else:
            return jsonify({
                'tax_info_on_file': False,
                'status': 'missing',
                'message': 'Tax information not yet received. Check your email from Xero for a W-9 request, or contact support if you haven\'t received one.'
            })
    except Exception as e:
        logger.error(f"Tax status check error: {e}")
        return jsonify({'error': 'check_failed'}), 500


@mobile_api.route('/user/username', methods=['PUT'])
@require_auth
def update_username():
    """
    Change username. Validates uniqueness, length, and allowed characters.
    Request body: { "username": "new-username" }
    """
    from models import db, User
    import re

    data = request.get_json()
    if not data or not data.get('username'):
        return jsonify({'error': 'username_required'}), 400

    new_username = data['username'].strip().lower()

    # Validation
    if len(new_username) < 3 or len(new_username) > 30:
        return jsonify({'error': 'username_must_be_3_to_30_characters'}), 400
    if not re.match(r'^[a-z0-9][a-z0-9._-]*[a-z0-9]$', new_username):
        return jsonify({'error': 'username_must_be_alphanumeric_with_hyphens_dots_underscores'}), 400

    try:
        user = User.query.get(g.user_id)
        if not user:
            return jsonify({'error': 'user_not_found'}), 404

        if user.username == new_username:
            return jsonify({'success': True, 'username': new_username})

        existing = User.query.filter_by(username=new_username).first()
        if existing:
            return jsonify({'error': 'username_already_taken'}), 409

        user.username = new_username
        db.session.commit()
        return jsonify({'success': True, 'username': user.username})
    except Exception as e:
        db.session.rollback()
        logger.error(f"Update username error: {e}")
        return jsonify({'error': 'update_failed'}), 500


# =============================================================================
# Authentication Endpoints
# =============================================================================

# ---------------------------------------------------------------------------
# OAuth ID token signature verification (Google / Apple)
#
# Pre-launch security blocker (LAUNCH_TODO.md:41): the original /auth/token
# below decoded ID tokens with `verify_signature=False`, which means any
# actor in possession of any valid Google or Apple ID token could
# authenticate as any user simply by forging a `sub` claim. The helpers
# below verify signatures against the upstream JWKS, validate issuer,
# expiration, and audience, and reject anything that doesn't match.
#
# Rollout safety: gated behind STRICT_OAUTH_VERIFICATION env var so we can
# deploy this code without breaking iOS/Android users mid-rollout. When the
# flag is unset (the default), the legacy unsafe path is used and a CRITICAL
# warning is logged on every auth request so the gap is visible in Vercel
# logs. Once the required client-ID env vars are configured on Vercel
# (GOOGLE_IOS_CLIENT_ID, GOOGLE_ANDROID_CLIENT_ID, APPLE_BUNDLE_ID), flip
# STRICT_OAUTH_VERIFICATION=enforce to activate strict verification. A
# follow-up commit should remove the legacy path entirely once verified.
# ---------------------------------------------------------------------------

GOOGLE_JWKS_URL = "https://www.googleapis.com/oauth2/v3/certs"
GOOGLE_ALLOWED_ISSUERS = {"https://accounts.google.com", "accounts.google.com"}
APPLE_JWKS_URL = "https://appleid.apple.com/auth/keys"
APPLE_ISSUER = "https://appleid.apple.com"

# Module-level JWKS clients, lazy-initialized. PyJWKClient caches keys
# internally so we don't refetch JWKS on every request.
_google_jwk_client = None
_apple_jwk_client = None


def _get_google_jwk_client():
    """Lazy singleton for Google's JWKS client."""
    global _google_jwk_client
    if _google_jwk_client is None:
        from jwt import PyJWKClient
        _google_jwk_client = PyJWKClient(GOOGLE_JWKS_URL, cache_keys=True, max_cached_keys=16)
    return _google_jwk_client


def _get_apple_jwk_client():
    """Lazy singleton for Apple's JWKS client."""
    global _apple_jwk_client
    if _apple_jwk_client is None:
        from jwt import PyJWKClient
        _apple_jwk_client = PyJWKClient(APPLE_JWKS_URL, cache_keys=True, max_cached_keys=16)
    return _apple_jwk_client


def _accepted_google_audiences():
    """Return the set of acceptable `aud` claim values for Google ID tokens.

    Current state of clients that hit /auth/token with provider=google:

      * Android (com.apestogether.app) — uses Credential Manager's
        GetGoogleIdOption with serverClientId = the *Web* OAuth client ID.
        The issued ID token has aud = that Web Client ID. That same value
        is GOOGLE_WEB_CLIENT_ID in android/secrets.properties; on Vercel
        it must be exposed as GOOGLE_ANDROID_CLIENT_ID.

      * iOS — does NOT use Google Sign-In at all (Apple Sign-In only;
        see ios/ApesTogetherApp/Services/AuthenticationManager.swift).
        GOOGLE_IOS_CLIENT_ID is therefore unused today. It's still read
        here so a future iOS Google flow can be enabled by setting one
        env var without a code change.

      * Legacy web (Flask Authlib in app.py / api/index.py) — uses
        GOOGLE_CLIENT_ID for the browser OAuth round-trip and posts to
        Authlib's own callback, NOT /auth/token. So GOOGLE_CLIENT_ID
        landing here is belt-and-suspenders for any future caller; the
        production web flow does not depend on it.
    """
    auds = set()
    for env_name in ("GOOGLE_IOS_CLIENT_ID", "GOOGLE_ANDROID_CLIENT_ID", "GOOGLE_CLIENT_ID"):
        v = os.environ.get(env_name)
        if v:
            auds.add(v.strip())
    return auds


def _verify_google_id_token(id_token_str):
    """Verify a Google ID token and return its payload.

    Raises ValueError on any failure (caller maps to 401 response).
    """
    import jwt as pyjwt

    audiences = _accepted_google_audiences()
    if not audiences:
        raise ValueError("server_misconfigured: no Google client IDs configured")

    try:
        signing_key = _get_google_jwk_client().get_signing_key_from_jwt(id_token_str)
    except Exception as e:
        raise ValueError(f"google_token_kid_lookup_failed: {e}")

    try:
        payload = pyjwt.decode(
            id_token_str,
            signing_key.key,
            algorithms=["RS256"],
            audience=list(audiences),
            options={"require": ["exp", "iat", "iss", "sub", "aud"]},
        )
    except pyjwt.ExpiredSignatureError:
        raise ValueError("google_token_expired")
    except pyjwt.InvalidAudienceError:
        # Surface the actual aud the token carried so we can diagnose without
        # a redeploy. The token signature was already verified above, so the
        # aud value is trusted (not attacker-controlled).
        try:
            unverified = pyjwt.decode(id_token_str, options={"verify_signature": False})
            actual_aud = unverified.get("aud")
        except Exception:
            actual_aud = "<unparseable>"
        raise ValueError(
            f"google_token_audience_mismatch: token_aud={actual_aud!r} "
            f"expected_one_of={sorted(audiences)}"
        )
    except pyjwt.InvalidTokenError as e:
        raise ValueError(f"google_token_invalid: {e}")

    iss = payload.get("iss")
    if iss not in GOOGLE_ALLOWED_ISSUERS:
        raise ValueError(f"google_token_bad_issuer: {iss}")

    return payload


def _verify_apple_id_token(id_token_str):
    """Verify an Apple ID token and return its payload.

    Raises ValueError on any failure (caller maps to 401 response).
    """
    import jwt as pyjwt

    # For native Sign in with Apple (AuthenticationServices on iOS), the
    # `aud` claim is the iOS app's Bundle ID, which matches what's already
    # configured for IAP receipt validation.
    expected_aud = os.environ.get("APPLE_BUNDLE_ID")
    if not expected_aud:
        raise ValueError("server_misconfigured: APPLE_BUNDLE_ID not set")

    try:
        signing_key = _get_apple_jwk_client().get_signing_key_from_jwt(id_token_str)
    except Exception as e:
        raise ValueError(f"apple_token_kid_lookup_failed: {e}")

    try:
        payload = pyjwt.decode(
            id_token_str,
            signing_key.key,
            algorithms=["RS256"],
            audience=expected_aud,
            issuer=APPLE_ISSUER,
            options={"require": ["exp", "iat", "iss", "sub", "aud"]},
        )
    except pyjwt.ExpiredSignatureError:
        raise ValueError("apple_token_expired")
    except pyjwt.InvalidAudienceError:
        # Surface the actual aud so we can diagnose APPLE_BUNDLE_ID misconfigs
        # without redeploying. Signature is already verified at this point.
        try:
            unverified = pyjwt.decode(id_token_str, options={"verify_signature": False})
            actual_aud = unverified.get("aud")
        except Exception:
            actual_aud = "<unparseable>"
        raise ValueError(
            f"apple_token_audience_mismatch: token_aud={actual_aud!r} "
            f"expected={expected_aud!r}"
        )
    except pyjwt.InvalidIssuerError:
        raise ValueError("apple_token_bad_issuer")
    except pyjwt.InvalidTokenError as e:
        raise ValueError(f"apple_token_invalid: {e}")

    return payload


def _strict_oauth_enabled():
    """Read STRICT_OAUTH_VERIFICATION env var. Accepts any truthy spelling.

    Default: off (legacy decode-without-verification path used). Set to
    `enforce` (or `true`/`1`/`on`) on Vercel to activate strict verification.
    """
    v = os.environ.get("STRICT_OAUTH_VERIFICATION", "").strip().lower()
    return v in ("1", "true", "on", "enforce", "yes")


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

    strict = _strict_oauth_enabled()

    try:
        if provider == 'apple':
            if strict:
                try:
                    payload = _verify_apple_id_token(id_token)
                except ValueError as ve:
                    logger.warning(f"Apple ID token rejected by strict verification: {ve}")
                    return jsonify({'error': 'invalid_apple_token'}), 401
                oauth_id = payload.get('sub')
                email = payload.get('email') or data.get('email')
            else:
                # LEGACY (INSECURE) PATH — TEMPORARY. Remove after rollout.
                logger.critical(
                    "AUTH SECURITY: /auth/token Apple flow decoded without "
                    "signature verification. Set STRICT_OAUTH_VERIFICATION=enforce."
                )
                import jwt as pyjwt
                try:
                    payload = pyjwt.decode(id_token, options={"verify_signature": False})
                    oauth_id = payload.get('sub')
                    email = payload.get('email') or data.get('email')
                except Exception:
                    return jsonify({'error': 'invalid_apple_token'}), 400

        elif provider == 'google':
            if strict:
                try:
                    payload = _verify_google_id_token(id_token)
                except ValueError as ve:
                    logger.warning(f"Google ID token rejected by strict verification: {ve}")
                    return jsonify({'error': 'invalid_google_token'}), 401
                oauth_id = payload.get('sub')
                email = payload.get('email') or data.get('email')
            else:
                # LEGACY (INSECURE) PATH — TEMPORARY. Remove after rollout.
                logger.critical(
                    "AUTH SECURITY: /auth/token Google flow decoded without "
                    "signature verification. Set STRICT_OAUTH_VERIFICATION=enforce."
                )
                import jwt as pyjwt
                try:
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
                'display_name': user.public_name,
                'portfolio_slug': user.portfolio_slug
            }
        })
        
    except Exception as e:
        import traceback
        logger.error(f"Auth token error: {e}")
        logger.error(f"Auth token traceback: {traceback.format_exc()}")
        return jsonify({'error': 'authentication_failed'}), 500


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
            'display_name': user.public_name,
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
    GET /api/mobile/top-influencers?industry=Technology&limit=20&hide_fractional=0
    Returns users ranked by subscriber count, optionally filtered by industry.

    Query params:
    - industry: filter by industry name (default: all)
    - limit: max entries (default 20, capped 50)
    - hide_fractional: 1/0 — Phase E: hide portfolios with any fractional
      share position. Default 0. NULL flags treated as "show" so users not
      yet processed by the daily cron remain visible during rollout.
    """
    from models import User, UserPortfolioStats, MobileSubscription
    
    industry = request.args.get('industry', 'all')
    limit = min(int(request.args.get('limit', 20)), 50)
    hide_fractional = request.args.get('hide_fractional', '0') == '1'
    
    try:
        # Build a combined subscriber count map from all sources:
        # 1. MobileSubscription (real subs)
        # 2. AdminSubscription (gifted subs)
        from models import AdminSubscription
        sub_totals = {}  # user_id -> total subscriber count
        
        try:
            real_counts = db.session.query(
                MobileSubscription.subscribed_to_id,
                db.func.count(MobileSubscription.id)
            ).filter_by(status='active').group_by(
                MobileSubscription.subscribed_to_id
            ).all()
            for uid, cnt in real_counts:
                sub_totals[uid] = sub_totals.get(uid, 0) + cnt
        except Exception:
            pass
        
        try:
            for asub in AdminSubscription.query.filter(AdminSubscription.bonus_subscriber_count > 0).all():
                sub_totals[asub.portfolio_user_id] = sub_totals.get(asub.portfolio_user_id, 0) + (asub.bonus_subscriber_count or 0)
        except Exception:
            pass
        
        # Filter to users with > 0 subs
        user_ids_with_subs = [uid for uid, cnt in sub_totals.items() if cnt > 0]
        if not user_ids_with_subs:
            return jsonify({'entries': [], 'available_industries': [], 'total': 0})
        
        # Load users and their stats
        users_map = {u.id: u for u in User.query.filter(User.id.in_(user_ids_with_subs)).all()}
        stats_map = {s.user_id: s for s in UserPortfolioStats.query.filter(
            UserPortfolioStats.user_id.in_(user_ids_with_subs)
        ).all()}
        
        # Build entries sorted by subscriber count
        raw_entries = []
        all_industries = set()
        for uid in user_ids_with_subs:
            user = users_map.get(uid)
            if not user:
                continue
            stats = stats_map.get(uid)
            industry_mix = (stats.industry_mix if stats and stats.industry_mix else {}) or {}

            # Hide-fractional filter (Phase E). Only hide when explicitly True;
            # None / missing stats row means "unknown — show", so users with
            # NULL flags survive until the cron has populated the column.
            if hide_fractional and stats is not None and stats.has_fractional_holdings is True:
                continue
            
            # Industry filter
            if industry and industry.lower() != 'all':
                matched = any(
                    industry.lower() in ind_name.lower() and pct >= 5
                    for ind_name, pct in industry_mix.items()
                )
                if not matched:
                    continue
            
            # Collect available industries
            for ind_name, pct in industry_mix.items():
                if pct >= 5:
                    all_industries.add(ind_name)
            
            top_industries = []
            if industry_mix:
                sorted_industries = sorted(industry_mix.items(), key=lambda x: x[1], reverse=True)
                top_industries = [
                    {'name': name, 'percent': round(pct, 1)}
                    for name, pct in sorted_industries[:3]
                ]
            
            raw_entries.append({
                'user': {
                    'id': user.id,
                    'username': user.username,
                    'display_name': user.public_name,
                    'portfolio_slug': user.portfolio_slug
                },
                'subscriber_count': sub_totals[uid],
                'unique_stocks': (stats.unique_stocks_count if stats else 0) or 0,
                'avg_trades_per_week': round((stats.avg_trades_per_week if stats else 0) or 0, 1),
                'top_industries': top_industries
            })
        
        # Sort by subscriber count desc, assign ranks, apply limit
        raw_entries.sort(key=lambda x: x['subscriber_count'], reverse=True)
        entries = []
        for i, entry in enumerate(raw_entries[:limit]):
            entry['rank'] = i + 1
            entries.append(entry)
        
        return jsonify({
            'entries': entries,
            'available_industries': sorted(list(all_industries)),
            'total': len(entries)
        })
        
    except Exception as e:
        logger.error(f"Top influencers error: {e}")
        return jsonify({'entries': [], 'available_industries': [], 'total': 0})


# =============================================================================
# Stock Price Lookup
# =============================================================================

@mobile_api.route('/stock/price/<ticker>', methods=['GET'])
@require_auth
@rate_limit(60)
def get_stock_price(ticker):
    """Get current stock price for a ticker via AlphaVantage (cached)."""
    ticker = ticker.upper().strip()
    if not ticker or len(ticker) > 10:
        return jsonify({'error': 'invalid_ticker'}), 400

    try:
        from portfolio_performance import PortfolioPerformanceCalculator
        calc = PortfolioPerformanceCalculator()
        data = calc.get_stock_data(ticker)
        if data and data.get('price'):
            return jsonify({
                'ticker': ticker,
                'price': round(float(data['price']), 2),
                'source': 'alphavantage'
            })
        return jsonify({'error': 'price_not_available', 'ticker': ticker}), 404
    except Exception as e:
        logger.error(f"Stock price lookup error for {ticker}: {e}")
        return jsonify({'error': str(e)}), 500


# =============================================================================
# Portfolio Performance / Chart Data
# =============================================================================

@mobile_api.route('/portfolio/<slug>/chart', methods=['GET'])
@require_auth
@rate_limit(60)
def get_portfolio_chart(slug):
    """
    Get portfolio performance chart data with S&P 500 overlay.
    
    Query params:
    - period: 1D, 1W, 1M, 3M, YTD, 1Y (default: 1W)
    
    Returns chart_data array with {date, portfolio, sp500} points.
    """
    from models import User, PortfolioSnapshot, MarketData
    
    period = request.args.get('period', '1W')
    # Map 1W -> 5D for backend compatibility, accept legacy 5D/7D too
    if period in ('1W', '7D'):
        period = '5D'
    valid_periods = ['1D', '5D', '1M', '3M', 'YTD', '1Y']
    if period not in valid_periods:
        return jsonify({'error': f'Invalid period. Must be one of: 1D, 1W, 1M, 3M, YTD, 1Y'}), 400
    
    try:
        # Find portfolio owner
        owner = User.query.filter_by(portfolio_slug=slug).first()
        if not owner:
            return jsonify({'error': 'portfolio_not_found'}), 404
        
        # Performance charts are publicly viewable (holdings are locked)
        # Try to use the unified performance calculator
        chart_data = []
        portfolio_return = 0.0
        sp500_return = 0.0
        
        try:
            from performance_calculator import calculate_portfolio_performance, get_period_dates, _sp500_benchmark_cache
            # Clear stale S&P cache from previous requests in same serverless instance
            _sp500_benchmark_cache.clear()
            
            start_date, end_date = get_period_dates(period, user_id=owner.id)
            result = calculate_portfolio_performance(
                owner.id, start_date, end_date,
                include_chart_data=True, period=period
            )
            if result and result.get('chart_data'):
                chart_data = result['chart_data']
                portfolio_return = result.get('portfolio_return', 0.0)
            
            # Compute PERIOD-LEVEL S&P 500 return (same as leaderboard header)
            # This uses the full period range, not the user's first snapshot date
            from models import MarketData
            from datetime import timedelta as td
            period_start, period_end = get_period_dates(period)  # No user_id = full period
            
            if period in ('1D', '5D'):
                sp_records = MarketData.query.filter(
                    MarketData.ticker == 'SPY_INTRADAY',
                    MarketData.date >= period_start,
                    MarketData.date <= period_end,
                    MarketData.timestamp.isnot(None)
                ).order_by(MarketData.timestamp.asc()).all()
                if not sp_records or len(sp_records) < 2:
                    sp_records = MarketData.query.filter(
                        MarketData.ticker == 'SPY_SP500',
                        MarketData.date >= period_start,
                        MarketData.date <= period_end
                    ).order_by(MarketData.date.asc()).all()
            else:
                sp_records = MarketData.query.filter(
                    MarketData.ticker == 'SPY_SP500',
                    MarketData.date >= period_start,
                    MarketData.date <= period_end
                ).order_by(MarketData.date.asc()).all()
            
            if sp_records and len(sp_records) >= 2:
                base_val = float(sp_records[0].close_price)
                end_val = float(sp_records[-1].close_price)
                if base_val > 0:
                    sp500_return = round(((end_val - base_val) / base_val) * 100, 2)
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
                    # Don't overwrite sp500_return — period-level value computed above
                    if sp500_return == 0.0:
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
        
        # Compute leaderboard eligibility for this period
        eligibility_info = {}
        try:
            from performance_calculator import get_leaderboard_eligibility
            elig = get_leaderboard_eligibility(owner.id, period)
            eligibility_info = {
                'leaderboard_eligible': elig['eligible'],
                'days_active': elig['days_active'],
                'days_required': elig['days_required'],
                'eligible_date': elig['eligible_date'].isoformat() if elig.get('eligible_date') else None,
                'first_activity_date': elig['first_activity_date'].isoformat() if elig.get('first_activity_date') else None
            }
        except Exception as e:
            logger.warning(f"Eligibility check failed for chart response: {e}")
            eligibility_info = {'leaderboard_eligible': True}  # Default to eligible on error
        
        return jsonify({
            'portfolio_return': round(portfolio_return, 2),
            'sp500_return': round(sp500_return, 2),
            'chart_data': chart_data,
            'period': period,
            **eligibility_info
        })
        
    except Exception as e:
        logger.error(f"Get portfolio chart error: {e}")
        return jsonify({
            'portfolio_return': 0,
            'sp500_return': 0,
            'chart_data': [],
            'period': period,
            'leaderboard_eligible': True  # Default on error
        })


# =============================================================================
# Feature Poll Endpoints
# =============================================================================

@mobile_api.route('/poll/active', methods=['GET'])
@require_auth
@rate_limit(30)
def get_active_poll():
    """Get the current active feature poll (if any) and whether user already voted."""
    import json as _json
    from models import FeaturePoll, FeaturePollVote
    from sqlalchemy import func

    try:
        poll = FeaturePoll.query.filter_by(active=True).order_by(FeaturePoll.created_at.desc()).first()
        if not poll:
            return jsonify({'poll': None})

        options = _json.loads(poll.options)

        # Check if user already voted
        user_vote = FeaturePollVote.query.filter_by(poll_id=poll.id, user_id=g.user_id).first()

        # Get vote counts per option
        vote_rows = db.session.query(
            FeaturePollVote.selected_option,
            func.count().label('cnt')
        ).filter_by(poll_id=poll.id).group_by(FeaturePollVote.selected_option).all()
        vote_counts = {r.selected_option: r.cnt for r in vote_rows}
        total_votes = sum(vote_counts.values())

        results = [{'option': o, 'votes': vote_counts.get(o, 0)} for o in options]

        return jsonify({
            'poll': {
                'id': poll.id,
                'question': poll.question,
                'options': options,
                'total_votes': total_votes,
                'results': results,
                'user_voted': user_vote.selected_option if user_vote else None,
            }
        })
    except Exception as e:
        logger.error(f"Get active poll error: {e}")
        return jsonify({'poll': None})


@mobile_api.route('/poll/vote', methods=['POST'])
@require_auth
@rate_limit(10)
def vote_on_poll():
    """Submit a vote on the active poll."""
    import json as _json
    from models import db, FeaturePoll, FeaturePollVote

    data = request.get_json()
    if not data:
        return jsonify({'error': 'missing_body'}), 400

    poll_id = data.get('poll_id')
    selected = data.get('selected_option')
    if not poll_id or not selected:
        return jsonify({'error': 'poll_id_and_selected_option_required'}), 400

    try:
        poll = FeaturePoll.query.get(poll_id)
        if not poll or not poll.active:
            return jsonify({'error': 'poll_not_found'}), 404

        options = _json.loads(poll.options)
        if selected not in options:
            return jsonify({'error': 'invalid_option'}), 400

        existing = FeaturePollVote.query.filter_by(poll_id=poll_id, user_id=g.user_id).first()
        if existing:
            existing.selected_option = selected
            existing.voted_at = datetime.utcnow()
        else:
            vote = FeaturePollVote(poll_id=poll_id, user_id=g.user_id, selected_option=selected)
            db.session.add(vote)

        db.session.commit()
        return jsonify({'success': True, 'selected_option': selected})

    except Exception as e:
        db.session.rollback()
        logger.error(f"Poll vote error: {e}")
        return jsonify({'error': 'vote_failed'}), 500


# =============================================================================
# Trade Endpoints (Buy / Sell)
# =============================================================================

@mobile_api.route('/portfolio/trade', methods=['POST'])
@require_auth
@rate_limit(20)
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
    if len(ticker) > 10:
        return jsonify({'error': 'invalid_ticker'}), 400
    if not quantity or quantity <= 0:
        return jsonify({'error': 'positive_quantity_required'}), 400
    if quantity > 1_000_000:
        return jsonify({'error': 'quantity_too_large', 'max': 1000000}), 400
    if trade_type not in ('buy', 'sell'):
        return jsonify({'error': 'type_must_be_buy_or_sell'}), 400
    
    try:
        from cash_tracking import process_transaction
        from timezone_utils import is_market_hours
        
        existing = Stock.query.filter_by(user_id=g.user_id, ticker=ticker).first()
        position_before_qty = existing.quantity if existing and trade_type == 'sell' else None
        
        # ── Market closed → queue as a PENDING trade ────────────────────────
        # A trade submitted outside regular hours must NOT land in Holdings at
        # a stale closing price (and must not be immediately re-sellable).
        # Instead we queue it; the existing /api/cron/market-open job settles
        # it at the next open price via process_queued_trades(). Cash-on-hand
        # ordering (cash_proceeds before new capital) is handled there too.
        if not is_market_hours():
            from models import QueuedEmailTrade, User
            from sqlalchemy import func as _func
            
            # Validate sells against shares actually held minus shares already
            # spoken for by other queued sells. A pending BUY never creates a
            # Stock row, so its shares are correctly NOT sellable until it
            # settles at open.
            if trade_type == 'sell':
                held = existing.quantity if existing else 0
                queued_sells = db.session.query(
                    _func.coalesce(_func.sum(QueuedEmailTrade.quantity), 0)
                ).filter(
                    QueuedEmailTrade.user_id == g.user_id,
                    QueuedEmailTrade.ticker == ticker,
                    QueuedEmailTrade.action == 'sell',
                    QueuedEmailTrade.status == 'queued',
                ).scalar() or 0
                available = held - queued_sells
                if available < quantity:
                    return jsonify({'error': 'insufficient_shares', 'available': available}), 400
            
            trader = User.query.get(g.user_id)
            queued = QueuedEmailTrade(
                user_id=g.user_id,
                user_email=(getattr(trader, 'email', None) or ''),
                ticker=ticker,
                action=trade_type,
                quantity=quantity,
                status='queued',
            )
            db.session.add(queued)
            db.session.commit()
            logger.info(f"Queued after-hours app trade: user={g.user_id} {trade_type} {quantity} {ticker}")
            return jsonify({
                'success': True,
                'pending': True,
                'message': 'Market closed — your trade is queued and will execute at the next market open.',
                'trade': {
                    'pending_id': queued.id,
                    'ticker': ticker,
                    'quantity': quantity,
                    'price': None,
                    'type': trade_type,
                    'status': 'pending',
                }
            })
        
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
        
        # Record transaction + update cash tracking (max_cash_deployed, cash_proceeds)
        process_transaction(
            db, g.user_id, ticker, quantity, price, trade_type,
            timestamp=datetime.utcnow(),
            position_before_qty=position_before_qty
        )
        
        db.session.commit()
        
        # Auto-populate stock metadata if missing (sector, market cap, etc.)
        if trade_type == 'buy':
            try:
                from models import StockInfo
                existing_info = StockInfo.query.filter_by(ticker=ticker).first()
                if not existing_info or not existing_info.sector:
                    from stock_metadata_utils import populate_stock_info
                    populate_stock_info(ticker)
                    logger.info(f"Auto-populated stock metadata for {ticker}")
            except Exception as meta_err:
                logger.warning(f"Non-blocking: failed to auto-populate metadata for {ticker}: {meta_err}")
        
        # Subscriber push + email notifications are fired by
        # process_transaction's internal fan-out above (cash_tracking.py).
        # We used to fan out again here which caused duplicate notifications
        # per trade (one with position_pct, one without). The single source
        # of truth is now process_transaction, which receives position_before_qty.
        
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


@mobile_api.route('/portfolio/pending-trades/<int:pending_id>', methods=['DELETE'])
@require_auth
@rate_limit(20)
def cancel_pending_trade(pending_id):
    """Cancel a queued (pending, not-yet-executed) after-hours trade.

    Only the owner of the queued trade may cancel it, and only while it is
    still 'queued' (before the market-open cron settles it).
    """
    from models import db, QueuedEmailTrade
    
    qt = QueuedEmailTrade.query.get(pending_id)
    if not qt or qt.user_id != g.user_id:
        return jsonify({'error': 'not_found'}), 404
    if qt.status != 'queued':
        return jsonify({'error': 'not_cancellable', 'status': qt.status}), 400
    
    qt.status = 'cancelled'
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logger.error(f"Cancel pending trade failed: {e}")
        return jsonify({'error': 'cancel_failed'}), 500
    
    return jsonify({'success': True, 'cancelled_id': pending_id})


# =============================================================================
# Admin Bot Backdoor API
# =============================================================================

def _is_admin_session():
    """Check if the current Flask session belongs to the admin user AND has passed 2FA."""
    from flask import session as flask_session
    admin_email = os.environ.get('ADMIN_EMAIL', 'admin@apestogether.ai')
    session_email = flask_session.get('email', '')
    has_2fa = flask_session.get('admin_2fa_verified', False)
    return session_email == admin_email and has_2fa


def require_cron_secret(f):
    """Decorator for automation-called endpoints (GitHub Actions, Google Apps Script).
    Accepts either:
      - X-Cron-Secret header (for automated callers — separate from admin API key)
      - Valid admin session with 2FA (for manual triggering from admin panel)
    Does NOT accept X-Admin-Key alone — that's intentional to isolate cron auth."""
    @wraps(f)
    def decorated(*args, **kwargs):
        # Path 1: Cron secret (for automated systems)
        cron_secret = request.headers.get('X-Cron-Secret')
        expected = os.environ.get('CRON_SECRET')
        if cron_secret and expected and cron_secret == expected:
            return f(*args, **kwargs)
        
        # Path 2: Admin session with 2FA (for manual triggering)
        if _is_admin_session():
            return f(*args, **kwargs)
        
        if not expected:
            return jsonify({'error': 'cron_secret_not_configured'}), 503
        return jsonify({'error': 'invalid_cron_secret'}), 403
    decorated.__name__ = f.__name__
    return decorated


def require_admin_or_cron(f):
    """Decorator for endpoints used BOTH by admin panel (2FA) and by automated pipelines (cron secret).
    Accepts either:
      - X-Cron-Secret header (automation)
      - X-Admin-Key + X-Admin-OTP headers (manual API call with 2FA)
      - Valid admin session with 2FA (admin panel browser)"""
    @wraps(f)
    def decorated(*args, **kwargs):
        # Path 1: Cron secret
        cron_secret = request.headers.get('X-Cron-Secret')
        expected_cron = os.environ.get('CRON_SECRET')
        if cron_secret and expected_cron and cron_secret == expected_cron:
            return f(*args, **kwargs)
        
        # Path 2: Admin session with 2FA
        if _is_admin_session():
            return f(*args, **kwargs)
        
        # Path 3: API key + OTP
        admin_key = request.headers.get('X-Admin-Key')
        expected_key = os.environ.get('ADMIN_API_KEY')
        if admin_key and expected_key and admin_key == expected_key:
            totp_secret = os.environ.get('ADMIN_TOTP_SECRET')
            if totp_secret:
                otp_code = request.headers.get('X-Admin-OTP')
                if otp_code and _verify_totp(otp_code):
                    return f(*args, **kwargs)
                return jsonify({'error': '2fa_required', 'message': 'X-Admin-OTP header required'}), 401
            # No TOTP configured — allow key-only with warning
            logger.warning(f"2FA not configured — allowing key-only access to {f.__name__}")
            return f(*args, **kwargs)
        
        return jsonify({'error': 'unauthorized'}), 403
    decorated.__name__ = f.__name__
    return decorated


def require_admin_key(f):
    """DEPRECATED — all callers should use require_admin_2fa, require_cron_secret, or require_admin_or_cron.
    Kept temporarily in case any code references it."""
    @wraps(f)
    def decorated(*args, **kwargs):
        # Path 1: API key auth (for bot scripts, cron jobs)
        admin_key = request.headers.get('X-Admin-Key')
        expected_key = os.environ.get('ADMIN_API_KEY')
        
        if admin_key and expected_key and admin_key == expected_key:
            return f(*args, **kwargs)
        
        # Path 2: Flask session auth (for admin dashboard SPA)
        if _is_admin_session():
            return f(*args, **kwargs)
        
        # Neither auth method succeeded
        if not expected_key:
            return jsonify({'error': 'admin_api_not_configured'}), 503
        
        return jsonify({'error': 'invalid_admin_key'}), 403
    return decorated


def _verify_totp(otp_code):
    """Verify a TOTP code against the admin secret. Returns True if valid."""
    import hmac
    import hashlib
    import struct
    import base64
    import time as _time
    
    totp_secret = os.environ.get('ADMIN_TOTP_SECRET')
    if not totp_secret:
        return False
    
    # Decode base32 secret
    try:
        key = base64.b32decode(totp_secret.upper().replace(' ', ''), casefold=True)
    except Exception:
        return False
    
    # Check current and adjacent 30-second windows (allows 30s clock skew)
    now = int(_time.time())
    for offset in [-1, 0, 1]:
        counter = (now // 30) + offset
        msg = struct.pack('>Q', counter)
        h = hmac.new(key, msg, hashlib.sha1).digest()
        o = h[-1] & 0x0F
        code = struct.unpack('>I', h[o:o+4])[0] & 0x7FFFFFFF
        code = code % 1_000_000
        if str(code).zfill(6) == str(otp_code).zfill(6):
            return True
    return False


def require_admin_2fa(f):
    """Decorator requiring admin identity + TOTP for sensitive endpoints.
    
    Accepts either:
      - X-Admin-Key header (for bot scripts) + X-Admin-OTP header
      - Valid admin Flask session that already passed 2FA gate (for dashboard)
    
    Session-based admins already verified 2FA to enter the admin panel
    (admin_2fa_verified flag in session), so we trust that flag and do NOT
    demand a fresh OTP on every API call from the SPA.
    
    If ADMIN_TOTP_SECRET is not set, falls back to identity-only auth with a warning.
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        # Check identity via API key OR session
        admin_key = request.headers.get('X-Admin-Key')
        expected_key = os.environ.get('ADMIN_API_KEY')
        
        has_key_auth = admin_key and expected_key and admin_key == expected_key
        has_session_auth = _is_admin_session()  # Checks email == ADMIN_EMAIL AND admin_2fa_verified == True
        
        if not has_key_auth and not has_session_auth:
            return jsonify({'error': 'invalid_admin_key'}), 403
        
        # For session auth: 2FA was already verified at login gate (admin_2fa_verified in session)
        # No need for per-request OTP — the session IS the proof of 2FA.
        if has_session_auth:
            return f(*args, **kwargs)
        
        # For API key auth (bot scripts, cron): require per-request OTP
        totp_secret = os.environ.get('ADMIN_TOTP_SECRET')
        if totp_secret:
            otp_code = request.headers.get('X-Admin-OTP')
            if not otp_code:
                return jsonify({'error': '2fa_required', 'message': 'X-Admin-OTP header required'}), 401
            if not _verify_totp(otp_code):
                return jsonify({'error': 'invalid_otp', 'message': 'Invalid or expired TOTP code'}), 403
        else:
            logger.warning(f"2FA not configured (ADMIN_TOTP_SECRET missing) — allowing identity-only access to {f.__name__}")
        
        return f(*args, **kwargs)
    return decorated


@mobile_api.route('/admin/bot/create-user', methods=['POST'])
@require_admin_or_cron
@with_db_retry
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
@require_admin_or_cron
@with_db_retry
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
        from cash_tracking import process_transaction
        
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
                total_cost = (existing.purchase_price * existing.quantity) + (price * quantity)
                existing.quantity += quantity
                existing.purchase_price = total_cost / existing.quantity if existing.quantity > 0 else price
            else:
                stock = Stock(
                    ticker=ticker,
                    quantity=quantity,
                    purchase_price=price,
                    user_id=user_id
                )
                db.session.add(stock)
            
            # Track cash deployed for this initial buy
            process_transaction(
                db, user_id, ticker, quantity, price, 'initial',
                timestamp=datetime.utcnow()
            )
            added += 1
        
        db.session.commit()
        return jsonify({
            'success': True,
            'added_count': added,
            'max_cash_deployed': float(user.max_cash_deployed or 0),
            'cash_proceeds': float(user.cash_proceeds or 0)
        })
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Bot add stocks error: {e}")
        return jsonify({'error': 'add_stocks_failed'}), 500


@mobile_api.route('/admin/bot/set-cash', methods=['POST'])
@require_admin_or_cron
@with_db_retry
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


@mobile_api.route('/admin/poll/list', methods=['GET'])
@require_admin_or_cron
@with_db_retry
def list_polls():
    """List all polls with vote counts."""
    import json as _json
    from models import FeaturePoll, FeaturePollVote
    from sqlalchemy import func

    try:
        polls = FeaturePoll.query.order_by(FeaturePoll.created_at.desc()).all()

        # Get vote counts per poll
        vote_counts = {}
        rows = db.session.query(
            FeaturePollVote.poll_id,
            FeaturePollVote.selected_option,
            func.count().label('cnt')
        ).group_by(FeaturePollVote.poll_id, FeaturePollVote.selected_option).all()
        for r in rows:
            if r.poll_id not in vote_counts:
                vote_counts[r.poll_id] = {}
            vote_counts[r.poll_id][r.selected_option] = r.cnt

        result = []
        for p in polls:
            options = _json.loads(p.options)
            vc = vote_counts.get(p.id, {})
            total = sum(vc.values())
            results = [{'option': o, 'votes': vc.get(o, 0)} for o in options]
            result.append({
                'id': p.id,
                'question': p.question,
                'options': options,
                'active': p.active,
                'created_at': p.created_at.isoformat() if p.created_at else None,
                'total_votes': total,
                'results': results,
            })
        return jsonify({'polls': result})
    except Exception as e:
        logger.error(f"List polls error: {e}")
        return jsonify({'error': 'list_failed'}), 500


@mobile_api.route('/admin/poll/toggle', methods=['POST'])
@require_admin_2fa
@with_db_retry
def toggle_poll():
    """Activate or deactivate a poll. Activating one deactivates all others."""
    from models import db, FeaturePoll

    data = request.get_json()
    if not data:
        return jsonify({'error': 'missing_body'}), 400

    poll_id = data.get('poll_id')
    active = data.get('active')
    if poll_id is None or active is None:
        return jsonify({'error': 'poll_id_and_active_required'}), 400

    try:
        poll = FeaturePoll.query.get(poll_id)
        if not poll:
            return jsonify({'error': 'poll_not_found'}), 404

        if active:
            # Deactivate all others first
            FeaturePoll.query.filter(FeaturePoll.id != poll_id).filter_by(active=True).update({'active': False})
        poll.active = active
        db.session.commit()
        return jsonify({'success': True, 'poll_id': poll.id, 'active': poll.active})
    except Exception as e:
        db.session.rollback()
        logger.error(f"Toggle poll error: {e}")
        return jsonify({'error': 'toggle_failed'}), 500


@mobile_api.route('/admin/poll/create', methods=['POST'])
@require_admin_2fa
@with_db_retry
def create_poll():
    """Create a new feature poll (deactivates any existing active poll)."""
    import json as _json
    from models import db, FeaturePoll

    data = request.get_json()
    if not data:
        return jsonify({'error': 'missing_body'}), 400

    question = data.get('question')
    options = data.get('options')
    if not question or not options or len(options) < 2:
        return jsonify({'error': 'question_and_at_least_2_options_required'}), 400

    try:
        # Deactivate existing polls
        FeaturePoll.query.filter_by(active=True).update({'active': False})

        poll = FeaturePoll(
            question=question,
            options=_json.dumps(options),
            active=True,
        )
        db.session.add(poll)
        db.session.commit()
        return jsonify({'success': True, 'poll_id': poll.id})
    except Exception as e:
        db.session.rollback()
        logger.error(f"Create poll error: {e}")
        return jsonify({'error': 'create_failed'}), 500


@mobile_api.route('/admin/bot/scale-holdings', methods=['POST'])
@require_admin_2fa
@with_db_retry
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
@require_admin_2fa
@with_db_retry
def bot_subscribe():
    """
    Create a subscription from one user to another.
    
    Request body:
    {
        "subscriber_id": 123,
        "subscribed_to_id": 456
    }
    """
    from models import db, MobileSubscription, InAppPurchase
    
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
        now = datetime.utcnow()
        # MobileSubscription.in_app_purchase_id is NOT NULL and there is no
        # `platform` column on MobileSubscription (that lives on InAppPurchase).
        # Admin/bot-created subscriptions have no real store purchase, so create a
        # $0 placeholder IAP flagged platform='admin' (price/payout/fees all 0 so it
        # stays out of revenue/Xero) and link the subscription to it.
        iap = InAppPurchase(
            subscriber_id=subscriber_id,
            subscribed_to_id=subscribed_to_id,
            platform='admin',
            product_id='admin.bot.subscription',
            transaction_id=f'admin-bot-{subscriber_id}-{subscribed_to_id}-{int(now.timestamp())}',
            status='active',
            purchase_date=now,
            expires_date=now + timedelta(days=365),
            price=0.0,
            influencer_payout=0.0,
            platform_revenue=0.0,
            store_fee=0.0,
        )
        db.session.add(iap)
        db.session.flush()  # assigns iap.id

        sub = MobileSubscription(
            subscriber_id=subscriber_id,
            subscribed_to_id=subscribed_to_id,
            in_app_purchase_id=iap.id,
            status='active',
            expires_at=now + timedelta(days=365),
            push_notifications_enabled=False
        )
        db.session.add(sub)
        db.session.commit()
        
        return jsonify({'success': True, 'subscription_id': sub.id, 'in_app_purchase_id': iap.id})
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Bot subscribe error: {e}")
        return jsonify({'error': 'subscribe_failed'}), 500


@mobile_api.route('/admin/bot/execute-trade', methods=['POST'])
@require_cron_secret
@rate_limit(30)
@with_db_retry
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
    # `price_source` is set by bot_executor with values like 'bot_rsi',
    # 'bot_news', 'bot_insider', 'bot_stoploss', 'bot_takeprofit', 'bot_fomo'
    # so the admin Recent Trades 'Source' column can show what drove the trade.
    # Defaults to 'bot_research' if the caller omits it. Truncated to 20 chars
    # to fit Transaction.price_source's column width.
    raw_source = (data.get('price_source') or '').strip() or 'bot_research'
    price_source = raw_source[:20]
    
    if not user_id or not ticker or quantity <= 0:
        return jsonify({'error': 'user_id_ticker_quantity_required'}), 400
    if trade_type not in ('buy', 'sell'):
        return jsonify({'error': 'type_must_be_buy_or_sell'}), 400
    
    try:
        from cash_tracking import process_transaction
        
        existing = Stock.query.filter_by(user_id=user_id, ticker=ticker).first()
        position_before_qty = existing.quantity if existing and trade_type == 'sell' else None
        
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
        
        # Record transaction + update cash tracking (max_cash_deployed, cash_proceeds)
        process_transaction(
            db, user_id, ticker, quantity, price, trade_type,
            timestamp=datetime.utcnow(),
            position_before_qty=position_before_qty,
            price_source=price_source
        )
        
        db.session.commit()
        
        # Auto-populate stock metadata if missing (sector, market cap, etc.)
        if trade_type == 'buy':
            try:
                from models import StockInfo
                existing_info = StockInfo.query.filter_by(ticker=ticker).first()
                if not existing_info or not existing_info.sector:
                    from stock_metadata_utils import populate_stock_info
                    populate_stock_info(ticker)
            except Exception as meta_err:
                logger.warning(f"Non-blocking: failed to auto-populate metadata for {ticker}: {meta_err}")
        
        return jsonify({'success': True})
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Bot trade error: {e}")
        return jsonify({'error': 'trade_failed'}), 500


def _bot_profile_meta(user_id):
    """Read (strategy, industry) from the committed .bot_profiles/<id>.json.

    That file is the source of truth for the live trade runner (GitHub Actions
    loads it each wave); the DB's User.extra_data is frequently empty for bots,
    which is why the admin Bot Management 'Strategy' column was showing '—' for
    every bot. Resolves the path the same way bot_agent.PROFILE_DIR does so it
    works both locally and on Vercel (the dir is committed, not gitignored).
    """
    try:
        import os as _os, json as _json
        path = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)),
                             '.bot_profiles', f'{user_id}.json')
        if _os.path.exists(path):
            with open(path) as f:
                p = _json.load(f)
            return p.get('strategy'), p.get('industry')
    except Exception:
        pass
    return None, None


@mobile_api.route('/admin/bot/list-users', methods=['GET'])
@require_admin_or_cron
@with_db_retry
def bot_list_users():
    """List all users with their portfolio info, filterable by role"""
    from models import db, User
    
    try:
        role_filter = request.args.get('role')  # 'agent', 'user', or None for all
        
        # Simple query — no joins, no subqueries
        query = User.query
        if role_filter:
            query = query.filter(User.role == role_filter)
        
        users = query.order_by(User.created_at.desc()).all()
        
        # Batch-fetch stock and trade counts in simple separate queries
        stock_counts = {}
        trade_counts = {}
        real_sub_counts = {}
        gifted_sub_counts = {}
        try:
            from models import Stock
            from sqlalchemy import func
            for uid, cnt in db.session.query(Stock.user_id, func.count(Stock.id)).group_by(Stock.user_id).all():
                stock_counts[uid] = cnt
        except Exception:
            pass
        try:
            from models import Transaction
            from sqlalchemy import func
            for uid, cnt in db.session.query(Transaction.user_id, func.count(Transaction.id)).group_by(Transaction.user_id).all():
                trade_counts[uid] = cnt
        except Exception:
            pass
        try:
            from models import MobileSubscription
            from sqlalchemy import func
            for uid, cnt in db.session.query(MobileSubscription.subscribed_to_id, func.count(MobileSubscription.id)).filter(MobileSubscription.status == 'active').group_by(MobileSubscription.subscribed_to_id).all():
                real_sub_counts[uid] = cnt
        except Exception:
            pass
        try:
            from models import AdminSubscription
            for asub in AdminSubscription.query.all():
                bonus = asub.bonus_subscriber_count or 0
                if bonus > 0:
                    gifted_sub_counts[asub.portfolio_user_id] = bonus
        except Exception:
            pass
        
        user_list = []
        for u in users:
            extra = u.extra_data or {}
            industry = extra.get('industry', 'General')
            bot_active = extra.get('bot_active', True) if u.role == 'agent' else None
            strategy = extra.get('trading_style', extra.get('strategy_name', None))
            # Bots store their real strategy/industry in the committed profile
            # file, not the DB extra_data (usually empty) — fall back to it so
            # the admin 'Strategy' column stops showing '—' for every bot.
            if u.role == 'agent' and (not strategy or industry == 'General'):
                p_strat, p_ind = _bot_profile_meta(u.id)
                if not strategy and p_strat:
                    strategy = p_strat
                if industry == 'General' and p_ind:
                    industry = p_ind
            
            # Surface copytrade_bot flag so callers (bot_executor's
            # get_active_bots → cmd_trade wave) can exclude bots that
            # only trade via the Public.com email pipeline. The source
            # of truth is _is_copytrade_bot() defined below in this
            # module (username allowlist + extra_data.copytrade_bot).
            # Without this, CoastHillBear / marblethehill72 were
            # making real autonomous bot-wave trades (e.g. wave 4 on
            # 2026-05-20 16:15 ET — marblethehill72 sold 1 LMT).
            copytrade_bot = _is_copytrade_bot(u) if u.role == 'agent' else False

            user_list.append({
                'id': u.id,
                'username': u.username,
                'email': u.email,
                'portfolio_slug': getattr(u, 'portfolio_slug', None),
                'role': u.role or 'user',
                'created_by': getattr(u, 'created_by', 'human') or 'human',
                'created_at': u.created_at.isoformat() if u.created_at else None,
                'industry': industry,
                'strategy': strategy,
                'bot_active': bot_active,
                'copytrade_bot': copytrade_bot,
                'stock_count': stock_counts.get(u.id, 0),
                'trade_count': trade_counts.get(u.id, 0),
                'real_subscribers': real_sub_counts.get(u.id, 0),
                'gifted_subscribers': gifted_sub_counts.get(u.id, 0),
                'subscriber_count': real_sub_counts.get(u.id, 0) + gifted_sub_counts.get(u.id, 0)
            })
        return jsonify({'users': user_list, 'total': len(user_list)})
    except Exception as e:
        logger.error(f"Bot list users error: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return jsonify({'error': 'list_failed', 'detail': str(e)}), 500


@mobile_api.route('/admin/user/<int:user_id>', methods=['GET'])
@require_admin_2fa
@with_db_retry
def admin_user_detail(user_id):
    """Get a single user's portfolio holdings and recent transactions."""
    from models import db, User, Stock, Transaction
    
    user = User.query.get(user_id)
    if not user:
        return jsonify({'error': 'user_not_found'}), 404
    
    stocks = Stock.query.filter_by(user_id=user.id).all()
    transactions = Transaction.query.filter_by(user_id=user.id).order_by(
        Transaction.timestamp.desc()
    ).limit(50).all()
    
    extra = user.extra_data or {}
    
    # Subscriber counts (real vs gifted)
    from models import Subscription, MobileSubscription
    real_subs = 0
    gifted_subs = 0
    try:
        real_subs += Subscription.query.filter_by(subscribed_to_id=user.id, status='active').count()
    except Exception:
        pass
    try:
        real_subs += MobileSubscription.query.filter_by(subscribed_to_id=user.id, status='active').count()
    except Exception:
        pass
    try:
        from models import AdminSubscription
        admin_sub = AdminSubscription.query.filter_by(portfolio_user_id=user.id).first()
        if admin_sub:
            gifted_subs = admin_sub.bonus_subscriber_count or 0
    except Exception:
        pass
    
    return jsonify({
        'user': {
            'id': user.id,
            'username': user.username,
            'email': user.email,
            'role': user.role or 'user',
            'created_at': user.created_at.isoformat() if user.created_at else None,
            'bot_active': extra.get('bot_active', True) if user.role == 'agent' else None,
            'strategy': extra.get('trading_style', extra.get('strategy_name', None)),
            'industry': extra.get('industry', 'General'),
            'subscriber_count': real_subs + gifted_subs,
            'real_subscribers': real_subs,
            'gifted_subscribers': gifted_subs,
        },
        'holdings': [{
            'ticker': s.ticker,
            'quantity': s.quantity,
            'purchase_price': s.purchase_price,
        } for s in stocks if s.quantity > 0],
        'transactions': [{
            'id': t.id,
            'ticker': t.ticker,
            'quantity': t.quantity,
            'price': t.price,
            'transaction_type': t.transaction_type,
            'timestamp': t.timestamp.isoformat() if t.timestamp else None,
            'notes': getattr(t, 'notes', None),
        } for t in transactions],
    })


@mobile_api.route('/admin/bot/dashboard', methods=['GET'])
@require_admin_or_cron
@with_db_retry
def bot_dashboard():
    """Get summary stats for the admin dashboard"""
    from models import db, User, Stock, Transaction
    from sqlalchemy import func
    
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
        
        # These tables may not exist yet — query safely
        real_subscriptions = 0
        gifted_subs = 0
        try:
            from models import MobileSubscription
            real_subscriptions = MobileSubscription.query.filter_by(status='active').count()
        except Exception:
            pass
        try:
            from models import AdminSubscription
            gifted_subs = db.session.query(
                func.coalesce(func.sum(AdminSubscription.bonus_subscriber_count), 0)
            ).scalar() or 0
        except Exception:
            pass
        
        return jsonify({
            'total_users': total_users,
            'human_users': human_users,
            'bot_users': bot_users,
            'active_bots': active_bots,
            'inactive_bots': inactive_bots,
            'industry_breakdown': industry_counts,
            'total_stocks': total_stocks,
            'total_trades': total_trades,
            'real_subscriptions': real_subscriptions,
            'gifted_subscriptions': gifted_subs,
            'total_subscriptions': real_subscriptions + gifted_subs
        })
    except Exception as e:
        logger.error(f"Bot dashboard error: {e}")
        return jsonify({'error': 'dashboard_failed'}), 500


@mobile_api.route('/admin/platform-growth', methods=['GET'])
@require_admin_2fa
@with_db_retry
def platform_growth():
    """Unified daily time series for all platform growth metrics."""
    from models import db, User, Subscription, Transaction
    from sqlalchemy import func, cast, Date, case
    from collections import defaultdict

    try:
        daily = defaultdict(lambda: {
            'signups': 0, 'real_signups': 0, 'bot_signups': 0,
            'trades': 0, 'active_traders': 0,
            'page_views': 0, 'unique_visitors': 0,
            'portfolio_clicks': 0,
            'apple_clicks': 0, 'android_clicks': 0,
        })

        # ── Signups by day ──
        for row in db.session.query(
            cast(User.created_at, Date).label('day'),
            func.count().label('total'),
            func.sum(case((User.created_by == 'system', 1), else_=0)).label('bots'),
            func.sum(case((User.created_by != 'system', 1), else_=0)).label('humans'),
        ).filter(User.created_at.isnot(None))\
         .group_by(cast(User.created_at, Date)).all():
            d = str(row.day)
            daily[d]['signups'] = row.total
            daily[d]['real_signups'] = int(row.humans or 0)
            daily[d]['bot_signups'] = int(row.bots or 0)

        # ── Trades + active traders by day ──
        for row in db.session.query(
            cast(Transaction.timestamp, Date).label('day'),
            func.count().label('count'),
            func.count(func.distinct(Transaction.user_id)).label('traders'),
        ).filter(Transaction.timestamp.isnot(None))\
         .group_by(cast(Transaction.timestamp, Date)).all():
            d = str(row.day)
            daily[d]['trades'] = row.count
            daily[d]['active_traders'] = row.traders

        # ── Page views (landing = page '/') + unique visitors ──
        try:
            from models import PageView
            for row in db.session.query(
                cast(PageView.created_at, Date).label('day'),
                func.count().label('views'),
                func.count(func.distinct(PageView.ip_hash)).label('unique'),
            ).filter(PageView.page == '/')\
             .group_by(cast(PageView.created_at, Date)).all():
                d = str(row.day)
                daily[d]['page_views'] = row.views
                daily[d]['unique_visitors'] = row.unique
        except Exception:
            pass

        # ── Shared portfolio link clicks (page starts with '/p/') ──
        try:
            from models import PageView as PV2
            for row in db.session.query(
                cast(PV2.created_at, Date).label('day'),
                func.count().label('clicks'),
            ).filter(PV2.page.like('/p/%'))\
             .group_by(cast(PV2.created_at, Date)).all():
                daily[str(row.day)]['portfolio_clicks'] = row.clicks
        except Exception:
            pass

        # ── App store link clicks by platform ──
        try:
            from models import LinkClick
            for row in db.session.query(
                cast(LinkClick.created_at, Date).label('day'),
                func.sum(case((LinkClick.platform == 'apple', 1), else_=0)).label('apple'),
                func.sum(case((LinkClick.platform == 'android', 1), else_=0)).label('android'),
            ).group_by(cast(LinkClick.created_at, Date)).all():
                d = str(row.day)
                daily[d]['apple_clicks'] = int(row.apple or 0)
                daily[d]['android_clicks'] = int(row.android or 0)
        except Exception:
            pass

        # ── Build continuous daily series (fill gaps with zeros) ──
        # Always cover at least 1 year back so every time range filter works
        if True:
            today = datetime.utcnow().date()
            one_year_ago = today - timedelta(days=365)
            earliest_data = min(daily.keys()) if daily else str(today)
            start_str = min(earliest_data, str(one_year_ago))
            series = []
            current = datetime.strptime(start_str, '%Y-%m-%d').date()
            end = today
            zero_row = {
                'signups': 0, 'real_signups': 0, 'bot_signups': 0,
                'trades': 0, 'active_traders': 0,
                'page_views': 0, 'unique_visitors': 0,
                'portfolio_clicks': 0,
                'apple_clicks': 0, 'android_clicks': 0,
            }
            while current <= end:
                d = str(current)
                entry = daily.get(d, zero_row).copy()
                entry['date'] = d
                series.append(entry)
                current += timedelta(days=1)

        return jsonify({'series': series})
    except Exception as e:
        logger.error(f"Platform growth error: {e}")
        return jsonify({'error': str(e)}), 500


@mobile_api.route('/admin/alphavantage/usage', methods=['GET'])
@require_admin_2fa
@with_db_retry
def alphavantage_usage():
    """Get AlphaVantage API usage stats for the admin dashboard.
    Premium tier ($99.99/mo): 150 req/min, no daily limit."""
    from models import db, AlphaVantageAPILog
    from sqlalchemy import func

    try:
        now = datetime.utcnow()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        one_min_ago = now - timedelta(minutes=1)
        one_hour_ago = now - timedelta(hours=1)
        seven_days_ago = now - timedelta(days=7)

        # Calls in the last minute (vs 75/min cap)
        last_min = AlphaVantageAPILog.query.filter(
            AlphaVantageAPILog.timestamp >= one_min_ago
        ).count()

        # Calls today
        today_total = AlphaVantageAPILog.query.filter(
            AlphaVantageAPILog.timestamp >= today_start
        ).count()
        today_success = AlphaVantageAPILog.query.filter(
            AlphaVantageAPILog.timestamp >= today_start,
            AlphaVantageAPILog.response_status == 'success'
        ).count()
        today_errors = AlphaVantageAPILog.query.filter(
            AlphaVantageAPILog.timestamp >= today_start,
            AlphaVantageAPILog.response_status != 'success'
        ).count()

        # Calls in the last hour
        last_hour = AlphaVantageAPILog.query.filter(
            AlphaVantageAPILog.timestamp >= one_hour_ago
        ).count()

        # Peak requests per minute over last 7 days
        # Group by truncated-to-minute timestamp, find the max count
        from sqlalchemy import cast, Date, text as sa_text
        peak_rows = db.session.query(
            cast(AlphaVantageAPILog.timestamp, Date).label('day'),
            func.count().label('calls_in_min'),
        ).filter(
            AlphaVantageAPILog.timestamp >= seven_days_ago
        ).group_by(
            func.date_trunc('minute', AlphaVantageAPILog.timestamp)
        ).order_by(func.count().desc()).limit(20).all()

        # Build peak-per-day from the grouped results
        peak_by_day = {}
        for r in peak_rows:
            day_str = str(r.day)
            if day_str not in peak_by_day or r.calls_in_min > peak_by_day[day_str]:
                peak_by_day[day_str] = r.calls_in_min
        overall_peak = max((r.calls_in_min for r in peak_rows), default=0)

        # Daily breakdown for last 7 days
        daily_rows = db.session.query(
            func.date(AlphaVantageAPILog.timestamp).label('day'),
            func.count().label('total'),
            func.sum(db.case(
                (AlphaVantageAPILog.response_status == 'success', 1),
                else_=0
            )).label('success'),
        ).filter(
            AlphaVantageAPILog.timestamp >= seven_days_ago
        ).group_by(func.date(AlphaVantageAPILog.timestamp)).order_by(
            func.date(AlphaVantageAPILog.timestamp).desc()
        ).all()

        daily = [{'date': str(r.day), 'total': r.total, 'success': int(r.success or 0), 'peak_per_min': peak_by_day.get(str(r.day), 0)} for r in daily_rows]

        # Top endpoints today
        endpoint_rows = db.session.query(
            AlphaVantageAPILog.endpoint,
            func.count().label('count')
        ).filter(
            AlphaVantageAPILog.timestamp >= today_start
        ).group_by(AlphaVantageAPILog.endpoint).order_by(func.count().desc()).limit(10).all()

        endpoints = [{'endpoint': r.endpoint, 'count': r.count} for r in endpoint_rows]

        # Top tickers today
        ticker_rows = db.session.query(
            AlphaVantageAPILog.symbol,
            func.count().label('count')
        ).filter(
            AlphaVantageAPILog.timestamp >= today_start,
            AlphaVantageAPILog.symbol.isnot(None)
        ).group_by(AlphaVantageAPILog.symbol).order_by(func.count().desc()).limit(15).all()

        tickers = [{'symbol': r.symbol, 'count': r.count} for r in ticker_rows]

        # ── Latency metrics (response_time_ms) ──────────────────────────
        # Today's avg/p95 for calls that have response_time_ms logged
        latency_today = db.session.query(
            func.avg(AlphaVantageAPILog.response_time_ms).label('avg_ms'),
            func.max(AlphaVantageAPILog.response_time_ms).label('max_ms'),
            func.min(AlphaVantageAPILog.response_time_ms).label('min_ms'),
            func.count(AlphaVantageAPILog.response_time_ms).label('measured'),
        ).filter(
            AlphaVantageAPILog.timestamp >= today_start,
            AlphaVantageAPILog.response_time_ms.isnot(None)
        ).first()

        # P95 approximation: get the 95th percentile value
        measured_count = int(latency_today.measured or 0)
        p95_ms = None
        if measured_count > 0:
            p95_offset = max(int(measured_count * 0.95) - 1, 0)
            p95_row = db.session.query(
                AlphaVantageAPILog.response_time_ms
            ).filter(
                AlphaVantageAPILog.timestamp >= today_start,
                AlphaVantageAPILog.response_time_ms.isnot(None)
            ).order_by(AlphaVantageAPILog.response_time_ms.asc()).offset(p95_offset).limit(1).first()
            p95_ms = p95_row[0] if p95_row else None

        # Per-endpoint latency breakdown (today)
        endpoint_latency_rows = db.session.query(
            AlphaVantageAPILog.endpoint,
            func.avg(AlphaVantageAPILog.response_time_ms).label('avg_ms'),
            func.count().label('total'),
            func.sum(db.case(
                (AlphaVantageAPILog.response_status != 'success', 1),
                else_=0
            )).label('errors'),
        ).filter(
            AlphaVantageAPILog.timestamp >= today_start,
            AlphaVantageAPILog.response_time_ms.isnot(None)
        ).group_by(AlphaVantageAPILog.endpoint).all()

        endpoint_latency = [{
            'endpoint': r.endpoint,
            'avg_ms': round(float(r.avg_ms), 1) if r.avg_ms else None,
            'total': r.total,
            'errors': int(r.errors or 0),
            'error_rate': round((int(r.errors or 0) / r.total) * 100, 1) if r.total > 0 else 0,
        } for r in endpoint_latency_rows]

        # 7-day latency trend (daily avg response time)
        daily_latency_rows = db.session.query(
            func.date(AlphaVantageAPILog.timestamp).label('day'),
            func.avg(AlphaVantageAPILog.response_time_ms).label('avg_ms'),
        ).filter(
            AlphaVantageAPILog.timestamp >= seven_days_ago,
            AlphaVantageAPILog.response_time_ms.isnot(None)
        ).group_by(func.date(AlphaVantageAPILog.timestamp)).order_by(
            func.date(AlphaVantageAPILog.timestamp).desc()
        ).all()

        daily_latency = [{'date': str(r.day), 'avg_ms': round(float(r.avg_ms), 1)} for r in daily_latency_rows]

        # Window-independent diagnostics so an empty dashboard can self-explain:
        # distinguishes "table genuinely empty / writes failing" from "today
        # window is empty but historical rows exist (timezone/window issue)".
        all_time_total = AlphaVantageAPILog.query.count()
        most_recent = db.session.query(func.max(AlphaVantageAPILog.timestamp)).scalar()

        return jsonify({
            'plan': 'Premium ($99.99/mo)',
            'rate_limit': {'per_minute': 150, 'daily': 'unlimited'},
            'diagnostics': {
                'all_time_total': all_time_total,
                'most_recent_call': most_recent.isoformat() + 'Z' if most_recent else None,
            },
            'current_minute': {'calls': last_min, 'limit': 150, 'pct': round(last_min / 150 * 100, 1)},
            'peak_per_minute': {'value': overall_peak, 'limit': 150, 'pct': round(overall_peak / 150 * 100, 1)},
            'last_hour': last_hour,
            'today': {'total': today_total, 'success': today_success, 'errors': today_errors},
            'daily_history': daily,
            'top_endpoints': endpoints,
            'top_tickers': tickers,
            'latency': {
                'avg_ms': round(float(latency_today.avg_ms), 1) if latency_today.avg_ms else None,
                'p95_ms': p95_ms,
                'max_ms': int(latency_today.max_ms) if latency_today.max_ms else None,
                'min_ms': int(latency_today.min_ms) if latency_today.min_ms else None,
                'measured_calls': measured_count,
                'by_endpoint': endpoint_latency,
                'daily_trend': daily_latency,
            },
        })
    except Exception as e:
        logger.error(f"AlphaVantage usage error: {e}")
        return jsonify({'error': str(e)}), 500


def _execute_bot_trade_wave(wave, dry_run=False):
    """
    Core bot trading logic for a specific wave. Called by both the POST endpoint
    and the Vercel cron GET wrapper.
    
    Returns a dict with trade results. Also persists a BotWaveLog row for
    every invocation (success or failure) so the admin panel and post-mortem
    analysis have a single source of truth for "why didn't the bots trade?".
    """
    import random
    from datetime import timedelta
    from models import db, User, Stock
    try:
        from models import BotWaveLog
    except ImportError:
        BotWaveLog = None  # type: ignore[assignment]

    # ── Diagnostics: open a BotWaveLog row up-front so a CRASH still leaves
    #    a trace. We commit it once at the end of this function in the
    #    finally block — even if the body raises.
    wave_log = None
    if BotWaveLog is not None:
        try:
            wave_log = BotWaveLog(wave=wave, started_at=datetime.utcnow(), status='running')
            db.session.add(wave_log)
            db.session.commit()
        except Exception as log_init_err:
            db.session.rollback()
            logger.warning(f"BotWaveLog init failed (non-fatal): {log_init_err}")
            wave_log = None

    # `results` is the dict returned to callers. It is ALSO read in the
    # finally block to populate the BotWaveLog row, so every meaningful
    # piece of state must land here (not in shadowing locals).
    results = {
        'wave': wave,
        'dry_run': dry_run,
        'bots_checked': 0,
        'bots_traded': 0,
        'trades_executed': 0,
        'decisions': [],
        'errors': [],
        'log_id': wave_log.id if wave_log else None,
    }
    wave_started_at = datetime.utcnow()

    try:
        # Get active bot users (bot_active is stored in extra_data JSON, not a column)
        all_bots = User.query.filter_by(role='agent').all()
        bots = [b for b in all_bots if (b.extra_data or {}).get('bot_active', True)]
        results['bots_checked'] = len(bots)
        if not bots:
            results['success'] = True
            results['message'] = 'No active bots'
            results['trades'] = 0
            return results
        
        # Lazy-import bot modules (heavy dependencies)
        try:
            from bot_strategies import generate_strategy_profile, generate_trade_decisions, compute_signal_score
            from bot_behaviors import should_trade_today, get_trade_wave, apply_human_biases, apply_fomo_trades
            from bot_data_hub import MarketDataHub
        except ImportError as e:
            results['error'] = f'Bot modules not available: {e}'
            return results

        # Refresh market data once for all bots. Failures here are diagnostic
        # GOLD: they reveal whether AV credentials are missing, throttled, or
        # the daily-bars cache is empty. We capture the data_quality snapshot
        # BEFORE the availability check so the BotWaveLog row records which
        # leg failed even when the wave returns early.
        hub = MarketDataHub()
        try:
            hub.refresh(include_extras=True)
        except Exception as refresh_err:
            logger.error(f"MarketDataHub.refresh raised: {refresh_err}")
            results['errors'].append(f'refresh: {refresh_err}')

        results['data_quality'] = getattr(hub, 'data_quality', None)
        try:
            results['data_summary'] = hub.summary()
        except Exception:
            results['data_summary'] = None

        if not hub.is_core_available():
            results['error'] = 'Market data unavailable'
            results['error_detail'] = 'fetch_bulk_prices returned no data (DailyPriceBar cache empty AND live AV+yfinance both failed). Run /api/cron/refresh-daily-bars to populate the cache.'
            return results

        logger.info(f"Data quality for wave {wave}: {hub.data_quality}")
        
        for bot in bots:
            try:
                # Load strategy profile. Priority order:
                #   1. extra_data['strategy_profile'] (set by batch-create /
                #      auto-create — the canonical persisted location)
                #   2. .bot_profiles/<id>.json (legacy file-based path; will
                #      NOT exist on Vercel's read-only serverless filesystem)
                #   3. Generate a fresh 'balanced' profile as a safety net
                #
                # Before May 14, only paths 2+3 existed, so every bot fell
                # through to 'balanced' regardless of what was assigned at
                # creation time — i.e., the strategy column in the admin
                # panel was decorative only. Fixed in this commit.
                import json, os
                _extra = bot.extra_data if isinstance(bot.extra_data, dict) else {}
                profile = _extra.get('strategy_profile')
                if not profile:
                    profile_path = os.path.join('.bot_profiles', f'{bot.id}.json')
                    if os.path.exists(profile_path):
                        with open(profile_path) as f:
                            profile = json.load(f)
                if not profile:
                    # Industry lives in extra_data, NOT as a User column.
                    industry = _extra.get('industry', 'General')
                    profile = generate_strategy_profile('balanced', industry)
                    logger.warning(
                        f"Bot {bot.username} (id={bot.id}) had no strategy_profile "
                        f"in extra_data; falling back to 'balanced'. Re-create the "
                        f"bot or POST /admin/bot/update-config to assign one."
                    )
                
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
                
                # Uninvested cash + mark-to-market portfolio value so BUY sizing
                # reflects total buying power and idle-cash redeployment can run
                # (mirrors the GitHub Actions runner path).
                bot_cash = float(bot.cash_proceeds or 0)
                portfolio_value = bot_cash
                for h in holdings:
                    sd = hub.get_stock_data(h['ticker'])
                    px = (sd.get('price') if sd else 0) or h.get('purchase_price', 0) or 0
                    portfolio_value += (h.get('quantity', 0) or 0) * px
                portfolio_value = max(1000.0, portfolio_value)

                # Generate decisions
                decisions = generate_trade_decisions(profile, hub, holdings, cash_available=bot_cash)
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
                    
                    # Execute trade via process_transaction (cash tracking + transaction record)
                    try:
                        from cash_tracking import process_transaction as pt_func
                        from bot_behaviors import calculate_position_size
                        action = d['action']
                        ticker = d['ticker']
                        price = d.get('price', 0)
                        if price <= 0:
                            decision_info['status'] = 'skipped_no_price'
                            results['decisions'].append(decision_info)
                            continue
                        # Size properly (matches the GH Actions executor): SELLs
                        # clamp to held qty, BUYs size off portfolio_value, and
                        # idle-cash-redeploy / rebalance buys honor target_notional.
                        _held = None
                        if action == 'sell':
                            _hs = Stock.query.filter_by(user_id=bot.id, ticker=ticker).first()
                            _held = _hs.quantity if _hs else 0
                        quantity = calculate_position_size(d, profile, portfolio_value, held_qty=_held)
                        if quantity <= 0:
                            decision_info['status'] = 'skipped_no_qty'
                            results['decisions'].append(decision_info)
                            continue
                        # Map the strategy's signal_tag onto Transaction.price_source
                        # so the admin Recent Trades 'Trigger' column can attribute
                        # the trade to its actual driver instead of always saying
                        # 'bot_research'. `generate_trade_decisions` returns a
                        # signal_tag like 'rsi', 'news', 'insider', 'stoploss',
                        # 'takeprofit', 'fomo', 'mixed' - see bot_strategies.py.
                        signal_tag = d.get('signal_tag') or 'mixed'
                        bot_price_source = f"bot_{signal_tag}"[:20]
                        decision_info['signal_tag'] = signal_tag

                        if action == 'buy':
                            stock = Stock.query.filter_by(user_id=bot.id, ticker=ticker).first()
                            if stock:
                                total_cost = (stock.quantity * stock.purchase_price) + (price * quantity)
                                stock.quantity += quantity
                                stock.purchase_price = total_cost / stock.quantity if stock.quantity > 0 else price
                            else:
                                stock = Stock(user_id=bot.id, ticker=ticker, quantity=quantity, purchase_price=price)
                                db.session.add(stock)
                            
                            pt_func(db, bot.id, ticker, quantity, price, 'buy',
                                    timestamp=datetime.utcnow(), price_source=bot_price_source)
                            
                        elif action == 'sell':
                            stock = Stock.query.filter_by(user_id=bot.id, ticker=ticker).first()
                            if stock and stock.quantity >= quantity:
                                pos_before = stock.quantity
                                stock.quantity -= quantity
                                pt_func(db, bot.id, ticker, quantity, price, 'sell',
                                       timestamp=datetime.utcnow(), position_before_qty=pos_before,
                                       price_source=bot_price_source)
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
        
        results['success'] = True
        return results
        
    except Exception as e:
        import traceback as _tb
        logger.error(f"Bot trade wave {wave} error: {e}")
        results['error'] = str(e)
        results['traceback'] = _tb.format_exc()
        return results
    finally:
        # ── Persist the BotWaveLog row regardless of how we got here ──
        # This is the single source of truth for wave-level diagnostics.
        # Any 500 you see in Vercel logs SHOULD have a corresponding row
        # in bot_wave_log explaining what failed and where.
        if wave_log is not None:
            try:
                finished_at = datetime.utcnow()
                wave_log.finished_at = finished_at
                wave_log.duration_ms = int((finished_at - wave_started_at).total_seconds() * 1000)
                wave_log.bots_checked = results.get('bots_checked', 0) or 0
                wave_log.bots_traded = results.get('bots_traded', 0) or 0
                wave_log.trades_executed = results.get('trades_executed', 0) or 0
                wave_log.data_quality = results.get('data_quality')
                wave_log.data_summary = results.get('data_summary')
                # Cap decisions array at 200 entries to keep the JSON column small.
                _decisions = results.get('decisions') or []
                wave_log.decisions = _decisions[:200] if len(_decisions) > 200 else _decisions
                # Combine the singular `error` (set by early-exit paths like
                # the lazy bot-modules ImportError or "Market data unavailable")
                # with the `errors` list (per-bot exceptions). Without this, a
                # wave that fails at module-import time leaves no trace of WHY
                # in the persisted log — only `status='no_data'` with empty
                # errors[] and null data_quality. Concatenating them here
                # closes that diagnostic gap permanently.
                _errors = list(results.get('errors') or [])
                _err_singular = results.get('error')
                if _err_singular:
                    _err_str = str(_err_singular)
                    _detail = results.get('error_detail')
                    if _detail:
                        _err_str = f"{_err_str} | detail: {_detail}"
                    _errors.insert(0, _err_str)
                wave_log.errors = _errors
                wave_log.traceback_text = results.get('traceback')
                if results.get('traceback'):
                    wave_log.status = 'error'
                elif results.get('error'):
                    # Soft-fail (e.g. no market data) — distinct from uncaught crash.
                    wave_log.status = 'no_data'
                elif results.get('errors'):
                    wave_log.status = 'partial'
                else:
                    wave_log.status = 'success'
                db.session.commit()
            except Exception as log_save_err:
                db.session.rollback()
                logger.warning(f"BotWaveLog save failed (non-fatal): {log_save_err}")


@mobile_api.route('/admin/users/set-display-name', methods=['POST'])
@require_admin_2fa
@with_db_retry
def admin_set_display_name():
    """Set or clear the public-facing display_name for one or more users.

    Idempotently runs `ALTER TABLE "user" ADD COLUMN IF NOT EXISTS display_name`
    so this endpoint also serves as the migration-applier — hit it once after
    deploy to install the column. Subsequent calls just update display_name
    values.

    Bypasses the username validation regex, so display_name can contain spaces,
    apostrophes, uppercase, emoji, etc. (length capped at 80 chars). Username
    itself is unchanged — it stays as the unique URL-safe handle.

    Request body (JSON):
        { "updates": [
            { "user_id": 13, "display_name": "The Grok Portfolio" },
            { "user_id": 14, "display_name": "Wolff's Flagship Fund" },
            { "user_id": 99, "display_name": null }   # clear it
        ] }

    Auth: admin 2FA session (or X-Admin-Key header in dev paths).
    """
    from models import db, User
    from sqlalchemy import text

    payload = request.get_json(silent=True) or {}
    updates = payload.get('updates') or []
    if not isinstance(updates, list):
        return jsonify({'error': 'updates must be a list'}), 400

    # Step 1: ensure column exists. We do a cheap information_schema lookup
    # FIRST (no locks) and only attempt the ALTER if missing. Reason:
    # `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` still acquires ACCESS EXCLUSIVE
    # on the table even when it's a no-op, and under live traffic Vercel's pooled
    # connection kills the wait via statement_timeout. By skipping the ALTER when
    # the column already exists, this endpoint is safely re-runnable without ever
    # contending for a write lock on the user table.
    try:
        col_exists = db.session.execute(text("""
            SELECT 1 FROM information_schema.columns
            WHERE table_name = 'user' AND column_name = 'display_name'
            LIMIT 1
        """)).fetchone()
        db.session.commit()  # close the read txn quickly

        if not col_exists:
            try:
                db.session.execute(text(
                    'ALTER TABLE "user" ADD COLUMN IF NOT EXISTS display_name VARCHAR(80)'
                ))
                db.session.commit()
            except Exception as e:
                db.session.rollback()
                logger.error(f"admin_set_display_name: ALTER failed (column missing): {e}")
                return jsonify({
                    'error': 'schema_setup_failed',
                    'message': str(e),
                    'hint': 'Run ALTER TABLE \"user\" ADD COLUMN IF NOT EXISTS display_name VARCHAR(80) directly via Supabase SQL Editor; the pooled connection cannot acquire ACCESS EXCLUSIVE under live traffic.',
                }), 500
    except Exception as e:
        db.session.rollback()
        logger.error(f"admin_set_display_name: schema check failed: {e}")
        return jsonify({'error': 'schema_check_failed', 'message': str(e)}), 500

    # Step 2: apply updates
    applied = []
    skipped = []
    for u in updates:
        if not isinstance(u, dict):
            skipped.append({'reason': 'not_a_dict', 'value': u})
            continue
        user_id = u.get('user_id')
        new_name = u.get('display_name')  # None means clear
        if not isinstance(user_id, int):
            skipped.append({'reason': 'invalid_user_id', 'user_id': user_id})
            continue
        if new_name is not None:
            if not isinstance(new_name, str):
                skipped.append({'reason': 'display_name_not_string', 'user_id': user_id})
                continue
            new_name = new_name.strip()
            if len(new_name) == 0:
                new_name = None  # treat empty string as clear
            elif len(new_name) > 80:
                skipped.append({'reason': 'display_name_too_long', 'user_id': user_id, 'length': len(new_name)})
                continue

        user = User.query.get(user_id)
        if not user:
            skipped.append({'reason': 'user_not_found', 'user_id': user_id})
            continue

        previous = user.display_name
        user.display_name = new_name
        applied.append({
            'user_id': user_id,
            'username': user.username,
            'previous_display_name': previous,
            'new_display_name': new_name,
        })

    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logger.error(f"admin_set_display_name: commit failed: {e}")
        return jsonify({'error': 'commit_failed', 'message': str(e)}), 500

    return jsonify({
        'success': True,
        'applied': applied,
        'skipped': skipped,
        'count': len(applied),
    })


@mobile_api.route('/admin/bot/log-av-calls', methods=['POST'])
@require_cron_secret
@with_db_retry
def log_av_calls():
    """Batch-log AlphaVantage API calls from external workers (GitHub Actions).

    Rationale: bot_agent.py runs in GitHub Actions with no DATABASE_URL and no
    Flask app context, so the direct-DB `_log_av_api_call()` in bot_data_hub.py
    silently fails (wrapped in bare except). This endpoint gives the external
    worker an HTTP path to record API usage, so the admin panel's "Market
    Research Data Sources" card reflects reality.

    Request body (JSON):
        { "logs": [
            { "endpoint": "NEWS_SENTIMENT", "symbol": "topic:technology",
              "response_status": "success", "response_time_ms": 850,
              "timestamp": "2026-05-09T18:45:12Z"  # optional, defaults to now
            },
            ...
        ] }

    Auth: X-Cron-Secret header OR admin 2FA session.
    """
    from models import db, AlphaVantageAPILog
    from datetime import datetime as _dt

    payload = request.get_json(silent=True) or {}
    logs = payload.get('logs', [])
    if not isinstance(logs, list):
        return jsonify({'error': 'logs must be a list'}), 400

    logged = 0
    errors = 0
    for entry in logs:
        if not isinstance(entry, dict):
            errors += 1
            continue
        try:
            ts = entry.get('timestamp')
            if ts:
                # Parse ISO 8601; strip trailing Z since fromisoformat() doesn't accept it
                ts_clean = ts.rstrip('Z').replace('Z', '')
                try:
                    ts_parsed = _dt.fromisoformat(ts_clean)
                except ValueError:
                    ts_parsed = _dt.utcnow()
            else:
                ts_parsed = _dt.utcnow()

            log = AlphaVantageAPILog(
                endpoint=(entry.get('endpoint') or 'UNKNOWN')[:100],
                symbol=(entry.get('symbol') or 'N/A')[:50],
                timestamp=ts_parsed,
                response_status=(entry.get('response_status') or 'success')[:20],
                response_time_ms=entry.get('response_time_ms'),
            )
            db.session.add(log)
            logged += 1
        except Exception as e:
            errors += 1
            logger.warning(f"log_av_calls: failed to parse entry {entry}: {e}")

    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logger.error(f"log_av_calls: commit failed: {e}")
        return jsonify({'error': 'commit_failed', 'message': str(e)}), 500

    return jsonify({'logged': logged, 'errors': errors, 'received': len(logs)})


@mobile_api.route('/admin/bot/log-wave', methods=['POST'])
@require_cron_secret
@with_db_retry
def log_bot_wave():
    """Persist a BotWaveLog row from external workers (GitHub Actions).

    Mirrors the in-process finally-block writes inside `_execute_bot_trade_wave()`.
    Called by `bot_agent.py:cmd_trade()` at the end of each wave (success or
    failure) so the admin panel's wave-status card and post-mortem queries
    can see what actually happened — previously the GH Actions waves left
    no trace in `bot_wave_log` because the runner has no DATABASE_URL.

    Request body (JSON), shape mirrors `BotWaveLog` columns:
        {
          "wave": 1,                                # required, 1-4
          "started_at": "2026-05-20T13:45:00Z",     # ISO 8601, defaults to now
          "finished_at": "2026-05-20T13:46:23Z",    # optional
          "duration_ms": 83000,                     # optional, auto-derived
          "status": "success",                      # default 'success'
          "bots_checked": 138,
          "bots_traded": 12,
          "trades_executed": 18,
          "data_quality": { "prices": true, ... },
          "data_summary": { "tickers_with_indicators": 138, ... },
          "decisions": [ {bot_id, username, action, ticker, score,
                          signal_tag, status}, ... ],
          "errors": [ "Bot 42: ...", ... ],
          "traceback_text": null
        }

    Auth: X-Cron-Secret header (or admin 2FA session via `require_cron_secret`).
    Returns: { "success": true, "log_id": <int> }
    """
    from models import db, BotWaveLog
    from datetime import datetime as _dt

    payload = request.get_json(silent=True) or {}

    # ── Validate wave number (must be 1-4) ──
    try:
        wave = int(payload.get('wave'))
    except (TypeError, ValueError):
        return jsonify({'error': 'wave must be an int 1-4'}), 400
    if wave not in (1, 2, 3, 4):
        return jsonify({'error': 'wave must be 1, 2, 3, or 4'}), 400

    # ── Parse timestamps. ISO 8601 with optional trailing Z. ──
    def _parse_ts(ts_str, fallback):
        if not ts_str:
            return fallback
        try:
            return _dt.fromisoformat(str(ts_str).rstrip('Z'))
        except (ValueError, AttributeError):
            return fallback

    now = _dt.utcnow()
    started_at = _parse_ts(payload.get('started_at'), now)
    finished_at = _parse_ts(payload.get('finished_at'), now)

    duration_ms = payload.get('duration_ms')
    if duration_ms is None:
        duration_ms = int((finished_at - started_at).total_seconds() * 1000)
    else:
        try:
            duration_ms = int(duration_ms)
        except (TypeError, ValueError):
            duration_ms = None

    # ── Cap large JSON fields to keep the row reasonable ──
    decisions = payload.get('decisions') or []
    if not isinstance(decisions, list):
        decisions = []
    if len(decisions) > 200:
        decisions = decisions[:200]

    errors = payload.get('errors') or []
    if not isinstance(errors, list):
        errors = []
    if len(errors) > 100:
        errors = errors[:100]

    # ── Validated counts default to 0 on bad input rather than 500 ──
    def _safe_int(v):
        try:
            return max(0, int(v))
        except (TypeError, ValueError):
            return 0

    log = BotWaveLog(
        wave=wave,
        started_at=started_at,
        finished_at=finished_at,
        duration_ms=duration_ms,
        status=(str(payload.get('status') or 'success'))[:30],
        bots_checked=_safe_int(payload.get('bots_checked')),
        bots_traded=_safe_int(payload.get('bots_traded')),
        trades_executed=_safe_int(payload.get('trades_executed')),
        data_quality=payload.get('data_quality') if isinstance(payload.get('data_quality'), dict) else None,
        data_summary=payload.get('data_summary') if isinstance(payload.get('data_summary'), dict) else None,
        decisions=decisions,
        errors=errors,
        traceback_text=payload.get('traceback_text') or None,
    )

    try:
        db.session.add(log)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logger.error(f"log_bot_wave: commit failed: {e}")
        return jsonify({'error': 'commit_failed', 'message': str(e)}), 500

    return jsonify({'success': True, 'log_id': log.id})


@mobile_api.route('/admin/bot/trade', methods=['POST'])
@require_cron_secret
@with_db_retry
def bot_trade_cron():
    """
    Trigger bot trading for a specific wave via POST.
    
    POST body (JSON):
        wave: int (1-4) — which trading wave to execute
        dry_run: bool (optional, default false)
    """
    data = request.get_json() or {}
    wave = data.get('wave')
    dry_run = data.get('dry_run', False)
    
    if not wave or wave not in [1, 2, 3, 4]:
        return jsonify({'error': 'wave required (1-4)'}), 400
    
    result = _execute_bot_trade_wave(wave, dry_run)
    if 'error' in result:
        return jsonify(result), 500
    return jsonify(result)


@mobile_api.route('/admin/dividend', methods=['POST'])
@require_admin_2fa
@with_db_retry
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


@mobile_api.route('/admin/test-push', methods=['POST'])
@require_admin_2fa
@with_db_retry
def admin_test_push():
    """Send a test push notification to all active device tokens for a user.

    Diagnostic endpoint for verifying the FCM -> APNs/FCM-Android -> device
    chain end-to-end. Returns per-token success/failure with the underlying
    FCM error so misconfigurations (wrong bundle ID, revoked APNs key,
    unregistered token, mismatched credential) can be diagnosed in one shot.

    POST body (JSON):
        username: str (required)
        title: str (optional, default 'Test Push')
        body: str (optional, default a timestamped message)
    """
    from models import db, User, DeviceToken
    from push_notification_service import get_push_service

    data = request.get_json() or {}
    username = (data.get('username') or '').strip().lower()
    if not username:
        return jsonify({'error': 'username_required'}), 400

    user = User.query.filter_by(username=username).first()
    if not user:
        return jsonify({'error': 'user_not_found', 'username': username}), 404

    device_tokens = DeviceToken.query.filter_by(user_id=user.id, is_active=True).all()
    if not device_tokens:
        return jsonify({
            'error': 'no_active_device_tokens',
            'username': username,
            'user_id': user.id,
        }), 404

    title = data.get('title') or 'Test Push'
    body = data.get('body') or f'Test push at {datetime.utcnow().isoformat()}Z'

    service = get_push_service()
    if not service.is_available:
        return jsonify({
            'error': 'firebase_not_available',
            'detail': 'FIREBASE_CREDENTIALS_JSON missing or initialization failed',
        }), 500

    # Send one-by-one (rather than multicast) so we can report per-token results.
    # Multicast obscures which specific token caused which specific failure.
    results = []
    for dt in device_tokens:
        r = service._send_single(dt.token, title, body, {'type': 'test_push'})
        results.append({
            'device_token_id': dt.id,
            'platform': dt.platform,
            'token_preview': (dt.token[:20] + '...') if dt.token else None,
            'token_len': len(dt.token) if dt.token else 0,
            'app_version': dt.app_version,
            'os_version': dt.os_version,
            'created_at': dt.created_at.isoformat() if dt.created_at else None,
            'updated_at': dt.updated_at.isoformat() if dt.updated_at else None,
            'success': r.get('success_count', 0) > 0,
            'message_id': r.get('message_id'),
            'error': r.get('error'),
        })

    success_total = sum(1 for x in results if x['success'])
    return jsonify({
        'username': username,
        'user_id': user.id,
        'tokens_attempted': len(results),
        'tokens_succeeded': success_total,
        'tokens_failed': len(results) - success_total,
        'results': results,
    })


# ── Copytrade bot filter ─────────────────────────────────────────────────
# Auto-match for Public.com email trades must restrict to TRUE copytrade
# bots, NOT strategy bots. Strategy bots (auto-created personas like
# `candle3873`) hold tickers from their own internal trading decisions and
# would incorrectly capture inbound Public.com emails. Concrete example
# (May 14 rebalance): Wolff's Flagship Fund sold REGN. A single-ticker
# email for REGN landed, the auto-match scanned ALL role=='agent' users,
# found that `candle3873` also held REGN, and routed the trade there.
# Mark a bot as a copytrade bot by either:
#   - Username in COPYTRADE_BOT_USERNAMES, or
#   - extra_data['copytrade_bot'] = True (preferred for new bots)
COPYTRADE_BOT_USERNAMES = ('CoastHillBear', 'marblethehill72')


def _is_copytrade_bot(u) -> bool:
    if not u:
        return False
    if u.username in COPYTRADE_BOT_USERNAMES:
        return True
    if isinstance(getattr(u, 'extra_data', None), dict) and u.extra_data.get('copytrade_bot') is True:
        return True
    return False


def _parse_email_received_at(iso_str):
    """Parse an ISO 8601 timestamp (as produced by JS toISOString()) to a
    naive UTC datetime, matching the DB schema convention. Returns None
    on failure so the caller can fall back to utcnow()."""
    if not iso_str:
        return None
    try:
        from datetime import timezone
        s = str(iso_str).replace('Z', '+00:00')
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is not None:
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt
    except Exception as e:
        logger.warning(f"Bad email_received_at '{iso_str}': {e}")
        return None


def _execute_single_bot_trade(bot, action, ticker, quantity, price, source, timestamp):
    """Execute a single buy/sell for a copytrade bot.

    Applies the bot's trade_multiplier (obfuscation), fetches the price
    from AlphaVantage if missing, runs the trade through
    cash_tracking.process_transaction (single source of truth for
    subscriber push/email fan-out), and updates the Stock row.

    Returns a result dict suitable for inclusion in an API response. Does
    NOT commit — caller is responsible for db.session.commit/rollback.
    """
    from models import db, Stock
    from cash_tracking import process_transaction

    if action not in ('buy', 'sell'):
        return {'ticker': ticker, 'error': f'Invalid action: {action}'}
    if not ticker:
        return {'error': 'ticker required'}

    # Apply trade multiplier (obfuscation) — set per bot via
    # extra_data['trade_multiplier'] by the scale-holdings endpoint.
    trade_multiplier = 1.0
    if bot.extra_data and isinstance(bot.extra_data, dict):
        trade_multiplier = float(bot.extra_data.get('trade_multiplier', 1.0))
    if trade_multiplier != 1.0:
        original_qty = quantity
        quantity = round(quantity * trade_multiplier, 6)
        logger.info(f"Scaled {ticker} qty: {original_qty} -> {quantity} (x{trade_multiplier}) for {bot.username}")

    # Fetch current price if not provided (NEVER fake prices)
    if price in (None, ''):
        try:
            from portfolio_performance import PortfolioPerformanceCalculator
            calc = PortfolioPerformanceCalculator()
            price_data = calc.get_stock_data(ticker)
            if price_data and price_data.get('price'):
                price = price_data['price']
                logger.info(f"Fetched price for {ticker}: ${float(price):.2f}")
            else:
                return {'ticker': ticker, 'error': 'Could not fetch price from AlphaVantage'}
        except Exception as e:
            logger.error(f"Price fetch failed for {ticker}: {e}")
            return {'ticker': ticker, 'error': f'Price fetch failed: {e}'}

    try:
        price = float(price)
    except (TypeError, ValueError):
        return {'ticker': ticker, 'error': f'Invalid price: {price}'}

    try:
        stock = Stock.query.filter_by(user_id=bot.id, ticker=ticker).first()

        # For sells: clamp/zero-means-all
        if action == 'sell':
            if not stock or (stock.quantity or 0) <= 0:
                return {'ticker': ticker, 'error': f'Bot {bot.username} does not hold {ticker}'}
            if quantity == 0 or quantity > stock.quantity:
                logger.info(f"Adjusting {ticker} sell qty: requested {quantity} -> actual {stock.quantity}")
                quantity = float(stock.quantity)

        pre_qty = float(stock.quantity) if stock else 0.0
        position_before_for_tx = pre_qty if action == 'sell' else None

        process_transaction(
            db, bot.id, ticker, quantity, price, action,
            timestamp=timestamp,
            position_before_qty=position_before_for_tx,
            price_source=source or 'copytrade',
        )

        if action == 'buy':
            if stock:
                total_cost = (stock.quantity * stock.purchase_price) + (quantity * price)
                stock.quantity += quantity
                stock.purchase_price = total_cost / stock.quantity if stock.quantity > 0 else price
            else:
                stock = Stock(user_id=bot.id, ticker=ticker, quantity=quantity, purchase_price=price)
                db.session.add(stock)
        elif action == 'sell':
            stock.quantity -= quantity

        position_pct = None
        if action == 'sell' and pre_qty > 0:
            position_pct = round((quantity / pre_qty) * 100, 1)

        return {
            'ticker': ticker,
            'action': action,
            'quantity': quantity,
            'price': price,
            'total_value': round(quantity * price, 2),
            'position_pct': position_pct,
            'status': 'executed',
            'source': source,
        }
    except Exception as e:
        logger.error(f"_execute_single_bot_trade error {ticker}: {e}", exc_info=True)
        return {'ticker': ticker, 'error': str(e)}


@mobile_api.route('/admin/bot/email-trade', methods=['POST'])
@require_cron_secret
@rate_limit(30)
@with_db_retry
def bot_email_trade():
    """Process trade notifications forwarded from Public.com emails.

    ROUTING STRATEGY (auto mode):
        - SELL with exactly one copytrade-bot holder → execute IMMEDIATELY
          on that bot, using email_received_at as the Transaction timestamp.
          This sell becomes a *cluster anchor* used to route deferred BUYs
          in the same time cluster.
        - All other trades (BUYs, SELLs with 0 or 2+ holders) → DEFER to
          PendingTrade with created_at=email_received_at. They are routed
          later by /admin/bot/process-pending-trades, which clusters
          pending rows by email_received_at and matches each cluster to
          the unique bot anchored by sells / single-holder buys in window.

    Why per-trade + anchor (instead of batch-level overlap)? Public.com
    sends one email per trade with NO bot-identifying info. The previous
    "best-overlap-on-batch" heuristic misallocated trades whenever two
    rebalances ran close together in time. Sells with exclusive ownership
    are unambiguous anchors and let us route concurrent rebalances
    correctly.

    Request body (JSON):
        bot_username: 'auto' for auto-routing, or a specific bot username
        trades: list of {action, ticker, quantity, price?}
        source: short source tag (e.g. 'public_email')
        notes: raw email text snippet (truncated to 500 chars for audit)
        email_subject: original Gmail subject (audit)
        email_received_at: ISO 8601 timestamp from Gmail message.getDate()
        email_message_id: Gmail message ID (audit)

    Legacy single-trade format (action/ticker/quantity/price at top level)
    is still supported.
    """
    from models import db, User, Stock, PendingTrade
    from datetime import timedelta
    import uuid

    data = request.get_json() or {}
    bot_username = data.get('bot_username')
    source = data.get('source', 'public_email')
    notes = data.get('notes', '')
    email_subject = data.get('email_subject', '')
    email_message_id = data.get('email_message_id', '')

    if not bot_username:
        return jsonify({'error': 'bot_username required'}), 400

    raw_trades = data.get('trades', [])
    if isinstance(raw_trades, list) and len(raw_trades) > 50:
        return jsonify({'error': 'batch_too_large', 'max_trades_per_request': 50}), 400

    # Email received-at: used as cluster key + Transaction timestamp. Falls
    # back to wall-clock if GAS didn't send it (older GAS versions).
    email_received_at = _parse_email_received_at(data.get('email_received_at'))
    if email_received_at is None:
        email_received_at = datetime.utcnow()

    # Normalise trades list (support legacy single-trade format)
    trades = list(raw_trades) if raw_trades else []
    if not trades and data.get('ticker'):
        trades = [{
            'action': data.get('action', 'buy'),
            'ticker': data.get('ticker', ''),
            'quantity': data.get('quantity', 1),
            'price': data.get('price'),
        }]
    if not trades:
        return jsonify({'error': 'No trades specified'}), 400

    try:
        # ── Explicit bot username path (manual admin / test calls) ───
        if bot_username != 'auto':
            bot = User.query.filter_by(username=bot_username, role='agent').first()
            if not bot:
                return jsonify({'error': f'Bot user "{bot_username}" not found'}), 404

            results = []
            for t in trades:
                action = (t.get('action') or '').lower()
                ticker = (t.get('ticker') or '').upper()
                quantity = float(t.get('quantity') or 1)
                price = t.get('price')
                try:
                    r = _execute_single_bot_trade(
                        bot, action, ticker, quantity, price,
                        source=source, timestamp=email_received_at,
                    )
                    results.append(r)
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
                'results': results,
            })

        # ── Auto-detect path ─────────────────────────────────────────
        all_agents = User.query.filter_by(role='agent').all()
        copytrade_bots = [u for u in all_agents if _is_copytrade_bot(u)]
        if not copytrade_bots:
            logger.warning(
                f"No copytrade bots configured among {len(all_agents)} agents; "
                f"all email trades will be deferred. Mark a bot with "
                f"extra_data.copytrade_bot=true or add its username to "
                f"COPYTRADE_BOT_USERNAMES."
            )

        # Build per-ticker holder map (positive-quantity holdings only)
        holders_by_ticker = {}
        for cb in copytrade_bots:
            for s in Stock.query.filter_by(user_id=cb.id).all():
                if (s.quantity or 0) > 0:
                    tk = (s.ticker or '').upper()
                    holders_by_ticker.setdefault(tk, []).append(cb)

        batch_id = str(uuid.uuid4())[:12]
        raw_snippet = (notes or '')[:500]
        # Expiry is anchored on email_received_at so historical replays
        # (e.g. reprocessTodaysTrades) age correctly.
        expires = email_received_at + timedelta(minutes=30)

        executed_results = []
        deferred_results = []
        auto_source = source if source.startswith('auto_') else f'auto_{source}'

        for t in trades:
            action = (t.get('action') or '').lower()
            ticker = (t.get('ticker') or '').upper()
            try:
                quantity = float(t.get('quantity') or 1)
            except (TypeError, ValueError):
                quantity = 1.0
            price_raw = t.get('price')
            price = price_raw if price_raw not in (None, '') else None

            if not ticker or action not in ('buy', 'sell'):
                executed_results.append({
                    'ticker': ticker, 'action': action,
                    'error': 'invalid action or ticker',
                })
                continue

            holders = holders_by_ticker.get(ticker, [])
            # Immediate execution ONLY for sells with a unique holder.
            # These are the safest signals: a sell of a ticker only one
            # bot holds is unambiguously that bot's trade, and it lays
            # down a Transaction at email_received_at that the cluster
            # resolver uses to anchor sibling buys.
            anchor_bot = holders[0] if (action == 'sell' and len(holders) == 1) else None

            if anchor_bot is not None:
                try:
                    r = _execute_single_bot_trade(
                        anchor_bot, action, ticker, quantity, price,
                        source=auto_source, timestamp=email_received_at,
                    )
                except Exception as e:
                    db.session.rollback()
                    r = {'ticker': ticker, 'error': str(e)}
                r['routing'] = {
                    'mode': 'sell_anchor',
                    'bot_username': anchor_bot.username,
                    'bot_id': anchor_bot.id,
                }
                executed_results.append(r)
            else:
                # Defer — cluster resolver will route via anchors
                if action == 'buy':
                    reason = 'buy_always_deferred'
                elif len(holders) == 0:
                    reason = 'sell_no_holder'
                else:
                    reason = 'sell_ambiguous_holders'
                pt = PendingTrade(
                    email_batch_id=batch_id,
                    ticker=ticker,
                    action=action,
                    quantity=quantity,
                    price=float(price) if price not in (None, '') else None,
                    status='pending',
                    source_email_subject=email_subject,
                    raw_email_snippet=raw_snippet,
                    created_at=email_received_at,
                    expires_at=expires,
                )
                db.session.add(pt)
                deferred_results.append({
                    'ticker': ticker,
                    'action': action,
                    'quantity': quantity,
                    'status': 'deferred',
                    'reason': reason,
                    'holders': [h.username for h in holders],
                })

        db.session.commit()

        executed_count = sum(1 for r in executed_results if r.get('status') == 'executed')
        if executed_results and deferred_results:
            status = 'mixed'
        elif executed_results:
            status = 'executed'
        else:
            status = 'deferred'

        logger.info(
            f"bot_email_trade auto: batch={batch_id} executed={executed_count} "
            f"deferred={len(deferred_results)} received_at={email_received_at.isoformat()} "
            f"msg_id={email_message_id or 'n/a'}"
        )

        return jsonify({
            'success': True,
            'status': status,
            'batch_id': batch_id,
            'email_received_at': email_received_at.isoformat(),
            'email_message_id': email_message_id or None,
            'trades_submitted': len(trades),
            'trades_executed': executed_count,
            'trades_deferred': len(deferred_results),
            'executed': executed_results,
            'deferred': deferred_results,
            'expires_at': expires.isoformat() if deferred_results else None,
        })

    except Exception as e:
        db.session.rollback()
        logger.error(f"Bot email trade error: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@mobile_api.route('/admin/bot/process-pending-trades', methods=['POST'])
@require_cron_secret
@rate_limit(10)
@with_db_retry
def bot_process_pending_trades():
    """Resolve PendingTrade rows by clustering on email_received_at and
    routing each cluster to the copytrade bot uniquely anchored by
    sells / single-holder buys in the cluster window.

    Algorithm:
        1. Load pending trades sorted by created_at (= email_received_at).
        2. Split into CLUSTERS where adjacent trades are within
           CLUSTER_GAP_SEC of each other.
        3. For each cluster, compute candidate bots from two sources:
             (a) sell_anchors = bots with auto_* Transactions in the
                 cluster's [start-pad, end+pad] window. SELLs are
                 strong signals (executed by bot_email_trade as a
                 unique-holder sell).
             (b) unique_buy_holders = for each pending BUY, the unique
                 copytrade-bot holder of its ticker (if any).
        4. Decide:
             - If sell_anchors is non-empty and unique → route cluster
               to that anchor.
             - elif sell_anchors empty AND unique_buy_holders has
               exactly one bot AND every pending BUY in cluster has
               that holder (no "no-holder" buys polluting the cluster)
               → route cluster to that bot.
             - elif candidates is empty → leave pending, expire only
               if any trade is past expires_at.
             - else (multiple candidates / mixed) → mark cluster
               unroutable + notify admin.
    """
    from models import db, User, Stock, PendingTrade, Transaction
    from datetime import timedelta

    # Tunables — feel free to tighten/loosen.
    CLUSTER_GAP_SEC = 60     # max gap between adjacent emails in same cluster
    WINDOW_PAD_SEC = 30      # tolerance when matching Transactions to cluster

    try:
        now = datetime.utcnow()
        pending = (
            PendingTrade.query.filter_by(status='pending')
            .order_by(PendingTrade.created_at.asc())
            .all()
        )
        if not pending:
            return jsonify({'success': True, 'message': 'No pending trades', 'processed': 0})

        # Cluster by email_received_at gap
        clusters = []
        current = []
        for pt in pending:
            if not current:
                current = [pt]
                continue
            gap = (pt.created_at - current[-1].created_at).total_seconds()
            if gap <= CLUSTER_GAP_SEC:
                current.append(pt)
            else:
                clusters.append(current)
                current = [pt]
        if current:
            clusters.append(current)

        all_agents = User.query.filter_by(role='agent').all()
        copytrade_bots = [u for u in all_agents if _is_copytrade_bot(u)]
        copytrade_by_id = {b.id: b for b in copytrade_bots}
        copytrade_ids = list(copytrade_by_id.keys())

        # Pre-build per-ticker holder map (positive holdings only)
        holders_by_ticker = {}
        for cb in copytrade_bots:
            for s in Stock.query.filter_by(user_id=cb.id).all():
                if (s.quantity or 0) > 0:
                    tk = (s.ticker or '').upper()
                    holders_by_ticker.setdefault(tk, []).append(cb)

        routed_count = 0
        expired_count = 0
        still_pending = 0
        ambiguous_clusters_log = []
        no_anchor_clusters_log = []
        routed_clusters_log = []

        for cluster in clusters:
            c_start = cluster[0].created_at - timedelta(seconds=WINDOW_PAD_SEC)
            c_end = cluster[-1].created_at + timedelta(seconds=WINDOW_PAD_SEC)

            # (a) Sell anchors: auto_* Transactions on copytrade bots in window
            sell_anchor_bot_ids = set()
            anchor_txns_detail = []
            if copytrade_ids:
                anchor_txns = (
                    Transaction.query
                    .filter(
                        Transaction.user_id.in_(copytrade_ids),
                        Transaction.timestamp >= c_start,
                        Transaction.timestamp <= c_end,
                        Transaction.price_source.like('auto_%'),
                    )
                    .all()
                )
                for tx in anchor_txns:
                    sell_anchor_bot_ids.add(tx.user_id)
                    anchor_txns_detail.append({
                        'user_id': tx.user_id,
                        'ticker': tx.ticker,
                        'type': tx.transaction_type,
                        'timestamp': tx.timestamp.isoformat() if tx.timestamp else None,
                        'price_source': tx.price_source,
                    })

            # (b) Per-BUY unique-holder analysis
            buy_holder_bot_ids = set()
            buy_no_holder_count = 0
            buy_ambig_holder_count = 0
            for pt in cluster:
                if pt.action != 'buy':
                    continue
                holders = holders_by_ticker.get(pt.ticker.upper(), [])
                if len(holders) == 1:
                    buy_holder_bot_ids.add(holders[0].id)
                elif len(holders) == 0:
                    buy_no_holder_count += 1
                else:
                    buy_ambig_holder_count += 1

            chosen_bot_id = None
            decision_reason = None

            if len(sell_anchor_bot_ids) == 1:
                chosen_bot_id = next(iter(sell_anchor_bot_ids))
                decision_reason = 'sell_anchor_unique'
            elif len(sell_anchor_bot_ids) >= 2:
                decision_reason = 'sell_anchors_conflict'
            elif (
                not sell_anchor_bot_ids
                and len(buy_holder_bot_ids) == 1
                and buy_no_holder_count == 0
                and buy_ambig_holder_count == 0
            ):
                chosen_bot_id = next(iter(buy_holder_bot_ids))
                decision_reason = 'unanimous_buy_holders'
            elif len(buy_holder_bot_ids) >= 2:
                decision_reason = 'buy_holders_conflict'
            elif (
                not sell_anchor_bot_ids
                and len(buy_holder_bot_ids) == 1
                and (buy_no_holder_count > 0 or buy_ambig_holder_count > 0)
            ):
                # Single holder match alongside no-holder/ambiguous buys.
                # Refuse to auto-route — this is the May-2026 misallocation
                # shape (one matching ticker + several unknowns).
                decision_reason = 'mixed_holder_signals'
            else:
                decision_reason = 'no_signal'

            cluster_info = {
                'window_start': c_start.isoformat(),
                'window_end': c_end.isoformat(),
                'reason': decision_reason,
                'sell_anchor_bot_ids': sorted(sell_anchor_bot_ids),
                'buy_holder_bot_ids': sorted(buy_holder_bot_ids),
                'buy_no_holder_count': buy_no_holder_count,
                'buy_ambig_holder_count': buy_ambig_holder_count,
                'anchor_txns': anchor_txns_detail,
                'trades': [
                    {'id': pt.id, 'ticker': pt.ticker, 'action': pt.action,
                     'quantity': pt.quantity, 'received_at': pt.created_at.isoformat() if pt.created_at else None}
                    for pt in cluster
                ],
            }

            if chosen_bot_id is not None:
                matched_bot = copytrade_by_id[chosen_bot_id]
                for pt in cluster:
                    r = _execute_single_bot_trade(
                        matched_bot, pt.action, pt.ticker.upper(),
                        float(pt.quantity), pt.price,
                        source='auto_deferred',
                        timestamp=pt.created_at,
                    )
                    if r.get('status') == 'executed':
                        pt.assigned_bot_id = matched_bot.id
                        pt.status = 'routed'
                        pt.routed_at = now
                        routed_count += 1
                        logger.info(
                            f"Cluster route: {pt.ticker} {pt.action} -> "
                            f"{matched_bot.username} (reason={decision_reason})"
                        )
                    else:
                        # Execution failed but routing decision was made;
                        # mark unroutable so it doesn't loop forever.
                        pt.status = 'unroutable'
                        expired_count += 1
                        logger.error(
                            f"Cluster execute fail: {pt.ticker} {pt.action} "
                            f"-> {matched_bot.username}: {r.get('error')}"
                        )
                cluster_info['routed_to'] = matched_bot.username
                routed_clusters_log.append(cluster_info)

            elif decision_reason in ('sell_anchors_conflict', 'buy_holders_conflict', 'mixed_holder_signals'):
                for pt in cluster:
                    pt.status = 'unroutable'
                    expired_count += 1
                ambiguous_clusters_log.append(cluster_info)
                _notify_admin_unroutable_trades(
                    cluster[0].email_batch_id, cluster,
                    reason=decision_reason, detail=cluster_info,
                )

            else:
                # no_signal — wait unless any trade has expired
                if any(pt.expires_at <= now for pt in cluster):
                    for pt in cluster:
                        pt.status = 'unroutable'
                        expired_count += 1
                    no_anchor_clusters_log.append(cluster_info)
                    _notify_admin_unroutable_trades(
                        cluster[0].email_batch_id, cluster,
                        reason='no_anchor_30min', detail=cluster_info,
                    )
                else:
                    still_pending += len(cluster)

        db.session.commit()

        return jsonify({
            'success': True,
            'pending_clusters': len(clusters),
            'routed': routed_count,
            'expired': expired_count,
            'still_pending': still_pending,
            'routed_clusters': routed_clusters_log,
            'ambiguous_clusters': ambiguous_clusters_log,
            'no_anchor_clusters': no_anchor_clusters_log,
        })

    except Exception as e:
        db.session.rollback()
        logger.error(f"Process pending trades error: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@mobile_api.route('/admin/bot/pending-trades', methods=['GET'])
@require_admin_2fa
@with_db_retry
def bot_pending_trades():
    """List all pending/unroutable trades for admin review."""
    from models import PendingTrade
    
    status_filter = request.args.get('status', 'all')
    query = PendingTrade.query
    if status_filter != 'all':
        query = query.filter_by(status=status_filter)
    
    trades = query.order_by(PendingTrade.created_at.desc()).limit(100).all()
    
    return jsonify({
        'count': len(trades),
        'trades': [{
            'id': t.id,
            'batch_id': t.email_batch_id,
            'ticker': t.ticker,
            'action': t.action,
            'quantity': t.quantity,
            'price': t.price,
            'status': t.status,
            'assigned_bot_id': t.assigned_bot_id,
            'created_at': t.created_at.isoformat() if t.created_at else None,
            'expires_at': t.expires_at.isoformat() if t.expires_at else None,
            'routed_at': t.routed_at.isoformat() if t.routed_at else None,
            'email_subject': t.source_email_subject,
        } for t in trades]
    })


@mobile_api.route('/admin/bot/assign-pending-trades', methods=['POST'])
@require_admin_2fa
@with_db_retry
def bot_assign_pending_trades():
    """
    Manually assign pending/unroutable trades to a specific bot.
    
    Request body:
    {
        "batch_id": "abc123",      // or "trade_ids": [1, 2, 3]
        "bot_user_id": 13
    }
    """
    from models import db, User, Stock, PendingTrade
    from cash_tracking import process_transaction
    
    data = request.get_json() or {}
    bot_user_id = data.get('bot_user_id')
    batch_id = data.get('batch_id')
    trade_ids = data.get('trade_ids', [])
    
    if not bot_user_id:
        return jsonify({'error': 'bot_user_id required'}), 400
    if not batch_id and not trade_ids:
        return jsonify({'error': 'batch_id or trade_ids required'}), 400
    
    try:
        bot = User.query.get(bot_user_id)
        if not bot:
            return jsonify({'error': 'bot_not_found'}), 404
        
        trade_multiplier = 1.0
        if bot.extra_data and isinstance(bot.extra_data, dict):
            trade_multiplier = float(bot.extra_data.get('trade_multiplier', 1.0))
        
        if batch_id:
            pending = PendingTrade.query.filter_by(email_batch_id=batch_id).filter(
                PendingTrade.status.in_(['pending', 'unroutable'])
            ).all()
        else:
            pending = PendingTrade.query.filter(
                PendingTrade.id.in_(trade_ids),
                PendingTrade.status.in_(['pending', 'unroutable'])
            ).all()
        
        if not pending:
            return jsonify({'error': 'No matching pending trades found'}), 404
        
        executed = []
        now = datetime.utcnow()
        
        for pt in pending:
            pt.assigned_bot_id = bot.id
            pt.status = 'routed'
            pt.routed_at = now
            
            qty = pt.quantity
            if trade_multiplier != 1.0:
                qty = round(qty * trade_multiplier, 6)
            
            price = pt.price
            if not price:
                try:
                    from portfolio_performance import PortfolioPerformanceCalculator
                    calc = PortfolioPerformanceCalculator()
                    price_data = calc.get_stock_data(pt.ticker)
                    price = price_data['price'] if price_data and price_data.get('price') else None
                except Exception:
                    price = None
            
            if price:
                try:
                    stock = Stock.query.filter_by(user_id=bot.id, ticker=pt.ticker).first()
                    pos_before = stock.quantity if stock and pt.action == 'sell' else None
                    process_transaction(db, bot.id, pt.ticker, qty, float(price), pt.action, timestamp=now, position_before_qty=pos_before)
                    if pt.action == 'buy':
                        if stock:
                            total_cost = (stock.quantity * stock.purchase_price) + (qty * float(price))
                            stock.quantity += qty
                            stock.purchase_price = total_cost / stock.quantity if stock.quantity > 0 else float(price)
                        else:
                            stock = Stock(user_id=bot.id, ticker=pt.ticker, quantity=qty, purchase_price=float(price))
                            db.session.add(stock)
                    elif pt.action == 'sell' and stock and stock.quantity >= qty:
                        stock.quantity -= qty
                    
                    executed.append({'ticker': pt.ticker, 'action': pt.action, 'quantity': qty, 'price': float(price)})
                except Exception as e:
                    logger.error(f"Manual assign trade error {pt.ticker}: {e}")
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'bot_user_id': bot.id,
            'bot_username': bot.username,
            'assigned': len(pending),
            'executed': len(executed),
            'trades': executed
        })
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Assign pending trades error: {e}")
        return jsonify({'error': str(e)}), 500


def _notify_admin_unroutable_trades(batch_id, trades, reason='no_anchor_30min', detail=None):
    """Send email notification to admin about unroutable trades.

    Args:
        batch_id: representative email_batch_id (for the assign endpoint).
        trades: list of PendingTrade rows (the unroutable cluster).
        reason: short reason code (e.g. 'sell_anchors_conflict',
                'mixed_holder_signals', 'no_anchor_30min'). Used in the
                subject + body so the admin can triage faster.
        detail: optional dict with cluster diagnostics. Included verbatim
                in the email body for forensics.
    """
    try:
        import smtplib
        import json as _json
        from email.mime.text import MIMEText

        # Fallback chain: ADMIN_NOTIFY_EMAIL → ADMIN_EMAIL → hardcoded admin inbox.
        admin_email = (
            os.environ.get('ADMIN_NOTIFY_EMAIL')
            or os.environ.get('ADMIN_EMAIL')
            or 'bobford00@gmail.com'
        )
        smtp_user = os.environ.get('SMTP_USER')
        smtp_pass = os.environ.get('SMTP_PASS')

        tickers = ', '.join(t.ticker for t in trades)

        if not smtp_user or not smtp_pass:
            logger.warning(
                f"UNROUTABLE TRADES (no SMTP configured) batch={batch_id} "
                f"reason={reason}: {tickers}"
            )
            return

        body = f"""Unroutable Trade Alert - Apes Together

Reason: {reason}
Batch ID: {batch_id}
Trades that could not be auto-routed:

"""
        for t in trades:
            body += f"  {t.action.upper()} {t.quantity} {t.ticker}"
            if t.price:
                body += f" @ ${float(t.price):.2f}"
            if t.created_at:
                body += f" (received {t.created_at.isoformat()})"
            body += "\n"

        if detail:
            try:
                body += "\nCluster diagnostics:\n"
                body += _json.dumps(detail, indent=2, default=str)
                body += "\n"
            except Exception:
                pass

        body += f"""

To manually assign these trades, call:
POST /admin/bot/assign-pending-trades
{{
    "batch_id": "{batch_id}",
    "bot_user_id": <13 for Grok, 14 for Wolff>
}}

Or inspect/list pending trades:
GET /admin/bot/pending-trades?status=unroutable
"""

        msg = MIMEText(body)
        msg['Subject'] = f'[ApesTogether] Unroutable trades ({reason}): {tickers}'
        msg['From'] = smtp_user
        msg['To'] = admin_email

        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(smtp_user, smtp_pass)
            server.send_message(msg)

        logger.info(f"Admin notified about unroutable trades batch={batch_id} reason={reason}")
    except Exception as e:
        logger.error(f"Failed to send admin notification: {e}")


@mobile_api.route('/admin/bot/sp500-backfill', methods=['POST'])
@require_admin_2fa
@with_db_retry
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
@require_admin_2fa
@with_db_retry
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
@require_admin_or_cron
@with_db_retry
def bot_holdings():
    """
    Get a user's current stock holdings + cash.
    Query param: user_id
    Returns {holdings: [{ticker, quantity, purchase_price}], count,
             cash, cash_proceeds, max_cash_deployed}
    """
    from models import Stock, User
    
    user_id = request.args.get('user_id')
    if not user_id:
        return jsonify({'error': 'user_id_required'}), 400
    
    try:
        uid = int(user_id)
        stocks = Stock.query.filter_by(user_id=uid).all()
        holdings = [{
            'ticker': s.ticker,
            'quantity': s.quantity,
            'purchase_price': round(float(s.purchase_price), 2) if s.purchase_price else 0,
        } for s in stocks if s.quantity > 0]
        # Surface cash so the bot trade runner can size BUYs off total buying
        # power (stock + cash) and run idle-cash redeployment. Without this the
        # runner sized buys off stock value alone, so a bot that had liquidated
        # to mostly cash could never redeploy — the cash-accumulation bug.
        u = User.query.get(uid)
        cash = round(float(u.cash_proceeds or 0), 2) if u else 0.0
        max_cash = round(float(u.max_cash_deployed or 0), 2) if u else 0.0
        return jsonify({
            'holdings': holdings,
            'count': len(holdings),
            'cash': cash,
            'cash_proceeds': cash,
            'max_cash_deployed': max_cash,
        })
    except Exception as e:
        logger.error(f"Bot holdings error: {e}")
        return jsonify({'error': 'holdings_failed'}), 500


@mobile_api.route('/admin/backfill-sectors', methods=['POST'])
@require_admin_2fa
@with_db_retry
def admin_backfill_sectors():
    """
    Backfill missing sector data for all stocks held by any user.
    Fetches from Alpha Vantage OVERVIEW for any StockInfo with null sector.
    Query params:
      - limit: max tickers to process (default 20, Alpha Vantage free = 25/day)
      - sleep: seconds between API calls (default 2)
      - dry_run: if true, just list tickers that need backfill
    """
    from models import db, Stock, StockInfo
    from stock_metadata_utils import populate_stock_info
    import time as _time
    
    limit = request.args.get('limit', 20, type=int)
    sleep_sec = request.args.get('sleep', 2, type=int)
    dry_run = request.args.get('dry_run', 'false').lower() == 'true'
    
    try:
        # Get all unique tickers held by any user
        held_tickers = db.session.query(Stock.ticker).filter(
            Stock.quantity > 0
        ).distinct().all()
        held_tickers = [t[0].upper() for t in held_tickers]
        
        # Find which ones are missing sector data
        missing = []
        for ticker in held_tickers:
            info = StockInfo.query.filter_by(ticker=ticker).first()
            if not info or not info.sector:
                missing.append(ticker)
        
        if dry_run:
            return jsonify({
                'total_held': len(held_tickers),
                'missing_sector': len(missing),
                'tickers': missing
            })
        
        # Process up to limit
        results = []
        for ticker in missing[:limit]:
            try:
                result = populate_stock_info(ticker, force_update=True)
                if result and result.sector:
                    results.append({'ticker': ticker, 'sector': result.sector, 'status': 'ok'})
                else:
                    results.append({'ticker': ticker, 'status': 'failed'})
            except Exception as e:
                results.append({'ticker': ticker, 'status': 'error', 'error': str(e)})
            
            if sleep_sec > 0 and ticker != missing[min(limit, len(missing)) - 1]:
                _time.sleep(sleep_sec)
        
        ok_count = sum(1 for r in results if r.get('status') == 'ok')
        return jsonify({
            'total_held': len(held_tickers),
            'missing_sector': len(missing),
            'processed': len(results),
            'success': ok_count,
            'results': results
        })
    except Exception as e:
        logger.error(f"Backfill sectors error: {e}")
        return jsonify({'error': str(e)}), 500



@mobile_api.route('/admin/bot/gift-subscribers', methods=['POST'])
@require_admin_2fa
@with_db_retry
def bot_gift_subscribers():
    """
    Gift promotional subscribers to a user (influencer).
    
    Uses AdminSubscription to track gifted subs separately from real ones.
    No Apple/Google fees, no platform cut — company pays influencer directly.
    The influencer sees the subscriber count go up and gets paid the same $6.50/sub
    they would from a real subscription.
    
    Request body:
    {
        "user_id": 123,
        "count": 5,
        "reason": "Marketing boost for launch"  (optional)
    }
    """
    from models import db, User, AdminSubscription, UserPortfolioStats
    
    data = request.get_json()
    if not data:
        return jsonify({'error': 'missing_request_body'}), 400
    
    user_id = data.get('user_id')
    count = data.get('count', 1)
    reason = data.get('reason', '')
    
    if not user_id or count <= 0:
        return jsonify({'error': 'user_id_and_positive_count_required'}), 400
    
    try:
        user = User.query.get(user_id)
        if not user:
            return jsonify({'error': 'user_not_found'}), 404
        
        # Get or create AdminSubscription record for this user
        admin_sub = AdminSubscription.query.filter_by(portfolio_user_id=user_id).first()
        if admin_sub:
            admin_sub.bonus_subscriber_count = (admin_sub.bonus_subscriber_count or 0) + count
            if reason:
                existing_reason = admin_sub.reason or ''
                admin_sub.reason = f"{existing_reason}; {reason}" if existing_reason else reason
        else:
            admin_sub = AdminSubscription(
                portfolio_user_id=user_id,
                bonus_subscriber_count=count,
                reason=reason
            )
            db.session.add(admin_sub)
        
        # Update UserPortfolioStats subscriber_count (what the influencer sees)
        # Also populate industry_mix/stats so user appears in Top Creators
        stats = UserPortfolioStats.query.filter_by(user_id=user_id).first()
        if stats:
            stats.subscriber_count = (stats.subscriber_count or 0) + count
        else:
            stats = UserPortfolioStats(
                user_id=user_id,
                subscriber_count=count
            )
            db.session.add(stats)
        
        # Populate stats fields if missing (needed for Top Creators)
        try:
            from leaderboard_utils import calculate_user_portfolio_stats
            user_stats = calculate_user_portfolio_stats(user_id)
            stats.unique_stocks_count = user_stats.get('unique_stocks_count', 0)
            stats.avg_trades_per_week = user_stats.get('avg_trades_per_week', 0)
            stats.industry_mix = user_stats.get('industry_mix', {})
            # Phase E: fractional-shares flag for Discover/Leaderboard filter.
            stats.has_fractional_holdings = user_stats.get('has_fractional_holdings', False)
        except Exception as stats_err:
            logger.warning(f"Non-blocking: failed to populate stats for user {user_id}: {stats_err}")
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'gifted': count,
            'total_bonus_subscribers': admin_sub.bonus_subscriber_count,
            'new_subscriber_count': stats.subscriber_count,
            'accounting': {
                'payout_per_sub': AdminSubscription.INFLUENCER_PAYOUT_PER_SUB,
                'total_monthly_payout': admin_sub.payout_amount,
                'store_fees': 0.0,
                'platform_cut': 0.0,
                'note': 'Gifted — company pays influencer directly, no store/platform fees'
            }
        })
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Gift subscribers error: {e}")
        return jsonify({'error': 'gift_failed'}), 500


@mobile_api.route('/admin/bot/deactivate', methods=['POST'])
@require_admin_2fa
@with_db_retry
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
@require_admin_2fa
@with_db_retry
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
@require_admin_or_cron
@with_db_retry
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
@require_admin_2fa
@with_db_retry
def bot_remove_subscribers():
    """
    Remove gifted/promotional subscribers from a user.
    Decrements AdminSubscription.bonus_subscriber_count and UserPortfolioStats.subscriber_count.
    
    Request body:
    {
        "user_id": 123,
        "count": 3
    }
    """
    from models import db, AdminSubscription, UserPortfolioStats
    
    data = request.get_json()
    if not data:
        return jsonify({'error': 'missing_request_body'}), 400
    
    user_id = data.get('user_id')
    count = data.get('count', 1)
    
    if not user_id or count <= 0:
        return jsonify({'error': 'user_id_and_positive_count_required'}), 400
    
    try:
        admin_sub = AdminSubscription.query.filter_by(portfolio_user_id=user_id).first()
        if not admin_sub or (admin_sub.bonus_subscriber_count or 0) == 0:
            return jsonify({'error': 'no_gifted_subscribers_to_remove'}), 400
        
        # Don't remove more than exist
        actual_remove = min(count, admin_sub.bonus_subscriber_count or 0)
        admin_sub.bonus_subscriber_count = (admin_sub.bonus_subscriber_count or 0) - actual_remove
        
        # Update stats
        stats = UserPortfolioStats.query.filter_by(user_id=user_id).first()
        if stats:
            stats.subscriber_count = max(0, (stats.subscriber_count or 0) - actual_remove)
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'removed': actual_remove,
            'remaining_bonus_subscribers': admin_sub.bonus_subscriber_count,
            'new_subscriber_count': stats.subscriber_count if stats else 0
        })
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Remove subscribers error: {e}")
        return jsonify({'error': 'remove_failed'}), 500


# ── Dashboard API Endpoints ──────────────────────────────────────────────────

@mobile_api.route('/admin/portfolio-stats/recompute-fractional', methods=['POST'])
@require_admin_2fa
@with_db_retry
def recompute_fractional_holdings():
    """One-shot backfill for the Phase E `has_fractional_holdings` column on
    `user_portfolio_stats`.

    Why this exists
    ---------------
    The migration adds the column as nullable with no default. The daily
    market-close cron will populate it via `calculate_user_portfolio_stats`
    going forward, but that means existing rows stay NULL until the user has
    a stats refresh — and the `hide_fractional` filter on /leaderboard +
    /top-influencers treats NULL as "show" (correct for rollout safety, but
    means the toggle does nothing until the column is populated).

    This endpoint walks every user with active Stocks and computes the flag
    directly, upserting `UserPortfolioStats` rows as needed. Idempotent —
    safe to run repeatedly. After running once, the toggle works for
    everyone immediately; the daily cron keeps it fresh.

    Query params:
        dry_run (1/0, default 0): preview without writing.

    Returns:
        {
          'dry_run': bool,
          'users_scanned': int,
          'users_with_fractional': int,
          'users_updated': int,    # rows actually changed
          'users_created': int,    # new UserPortfolioStats rows
          'duration_ms': int,
        }
    """
    from models import db, User, Stock, UserPortfolioStats
    from datetime import datetime as _dt
    import time as _time

    dry_run = request.args.get('dry_run', '0') == '1'
    started = _time.time()

    # Bulk fetch every Stock with quantity>0, group by user. Far cheaper than
    # iterating users and querying Stocks per user.
    stock_rows = Stock.query.filter(Stock.quantity > 0).all()
    by_user = {}
    for s in stock_rows:
        if s.quantity is None:
            continue
        by_user.setdefault(s.user_id, []).append(s)

    users_scanned = 0
    users_with_fractional = 0
    users_updated = 0
    users_created = 0

    for user_id, stocks in by_user.items():
        users_scanned += 1
        has_frac = any(
            abs(s.quantity - round(s.quantity)) > 0.0001
            for s in stocks
        )
        if has_frac:
            users_with_fractional += 1

        if dry_run:
            continue

        stats_row = UserPortfolioStats.query.filter_by(user_id=user_id).first()
        if stats_row is None:
            stats_row = UserPortfolioStats(
                user_id=user_id,
                has_fractional_holdings=has_frac,
                last_updated=_dt.utcnow(),
            )
            db.session.add(stats_row)
            users_created += 1
        elif stats_row.has_fractional_holdings != has_frac:
            stats_row.has_fractional_holdings = has_frac
            stats_row.last_updated = _dt.utcnow()
            users_updated += 1

    if not dry_run:
        db.session.commit()

    return jsonify({
        'dry_run': dry_run,
        'users_scanned': users_scanned,
        'users_with_fractional': users_with_fractional,
        'users_updated': users_updated,
        'users_created': users_created,
        'duration_ms': int((_time.time() - started) * 1000),
    })


@mobile_api.route('/admin/bot/diagnose-imports', methods=['GET'])
@require_admin_2fa
def bot_diagnose_imports():
    """Synchronously attempt every import the bot trade wave needs and
    report which one (if any) fails.

    Why this exists
    ---------------
    `_execute_bot_trade_wave` lazy-imports `bot_strategies`, `bot_behaviors`,
    and `bot_data_hub` inside a try/except ImportError. When that fires on
    Vercel (e.g. numpy stripped from the function bundle, dep version
    conflict), the wave aborts with status='no_data' and 0/12 bots traded
    in 0.0s. The cron only runs every ~30-60 min, so debugging via that
    log loop is slow.

    This endpoint runs the same imports right now and tells you exactly
    which import raised what. No waiting, no 0/12 mystery.

    Returns:
        {
          'all_ok': bool,
          'imports': [
            {'name': 'bot_strategies', 'ok': True|False, 'error': str|None,
             'symbols_resolved': bool, 'missing_symbols': [...]},
            ...
          ],
          'numpy_version': str|None,
          'pandas_version': str|None,
          'yfinance_version': str|None,
          'requests_version': str|None,
        }
    """
    import importlib
    import sys

    targets = [
        ('bot_strategies', [
            'generate_strategy_profile', 'generate_trade_decisions',
            'compute_signal_score',
        ]),
        ('bot_behaviors', [
            'should_trade_today', 'get_trade_wave',
            'apply_human_biases', 'apply_fomo_trades',
        ]),
        ('bot_data_hub', ['MarketDataHub']),
    ]

    results = []
    all_ok = True
    for module_name, expected_symbols in targets:
        entry = {'name': module_name, 'ok': False, 'error': None,
                 'symbols_resolved': False, 'missing_symbols': []}
        try:
            # Force a fresh import to avoid cached partial-failure state.
            if module_name in sys.modules:
                mod = importlib.reload(sys.modules[module_name])
            else:
                mod = importlib.import_module(module_name)
            entry['ok'] = True
            missing = [s for s in expected_symbols if not hasattr(mod, s)]
            entry['missing_symbols'] = missing
            entry['symbols_resolved'] = len(missing) == 0
            if missing:
                all_ok = False
        except Exception as e:
            import traceback as _tb
            entry['error'] = f"{type(e).__name__}: {e}"
            entry['traceback'] = _tb.format_exc()[:2048]
            all_ok = False
        results.append(entry)

    # Also probe the heavy deps directly so we can tell numpy-missing from
    # something-else-missing in one glance.
    def _ver(mod_name):
        try:
            m = importlib.import_module(mod_name)
            return getattr(m, '__version__', '<no __version__>')
        except Exception as e:
            return f'<import failed: {type(e).__name__}: {e}>'

    return jsonify({
        'all_ok': all_ok,
        'imports': results,
        'numpy_version': _ver('numpy'),
        'pandas_version': _ver('pandas'),
        'yfinance_version': _ver('yfinance'),
        'requests_version': _ver('requests'),
        'next_step': (
            'Imports OK — wave failure must be downstream (hub.refresh / is_core_available). '
            'Check /api/cron/refresh-daily-bars and AV credentials.'
            if all_ok else
            'One or more imports broken — see imports[].error. If numpy_version starts '
            'with "<import failed", deploy bundle is missing numpy; check Vercel function '
            'size limits or requirements.txt.'
        ),
    })


@mobile_api.route('/admin/bot/last-wave-status', methods=['GET'])
@require_admin_2fa
@with_db_retry
def bot_last_wave_status():
    """Return the most recent BotWaveLog rows so the admin panel can show
    why bots did or didn't trade in each wave.

    Query params:
        limit (int, default 10, max 50) — how many recent waves to include

    Each row exposes:
        wave, started_at, finished_at, duration_ms, status, bots_*,
        trades_executed, data_quality, data_summary, decisions (list),
        errors (list), traceback_text (truncated to 4 KB).

    Status taxonomy:
        success | partial | no_data | error | running | skipped
    """
    from models import db, BotWaveLog
    from sqlalchemy import desc

    try:
        limit = min(int(request.args.get('limit', 10)), 50)
    except (TypeError, ValueError):
        limit = 10

    try:
        rows = (
            BotWaveLog.query
            .order_by(desc(BotWaveLog.started_at))
            .limit(limit)
            .all()
        )
    except Exception as e:
        logger.error(f"bot_last_wave_status query failed: {e}")
        return jsonify({'error': 'query_failed', 'detail': str(e)}), 500

    def _serialize(r):
        tb = r.traceback_text or None
        if tb and len(tb) > 4096:
            tb = tb[:4096] + '...[truncated]'
        return {
            'id': r.id,
            'wave': r.wave,
            'started_at': _utc_iso(r.started_at),
            'finished_at': _utc_iso(r.finished_at),
            'duration_ms': r.duration_ms,
            'status': r.status,
            'bots_checked': r.bots_checked,
            'bots_traded': r.bots_traded,
            'trades_executed': r.trades_executed,
            'data_quality': r.data_quality,
            'data_summary': r.data_summary,
            'decisions': r.decisions,
            'errors': r.errors,
            'traceback_text': tb,
        }

    return jsonify({'waves': [_serialize(r) for r in rows], 'count': len(rows)})


@mobile_api.route('/admin/bot/activity-feed', methods=['GET'])
@require_admin_2fa
@with_db_retry
def bot_activity_feed():
    """Recent activity across the platform for the admin dashboard."""
    from models import db, User, Transaction
    from sqlalchemy import desc, func
    
    limit = min(int(request.args.get('limit', 30)), 100)
    
    try:
        events = []
        
        # Recent trades (last 30)
        trades = db.session.query(Transaction, User).join(
            User, Transaction.user_id == User.id
        ).order_by(desc(Transaction.timestamp)).limit(limit).all()
        
        for txn, user in trades:
            display = getattr(user, 'public_name', None) or user.display_name or user.username
            events.append({
                'type': 'trade',
                'timestamp': _utc_iso(txn.timestamp),
                'user': user.username,
                'display_name': display,
                'user_id': user.id,
                'role': user.role or 'user',
                'detail': f"{txn.transaction_type.upper()} {txn.quantity} {txn.ticker} @ ${txn.price:.2f}" if txn.price else f"{txn.transaction_type.upper()} {txn.quantity} {txn.ticker}",
                'ticker': txn.ticker,
                'action': txn.transaction_type,
            })
        
        # Recent pending trades (table may not exist)
        try:
            from models import PendingTrade
            pending = PendingTrade.query.order_by(desc(PendingTrade.created_at)).limit(10).all()
            for pt in pending:
                events.append({
                    'type': 'pending_trade',
                    'timestamp': _utc_iso(pt.created_at),
                    'detail': f"{pt.action.upper()} {pt.quantity} {pt.ticker} — {pt.status}",
                    'status': pt.status,
                    'ticker': pt.ticker,
                })
        except Exception:
            pass
        
        # Sort all events by timestamp descending
        events.sort(key=lambda e: e.get('timestamp') or '', reverse=True)
        
        return jsonify({'events': events[:limit]})
    except Exception as e:
        logger.error(f"Activity feed error: {e}")
        return jsonify({'error': 'activity_feed_failed'}), 500


@mobile_api.route('/admin/bot/alert-summary', methods=['GET'])
@require_admin_2fa
@with_db_retry
def bot_alert_summary():
    """Get alert counts and health status for the admin dashboard."""
    from models import db, User, Transaction, PortfolioSnapshot
    from sqlalchemy import func, and_
    
    try:
        now = datetime.utcnow()
        today = now.date()
        
        # Unroutable / pending trades (table may not exist)
        pending_count = 0
        oldest_pending = None
        try:
            from models import PendingTrade
            pending_count = PendingTrade.query.filter(
                PendingTrade.status.in_(['pending', 'unroutable'])
            ).count()
            oldest_pending = PendingTrade.query.filter(
                PendingTrade.status.in_(['pending', 'unroutable'])
            ).order_by(PendingTrade.created_at.asc()).first()
        except Exception:
            pass
        
        # Bots with 0 trades today
        agent_ids = [u.id for u in User.query.filter_by(role='agent').all()]
        bots_with_trades_today = set()
        if agent_ids:
            rows = db.session.query(Transaction.user_id).filter(
                Transaction.user_id.in_(agent_ids),
                func.date(Transaction.timestamp) == today
            ).distinct().all()
            bots_with_trades_today = {r[0] for r in rows}
        
        active_bots = []
        for u in User.query.filter_by(role='agent').all():
            extra = u.extra_data or {}
            if extra.get('bot_active', True):
                active_bots.append(u.id)
        
        silent_bots = [bid for bid in active_bots if bid not in bots_with_trades_today]
        
        # Last bot trade
        last_agent_trade = db.session.query(Transaction).join(
            User, Transaction.user_id == User.id
        ).filter(User.role == 'agent').order_by(Transaction.timestamp.desc()).first()
        
        # Last snapshot (proxy for market-close cron health)
        last_snapshot = PortfolioSnapshot.query.order_by(
            PortfolioSnapshot.date.desc()
        ).first()
        
        alerts = []
        
        if pending_count > 0:
            alerts.append({
                'level': 'error',
                'title': f'{pending_count} unroutable trade(s)',
                'detail': f'Oldest: {oldest_pending.created_at.isoformat()}' if oldest_pending else '',
            })
        
        if len(silent_bots) > 0 and now.hour >= 14:  # only alert after market has been open a while
            alerts.append({
                'level': 'warning',
                'title': f'{len(silent_bots)} active bot(s) with 0 trades today',
                'detail': f'IDs: {silent_bots[:5]}',
            })
        
        if last_snapshot and (today - last_snapshot.date).days > 2:
            alerts.append({
                'level': 'error',
                'title': 'Market-close cron may be stale',
                'detail': f'Last snapshot: {last_snapshot.date.isoformat()}',
            })
        
        if not alerts:
            alerts.append({
                'level': 'ok',
                'title': 'All systems operational',
                'detail': '',
            })
        
        return jsonify({
            'alerts': alerts,
            'pending_trades': pending_count,
            'silent_bots': len(silent_bots),
            'last_bot_trade': last_agent_trade.timestamp.isoformat() if last_agent_trade and last_agent_trade.timestamp else None,
            'last_snapshot_date': last_snapshot.date.isoformat() if last_snapshot else None,
        })
    except Exception as e:
        logger.error(f"Alert summary error: {e}")
        return jsonify({'error': 'alert_summary_failed'}), 500


@mobile_api.route('/admin/bot/revenue-summary', methods=['GET'])
@require_admin_2fa
@with_db_retry
def bot_revenue_summary():
    """Revenue breakdown for the admin dashboard."""
    from models import db, User
    from sqlalchemy import func
    
    # Pricing constants (same as AdminSubscription model)
    price = 9.00
    store_fee_pct = 0.15
    platform_fee_pct = 0.15
    store_fee = round(price * store_fee_pct, 2)            # $1.35
    after_store = price * (1 - store_fee_pct)               # $7.65
    platform_cut = round(after_store * platform_fee_pct, 2) # $1.15
    influencer_pay = round(after_store * (1 - platform_fee_pct), 2)  # $6.50
    
    try:
        # Real subscriptions (table may not exist)
        real_subs = 0
        try:
            from models import MobileSubscription
            real_subs = MobileSubscription.query.filter_by(status='active').count()
        except Exception:
            pass
        
        # Per-user gifted breakdown (table may not exist)
        gifted_rows = []
        total_gifted = 0
        try:
            from models import AdminSubscription
            gifted_rows = AdminSubscription.query.filter(
                AdminSubscription.bonus_subscriber_count > 0
            ).all()
            total_gifted = sum(r.bonus_subscriber_count or 0 for r in gifted_rows)
        except Exception:
            pass
        
        # Per-influencer breakdown
        influencers = []
        for row in gifted_rows:
            user = User.query.get(row.portfolio_user_id)
            username = user.username if user else f'user_{row.portfolio_user_id}'
            is_bot = user and user.role == 'agent'
            
            # Count real subs for this user
            real_for_user = 0
            try:
                from models import MobileSubscription
                real_for_user = MobileSubscription.query.filter_by(
                    subscribed_to_id=row.portfolio_user_id, status='active'
                ).count()
            except Exception:
                pass
            
            gifted_for_user = row.bonus_subscriber_count or 0
            total_for_user = real_for_user + gifted_for_user
            influencers.append({
                'user_id': row.portfolio_user_id,
                'username': username,
                'is_company_bot': is_bot,
                'real_subs': real_for_user,
                'gifted_subs': gifted_for_user,
                'total_subs': total_for_user,
                'real_payout': 0.0 if is_bot else round(real_for_user * influencer_pay, 2),
                'gifted_payout': 0.0 if is_bot else round(gifted_for_user * influencer_pay, 2),
                'total_payout': 0.0 if is_bot else round(total_for_user * influencer_pay, 2),
            })
        
        # Also include users with real subs but no gifted record
        try:
            from models import MobileSubscription
            users_with_real = db.session.query(
                MobileSubscription.subscribed_to_id,
                func.count(MobileSubscription.id)
            ).filter_by(status='active').group_by(
                MobileSubscription.subscribed_to_id
            ).all()
            
            existing_ids = {i['user_id'] for i in influencers}
            for uid, cnt in users_with_real:
                if uid not in existing_ids:
                    user = User.query.get(uid)
                    is_bot = user and user.role == 'agent'
                    influencers.append({
                        'user_id': uid,
                        'username': user.username if user else f'user_{uid}',
                        'is_company_bot': is_bot,
                        'real_subs': cnt,
                        'gifted_subs': 0,
                        'total_subs': cnt,
                        'real_payout': 0.0 if is_bot else round(cnt * influencer_pay, 2),
                        'gifted_payout': 0,
                        'total_payout': 0.0 if is_bot else round(cnt * influencer_pay, 2),
                    })
        except Exception:
            pass
        
        # Mark bot-owned influencers in existing list too
        for inf in influencers:
            if 'is_company_bot' not in inf:
                user = User.query.get(inf['user_id'])
                inf['is_company_bot'] = user and user.role == 'agent'
                if inf['is_company_bot']:
                    inf['real_payout'] = 0.0
                    inf['gifted_payout'] = 0.0
                    inf['total_payout'] = 0.0
        
        # Compute bot-specific revenue summary
        bot_real_subs = sum(i['real_subs'] for i in influencers if i.get('is_company_bot'))
        bot_gifted_subs = sum(i['gifted_subs'] for i in influencers if i.get('is_company_bot'))
        human_real_subs = real_subs - bot_real_subs
        human_gifted_subs = total_gifted - bot_gifted_subs  # Only gifted to non-bot users generate payout
        
        bot_revenue = {
            'real_subs': bot_real_subs,
            'gifted_subs': bot_gifted_subs,
            'gross_revenue': round(bot_real_subs * price, 2),
            'store_fees': round(bot_real_subs * store_fee, 2),
            'company_keeps': round(bot_real_subs * (price - store_fee), 2),
            'note': 'No influencer payout — company retains full post-store revenue',
        }
        
        return jsonify({
            'real_subscriptions': real_subs,
            'gifted_subscriptions': total_gifted,
            'total_subscriptions': real_subs + total_gifted,
            'mrr': round(real_subs * price, 2),
            'store_fees': round(real_subs * store_fee, 2),
            'platform_revenue': round(real_subs * platform_cut, 2),
            'influencer_payouts_real': round(human_real_subs * influencer_pay, 2),
            'influencer_payouts_gifted': round(human_gifted_subs * influencer_pay, 2),
            'company_obligation': round(human_gifted_subs * influencer_pay, 2),
            'total_payout_obligation': round((human_real_subs + human_gifted_subs) * influencer_pay, 2),
            'bot_revenue': bot_revenue,
            'per_sub': {
                'price': price,
                'store_fee': store_fee,
                'platform_cut': platform_cut,
                'influencer_pay': influencer_pay,
            },
            'influencers': sorted(influencers, key=lambda x: x['total_subs'], reverse=True),
        })
    except Exception as e:
        logger.error(f"Revenue summary error: {e}")
        return jsonify({'error': 'revenue_summary_failed'}), 500


@mobile_api.route('/admin/bot/generate-payout-records', methods=['POST'])
@require_admin_2fa
@with_db_retry
def bot_generate_payout_records():
    """
    Generate month-end XeroPayoutRecord entries for all influencers.
    
    Creates one record per influencer with real + gifted subscriber counts,
    revenue split, and payout amounts. Idempotent — won't create duplicates
    for the same period.
    
    Request body:
    {
        "period_year": 2026,   (optional — defaults to current month)
        "period_month": 3      (optional — defaults to current month)
    }
    """
    from models import db, User, AdminSubscription, XeroPayoutRecord, MobileSubscription
    from sqlalchemy import func
    from calendar import monthrange
    
    data = request.get_json() or {}
    now = datetime.utcnow()
    year = data.get('period_year', now.year)
    month = data.get('period_month', now.month)
    
    period_start = date(year, month, 1)
    period_end = date(year, month, monthrange(year, month)[1])
    
    try:
        # Check for existing records this period (idempotent)
        existing = XeroPayoutRecord.query.filter_by(
            period_start=period_start,
            period_end=period_end
        ).count()
        
        if existing > 0:
            return jsonify({
                'error': 'payout_records_already_exist',
                'period': f'{period_start} to {period_end}',
                'existing_count': existing,
                'hint': 'Delete existing records first if you want to regenerate'
            }), 409
        
        records_created = []
        
        # Gather all users who have real or gifted subscribers
        # 1. Users with gifted subs
        gifted_map = {}
        gifted_rows = AdminSubscription.query.filter(
            AdminSubscription.bonus_subscriber_count > 0
        ).all()
        for row in gifted_rows:
            gifted_map[row.portfolio_user_id] = row.bonus_subscriber_count or 0
        
        # 2. Users with real subs
        real_map = {}
        try:
            real_counts = db.session.query(
                MobileSubscription.subscribed_to_id,
                func.count(MobileSubscription.id)
            ).filter_by(status='active').group_by(
                MobileSubscription.subscribed_to_id
            ).all()
            for uid, cnt in real_counts:
                real_map[uid] = cnt
        except Exception:
            pass
        
        # Combine all user IDs
        all_user_ids = set(gifted_map.keys()) | set(real_map.keys())
        
        for uid in all_user_ids:
            user = User.query.get(uid)
            if not user:
                continue
            
            # Skip company bots — they don't get paid
            is_bot = hasattr(user, 'role') and user.role == 'agent'
            if is_bot:
                continue
            
            real_count = real_map.get(uid, 0)
            bonus_count = gifted_map.get(uid, 0)
            
            if real_count == 0 and bonus_count == 0:
                continue
            
            record = XeroPayoutRecord(
                portfolio_user_id=uid,
                period_start=period_start,
                period_end=period_end,
                real_subscriber_count=real_count,
                bonus_subscriber_count=bonus_count,
                payment_status='pending',
            )
            record.calculate_totals()
            db.session.add(record)
            
            records_created.append({
                'user_id': uid,
                'username': user.username,
                'real_subs': real_count,
                'bonus_subs': bonus_count,
                'total_subs': record.total_subscriber_count,
                'influencer_payout': record.influencer_payout,
                'bonus_payout': record.bonus_payout,
                'total_payout': record.total_payout,
                'payment_status': record.payment_status,
            })
        
        db.session.commit()
        
        total_obligation = sum(r['total_payout'] for r in records_created)
        
        return jsonify({
            'success': True,
            'period': f'{period_start} to {period_end}',
            'records_created': len(records_created),
            'total_payout_obligation': round(total_obligation, 2),
            'records': sorted(records_created, key=lambda x: x['total_payout'], reverse=True),
        })
        
    except Exception as e:
        logger.error(f"Generate payout records error: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return jsonify({'error': 'generate_payout_failed'}), 500


@mobile_api.route('/admin/bot/payout-records', methods=['GET'])
@require_admin_2fa
@with_db_retry
def bot_list_payout_records():
    """
    List payout records, optionally filtered by period or payment status.
    
    Query params:
        year: filter by year (e.g., 2026)
        month: filter by month (e.g., 3)
        status: filter by payment_status ('pending', 'paid', 'held')
    """
    from models import db, User, XeroPayoutRecord
    
    year = request.args.get('year', type=int)
    month = request.args.get('month', type=int)
    status = request.args.get('status')
    
    try:
        query = XeroPayoutRecord.query
        
        if year and month:
            period_start = date(year, month, 1)
            query = query.filter_by(period_start=period_start)
        elif year:
            from sqlalchemy import extract
            query = query.filter(
                extract('year', XeroPayoutRecord.period_start) == year
            )
        
        if status:
            query = query.filter_by(payment_status=status)
        
        records = query.order_by(XeroPayoutRecord.period_start.desc()).all()
        
        result = []
        for r in records:
            user = User.query.get(r.portfolio_user_id)
            result.append({
                'id': r.id,
                'user_id': r.portfolio_user_id,
                'username': user.username if user else f'user_{r.portfolio_user_id}',
                'period': f'{r.period_start} to {r.period_end}',
                'real_subs': r.real_subscriber_count,
                'bonus_subs': r.bonus_subscriber_count,
                'total_subs': r.total_subscriber_count,
                'gross_revenue': r.gross_revenue,
                'store_fees': r.store_fees,
                'platform_revenue': r.platform_revenue,
                'influencer_payout': r.influencer_payout,
                'bonus_payout': r.bonus_payout,
                'total_payout': r.total_payout,
                'payment_status': r.payment_status,
                'paid_at': r.paid_at.isoformat() if r.paid_at else None,
                'xero_sync_status': r.xero_sync_status,
            })
        
        return jsonify({
            'records': result,
            'total_count': len(result),
            'total_obligation': round(sum(r['total_payout'] for r in result), 2),
        })
    except Exception as e:
        logger.error(f"List payout records error: {e}")
        return jsonify({'error': 'list_payout_records_failed'}), 500


@mobile_api.route('/admin/bot/payout-records/<int:record_id>/mark-paid', methods=['POST'])
@require_admin_2fa
@with_db_retry
def bot_mark_payout_paid(record_id):
    """Mark a payout record as paid (after writing the check)."""
    from models import db, XeroPayoutRecord
    
    try:
        record = XeroPayoutRecord.query.get(record_id)
        if not record:
            return jsonify({'error': 'record_not_found'}), 404
        
        record.payment_status = 'paid'
        record.paid_at = datetime.utcnow()
        db.session.commit()
        
        return jsonify({
            'success': True,
            'record_id': record.id,
            'payment_status': 'paid',
            'paid_at': record.paid_at.isoformat(),
        })
    except Exception as e:
        logger.error(f"Mark payout paid error: {e}")
        return jsonify({'error': 'mark_paid_failed'}), 500


# ── Xero OAuth + Sync Routes ───────────────────────────────────────────────

@mobile_api.route('/admin/xero/connect', methods=['GET'])
def xero_connect():
    """Start Xero OAuth2 flow — redirects admin to Xero login.
    
    Auth: Flask admin session only (browser redirect — can't use API key headers).
    """
    from flask import session, redirect
    import xero_service
    
    if not _is_admin_session():
        return jsonify({'error': 'admin_session_required', 'message': 'Log in as admin first'}), 403
    
    url, state, code_verifier = xero_service.get_authorization_url()
    session['xero_oauth_state'] = state
    session['xero_code_verifier'] = code_verifier
    return redirect(url)


@mobile_api.route('/admin/xero/callback', methods=['GET'])
def xero_callback():
    """Handle Xero OAuth2 callback after admin authorizes.
    
    Auth: CSRF state token (set during /connect, verified here).
    No decorator — Xero redirects the browser here directly.
    """
    from flask import session, redirect
    import xero_service
    
    # Verify CSRF state (proves this callback was initiated by our /connect route)
    state = request.args.get('state')
    stored_state = session.pop('xero_oauth_state', None)
    if not state or not stored_state or state != stored_state:
        return jsonify({'error': 'invalid_state', 'message': 'CSRF state mismatch — try connecting again'}), 400
    
    # Check for errors from Xero
    error = request.args.get('error')
    if error:
        error_desc = request.args.get('error_description', 'Unknown error')
        return jsonify({'error': error, 'message': error_desc}), 400
    
    code = request.args.get('code')
    if not code:
        return jsonify({'error': 'missing_code'}), 400
    
    code_verifier = session.pop('xero_code_verifier', None)
    token = xero_service.exchange_code_for_token(code, code_verifier=code_verifier)
    if not token:
        return jsonify({'error': 'token_exchange_failed', 'message': 'Failed to exchange code for token — check logs'}), 500
    
    return jsonify({
        'success': True,
        'message': 'Xero connected successfully',
        'tenant_id': token.tenant_id,
        'expires_at': token.expires_at.isoformat(),
    })


@mobile_api.route('/admin/xero/status', methods=['GET'])
@require_admin_2fa
def xero_status():
    """Check current Xero connection status."""
    import xero_service
    return jsonify(xero_service.get_xero_status())


@mobile_api.route('/admin/xero/sync-payouts', methods=['POST'])
@require_admin_2fa
@with_db_retry
def xero_sync_payouts():
    """Sync pending XeroPayoutRecord entries as bills in Xero.
    
    Request body (optional):
    {
        "period_year": 2026,
        "period_month": 3
    }
    If omitted, syncs ALL pending records.
    """
    import xero_service
    from calendar import monthrange
    
    data = request.get_json() or {}
    year = data.get('period_year')
    month = data.get('period_month')
    
    period_start = None
    period_end = None
    if year and month:
        period_start = date(year, month, 1)
        period_end = date(year, month, monthrange(year, month)[1])
    
    result = xero_service.sync_payout_records_to_xero(
        period_start=period_start,
        period_end=period_end,
    )
    
    if 'error' in result:
        return jsonify(result), 400
    
    return jsonify({
        'success': True,
        'synced_count': len(result['synced']),
        'failed_count': len(result['failed']),
        'skipped_count': result['skipped'],
        'total_amount': round(result['total_amount'], 2),
        'synced': result['synced'],
        'failed': result['failed'],
    })


@mobile_api.route('/admin/xero/disconnect', methods=['POST'])
@require_admin_2fa
def xero_disconnect():
    """Remove stored Xero tokens (disconnect)."""
    from models import db, XeroOAuthToken
    
    token = XeroOAuthToken.query.first()
    if token:
        db.session.delete(token)
        db.session.commit()
        return jsonify({'success': True, 'message': 'Xero disconnected'})
    
    return jsonify({'success': True, 'message': 'No Xero connection to disconnect'})


@mobile_api.route('/admin/bot/cron-health', methods=['GET'])
@require_admin_2fa
@with_db_retry
def bot_cron_health():
    """Check health of cron jobs based on data freshness."""
    from models import db, PortfolioSnapshot, PortfolioSnapshotIntraday, Transaction, User
    from sqlalchemy import func, desc
    
    try:
        now = datetime.utcnow()
        today = now.date()
        
        # Last portfolio snapshot (market-close cron)
        last_snap = PortfolioSnapshot.query.order_by(PortfolioSnapshot.date.desc()).first()
        
        # Last intraday snapshot
        last_intraday = None
        try:
            last_intraday = PortfolioSnapshotIntraday.query.order_by(
                desc(PortfolioSnapshotIntraday.timestamp)
            ).first()
        except Exception:
            pass
        
        # Last bot trade (proxy for bot trading waves)
        last_bot_trade = db.session.query(Transaction).join(
            User, Transaction.user_id == User.id
        ).filter(User.role == 'agent').order_by(desc(Transaction.timestamp)).first()
        
        # Last pending trade processed (table may not exist)
        last_routed = None
        try:
            from models import PendingTrade
            last_routed = PendingTrade.query.filter_by(status='routed').order_by(
                desc(PendingTrade.routed_at)
            ).first()
        except Exception:
            pass
        
        jobs = []
        
        # Helper: determine if today is a weekday (market day)
        is_weekday = now.weekday() < 5  # Mon-Fri
        
        # Helper: get last market day
        def get_last_market_day():
            d = today
            if now.hour < 21:  # Before 9 PM UTC (5 PM ET) — market close hasn't run yet today
                d = d - timedelta(days=1)
            while d.weekday() >= 5:  # Skip weekends
                d -= timedelta(days=1)
            return d
        
        last_market_day = get_last_market_day()
        
        # Market Close — should have a snapshot for the last market day
        # Return a full datetime (not just date) so JS doesn't misinterpret timezone.
        # The market-close cron runs at 20:05 UTC (4:05 PM ET).
        if last_snap:
            # Naive UTC → 'Z'-suffixed ISO so the admin panel JS
            # (`new Date(...)`) parses it as UTC, not local. Without the Z
            # the timestamp gets shifted by the viewer's tz offset (the
            # '8 PM instead of 4 PM ET' bug).
            snap_date = _utc_iso(datetime.combine(last_snap.date, datetime.min.time().replace(hour=20, minute=5)))
        else:
            snap_date = None
        if last_snap:
            days_since = (last_market_day - last_snap.date).days
            if days_since <= 0:
                snap_status = 'ok'
            elif days_since <= 1:
                snap_status = 'warning'  # Missed 1 day
            else:
                snap_status = 'error'    # Missed 2+ days
        else:
            snap_status = 'error'
        jobs.append({
            'name': 'Market Close Snapshots',
            'schedule': '4:05 PM ET weekdays',
            'last_run': snap_date,
            'status': snap_status,
        })
        
        # Intraday Collection — should run every 15 min during market hours
        intraday_ts = _utc_iso(last_intraday.timestamp) if last_intraday and hasattr(last_intraday, 'timestamp') and last_intraday.timestamp else None
        if last_intraday and last_intraday.timestamp:
            # During market hours (Mon-Fri 13:30-20:00 UTC), stale if >30 min old
            hours_since = (now - last_intraday.timestamp).total_seconds() / 3600
            in_market_hours = is_weekday and 13.5 <= now.hour + now.minute/60 <= 20.5
            if in_market_hours:
                intraday_status = 'ok' if hours_since < 0.5 else ('warning' if hours_since < 1 else 'error')
            else:
                # Outside market hours — ok if last run was today or last market day
                intraday_status = 'ok' if last_intraday.timestamp.date() >= last_market_day else 'warning'
        else:
            intraday_status = 'error' if is_weekday else 'unknown'
        jobs.append({
            'name': 'Intraday Collection',
            'schedule': 'Every 15min during market hours',
            'last_run': intraday_ts,
            'status': intraday_status,
        })
        
        # Bot Trading Waves — should trade on market days
        bot_ts = _utc_iso(last_bot_trade.timestamp) if last_bot_trade and last_bot_trade.timestamp else None
        if last_bot_trade and last_bot_trade.timestamp:
            days_since_trade = (today - last_bot_trade.timestamp.date()).days
            if days_since_trade <= 0:
                bot_status = 'ok'
            elif days_since_trade <= 1:
                # Only warn on weekdays (no trades expected on weekends)
                bot_status = 'ok' if not is_weekday else 'warning'
            else:
                bot_status = 'error'
        else:
            bot_status = 'error' if is_weekday else 'unknown'
        jobs.append({
            'name': 'Bot Trading Waves',
            # Configured cron times in ET. GitHub Actions free-tier
            # routinely drifts 30-60 min late on scheduled runs, so the
            # actual trade timestamps in 'Bot Wave Diagnostics' below
            # will not match these times exactly. This is a known GH
            # platform limitation, not a bug in our code. (See
            # bot-trading.yml for the full schedule.)
            'schedule': 'Scheduled 9:45, 10:45, 1:15, 3:30 ET (GH cron drifts up to ~60min)',
            'last_run': bot_ts,
            'status': bot_status,
        })
        
        # Pending Trade Retry
        routed_ts = _utc_iso(last_routed.routed_at) if last_routed and last_routed.routed_at else None
        if last_routed and last_routed.routed_at:
            days_since_route = (today - last_routed.routed_at.date()).days
            pending_status = 'ok' if days_since_route <= 3 else 'warning'
        else:
            pending_status = 'unknown'
        jobs.append({
            'name': 'Pending Trade Retry',
            'schedule': 'Every 5min (Google Apps Script)',
            'last_run': routed_ts,
            'status': pending_status,
        })
        
        # ── Market Research Data Quality ──
        data_sources = []
        try:
            from models import AlphaVantageAPILog
            import os
            from sqlalchemy import func as sqlfunc
            
            # Check last 24 hours of API calls
            cutoff = now - timedelta(hours=24)
            
            # AlphaVantage news sentiment
            news_calls = AlphaVantageAPILog.query.filter(
                AlphaVantageAPILog.endpoint == 'NEWS_SENTIMENT',
                AlphaVantageAPILog.timestamp >= cutoff
            ).all()
            news_ok = sum(1 for c in news_calls if c.response_status == 'success')
            data_sources.append({
                'name': 'AlphaVantage News', 'type': 'news_sentiment',
                'calls_24h': len(news_calls), 'successes': news_ok,
                'status': 'active' if news_ok > 0 else ('error' if len(news_calls) > 0 else 'no_calls'),
                'avg_latency_ms': round(sum(c.response_time_ms or 0 for c in news_calls) / max(len(news_calls), 1)),
            })
            
            # AlphaVantage top movers
            mover_calls = AlphaVantageAPILog.query.filter(
                AlphaVantageAPILog.endpoint == 'TOP_GAINERS_LOSERS',
                AlphaVantageAPILog.timestamp >= cutoff
            ).all()
            mover_ok = sum(1 for c in mover_calls if c.response_status == 'success')
            data_sources.append({
                'name': 'AlphaVantage Movers', 'type': 'top_movers',
                'calls_24h': len(mover_calls), 'successes': mover_ok,
                'status': 'active' if mover_ok > 0 else ('error' if len(mover_calls) > 0 else 'no_calls'),
            })
            
            # AlphaVantage price fallback
            price_calls = AlphaVantageAPILog.query.filter(
                AlphaVantageAPILog.endpoint == 'TIME_SERIES_DAILY',
                AlphaVantageAPILog.timestamp >= cutoff
            ).all()
            price_ok = sum(1 for c in price_calls if c.response_status == 'success')
            data_sources.append({
                'name': 'AlphaVantage Prices (fallback)', 'type': 'price_fallback',
                'calls_24h': len(price_calls), 'successes': price_ok,
                'status': 'active' if price_ok > 0 else 'idle',
            })
            
            # yfinance (primary price source) — no direct logging, but infer from whether
            # bots have indicator data (they do if prices loaded)
            data_sources.append({
                'name': 'yfinance (primary prices)', 'type': 'yfinance',
                'calls_24h': None,  # No per-call logging for yfinance
                'status': 'active' if bot_status in ('ok', 'warning') else 'unknown',
                'note': 'Primary price + OHLCV source; no per-call tracking',
            })
            
            # Finnhub — actually probe each endpoint instead of just checking
            # the env var. Cached for 6h so we don't hammer the API on every
            # admin page load. Each endpoint becomes its own card row so the
            # admin can see at a glance which signals are live and which are
            # blocked by the free-tier paywall.
            try:
                from bot_data_hub import probe_finnhub_health
                health = probe_finnhub_health()
                ep = (health or {}).get('endpoints', {}) or {}
                last_probe_iso = None
                if health and health.get('last_probe_at'):
                    try:
                        last_probe_iso = datetime.utcfromtimestamp(health['last_probe_at']).isoformat() + 'Z'
                    except Exception:
                        last_probe_iso = None

                # Map probe statuses to the card's status vocabulary.
                # 'active' / 'empty' → active (endpoint reachable + working)
                # 'forbidden' → error (paywalled — clearly not working for us)
                # 'rate_limited' / 'error' → error
                # 'missing_key' → missing_key
                def _probe_card_status(probe_status):
                    if probe_status in ('active', 'empty'):
                        return 'active'
                    if probe_status == 'missing_key':
                        return 'missing_key'
                    return 'error'

                def _ep_entry(label, probe_key):
                    p = ep.get(probe_key, {}) or {}
                    note_parts = []
                    if p.get('note'):
                        note_parts.append(p['note'])
                    if p.get('latency_ms') is not None:
                        note_parts.append(f"{p['latency_ms']}ms")
                    if last_probe_iso:
                        note_parts.append(f"probed {last_probe_iso}")
                    return {
                        'name': label,
                        'type': f'finnhub_{probe_key}',
                        'calls_24h': None,
                        'status': _probe_card_status(p.get('status', 'unknown')),
                        'http_status': p.get('http_status'),
                        'note': ' · '.join(note_parts) if note_parts else None,
                    }

                data_sources.append(_ep_entry('Finnhub: Insider Transactions', 'insider'))
                data_sources.append(_ep_entry('Finnhub: Social Sentiment',     'social'))
                data_sources.append(_ep_entry('Finnhub: Analyst Recommendations', 'analyst'))
            except Exception as fh_err:
                logger.warning(f"Finnhub health probe failed: {fh_err}")
                # Fall back to the old env-var check so the card isn't empty.
                finnhub_key = os.environ.get('FINNHUB_API_KEY', '')
                data_sources.append({
                    'name': 'Finnhub', 'type': 'finnhub',
                    'calls_24h': None,
                    'status': 'configured' if finnhub_key else 'missing_key',
                    'note': f'Probe failed: {fh_err}' if finnhub_key else 'FINNHUB_API_KEY not set in env vars',
                })
        except Exception as dq_err:
            logger.warning(f"Data quality check error: {dq_err}")
        
        # ── Data-source → trade attribution ──────────────────────────────────
        # Connects the green-light sources above to reality: how many recent bot
        # trades did each source actually inform? Bot trades carry
        # price_source='bot_<signal_tag>' (bot_news, bot_rsi, bot_insider, ...),
        # set from the dominant signal component at decision time. A source
        # that's "active" but informed 0 trades is effectively a dead leg (e.g.
        # Finnhub social on the free tier) — exactly the gap we need to see.
        try:
            # NOTE: do NOT `from datetime import timedelta` here — `timedelta`
            # is already module-level imported and used earlier in this
            # function (get_last_market_day, the 24h data-quality cutoff). A
            # local import would make `timedelta` a function-local for the
            # WHOLE scope, raising UnboundLocalError at those earlier uses and
            # 500-ing the endpoint (which blanks the entire System Health tab).
            cutoff_7d = now - timedelta(days=7)
            cutoff_1d = now - timedelta(days=1)
            bot_ids = [bid for (bid,) in db.session.query(User.id).filter(User.role == 'agent').all()]
            by_tag_7d, by_tag_1d = {}, {}
            if bot_ids:
                rows = db.session.query(
                    Transaction.price_source, Transaction.timestamp
                ).filter(
                    Transaction.user_id.in_(bot_ids),
                    Transaction.timestamp >= cutoff_7d,
                ).all()
                for ps, ts in rows:
                    if not ps or not ps.startswith('bot_'):
                        continue
                    tag = ps[4:]
                    by_tag_7d[tag] = by_tag_7d.get(tag, 0) + 1
                    if ts and ts >= cutoff_1d:
                        by_tag_1d[tag] = by_tag_1d.get(tag, 0) + 1

            # Map each data-source 'type' to the signal_tag(s) it feeds. Note:
            # the AV 'price_fallback' row is intentionally unmapped to avoid
            # double-counting indicator trades already attributed to yfinance.
            source_tags = {
                'news_sentiment': ('news',),
                'top_movers': ('mover',),
                'yfinance': ('rsi', 'macd', 'volume', 'trend'),
                'insider': ('insider',),
                'analyst': ('analyst',),
                'social': ('social',),
                'finnhub': ('insider', 'analyst', 'social'),  # combined fallback row
            }
            for src in data_sources:
                tags = source_tags.get(src.get('type'))
                if not tags:
                    continue
                src['trades_7d'] = sum(by_tag_7d.get(t, 0) for t in tags)
                src['trades_today'] = sum(by_tag_1d.get(t, 0) for t in tags)
        except Exception as attr_err:
            logger.warning(f"Trade attribution failed: {attr_err}")
        
        return jsonify({'jobs': jobs, 'data_sources': data_sources, 'server_time': _utc_iso(now)})
    except Exception as e:
        logger.error(f"Cron health error: {e}")
        return jsonify({'error': 'cron_health_failed'}), 500


@mobile_api.route('/admin/bot/trade-history', methods=['GET'])
@require_admin_2fa
@with_db_retry
def bot_trade_history():
    """Paginated trade history with filtering for the admin dashboard."""
    from models import db, User, Transaction
    from sqlalchemy import desc
    
    try:
        page = max(1, int(request.args.get('page', 1)))
        per_page = min(int(request.args.get('per_page', 50)), 200)
        role_filter = request.args.get('role')  # 'agent', 'user', or None for all
        user_id_filter = request.args.get('user_id')
        ticker_filter = request.args.get('ticker')
        
        query = db.session.query(Transaction, User).join(
            User, Transaction.user_id == User.id
        )
        
        if role_filter:
            query = query.filter(User.role == role_filter)
        if user_id_filter:
            query = query.filter(Transaction.user_id == int(user_id_filter))
        if ticker_filter:
            query = query.filter(Transaction.ticker == ticker_filter.upper())
        
        total = query.count()
        trades = query.order_by(desc(Transaction.timestamp)).offset(
            (page - 1) * per_page
        ).limit(per_page).all()
        
        results = []
        for txn, user in trades:
            # public_name = display_name when set, else username. Admin UI
            # should render this so bots show as "Wolff's Flagship Fund"
            # rather than "CoastHillBear". `username` kept for compat /
            # disambiguation (e.g., search, gift-modal target).
            display = getattr(user, 'public_name', None) or user.display_name or user.username
            results.append({
                'id': txn.id,
                'user_id': user.id,
                'username': user.username,
                'display_name': display,
                'role': user.role or 'user',
                'ticker': txn.ticker,
                'quantity': txn.quantity,
                'price': txn.price,
                'type': txn.transaction_type,
                'timestamp': _utc_iso(txn.timestamp),
                'value': round(txn.quantity * txn.price, 2) if txn.price else 0,
                'price_source': getattr(txn, 'price_source', None) or '—',
            })
        
        return jsonify({
            'trades': results,
            'total': total,
            'page': page,
            'per_page': per_page,
            'pages': (total + per_page - 1) // per_page,
        })
    except Exception as e:
        logger.error(f"Trade history error: {e}")
        return jsonify({'error': 'trade_history_failed'}), 500


# ── Batch Bot Seed & Auto-Creation ───────────────────────────────────────────

@mobile_api.route('/admin/bot/batch-seed', methods=['POST'])
@require_admin_2fa
@with_db_retry
def bot_batch_seed():
    """
    Create multiple bots at once with strategy profiles and initial portfolios.
    Reuses bot_personas + bot_executor logic server-side.
    
    Request body:
    {
        "count": 5,
        "strategy": "momentum",   // optional — random if omitted
        "industry": "Technology"   // optional — random if omitted
    }
    """
    from models import db, User
    
    data = request.get_json() or {}
    count = min(data.get('count', 1), 100)  # Cap at 100 per request
    strategy = data.get('strategy')
    industry = data.get('industry')
    
    if count < 1:
        return jsonify({'error': 'count must be >= 1'}), 400
    
    try:
        from bot_personas import generate_bot_persona, generate_bot_batch
        from bot_strategies import STRATEGY_TEMPLATES, generate_strategy_profile
    except ImportError as ie:
        logger.error(f"Bot modules not available: {ie}")
        return jsonify({'error': 'bot_modules_unavailable', 'detail': str(ie)}), 500
    
    # Validate strategy if provided
    if strategy and strategy not in STRATEGY_TEMPLATES:
        return jsonify({'error': 'invalid_strategy', 'valid': list(STRATEGY_TEMPLATES.keys())}), 400
    
    created = []
    errors = []
    
    personas = generate_bot_batch(count, industry=industry, strategy=strategy)
    
    for i, persona in enumerate(personas):
        username = persona['username']
        email = persona['email']
        ind = persona['industry']
        strat = persona['strategy_name']
        profile = persona['strategy_profile']
        sub_count = persona.get('subscriber_count', 0)
        
        try:
            # Check for existing user
            existing = User.query.filter(
                (User.username == username) | (User.email == email)
            ).first()
            if existing:
                # Append random suffix
                import random as _rnd
                username = username + str(_rnd.randint(100, 999))
                email = f"{username.replace('-', '.').replace('_', '.')}@apestogether.ai"
            
            user = User(
                username=username,
                email=email,
                portfolio_slug=_generate_portfolio_slug(),
                role='agent',
                created_by='system',
                subscription_price=9.00,
                extra_data={
                    'industry': ind,
                    'bot_active': True,
                    'bot_created_at': datetime.utcnow().isoformat(),
                    'trading_style': strat,
                    'strategy_profile': profile,
                }
            )
            db.session.add(user)
            db.session.flush()  # Get user.id
            
            user_id = user.id
            
            # Seed initial portfolio using attention universe + real prices
            stock_count = 0
            attention = profile.get('attention_universe', [])
            if attention:
                stock_count = _seed_bot_portfolio(user_id, profile, attention)
            
            # Gift initial subscribers
            gifted = 0
            if sub_count > 0:
                gifted = _gift_bot_subscribers(user_id, sub_count)
            
            created.append({
                'user_id': user_id,
                'username': username,
                'industry': ind,
                'strategy': strat,
                'stocks_seeded': stock_count,
                'subscribers_gifted': gifted,
            })
            
        except Exception as e:
            logger.error(f"Batch seed error for {username}: {e}")
            errors.append({'username': username, 'error': str(e)})
    
    db.session.commit()
    
    return jsonify({
        'success': True,
        'created': len(created),
        'requested': count,
        'bots': created,
        'errors': errors,
    })


def _seed_bot_portfolio(user_id, profile, attention):
    """Seed a bot's initial portfolio with stocks from its attention universe.

    CRITICAL: Each holding goes through process_transaction() with type='initial' so:
      - A Transaction row is created (required for replay-based reconciliation)
      - user.max_cash_deployed is incremented by the purchase value
      - user.cash_proceeds stays at 0 (no proceeds from initial seeding)

    Without this, a newly-seeded bot has Stock rows but max_cash_deployed=0, which
    breaks Modified Dietz on its first chart render and causes drift visible in
    the leaderboard.
    """
    from models import db, Stock
    from cash_tracking import process_transaction
    import random as _rnd

    num_stocks = _rnd.randint(4, min(10, len(attention)))
    selected = _rnd.sample(attention, num_stocks)

    # Log-normal portfolio size: median ~$40K, range $5K–$500K
    raw = _rnd.lognormvariate(10.6, 0.9)
    portfolio_size = max(5_000, min(500_000, raw))

    added = 0
    for ticker in selected:
        try:
            price = _get_approximate_price(ticker)
            if price <= 0:
                continue

            allocation = portfolio_size / num_stocks
            qty = max(1, int(allocation / price))
            qty = max(1, int(qty * _rnd.uniform(0.7, 1.3)))
            if qty > 20:
                qty = round(qty / 5) * 5
            elif qty > 10:
                qty = round(qty / 2) * 2

            price_noise = _rnd.uniform(-0.02, 0.02)
            purchase_price = round(price * (1 + price_noise), 2)
            ticker_upper = ticker.upper()

            # 1. Create or update the Stock holding
            existing = Stock.query.filter_by(user_id=user_id, ticker=ticker_upper).first()
            if existing:
                total_cost = (existing.purchase_price * existing.quantity) + (purchase_price * qty)
                existing.quantity += qty
                existing.purchase_price = total_cost / existing.quantity if existing.quantity > 0 else purchase_price
            else:
                stock = Stock(
                    user_id=user_id,
                    ticker=ticker_upper,
                    quantity=qty,
                    purchase_price=purchase_price,
                    purchase_date=datetime.utcnow().date(),
                )
                db.session.add(stock)

            # 2. Record transaction + increment user.max_cash_deployed via process_transaction
            #    Type 'initial' is treated like a buy for cash-tracking purposes.
            process_transaction(
                db, user_id, ticker_upper, qty, purchase_price, 'initial',
                timestamp=datetime.utcnow()
            )
            added += 1
        except Exception as e:
            logger.debug(f"Skip seeding {ticker} for user {user_id}: {e}")

    return added


def _get_approximate_price(ticker):
    """Get an approximate stock price. Uses MarketData cache or hardcoded fallbacks."""
    try:
        from models import MarketData
        md = MarketData.query.filter_by(ticker=ticker.upper()).first()
        if md and md.current_price and md.current_price > 0:
            return float(md.current_price)
    except Exception:
        pass
    
    # Fallback: approximate prices for common tickers
    APPROX = {
        'AAPL': 195, 'MSFT': 420, 'GOOGL': 175, 'AMZN': 185, 'NVDA': 880,
        'META': 500, 'TSLA': 175, 'JPM': 195, 'V': 280, 'JNJ': 155,
        'UNH': 520, 'XOM': 105, 'PG': 165, 'MA': 460, 'HD': 370,
        'COST': 730, 'ABBV': 170, 'MRK': 125, 'CRM': 270, 'PEP': 175,
        'KO': 60, 'LLY': 780, 'AVGO': 1350, 'TMO': 560, 'ACN': 340,
        'MCD': 280, 'CSCO': 50, 'ABT': 110, 'DHR': 250, 'TXN': 170,
        'NEE': 75, 'PM': 95, 'WMT': 170, 'DIS': 110, 'NKE': 95,
        'INTC': 30, 'AMD': 160, 'QCOM': 170, 'BA': 190, 'GS': 380,
        'SPY': 510, 'QQQ': 440, 'IWM': 205, 'VTI': 260,
    }
    return APPROX.get(ticker.upper(), 100)  # Default $100 for unknowns


def _gift_bot_subscribers(user_id, count):
    """Gift subscribers to a bot during batch creation."""
    from models import db, AdminSubscription, UserPortfolioStats
    
    try:
        admin_sub = AdminSubscription.query.filter_by(user_id=user_id).first()
        if not admin_sub:
            admin_sub = AdminSubscription(user_id=user_id, bonus_subscriber_count=0)
            db.session.add(admin_sub)
        
        admin_sub.bonus_subscriber_count = (admin_sub.bonus_subscriber_count or 0) + count
        
        # Update stats
        stats = UserPortfolioStats.query.filter_by(user_id=user_id).first()
        if not stats:
            stats = UserPortfolioStats(user_id=user_id, subscriber_count=0)
            db.session.add(stats)
        stats.subscriber_count = (stats.subscriber_count or 0) + count
        
        return count
    except Exception as e:
        logger.error(f"Gift subscribers error for user {user_id}: {e}")
        return 0


@mobile_api.route('/admin/bot/auto-create-settings', methods=['GET'])
@require_admin_2fa
@with_db_retry
def bot_auto_create_settings_get():
    """Get the current auto-creation settings."""
    from models import db
    
    try:
        # Store settings in a simple key-value approach using the database
        # We'll use a settings row in a lightweight way
        settings = _get_auto_create_settings()
        return jsonify({'success': True, **settings})
    except Exception as e:
        logger.error(f"Get auto-create settings error: {e}")
        return jsonify({'error': str(e)}), 500


@mobile_api.route('/admin/bot/auto-create-settings', methods=['POST'])
@require_admin_2fa
@with_db_retry
def bot_auto_create_settings_set():
    """
    Update auto-creation settings.
    
    Request body:
    {
        "enabled": true,
        "daily_count": 3,
        "strategy": "random",     // or specific archetype name
        "industry": "random"      // or specific industry
    }
    """
    from models import db
    
    data = request.get_json() or {}
    
    try:
        settings = _get_auto_create_settings()
        
        if 'enabled' in data:
            settings['enabled'] = bool(data['enabled'])
        if 'daily_count' in data:
            settings['daily_count'] = max(0, min(100, int(data['daily_count'])))
        if 'strategy' in data:
            settings['strategy'] = data['strategy'] if data['strategy'] != 'random' else None
        if 'industry' in data:
            settings['industry'] = data['industry'] if data['industry'] != 'random' else None
        
        _save_auto_create_settings(settings)
        
        return jsonify({'success': True, **settings})
    except Exception as e:
        logger.error(f"Save auto-create settings error: {e}")
        return jsonify({'error': str(e)}), 500


@mobile_api.route('/admin/bot/auto-create-run', methods=['POST'])
@require_cron_secret
@with_db_retry
def bot_auto_create_run():
    """
    Cron-triggered endpoint: create bots according to auto-creation settings.
    Called daily by an external scheduler (e.g., Vercel cron, GAS timer).
    Only creates bots if auto-creation is enabled.
    """
    settings = _get_auto_create_settings()
    
    if not settings.get('enabled'):
        return jsonify({'success': True, 'message': 'Auto-creation is disabled', 'created': 0})
    
    count = settings.get('daily_count', 0)
    if count <= 0:
        return jsonify({'success': True, 'message': 'daily_count is 0', 'created': 0})
    
    from models import db, User
    try:
        from bot_personas import generate_bot_batch
        from bot_strategies import STRATEGY_TEMPLATES
    except ImportError as ie:
        return jsonify({'error': 'bot_modules_unavailable', 'detail': str(ie)}), 500
    
    strategy = settings.get('strategy')
    industry = settings.get('industry')
    
    if strategy and strategy not in STRATEGY_TEMPLATES:
        strategy = None
    
    personas = generate_bot_batch(count, industry=industry, strategy=strategy)
    created = []
    
    for persona in personas:
        username = persona['username']
        email = persona['email']
        ind = persona['industry']
        strat = persona['strategy_name']
        profile = persona['strategy_profile']
        sub_count = persona.get('subscriber_count', 0)
        
        try:
            existing = User.query.filter(
                (User.username == username) | (User.email == email)
            ).first()
            if existing:
                import random as _rnd
                username = username + str(_rnd.randint(100, 999))
                email = f"{username.replace('-', '.').replace('_', '.')}@apestogether.ai"
            
            user = User(
                username=username, email=email,
                portfolio_slug=_generate_portfolio_slug(),
                role='agent', created_by='system', subscription_price=9.00,
                extra_data={
                    'industry': ind, 'bot_active': True,
                    'bot_created_at': datetime.utcnow().isoformat(),
                    'trading_style': strat, 'strategy_profile': profile,
                }
            )
            db.session.add(user)
            db.session.flush()
            
            stock_count = 0
            attention = profile.get('attention_universe', [])
            if attention:
                stock_count = _seed_bot_portfolio(user.id, profile, attention)
            
            gifted = _gift_bot_subscribers(user.id, sub_count) if sub_count > 0 else 0
            
            created.append({
                'user_id': user.id, 'username': username,
                'strategy': strat, 'industry': ind,
            })
        except Exception as e:
            logger.error(f"Auto-create error for {username}: {e}")
    
    db.session.commit()
    
    # Log the auto-creation event — _utc_iso so admin panel renders ET
    # correctly (see _utc_iso docstring for the non-Z parsing footgun).
    _save_auto_create_settings({**settings, 'last_run': _utc_iso(datetime.utcnow()), 'last_created': len(created)})
    
    return jsonify({
        'success': True,
        'created': len(created),
        'bots': created,
    })


# ── Auto-creation settings helpers (stored in environment/DB) ────────────────

_AUTO_CREATE_CACHE = {}

def _get_auto_create_settings():
    """Load auto-creation settings. Uses in-memory cache backed by User extra_data on admin account."""
    global _AUTO_CREATE_CACHE
    if _AUTO_CREATE_CACHE:
        return dict(_AUTO_CREATE_CACHE)
    
    try:
        from models import User
        admin_email = os.environ.get('ADMIN_EMAIL', 'admin@apestogether.ai')
        admin = User.query.filter_by(email=admin_email).first()
        if admin and admin.extra_data and 'auto_create_bots' in admin.extra_data:
            _AUTO_CREATE_CACHE = admin.extra_data['auto_create_bots']
            return dict(_AUTO_CREATE_CACHE)
    except Exception:
        pass
    
    return {
        'enabled': False,
        'daily_count': 2,
        'strategy': None,
        'industry': None,
        'last_run': None,
        'last_created': 0,
    }


def _save_auto_create_settings(settings):
    """Persist auto-creation settings to the admin user's extra_data."""
    global _AUTO_CREATE_CACHE
    _AUTO_CREATE_CACHE = dict(settings)
    
    try:
        from models import db, User
        from sqlalchemy.orm.attributes import flag_modified
        admin_email = os.environ.get('ADMIN_EMAIL', 'admin@apestogether.ai')
        admin = User.query.filter_by(email=admin_email).first()
        if admin:
            extra = dict(admin.extra_data or {})
            extra['auto_create_bots'] = settings
            admin.extra_data = extra
            flag_modified(admin, 'extra_data')
            db.session.commit()
    except Exception as e:
        logger.error(f"Save auto-create settings error: {e}")


# =============================================================================
# Admin Payout / Tax Info Endpoints (Xero handles W-9 collection natively)
# =============================================================================



# NOTE: Payouts are no longer held for W-9 completion.
# Xero handles W-9 collection natively via the 1099 Contractors group.
# All payouts go to 'pending' immediately and are synced to Xero as bills.
# At year-end, Xero flags missing TINs in the 1099 report.


@mobile_api.route('/admin/rebuild-leaderboard-cache/<period>', methods=['GET'])
@require_admin_2fa
@with_db_retry
def rebuild_leaderboard_cache_single(period):
    """Rebuild leaderboard cache for a single period (avoids Vercel timeout).

    Reset the DB session up-front so we never spend the budget on a stale cold
    connection. with_db_retry handles transient SSL drops mid-execution.

    Auth: admin Flask session (2FA-verified) OR X-Admin-Key + X-Admin-OTP headers.
    Browser users with an active admin session pass through transparently.
    """
    _reset_db_session()
    import time as _time
    t0 = _time.time()
    try:
        from leaderboard_utils import update_leaderboard_cache
        cache_period = '5D' if period == '1W' else period
        updated = update_leaderboard_cache(periods=[cache_period])
        from models import db
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
        return jsonify({
            'success': True,
            'period': period,
            'cache_period': cache_period,
            'entries_updated': updated,
            'elapsed_seconds': round(_time.time() - t0, 2),
        })
    except Exception as e:
        import traceback
        return jsonify({
            'error': str(e),
            'traceback': traceback.format_exc(),
            'elapsed_seconds': round(_time.time() - t0, 2),
        }), 500


@mobile_api.route('/admin/debug-sparkline/<username>/<period>', methods=['GET'])
@require_admin_2fa
@with_db_retry
def debug_sparkline(username, period):
    """Compare cached sparkline vs live chart data for a user.

    Auth: admin 2FA required. Without it this would publicly expose every
    user's sparkline + performance time series by username (a useful
    leaderboard-bypass for scraping individual performance curves), plus
    clear the SP500 benchmark cache as a side effect on each call.
    """
    import json
    from models import User, LeaderboardCache
    from performance_calculator import calculate_portfolio_performance, get_period_dates, _sp500_benchmark_cache
    
    user = User.query.filter_by(username=username).first()
    if not user:
        return jsonify({'error': 'user_not_found'}), 404
    
    # 1) Get cached sparkline from LeaderboardCache
    cache_period = '5D' if period == '1W' else period
    cached_sparkline = None
    cached_perf = None
    cache_key = f"{cache_period}_all"
    cache_entry = LeaderboardCache.query.filter_by(period=cache_key).first()
    if cache_entry:
        cached_data = json.loads(cache_entry.leaderboard_data)
        for entry in cached_data:
            if entry.get('user_id') == user.id:
                cached_sparkline = entry.get('sparkline_data', [])
                cached_perf = entry.get('performance_percent')
                break
    
    # 2) Compute live chart data
    _sp500_benchmark_cache.clear()
    chart_period = '5D' if period == '1W' else period
    start_date, end_date = get_period_dates(chart_period, user_id=user.id)
    result = calculate_portfolio_performance(
        user.id, start_date, end_date,
        include_chart_data=True, period=chart_period
    )
    
    live_chart_data = result.get('chart_data', []) if result else []
    live_sparkline = [round(pt.get('portfolio', 0) or 0, 2) for pt in live_chart_data]
    live_perf = result.get('portfolio_return') if result else None
    
    return jsonify({
        'user_id': user.id,
        'username': username,
        'period': period,
        'cache_period': cache_period,
        'start_date': str(start_date),
        'end_date': str(end_date),
        'cache_generated_at': cache_entry.generated_at.isoformat() if cache_entry else None,
        'cached_sparkline': cached_sparkline,
        'cached_sparkline_len': len(cached_sparkline) if cached_sparkline else 0,
        'cached_perf': cached_perf,
        'live_chart_data': live_chart_data,
        'live_chart_data_len': len(live_chart_data),
        'live_sparkline': live_sparkline,
        'live_sparkline_len': len(live_sparkline),
        'live_perf': live_perf,
        'match': cached_sparkline == live_sparkline if cached_sparkline else 'no_cache',
    })
