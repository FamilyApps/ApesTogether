"""
In-App Purchase Validation Service for Apes Together Mobile App
Handles Apple App Store and Google Play receipt verification

Setup required:
Apple:
- APPLE_SHARED_SECRET: App-specific shared secret from App Store Connect
- APPLE_BUNDLE_ID: Your app's bundle ID (e.g., com.apestogether.app)

Google:
- GOOGLE_PLAY_CREDENTIALS_JSON: Service account JSON for Google Play Developer API
- GOOGLE_PLAY_PACKAGE_NAME: Your app's package name
"""

import os
import json
import logging
import httpx
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, Tuple
from enum import Enum

logger = logging.getLogger(__name__)


class Platform(Enum):
    APPLE = 'apple'
    GOOGLE = 'google'


class SubscriptionStatus(Enum):
    ACTIVE = 'active'
    EXPIRED = 'expired'
    CANCELED = 'canceled'
    REFUNDED = 'refunded'
    GRACE_PERIOD = 'grace_period'
    PENDING = 'pending'


class IAPValidationService:
    """Service for validating In-App Purchase receipts"""
    
    # Apple endpoints
    APPLE_PRODUCTION_URL = 'https://buy.itunes.apple.com/verifyReceipt'
    APPLE_SANDBOX_URL = 'https://sandbox.itunes.apple.com/verifyReceipt'
    
    # Our product ID
    PRODUCT_ID = 'com.apestogether.subscription.monthly'
    
    # Pricing
    SUBSCRIPTION_PRICE = 9.00
    INFLUENCER_PAYOUT = 5.40  # 60%
    PLATFORM_REVENUE = 0.90   # 10%
    STORE_FEE = 2.70          # 30%
    
    def __init__(self):
        # Apple credentials
        self.apple_shared_secret = os.environ.get('APPLE_SHARED_SECRET')
        self.apple_bundle_id = os.environ.get('APPLE_BUNDLE_ID', 'com.apestogether.app')
        
        # Google credentials
        self.google_credentials = None
        google_creds_json = os.environ.get('GOOGLE_PLAY_CREDENTIALS_JSON')
        if google_creds_json:
            try:
                self.google_credentials = json.loads(google_creds_json)
            except json.JSONDecodeError:
                logger.error("Invalid GOOGLE_PLAY_CREDENTIALS_JSON")
        
        self.google_package_name = os.environ.get('GOOGLE_PLAY_PACKAGE_NAME', 'com.apestogether.app')
    
    async def validate_apple_receipt(
        self,
        receipt_data: str,
        exclude_old_transactions: bool = True
    ) -> Dict[str, Any]:
        """
        Validate Apple App Store receipt
        
        Args:
            receipt_data: Base64-encoded receipt data from StoreKit
            exclude_old_transactions: Only return latest transaction
            
        Returns:
            Dict with validation result and subscription info
        """
        if not self.apple_shared_secret:
            logger.error("APPLE_SHARED_SECRET not configured")
            return {'valid': False, 'error': 'server_config_error'}
        
        payload = {
            'receipt-data': receipt_data,
            'password': self.apple_shared_secret,
            'exclude-old-transactions': exclude_old_transactions
        }
        
        async with httpx.AsyncClient() as client:
            # Try production first
            response = await client.post(
                self.APPLE_PRODUCTION_URL,
                json=payload,
                timeout=30.0
            )
            result = response.json()
            
            # Status 21007 means sandbox receipt sent to production
            if result.get('status') == 21007:
                response = await client.post(
                    self.APPLE_SANDBOX_URL,
                    json=payload,
                    timeout=30.0
                )
                result = response.json()
        
        return self._parse_apple_response(result)
    
    def _parse_apple_response(self, response: Dict[str, Any]) -> Dict[str, Any]:
        """Parse Apple's receipt validation response"""
        status = response.get('status', -1)
        
        # Apple status codes
        if status != 0:
            error_messages = {
                21000: 'App Store could not read the receipt',
                21002: 'Receipt data was malformed',
                21003: 'Receipt could not be authenticated',
                21004: 'Shared secret mismatch',
                21005: 'Receipt server unavailable',
                21006: 'Valid receipt but subscription expired',
                21007: 'Sandbox receipt sent to production',
                21008: 'Production receipt sent to sandbox',
                21010: 'Account not found',
            }
            return {
                'valid': False,
                'error': error_messages.get(status, f'Unknown error: {status}'),
                'status_code': status
            }
        
        # Get latest receipt info
        receipt_info = response.get('receipt', {})
        latest_receipt_info = response.get('latest_receipt_info', [])
        pending_renewal_info = response.get('pending_renewal_info', [])
        
        if not latest_receipt_info:
            # Try in_app array for non-subscription purchases
            latest_receipt_info = receipt_info.get('in_app', [])
        
        if not latest_receipt_info:
            return {'valid': False, 'error': 'no_transactions_found'}
        
        # Get the most recent transaction
        latest_transaction = max(
            latest_receipt_info,
            key=lambda x: int(x.get('purchase_date_ms', 0))
        )
        
        # Parse dates
        purchase_date = datetime.fromtimestamp(
            int(latest_transaction.get('purchase_date_ms', 0)) / 1000
        )
        expires_date = None
        if latest_transaction.get('expires_date_ms'):
            expires_date = datetime.fromtimestamp(
                int(latest_transaction['expires_date_ms']) / 1000
            )
        
        # Determine subscription status
        now = datetime.utcnow()
        if expires_date and expires_date > now:
            status = SubscriptionStatus.ACTIVE
        elif expires_date:
            # Check for grace period
            grace_period_expires = response.get('grace_period_expires_date_ms')
            if grace_period_expires:
                grace_date = datetime.fromtimestamp(int(grace_period_expires) / 1000)
                if grace_date > now:
                    status = SubscriptionStatus.GRACE_PERIOD
                else:
                    status = SubscriptionStatus.EXPIRED
            else:
                status = SubscriptionStatus.EXPIRED
        else:
            status = SubscriptionStatus.ACTIVE  # Non-renewing or lifetime
        
        # Check for cancellation/refund
        cancellation_date = latest_transaction.get('cancellation_date_ms')
        if cancellation_date:
            status = SubscriptionStatus.REFUNDED
        
        return {
            'valid': True,
            'platform': Platform.APPLE.value,
            'product_id': latest_transaction.get('product_id'),
            'transaction_id': latest_transaction.get('transaction_id'),
            'original_transaction_id': latest_transaction.get('original_transaction_id'),
            'purchase_date': purchase_date,
            'expires_date': expires_date,
            'status': status.value,
            'is_trial': latest_transaction.get('is_trial_period') == 'true',
            'is_in_intro_offer': latest_transaction.get('is_in_intro_offer_period') == 'true',
            'auto_renew_status': self._get_auto_renew_status(pending_renewal_info),
            'latest_receipt': response.get('latest_receipt'),
            'price': self.SUBSCRIPTION_PRICE,
            'influencer_payout': self.INFLUENCER_PAYOUT,
            'platform_revenue': self.PLATFORM_REVENUE,
            'store_fee': self.STORE_FEE,
        }
    
    def _get_auto_renew_status(self, pending_renewal_info: list) -> bool:
        """Check if auto-renewal is enabled"""
        if not pending_renewal_info:
            return False
        return pending_renewal_info[0].get('auto_renew_status') == '1'
    
    async def validate_google_purchase(
        self,
        purchase_token: str,
        product_id: str = None
    ) -> Dict[str, Any]:
        """
        Validate Google Play purchase
        
        Args:
            purchase_token: Token from Google Play Billing
            product_id: Product ID (defaults to our subscription)
            
        Returns:
            Dict with validation result and subscription info
        """
        if not self.google_credentials:
            logger.error("GOOGLE_PLAY_CREDENTIALS_JSON not configured")
            return {'valid': False, 'error': 'server_config_error'}
        
        product_id = product_id or self.PRODUCT_ID
        
        try:
            # Get access token
            access_token = await self._get_google_access_token()
            if not access_token:
                return {'valid': False, 'error': 'failed_to_get_access_token'}
            
            # Verify subscription
            url = (
                f"https://androidpublisher.googleapis.com/androidpublisher/v3/"
                f"applications/{self.google_package_name}/purchases/subscriptions/"
                f"{product_id}/tokens/{purchase_token}"
            )
            
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    url,
                    headers={'Authorization': f'Bearer {access_token}'},
                    timeout=30.0
                )
                
                if response.status_code == 404:
                    return {'valid': False, 'error': 'purchase_not_found'}
                elif response.status_code != 200:
                    return {'valid': False, 'error': f'api_error_{response.status_code}'}
                
                result = response.json()
            
            return self._parse_google_response(result, purchase_token, product_id)
            
        except Exception as e:
            logger.error(f"Google validation error: {e}")
            return {'valid': False, 'error': str(e)}
    
    async def _get_google_access_token(self) -> Optional[str]:
        """Get OAuth2 access token for Google Play API"""
        try:
            import jwt
            from datetime import datetime, timedelta
            
            # Create JWT
            now = datetime.utcnow()
            payload = {
                'iss': self.google_credentials['client_email'],
                'scope': 'https://www.googleapis.com/auth/androidpublisher',
                'aud': 'https://oauth2.googleapis.com/token',
                'iat': now,
                'exp': now + timedelta(hours=1)
            }
            
            token = jwt.encode(
                payload,
                self.google_credentials['private_key'],
                algorithm='RS256'
            )
            
            # Exchange for access token
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    'https://oauth2.googleapis.com/token',
                    data={
                        'grant_type': 'urn:ietf:params:oauth:grant-type:jwt-bearer',
                        'assertion': token
                    },
                    timeout=30.0
                )
                
                if response.status_code == 200:
                    return response.json().get('access_token')
                else:
                    logger.error(f"Failed to get Google access token: {response.text}")
                    return None
                    
        except ImportError:
            logger.error("PyJWT not installed, required for Google Play validation")
            return None
        except Exception as e:
            logger.error(f"Error getting Google access token: {e}")
            return None
    
    def _parse_google_response(
        self,
        response: Dict[str, Any],
        purchase_token: str,
        product_id: str
    ) -> Dict[str, Any]:
        """Parse Google Play subscription response"""
        
        # Parse timestamps (Google uses milliseconds)
        start_time_ms = int(response.get('startTimeMillis', 0))
        expiry_time_ms = int(response.get('expiryTimeMillis', 0))
        
        purchase_date = datetime.fromtimestamp(start_time_ms / 1000) if start_time_ms else None
        expires_date = datetime.fromtimestamp(expiry_time_ms / 1000) if expiry_time_ms else None
        
        # Determine status
        now = datetime.utcnow()
        cancel_reason = response.get('cancelReason')
        
        if cancel_reason == 1:
            status = SubscriptionStatus.CANCELED
        elif cancel_reason == 2:
            status = SubscriptionStatus.REFUNDED
        elif expires_date and expires_date > now:
            status = SubscriptionStatus.ACTIVE
        else:
            status = SubscriptionStatus.EXPIRED
        
        # Check acknowledgement
        acknowledged = response.get('acknowledgementState') == 1
        
        return {
            'valid': True,
            'platform': Platform.GOOGLE.value,
            'product_id': product_id,
            'transaction_id': response.get('orderId'),
            'original_transaction_id': response.get('linkedPurchaseToken', purchase_token),
            'purchase_token': purchase_token,
            'purchase_date': purchase_date,
            'expires_date': expires_date,
            'status': status.value,
            'is_trial': response.get('paymentState') == 2,  # Free trial
            'auto_renew_status': response.get('autoRenewing', False),
            'acknowledged': acknowledged,
            'price': self.SUBSCRIPTION_PRICE,
            'influencer_payout': self.INFLUENCER_PAYOUT,
            'platform_revenue': self.PLATFORM_REVENUE,
            'store_fee': self.STORE_FEE,
        }
    
    async def acknowledge_google_purchase(self, purchase_token: str, product_id: str = None) -> bool:
        """
        Acknowledge a Google Play purchase (required within 3 days)
        """
        if not self.google_credentials:
            return False
        
        product_id = product_id or self.PRODUCT_ID
        
        try:
            access_token = await self._get_google_access_token()
            if not access_token:
                return False
            
            url = (
                f"https://androidpublisher.googleapis.com/androidpublisher/v3/"
                f"applications/{self.google_package_name}/purchases/subscriptions/"
                f"{product_id}/tokens/{purchase_token}:acknowledge"
            )
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    url,
                    headers={'Authorization': f'Bearer {access_token}'},
                    timeout=30.0
                )
                return response.status_code == 204
                
        except Exception as e:
            logger.error(f"Failed to acknowledge Google purchase: {e}")
            return False


