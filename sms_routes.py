"""
SMS-related routes for phone verification and SMS management
"""
from flask import Blueprint, request, jsonify, render_template, flash, redirect, url_for
from flask_login import login_required, current_user
from models import db, SMSNotification
from sms_utils import send_verification_sms, verify_phone_number, get_user_sms_settings
import re

sms_bp = Blueprint('sms', __name__, url_prefix='/sms')

@sms_bp.route('/settings')
@login_required
def sms_settings():
    """Display SMS settings page"""
    settings = get_user_sms_settings(current_user.id)
    return render_template('sms_settings.html', settings=settings)

@sms_bp.route('/send-verification', methods=['POST'])
@login_required
def send_verification():
    """Send SMS verification code to phone number"""
    phone_number = request.form.get('phone_number', '').strip()
    
    # Basic phone number validation
    if not phone_number:
        flash('Phone number is required', 'danger')
        return redirect(url_for('sms.sms_settings'))
    
    # Remove any formatting and validate
    phone_clean = re.sub(r'[^\d+]', '', phone_number)
    if not re.match(r'^\+?1?\d{10,}$', phone_clean):
        flash('Please enter a valid phone number', 'danger')
        return redirect(url_for('sms.sms_settings'))
    
    # Ensure phone number starts with +1 for US numbers
    if not phone_clean.startswith('+'):
        if phone_clean.startswith('1'):
            phone_clean = '+' + phone_clean
        else:
            phone_clean = '+1' + phone_clean
    
    success, error = send_verification_sms(current_user.id, phone_clean)
    
    if success:
        flash('Verification code sent! Check your phone and enter the code below.', 'success')
    else:
        flash(f'Failed to send verification code: {error}', 'danger')
    
    return redirect(url_for('sms.sms_settings'))

@sms_bp.route('/verify', methods=['POST'])
@login_required
def verify():
    """Verify phone number with code"""
    code = request.form.get('verification_code', '').strip()
    
    if not code:
        flash('Verification code is required', 'danger')
        return redirect(url_for('sms.sms_settings'))
    
    success, error = verify_phone_number(current_user.id, code)
    
    if success:
        flash('Phone number verified successfully! SMS notifications are now enabled.', 'success')
    else:
        flash(f'Verification failed: {error}', 'danger')
    
    return redirect(url_for('sms.sms_settings'))

@sms_bp.route('/toggle', methods=['POST'])
@login_required
def toggle_sms():
    """Toggle SMS notifications on/off"""
    sms_notification = SMSNotification.query.filter_by(user_id=current_user.id).first()
    
    if not sms_notification:
        flash('No SMS settings found. Please add a phone number first.', 'danger')
        return redirect(url_for('sms.sms_settings'))
    
    if not sms_notification.is_verified:
        flash('Please verify your phone number before enabling SMS notifications.', 'danger')
        return redirect(url_for('sms.sms_settings'))
    
    # Toggle SMS enabled status
    sms_notification.sms_enabled = not sms_notification.sms_enabled
    db.session.commit()
    
    status = 'enabled' if sms_notification.sms_enabled else 'disabled'
    flash(f'SMS notifications {status}', 'success')
    
    return redirect(url_for('sms.sms_settings'))

@sms_bp.route('/webhook', methods=['POST'])
def sms_webhook():
    """Handle incoming SMS messages from Twilio"""
    # This will be implemented when Twilio is set up
    # For now, return a basic response
    
    from_number = request.form.get('From', '')
    message_body = request.form.get('Body', '')
    
    # Log the incoming message
    print(f"Incoming SMS from {from_number}: {message_body}")
    
    # TODO: Implement SMS trade submission parsing
    # TODO: Find user by phone number
    # TODO: Parse trade command
    # TODO: Execute trade if valid
    
    # Return TwiML response
    response = """<?xml version="1.0" encoding="UTF-8"?>
    <Response>
        <Message>Thank you for your message. SMS trading is coming soon!</Message>
    </Response>"""
    
    return response, 200, {'Content-Type': 'text/xml'}

@sms_bp.route('/api/settings')
@login_required
def api_settings():
    """API endpoint to get SMS settings"""
    settings = get_user_sms_settings(current_user.id)
    return jsonify(settings)
