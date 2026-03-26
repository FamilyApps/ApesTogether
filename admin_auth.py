"""
Shared admin authentication decorator for all admin route files.

Usage:
    from admin_auth import admin_required
"""
import os
from functools import wraps
from flask import jsonify, session, redirect, url_for, flash
from flask_login import current_user

ADMIN_EMAIL = os.environ.get('ADMIN_EMAIL', 'admin@apestogether.ai')


def admin_required(f):
    """Decorator: requires the user to be logged in AND be the admin."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Check both Flask-Login and session-based auth
        email = session.get('email', '')
        if not email and current_user.is_authenticated:
            email = getattr(current_user, 'email', '')

        if email == ADMIN_EMAIL:
            return f(*args, **kwargs)

        # Not admin — return 403
        return jsonify({'error': 'Admin access required'}), 403
    return decorated_function
