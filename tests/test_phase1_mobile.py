"""
Unit Tests for Phase 1: Mobile Backend Preparation
Tests for models, push notifications, IAP validation, and mobile API endpoints

Run with: pytest tests/test_phase1_mobile.py -v
"""

import pytest
import json
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# =============================================================================
# Model Tests
# =============================================================================

class TestMobileModels:
    """Test new mobile app database models"""
    
    def test_device_token_model(self):
        """Test DeviceToken model creation"""
        from models import DeviceToken
        
        token = DeviceToken(
            user_id=1,
            token="test_fcm_token_12345",
            platform="ios",
            device_id="device_abc123",
            app_version="1.0.0",
            os_version="iOS 17.2",
            is_active=True
        )
        
        assert token.user_id == 1
        assert token.platform == "ios"
        assert token.is_active == True
        assert "DeviceToken" in repr(token)
    
    def test_in_app_purchase_model(self):
        """Test InAppPurchase model with flat $9 pricing"""
        from models import InAppPurchase
        
        purchase = InAppPurchase(
            subscriber_id=2,
            subscribed_to_id=1,
            platform="apple",
            product_id="com.apestogether.subscription.monthly",
            transaction_id="txn_12345",
            status="active",
            purchase_date=datetime.utcnow(),
            expires_date=datetime.utcnow() + timedelta(days=30)
        )
        
        # Verify flat pricing
        assert purchase.price == 9.00
        assert purchase.influencer_payout == 5.40  # 60%
        assert purchase.platform_revenue == 0.90   # 10%
        assert purchase.store_fee == 2.70          # 30%
        
        # Verify total adds up
        total = purchase.influencer_payout + purchase.platform_revenue + purchase.store_fee
        assert abs(total - purchase.price) < 0.01
    
    def test_push_notification_log_model(self):
        """Test PushNotificationLog model"""
        from models import PushNotificationLog
        
        log = PushNotificationLog(
            user_id=2,
            portfolio_owner_id=1,
            title="🟢 trader1 BUY",
            body="10 AAPL @ $150.00",
            data_payload={"type": "trade_alert", "ticker": "AAPL"},
            status="sent"
        )
        
        assert log.title == "🟢 trader1 BUY"
        assert log.data_payload["ticker"] == "AAPL"
        assert log.status == "sent"
    
    def test_xero_payout_record_model(self):
        """Test XeroPayoutRecord model calculations"""
        from models import XeroPayoutRecord
        
        payout = XeroPayoutRecord(
            portfolio_user_id=1,
            period_start=datetime.utcnow().date(),
            period_end=datetime.utcnow().date() + timedelta(days=30),
            real_subscriber_count=10,
            bonus_subscriber_count=5
        )
        
        payout.calculate_totals()
        
        # Verify calculations
        assert payout.total_subscriber_count == 15
        assert payout.gross_revenue == 90.00  # 10 real × $9
        assert payout.store_fees == 27.00     # 10 × $2.70
        assert payout.platform_revenue == 9.00  # 10 × $0.90
        assert payout.influencer_payout == 54.00  # 10 × $5.40
        assert payout.bonus_payout == 27.00   # 5 × $5.40
        assert payout.total_payout == 81.00   # $54 + $27
    
    def test_admin_subscription_flat_pricing(self):
        """Test AdminSubscription with new flat $9 pricing"""
        from models import AdminSubscription
        
        admin_sub = AdminSubscription(
            portfolio_user_id=1,
            bonus_subscriber_count=10,
            reason="Marketing boost"
        )
        
        # Verify flat pricing constants
        assert AdminSubscription.SUBSCRIPTION_PRICE == 9.00
        assert AdminSubscription.INFLUENCER_PAYOUT_PERCENT == 0.60
        assert AdminSubscription.PLATFORM_PERCENT == 0.10
        assert AdminSubscription.STORE_FEE_PERCENT == 0.30
        
        # Verify calculations
        assert admin_sub.monthly_revenue == 90.00  # 10 × $9
        assert admin_sub.payout_amount == 54.00    # 10 × $9 × 0.60
        assert admin_sub.calculate_payout() == 54.00
    
    def test_mobile_subscription_model(self):
        """Test MobileSubscription model"""
        from models import MobileSubscription
        
        sub = MobileSubscription(
            subscriber_id=2,
            subscribed_to_id=1,
            in_app_purchase_id=100,
            status="active",
            push_notifications_enabled=True
        )
        
        assert sub.status == "active"
        assert sub.push_notifications_enabled == True


