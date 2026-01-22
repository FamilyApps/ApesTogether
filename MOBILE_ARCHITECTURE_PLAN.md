# 📱 Apes Together Mobile Architecture & Development Plan
## iOS & Android Apps with Shared Backend

**Document Version**: 1.0  
**Created**: January 21, 2026  
**Purpose**: Complete architectural pivot from web app with SMS to native iOS/Android apps with push notifications

---

## Executive Summary

### The Pivot
- **From**: Web app with Twilio SMS notifications (blocked by stock price restrictions)
- **To**: Native iOS & Android apps with push notifications + in-app purchases

### Key Changes
| Component | Web App (Current) | Mobile Apps (New) |
|-----------|-------------------|-------------------|
| **Notifications** | Twilio SMS ($0.0075/msg) | FCM/APNs (free up to millions) |
| **Payments** | Stripe (2.9% + $0.30) | Apple/Google (30% platform fee) |
| **Stock Prices** | Restricted via SMS | ✅ Allowed in native apps |
| **Distribution** | Direct web access | App Store / Play Store |
| **User Auth** | Google/Apple OAuth | Same + native Sign-in |

### Revenue Model (Updated)

**Single Flat Price**: $9/month for ALL subscriptions

| Recipient | Percentage | Amount |
|-----------|------------|--------|
| Apple/Google | 30% | $2.70 |
| Influencer | 60% | $5.40 |
| Platform | 10% | $0.90 |

**Rationale**: 
- No per-notification costs (SMS was $0.0075/msg) means costs don't scale with users
- Simplified pricing attracts more subscribers
- 60% influencer payout is competitive and fair given platform handles all tech/payments
- 10% platform margin is sustainable at scale

---

## 🏗️ System Architecture

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        MOBILE CLIENTS                                │
│  ┌─────────────────────┐         ┌─────────────────────┐           │
│  │     iOS App         │         │    Android App      │           │
│  │  (Swift/SwiftUI)    │         │   (Kotlin/Compose)  │           │
│  │                     │         │                     │           │
│  │  - Portfolio UI     │         │  - Portfolio UI     │           │
│  │  - Charts (native)  │         │  - Charts (native)  │           │
│  │  - Push Notifs      │         │  - Push Notifs      │           │
│  │  - StoreKit 2       │         │  - Google Billing   │           │
│  │  - Sign in w/ Apple │         │  - Google Sign-In   │           │
│  └──────────┬──────────┘         └──────────┬──────────┘           │
│             │                               │                       │
│             └───────────────┬───────────────┘                       │
│                             │ HTTPS/REST + WebSocket                │
└─────────────────────────────┼───────────────────────────────────────┘
                              │
┌─────────────────────────────┼───────────────────────────────────────┐
│                    API GATEWAY LAYER                                 │
│  ┌──────────────────────────┴──────────────────────────────────┐   │
│  │              AWS API Gateway / Vercel Edge                   │   │
│  │  - Rate limiting (per user, per IP)                         │   │
│  │  - JWT validation                                            │   │
│  │  - Request routing                                           │   │
│  │  - WebSocket connection management                           │   │
│  └──────────────────────────┬──────────────────────────────────┘   │
└─────────────────────────────┼───────────────────────────────────────┘
                              │
