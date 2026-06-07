# 🚀 Apes Together Mobile - Phased Implementation Plan
## Built for 10,000 Users / 5,000 Concurrent from Day 1

**Document Version**: 1.0  
**Created**: January 21, 2026  
**Target Scale**: 10K total users, 5K concurrent users at launch

---

## Infrastructure Baseline (Day 1 Ready)

Based on 10K users / 5K concurrent requirement, we start with **Tier 2 infrastructure**:

```
DAY 1 INFRASTRUCTURE STACK
══════════════════════════════════════════════════════════════

Backend:
├── Vercel Pro ($20/mo) - serverless Flask API
├── Supabase Pro ($25/mo) - PostgreSQL with connection pooling
│   ├── 500 connections (pooled)
│   ├── 8GB storage
│   └── Point-in-time recovery
├── Upstash Redis Pro ($10/mo) - caching + rate limiting
│   ├── 10K commands/day
│   └── Global edge caching
└── Total Backend: ~$55/mo

Stock Data:
├── Alpha Vantage Premium ($99.99/mo)
│   ├── 150 requests/minute
│   ├── Real-time US market data
│   └── REALTIME_BULK_QUOTES (100 symbols/request)
└── yfinance (free) - failover only

Push Notifications:
├── Firebase Cloud Messaging (free)
│   ├── iOS via APNs
│   ├── Android native
│   └── 1M notifications/month free
└── Firebase Blaze (pay-as-you-go for >1M)

Payments:
├── Apple App Store Connect
│   ├── $99/year developer fee
│   └── 30% transaction fee (15% after year 1)
└── Google Play Console
    ├── $25 one-time fee
    └── 30% transaction fee (15% after year 1)

Monitoring:
├── Vercel Analytics (free)
├── Sentry (free tier) - error tracking
└── Datadog Starter ($15/mo) - APM

Security (Grok Recommendation):
└── Vercel WAF ($20/mo) - DDoS protection (add if needed)

══════════════════════════════════════════════════════════════
TOTAL INFRASTRUCTURE: ~$190/mo + $124/year app store fees
(Add 10-15% buffer for unexpected overages = ~$210-220/mo)
══════════════════════════════════════════════════════════════
```

---

## Revenue Model Recap

| Component | Split | Per Subscription |
|-----------|-------|------------------|
| Subscription Price | 100% | $9.00 |
| Apple/Google Fee | 30% | $2.70 |
| Influencer Payout | 60% | $5.40 |
| Platform Revenue | 10% | $0.90 |

**Break-even**: ~211 subscriptions/month ($190 ÷ $0.90)

---

## Phase Overview

```
PHASE 1: Backend Preparation (Weeks 1-2)
├── Database migrations for mobile
├── Push notification service
├── IAP validation endpoints
├── Mobile API endpoints
└── Testing: Unit + Integration

PHASE 2: iOS App Development (Weeks 3-6)
├── Core app structure
├── Authentication (Sign in with Apple)
├── Portfolio views + charts
├── Push notifications
├── StoreKit 2 subscriptions
└── Testing: Simulator + TestFlight

PHASE 3: Android App Development (Weeks 7-10)
├── Core app structure  
├── Authentication (Google Sign-In)
├── Portfolio views + charts
├── Push notifications
├── Google Billing subscriptions
└── Testing: Emulator + Internal Testing

PHASE 4: Integration & QA (Weeks 11-12)
├── End-to-end testing
├── Load testing (5K concurrent)
├── Security audit
├── App Store submissions
└── Testing: Beta users + Locust

PHASE 5: Launch & Monitoring (Weeks 13-14)
├── Staged rollout
├── Monitoring dashboards
├── Support infrastructure
└── Post-launch fixes

TOTAL: 14 weeks (3.5 months)
```

---

## PHASE 1: Backend Preparation
### Weeks 1-2

#### 1.1 Database Migrations

**New Tables Required**:

```python
# models.py additions

class DeviceToken(db.Model):
    """Push notification tokens for mobile devices"""
    __tablename__ = 'device_token'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    token = db.Column(db.String(500), nullable=False)
    platform = db.Column(db.String(10), nullable=False)  # 'ios' or 'android'
    device_id = db.Column(db.String(100), nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, onupdate=datetime.utcnow)
    
    __table_args__ = (
        db.UniqueConstraint('user_id', 'token', name='unique_user_token'),
    )


class InAppPurchase(db.Model):
    """Apple/Google purchase receipts"""
    __tablename__ = 'in_app_purchase'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    platform = db.Column(db.String(10), nullable=False)  # 'apple' or 'google'
    product_id = db.Column(db.String(100), nullable=False)
    transaction_id = db.Column(db.String(100), unique=True, nullable=False)
    original_transaction_id = db.Column(db.String(100), nullable=True)
    purchase_date = db.Column(db.DateTime, nullable=False)
    expires_date = db.Column(db.DateTime, nullable=True)
    is_trial = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, default=True)
    receipt_data = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class PushNotificationLog(db.Model):
    """Track push notifications sent"""
    __tablename__ = 'push_notification_log'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    notification_type = db.Column(db.String(50), nullable=False)
    title = db.Column(db.String(200), nullable=True)
    body = db.Column(db.String(500), nullable=True)
    data = db.Column(db.JSON, nullable=True)
    sent_at = db.Column(db.DateTime, default=datetime.utcnow)
    delivered = db.Column(db.Boolean, default=None)
    fcm_message_id = db.Column(db.String(100), nullable=True)


class XeroPayoutRecord(db.Model):
    """Monthly payout records for Xero sync"""
    __tablename__ = 'xero_payout_record'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    payout_month = db.Column(db.Integer, nullable=False)
    payout_year = db.Column(db.Integer, nullable=False)
    real_subscriber_count = db.Column(db.Integer, default=0)
    bonus_subscriber_count = db.Column(db.Integer, default=0)
    total_payout = db.Column(db.Float, default=0.0)
    xero_invoice_id = db.Column(db.String(100), nullable=True)
    status = db.Column(db.String(20), default='pending')
    synced_at = db.Column(db.DateTime, nullable=True)
```

**Verification Tests**:
```python
# tests/test_phase1_migrations.py

def test_device_token_table_exists():
    """Verify DeviceToken table created"""
    assert DeviceToken.__table__.exists(db.engine)

def test_device_token_unique_constraint():
    """Verify user can't have duplicate tokens"""
    token = DeviceToken(user_id=1, token='abc123', platform='ios')
    db.session.add(token)
    db.session.commit()
    
    duplicate = DeviceToken(user_id=1, token='abc123', platform='ios')
    db.session.add(duplicate)
    with pytest.raises(IntegrityError):
        db.session.commit()

def test_in_app_purchase_table_exists():
    """Verify InAppPurchase table created"""
    assert InAppPurchase.__table__.exists(db.engine)

def test_push_notification_log_table_exists():
    """Verify PushNotificationLog table created"""
    assert PushNotificationLog.__table__.exists(db.engine)
```

---

#### 1.2 Push Notification Service

**Implementation**:
```python
# services/push_notifications.py

import firebase_admin
from firebase_admin import credentials, messaging
import os

class PushNotificationService:
    def __init__(self):
        if not firebase_admin._apps:
            cred = credentials.Certificate(
                json.loads(os.environ.get('FIREBASE_SERVICE_ACCOUNT'))
            )
            firebase_admin.initialize_app(cred)
    
    def send_trade_alert(self, user_id: int, trade: dict) -> bool:
        """Send trade notification to user's devices"""
        tokens = DeviceToken.query.filter_by(
            user_id=user_id, 
            is_active=True
        ).all()
        
        if not tokens:
            return False
        
        message = messaging.MulticastMessage(
            notification=messaging.Notification(
                title=f"🔔 {trade['username']} made a trade",
                body=f"{trade['action'].upper()} {trade['quantity']} {trade['ticker']} @ ${trade['price']:.2f}"
            ),
            data={
                'type': 'trade_alert',
                'trader_id': str(trade['user_id']),
                'ticker': trade['ticker'],
                'action': trade['action'],
                'quantity': str(trade['quantity']),
                'price': str(trade['price'])
            },
            tokens=[t.token for t in tokens]
        )
        
        response = messaging.send_multicast(message)
        
        # Log notification
        for token in tokens:
            log = PushNotificationLog(
                user_id=user_id,
                notification_type='trade_alert',
                title=message.notification.title,
                body=message.notification.body,
                data=trade
            )
            db.session.add(log)
        
        db.session.commit()
        return response.success_count > 0
```