# Singleton instance
_iap_service = None

def get_iap_service() -> IAPValidationService:
    """Get singleton IAP validation service instance"""
    global _iap_service
    if _iap_service is None:
        _iap_service = IAPValidationService()
    return _iap_service


async def validate_and_save_purchase(
    db,
    subscriber_id: int,
    subscribed_to_id: int,
    platform: str,
    receipt_data: str = None,
    purchase_token: str = None
) -> Tuple[bool, Dict[str, Any]]:
    """
    Validate a purchase and save it to the database
    
    Args:
        db: SQLAlchemy database instance
        subscriber_id: User ID of the subscriber
        subscribed_to_id: User ID of the portfolio owner being subscribed to
        platform: 'apple' or 'google'
        receipt_data: Apple receipt (base64)
        purchase_token: Google purchase token
        
    Returns:
        Tuple of (success, result_dict)
    """
    from models import InAppPurchase, MobileSubscription
    
    service = get_iap_service()
    
    # Validate based on platform
    if platform == 'apple':
        if not receipt_data:
            return False, {'error': 'receipt_data_required'}
        result = await service.validate_apple_receipt(receipt_data)
    elif platform == 'google':
        if not purchase_token:
            return False, {'error': 'purchase_token_required'}
        result = await service.validate_google_purchase(purchase_token)
    else:
        return False, {'error': 'invalid_platform'}
    
    if not result.get('valid'):
        return False, result
    
    # Check if this transaction already exists
    existing = InAppPurchase.query.filter_by(
        transaction_id=result['transaction_id']
    ).first()
    
    if existing:
        # Update existing purchase
        existing.status = result['status']
        existing.expires_date = result.get('expires_date')
        existing.updated_at = datetime.utcnow()
        db.session.commit()
        return True, {'purchase_id': existing.id, 'updated': True, **result}
    
    # Create new purchase record
    purchase = InAppPurchase(
        subscriber_id=subscriber_id,
        subscribed_to_id=subscribed_to_id,
        platform=platform,
        product_id=result['product_id'],
        transaction_id=result['transaction_id'],
        original_transaction_id=result.get('original_transaction_id'),
        receipt_data=receipt_data if platform == 'apple' else purchase_token,
        status=result['status'],
        purchase_date=result['purchase_date'],
        expires_date=result.get('expires_date'),
        price=result['price'],
        influencer_payout=result['influencer_payout'],
        platform_revenue=result['platform_revenue'],
        store_fee=result['store_fee'],
    )
    db.session.add(purchase)
    db.session.flush()  # Get the ID
    
    # Create or update mobile subscription
    existing_sub = MobileSubscription.query.filter_by(
        subscriber_id=subscriber_id,
        subscribed_to_id=subscribed_to_id
    ).first()
    
    if existing_sub:
        existing_sub.in_app_purchase_id = purchase.id
        existing_sub.status = 'active' if result['status'] == 'active' else 'expired'
        existing_sub.expires_at = result.get('expires_date')
    else:
        subscription = MobileSubscription(
            subscriber_id=subscriber_id,
            subscribed_to_id=subscribed_to_id,
            in_app_purchase_id=purchase.id,
            status='active' if result['status'] == 'active' else 'expired',
            expires_at=result.get('expires_date'),
            push_notifications_enabled=True
        )
        db.session.add(subscription)
    
    db.session.commit()
    
    # Acknowledge Google purchase if needed
    if platform == 'google' and not result.get('acknowledged'):
        await service.acknowledge_google_purchase(purchase_token)
    
    return True, {'purchase_id': purchase.id, 'subscription_created': True, **result}