┌─────────────────────────────┼───────────────────────────────────────┐
│                    BACKEND SERVICES                                  │
│                                                                      │
│  ┌────────────────┐  ┌────────────────┐  ┌────────────────┐        │
│  │  Auth Service  │  │ Portfolio Svc  │  │ Notification   │        │
│  │                │  │                │  │   Service      │        │
│  │ - JWT tokens   │  │ - CRUD stocks  │  │                │        │
│  │ - OAuth flows  │  │ - Transactions │  │ - FCM/APNs     │        │
│  │ - Device reg   │  │ - Snapshots    │  │ - Real-time    │        │
│  └───────┬────────┘  └───────┬────────┘  └───────┬────────┘        │
│          │                   │                   │                  │
│  ┌───────┴───────────────────┴───────────────────┴────────┐        │
│  │              Core Flask API (api/index.py)              │        │
│  │  - Existing routes (refactored for mobile)              │        │
│  │  - Admin dashboard (web-only)                           │        │
│  │  - Cron jobs (market close, intraday)                   │        │
│  └─────────────────────────┬───────────────────────────────┘        │
│                            │                                        │
│  ┌─────────────────────────┴───────────────────────────────┐        │
│  │                    Background Workers                    │        │
│  │  - Agent trading system (existing)                       │        │
│  │  - Leaderboard calculations                              │        │
│  │  - Push notification dispatcher                          │        │
│  │  - IAP receipt validation                                │        │
│  └─────────────────────────────────────────────────────────┘        │
└─────────────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────┼───────────────────────────────────────┐
│                    DATA LAYER                                        │
│                                                                      │
│  ┌────────────────┐  ┌────────────────┐  ┌────────────────┐        │
│  │  PostgreSQL    │  │     Redis      │  │   S3/CloudFront│        │
│  │  (Primary DB)  │  │   (Caching)    │  │   (Assets)     │        │
│  │                │  │                │  │                │        │
│  │ - Users        │  │ - Stock prices │  │ - Chart images │        │
│  │ - Portfolios   │  │ - Sessions     │  │ - User avatars │        │
│  │ - Transactions │  │ - Rate limits  │  │ - Static assets│        │
│  │ - Subscriptions│  │ - Push tokens  │  │                │        │
│  └────────────────┘  └────────────────┘  └────────────────┘        │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────┼───────────────────────────────────────┐
│                    EXTERNAL SERVICES                                 │
│                                                                      │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐   │
│  │AlphaVantage │ │  Firebase   │ │ App Store   │ │ Play Store  │   │
│  │ (Prices)    │ │   (FCM)     │ │ Connect     │ │ Console     │   │
│  │             │ │             │ │             │ │             │   │
│  │ - Real-time │ │ - Push iOS  │ │ - IAP       │ │ - IAP       │   │
│  │ - Historical│ │ - Push Droid│ │ - Reviews   │ │ - Reviews   │   │
│  │ - Batch API │ │ - Analytics │ │ - TestFlight│ │ - Beta      │   │
│  └─────────────┘ └─────────────┘ └─────────────┘ └─────────────┘   │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

### Technology Decisions

#### Mobile Framework Choice: **Native Apps**

| Option | Pros | Cons | Decision |
|--------|------|------|----------|
| **React Native** | Single codebase, faster dev | Performance limits, bridge overhead | ❌ |
| **Flutter** | Single codebase, great perf | Dart learning curve, larger app size | ❌ |
| **Native (Swift/Kotlin)** | Best performance, native APIs | Two codebases, longer dev time | ✅ |

**Rationale for Native**:
1. **Real-time stock data** requires maximum performance
2. **Push notifications** work best with native APIs
3. **StoreKit 2 / Google Billing** complex integrations
4. **Charts** need 60fps smooth scrolling
5. **Long-term maintainability** for financial app

#### Backend Evolution

**Keep**: Flask API on Vercel (refactor endpoints for mobile)
**Add**: 
- Redis for real-time price caching and WebSocket state
- Firebase Cloud Messaging for push notifications
- AWS Lambda for background processing at scale

---

## 📊 Database Schema Updates

### New Tables for Mobile

```python
# Add to models.py

class DeviceToken(db.Model):
    """Push notification device tokens"""
    __tablename__ = 'device_token'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    token = db.Column(db.String(500), nullable=False)  # FCM/APNs token
    platform = db.Column(db.String(10), nullable=False)  # 'ios' or 'android'
    device_id = db.Column(db.String(100), nullable=True)  # Unique device identifier
    app_version = db.Column(db.String(20), nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    __table_args__ = (db.UniqueConstraint('user_id', 'token', name='unique_user_token'),)


class InAppPurchase(db.Model):
    """Track in-app purchases from Apple/Google"""
    __tablename__ = 'in_app_purchase'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    platform = db.Column(db.String(10), nullable=False)  # 'ios' or 'android'
    product_id = db.Column(db.String(100), nullable=False)  # App Store/Play Store product ID
    transaction_id = db.Column(db.String(200), unique=True, nullable=False)
    original_transaction_id = db.Column(db.String(200), nullable=True)  # For renewals
    purchase_date = db.Column(db.DateTime, nullable=False)
    expires_date = db.Column(db.DateTime, nullable=True)  # For subscriptions
    is_trial = db.Column(db.Boolean, default=False)
    status = db.Column(db.String(20), nullable=False)  # 'active', 'expired', 'refunded', 'grace_period'
    receipt_data = db.Column(db.Text, nullable=True)  # Store receipt for verification
    verified_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    user = db.relationship('User', backref=db.backref('purchases', lazy='dynamic'))


class PushNotificationLog(db.Model):
    """Log of all push notifications sent"""
    __tablename__ = 'push_notification_log'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    notification_type = db.Column(db.String(50), nullable=False)  # 'trade_alert', 'price_alert', 'leaderboard', etc.
    title = db.Column(db.String(200), nullable=False)
    body = db.Column(db.Text, nullable=False)
    data_payload = db.Column(db.JSON, nullable=True)  # Deep link data
    platform = db.Column(db.String(10), nullable=False)  # 'ios' or 'android'
    status = db.Column(db.String(20), nullable=False)  # 'sent', 'delivered', 'failed', 'opened'
    fcm_message_id = db.Column(db.String(200), nullable=True)
    error_message = db.Column(db.Text, nullable=True)
    sent_at = db.Column(db.DateTime, default=datetime.utcnow)
    delivered_at = db.Column(db.DateTime, nullable=True)
    opened_at = db.Column(db.DateTime, nullable=True)


class UserMobileSettings(db.Model):
    """Mobile-specific user preferences"""
    __tablename__ = 'user_mobile_settings'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, unique=True)
    
    # Notification preferences
    push_enabled = db.Column(db.Boolean, default=True)
    trade_alerts_enabled = db.Column(db.Boolean, default=True)
    price_alerts_enabled = db.Column(db.Boolean, default=True)
    leaderboard_alerts_enabled = db.Column(db.Boolean, default=True)
    quiet_hours_start = db.Column(db.Time, nullable=True)  # e.g., 22:00
    quiet_hours_end = db.Column(db.Time, nullable=True)    # e.g., 08:00
    
    # Display preferences
    default_chart_period = db.Column(db.String(10), default='1D')
    theme = db.Column(db.String(10), default='system')  # 'light', 'dark', 'system'
    
    # Biometric settings
    biometric_enabled = db.Column(db.Boolean, default=False)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    user = db.relationship('User', backref=db.backref('mobile_settings', uselist=False))
```