**Verification Tests**:
```python
# tests/test_phase1_push.py

def test_push_service_initializes():
    """Verify Firebase initializes correctly"""
    service = PushNotificationService()
    assert firebase_admin._apps

def test_trade_alert_formatting():
    """Verify trade alert message format"""
    trade = {
        'username': 'stockguru',
        'user_id': 1,
        'ticker': 'AAPL',
        'action': 'buy',
        'quantity': 100,
        'price': 150.00
    }
    # Mock the messaging and verify format
    # Expected: "🔔 stockguru made a trade"
    # Body: "BUY 100 AAPL @ $150.00"

def test_inactive_tokens_skipped():
    """Verify inactive tokens not sent to"""
    # Create active and inactive tokens
    # Verify only active tokens receive messages
```

---

#### 1.3 IAP Validation Endpoints

**Implementation**:
```python
# api/mobile_endpoints.py

@app.route('/api/v1/iap/validate/apple', methods=['POST'])
@login_required
def validate_apple_receipt():
    """Validate Apple App Store receipt"""
    receipt_data = request.json.get('receipt_data')
    
    result = verify_apple_receipt(receipt_data, current_user.id)
    
    if result['success']:
        # Create subscription
        subscription = Subscription(
            subscriber_id=current_user.id,
            subscribed_to_id=request.json.get('trader_id'),
            status='active',
            platform='apple',
            monthly_amount=9.00
        )
        db.session.add(subscription)
        db.session.commit()
        
        return jsonify({'success': True, 'subscription_id': subscription.id})
    
    return jsonify({'success': False, 'error': result['error']}), 400


@app.route('/api/v1/iap/validate/google', methods=['POST'])
@login_required
def validate_google_receipt():
    """Validate Google Play receipt"""
    purchase_token = request.json.get('purchase_token')
    product_id = request.json.get('product_id')
    
    result = verify_google_purchase(purchase_token, product_id, current_user.id)
    
    if result['success']:
        subscription = Subscription(
            subscriber_id=current_user.id,
            subscribed_to_id=request.json.get('trader_id'),
            status='active',
            platform='google',
            monthly_amount=9.00
        )
        db.session.add(subscription)
        db.session.commit()
        
        return jsonify({'success': True, 'subscription_id': subscription.id})
    
    return jsonify({'success': False, 'error': result['error']}), 400
```

**Verification Tests**:
```python
# tests/test_phase1_iap.py

def test_apple_receipt_validation_endpoint():
    """Verify Apple receipt endpoint exists and validates"""
    response = client.post('/api/v1/iap/validate/apple', json={
        'receipt_data': 'test_receipt',
        'trader_id': 1
    })
    assert response.status_code in [200, 400]  # Either success or validation error

def test_google_receipt_validation_endpoint():
    """Verify Google receipt endpoint exists"""
    response = client.post('/api/v1/iap/validate/google', json={
        'purchase_token': 'test_token',
        'product_id': 'subscription_monthly',
        'trader_id': 1
    })
    assert response.status_code in [200, 400]

def test_subscription_created_on_valid_purchase():
    """Verify subscription record created after valid IAP"""
    # Mock valid receipt
    # Call endpoint
    # Verify Subscription record exists
```

---

#### 1.4 Mobile API Endpoints

