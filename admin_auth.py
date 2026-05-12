"""
Shared admin authentication decorator for all admin route files.

Usage:
    from admin_auth import admin_required

Auth posture (as of 2026-05-12):
    `admin_required` now requires EITHER:
      (a) the ADMIN_API_KEY header `X-Admin-Key` (for scripts / cron / curl)
      (b) a Flask session with `email == ADMIN_EMAIL` AND `admin_2fa_verified == True`
          (set by the 2FA gate at /admin-panel after a successful TOTP entry).

    Previously this decorator only checked email, which allowed any session
    that authenticated as admin@apestogether.ai (e.g., via the normal Google
    OAuth flow) to access destructive admin endpoints WITHOUT going through
    the 2FA gate. Stolen-credentials attack vector now closed.
"""
import os
from functools import wraps
from flask import jsonify, session, redirect, url_for, flash, request
from flask_login import current_user

ADMIN_EMAIL = os.environ.get('ADMIN_EMAIL', 'admin@apestogether.ai')


def _wants_html_response() -> bool:
    """Heuristic: is the caller a browser navigating to an HTML page?

    True for browser navigation (Accept includes text/html and not application/json),
    False for AJAX / SPA fetch calls (which set Accept: application/json or use
    X-Requested-With: XMLHttpRequest).
    """
    accepts = request.accept_mimetypes
    if request.is_json:
        return False
    if request.headers.get('X-Requested-With', '') == 'XMLHttpRequest':
        return False
    return accepts.accept_html and not accepts.accept_json


def admin_required(f):
    """Decorator: admin identity + 2FA verification (or X-Admin-Key for scripts).

    Behavior:
      - Accepts `X-Admin-Key: <ADMIN_API_KEY>` header for scripts/automation.
      - Accepts Flask session with `email == ADMIN_EMAIL` AND
        `session['admin_2fa_verified'] == True` (set by /admin-panel TOTP gate).
      - For HTML browser requests with admin email but missing 2FA flag,
        redirects to /admin-panel so the user can complete TOTP.
      - For AJAX requests, returns JSON 401/403 errors.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Path 1: X-Admin-Key header (scripts, cron, curl)
        provided_key = request.headers.get('X-Admin-Key', '')
        expected_key = os.environ.get('ADMIN_API_KEY', '')
        if provided_key and expected_key and provided_key == expected_key:
            return f(*args, **kwargs)

        # Path 2: Session-based admin with 2FA verified
        email = session.get('email', '')
        if not email:
            try:
                if current_user.is_authenticated:
                    email = getattr(current_user, 'email', '')
            except Exception:
                pass

        # Not admin email at all → bounce
        if email != ADMIN_EMAIL:
            if _wants_html_response():
                flash('Admin access required.', 'danger')
                try:
                    return redirect(url_for('login'))
                except Exception:
                    return redirect('/')
            return jsonify({'error': 'admin_login_required'}), 403

        # Admin email present but 2FA flag missing → push through 2FA gate
        if not session.get('admin_2fa_verified'):
            if _wants_html_response():
                return redirect('/admin-panel')
            return jsonify({
                'error': '2fa_required',
                'message': 'Visit /admin-panel and complete 2FA before accessing this endpoint.',
            }), 401

        return f(*args, **kwargs)
    return decorated_function


# Alias for callers who want the explicit name. Same implementation.
admin_2fa_required = admin_required