### User Model Updates

```python
# Updates to existing User model

class User(UserMixin, db.Model):
    # ... existing fields ...
    
    # Add mobile-specific fields
    primary_platform = db.Column(db.String(10), nullable=True)  # 'ios', 'android', 'web'
    app_version = db.Column(db.String(20), nullable=True)  # Last known app version
    last_app_open = db.Column(db.DateTime, nullable=True)  # For engagement metrics
    
    # Subscription source tracking
    subscription_platform = db.Column(db.String(10), nullable=True)  # 'apple', 'google', 'stripe'
```

---

## 🔔 Push Notification System

### Architecture

```
Trade Executed
      │
      ▼
┌─────────────────┐
│  Flask Backend  │
│  (api/index.py) │
└────────┬────────┘
         │ Queue notification
         ▼
┌─────────────────┐
│  Redis Queue    │
│  (Bull/Celery)  │
└────────┬────────┘
         │ Process async
         ▼
┌─────────────────┐
│  Notification   │
│    Worker       │
└────────┬────────┘
         │
    ┌────┴────┐
    │         │
    ▼         ▼
┌───────┐ ┌───────┐
│ FCM   │ │ APNs  │
│(both) │ │(iOS)  │
└───┬───┘ └───┬───┘
    │         │
    ▼         ▼
┌───────┐ ┌───────┐
│Android│ │  iOS  │
│ App   │ │  App  │
└───────┘ └───────┘
```

### Notification Types

| Type | Trigger | Priority | Content Example |
|------|---------|----------|-----------------|
| **Trade Alert** | Subscribed user trades | High | "🚀 @trader just bought 50 TSLA @ $248.50" |
| **Price Alert** | Price target hit | High | "📈 AAPL hit your target: $195.00" |
| **Leaderboard** | Rank change | Normal | "🏆 You moved up to #3 on 7D leaderboard!" |
| **Portfolio** | Significant change | Normal | "📊 Your portfolio is up 5.2% today" |
| **Market** | Open/Close | Low | "🔔 Market is now open" |

### Implementation (Python)