**New Endpoints Required**:

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/v1/auth/device` | POST | Register device token |
| `/api/v1/auth/device` | DELETE | Unregister device token |
| `/api/v1/portfolio/realtime` | GET | Real-time portfolio with prices |
| `/api/v1/leaderboard` | GET | Leaderboard with subscriber counts |
| `/api/v1/trader/{id}/subscribe` | POST | Subscribe to trader |
| `/api/v1/trader/{id}/unsubscribe` | POST | Unsubscribe from trader |
| `/api/v1/iap/validate/apple` | POST | Validate Apple receipt |
| `/api/v1/iap/validate/google` | POST | Validate Google receipt |
| `/api/v1/user/settings` | GET/PUT | User preferences |

**Verification Tests**:
```python
# tests/test_phase1_api.py

def test_device_registration():
    """Verify device token registration works"""
    response = client.post('/api/v1/auth/device', json={
        'token': 'fcm_token_123',
        'platform': 'ios'
    }, headers={'Authorization': f'Bearer {user_token}'})
    assert response.status_code == 200
    assert DeviceToken.query.filter_by(token='fcm_token_123').first()

def test_realtime_portfolio():
    """Verify portfolio endpoint returns stock prices"""
    response = client.get('/api/v1/portfolio/realtime',
        headers={'Authorization': f'Bearer {user_token}'})
    assert response.status_code == 200
    data = response.json
    assert 'stocks' in data
    assert 'total_value' in data

def test_leaderboard_includes_subscribers():
    """Verify leaderboard shows subscriber counts"""
    response = client.get('/api/v1/leaderboard?period=7d')
    assert response.status_code == 200
    data = response.json
    assert 'users' in data
    assert 'subscriber_count' in data['users'][0]
```

---

#### Phase 1 Completion Checklist

- [ ] Database migrations run successfully
- [ ] All new tables created (DeviceToken, InAppPurchase, PushNotificationLog, XeroPayoutRecord)
- [ ] Push notification service sends test message
- [ ] IAP validation endpoints respond correctly
- [ ] All mobile API endpoints functional
- [ ] Unit tests pass (>90% coverage for new code)
- [ ] Integration tests pass
- [ ] API documentation updated

**Verification Command**:
```bash
# Run Phase 1 tests
pytest tests/test_phase1_*.py -v --cov=api --cov=services

# Expected: All tests pass, >90% coverage
```

---

## PHASE 2: iOS App Development
### Weeks 3-6

#### 2.1 Project Structure

```
ApesTogetherApp/
├── App/
│   ├── ApesTogetherApp.swift
│   └── AppDelegate.swift
├── Features/
│   ├── Auth/
│   │   ├── SignInView.swift
│   │   └── AuthViewModel.swift
│   ├── Portfolio/
│   │   ├── PortfolioView.swift
│   │   ├── PortfolioViewModel.swift
│   │   └── StockRowView.swift
│   ├── Leaderboard/
│   │   ├── LeaderboardView.swift
│   │   └── LeaderboardViewModel.swift
│   ├── TraderProfile/
│   │   ├── TraderProfileView.swift
│   │   └── SubscribeButton.swift
│   └── Settings/
│       └── SettingsView.swift
├── Services/
│   ├── APIService.swift
│   ├── AuthService.swift
│   ├── PushNotificationService.swift
│   └── SubscriptionService.swift
├── Models/
│   ├── User.swift
│   ├── Stock.swift
│   ├── Portfolio.swift
│   └── Subscription.swift
└── Resources/
    └── Assets.xcassets
```

#### 2.2 Key Features

**Week 3-4: Core App**
- Sign in with Apple integration
- API service with JWT handling
- Portfolio view with real-time prices
- Charts (Swift Charts)

**Week 5: Notifications + Subscriptions**
- Push notification handling
- StoreKit 2 integration
- Subscribe/unsubscribe flow

**Week 6: Polish + Testing**
- UI polish
- Error handling
- TestFlight deployment
- **Start App Store submission early** (Grok: Apple approval can take 1-2 weeks)

#### 2.3 Verification Tests

```swift
// Tests/AuthTests.swift

func testSignInWithAppleFlow() async throws {
    let authService = AuthService()
    let result = try await authService.signInWithApple(credential: mockCredential)
    XCTAssertNotNil(result.accessToken)
    XCTAssertNotNil(result.user)
}