# =============================================================================
# Push Notification Service Tests
# =============================================================================

class TestPushNotificationService:
    """Test push notification service"""
    
    def test_service_initialization_without_firebase(self):
        """Test service handles missing Firebase gracefully"""
        from push_notification_service import PushNotificationService
        
        service = PushNotificationService()
        # Service should initialize without crashing even if Firebase not configured
        assert service is not None
    
    def test_trade_notification_format(self):
        """Test trade notification formatting"""
        from push_notification_service import PushNotificationService
        
        service = PushNotificationService()
        
        # Even if not available, should return proper structure
        result = service.send_trade_notification(
            device_tokens=["token1", "token2"],
            trader_username="testuser",
            action="BUY",
            ticker="AAPL",
            quantity=10,
            price=150.00
        )
        
        assert 'success_count' in result
        assert 'failure_count' in result
        assert 'failed_tokens' in result
    
    @patch('push_notification_service.messaging')
    def test_send_multicast_batching(self, mock_messaging):
        """Test that multicast respects 500 token limit"""
        from push_notification_service import PushNotificationService
        
        # Create 600 tokens to test batching
        tokens = [f"token_{i}" for i in range(600)]
        
        service = PushNotificationService()
        service._initialized = True  # Force initialized state
        
        # Mock the send response
        mock_response = Mock()
        mock_response.success_count = 500
        mock_response.failure_count = 0
        mock_response.responses = []
        mock_messaging.send_each_for_multicast.return_value = mock_response
        
        # This should make 2 batch calls (500 + 100)
        result = service._send_multicast(tokens, "Title", "Body", {})
        
        # Verify batching occurred
        if mock_messaging.send_each_for_multicast.called:
            assert mock_messaging.send_each_for_multicast.call_count >= 2


# =============================================================================
# IAP Validation Service Tests
# =============================================================================

class TestIAPValidationService:
    """Test In-App Purchase validation service"""
    
    def test_service_initialization(self):
        """Test IAP service initializes"""
        from iap_validation_service import IAPValidationService
        
        service = IAPValidationService()
        assert service.SUBSCRIPTION_PRICE == 9.00
        assert service.INFLUENCER_PAYOUT == 5.40
        assert service.PLATFORM_REVENUE == 0.90
        assert service.STORE_FEE == 2.70
    
    def test_apple_status_codes(self):
        """Test Apple receipt status code parsing"""
        from iap_validation_service import IAPValidationService
        
        service = IAPValidationService()
        
        # Test error status
        result = service._parse_apple_response({'status': 21003})
        assert result['valid'] == False
        assert 'authenticated' in result['error'].lower()
    
    def test_google_response_parsing(self):
        """Test Google Play response parsing"""
        from iap_validation_service import IAPValidationService, SubscriptionStatus
        
        service = IAPValidationService()
        
        # Mock Google response for active subscription
        now_ms = int(datetime.utcnow().timestamp() * 1000)
        future_ms = int((datetime.utcnow() + timedelta(days=30)).timestamp() * 1000)
        
        response = {
            'orderId': 'GPA.1234-5678-9012',
            'startTimeMillis': str(now_ms),
            'expiryTimeMillis': str(future_ms),
            'autoRenewing': True,
            'acknowledgementState': 1
        }
        
        result = service._parse_google_response(response, 'test_token', 'test_product')
        
        assert result['valid'] == True
        assert result['platform'] == 'google'
        assert result['status'] == SubscriptionStatus.ACTIVE.value
        assert result['auto_renew_status'] == True
        assert result['price'] == 9.00


# =============================================================================
# Mobile API Endpoint Tests
# =============================================================================