```python
# services/push_notifications.py

import firebase_admin
from firebase_admin import credentials, messaging
import os
import json
from models import db, DeviceToken, PushNotificationLog, Subscription
from datetime import datetime

# Initialize Firebase Admin SDK
cred = credentials.Certificate(json.loads(os.environ.get('FIREBASE_SERVICE_ACCOUNT')))
firebase_admin.initialize_app(cred)

def send_trade_notification(trader_user_id: int, ticker: str, quantity: float, 
                            price: float, action: str):
    """
    Send push notification to all subscribers when a trade is executed.
    INCLUDES STOCK PRICE - this is allowed in native apps!
    """
    from models import User, Subscription
    
    trader = User.query.get(trader_user_id)
    if not trader:
        return
    
    # Get all active subscribers
    subscriptions = Subscription.query.filter_by(
        subscribed_to_id=trader_user_id,
        status='active'
    ).all()
    
    for sub in subscriptions:
        # Get subscriber's device tokens
        tokens = DeviceToken.query.filter_by(
            user_id=sub.subscriber_id,
            is_active=True
        ).all()
        
        if not tokens:
            continue
        
        # Build notification with REAL PRICE (allowed in apps!)
        title = f"🚨 {trader.username} just traded!"
        body = f"{action.upper()} {quantity} {ticker} @ ${price:.2f}"
        
        # Rich data payload for deep linking
        data = {
            'type': 'trade_alert',
            'trader_id': str(trader_user_id),
            'trader_username': trader.username,
            'ticker': ticker,
            'quantity': str(quantity),
            'price': str(price),
            'action': action,
            'timestamp': datetime.utcnow().isoformat()
        }
        
        for token in tokens:
            try:
                message = messaging.Message(
                    notification=messaging.Notification(
                        title=title,
                        body=body
                    ),
                    data=data,
                    token=token.token,
                    # Platform-specific config
                    android=messaging.AndroidConfig(
                        priority='high',
                        notification=messaging.AndroidNotification(
                            icon='ic_notification',
                            color='#4CAF50',
                            click_action='TRADE_ALERT'
                        )
                    ),
                    apns=messaging.APNSConfig(
                        payload=messaging.APNSPayload(
                            aps=messaging.Aps(
                                badge=1,
                                sound='trade_alert.wav',
                                category='TRADE_ALERT'
                            )
                        )
                    )
                )
                
                response = messaging.send(message)
                
                # Log success
                log = PushNotificationLog(
                    user_id=sub.subscriber_id,
                    notification_type='trade_alert',
                    title=title,
                    body=body,
                    data_payload=data,
                    platform=token.platform,
                    status='sent',
                    fcm_message_id=response
                )
                db.session.add(log)
                
            except messaging.UnregisteredError:
                # Token is invalid, mark as inactive
                token.is_active = False
                
            except Exception as e:
                # Log failure
                log = PushNotificationLog(
                    user_id=sub.subscriber_id,
                    notification_type='trade_alert',
                    title=title,
                    body=body,
                    data_payload=data,
                    platform=token.platform,
                    status='failed',
                    error_message=str(e)
                )
                db.session.add(log)
    
    db.session.commit()
```

---

## 💳 In-App Purchase System

### Simplified Flat Pricing Model

**All subscriptions**: $9/month flat rate

| Component | Split | Amount per Subscription |
|-----------|-------|-------------------------|
| Apple/Google Platform Fee | 30% | $2.70 |
| Influencer Payout | 60% | $5.40 |
| Platform Revenue | 10% | $0.90 |

**Why Flat Pricing Works**:
- No SMS costs means no per-user variable costs
- Push notifications are free (FCM/APNs)
- Simpler for users to understand
- Lower price point = higher conversion

**Note**: After first year, Apple/Google reduce to 15% for subscriptions:
- Apple/Google: $1.35 (15%)
- Influencer: $5.40 (60%) - unchanged
- Platform: $2.25 (25%) - increases

### Product IDs

```
# Apple App Store
com.apestogether.subscription.monthly    # $9/month flat

# Google Play Store  
subscription_monthly                      # $9/month flat
```

### Server-Side Receipt Validation