func testJWTRefresh() async throws {
    let apiService = APIService()
    apiService.accessToken = expiredToken
    
    // Should automatically refresh
    let portfolio = try await apiService.getPortfolio()
    XCTAssertNotNil(portfolio)
}

// Tests/PortfolioTests.swift

func testPortfolioLoadsRealTimePrices() async throws {
    let viewModel = PortfolioViewModel()
    await viewModel.loadPortfolio()
    
    XCTAssertFalse(viewModel.stocks.isEmpty)
    XCTAssertNotNil(viewModel.stocks.first?.currentPrice)
}

func testChartDisplaysCorrectData() async throws {
    let viewModel = PortfolioViewModel()
    await viewModel.loadChartData(period: .oneWeek)
    
    XCTAssertEqual(viewModel.chartData.count, 7) // 7 days
}

// Tests/SubscriptionTests.swift

func testStoreKitPurchaseFlow() async throws {
    let service = SubscriptionService()
    let product = try await service.fetchProduct(id: "com.apestogether.subscription.monthly")
    
    XCTAssertEqual(product.displayPrice, "$9.00")
}

func testPushNotificationPermission() async throws {
    let service = PushNotificationService()
    let granted = try await service.requestPermission()
    // Simulator always grants
    XCTAssertTrue(granted)
}
```

#### Phase 2 Completion Checklist

- [ ] App builds without errors
- [ ] Sign in with Apple works
- [ ] Portfolio displays with live prices
- [ ] Charts render correctly for all periods
- [ ] Leaderboard loads with subscriber counts
- [ ] Push notifications receive and display
- [ ] StoreKit 2 subscription flow works (sandbox)
- [ ] App passes all UI tests
- [ ] TestFlight build approved
- [ ] 10 beta testers complete basic flows

**Verification Process**:
1. Run XCTest suite: `xcodebuild test -scheme ApesTogetherApp`
2. Manual testing on 3 device sizes (iPhone SE, 14, 14 Pro Max)
3. TestFlight distribution to beta testers
4. Collect crash reports via Sentry

---

## PHASE 3: Android App Development
### Weeks 7-10

#### 3.1 Project Structure

```
app/
├── src/main/java/com/apestogether/
│   ├── ApesTogetherApp.kt
│   ├── MainActivity.kt
│   ├── ui/
│   │   ├── auth/
│   │   │   ├── SignInScreen.kt
│   │   │   └── AuthViewModel.kt
│   │   ├── portfolio/
│   │   │   ├── PortfolioScreen.kt
│   │   │   └── PortfolioViewModel.kt
│   │   ├── leaderboard/
│   │   │   ├── LeaderboardScreen.kt
│   │   │   └── LeaderboardViewModel.kt
│   │   └── settings/
│   │       └── SettingsScreen.kt
│   ├── data/
│   │   ├── api/
│   │   │   └── ApiService.kt
│   │   ├── repository/
│   │   │   └── PortfolioRepository.kt
│   │   └── models/
│   │       ├── User.kt
│   │       └── Stock.kt
│   └── services/
│       ├── PushNotificationService.kt
│       └── BillingService.kt
└── src/test/
    └── ... tests
```

#### 3.2 Key Features

**Week 7-8: Core App**
- Google Sign-In integration
- Retrofit API service
- Portfolio view with Compose
- Charts (Vico or similar)

**Week 9: Notifications + Billing**
- FCM push handling
- Google Play Billing Library
- Subscribe/unsubscribe flow

**Week 10: Polish + Testing**
- Material Design 3 polish
- Error handling
- Internal testing track

#### 3.3 Verification Tests

```kotlin
// AuthViewModelTest.kt

@Test
fun `sign in with Google returns user`() = runTest {
    val viewModel = AuthViewModel(mockAuthRepository)
    viewModel.signInWithGoogle(mockCredential)
    
    assertNotNull(viewModel.user.value)
    assertNotNull(viewModel.accessToken.value)
}

// PortfolioViewModelTest.kt

@Test
fun `portfolio loads with real-time prices`() = runTest {
    val viewModel = PortfolioViewModel(mockRepository)
    viewModel.loadPortfolio()
    
    assertTrue(viewModel.stocks.value.isNotEmpty())
    assertNotNull(viewModel.stocks.value.first().currentPrice)
}

