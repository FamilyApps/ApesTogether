"""
SMS utilities for Twilio integration and phone verification
"""
import os
import random
import string
from datetime import datetime, timedelta
from flask import current_app
from models import db, SMSNotification, User
import logging

# Twilio configuration (will be set up when user adds credentials)
TWILIO_ACCOUNT_SID = os.environ.get('TWILIO_ACCOUNT_SID')
TWILIO_AUTH_TOKEN = os.environ.get('TWILIO_AUTH_TOKEN')
TWILIO_PHONE_NUMBER = os.environ.get('TWILIO_PHONE_NUMBER')

# Mock mode for testing without Twilio credentials
MOCK_SMS_MODE = not all([TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_PHONE_NUMBER])

def send_sms(phone_number, message):
    """
    Send SMS message to phone number
    Returns (success: bool, message_id: str or None, error: str or None)
    """
    if MOCK_SMS_MODE:
        # Mock SMS sending for testing
        current_app.logger.info(f"MOCK SMS to {phone_number}: {message}")
        return True, f"mock_msg_{random.randint(1000, 9999)}", None
    
    try:
        # Real Twilio implementation
        from twilio.rest import Client
        client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        message = client.messages.create(
            body=message,
            from_=TWILIO_PHONE_NUMBER,
            to=phone_number
        )
        return True, message.sid, None
        
    except Exception as e:
        current_app.logger.error(f"SMS sending failed: {str(e)}")
        return False, None, str(e)

def generate_verification_code():
    """Generate a 6-digit verification code"""
    return ''.join(random.choices(string.digits, k=6))

def send_verification_sms(user_id, phone_number):
    """
    Send verification code to user's phone number
    Returns (success: bool, error: str or None)
    """
    # Generate verification code
    code = generate_verification_code()
    expires_at = datetime.now() + timedelta(minutes=10)  # 10 minute expiry
    
    # Get or create SMS notification record
    sms_notification = SMSNotification.query.filter_by(user_id=user_id).first()
    if not sms_notification:
        sms_notification = SMSNotification(user_id=user_id)
        db.session.add(sms_notification)
    
    # Update phone number and verification code
    sms_notification.phone_number = phone_number
    sms_notification.verification_code = code
    sms_notification.verification_expires = expires_at
    sms_notification.is_verified = False
    sms_notification.updated_at = datetime.now()
    
    db.session.commit()
    
    # Send SMS
    message = f"Your ApesTogetherAI verification code is: {code}. This code expires in 10 minutes."
    success, message_id, error = send_sms(phone_number, message)
    
    if success:
        current_app.logger.info(f"Verification SMS sent to user {user_id} at {phone_number}")
        return True, None
    else:
        current_app.logger.error(f"Failed to send verification SMS to user {user_id}: {error}")
        return False, error

def verify_phone_number(user_id, code):
    """
    Verify phone number with provided code
    Returns (success: bool, error: str or None)
    """
    sms_notification = SMSNotification.query.filter_by(user_id=user_id).first()
    
    if not sms_notification:
        return False, "No phone verification in progress"
    
    if not sms_notification.verification_code:
        return False, "No verification code found"
    
    if datetime.now() > sms_notification.verification_expires:
        return False, "Verification code has expired"
    
    if sms_notification.verification_code != code:
        return False, "Invalid verification code"
    
    # Mark as verified
    sms_notification.is_verified = True
    sms_notification.verification_code = None
    sms_notification.verification_expires = None
    sms_notification.updated_at = datetime.now()
    
    db.session.commit()
    
    current_app.logger.info(f"Phone number verified for user {user_id}")
    return True, None

def send_trade_confirmation_sms(user_id, ticker, quantity, action="bought"):
    """
    Send trade confirmation SMS to user if they have SMS enabled and verified
    Returns (success: bool, error: str or None)
    """
    sms_notification = SMSNotification.query.filter_by(user_id=user_id).first()
    
    if not sms_notification or not sms_notification.is_verified or not sms_notification.sms_enabled:
        return False, "SMS not enabled or verified for user"
    
    message = f"Trade confirmed: {action} {quantity} shares of {ticker}. Portfolio updated on ApesTogetherAI."
    success, message_id, error = send_sms(sms_notification.phone_number, message)
    
    if success:
        current_app.logger.info(f"Trade confirmation SMS sent to user {user_id}")
    
    return success, error

def send_subscriber_notification_sms(subscriber_user_id, trader_username, ticker, quantity, action="bought"):
    """
    Send notification SMS to subscriber when someone they follow makes a trade
    Returns (success: bool, error: str or None)
    """
    sms_notification = SMSNotification.query.filter_by(user_id=subscriber_user_id).first()
    
    if not sms_notification or not sms_notification.is_verified or not sms_notification.sms_enabled:
        return False, "SMS not enabled or verified for subscriber"
    
    message = f"🚨 {trader_username} just {action} {quantity} shares of {ticker}! Check your ApesTogetherAI dashboard for details."
    success, message_id, error = send_sms(sms_notification.phone_number, message)
    
    if success:
        current_app.logger.info(f"Subscriber notification SMS sent to user {subscriber_user_id}")
    
    return success, error

def parse_sms_trade_submission(message_body):
    """
    Parse incoming SMS for trade submissions
    Expected format: "BUY 10 AAPL" or "SELL 5 TSLA"
    Returns (success: bool, action: str, quantity: float, ticker: str, error: str or None)
    """
    try:
        parts = message_body.strip().upper().split()
        
        if len(parts) != 3:
            return False, None, None, None, "Invalid format. Use: BUY/SELL [quantity] [ticker]"
        
        action, quantity_str, ticker = parts
        
        if action not in ['BUY', 'SELL']:
            return False, None, None, None, "Action must be BUY or SELL"
        
        try:
            quantity = float(quantity_str)
            if quantity <= 0:
                return False, None, None, None, "Quantity must be positive"
        except ValueError:
            return False, None, None, None, "Invalid quantity format"
        
        if not ticker.isalpha() or len(ticker) > 5:
            return False, None, None, None, "Invalid ticker format"
        
        return True, action, quantity, ticker, None
        
    except Exception as e:
        return False, None, None, None, f"Error parsing message: {str(e)}"

def get_user_sms_settings(user_id):
    """Get user's SMS notification settings"""
    sms_notification = SMSNotification.query.filter_by(user_id=user_id).first()
    
    if not sms_notification:
        return {
            'phone_number': None,
            'is_verified': False,
            'sms_enabled': True,
            'has_settings': False
        }
    
    return {
        'phone_number': sms_notification.phone_number,
        'is_verified': sms_notification.is_verified,
        'sms_enabled': sms_notification.sms_enabled,
        'has_settings': True
    }