```python
# services/iap_validation.py

import requests
import os
from datetime import datetime
from models import db, InAppPurchase, Subscription, User

# Apple App Store
APPLE_VERIFY_URL_PROD = 'https://buy.itunes.apple.com/verifyReceipt'
APPLE_VERIFY_URL_SANDBOX = 'https://sandbox.itunes.apple.com/verifyReceipt'
APPLE_SHARED_SECRET = os.environ.get('APPLE_SHARED_SECRET')

# Google Play
GOOGLE_PACKAGE_NAME = 'com.apestogether.app'

def verify_apple_receipt(receipt_data: str, user_id: int) -> dict:
    """
    Verify Apple App Store receipt and create/update subscription
    """
    payload = {
        'receipt-data': receipt_data,
        'password': APPLE_SHARED_SECRET,
        'exclude-old-transactions': True
    }
    
    # Try production first, fall back to sandbox
    response = requests.post(APPLE_VERIFY_URL_PROD, json=payload)
    result = response.json()
    
    if result.get('status') == 21007:  # Sandbox receipt
        response = requests.post(APPLE_VERIFY_URL_SANDBOX, json=payload)
        result = response.json()
    
    if result.get('status') != 0:
        return {'success': False, 'error': f"Invalid receipt: status {result.get('status')}"}
    
    # Get latest subscription info
    latest_receipt_info = result.get('latest_receipt_info', [])
    if not latest_receipt_info:
        return {'success': False, 'error': 'No subscription found in receipt'}
    
    latest = latest_receipt_info[-1]
    
    # Extract subscription details
    transaction_id = latest.get('transaction_id')
    original_transaction_id = latest.get('original_transaction_id')
    product_id = latest.get('product_id')
    purchase_date = datetime.fromtimestamp(int(latest.get('purchase_date_ms', 0)) / 1000)
    expires_date = datetime.fromtimestamp(int(latest.get('expires_date_ms', 0)) / 1000)
    is_trial = latest.get('is_trial_period') == 'true'
    
    # Check if already processed
    existing = InAppPurchase.query.filter_by(transaction_id=transaction_id).first()
    if existing:
        return {'success': True, 'already_processed': True, 'purchase_id': existing.id}
    
    # Create purchase record
    purchase = InAppPurchase(
        user_id=user_id,
        platform='ios',
        product_id=product_id,
        transaction_id=transaction_id,
        original_transaction_id=original_transaction_id,
        purchase_date=purchase_date,
        expires_date=expires_date,
        is_trial=is_trial,
        status='active' if expires_date > datetime.utcnow() else 'expired',
        receipt_data=receipt_data,
        verified_at=datetime.utcnow()
    )
    db.session.add(purchase)
    
    # Update user subscription status
    user = User.query.get(user_id)
    user.subscription_platform = 'apple'
    # Map product_id to tier and update user's subscription level
    
    db.session.commit()
    
    return {
        'success': True,
        'purchase_id': purchase.id,
        'expires_date': expires_date.isoformat(),
        'is_trial': is_trial
    }


def verify_google_purchase(purchase_token: str, product_id: str, user_id: int) -> dict:
    """
    Verify Google Play purchase using Google Play Developer API
    """
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    
    # Load service account credentials
    credentials = service_account.Credentials.from_service_account_info(
        json.loads(os.environ.get('GOOGLE_PLAY_SERVICE_ACCOUNT')),
        scopes=['https://www.googleapis.com/auth/androidpublisher']
    )
    
    service = build('androidpublisher', 'v3', credentials=credentials)
    
    try:
        result = service.purchases().subscriptions().get(
            packageName=GOOGLE_PACKAGE_NAME,
            subscriptionId=product_id,
            token=purchase_token
        ).execute()
        
        # Extract details
        expiry_time = datetime.fromtimestamp(int(result.get('expiryTimeMillis', 0)) / 1000)
        start_time = datetime.fromtimestamp(int(result.get('startTimeMillis', 0)) / 1000)
        
        # Create purchase record
        purchase = InAppPurchase(
            user_id=user_id,
            platform='android',
            product_id=product_id,
            transaction_id=result.get('orderId'),
            purchase_date=start_time,
            expires_date=expiry_time,
            status='active' if expiry_time > datetime.utcnow() else 'expired',
            verified_at=datetime.utcnow()
        )
        db.session.add(purchase)
        
        # Update user
        user = User.query.get(user_id)
        user.subscription_platform = 'google'
        
        db.session.commit()
        
        return {
            'success': True,
            'purchase_id': purchase.id,
            'expires_date': expiry_time.isoformat()
        }
        
    except Exception as e:
        return {'success': False, 'error': str(e)}
```

---

## 📱 API Endpoints for Mobile

### New Mobile-Specific Endpoints