// BillingServiceTest.kt

@Test
fun `subscription product fetches correctly`() = runTest {
    val service = BillingService(mockBillingClient)
    val product = service.getProduct("subscription_monthly")
    
    assertEquals("$9.00", product.formattedPrice)
}
```

#### Phase 3 Completion Checklist

- [ ] App builds without errors
- [ ] Google Sign-In works
- [ ] Portfolio displays with live prices
- [ ] Charts render correctly
- [ ] Leaderboard loads properly
- [ ] FCM notifications work
- [ ] Google Play Billing works (test track)
- [ ] All unit tests pass
- [ ] Internal testing track published
- [ ] 10 beta testers complete basic flows

**Verification Process**:
1. Run tests: `./gradlew test`
2. Manual testing on 3 device sizes
3. Internal testing track distribution
4. Collect crash reports via Sentry

---

## PHASE 4: Integration & QA
### Weeks 11-12

#### 4.1 End-to-End Testing

**Test Scenarios**:

| # | Scenario | Steps | Expected Result |
|---|----------|-------|-----------------|
| 1 | New user signup | Open app → Sign in → Grant permissions | User created, portfolio empty |
| 2 | Subscribe to trader | View leaderboard → Tap trader → Subscribe → Pay $9 | Subscription active, notifications enabled |
| 3 | Receive trade alert | Subscribed trader makes trade | Push notification with stock details |
| 4 | View portfolio | Login → View portfolio | All stocks with current prices |
| 5 | Cancel subscription | Settings → Subscriptions → Cancel | Subscription ends at period end |
| 6 | Cross-platform sync | Login iOS → Add stock → Login Android | Same portfolio on both platforms |

#### 4.2 Load Testing (5K Concurrent)

```python
# tests/load_test_5k.py

from locust import HttpUser, task, between

class MobileAppUser(HttpUser):
    wait_time = between(2, 5)
    
    @task(10)
    def get_leaderboard(self):
        self.client.get("/api/v1/leaderboard?period=7d")
    
    @task(5)
    def get_portfolio(self):
        self.client.get("/api/v1/portfolio/realtime",
            headers={"Authorization": f"Bearer {self.token}"})
    
    @task(2)
    def get_trader_profile(self):
        self.client.get("/api/v1/trader/1/profile")
    
    @task(1)
    def execute_trade(self):
        self.client.post("/api/v1/trade", json={
            "ticker": "AAPL",
            "quantity": 10,
            "action": "buy"
        }, headers={"Authorization": f"Bearer {self.token}"})

# Run: locust -f tests/load_test_5k.py --users 5000 --spawn-rate 100
```

**Load Test Targets**:
| Metric | Target | Maximum |
|--------|--------|---------|
| P95 Latency | <300ms | 500ms |
| Error Rate | <0.5% | 1% |
| Throughput | >1000 RPS | - |
| Database Connections | <400 | 500 |

#### 4.3 Security Audit

**Checklist**:
- [ ] JWT tokens expire appropriately (24h access, 30d refresh)
- [ ] API rate limiting active (100 req/min per user)
- [ ] Receipt validation prevents replay attacks
- [ ] No sensitive data in logs
- [ ] HTTPS enforced on all endpoints
- [ ] SQL injection prevention verified
- [ ] Push notification tokens validated per-user

#### Phase 4 Completion Checklist

- [ ] All E2E test scenarios pass on both platforms
- [ ] Load test passes 5K concurrent users
- [ ] P95 latency <300ms under load
- [ ] Security audit complete, no critical issues
- [ ] iOS app submitted to App Store review
- [ ] Android app submitted to Play Store review
- [ ] App store assets (screenshots, descriptions) complete

---

## PHASE 5: Launch & Monitoring
### Weeks 13-14

#### 5.1 Staged Rollout

**Day 1-3**: 1% rollout
- Monitor crash rates
- Check error logs
- Verify push delivery

**Day 4-7**: 10% rollout
- Monitor performance metrics
- Check subscription flows
- Verify Xero sync

**Day 8-14**: 100% rollout
- Full launch announcement
- Monitor all metrics
- 24/7 on-call support

#### 5.2 Monitoring Dashboard

**Key Metrics to Display**:
```
┌─────────────────────────────────────────────────────────────┐
│  APES TOGETHER - LIVE DASHBOARD                             │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  USERS                    SUBSCRIPTIONS                     │
│  ─────                    ─────────────                     │
│  Total: 8,234             Active: 1,247                     │
│  DAU: 3,456               MRR: $11,223                      │
│  Concurrent: 1,892        Churn: 2.3%                       │
│                                                             │
│  PERFORMANCE              NOTIFICATIONS                     │
│  ───────────              ─────────────                     │
│  API P95: 142ms           Sent Today: 45,892                │
│  Error Rate: 0.02%        Delivery Rate: 99.2%              │
│  DB Connections: 45/500   Failed: 367                       │
│                                                             │
│  ALPHA VANTAGE            REVENUE                           │
│  ────────────             ───────                           │
│  Calls/min: 78/150        Today: $387                       │
│  Cache Hit: 94%           This Month: $8,923                │
│  yfinance Fallback: 0     Influencer Payouts: $6,692        │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