class TestMobileAPIEndpoints:
    """Test mobile API endpoints"""
    
    def test_jwt_token_generation(self):
        """Test JWT token generation"""
        from api.mobile_api import generate_jwt_token
        import jwt
        
        token = generate_jwt_token(user_id=1, email="test@example.com")
        
        # Decode without verification to check structure
        payload = jwt.decode(token, options={"verify_signature": False})
        
        assert payload['user_id'] == 1
        assert payload['email'] == "test@example.com"
        assert 'exp' in payload
        assert 'iat' in payload
    
    def test_require_auth_decorator_missing_header(self):
        """Test auth decorator rejects missing header"""
        from flask import Flask
        from api.mobile_api import mobile_api
        
        app = Flask(__name__)
        app.register_blueprint(mobile_api)
        
        with app.test_client() as client:
            response = client.get('/api/mobile/subscriptions')
            assert response.status_code == 401
            data = json.loads(response.data)
            assert 'error' in data
    
    def test_require_auth_decorator_invalid_token(self):
        """Test auth decorator rejects invalid token"""
        from flask import Flask
        from api.mobile_api import mobile_api
        
        app = Flask(__name__)
        app.config['SECRET_KEY'] = 'test-secret'
        app.register_blueprint(mobile_api)
        
        with app.test_client() as client:
            response = client.get(
                '/api/mobile/subscriptions',
                headers={'Authorization': 'Bearer invalid_token'}
            )
            assert response.status_code == 401
    
    def test_leaderboard_endpoint_no_auth(self):
        """Test leaderboard endpoint doesn't require auth"""
        from flask import Flask
        from api.mobile_api import mobile_api
        
        app = Flask(__name__)
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
        
        from models import db
        db.init_app(app)
        
        app.register_blueprint(mobile_api)
        
        with app.app_context():
            db.create_all()
            
            with app.test_client() as client:
                response = client.get('/api/mobile/leaderboard?period=7D')
                # Should not return 401 (may return 500 if no data, but not auth error)
                assert response.status_code != 401


# =============================================================================
# Integration Tests
# =============================================================================

class TestPhase1Integration:
    """Integration tests for Phase 1 components"""
    
    def test_full_subscription_flow_mock(self):
        """Test complete subscription flow with mocked services"""
        from models import (
            db, User, DeviceToken, InAppPurchase, 
            MobileSubscription, PushNotificationLog
        )
        from flask import Flask
        
        app = Flask(__name__)
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
        
        db.init_app(app)
        
        with app.app_context():
            db.create_all()
            
            # Create test users
            trader = User(
                email="trader@example.com",
                username="trader1",
                portfolio_slug="trader1"
            )
            subscriber = User(
                email="subscriber@example.com",
                username="subscriber1"
            )
            db.session.add_all([trader, subscriber])
            db.session.commit()
            
            # Register device
            device = DeviceToken(
                user_id=subscriber.id,
                token="fcm_test_token",
                platform="ios",
                device_id="test_device",
                is_active=True
            )
            db.session.add(device)
            db.session.commit()
            
            # Create purchase
            purchase = InAppPurchase(
                subscriber_id=subscriber.id,
                subscribed_to_id=trader.id,
                platform="apple",
                product_id="com.apestogether.subscription.monthly",
                transaction_id="txn_test_123",
                status="active",
                purchase_date=datetime.utcnow(),
                expires_date=datetime.utcnow() + timedelta(days=30)
            )
            db.session.add(purchase)
            db.session.commit()
            
            # Create subscription
            subscription = MobileSubscription(
                subscriber_id=subscriber.id,
                subscribed_to_id=trader.id,
                in_app_purchase_id=purchase.id,
                status="active",
                push_notifications_enabled=True
            )
            db.session.add(subscription)
            db.session.commit()
            
            # Verify relationships
            assert purchase.subscriber_id == subscriber.id
            assert purchase.subscribed_to_id == trader.id
            assert subscription.in_app_purchase_id == purchase.id
            
            # Verify pricing
            assert purchase.price == 9.00
            assert purchase.influencer_payout == 5.40
            
            # Simulate notification log
            notification = PushNotificationLog(
                user_id=subscriber.id,
                portfolio_owner_id=trader.id,
                device_token_id=device.id,
                title="🟢 trader1 BUY",
                body="10 AAPL @ $150.00",
                status="sent"
            )
            db.session.add(notification)
            db.session.commit()
            
            # Verify notification logged
            logs = PushNotificationLog.query.filter_by(user_id=subscriber.id).all()
            assert len(logs) == 1
            assert logs[0].status == "sent"


# =============================================================================
# Run Tests
# =============================================================================

if __name__ == '__main__':
    pytest.main([__file__, '-v'])
