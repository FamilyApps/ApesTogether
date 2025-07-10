"""
Admin Route Debug Script

This script adds a temporary debug route to check admin route registration
and user authentication status. It will be deployed to production to help
diagnose why the /admin routes aren't being found.
"""

import os
from flask import Blueprint, jsonify
from flask_login import current_user

# Create a debug blueprint that will be accessible without authentication
debug_bp = Blueprint('debug', __name__, url_prefix='/debug')

@debug_bp.route('/check_admin_routes')
def check_admin_routes():
    """Check if admin routes are properly registered and return diagnostic info"""
    from app import app
    
    # Get all registered routes
    routes = []
    for rule in app.url_map.iter_rules():
        routes.append({
            'endpoint': rule.endpoint,
            'methods': [m for m in rule.methods if m != 'OPTIONS' and m != 'HEAD'],
            'rule': str(rule)
        })
    
    # Filter for admin routes
    admin_routes = [r for r in routes if r['endpoint'].startswith('admin.')]
    
    # Get user authentication status
    user_info = None
    if current_user.is_authenticated:
        user_info = {
            'username': current_user.username,
            'email': current_user.email,
            'is_authenticated': current_user.is_authenticated
        }
    
    # Get environment variables (excluding sensitive ones)
    env_vars = {
        'FLASK_ENV': os.environ.get('FLASK_ENV'),
        'FLASK_DEBUG': os.environ.get('FLASK_DEBUG'),
        'APP_SETTINGS': os.environ.get('APP_SETTINGS'),
        'DATABASE_URL_EXISTS': os.environ.get('DATABASE_URL') is not None
    }
    
    # Check if admin blueprint is registered
    blueprints = [bp.name for bp in app.blueprints.values()]
    
    return jsonify({
        'admin_routes_found': len(admin_routes) > 0,
        'admin_routes': admin_routes,
        'blueprints_registered': blueprints,
        'user_info': user_info,
        'environment': env_vars
    })

# To use this script, add the following to app.py:
"""
# Register the debug blueprint (temporary)
try:
    from admin_route_debug import debug_bp
    app.register_blueprint(debug_bp)
    app.logger.info("Debug blueprint registered successfully")
except ImportError as e:
    app.logger.warning(f"Could not register debug blueprint: {str(e)}")
"""