#### Phase 5 Completion Checklist

- [ ] Apps approved in both stores
- [ ] Staged rollout complete
- [ ] No critical bugs in first week
- [ ] Monitoring dashboard live
- [ ] Support email/chat operational
- [ ] First Xero payout sync tested

---

## New Grok Verification Prompt

Since we're building for 10K users / 5K concurrent from day 1, here's an updated prompt for Grok:

---

**Copy and paste to Grok:**

---

I'm building a mobile stock portfolio app and need you to verify my **Day 1 architecture** designed for **10,000 total users and 5,000 concurrent users**. This is NOT a gradual scaling plan—we expect rapid growth and need to be ready immediately.

## IMPORTANT: This is a MOBILE-ONLY Architecture

**We are NOT using SMS/Twilio.** This is a complete pivot from web+SMS to native mobile apps:
- ❌ **NO Twilio** - SMS notifications are eliminated entirely
- ❌ **NO SMS costs** - Push notifications are free (Firebase FCM)
- ❌ **NO per-message fees** - One of the key benefits of this pivot
- ✅ **Push notifications only** - Via Firebase Cloud Messaging (FCM) for Android and APNs for iOS

This is critical to the cost model. Do not include Twilio/SMS in any cost calculations.

## App Overview
- **Native iOS app** (Swift/SwiftUI) - App Store distribution
- **Native Android app** (Kotlin/Jetpack Compose) - Play Store distribution
- Real-time stock portfolio tracking with live prices
- $9/month subscriptions via Apple/Google In-App Purchase (60% to influencer, 10% to platform, 30% to Apple/Google)
- **Push notifications for trade alerts** (NOT SMS) - free via Firebase/APNs

## Day 1 Infrastructure

**Backend**:
- Vercel Pro ($20/mo) - serverless Flask
- Supabase Pro ($25/mo) - PostgreSQL with connection pooling (500 connections)
- Upstash Redis Pro ($10/mo) - caching + rate limiting

**Stock Data**:
- Alpha Vantage Premium ($99.99/mo) - 150 requests/minute, real-time US data
- REALTIME_BULK_QUOTES endpoint: 100 symbols per request
- 90-second cache during market hours
- yfinance as automatic failover

**Push Notifications**:
- Firebase Cloud Messaging (free up to 1M/month)

**Payments**:
- Apple StoreKit 2 / Google Play Billing (NOT Stripe)
- 30% platform fee handled by Apple/Google
- No Stripe integration needed for subscriptions

**Cost Summary** (NO SMS/Twilio costs):
| Service | Monthly Cost |
|---------|--------------|
| Vercel Pro | $20 |
| Supabase Pro | $25 |
| Upstash Redis Pro | $10 |
| Alpha Vantage Premium | $99.99 |
| Firebase FCM | $0 (free) |
| Apple/Google IAP | $0 (30% deducted from revenue) |
| **Twilio/SMS** | **$0 (eliminated)** |
| **Total** | **~$155/mo** |

