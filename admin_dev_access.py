"""
Development-only admin access script.
This provides a direct login route for admin access during local development.
DO NOT use this in production!
"""
import os
from flask import Blueprint, redirect, url_for, flash, session, current_app
from flask_login import login_user

# Create a Blueprint for the admin dev access
admin_dev_bp = Blueprint('admin_dev', __name__, url_prefix='/dev')

@admin_dev_bp.route('/admin-login')
def admin_login():
    """
    Development-only route to log in as admin without OAuth
    Only works if FLASK_ENV is set to development
    """
    if os.environ.get('FLASK_ENV') != 'development':
        flash('This route is only available in development mode', 'danger')
        return redirect(url_for('index'))
    
    # Get the User model and db from models
    from models import User, db
    
    # Find or create admin user
    admin_email = 'fordutilityapps@gmail.com'
    admin_user = User.query.filter_by(email=admin_email).first()
    
    if not admin_user:
        # Create admin user if it doesn't exist
        admin_user = User(
            username='Admin',
            email=admin_email,
            profile_picture='https://via.placeholder.com/150',
            subscription_active=True
        )
        db.session.add(admin_user)
        db.session.commit()
    
    # Log in as admin
    login_user(admin_user)
    session['user_info'] = {
        'name': 'Admin',
        'email': admin_email,
        'picture': 'https://via.placeholder.com/150'
    }
    
    flash('Logged in as admin for development', 'success')
    return redirect(url_for('admin.index'))