```python
# Add to api/index.py

# ============================================================================
# MOBILE API ENDPOINTS
# ============================================================================

@app.route('/api/v1/auth/register-device', methods=['POST'])
@login_required
def register_device():
    """Register device for push notifications"""
    data = request.get_json()
    token = data.get('token')
    platform = data.get('platform')  # 'ios' or 'android'
    device_id = data.get('device_id')
    app_version = data.get('app_version')
    
    if not token or not platform:
        return jsonify({'error': 'Missing required fields'}), 400
    
    # Deactivate old tokens for this device
    DeviceToken.query.filter_by(
        user_id=current_user.id,
        device_id=device_id
    ).update({'is_active': False})
    
    # Create new token
    device_token = DeviceToken(
        user_id=current_user.id,
        token=token,
        platform=platform,
        device_id=device_id,
        app_version=app_version
    )
    db.session.add(device_token)
    db.session.commit()
    
    return jsonify({'success': True, 'device_id': device_token.id})


@app.route('/api/v1/iap/verify', methods=['POST'])
@login_required
def verify_iap():
    """Verify in-app purchase receipt"""
    data = request.get_json()
    platform = data.get('platform')
    
    if platform == 'ios':
        receipt_data = data.get('receipt_data')
        result = verify_apple_receipt(receipt_data, current_user.id)
    elif platform == 'android':
        purchase_token = data.get('purchase_token')
        product_id = data.get('product_id')
        result = verify_google_purchase(purchase_token, product_id, current_user.id)
    else:
        return jsonify({'error': 'Invalid platform'}), 400
    
    return jsonify(result)


@app.route('/api/v1/user/settings', methods=['GET', 'PUT'])
@login_required
def mobile_settings():
    """Get or update mobile-specific user settings"""
    settings = UserMobileSettings.query.filter_by(user_id=current_user.id).first()
    
    if request.method == 'GET':
        if not settings:
            return jsonify({
                'push_enabled': True,
                'trade_alerts_enabled': True,
                'price_alerts_enabled': True,
                'leaderboard_alerts_enabled': True,
                'theme': 'system',
                'default_chart_period': '1D'
            })
        return jsonify({
            'push_enabled': settings.push_enabled,
            'trade_alerts_enabled': settings.trade_alerts_enabled,
            'price_alerts_enabled': settings.price_alerts_enabled,
            'leaderboard_alerts_enabled': settings.leaderboard_alerts_enabled,
            'theme': settings.theme,
            'default_chart_period': settings.default_chart_period,
            'biometric_enabled': settings.biometric_enabled
        })
    
    # PUT - update settings
    data = request.get_json()
    if not settings:
        settings = UserMobileSettings(user_id=current_user.id)
        db.session.add(settings)
    
    for key in ['push_enabled', 'trade_alerts_enabled', 'price_alerts_enabled',
                'leaderboard_alerts_enabled', 'theme', 'default_chart_period',
                'biometric_enabled']:
        if key in data:
            setattr(settings, key, data[key])
    
    db.session.commit()
    return jsonify({'success': True})


@app.route('/api/v1/portfolio/realtime', methods=['GET'])
@login_required
def realtime_portfolio():
    """
    Get real-time portfolio data optimized for mobile.
    Includes current prices for all holdings.
    """
    stocks = Stock.query.filter_by(user_id=current_user.id).all()
    tickers = [s.ticker for s in stocks]
    
    # Get batch prices (uses existing caching)
    from portfolio_performance import PortfolioPerformanceCalculator
    calc = PortfolioPerformanceCalculator()
    prices = calc.get_batch_stock_data(tickers)
    
    holdings = []
    total_value = 0
    total_cost = 0
    
    for stock in stocks:
        current_price = prices.get(stock.ticker.upper(), stock.purchase_price)
        market_value = current_price * stock.quantity
        cost_basis = stock.purchase_price * stock.quantity
        gain_loss = market_value - cost_basis
        gain_loss_percent = (gain_loss / cost_basis * 100) if cost_basis > 0 else 0
        
        holdings.append({
            'id': stock.id,
            'ticker': stock.ticker,
            'quantity': stock.quantity,
            'purchase_price': stock.purchase_price,
            'current_price': current_price,
            'market_value': market_value,
            'cost_basis': cost_basis,
            'gain_loss': gain_loss,
            'gain_loss_percent': gain_loss_percent
        })
        
        total_value += market_value
        total_cost += cost_basis
    
    return jsonify({
        'holdings': holdings,
        'total_value': total_value,
        'total_cost': total_cost,
        'total_gain_loss': total_value - total_cost,
        'total_gain_loss_percent': ((total_value - total_cost) / total_cost * 100) if total_cost > 0 else 0,
        'last_updated': datetime.utcnow().isoformat()
    })
```

---

## 📈 Scaling Analysis

### Tier 1: 0 - 10,000 Concurrent Users

**Architecture**: Current (Vercel Serverless + Postgres)

| Component | Current | Scaling Action | Cost |
|-----------|---------|----------------|------|
| **Backend** | Vercel Pro | Sufficient | $20/mo |
| **Database** | Vercel Postgres | Upgrade to Pro | $50/mo |
| **Redis** | Upstash Free | Upgrade to Pay-as-go | $10/mo |
| **Firebase** | Spark (free) | Sufficient (1M notifications) | $0 |
| **AlphaVantage** | Premium | Sufficient (150 req/min) | $100/mo |

**Total**: ~$180/month

**Bottlenecks to Watch**:
- Database connection limits (20 → upgrade at 15K users)
- Vercel function cold starts (monitor P95 latency)
- AlphaVantage rate limits during market open

---

### Tier 2: 10,000 - 50,000 Concurrent Users

**Architecture Changes Required**:

```
┌─────────────────────────────────────────────────────────┐
│                   LOAD BALANCER                          │
│              (Vercel Edge / Cloudflare)                 │
└────────────────────────┬────────────────────────────────┘
                         │
         ┌───────────────┼───────────────┐
         │               │               │
         ▼               ▼               ▼
    ┌─────────┐     ┌─────────┐     ┌─────────┐
    │ Vercel  │     │ Vercel  │     │ Vercel  │
    │Region 1 │     │Region 2 │     │Region 3 │
    └────┬────┘     └────┬────┘     └────┬────┘
         │               │               │
         └───────────────┼───────────────┘
                         │
    ┌────────────────────┼────────────────────┐
    │                    │                    │
    ▼                    ▼                    ▼
┌───────────┐      ┌───────────┐      ┌───────────┐
│  Supabase │      │   Redis   │      │  Firebase │
│ Postgres  │      │  Cluster  │      │   (FCM)   │
│ (Primary) │      │ (Upstash) │      │           │
└───────────┘      └───────────┘      └───────────┘
```

| Component | Upgrade | Cost |
|-----------|---------|------|
| **Backend** | Vercel Enterprise or AWS ECS | $200-500/mo |
| **Database** | Supabase Pro (100K connections) | $500/mo |
| **Redis** | Upstash Enterprise | $100/mo |
| **Firebase** | Blaze (pay-as-go) | $50-100/mo |
| **AlphaVantage** | Add secondary key | $200/mo |
| **CDN** | Cloudflare Pro | $20/mo |

**Total**: ~$1,000-1,500/month

**Required Refactoring**:
1. **Connection pooling**: PgBouncer for database
2. **Read replicas**: Offload leaderboard/chart queries
3. **Queue system**: Redis-based for notifications
4. **API versioning**: `/api/v1/` prefix (already started)

---

### Tier 3: 50,000 - 100,000+ Concurrent Users

**Architecture Changes Required**:

```
┌─────────────────────────────────────────────────────────────────┐
│                     GLOBAL CDN + EDGE                            │
│               (Cloudflare / AWS CloudFront)                      │
└──────────────────────────┬──────────────────────────────────────┘
                           │
┌──────────────────────────┼──────────────────────────────────────┐
│                    API GATEWAY                                   │
│           (AWS API Gateway / Kong)                               │
│    - Rate limiting    - JWT validation    - Request routing     │
└──────────────────────────┬──────────────────────────────────────┘
                           │
      ┌────────────────────┼────────────────────┐
      │                    │                    │
      ▼                    ▼                    ▼
┌───────────────┐  ┌───────────────┐  ┌───────────────┐
│  Auth Service │  │Portfolio Svc  │  │  Notification │
│  (ECS/K8s)    │  │  (ECS/K8s)    │  │   Service     │
└───────────────┘  └───────────────┘  └───────────────┘
      │                    │                    │
      └────────────────────┼────────────────────┘
                           │
┌──────────────────────────┼──────────────────────────────────────┐
│                    DATA LAYER                                    │
│                                                                  │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐              │
│  │  PostgreSQL │  │   Redis     │  │ TimescaleDB │              │
│  │  (Aurora)   │  │  Cluster    │  │ (Prices)    │              │
│  │             │  │             │  │             │              │
│  │ - 3 nodes   │  │ - 3 nodes   │  │ - Time-series│             │
│  │ - Auto-scale│  │ - HA        │  │ - 90-day    │              │
│  └─────────────┘  └─────────────┘  └─────────────┘              │
└─────────────────────────────────────────────────────────────────┘
```

| Component | Upgrade | Cost |
|-----------|---------|------|
| **Compute** | AWS ECS/EKS (3+ nodes) | $1,000-2,000/mo |
| **Database** | Aurora PostgreSQL | $500-1,000/mo |
| **Redis** | ElastiCache (3-node cluster) | $300/mo |
| **Time-series** | TimescaleDB Cloud | $200/mo |
| **Firebase** | Blaze + quota increase | $200-500/mo |
| **Stock Data** | Multiple AlphaVantage keys | $500/mo |
| **CDN** | Cloudflare Enterprise | $200/mo |
| **Monitoring** | Datadog/New Relic | $100/mo |

**Total**: ~$3,000-5,000/month

**Required Refactoring**:
1. **Microservices**: Split Flask app into services
2. **Event-driven**: Kafka/SQS for trade events
3. **CQRS**: Separate read/write paths
4. **Sharding**: User-based database partitioning
5. **WebSocket**: Dedicated real-time servers

---

## 🤖 Agent System (Bot Accounts)