## Expected Load at 5K Concurrent

**Assumptions**:
- 5,000 concurrent users during market hours (9:30 AM - 4:00 PM ET)
- Average user has 15 stocks in portfolio
- Average user checks portfolio 10x/day during market hours
- 1,000 unique stocks across all portfolios
- 500 trades/day across platform
- 10 notifications per subscriber per day

**Calculated Load**:
- API requests: ~2,000/minute (portfolio refreshes + leaderboard)
- Alpha Vantage: 10-15 requests/minute with batching (100 symbols × 10 batches = 1,000 unique stocks)
- Database queries: ~500/second (with caching)
- Push notifications: ~5,000/hour during trading (500 trades × 10 subscribers avg)

## My Questions

1. **Is Supabase Pro (500 pooled connections) sufficient for 5K concurrent?** Or should I start with dedicated Postgres?

2. **Alpha Vantage at 150 req/min**: With REALTIME_BULK_QUOTES (100 symbols/req) and 90-second caching, can I serve 1,000 unique stocks to 5K users? My math: 1,000 stocks ÷ 100 per request = 10 requests every 90 seconds = ~7 req/min. Is this correct?

3. **Redis sizing**: Is Upstash Pro (10K commands/day) enough, or do I need higher tier?

4. **Push notification throughput**: At 500 trades/day with avg 10 subscribers each = 5,000 notifications/day. Firebase free tier handles 1M/month. Am I missing any bottlenecks?

5. **What's my weakest link?** Where will I hit scaling issues first?

6. **Cost efficiency**: At $155/mo infrastructure + $99.99 Alpha Vantage = ~$255/mo total. Is this reasonable for 10K users, or am I over/under-provisioned?

Please be specific about where my calculations might be wrong.

---

**End of Grok prompt**

---

## Summary

| Phase | Duration | Key Deliverables | Success Criteria |
|-------|----------|------------------|------------------|
| **1** | 2 weeks | Backend APIs, DB migrations, Push service | All tests pass, endpoints functional |
| **2** | 4 weeks | iOS app with full features | TestFlight approved, 10 beta testers |
| **3** | 4 weeks | Android app with full features | Internal testing approved, 10 beta testers |
| **4** | 2 weeks | Integration, load testing, security | 5K concurrent load test passes |
| **5** | 2 weeks | Launch, monitoring, support | Apps live in stores, metrics healthy |

**Total**: 14 weeks (3.5 months)

---

## Grok Review Notes (January 21, 2026)

### ✅ Incorporated Recommendations

| Recommendation | Implementation |
|----------------|----------------|
| DDoS protection | Added Vercel WAF ($20/mo) as optional security layer |
| 10-15% cost buffer | Updated total to ~$210-220/mo with buffer |
| App approval delays | Added early submission note in Week 6 (iOS) |
| Agent performance dashboard | Consider `/admin/agent-perf` in future iteration |
| Load testing with Locust | Already in Phase 4 ✓ |
| Redis caching early | Already planned (Upstash Redis Pro) ✓ |

### ❌ IGNORE These Recommendations (Wrong Architecture)

Grok referenced outdated documents and assumed SMS/Stripe. **These do NOT apply:**

| Grok Said | Why It's Wrong |
|-----------|----------------|
| Twilio: $5-200/mo | **$0** - We use push notifications, NOT SMS |
| Stripe: $5-300/mo | **$0** - We use Apple/Google IAP, NOT Stripe |
| "$0.008/SMS spikes" | N/A - No SMS in this architecture |
| "SendGrid email hybrid" | N/A - Push notifications only |
| "Flutter for code reuse" | We chose native Swift/Kotlin for best UX |

**Critical Clarification**: This mobile architecture specifically **eliminates** per-message costs. One of the key benefits of pivoting from web+SMS to native apps is that notification costs are $0 (Firebase FCM free tier).

---

*Document maintained by: Development Team*
*Last updated: January 21, 2026*
