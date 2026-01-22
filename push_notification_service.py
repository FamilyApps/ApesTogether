"""
Push Notification Service for Apes Together Mobile App
Uses Firebase Cloud Messaging (FCM) for both iOS and Android

Setup required:
1. Create Firebase project at console.firebase.google.com
2. Download service account JSON key
3. Set FIREBASE_CREDENTIALS_JSON environment variable (JSON string)
   OR set FIREBASE_CREDENTIALS_PATH to file path

Environment Variables:
- FIREBASE_CREDENTIALS_JSON: JSON string of service account credentials
- FIREBASE_CREDENTIALS_PATH: Path to service account JSON file (alternative)
"""

import os
import json
import logging
from datetime import datetime
from typing import List, Dict, Optional, Any

# Firebase Admin SDK
try:
    import firebase_admin
    from firebase_admin import credentials, messaging
    FIREBASE_AVAILABLE = True
except ImportError:
    FIREBASE_AVAILABLE = False
    firebase_admin = None
    messaging = None

logger = logging.getLogger(__name__)


class PushNotificationService:
    """Service for sending push notifications via Firebase Cloud Messaging"""
    
    _initialized = False
    _app = None
    
    def __init__(self):
        self._ensure_initialized()
    
    @classmethod
    def _ensure_initialized(cls):
        """Initialize Firebase Admin SDK if not already done"""
        if cls._initialized:
            return
        
        if not FIREBASE_AVAILABLE:
            logger.warning("Firebase Admin SDK not installed. Push notifications disabled.")
            return
        
        try:
            # Try JSON string from environment first
            creds_json = os.environ.get('FIREBASE_CREDENTIALS_JSON')
            if creds_json:
                creds_dict = json.loads(creds_json)
                cred = credentials.Certificate(creds_dict)
                cls._app = firebase_admin.initialize_app(cred)
                cls._initialized = True
                logger.info("Firebase initialized from FIREBASE_CREDENTIALS_JSON")
                return
            
            # Try file path
            creds_path = os.environ.get('FIREBASE_CREDENTIALS_PATH')
            if creds_path and os.path.exists(creds_path):
                cred = credentials.Certificate(creds_path)
                cls._app = firebase_admin.initialize_app(cred)
                cls._initialized = True
                logger.info(f"Firebase initialized from {creds_path}")
                return
            
            # Try default credentials (for Google Cloud environments)
            try:
                cls._app = firebase_admin.initialize_app()
                cls._initialized = True
                logger.info("Firebase initialized with default credentials")
                return
            except Exception:
                pass
            
            logger.warning("Firebase credentials not found. Push notifications disabled.")
            
        except Exception as e:
            logger.error(f"Failed to initialize Firebase: {e}")
    
    @property
    def is_available(self) -> bool:
        """Check if push notifications are available"""
        return FIREBASE_AVAILABLE and self._initialized
    
    def send_trade_notification(
        self,
        device_tokens: List[str],
        trader_username: str,
        action: str,  # 'BUY' or 'SELL'
        ticker: str,
        quantity: float,
        price: float,
        portfolio_slug: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Send a trade alert notification to subscribers
        
        Returns:
            Dict with 'success_count', 'failure_count', 'failed_tokens'
        """
        if not self.is_available:
            logger.warning("Push notifications not available")
            return {'success_count': 0, 'failure_count': len(device_tokens), 'failed_tokens': device_tokens}
        
        if not device_tokens:
            return {'success_count': 0, 'failure_count': 0, 'failed_tokens': []}
        
        # Format the notification
        action_emoji = "🟢" if action.upper() == "BUY" else "🔴"
        title = f"{action_emoji} {trader_username} {action.upper()}"
        body = f"{quantity} {ticker} @ ${price:.2f}"
        
        # Data payload for app to handle
        data = {
            'type': 'trade_alert',
            'trader': trader_username,
            'action': action.upper(),
            'ticker': ticker,
            'quantity': str(quantity),
            'price': str(price),
            'timestamp': datetime.utcnow().isoformat(),
        }
        if portfolio_slug:
            data['portfolio_slug'] = portfolio_slug
        
        return self._send_multicast(device_tokens, title, body, data)
    
    def send_price_alert(
        self,
        device_tokens: List[str],
        ticker: str,
        current_price: float,
        change_percent: float,
        alert_type: str = 'threshold'  # 'threshold', 'daily_high', 'daily_low'
    ) -> Dict[str, Any]:
        """Send a price alert notification"""
        if not self.is_available:
            return {'success_count': 0, 'failure_count': len(device_tokens), 'failed_tokens': device_tokens}
        
        direction = "📈" if change_percent >= 0 else "📉"
        sign = "+" if change_percent >= 0 else ""
        
        title = f"{direction} {ticker} Price Alert"
        body = f"${current_price:.2f} ({sign}{change_percent:.2f}%)"
        
        data = {
            'type': 'price_alert',
            'ticker': ticker,
            'price': str(current_price),
            'change_percent': str(change_percent),
            'alert_type': alert_type,
            'timestamp': datetime.utcnow().isoformat(),
        }
        
        return self._send_multicast(device_tokens, title, body, data)
    
    def send_subscription_notification(
        self,
        device_token: str,
        notification_type: str,  # 'new_subscriber', 'subscription_expired', 'subscription_renewed'
        subscriber_username: Optional[str] = None,
        portfolio_username: Optional[str] = None
    ) -> Dict[str, Any]:
        """Send subscription-related notifications"""
        if not self.is_available:
            return {'success_count': 0, 'failure_count': 1, 'failed_tokens': [device_token]}
        
        if notification_type == 'new_subscriber':
            title = "🎉 New Subscriber!"
            body = f"{subscriber_username} subscribed to your portfolio"
        elif notification_type == 'subscription_expired':
            title = "Subscription Expired"
            body = f"Your subscription to {portfolio_username}'s portfolio has expired"
        elif notification_type == 'subscription_renewed':
            title = "✅ Subscription Renewed"
            body = f"Your subscription to {portfolio_username}'s portfolio has been renewed"
        else:
            title = "Subscription Update"
            body = "Your subscription status has changed"
        
        data = {
            'type': notification_type,
            'timestamp': datetime.utcnow().isoformat(),
        }
        if subscriber_username:
            data['subscriber'] = subscriber_username
        if portfolio_username:
            data['portfolio_owner'] = portfolio_username
        
        return self._send_single(device_token, title, body, data)
    
    def send_custom_notification(
        self,
        device_tokens: List[str],
        title: str,
        body: str,
        data: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """Send a custom notification"""
        if not self.is_available:
            return {'success_count': 0, 'failure_count': len(device_tokens), 'failed_tokens': device_tokens}
        
        return self._send_multicast(device_tokens, title, body, data or {})
    
    def _send_single(
        self,
        token: str,
        title: str,
        body: str,
        data: Dict[str, str]
    ) -> Dict[str, Any]:
        """Send notification to a single device"""
        try:
            message = messaging.Message(
                notification=messaging.Notification(
                    title=title,
                    body=body,
                ),
                data=data,
                token=token,
                # iOS specific
                apns=messaging.APNSConfig(
                    payload=messaging.APNSPayload(
                        aps=messaging.Aps(
                            sound='default',
                            badge=1,
                        )
                    )
                ),
                # Android specific
                android=messaging.AndroidConfig(
                    priority='high',
                    notification=messaging.AndroidNotification(
                        sound='default',
                        priority='high',
                    )
                )
            )
            
            response = messaging.send(message)
            logger.info(f"Successfully sent message: {response}")
            return {'success_count': 1, 'failure_count': 0, 'failed_tokens': [], 'message_id': response}
            
        except messaging.UnregisteredError:
            logger.warning(f"Token unregistered: {token[:20]}...")
            return {'success_count': 0, 'failure_count': 1, 'failed_tokens': [token], 'error': 'unregistered'}
        except Exception as e:
            logger.error(f"Failed to send notification: {e}")
            return {'success_count': 0, 'failure_count': 1, 'failed_tokens': [token], 'error': str(e)}
    
    def _send_multicast(
        self,
        tokens: List[str],
        title: str,
        body: str,
        data: Dict[str, str]
    ) -> Dict[str, Any]:
        """Send notification to multiple devices"""
        if not tokens:
            return {'success_count': 0, 'failure_count': 0, 'failed_tokens': []}
        
        # FCM multicast is limited to 500 tokens per request
        MAX_TOKENS_PER_BATCH = 500
        
        total_success = 0
        total_failure = 0
        failed_tokens = []
        
        for i in range(0, len(tokens), MAX_TOKENS_PER_BATCH):
            batch_tokens = tokens[i:i + MAX_TOKENS_PER_BATCH]
            
            try:
                message = messaging.MulticastMessage(
                    notification=messaging.Notification(
                        title=title,
                        body=body,
                    ),
                    data=data,
                    tokens=batch_tokens,
                    apns=messaging.APNSConfig(
                        payload=messaging.APNSPayload(
                            aps=messaging.Aps(
                                sound='default',
                                badge=1,
                            )
                        )
                    ),
                    android=messaging.AndroidConfig(
                        priority='high',
                        notification=messaging.AndroidNotification(
                            sound='default',
                            priority='high',
                        )
                    )
                )
                
                response = messaging.send_each_for_multicast(message)
                total_success += response.success_count
                total_failure += response.failure_count
                
                # Collect failed tokens
                for idx, send_response in enumerate(response.responses):
                    if not send_response.success:
                        failed_tokens.append(batch_tokens[idx])
                        if send_response.exception:
                            logger.warning(f"Failed to send to token: {send_response.exception}")
                
            except Exception as e:
                logger.error(f"Batch send failed: {e}")
                total_failure += len(batch_tokens)
                failed_tokens.extend(batch_tokens)
        
        logger.info(f"Multicast result: {total_success} success, {total_failure} failures")
        return {
            'success_count': total_success,
            'failure_count': total_failure,
            'failed_tokens': failed_tokens
        }
    
    def validate_token(self, token: str) -> bool:
        """
        Validate a device token by sending a dry-run message
        Returns True if token is valid
        """
        if not self.is_available:
            return False
        
        try:
            message = messaging.Message(
                token=token,
                # Minimal message for validation
                data={'validate': 'true'}
            )
            # dry_run=True validates without actually sending
            messaging.send(message, dry_run=True)
            return True
        except messaging.UnregisteredError:
            return False
        except messaging.InvalidArgumentError:
            return False
        except Exception as e:
            logger.error(f"Token validation error: {e}")
            return False


# Singleton instance
_push_service = None

def get_push_service() -> PushNotificationService:
    """Get the singleton push notification service instance"""
    global _push_service
    if _push_service is None:
        _push_service = PushNotificationService()
    return _push_service


# Convenience functions for common operations
def send_trade_alert(
    device_tokens: List[str],
    trader_username: str,
    action: str,
    ticker: str,
    quantity: float,
    price: float,
    portfolio_slug: Optional[str] = None
) -> Dict[str, Any]:
    """Send trade alert to multiple devices"""
    service = get_push_service()
    return service.send_trade_notification(
        device_tokens, trader_username, action, ticker, quantity, price, portfolio_slug
    )


def notify_subscribers_of_trade(
    db,  # SQLAlchemy db instance
    trader_user_id: int,
    action: str,
    ticker: str,
    quantity: float,
    price: float
) -> Dict[str, Any]:
    """
    Notify all subscribers of a trader about a new trade
    This is the main function to call after a trade is executed
    """
    from models import User, MobileSubscription, DeviceToken, PushNotificationLog
    
    service = get_push_service()
    if not service.is_available:
        logger.warning("Push service not available, skipping notifications")
        return {'success_count': 0, 'failure_count': 0, 'skipped': True}
    
    # Get trader info
    trader = User.query.get(trader_user_id)
    if not trader:
        return {'success_count': 0, 'failure_count': 0, 'error': 'trader_not_found'}
    
    # Get all active mobile subscribers
    active_subs = MobileSubscription.query.filter_by(
        subscribed_to_id=trader_user_id,
        status='active'
    ).all()
    
    if not active_subs:
        return {'success_count': 0, 'failure_count': 0, 'no_subscribers': True}
    
    # Get device tokens for all subscribers with notifications enabled
    subscriber_ids = [
        sub.subscriber_id for sub in active_subs 
        if sub.push_notifications_enabled
    ]
    
    device_tokens = DeviceToken.query.filter(
        DeviceToken.user_id.in_(subscriber_ids),
        DeviceToken.is_active == True
    ).all()
    
    if not device_tokens:
        return {'success_count': 0, 'failure_count': 0, 'no_tokens': True}
    
    # Send notifications
    tokens = [dt.token for dt in device_tokens]
    result = service.send_trade_notification(
        device_tokens=tokens,
        trader_username=trader.username,
        action=action,
        ticker=ticker,
        quantity=quantity,
        price=price,
        portfolio_slug=trader.portfolio_slug
    )
    
    # Log notifications
    for dt in device_tokens:
        status = 'sent' if dt.token not in result.get('failed_tokens', []) else 'failed'
        log = PushNotificationLog(
            user_id=dt.user_id,
            portfolio_owner_id=trader_user_id,
            device_token_id=dt.id,
            title=f"{'🟢' if action.upper() == 'BUY' else '🔴'} {trader.username} {action.upper()}",
            body=f"{quantity} {ticker} @ ${price:.2f}",
            data_payload={
                'type': 'trade_alert',
                'ticker': ticker,
                'action': action,
                'quantity': str(quantity),
                'price': str(price)
            },
            status=status
        )
        db.session.add(log)
        
        # Mark token as inactive if it failed
        if dt.token in result.get('failed_tokens', []):
            dt.is_active = False
        else:
            dt.last_used_at = datetime.utcnow()
    
    db.session.commit()
    
    return result