### Agent Architecture (Unchanged)

The agent system remains backend-only and works identically:

```python
# Agent accounts created via admin interface
# Trades executed via internal API calls
# Subscribers receive push notifications instead of SMS

def execute_agent_trade(agent_user_id: int, ticker: str, quantity: float, 
                        action: str, price: float):
    """Execute trade for agent and notify subscribers via push"""
    
    # 1. Execute trade (existing logic)
    transaction = create_transaction(agent_user_id, ticker, quantity, action, price)
    
    # 2. Notify subscribers via PUSH instead of SMS
    send_trade_notification(
        trader_user_id=agent_user_id,
        ticker=ticker,
        quantity=quantity,
        price=price,
        action=action
    )
    
    return transaction
```

### Admin Control Dashboard

The admin dashboard remains web-based for:
- Creating/managing agent accounts
- Monitoring agent performance
- Manual trade execution
- Ghost subscriber management
- Analytics and metrics

---

## 📅 Development Timeline

### Phase 1: Backend Preparation (Weeks 1-2)

| Task | Duration | Deliverable |
|------|----------|-------------|
| Database schema updates | 2 days | Migration files |
| Push notification service | 3 days | FCM integration |
| Mobile API endpoints | 3 days | `/api/v1/*` routes |
| IAP validation service | 2 days | Apple/Google verification |

### Phase 2: iOS App Development (Weeks 3-8)

| Week | Focus | Deliverables |
|------|-------|--------------|
| 3-4 | Core UI | SwiftUI screens, navigation |
| 5 | Authentication | Sign in with Apple, JWT handling |
| 6 | Portfolio | Holdings, charts, real-time prices |
| 7 | Subscriptions | StoreKit 2, subscription flow |
| 8 | Polish | Push notifications, settings, testing |

### Phase 3: Android App Development (Weeks 9-14)

| Week | Focus | Deliverables |
|------|-------|--------------|
| 9-10 | Core UI | Jetpack Compose screens |
| 11 | Authentication | Google Sign-In, JWT handling |
| 12 | Portfolio | Holdings, charts, real-time prices |
| 13 | Subscriptions | Google Billing Library |
| 14 | Polish | FCM notifications, testing |

### Phase 4: Launch Preparation (Weeks 15-16)

| Task | Duration |
|------|----------|
| App Store submission | 3 days |
| Play Store submission | 2 days |
| Beta testing | 5 days |
| Bug fixes | 3 days |
| Launch | Day 1 |

**Total Timeline**: 16 weeks (4 months)

---

## 💰 Cost Summary

### Development Costs (One-Time)

| Item | Cost |
|------|------|
| iOS Developer (16 weeks) | $15,000-25,000 |
| Android Developer (16 weeks) | $15,000-25,000 |
| Backend updates | $2,000-5,000 |
| App Store fees | $99 (Apple) + $25 (Google) |
| **Total** | $32,000-55,000 |

### Monthly Operating Costs

| Scale | Monthly Cost |
|-------|--------------|
| 0-10K users | $180-250 |
| 10K-50K users | $1,000-1,500 |
| 50K-100K users | $3,000-5,000 |
| 100K+ users | $5,000+ |

### Revenue Projection (Break-Even)

At average $35/month subscription with 30% platform fee:
- Net per subscriber: $24.50/month
- To cover $180/month costs: **8 paying subscribers**
- To cover $3,000/month costs: **123 paying subscribers**

---

## ✅ Pre-Launch Checklist

### App Store Requirements
- [ ] Privacy Policy URL
- [ ] Terms of Service URL
- [ ] App screenshots (6.5", 5.5")
- [ ] App icon (1024x1024)
- [ ] App Store description
- [ ] Keywords
- [ ] Age rating declaration
- [ ] IDFA declaration

### Play Store Requirements
- [ ] Privacy Policy URL
- [ ] Feature graphic (1024x500)
- [ ] App screenshots
- [ ] Short/full description
- [ ] Content rating questionnaire
- [ ] Data safety declaration

### Backend Requirements
- [ ] Firebase project configured
- [ ] APNs certificates uploaded
- [ ] Apple App Store Connect configured
- [ ] Google Play Console configured
- [ ] IAP products created
- [ ] Server-side validation tested

---

## 🚀 Next Steps

1. **Immediate**: Set up Firebase project and FCM
2. **Week 1**: Create database migrations for mobile tables
3. **Week 2**: Implement push notification service
4. **Week 3**: Begin iOS app development
5. **Ongoing**: Hire/contract iOS and Android developers

---

*Document maintained by: Development Team*
*Last updated: January 21, 2026*
