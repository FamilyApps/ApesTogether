"""
Vercel serverless function handler for the Flask app.
This is a standalone version with admin access functionality.
"""
import os
import re
import json
import random
import logging
import traceback
import uuid
import time
# import stripe  # DISABLED (Feb 2026): Web payments disabled, mobile uses Apple IAP
import sys
import traceback
from datetime import datetime, timedelta, date
from functools import wraps
from dotenv import load_dotenv
from zoneinfo import ZoneInfo
from sqlalchemy import create_engine, Column, Integer, String, Float, ForeignKey, DateTime, Boolean, func, text, and_, or_, cast, Date
from sqlalchemy.pool import NullPool
from flask import Flask, render_template_string, render_template, redirect, url_for, request, session, flash, jsonify, send_from_directory, make_response
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_session import Session
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.middleware.proxy_fix import ProxyFix
from authlib.integrations.flask_client import OAuth
import secrets
import string
import requests

# Load environment variables
load_dotenv()

# Configure structured logging
log_level = os.environ.get('LOG_LEVEL', 'INFO').upper()
log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
logging.basicConfig(
    level=getattr(logging, log_level),
    format=log_format
)

# Create logger
logger = logging.getLogger('apestogether')

# Add handler for Vercel environment
if os.environ.get('VERCEL_ENV') == 'production':
    # In production, log to stderr which Vercel captures
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(log_format))
    logger.addHandler(handler)
    logger.info("Configured logging for Vercel production environment")
else:
    # In development, log to console
    logger.info("Configured logging for development environment")

# Admin credentials from environment variables
ADMIN_EMAIL = os.environ.get('ADMIN_EMAIL', 'admin@apestogether.ai')
ADMIN_USERNAME = os.environ.get('ADMIN_USERNAME', 'admin')

# =============================================================================
# TIMEZONE CONFIGURATION (Eastern Time for US Stock Market)
# =============================================================================
# Vercel runs in UTC, but we need Eastern Time for market operations
MARKET_TZ = ZoneInfo('America/New_York')

def get_market_time():
    """Get current time in Eastern Time (handles DST automatically)"""
    return datetime.now(MARKET_TZ)

def get_market_date():
    """Get current date in Eastern Time"""
    return get_market_time().date()

def generate_portfolio_slug():
    """Generate a URL-safe unique slug for portfolio sharing (11 chars, like nanoid)"""
    alphabet = string.ascii_letters + string.digits  # a-z, A-Z, 0-9
    return ''.join(secrets.choice(alphabet) for _ in range(11))

def is_market_hours(dt=None):
    """
    Check if current time (or provided datetime) is during market hours
    Market hours: Monday-Friday, 9:30 AM - 4:00 PM ET (excluding holidays)
    
    Args:
        dt: datetime object (with timezone). If None, uses current ET time.
    
    Returns:
        bool: True if during market hours
    """
    if dt is None:
        dt = get_market_time()
    
    # Ensure datetime is in ET
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=MARKET_TZ)
    elif dt.tzinfo != MARKET_TZ:
        dt = dt.astimezone(MARKET_TZ)
    
    # Check if weekend
    if dt.weekday() >= 5:  # Saturday=5, Sunday=6
        return False
    
    # Check if within market hours (9:30 AM - 4:00 PM ET)
    market_open = dt.replace(hour=9, minute=30, second=0, microsecond=0)
    market_close = dt.replace(hour=16, minute=0, second=0, microsecond=0)
    
    return market_open <= dt <= market_close

def is_market_holiday(check_date=None):
    """
    Check if a given date is a US market holiday (NYSE/NASDAQ closed)
    
    Args:
        check_date: date object to check. If None, uses current ET date.
    
    Returns:
        bool: True if market is closed for a holiday
    """
    if check_date is None:
        check_date = get_market_date()
    
    year = check_date.year
    month = check_date.month
    day = check_date.day
    
    # Fixed holidays
    holidays = [
        date(year, 1, 1),   # New Year's Day
        date(year, 7, 4),   # Independence Day
        date(year, 12, 25), # Christmas
    ]
    
    # NOTE: MLK Day is NOT a market holiday - NYSE/NASDAQ are open
    
    # Presidents Day - 3rd Monday in February
    feb_1 = date(year, 2, 1)
    presidents_day = feb_1 + timedelta(days=(7 - feb_1.weekday() + 14))  # 3rd Monday
    holidays.append(presidents_day)
    
    # Good Friday - Friday before Easter (complex calculation)
    # Simplified: Use a lookup table for common years
    good_fridays = {
        2024: date(2024, 3, 29),
        2025: date(2025, 4, 18),
        2026: date(2026, 4, 3),
        2027: date(2027, 3, 26),
        2028: date(2028, 4, 14),
    }
    if year in good_fridays:
        holidays.append(good_fridays[year])
    
    # Memorial Day - Last Monday in May
    may_31 = date(year, 5, 31)
    memorial_day = may_31 - timedelta(days=(may_31.weekday() + 7) % 7)
    holidays.append(memorial_day)
    
    # Juneteenth - June 19 (observed if weekend)
    juneteenth = date(year, 6, 19)
    if juneteenth.weekday() == 5:  # Saturday
        juneteenth = date(year, 6, 18)
    elif juneteenth.weekday() == 6:  # Sunday
        juneteenth = date(year, 6, 20)
    holidays.append(juneteenth)
    
    # Labor Day - 1st Monday in September
    sep_1 = date(year, 9, 1)
    labor_day = sep_1 + timedelta(days=(7 - sep_1.weekday()) % 7)
    holidays.append(labor_day)
    
    # Thanksgiving - 4th Thursday in November
    nov_1 = date(year, 11, 1)
    thanksgiving = nov_1 + timedelta(days=(3 - nov_1.weekday() + 21) % 7 + 21)
    holidays.append(thanksgiving)
    
    # NOTE: Columbus Day is NOT a market holiday - NYSE/NASDAQ are open
    
    # Observed holidays (if holiday falls on weekend, observe on Friday/Monday)
    for holiday in list(holidays):
        if holiday.weekday() == 5:  # Saturday -> observe Friday
            holidays.append(holiday - timedelta(days=1))
        elif holiday.weekday() == 6:  # Sunday -> observe Monday
            holidays.append(holiday + timedelta(days=1))
    
    return check_date in holidays

def verify_cron_request(secret_env_var='CRON_SECRET'):
    """Verify that a cron request is authorized.
    
    Vercel crons send GET requests with Authorization: Bearer <CRON_SECRET>.
    Also accepts POST with Authorization or X-Cron-Secret headers.
    
    Returns None if authorized, or a (jsonify response, status_code) tuple if not.
    """
    expected_token = os.environ.get(secret_env_var)
    if not expected_token:
        logger.error(f"{secret_env_var} not configured")
        return jsonify({'error': 'Server configuration error'}), 500
    
    auth_header = request.headers.get('Authorization', '')
    cron_secret = request.headers.get('X-Cron-Secret', '')
    
    is_bearer = auth_header.startswith('Bearer ') and auth_header[7:] == expected_token
    is_cron_header = cron_secret and cron_secret == expected_token
    is_vercel_cron = request.headers.get('x-vercel-cron') == '1'
    
    if is_bearer or is_cron_header or is_vercel_cron:
        return None  # Authorized
    
    logger.warning(f"Unauthorized {request.method} cron attempt on {request.path}")
    return jsonify({'error': 'Unauthorized'}), 401

# =============================================================================

# Initialize Flask app
# Use absolute paths for templates and static files in production
import shutil

# Helper function to add common template variables
def render_template_with_defaults(*args, **kwargs):
    """Wrapper for render_template that adds common variables"""
    # Add the current date/time for use in templates (e.g., copyright year)
    if 'now' not in kwargs:
        kwargs['now'] = datetime.now()
    return render_template(*args, **kwargs)

# Create a Flask app with the appropriate template and static folders
if os.environ.get('VERCEL_ENV') == 'production':
    # For Vercel production environment
    app = Flask(__name__)
    
    # Set absolute paths for templates and static files
    app.template_folder = '/var/task/templates'
    app.static_folder = '/var/task/static'
    
    # Ensure the directories exist
    os.makedirs(app.template_folder, exist_ok=True)
    os.makedirs(app.static_folder, exist_ok=True)
    
    # Copy templates if needed
    source_templates = '/var/task/templates'
    if not os.path.exists(os.path.join(source_templates, 'index.html')):
        try:
            # Try different source paths
            potential_sources = [
                '/var/task/api/../templates',
                '/var/task/templates',
                os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'templates')
            ]
            
            for src_path in potential_sources:
                if os.path.exists(src_path) and os.path.isdir(src_path):
                    print(f"Found templates at: {src_path}")
                    for item in os.listdir(src_path):
                        src = os.path.join(src_path, item)
                        dst = os.path.join(app.template_folder, item)
                        if os.path.isdir(src):
                            shutil.copytree(src, dst, dirs_exist_ok=True)
                        else:
                            shutil.copy2(src, dst)
                    print(f"Templates copied from {src_path} to {app.template_folder}")
                    break
        except Exception as e:
            print(f"Error copying templates: {str(e)}")
    
    # Copy static files if needed
    if not os.listdir(app.static_folder):
        try:
            # Try different source paths
            potential_sources = [
                '/var/task/api/../static',
                '/var/task/static',
                os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'static')
            ]
            
            for src_path in potential_sources:
                if os.path.exists(src_path) and os.path.isdir(src_path):
                    print(f"Found static files at: {src_path}")
                    for item in os.listdir(src_path):
                        src = os.path.join(src_path, item)
                        dst = os.path.join(app.static_folder, item)
                        if os.path.isdir(src):
                            shutil.copytree(src, dst, dirs_exist_ok=True)
                        else:
                            shutil.copy2(src, dst)
                    print(f"Static files copied from {src_path} to {app.static_folder}")
                    break
        except Exception as e:
            print(f"Error copying static files: {str(e)}")
    
    print(f"Final template folder: {app.template_folder}")
    print(f"Final static folder: {app.static_folder}")
else:
    # For local development
    app = Flask(__name__, template_folder='../templates', static_folder='../static')

app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1)

# Enable jinja2 template features in render_template_string
app.jinja_env.globals.update({
    'len': len,
    'format': format
})

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Get Vercel environment information
VERCEL_ENV = os.environ.get('VERCEL_ENV', 'development')
VERCEL_REGION = os.environ.get('VERCEL_REGION', 'local')
VERCEL_URL = os.environ.get('VERCEL_URL', 'localhost')

# Login required decorator
# Use Flask-Login's login_required decorator instead of our custom one
# This is kept for backward compatibility with existing code
def custom_login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash('Please log in to access this page', 'danger')
            return redirect(url_for('login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function

# For backward compatibility, keep the original name
login_required = custom_login_required

# Admin decorators: imported from the shared admin_auth module, which (as of
# 2026-05-12) enforces admin email + 2FA flag, or accepts X-Admin-Key for
# scripts. Previously this file defined two separate local versions that only
# checked the email — a stolen-credentials risk. The shared decorator closes
# that gap. `admin_2fa_required` remains as an alias for explicitness.
from admin_auth import admin_required, admin_2fa_required

# Get environment variables with fallbacks
# Check for DATABASE_URL first, then fall back to POSTGRES_PRISMA_URL if available
DATABASE_URL = os.environ.get('DATABASE_URL') or os.environ.get('POSTGRES_PRISMA_URL')
VERCEL_ENV = os.environ.get('VERCEL_ENV')

# SECRET_KEY: required in production — no hardcoded fallback
SECRET_KEY = os.environ.get('SECRET_KEY')
if not SECRET_KEY:
    if VERCEL_ENV:
        raise RuntimeError("SECRET_KEY environment variable is required in production")
    SECRET_KEY = 'dev-key-for-local-testing-only'
    logger.warning("SECRET_KEY not set — using insecure default (local dev only)")

# Log environment information
logger.info(f"Starting app with VERCEL_ENV: {VERCEL_ENV}")
logger.info(f"DATABASE_URL present: {'Yes' if DATABASE_URL else 'No'}")
logger.info(f"POSTGRES_PRISMA_URL present: {'Yes' if os.environ.get('POSTGRES_PRISMA_URL') else 'No'}")
logger.info(f"SECRET_KEY present: {'Yes' if SECRET_KEY else 'No'}")

# Configure database with error handling
try:
    # Configure database
    DATABASE_URL = os.environ.get('DATABASE_URL', os.environ.get('POSTGRES_PRISMA_URL'))
    if not DATABASE_URL:
        logger.error("No database URL provided - using SQLite fallback")
        DATABASE_URL = 'sqlite:///portfolio.db'
    elif DATABASE_URL.startswith('postgres://'):
        # Heroku-style postgres:// URL needs to be converted for SQLAlchemy
        DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql://', 1)
    
    # Ensure sslmode is set for Supabase
    if 'postgresql' in DATABASE_URL and 'sslmode' not in DATABASE_URL:
        separator = '&' if '?' in DATABASE_URL else '?'
        DATABASE_URL += f'{separator}sslmode=require'
    
    # Log connection info (redact password but show enough to debug $ interpolation)
    try:
        from urllib.parse import urlparse
        parsed = urlparse(DATABASE_URL)
        # Show first 3 + last 2 chars of password to detect shell interpolation of $
        pw = parsed.password or ''
        pw_hint = f"{pw[:3]}...{pw[-2:]}" if len(pw) > 5 else '***'
        logger.info(f"DB connection: host={parsed.hostname}, port={parsed.port}, user={parsed.username}, pw_hint={pw_hint}, db={parsed.path}")
        logger.info(f"DB URL query params: {parsed.query}")
    except Exception as log_err:
        logger.warning(f"Could not parse DB URL for logging: {log_err}")
    logger.info(f"Using database type: {DATABASE_URL.split('://')[0]}")

    # Configure Flask app
    app.config['SECRET_KEY'] = SECRET_KEY
    app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['MAX_CONTENT_LENGTH'] = 1 * 1024 * 1024  # 1 MB max request body
    # Serverless-friendly SQLAlchemy engine options
    # NullPool: no connection pooling — each DB operation gets a fresh connection
    # and returns it immediately. This is the ONLY safe option for Vercel serverless
    # because QueuePool causes pool exhaustion (connections aren't returned between
    # Lambda invocations that share the same module-level state).
    # SSL drops from PgBouncer are handled by the db_retry() wrapper instead.
    app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
        'poolclass': NullPool,
        'pool_pre_ping': True,  # Validate connections before use — catches dead SSL sockets
        'connect_args': {
            'connect_timeout': 5,
            'keepalives': 1,
            'keepalives_idle': 5,
            'keepalives_interval': 2,
            'keepalives_count': 3,
            'options': '-c statement_timeout=15000',  # 15s — queries on broken connections fail fast
        },
    }
    
    # Session config — using Flask's built-in signed cookie sessions (no Flask-Session)
    app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=7)
    app.config['SESSION_COOKIE_SECURE'] = True
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

    # Cap request body size (audit S-5): reject oversized/garbage payloads before
    # they reach handlers. These JSON APIs never legitimately need >1 MB.
    app.config['MAX_CONTENT_LENGTH'] = 1 * 1024 * 1024  # 1 MB
    
    # Debug logging for session configuration
    logger.info(f"Session configuration: TYPE={app.config.get('SESSION_TYPE')}, LIFETIME={app.config.get('PERMANENT_SESSION_LIFETIME')}")
    logger.info(f"Database URL for sessions: [REDACTED]")

    # Initialize rate limiter (in-memory for serverless; upgrade to Redis when >1K users)
    try:
        from flask_limiter import Limiter
        from flask_limiter.util import get_remote_address
        
        limiter = Limiter(
            app=app,
            key_func=get_remote_address,
            default_limits=["200 per day", "50 per hour"],
            storage_uri="memory://",
        )
        app.limiter = limiter  # Store on app so blueprints can access it
        logger.info("Rate limiter initialized (in-memory)")
    except Exception as limiter_err:
        logger.warning(f"Rate limiter not available: {limiter_err}")
        # No-op limiter so @limiter.limit() decorators don't crash
        class _NoOpLimiter:
            def limit(self, *a, **kw):
                def decorator(f):
                    return f
                return decorator
        limiter = _NoOpLimiter()
        app.limiter = None

    # Initialize Flask-Login
    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = 'login'

    # Track whether the previous request on this Vercel instance had a DB error.
    # If so, we need to dispose the engine (not just remove session) to get a
    # truly fresh TCP connection, since PgBouncer may have blacklisted our socket.
    app._last_request_had_db_error = False
    
    # Add a before_request handler to ensure session and current_user are properly initialized
    @app.before_request
    def handle_before_request():
        # Skip session processing for static files and favicon
        if request.path.startswith('/static/') or request.path == '/favicon.png':
            return  # Skip session processing for static files
        
        # CRITICAL: Remove any leftover DB session from previous requests.
        # On Vercel serverless, the module persists between requests but the
        # underlying DB connection may be dead (PgBouncer closed it).
        # This ensures every request starts with a completely fresh session.
        try:
            db.session.remove()
        except Exception:
            pass
        
        # If previous request had a DB error, dispose engine for a fresh TCP connection
        if getattr(app, '_last_request_had_db_error', False):
            logger.info("[before_request] Previous request had DB error — disposing engine for fresh connection")
            try:
                db.engine.dispose()
            except Exception:
                pass
            app._last_request_had_db_error = False
        
        try:
            session.permanent = True
            
            if '_user_id' in session and not hasattr(current_user, 'is_authenticated'):
                user_id = session.get('_user_id')
                if user_id:
                    user = load_user(user_id)
                    if user:
                        login_user(user)
                        logger.info(f"User {user_id} loaded from session")
            
            if current_user.is_authenticated:
                session['user_id'] = current_user.id
                session['email'] = getattr(current_user, 'email', None)
                session['username'] = getattr(current_user, 'username', None)
                session.modified = True  # Refresh the session to keep it alive
        except Exception as e:
            # Log but don't fail the request
            logger.error(f"Error in before_request handler: {str(e)}")
            logger.error(traceback.format_exc())
        
        
        # Add request logging for debugging (moved from separate handler)
        if request.path.startswith('/api/portfolio/'):
            logger.info(f"REQUEST: {request.method} {request.path}")
            logger.info(f"User-Agent: {request.headers.get('User-Agent', 'Unknown')}")

    @login_manager.user_loader
    def load_user(user_id):
        try:
            return db_retry(lambda: User.query.get(int(user_id)))
        except Exception as e:
            logger.error(f"Error loading user: {str(e)}")
            try:
                db.session.rollback()
                db.session.remove()
            except Exception:
                pass
            return None

    # DISABLED (Feb 2026): Web payments disabled, mobile uses Apple IAP
    # app.config['STRIPE_PUBLIC_KEY'] = os.environ.get('STRIPE_PUBLIC_KEY')
    # app.config['STRIPE_SECRET_KEY'] = os.environ.get('STRIPE_SECRET_KEY')
    # app.config['STRIPE_WEBHOOK_SECRET'] = os.environ.get('STRIPE_WEBHOOK_SECRET')
    # stripe.api_key = app.config['STRIPE_SECRET_KEY']

    # Initialize OAuth
    oauth = OAuth(app)

    # Configure OAuth providers
    google = oauth.register(
        name='google',
        client_id=os.environ.get('GOOGLE_CLIENT_ID', 'google-client-id'),
        client_secret=os.environ.get('GOOGLE_CLIENT_SECRET', 'google-client-secret'),
        server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
        client_kwargs={
            'scope': 'openid email profile'
        }
    )

    apple = oauth.register(
        name='apple',
        client_id=os.environ.get('APPLE_CLIENT_ID', 'apple-client-id'),
        client_secret=os.environ.get('APPLE_CLIENT_SECRET', 'apple-client-secret'),
        access_token_url='https://appleid.apple.com/auth/token',
        access_token_params=None,
        authorize_url='https://appleid.apple.com/auth/authorize',
        authorize_params=None,
        api_base_url='https://appleid.apple.com/',
        client_kwargs={'scope': 'name email'},
    )

    # Initialize SQLAlchemy
    db = SQLAlchemy(app)
    migrate = Migrate(app, db)
    
    # Global engine event: on any disconnect error, invalidate the connection
    # so SQLAlchemy doesn't try to reuse a broken TCP socket
    from sqlalchemy import event
    @event.listens_for(db.engine, "handle_error")
    def handle_db_error(context):
        """Invalidate connections on SSL/connection errors so next query gets a fresh one."""
        if context.original_exception:
            err_str = str(context.original_exception).lower()
            if any(phrase in err_str for phrase in [
                'ssl connection has been closed',
                'connection has been closed',
                'server closed the connection',
                'closed the connection unexpectedly',
                'connection timed out',
                'could not connect',
            ]):
                context.invalidate_pool_on_disconnect = True
                app._last_request_had_db_error = True
                logger.warning(f"DB disconnect detected, invalidating connection: {context.original_exception}")
    
    # Retry helper for DB operations that may fail due to PgBouncer SSL drops
    def _nuke_session():
        """Nuclear session cleanup — destroy every trace of the current session/connection."""
        # 1. Try to rollback the session-level transaction
        try:
            db.session.rollback()
        except Exception:
            pass
        # 2. Close the session (releases underlying connection)
        try:
            db.session.close()
        except Exception:
            pass
        # 3. Remove from scoped session registry
        try:
            db.session.remove()
        except Exception:
            pass
        # 4. Clear the scoped session registry directly — this is the nuclear option
        #    that ensures no stale session/connection references survive
        try:
            if hasattr(db.session, 'registry'):
                db.session.registry.clear()
        except Exception:
            pass
        # 5. Dispose engine (closes all engine-level connections)
        try:
            db.engine.dispose()
        except Exception:
            pass

    def db_retry(fn, max_retries=2):
        """Execute fn(), retrying on SSL/connection errors with fresh DB session."""
        last_error = None
        for attempt in range(max_retries + 1):
            # Ensure clean session at the START of every retry (not first attempt)
            if attempt > 0:
                _nuke_session()
                import time as _time
                _time.sleep(1)
            try:
                return fn()
            except Exception as e:
                last_error = e
                err_str = str(e).lower()
                is_connection_error = (
                    'ssl connection has been closed' in err_str or
                    'connection has been closed' in err_str or
                    'invalid transaction' in err_str or
                    'could not connect' in err_str or
                    'connection refused' in err_str or
                    'server closed the connection' in err_str or
                    'closed the connection unexpectedly' in err_str or
                    'connection timed out' in err_str or
                    'pending rollback' in err_str or
                    "can't reconnect" in err_str
                )
                if is_connection_error:
                    app._last_request_had_db_error = True
                    # Nuke immediately after error too, don't wait for next iteration top
                    _nuke_session()
                if is_connection_error and attempt < max_retries:
                    logger.warning(f"DB connection error (attempt {attempt+1}/{max_retries+1}): {e}")
                    continue
                raise last_error
    
    # Store on app so blueprints and decorators can access them
    app._nuke_session = _nuke_session
    app.db_retry = db_retry
    
    # Use Flask's built-in signed cookie sessions (SecureCookieSession).
    # This stores session data client-side in a signed cookie — zero DB dependency.
    # Much more resilient on serverless than DB-backed sessions: no stale connections,
    # no schema issues, works across all Vercel instances automatically.
    # OAuth state/nonce fits fine in a cookie (< 4KB).
    # Flask-Session is NOT used — just Flask's default session mechanism.
    logger.info("Using Flask built-in signed cookie sessions (no DB dependency)")
    
    # IMPORTANT: Do NOT run any DB queries at startup (module load time).
    # On Vercel serverless, the cold-start DB connection may fail (SSL drops,
    # IPv4/IPv6 mismatch, etc.) and poison the SQLAlchemy session, causing
    # ALL subsequent requests to fail with "invalid transaction" errors.
    # Tables like pending_trade should be created via Supabase SQL Editor.
    
    # Teardown: ensure every request gets a clean DB session
    @app.teardown_appcontext
    def shutdown_session(exception=None):
        try:
            if exception:
                db.session.rollback()
            db.session.remove()
        except Exception:
            pass

    logger.info("Database and migrations initialized successfully")
except Exception as e:
    logger.error(f"Failed to initialize database: {str(e)}")
    # Continue without database to allow basic functionality

# Define database models
class User(db.Model, UserMixin):
    __tablename__ = 'user'  # Explicitly set for PostgreSQL compatibility
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    stripe_customer_id = db.Column(db.String(120), nullable=True)
    oauth_provider = db.Column(db.String(20), nullable=True)
    oauth_id = db.Column(db.String(100), nullable=True)
    stripe_price_id = db.Column(db.String(255), nullable=True)
    subscription_price = db.Column(db.Float, nullable=True)
    
    # Cash tracking
    max_cash_deployed = db.Column(db.Float, default=0.0, nullable=False)
    cash_proceeds = db.Column(db.Float, default=0.0, nullable=False)
    
    # Portfolio sharing & GDPR
    portfolio_slug = db.Column(db.String(20), unique=True, nullable=True)
    deleted_at = db.Column(db.DateTime, nullable=True)
    
    # SMS/Email trading and notifications
    phone_number = db.Column(db.String(20), nullable=True)  # E.164 format: +12125551234
    default_notification_method = db.Column(db.String(10), default='email')  # 'email', 'sms', or 'both'
    
    stocks = db.relationship('Stock', backref='user', lazy=True)
    transactions = db.relationship('Transaction', backref='user', lazy=True)
    # We'll use subscriptions_made and subscribers relationships defined in the Subscription model
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
        
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
        
    @property
    def is_admin(self):
        return self.email == ADMIN_EMAIL or self.username == ADMIN_USERNAME

    def __repr__(self):
        return f'<User {self.username}>'

class Stock(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    ticker = db.Column(db.String(10), nullable=False)
    quantity = db.Column(db.Float, nullable=False)
    purchase_price = db.Column(db.Float, nullable=False)
    purchase_date = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<Stock {self.ticker}>'
        
    def current_value(self):
        # Get real stock data from Alpha Vantage
        stock_data = get_stock_data(self.ticker)
        current_price = stock_data.get('price', self.purchase_price)
        return current_price * self.quantity
        
    def profit_loss(self):
        return self.current_value() - (self.purchase_price * self.quantity)

class Transaction(db.Model):
    __tablename__ = 'stock_transaction'  # Use same table name as models.py to avoid conflicts
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    ticker = db.Column(db.String(10), nullable=False)
    quantity = db.Column(db.Float, nullable=False)
    price = db.Column(db.Float, nullable=False)
    transaction_type = db.Column(db.String(4), nullable=False)  # 'buy' or 'sell'
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<Transaction {self.transaction_type} {self.ticker}>'

class Subscription(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    subscriber_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    subscribed_to_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    stripe_subscription_id = db.Column(db.String(255), unique=True, nullable=False)
    status = db.Column(db.String(20), nullable=False, default='active')  # 'active', 'canceled', etc.
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    start_date = db.Column(db.DateTime, default=datetime.utcnow)
    end_date = db.Column(db.DateTime, nullable=True)
    
    # Define relationships to get User objects with explicit foreign keys
    # backref creates a 'subscriptions_made' collection on the User model (for the subscriber)
    subscriber = db.relationship(
        'User', 
        foreign_keys=[subscriber_id], 
        backref=db.backref('subscriptions_made', lazy=True),
        lazy=True
    )
    
    # backref creates a 'subscribers' collection on the User model (for the user being subscribed to)
    subscribed_to = db.relationship(
        'User', 
        foreign_keys=[subscribed_to_id], 
        backref=db.backref('subscribers', lazy=True),
        lazy=True
    )

    def __repr__(self):
        return f'<Subscription {self.subscriber_id} to {self.subscribed_to_id} - {self.status}>'

class UserPortfolioChartCache(db.Model):
    """Pre-generated portfolio charts for leaderboard users only"""
    __tablename__ = 'user_portfolio_chart_cache'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    period = db.Column(db.String(10), nullable=False)  # '1D', '5D', '3M', 'YTD', '1Y', '5Y', 'MAX'
    chart_data = db.Column(db.Text, nullable=False)  # JSON string of chart data
    generated_at = db.Column(db.DateTime, nullable=False)
    
    # Ensure one cache entry per user per period
    __table_args__ = (db.UniqueConstraint('user_id', 'period', name='unique_user_period_chart'),)
    
    def __repr__(self):
        return f"<UserPortfolioChartCache user_id={self.user_id} {self.period} generated at {self.generated_at}>"

# Secret key is already set in app.config

# Check if we're running on Vercel
VERCEL_ENV = os.environ.get('VERCEL_ENV')
if VERCEL_ENV:
    print(f"Running in Vercel environment: {VERCEL_ENV}")

# Admin email for authentication - using environment variables defined above

# Flash message categories
app.config['MESSAGE_CATEGORIES'] = ['success', 'info', 'warning', 'danger']

# Admin decorators (`admin_required` and `admin_2fa_required`) are now imported
# from the shared `admin_auth` module near the top of this file (~line 334).
# The previous local versions in this spot did not enforce the 2FA flag, which
# was a stolen-credentials security risk — closed 2026-05-12.

# Simple HTML template for the home page
HOME_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>ApesTogether</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 40px; }
        .container { max-width: 800px; margin: 0 auto; }
        .info { margin-top: 20px; background: #f5f5f5; padding: 15px; border-radius: 5px; }
        .button { 
            display: inline-block; 
            background: #4CAF50; 
            color: white; 
            padding: 10px 20px; 
            text-decoration: none; 
            border-radius: 5px; 
            margin-top: 20px;
        }
        .button-secondary {
            background: #2196F3;
        }
        .nav {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 20px;
        }
        .nav-links a {
            margin-left: 15px;
            text-decoration: none;
            color: #333;
        }
        .hero {
            background: #f9f9f9;
            padding: 40px;
            border-radius: 5px;
            text-align: center;
            margin-bottom: 30px;
        }
        .features {
            display: flex;
            justify-content: space-between;
            flex-wrap: wrap;
            margin-bottom: 30px;
        }
        .feature {
            flex-basis: 30%;
            background: #f9f9f9;
            padding: 20px;
            border-radius: 5px;
            margin-bottom: 20px;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="nav">
            <h2>ApesTogether</h2>
            <div class="nav-links">
                <a href="/">Home</a>
                <a href="/login">Login</a>
                <a href="/register">Register</a>
                <a href="/admin">Admin</a>
            </div>
        </div>
        
        <div class="hero">
            <h1>ApesTogether Stock Portfolio App</h1>
            <p>Track, manage, and optimize your stock investments in one place</p>
            <a href="/register" class="button">Get Started</a>
            <a href="/login" class="button button-secondary">Login</a>
        </div>
        
        <div class="features">
            <div class="feature">
                <h3>Portfolio Tracking</h3>
                <p>Keep track of all your stock investments in one place</p>
            </div>
            <div class="feature">
                <h3>Performance Analysis</h3>
                <p>Analyze your portfolio performance over time</p>
            </div>
            <div class="feature">
                <h3>Stock Comparison</h3>
                <p>Compare different stocks to make better investment decisions</p>
            </div>
        </div>
        
        <div class="info">
            <h2>Admin Access</h2>
            <p>If you are an admin user, you can access the admin panel here:</p>
            <a href="/admin" class="button">Admin Access</a>
        </div>
        
        <div class="info">
            <h2>Environment Info:</h2>
            <p><strong>Time:</strong> {{ current_time }}</p>
            <p><strong>Environment:</strong> {{ environment }}</p>
        </div>
    </div>
</body>
</html>
"""

# Add diagnostic route for troubleshooting
# Subscription and Payment Routes

# ──────────────────────────────────────────────────────────────
# DISABLED (Feb 2026): Stripe web payment routes disabled.
# Mobile subscriptions use Apple IAP / Google Play Billing.
# Web app is now a landing page directing users to the app stores.
# To re-enable, uncomment the stripe import, config block above,
# and restore these route bodies.
# ──────────────────────────────────────────────────────────────

@app.route('/create-checkout-session/<int:user_id>')
@login_required
def create_checkout_session(user_id):
    """DISABLED: Stripe checkout - web payments disabled Feb 2026"""
    flash('Subscriptions are now handled through the mobile app.', 'info')
    return redirect(url_for('index'))

@app.route('/create-payment-intent', methods=['POST'])
@login_required
def create_payment_intent():
    """DISABLED: Stripe payment intent - web payments disabled Feb 2026"""
    return jsonify({'error': 'Web payments disabled. Please use the mobile app.'}), 410

@app.route('/payment-confirmation')
@login_required
def payment_confirmation():
    """DISABLED: Stripe payment confirmation - web payments disabled Feb 2026"""
    flash('Subscriptions are now handled through the mobile app.', 'info')
    return redirect(url_for('index'))

@app.route('/subscription-success')
@login_required
def subscription_success():
    """DISABLED: Stripe subscription success - web payments disabled Feb 2026"""
    flash('Subscriptions are now handled through the mobile app.', 'info')
    return redirect(url_for('index'))

@app.route('/webhook', methods=['POST'])
def webhook():
    """DISABLED: Stripe webhook - web payments disabled Feb 2026"""
    return jsonify({'status': 'disabled', 'message': 'Stripe webhooks disabled'}), 410

@app.route('/subscriptions')
@login_required
def subscriptions():
    """Display a user's active and canceled subscriptions"""
    try:
        # Verify user is authenticated - this should be redundant with @login_required
        # but we're being extra cautious in the serverless environment
        if not current_user.is_authenticated:
            logger.warning("User not authenticated despite @login_required decorator")
            flash('Please log in to access your subscriptions.', 'warning')
            return redirect(url_for('login'))
            
        # For backward compatibility, ensure session is in sync with Flask-Login
        # and refresh the session to keep it alive in the serverless environment
        if session.get('user_id') != current_user.id:
            session['user_id'] = current_user.id
            session['email'] = current_user.email
            session['username'] = current_user.username
            session.modified = True
            
        # Log successful access for debugging
        logger.info(f"Subscriptions accessed by user: {current_user.username} (ID: {current_user.id})")
            
        current_user_id = current_user.id
        
        # Get active and cancelled (but not expired) subscriptions
        try:
            from models import Subscription
            from datetime import datetime, timedelta
            
            # Get all active subscriptions
            active_subs = Subscription.query.filter_by(
                subscriber_id=current_user_id,
                status='active'
            ).all()
            
            # Get cancelled subscriptions that haven't expired yet
            cancelled_subs = Subscription.query.filter(
                Subscription.subscriber_id == current_user_id,
                Subscription.status == 'cancelled',
                (Subscription.end_date.is_(None) | (Subscription.end_date > datetime.utcnow()))
            ).all()
            
            # Combine active and cancelled (still have access) as "active_subscriptions"
            all_active_subs = active_subs + cancelled_subs
            
            # Clean up expired cancelled subscriptions
            expired_subs = Subscription.query.filter(
                Subscription.subscriber_id == current_user_id,
                Subscription.status == 'cancelled',
                Subscription.end_date <= datetime.utcnow()
            ).all()
            for sub in expired_subs:
                db.session.delete(sub)
            if expired_subs:
                db.session.commit()
            
            # Get truly canceled (past) subscriptions for history
            past_subs = Subscription.query.filter(
                Subscription.subscriber_id == current_user_id,
                Subscription.status.in_(['canceled', 'expired'])
            ).all()
            
            return render_template_with_defaults(
                'subscriptions.html',
                active_subscriptions=all_active_subs,
                canceled_subscriptions=past_subs,
                current_user=current_user
            )
        except Exception as e:
            logger.error(f"Error querying subscriptions: {str(e)}")
            logger.error(traceback.format_exc())
            flash('An error occurred while loading your subscriptions. Please try again.', 'warning')
            return render_template_with_defaults(
                'subscriptions.html',
                active_subscriptions=[],
                canceled_subscriptions=[],
                current_user=current_user
            )
    except Exception as e:
        logger.error(f"Error in subscriptions route: {str(e)}")
        logger.error(traceback.format_exc())
        flash('An error occurred while loading your subscriptions. Please try again.', 'danger')
        return redirect(url_for('index'))
    

@app.route('/cancel-subscription', methods=['POST'])
@login_required
def cancel_subscription():
    """DISABLED: Stripe cancel subscription - web payments disabled Feb 2026"""
    flash('Subscription management is now handled through the mobile app.', 'info')
    return redirect(url_for('index'))

@app.route('/resubscribe', methods=['POST'])
@login_required
def resubscribe():
    """DISABLED: Stripe resubscribe - web payments disabled Feb 2026"""
    flash('Subscriptions are now handled through the mobile app.', 'info')
    return redirect(url_for('index'))

@app.route('/explore')
@login_required
def explore():
    """Display a list of all other users to subscribe to."""
    current_user_id = session.get('user_id')
    users = User.query.filter(User.id != current_user_id).order_by(User.username).all()
    return render_template_with_defaults('explore.html', users=users)

@app.route('/onboarding')
@login_required
def onboarding():
    """User onboarding page"""
    return render_template_with_defaults('onboarding.html')

@app.route('/dashboard')
@login_required
def dashboard():
    """Display the user's dashboard."""
    import time
    start_time = time.time()
    logger.info(f"⏱️ Dashboard load started for user {current_user.id}")
    
    # Log dashboard view activity
    try:
        from models import UserActivity
        activity = UserActivity(
            user_id=current_user.id,
            activity_type='view_dashboard',
            ip_address=request.remote_addr,
            user_agent=request.headers.get('User-Agent', '')[:255]
        )
        db.session.add(activity)
        db.session.commit()
        db.session.flush()  # Ensure record is immediately visible
        logger.info(f"Successfully logged dashboard activity for user {current_user.id}")
    except Exception as e:
        logger.error(f"Error logging dashboard activity: {str(e)}")
        logger.error(traceback.format_exc())
        db.session.rollback()
    
    # Get user's portfolio
    portfolio_data = []
    total_portfolio_value = 0
    
    if current_user.is_authenticated:
        from datetime import date, datetime, timedelta
        from models import PortfolioSnapshot
        from models import PortfolioSnapshotIntraday
        
        # Check if it's weekend or after market hours
        today = get_market_date()  # FIX: Use ET not UTC
        is_weekend = today.weekday() >= 5  # Saturday = 5, Sunday = 6
        current_hour = get_market_time().hour  # FIX: Use ET not UTC
        is_after_hours = current_hour < 9 or current_hour >= 16  # Before 9 AM or after 4 PM
        
        # SMART CACHING STRATEGY: Use cached data by default, refresh only when requested during market hours
        force_refresh = request.args.get('refresh') == 'true'
        is_market_hours_weekday = not is_weekend and not is_after_hours
        use_cached_data = not (is_market_hours_weekday and force_refresh)
        
        # Always try cached data first (fastest loading)
        from models import PortfolioSnapshotIntraday
        
        # Get most recent data from either intraday or daily snapshots
        latest_daily_snapshot = PortfolioSnapshot.query.filter_by(user_id=current_user.id)\
            .order_by(PortfolioSnapshot.date.desc()).first()
        
        latest_intraday_snapshot = PortfolioSnapshotIntraday.query.filter_by(user_id=current_user.id)\
            .order_by(PortfolioSnapshotIntraday.timestamp.desc()).first()
        
        # Determine which snapshot is more recent
        use_intraday = False
        latest_snapshot = latest_daily_snapshot
        
        if latest_intraday_snapshot and latest_daily_snapshot:
            # Compare intraday timestamp with daily date
            intraday_date = latest_intraday_snapshot.timestamp.date()
            daily_date = latest_daily_snapshot.date
            
            if intraday_date >= daily_date:
                use_intraday = True
                latest_snapshot = latest_intraday_snapshot
        elif latest_intraday_snapshot:
            use_intraday = True
            latest_snapshot = latest_intraday_snapshot
        
        if use_cached_data and latest_snapshot:
            # Use cached data (fast loading)
            if use_intraday:
                total_portfolio_value = latest_snapshot.total_value
                data_timestamp = latest_snapshot.timestamp
                data_source = f"Intraday snapshot from {data_timestamp.strftime('%H:%M')}"
            else:
                total_portfolio_value = latest_snapshot.total_value
                data_timestamp = datetime.combine(latest_snapshot.date, datetime.min.time())
                data_source = f"Market close from {latest_snapshot.date.strftime('%m/%d/%Y')}"
            
            # Get individual stock data for display
            stocks = Stock.query.filter_by(user_id=current_user.id).all()
            
            # Calculate individual stock values proportionally
            total_cost_basis = sum(stock.quantity * stock.purchase_price for stock in stocks if stock.purchase_price)
            
            for stock in stocks:
                if total_cost_basis > 0:
                    # Estimate current price based on proportional portfolio performance
                    cost_basis = stock.quantity * stock.purchase_price if stock.purchase_price else 0
                    portfolio_multiplier = total_portfolio_value / total_cost_basis if total_cost_basis > 0 else 1
                    estimated_current_price = stock.purchase_price * portfolio_multiplier if stock.purchase_price else 0
                    
                    value = stock.quantity * estimated_current_price
                    gain_loss = value - cost_basis
                    gain_loss_percent = (gain_loss / cost_basis) * 100 if cost_basis > 0 else 0
                    
                    portfolio_data.append({
                        'ticker': stock.ticker,
                        'quantity': stock.quantity,
                        'purchase_price': stock.purchase_price,
                        'current_price': estimated_current_price,
                        'value': value,
                        'gain_loss': gain_loss,
                        'gain_loss_percent': gain_loss_percent
                    })
                else:
                    portfolio_data.append({
                        'ticker': stock.ticker,
                        'quantity': stock.quantity,
                        'purchase_price': stock.purchase_price,
                        'current_price': 'N/A',
                        'value': 'N/A',
                        'gain_loss': 'N/A',
                        'gain_loss_percent': 'N/A'
                    })
            
            # Smart refresh logic: Only make API calls if user requests refresh AND data is stale
            if force_refresh and is_market_hours_weekday:
                current_time = datetime.now()
                data_age_seconds = (current_time - data_timestamp).total_seconds()
                
                if data_age_seconds > 90:  # Data is stale, refresh with API calls
                    # Clear cached data and fall through to API refresh
                    portfolio_data = []
                    total_portfolio_value = 0
                    use_cached_data = False
                # If data is fresh (<90s), keep using cached data even though user clicked refresh
        
        if not use_cached_data:
            # Use live API data during market hours on weekdays
            stocks = Stock.query.filter_by(user_id=current_user.id).all()
            
            # Get all tickers for batch processing
            tickers = [stock.ticker for stock in stocks]
            batch_prices = get_batch_stock_data(tickers)
            
            for stock in stocks:
                ticker_upper = stock.ticker.upper()
                current_price = batch_prices.get(ticker_upper)
                
                if current_price is not None:
                    value = stock.quantity * current_price
                    gain_loss = value - (stock.quantity * stock.purchase_price)
                    gain_loss_percent = (gain_loss / (stock.quantity * stock.purchase_price)) * 100 if stock.purchase_price else 0
                    
                    portfolio_data.append({
                        'ticker': stock.ticker,
                        'quantity': stock.quantity,
                        'purchase_price': stock.purchase_price,
                        'current_price': current_price,
                        'value': value,
                        'gain_loss': gain_loss,
                        'gain_loss_percent': gain_loss_percent
                    })
                    
                    total_portfolio_value += value
                else:
                    # Handle cases where stock data couldn't be fetched
                    portfolio_data.append({
                        'ticker': stock.ticker,
                        'quantity': stock.quantity,
                        'purchase_price': stock.purchase_price,
                        'current_price': 'N/A',
                        'value': 'N/A',
                        'gain_loss': 'N/A',
                        'gain_loss_percent': 'N/A'
                    })
    
    # Generate portfolio slug if user doesn't have one
    if current_user.is_authenticated and not current_user.portfolio_slug:
        try:
            current_user.portfolio_slug = generate_portfolio_slug()
            db.session.commit()
            logger.info(f"Generated portfolio slug for user {current_user.id}")
        except Exception as e:
            logger.error(f"Error generating portfolio slug: {str(e)}")
            db.session.rollback()
    
    # Build share URL
    share_url = f"https://apestogether.ai/p/{current_user.portfolio_slug}" if current_user.is_authenticated and current_user.portfolio_slug else ""
    
    # Get user's leaderboard positions (if in top 20)
    # This reads from pre-calculated LeaderboardCache (fast), doesn't recalculate entire leaderboard
    leaderboard_positions = {}
    try:
        from leaderboard_utils import get_user_leaderboard_positions
        leaderboard_positions = get_user_leaderboard_positions(current_user.id, top_n=20)
        logger.info(f"Retrieved leaderboard positions for user {current_user.id}: {leaderboard_positions}")
    except Exception as e:
        logger.error(f"Error fetching leaderboard positions: {str(e)}")
        logger.error(traceback.format_exc())
    
    # Get user's portfolio stats (Phase 3)
    portfolio_stats = None
    try:
        from models import UserPortfolioStats
        portfolio_stats = UserPortfolioStats.query.filter_by(user_id=current_user.id).first()
        logger.info(f"DEBUG: Portfolio stats for user {current_user.id}: {portfolio_stats}")
    except Exception as e:
        logger.error(f"Error fetching portfolio stats: {str(e)}")
    
    elapsed_time = time.time() - start_time
    logger.info(f"⏱️ Dashboard load completed for user {current_user.id} in {elapsed_time:.2f}s")
    
    return render_template_with_defaults('dashboard.html', 
                                       portfolio_data=portfolio_data,
                                       stocks=portfolio_data,  # Template expects 'stocks' variable
                                       total_portfolio_value=total_portfolio_value,
                                       leaderboard_positions=leaderboard_positions,
                                       portfolio_stats=portfolio_stats,
                                       share_url=share_url,
                                       now=datetime.now())

@app.route('/update_username', methods=['POST'])
@login_required
def update_username():
    """Update the user's username."""
    new_username = request.form.get('username')
    if not new_username or len(new_username) < 3:
        flash('Username must be at least 3 characters long', 'danger')
        return redirect(url_for('dashboard'))
    
    # Check if username already exists (except for current user)
    existing_user = User.query.filter(User.username == new_username, User.id != current_user.id).first()
    if existing_user:
        flash('Username already taken', 'danger')
        return redirect(url_for('dashboard'))
    
    try:
        current_user.username = new_username
        db.session.commit()
        flash('Username updated successfully', 'success')
        # Update session if using session-based auth
        if 'username' in session:
            session['username'] = new_username
    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Error updating username: {str(e)}")
        flash('An error occurred while updating your username', 'danger')
    
    return redirect(url_for('dashboard'))

@app.route('/api/portfolio_value')
def portfolio_value():
    """API endpoint to get portfolio value data - returns JSON, not HTML redirects"""
    from datetime import date, datetime
    from models import PortfolioSnapshot
    
    # Check authentication without redirect (API endpoints should return JSON, not HTML redirects)
    if not current_user.is_authenticated:
        return jsonify({'error': 'User not authenticated'}), 401
    
    # Get current user from session
    current_user_id = current_user.id
    
    # Check if it's weekend or after market hours - use cached snapshots
    today = get_market_date()  # FIX: Use ET not UTC
    is_weekend = today.weekday() >= 5  # Saturday = 5, Sunday = 6
    current_hour = get_market_time().hour  # FIX: Use ET not UTC
    is_after_hours = current_hour < 9 or current_hour >= 16  # Before 9 AM or after 4 PM
    
    # ALWAYS fetch actual stock prices (smart cache handles efficiency)
    # Smart cache returns:
    # - Market hours: 90-second fresh cache
    # - After hours/weekends: Friday's closing price from cache (or API if not cached)
    stocks = Stock.query.filter_by(user_id=current_user_id).all()
    portfolio_data = []
    total_value = 0
    
    # Get all tickers for batch processing
    tickers = [stock.ticker for stock in stocks]
    batch_prices = get_batch_stock_data(tickers)
    
    # Use actual stock prices (not proportional estimates)
    for stock in stocks:
        ticker_upper = stock.ticker.upper()
        current_price = batch_prices.get(ticker_upper)
        
        if current_price is not None:
            value = stock.quantity * current_price
            total_value += value
            stock_info = {
                'id': stock.id,
                'ticker': stock.ticker,
                'quantity': stock.quantity,
                'purchase_price': stock.purchase_price,
                'current_price': current_price,
                'value': value,
                'gain_loss': (current_price - stock.purchase_price) * stock.quantity if stock.purchase_price else 0
            }
            portfolio_data.append(stock_info)
        else:
            # Handle cases where stock data couldn't be fetched
            stock_info = {
                'id': stock.id,
                'ticker': stock.ticker,
                'quantity': stock.quantity,
                'purchase_price': stock.purchase_price,
                'current_price': 'N/A',
                'value': 'N/A',
                'gain_loss': 'N/A'
            }
            portfolio_data.append(stock_info)
    
    return jsonify({
        'stocks': portfolio_data,
        'total_value': total_value
    })

@app.route('/save_onboarding', methods=['POST'])
@login_required
def save_onboarding():
    """Process the submitted stocks from onboarding"""
    # Get current user from session
    current_user_id = session.get('user_id')
    current_user = User.query.get(current_user_id)
    
    # Process the submitted stocks
    stocks_to_add = []
    
    # First collect all valid ticker/quantity pairs
    for i in range(10):  # We have 10 possible stock entries
        ticker = request.form.get(f'ticker_{i}')
        quantity = request.form.get(f'quantity_{i}')
        
        # Only process rows where both fields are filled
        if ticker and quantity:
            try:
                stocks_to_add.append({
                    'ticker': ticker.upper(),
                    'quantity': float(quantity)
                })
            except ValueError:
                flash(f'Invalid quantity for {ticker}. Skipped.', 'warning')
    
    # If we have stocks to check, validate and add them
    if stocks_to_add:
        stocks_added_count = 0
        for stock_data in stocks_to_add:
            stock_data_db = get_stock_data(stock_data['ticker'])
            if stock_data_db and stock_data_db.get('price') is not None:
                stock = Stock(
                    ticker=stock_data['ticker'],
                    quantity=stock_data['quantity'],
                    purchase_price=stock_data_db['price'],
                    user_id=current_user_id
                )
                db.session.add(stock)
                stocks_added_count += 1
            else:
                flash(f"Could not find ticker '{stock_data['ticker']}'. It was not added.", 'warning')
        
        if stocks_added_count > 0:
            db.session.commit()
            flash(f'Successfully added {stocks_added_count} stock(s) to your portfolio!', 'success')
    else:
        flash('No stocks were entered.', 'warning')
    
    return redirect(url_for('dashboard'))

@app.route('/stock-comparison')
def stock_comparison():
    """Stock comparison page with mock data"""
    try:
        # Generate mock data for the last 30 days
        from datetime import datetime, timedelta
        import random
        
        dates = []
        tsla_prices = []
        sp500_prices = []
        
        # Start with base prices
        tsla_base = 240.0
        spy_base = 500.0
        
        # Generate 30 days of mock data
        for i in range(30):
            day = datetime.now() - timedelta(days=30-i)
            dates.append(day.strftime('%Y-%m-%d'))
            
            # Add some random variation
            tsla_change = random.uniform(-10, 10)
            spy_change = random.uniform(-5, 5)
            
            tsla_base += tsla_change
            spy_base += spy_change
            
            tsla_prices.append(round(tsla_base, 2))
            sp500_prices.append(round(spy_base, 2))

        # Return the mock data
        return render_template_with_defaults('stock_comparison.html', dates=dates, tsla_prices=tsla_prices, sp500_prices=sp500_prices)
        
    except Exception as e:
        flash(f"Error generating mock stock comparison data: {e}", "danger")
        return render_template_with_defaults('stock_comparison.html', dates=[], tsla_prices=[], sp500_prices=[])

@app.route('/profile/<username>')
@login_required
def profile(username):
    """Redirect to the new public portfolio page at /p/<slug>."""
    # Redirect to own dashboard if viewing self
    current_user_id = session.get('user_id')
    current_user = User.query.get(current_user_id)
    
    if current_user.username == username:
        return redirect(url_for('dashboard'))

    user_to_view = User.query.filter_by(username=username).first_or_404()

    # Ensure user has a portfolio slug, generate one if missing
    if not user_to_view.portfolio_slug:
        user_to_view.portfolio_slug = generate_portfolio_slug()
        db.session.commit()

    # Redirect to the redesigned public portfolio page
    return redirect(f'/p/{user_to_view.portfolio_slug}')

@app.route('/admin-panel')
def admin_panel():
    """Serve the admin dashboard. Requires Google OAuth + TOTP verification."""
    email = session.get('email', '')
    if email != ADMIN_EMAIL:
        # Not logged in as admin — redirect to Google OAuth
        session['admin_panel_redirect'] = True
        return redirect(url_for('login_google'))
    # Must verify TOTP every session
    if not session.get('admin_2fa_verified'):
        return render_template('admin_2fa_gate.html')
    return render_template('admin_panel.html', admin_api_key=os.environ.get('ADMIN_API_KEY', ''))

@app.route('/admin-panel/verify-2fa', methods=['POST'])
def admin_panel_verify_2fa():
    """Verify TOTP code for admin panel access."""
    from mobile_api import _verify_totp
    email = session.get('email', '')
    if email != ADMIN_EMAIL:
        return jsonify({'error': 'not_admin'}), 403
    
    otp_code = request.form.get('otp') or (request.json or {}).get('otp')
    if not otp_code:
        return jsonify({'error': 'otp_required'}), 400
    
    totp_secret = os.environ.get('ADMIN_TOTP_SECRET')
    if not totp_secret:
        # If TOTP isn't configured yet, let them through with a warning
        logger.warning("ADMIN_TOTP_SECRET not set — skipping 2FA for admin panel")
        session['admin_2fa_verified'] = True
        return redirect(url_for('admin_panel'))
    
    if _verify_totp(otp_code):
        session['admin_2fa_verified'] = True
        return redirect(url_for('admin_panel'))
    else:
        return render_template('admin_2fa_gate.html', error='Invalid or expired code. Try again.')

@app.route('/api/admin-panel/auth-status')
def admin_panel_auth_status():
    """Check if the current session is a fully authenticated admin (OAuth + 2FA). Used by SPA."""
    email = session.get('email', '')
    if email == ADMIN_EMAIL and session.get('admin_2fa_verified'):
        return jsonify({'authenticated': True, 'email': email})
    return jsonify({'authenticated': False}), 401


@app.route('/admin/subscription-analytics')
@admin_2fa_required
def admin_subscription_analytics():
    """Admin dashboard for subscription analytics"""
    # Check if user is admin
    current_user_id = session.get('user_id')
    current_user = User.query.get(current_user_id)
    
    try:
        # Get subscription analytics data
        active_subscriptions_count = Subscription.query.filter_by(status='active').count()
        
        # Calculate total revenue (assuming $5 per subscription per month)
        subscription_price = 5.00
        total_revenue = active_subscriptions_count * subscription_price
        
        # Get recent subscriptions
        recent_subscriptions = Subscription.query.order_by(Subscription.start_date.desc()).limit(10).all()
        
        # Calculate conversion rate (subscriptions / total users)
        total_users = User.query.count()
        conversion_rate = round((active_subscriptions_count / total_users) * 100, 2) if total_users > 0 else 0
        
        # Calculate churn rate (canceled subscriptions / total subscriptions)
        canceled_subscriptions = Subscription.query.filter_by(status='canceled').count()
        total_subscriptions = active_subscriptions_count + canceled_subscriptions
        churn_rate = round((canceled_subscriptions / total_subscriptions) * 100, 2) if total_subscriptions > 0 else 0
        
        # Generate subscription growth data for the last 30 days
        subscription_dates = []
        subscription_counts = []
        revenue_dates = []
        revenue_amounts = []
        
        # Get the last 30 days
        today = datetime.utcnow().date()
        for i in range(30, 0, -1):
            date = today - timedelta(days=i)
            date_str = date.strftime('%Y-%m-%d')
            subscription_dates.append(date_str)
            
            # Count subscriptions created on this date
            count = Subscription.query.filter(
                func.date(Subscription.start_date) == date
            ).count()
            subscription_counts.append(count)
        
        # Generate monthly revenue data for the last 6 months
        for i in range(6, 0, -1):
            # Calculate the month and year correctly
            month = today.month - i + 1
            year = today.year
            
            # Handle year boundary
            if month <= 0:
                month += 12
                year -= 1
                
            # Get the first day of the month
            first_day = datetime(year, month, 1).date()
            month_name = first_day.strftime('%b %Y')
            revenue_dates.append(month_name)
            
            # Count active subscriptions in this month
            month_subscriptions = Subscription.query.filter(
                func.extract('month', Subscription.start_date) == first_day.month,
                func.extract('year', Subscription.start_date) == first_day.year,
                Subscription.status == 'active'
            ).count()
            revenue_amounts.append(month_subscriptions * subscription_price)
    except Exception as e:
        app.logger.error(f"Database error in admin_subscription_analytics: {str(e)}")
        # Fallback to mock data if database fails
        active_subscriptions_count = 15
        total_revenue = 75.00
        recent_subscriptions = []
        conversion_rate = 25.5
        churn_rate = 10.2
        subscription_dates = [f"2025-06-{i}" for i in range(16, 16+30)]
        subscription_counts = [random.randint(0, 3) for _ in range(30)]
        revenue_dates = ['Feb 2025', 'Mar 2025', 'Apr 2025', 'May 2025', 'Jun 2025', 'Jul 2025']
        revenue_amounts = [15.0, 25.0, 35.0, 45.0, 60.0, 75.0]
    
    return render_template_with_defaults(
        'admin/subscription_analytics.html',
        active_subscriptions_count=active_subscriptions_count,
        total_revenue=total_revenue,
        recent_subscriptions=recent_subscriptions,
        subscription_price=subscription_price,
        conversion_rate=conversion_rate,
        churn_rate=churn_rate,
        subscription_dates=subscription_dates,
        subscription_counts=subscription_counts,
        revenue_dates=revenue_dates,
        revenue_amounts=revenue_amounts
    )

# ── Removed: /admin/debug, /admin/debug/users, /admin/debug/oauth,
# /admin/debug/database, /admin/debug/models, /admin/debug/oauth-login
# These unprotected debug endpoints exposed internal state to the public internet.
# Use the admin panel dashboard or Vercel logs for diagnostics instead.

@app.route('/favicon.png')
def serve_favicon():
    try:
        return send_from_directory(app.static_folder, 'favicon.png')
    except Exception as e:
        logger.error(f"Error serving favicon: {str(e)}")
        return '', 404

# Health check endpoints
@app.route('/api/health')
def health_check():
    try:
        # Check database connectivity with retry to avoid poisoning connection state
        db_status = False
        version = None
        try:
            def _health_query():
                r = db.session.execute(text('SELECT version()'))
                return r.scalar()
            version = db_retry(_health_query, max_retries=2)
            db_status = True
        except Exception as e:
            logger.error(f"Database health check failed: {str(e)}")
            # Clean up immediately so this doesn't poison the next request
            try:
                db.session.rollback()
            except Exception:
                pass
            try:
                db.session.remove()
            except Exception:
                pass
            try:
                db.engine.dispose()
            except Exception:
                pass
            # Clear the error flag — we already disposed, no need for before_request to do it again
            app._last_request_had_db_error = False
        
        # Return health status
        return jsonify({
            'status': 'ok',
            'timestamp': datetime.now().isoformat(),
            'database': {
                'connected': db_status,
                'version': version
            },
            'environment': os.environ.get('VERCEL_ENV', 'development')
        })
    except Exception as e:
        logger.error(f"Health check failed: {str(e)}")
        return jsonify({'status': 'error', 'message': 'Health check failed'}), 500

@app.route('/api/init-db', methods=['POST'])
def init_database():
    """Initialize database tables for fresh Supabase instance.
    Protected by SECRET_KEY in Authorization header (not URL).
    Usage: POST /api/init-db  with header  Authorization: Bearer <SECRET_KEY>
    NOTE: force-drop is permanently disabled to prevent accidental data loss.
    """
    try:
        # Verify secret key from Authorization header (never from URL query string)
        auth_header = request.headers.get('Authorization', '')
        provided_key = ''
        if auth_header.startswith('Bearer '):
            provided_key = auth_header[7:]
        expected_key = os.environ.get('SECRET_KEY', '')
        
        if not provided_key or provided_key != expected_key:
            return jsonify({'error': 'Unauthorized'}), 403
        
        # Import all models
        from models import (db, User, Stock, Transaction, PortfolioSnapshot, StockInfo, 
                           SubscriptionTier, Subscription, SMSNotification, LeaderboardCache, 
                           UserPortfolioChartCache, AlphaVantageAPILog, PlatformMetrics, 
                           UserActivity, NotificationPreferences, NotificationLog,
                           AdminSubscription, PortfolioSnapshotIntraday)
        
        results = []
        
        # Create all tables (additive only — never drops existing data)
        try:
            db.create_all()
            results.append('All database tables created successfully')
        except Exception as e:
            results.append(f'Table creation error: {str(e)}')
        
        # Commit
        try:
            db.session.commit()
            results.append('Database commit successful')
        except Exception as e:
            db.session.rollback()
            results.append(f'Commit error: {str(e)}')
        
        # Verify tables exist
        try:
            user_count = User.query.count()
            results.append(f'User table exists, count: {user_count}')
        except Exception as e:
            results.append(f'User table check error: {str(e)}')
        
        return jsonify({
            'status': 'success',
            'message': 'Database initialized',
            'results': results,
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        logger.error(f"Database init failed: {str(e)}")
        return jsonify({'status': 'error', 'message': 'Internal error'}), 500

# SMS/Email Trading Endpoints
# DISABLED (Feb 2026): Twilio SMS trading disabled, mobile app uses push notifications
@app.route('/api/twilio/inbound', methods=['POST'])
def twilio_inbound():
    """DISABLED: Twilio inbound SMS - replaced by mobile push notifications Feb 2026"""
    return '', 410

@app.route('/api/email/inbound', methods=['POST'])
def email_inbound():
    """Handle inbound emails from SendGrid for trade execution"""
    try:
        from services.trading_email import handle_inbound_email
        
        # SendGrid sends email data as form-encoded
        from_email = request.form.get('from') or request.json.get('from')
        subject = request.form.get('subject') or request.json.get('subject')
        body = request.form.get('text') or request.json.get('text')
        
        if not from_email:
            return jsonify({'error': 'Missing from email'}), 400
        
        # Extract email address from "Name <email@example.com>" format
        import re
        email_match = re.search(r'<(.+?)>', from_email)
        if email_match:
            from_email = email_match.group(1)
        
        # Handle the email (parse, execute trade, send confirmations)
        result = handle_inbound_email(from_email, subject or '', body or '')
        
        # Return empty response (SendGrid doesn't need content)
        return '', 200
        
    except Exception as e:
        logger.error(f"Email inbound error: {str(e)}")
        logger.error(traceback.format_exc())
        # Still return 200 to SendGrid to avoid retries
        return '', 200

# Root health check endpoint
@app.route('/health')
def root_health_check():
    try:
        # Simple health check that doesn't access the database
        return jsonify({
            'status': 'ok',
            'timestamp': datetime.now().isoformat(),
            'environment': os.environ.get('VERCEL_ENV', 'development')
        })
    except Exception as e:
        logger.error(f"Root health check failed: {str(e)}")
        return jsonify({'status': 'error', 'message': 'Health check failed'}), 500


@app.route('/login', methods=['GET', 'POST'])
@limiter.limit("10 per minute")
def login():
    """User login page"""
    try:
        if request.method == 'POST':
            email = request.form.get('email')
            password = request.form.get('password')
            
            logger.info(f"Login attempt for email: {email}")
            
            try:
                user = User.query.filter_by(email=email).first()
                logger.info(f"User found: {user is not None}")
                
                if user:
                    password_check = user.check_password(password)
                    logger.info(f"Password check result: {password_check}")
                    
                    if password_check:
                        # A soft-deleted account cannot be logged into. We do NOT
                        # silently restore it — that would hide a malicious deletion
                        # from the victim. Tell them to contact support; the 30-day
                        # purge timer keeps running until support restores it.
                        if user.deleted_at:
                            flash('This account is scheduled for deletion. To restore it, email support@apestogether.ai before the deletion completes.', 'warning')
                            return render_template_with_defaults('login.html')
                        # Use Flask-Login to handle user session
                        login_user(user)
                        logger.info(f"User logged in successfully: {user.username}")
                        flash('Login successful!', 'success')
                        
                        # Log login activity
                        try:
                            from models import UserActivity
                            activity = UserActivity(
                                user_id=user.id,
                                activity_type='login',
                                ip_address=request.remote_addr,
                                user_agent=request.headers.get('User-Agent', '')[:255]
                            )
                            db.session.add(activity)
                            db.session.commit()
                            db.session.flush()  # Ensure record is immediately visible
                            logger.info(f"Successfully logged login activity for user {user.id}")
                        except Exception as e:
                            logger.error(f"Error logging login activity: {str(e)}")
                            logger.error(traceback.format_exc())
                            db.session.rollback()
                        
                        # For backward compatibility, also set session variables
                        session['user_id'] = user.id
                        session['email'] = user.email
                        session['username'] = user.username
                        
                        # Redirect to next page or dashboard
                        next_page = request.args.get('next')
                        return redirect(next_page or url_for('dashboard'))
                    else:
                        logger.warning(f"Invalid password for user: {email}")
                        flash('Invalid email or password', 'danger')
                else:
                    logger.warning(f"User not found with email: {email}")
                    flash('Invalid email or password', 'danger')
            except Exception as e:
                logger.error(f"Error during user lookup or password check: {str(e)}")
                logger.error(traceback.format_exc())
                flash('An error occurred during login. Please try again.', 'danger')
        
    except Exception as e:
        logger.error(f"Unexpected error in login route: {str(e)}")
        logger.error(traceback.format_exc())
        flash('An unexpected error occurred. Please try again later.', 'danger')
    
    return render_template_with_defaults('login.html')

@app.route('/')
def index():
    """Marketing landing page"""
    from models import BetaWaitlist
    try:
        waitlist_count = db_retry(lambda: BetaWaitlist.query.count(), max_retries=2)
    except Exception:
        waitlist_count = 0
    return render_template('landing.html', waitlist_count=waitlist_count)

@app.route('/api/waitlist', methods=['POST'])
def join_waitlist():
    """Add an email to the beta waitlist"""
    from models import BetaWaitlist
    try:
        data = request.get_json() or {}
        email = (data.get('email') or '').strip().lower()
        role = data.get('role', '').strip() or None  # 'investor' or 'trader'
        referral = data.get('referral_source', '').strip() or None

        if not email or '@' not in email:
            return jsonify({'error': 'Valid email required'}), 400

        # Check duplicate
        existing = BetaWaitlist.query.filter_by(email=email).first()
        if existing:
            return jsonify({'success': True, 'message': 'already_on_list', 'position': existing.id})

        entry = BetaWaitlist(email=email, role=role, referral_source=referral)
        db.session.add(entry)
        db.session.commit()

        count = BetaWaitlist.query.count()
        return jsonify({'success': True, 'message': 'added', 'position': count})

    except Exception as e:
        db.session.rollback()
        logger.error(f"Waitlist signup error: {e}")
        return jsonify({'error': 'Something went wrong. Please try again.'}), 500

@app.route('/api/waitlist/count')
def waitlist_count():
    """Public count of waitlist signups (for social proof)"""
    from models import BetaWaitlist
    try:
        count = BetaWaitlist.query.count()
        return jsonify({'count': count})
    except Exception:
        return jsonify({'count': 0})

@app.route('/api/track/pageview', methods=['POST'])
def track_pageview():
    """Log a landing page visit (called from frontend JS)"""
    try:
        from models import PageView, db as _db
        import hashlib
        data = request.get_json(silent=True) or {}
        ip_raw = request.headers.get('X-Forwarded-For', request.remote_addr or '')
        ip_hash = hashlib.sha256(ip_raw.encode()).hexdigest()[:16] if ip_raw else None
        pv = PageView(
            page=data.get('page', '/')[:100],
            referrer=(request.referrer or data.get('referrer', ''))[:500] or None,
            utm_source=data.get('utm_source', '')[:100] or None,
            utm_medium=data.get('utm_medium', '')[:100] or None,
            utm_campaign=data.get('utm_campaign', '')[:100] or None,
            user_agent=(request.headers.get('User-Agent', ''))[:500] or None,
            ip_hash=ip_hash,
        )
        _db.session.add(pv)
        _db.session.commit()
        return jsonify({'ok': True}), 201
    except Exception as e:
        logger.warning(f"Pageview track error: {e}")
        return jsonify({'ok': False}), 200  # Don't error out client


@app.route('/api/track/linkclick', methods=['POST'])
def track_linkclick():
    """Log an app store link click (called from frontend JS)"""
    try:
        from models import LinkClick, db as _db
        import hashlib
        data = request.get_json(silent=True) or {}
        platform = data.get('platform', 'unknown')[:20]
        if platform not in ('apple', 'android'):
            platform = 'unknown'
        ip_raw = request.headers.get('X-Forwarded-For', request.remote_addr or '')
        ip_hash = hashlib.sha256(ip_raw.encode()).hexdigest()[:16] if ip_raw else None
        lc = LinkClick(
            platform=platform,
            source_page=data.get('source_page', '/')[:100] or None,
            utm_source=data.get('utm_source', '')[:100] or None,
            utm_campaign=data.get('utm_campaign', '')[:100] or None,
            user_agent=(request.headers.get('User-Agent', ''))[:500] or None,
            ip_hash=ip_hash,
        )
        _db.session.add(lc)
        _db.session.commit()
        return jsonify({'ok': True}), 201
    except Exception as e:
        logger.warning(f"Link click track error: {e}")
        return jsonify({'ok': False}), 200


@app.route('/admin/waitlist')
@admin_required
def admin_view_waitlist():
    """View all beta waitlist signups with role breakdown."""
    from models import BetaWaitlist
    entries = BetaWaitlist.query.order_by(BetaWaitlist.created_at.desc()).all()
    rows = [{
        'id': e.id,
        'email': e.email,
        'role': e.role or 'unspecified',
        'referral_source': e.referral_source,
        'signed_up': e.created_at.isoformat() if e.created_at else None
    } for e in entries]
    investors = sum(1 for e in entries if e.role == 'investor')
    traders = sum(1 for e in entries if e.role == 'trader')
    unspecified = sum(1 for e in entries if not e.role)
    return jsonify({
        'total': len(rows),
        'breakdown': {'investors': investors, 'traders': traders, 'unspecified': unspecified},
        'entries': rows
    })


@app.route('/admin/debug-user-snapshots')
@admin_required
def admin_debug_user_snapshots():
    """
    Show snapshot data for a user around a date range to diagnose chart jumps.
    Usage: /admin/debug-user-snapshots?username=chart1658&start=2026-03-15&end=2026-05-03
    """
    from models import User, PortfolioSnapshot, Transaction
    from sqlalchemy import and_
    username = request.args.get('username')
    user_id = request.args.get('user_id')
    start = request.args.get('start', '2026-03-01')
    end = request.args.get('end', '2026-05-03')

    if username:
        user = User.query.filter_by(username=username).first()
        if not user:
            return jsonify({'error': f'User {username} not found'}), 404
        user_id = user.id
    elif user_id:
        user_id = int(user_id)
        user = User.query.get(user_id)
    else:
        return jsonify({'error': 'username or user_id required'}), 400

    from datetime import date as _date
    start_date = _date.fromisoformat(start)
    end_date = _date.fromisoformat(end)

    snapshots = PortfolioSnapshot.query.filter(
        and_(
            PortfolioSnapshot.user_id == user_id,
            PortfolioSnapshot.date >= start_date,
            PortfolioSnapshot.date <= end_date
        )
    ).order_by(PortfolioSnapshot.date.asc()).all()

    # Also get transactions in this window to see capital flows
    transactions = Transaction.query.filter(
        and_(
            Transaction.user_id == user_id,
            Transaction.timestamp >= start_date,
            Transaction.timestamp <= end_date
        )
    ).order_by(Transaction.timestamp.asc()).all()

    # Build snapshot rows with day-over-day deltas
    rows = []
    prev = None
    for s in snapshots:
        row = {
            'date': s.date.isoformat(),
            'total_value': round(s.total_value, 2),
            'stock_value': round(s.stock_value or 0, 2),
            'cash_proceeds': round(s.cash_proceeds or 0, 2),
            'max_cash_deployed': round(s.max_cash_deployed or 0, 2),
        }
        if prev:
            row['delta_total_value'] = round(s.total_value - prev.total_value, 2)
            row['delta_max_cash'] = round((s.max_cash_deployed or 0) - (prev.max_cash_deployed or 0), 2)
            row['delta_stock_value'] = round((s.stock_value or 0) - (prev.stock_value or 0), 2)
            # Flag suspicious jumps (>10% in one day on total_value or >$500 on max_cash)
            if prev.total_value > 0:
                pct_change = abs(s.total_value - prev.total_value) / prev.total_value * 100
                row['pct_change'] = round(pct_change, 2)
                if pct_change > 10:
                    row['FLAG'] = f'⚠️ {pct_change:.1f}% daily change'
            if abs(row['delta_max_cash']) > 0:
                row['CAPITAL_FLOW'] = f'💰 ${row["delta_max_cash"]:.2f} new capital'
        prev = s
        rows.append(row)

    txn_rows = [{
        'date': t.timestamp.isoformat() if t.timestamp else 'N/A',
        'type': t.transaction_type,
        'ticker': t.ticker,
        'quantity': t.quantity,
        'price': t.price,
        'total': round(t.quantity * t.price, 2) if t.quantity and t.price else None
    } for t in transactions]

    # Replay cash tracking from ALL transactions to verify max_cash_deployed
    all_txns = Transaction.query.filter(
        Transaction.user_id == user_id
    ).order_by(Transaction.timestamp.asc()).all()
    
    replay_cash = 0.0
    replay_max_cash = 0.0
    replay_log = []
    for txn in all_txns:
        val = txn.quantity * txn.price
        txn_date = txn.timestamp.date().isoformat() if txn.timestamp else 'N/A'
        before_cash = replay_cash
        before_max = replay_max_cash
        if txn.transaction_type in ('buy', 'initial'):
            if replay_cash >= val:
                replay_cash -= val
            else:
                new_cap = val - replay_cash
                replay_cash = 0
                replay_max_cash += new_cap
        elif txn.transaction_type in ('sell', 'dividend'):
            replay_cash += val
        # Only log transactions in our date window for readability
        if start_date <= (txn.timestamp.date() if txn.timestamp else start_date) <= end_date:
            replay_log.append({
                'date': txn_date,
                'type': txn.transaction_type,
                'ticker': txn.ticker,
                'total': round(val, 2),
                'cash_before': round(before_cash, 2),
                'max_cash_before': round(before_max, 2),
                'cash_after': round(replay_cash, 2),
                'max_cash_after': round(replay_max_cash, 2),
            })
    
    return jsonify({
        'user': {
            'id': user_id,
            'username': user.username,
            'max_cash_deployed_current': user.max_cash_deployed,
            'cash_proceeds_current': user.cash_proceeds,
            'max_cash_deployed_replayed': round(replay_max_cash, 2),
            'cash_proceeds_replayed': round(replay_cash, 2),
            'drift': round(user.max_cash_deployed - replay_max_cash, 2),
        },
        'period': f'{start} to {end}',
        'snapshot_count': len(rows),
        'transaction_count': len(txn_rows),
        'total_transaction_count': len(all_txns),
        'snapshots': rows,
        'transactions': txn_rows,
        'cash_replay_in_window': replay_log,
    })


@app.route('/admin/audit-snapshot-cash-drift')
@admin_required
def admin_audit_snapshot_cash_drift():
    """
    Walk every PortfolioSnapshot for every user and verify that
    snapshot.cash_proceeds matches what a chronological transaction replay
    would yield at the end of that snapshot's date.

    The bug pattern this catches: snapshots written with stale User.cash_proceeds
    while live Stock holdings already reflect the same-day bot trades, causing
    phantom 'drops' on the chart whenever a sell happens close to snapshot time.
    Manifested today as panther2585 May 7-8: stock_value reflected post-sell
    holdings, but cash_proceeds did not yet reflect the sell proceeds.

    Query params:
      ?threshold=0.50   Min |drift| in $ to flag a snapshot (default 0.50)
      ?limit_users=N    Audit only the first N users (for spot-checking)
      ?role=agent       Restrict to bot accounts only
      ?fix=true         Apply UPDATEs to repair flagged snapshots in-place
                        (sets cash_proceeds = expected, total_value = stock_value + expected)

    Response: per-user summary of bad snapshots, plus aggregate counts.
    """
    from models import db, User, Transaction, PortfolioSnapshot
    from sqlalchemy import text as _sql_text
    from datetime import time as _dt_time, timedelta as _td

    try:
        threshold = float(request.args.get('threshold', '0.50'))
    except (TypeError, ValueError):
        threshold = 0.50
    role_filter = request.args.get('role')
    limit_users_param = request.args.get('limit_users')
    apply_fix = request.args.get('fix', 'false').lower() == 'true'

    try:
        from mobile_api import _is_copytrade_bot
    except Exception:
        def _is_copytrade_bot(_u):
            return False

    # Bucket each trade by its UTC calendar date to MATCH the snapshot writer
    # (calculate_cash_proceeds_as_of_date + historical stock-value replay both use
    # `func.date(Transaction.timestamp) <= target_date`). The old 20:05-UTC cutoff
    # rolled late-wave trades to the next day and falsely flagged snapshots that had
    # correctly captured them same-day. See cron_snapshot_audit for the full write-up.
    def _eff_date(ts):
        if ts is None:
            return None
        return (ts.replace(tzinfo=None) if ts.tzinfo else ts).date()

    # Ambiguous-trade tolerance: post-market-close trades (>= 20:00 UTC) on date D
    # may or may not be in that day's EOD snapshot; tolerate their summed |value| so
    # boundary-wave trades never falsely flag. Intraday trades still surface genuine drift.
    _amb_start = _dt_time(20, 0)
    _amb_end = _dt_time(23, 59, 59)

    q = User.query.order_by(User.id.asc())
    if role_filter:
        q = q.filter(User.role == role_filter)
    users = q.all()
    if limit_users_param:
        try:
            users = users[: int(limit_users_param)]
        except (TypeError, ValueError):
            pass

    issues = []
    total_snapshots_checked = 0
    total_bad_snapshots = 0
    fix_count = 0
    skipped_copytrade = 0

    for user in users:
        # Copytrade bots derive cash/holdings from brokerage-screenshot migrations
        # (price_source='phase_c_migration') that a transaction replay cannot
        # reproduce — they always show false-positive drift. Skip them so a blanket
        # ?fix=true can never overwrite their brokerage-matched cash.
        if _is_copytrade_bot(user):
            skipped_copytrade += 1
            continue
        txns = Transaction.query.filter_by(user_id=user.id).order_by(
            Transaction.timestamp.asc()
        ).all()
        snaps = PortfolioSnapshot.query.filter_by(user_id=user.id).order_by(
            PortfolioSnapshot.date.asc()
        ).all()
        if not snaps or not txns:
            continue

        # Pre-compute per-date ambiguous-trade tolerance for this user
        amb_tol_by_date = {}
        for txn in txns:
            if txn.timestamp is None:
                continue
            ts_n = txn.timestamp.replace(tzinfo=None) if txn.timestamp.tzinfo else txn.timestamp
            if _amb_start <= ts_n.time() < _amb_end:
                v = abs(float((txn.quantity or 0) * (txn.price or 0)))
                d = ts_n.date()
                amb_tol_by_date[d] = amb_tol_by_date.get(d, 0.0) + v

        # Replay transactions chronologically bucketed by UTC calendar date (matching
        # the snapshot writer's func.date(timestamp) filter). Post-close boundary-wave
        # trades are absorbed by the ambiguous-trade tolerance computed above.
        replay_cash = 0.0
        replay_max = 0.0
        txn_idx = 0

        user_bad = []
        for snap in snaps:
            # Advance through txns whose effective_date is on or before snap.date
            while txn_idx < len(txns):
                txn = txns[txn_idx]
                txn_eff = _eff_date(txn.timestamp)
                if txn_eff is None or txn_eff > snap.date:
                    break
                val = (txn.quantity or 0) * (txn.price or 0)
                if txn.transaction_type in ('buy', 'initial'):
                    if replay_cash >= val:
                        replay_cash -= val
                    else:
                        replay_max += val - replay_cash
                        replay_cash = 0
                elif txn.transaction_type in ('sell', 'dividend'):
                    replay_cash += val
                txn_idx += 1

            actual_cash = round(float(snap.cash_proceeds or 0), 2)
            expected_cash = round(replay_cash, 2)
            cash_drift = round(expected_cash - actual_cash, 2)

            total_snapshots_checked += 1

            # Apply ambiguous-trade tolerance for this snapshot's date
            amb_tol = amb_tol_by_date.get(snap.date, 0.0)
            effective_threshold = threshold + amb_tol

            if abs(cash_drift) >= effective_threshold:
                total_bad_snapshots += 1
                user_bad.append({
                    'date': snap.date.isoformat(),
                    'actual_cash_proceeds': actual_cash,
                    'expected_cash_proceeds': expected_cash,
                    'drift': cash_drift,
                    'stock_value': round(float(snap.stock_value or 0), 2),
                    'actual_total_value': round(float(snap.total_value or 0), 2),
                    'expected_total_value': round(
                        float(snap.stock_value or 0) + expected_cash, 2
                    ),
                    'ambiguous_tolerance': round(amb_tol, 2) if amb_tol > 0 else None,
                })

                if apply_fix:
                    # Repair the snapshot in-place. Use parameterized update.
                    db.session.execute(_sql_text("""
                        UPDATE portfolio_snapshot
                        SET cash_proceeds = :cp,
                            total_value = stock_value + :cp
                        WHERE id = :sid
                    """), {'cp': expected_cash, 'sid': snap.id})
                    fix_count += 1

        if user_bad:
            issues.append({
                'user_id': user.id,
                'username': user.username,
                'role': user.role,
                'bad_snapshot_count': len(user_bad),
                'first_bad_date': user_bad[0]['date'],
                'last_bad_date': user_bad[-1]['date'],
                'max_abs_drift': round(max(abs(b['drift']) for b in user_bad), 2),
                'sample_bad_snapshots': user_bad[:5],
                'all_bad_snapshots': user_bad if len(user_bad) <= 30 else None,
            })

    if apply_fix:
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            return jsonify({
                'error': 'commit_failed',
                'message': str(e),
                'fix_count_attempted': fix_count,
            }), 500

    # Sort issues by max drift descending so worst cases surface first
    issues.sort(key=lambda x: -x['max_abs_drift'])

    return jsonify({
        'threshold': threshold,
        'fix_applied': apply_fix,
        'fix_count': fix_count if apply_fix else 0,
        'users_scanned': len(users),
        'copytrade_bots_skipped': skipped_copytrade,
        'users_with_issues': len(issues),
        'total_snapshots_checked': total_snapshots_checked,
        'total_bad_snapshots': total_bad_snapshots,
        'issues': issues,
        'next_steps': (
            'After fixing, run DELETE FROM user_portfolio_chart_cache WHERE user_id IN (...) '
            'for affected users to force chart regeneration from the corrected snapshots.'
        ),
    })


@app.route('/admin/audit-intraday-anomalies')
@admin_required
def admin_audit_intraday_anomalies():
    """
    Fleet-wide scan of PortfolioSnapshotIntraday for one-tick spike/dip-and-revert
    rows: a snapshot whose total_value deviates from BOTH its same-day neighbors in
    the SAME direction by >= threshold, i.e. an isolated outlier that snaps back.

    ROOT CAUSE (see cash_tracking.calculate_portfolio_value_with_cash): the intraday
    writer reads user.cash_proceeds and the Stock holdings in TWO separate queries.
    A bot trade commits both atomically, but if it lands between those reads the row
    stores post-trade stock_value with pre-trade cash (spike on a buy) or pre-trade
    stock_value with post-trade cash (dip on a sell). The next tick reads cleanly, so
    the artifact is a single isolated outlier. The daily-snapshot twin of this race is
    handled by /admin/audit-snapshot-cash-drift; this covers the intraday table, which
    no existing audit touched. The source race is now fixed, so this should mainly
    surface PRE-FIX historical rows.

    Query params:
      ?threshold=0.025        Min |deviation| vs EACH neighbor to flag (fraction; default 0.025 = 2.5%)
      ?days=N                 Only scan intraday snapshots from the last N days (default: all)
      ?role=agent             Restrict to a single role
      ?limit_users=N          Audit only the first N users
      ?fingerprint_only=true  Only report rows matching the cash-lag race signature
      ?fix=true               DELETE the flagged rows (chart then interpolates across
                              the gap). Read-only unless this is set.

    Response: per-user flagged rows with prev/outlier/next decomposition + aggregates.
    """
    from models import db, User, PortfolioSnapshotIntraday
    from datetime import datetime as _dt, timedelta as _td

    try:
        threshold = float(request.args.get('threshold', '0.025'))
    except (TypeError, ValueError):
        threshold = 0.025
    role_filter = request.args.get('role')
    limit_users_param = request.args.get('limit_users')
    fingerprint_only = request.args.get('fingerprint_only', 'false').lower() == 'true'
    apply_fix = request.args.get('fix', 'false').lower() == 'true'
    days_param = request.args.get('days')
    since = None
    if days_param:
        try:
            since = _dt.utcnow() - _td(days=int(days_param))
        except (TypeError, ValueError):
            since = None

    q = User.query.order_by(User.id.asc())
    if role_filter:
        q = q.filter(User.role == role_filter)
    users = q.all()
    if limit_users_param:
        try:
            users = users[: int(limit_users_param)]
        except (TypeError, ValueError):
            pass

    def _f(v):
        return float(v) if v is not None else None

    def _r(v):
        return round(float(v), 2) if v is not None else None

    issues = []
    total_points_checked = 0
    total_flagged = 0
    total_fingerprint = 0
    fix_ids = []

    for user in users:
        sq = PortfolioSnapshotIntraday.query.filter_by(user_id=user.id)
        if since is not None:
            sq = sq.filter(PortfolioSnapshotIntraday.timestamp >= since)
        snaps = sq.order_by(PortfolioSnapshotIntraday.timestamp.asc()).all()
        if len(snaps) < 3:
            continue

        # Group by UTC calendar date so we never compare across the overnight gap
        # (open-vs-prior-close jumps are legitimate price moves, not phantoms).
        by_day = {}
        for s in snaps:
            ts = s.timestamp
            if ts is None or s.total_value is None:
                continue
            d = (ts.replace(tzinfo=None) if ts.tzinfo else ts).date()
            by_day.setdefault(d, []).append(s)

        user_flagged = []
        for d, day_snaps in by_day.items():
            n = len(day_snaps)
            if n < 3:
                continue
            for i in range(1, n - 1):
                prev_s, cur_s, next_s = day_snaps[i - 1], day_snaps[i], day_snaps[i + 1]
                prev_t = _f(prev_s.total_value)
                cur_t = _f(cur_s.total_value)
                next_t = _f(next_s.total_value)
                total_points_checked += 1
                if not prev_t or not next_t or cur_t is None:
                    continue
                dev_prev = (cur_t - prev_t) / prev_t
                dev_next = (cur_t - next_t) / next_t
                # Isolated outlier: deviates from BOTH neighbors in the SAME direction.
                is_spike = dev_prev >= threshold and dev_next >= threshold
                is_dip = dev_prev <= -threshold and dev_next <= -threshold
                if not (is_spike or is_dip):
                    continue

                # Cash-lag fingerprint: at the outlier the cash side did NOT move from
                # the previous tick, then the next tick corrects cash. This is the exact
                # race signature (requires the cash columns to be populated).
                cur_cash = _f(cur_s.cash_proceeds)
                prev_cash = _f(prev_s.cash_proceeds)
                next_cash = _f(next_s.cash_proceeds)
                fingerprint = None
                if None not in (cur_cash, prev_cash, next_cash):
                    cash_static = abs(cur_cash - prev_cash) < 0.005
                    cash_moves_next = abs(next_cash - cur_cash) >= 0.01
                    fingerprint = bool(cash_static and cash_moves_next)

                if fingerprint_only and not fingerprint:
                    continue

                total_flagged += 1
                if fingerprint:
                    total_fingerprint += 1
                if apply_fix:
                    fix_ids.append(cur_s.id)

                user_flagged.append({
                    'snapshot_id': cur_s.id,
                    'timestamp': cur_s.timestamp.isoformat(),
                    'direction': 'spike' if is_spike else 'dip',
                    'dev_vs_prev_pct': round(dev_prev * 100, 3),
                    'dev_vs_next_pct': round(dev_next * 100, 3),
                    'cash_lag_fingerprint': fingerprint,
                    'prev': {'total': _r(prev_t), 'stock': _r(prev_s.stock_value), 'cash': _r(prev_cash)},
                    'outlier': {'total': _r(cur_t), 'stock': _r(cur_s.stock_value), 'cash': _r(cur_cash)},
                    'next': {'total': _r(next_t), 'stock': _r(next_s.stock_value), 'cash': _r(next_cash)},
                })

        if user_flagged:
            user_flagged.sort(
                key=lambda x: max(abs(x['dev_vs_prev_pct']), abs(x['dev_vs_next_pct'])),
                reverse=True,
            )
            issues.append({
                'user_id': user.id,
                'username': user.username,
                'role': user.role,
                'flagged_count': len(user_flagged),
                'fingerprint_count': sum(1 for f in user_flagged if f['cash_lag_fingerprint']),
                'max_dev_pct': round(
                    max(max(abs(f['dev_vs_prev_pct']), abs(f['dev_vs_next_pct'])) for f in user_flagged), 3
                ),
                'sample': user_flagged[:5],
                'all_flagged': user_flagged if len(user_flagged) <= 50 else None,
            })

    rows_deleted = 0
    if apply_fix and fix_ids:
        try:
            for chunk_start in range(0, len(fix_ids), 500):
                chunk = fix_ids[chunk_start:chunk_start + 500]
                rows_deleted += PortfolioSnapshotIntraday.query.filter(
                    PortfolioSnapshotIntraday.id.in_(chunk)
                ).delete(synchronize_session=False)
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            return jsonify({
                'error': 'delete_failed',
                'message': str(e),
                'fix_count_attempted': len(fix_ids),
            }), 500

    issues.sort(key=lambda x: -x['max_dev_pct'])
    return jsonify({
        'threshold_pct': round(threshold * 100, 3),
        'fingerprint_only': fingerprint_only,
        'fix_applied': apply_fix,
        'rows_deleted': rows_deleted,
        'days_scanned': days_param or 'all',
        'users_scanned': len(users),
        'users_with_issues': len(issues),
        'total_points_checked': total_points_checked,
        'total_flagged_rows': total_flagged,
        'total_fingerprint_rows': total_fingerprint,
        'issues': issues,
        'next_steps': (
            'Add ?fingerprint_only=true to isolate the exact cash-lag race signature. '
            'Re-run with ?fix=true to DELETE flagged rows (the 1D chart interpolates across '
            'the gap). The source race is fixed in calculate_portfolio_value_with_cash, so '
            'only PRE-FIX historical rows should appear going forward.'
        ),
    })


@app.route('/admin/audit-snapshot-stock-value')
@admin_required
def admin_audit_snapshot_stock_value():
    """
    Fleet-wide validation of PortfolioSnapshot.stock_value — the one snapshot field no
    existing audit checks (cash-drift + max-cash-drift cover cash / max_cash_deployed only).

    For each daily snapshot we reconstruct holdings as-of that date by replaying the user's
    transactions (buy/initial +qty, sell -qty; dividends don't change share count) — exactly
    mirroring PortfolioPerformanceCalculator.calculate_portfolio_value's HISTORICAL branch
    (same `func.date(timestamp) <= target_date` bucketing) — and price each holding from the
    MarketData daily close (timestamp IS NULL). We use the EXACT-date close when present
    (matching get_historical_price); if absent we carry forward the most recent earlier close,
    which is correct on weekends/holidays but on a *weekday* signals a MarketData gap we can't
    trust, so such rows are reported as unvalidatable rather than flagged for drift.

    Issue buckets:
      - DRIFT: snapshot fully priced (every holding has an exact/weekend close) yet
        |expected - stored stock_value| exceeds the threshold. Historical closes are
        deterministic, so real drift means the stored value used a bad price (the live-day
        path can fall back to an expired cache price or, worst case, purchase_price) or a
        wrong quantity. These are the only rows ?fix=true will repair.
      - MISSING_PRICE: a held ticker has NO MarketData close on-or-before the date.
        calculate_portfolio_value SILENTLY SKIPS unpriced holdings (price=None -> continue),
        undervaluing the snapshot. Needs a MarketData backfill, NOT an in-place recompute,
        so these are never auto-fixed.
      - STALE_WEEKDAY: a weekday snapshot whose ticker lacks an exact-date close (only an
        older one exists) — a MarketData coverage gap; reported, not drift-flagged.
      - ABSURD_PRICE: a MarketData close <= 0.

    Copytrade bots are skipped (their brokerage-migration holdings can't be rebuilt from a
    transaction replay — same rationale as the cash-drift audit).

    Query params:
      ?threshold=0.01    Relative drift to flag (fraction of expected; default 1%)
      ?abs_floor=1.00    Absolute $ floor so penny rounding never flags (default 1.00)
      ?days=N            Only audit snapshots from the last N days
      ?role=agent        Restrict to a single role
      ?limit_users=N     Audit only the first N users
      ?fix=true          Repair ONLY clean drift rows (fully priced, no missing/absurd):
                         stock_value=expected, total_value=expected+cash_proceeds.

    Response: per-user flagged snapshots + aggregate counts by issue type.
    """
    from models import db, User, Transaction, PortfolioSnapshot, MarketData
    from sqlalchemy import text as _sql_text
    from datetime import date as _date, timedelta as _td
    import bisect

    try:
        from mobile_api import _is_copytrade_bot
    except Exception:
        def _is_copytrade_bot(_u):
            return False

    try:
        rel_threshold = float(request.args.get('threshold', '0.01'))
    except (TypeError, ValueError):
        rel_threshold = 0.01
    try:
        abs_floor = float(request.args.get('abs_floor', '1.00'))
    except (TypeError, ValueError):
        abs_floor = 1.00
    role_filter = request.args.get('role')
    limit_users_param = request.args.get('limit_users')
    apply_fix = request.args.get('fix', 'false').lower() == 'true'
    days_param = request.args.get('days')
    since_date = None
    if days_param:
        try:
            since_date = _date.today() - _td(days=int(days_param))
        except (TypeError, ValueError):
            since_date = None

    def _lookup(price_index, ticker, d):
        """Return (price, kind) where kind is 'exact' | 'stale' | 'none'."""
        entry = price_index.get(ticker)
        if not entry:
            return (None, 'none')
        dates, closes = entry
        i = bisect.bisect_right(dates, d) - 1
        if i < 0:
            return (None, 'none')
        return (closes[i], 'exact' if dates[i] == d else 'stale')

    q = User.query.order_by(User.id.asc())
    if role_filter:
        q = q.filter(User.role == role_filter)
    users = q.all()
    if limit_users_param:
        try:
            users = users[: int(limit_users_param)]
        except (TypeError, ValueError):
            pass

    issues = []
    total_snapshots_checked = 0
    snapshots_with_drift = 0
    snapshots_with_missing = 0
    snapshots_with_stale_weekday = 0
    snapshots_with_absurd = 0
    skipped_null_stock_value = 0
    skipped_copytrade = 0
    fix_count = 0

    for user in users:
        if _is_copytrade_bot(user):
            skipped_copytrade += 1
            continue

        txns = Transaction.query.filter_by(user_id=user.id).order_by(
            Transaction.timestamp.asc()
        ).all()
        snap_q = PortfolioSnapshot.query.filter_by(user_id=user.id)
        if since_date is not None:
            snap_q = snap_q.filter(PortfolioSnapshot.date >= since_date)
        snaps = snap_q.order_by(PortfolioSnapshot.date.asc()).all()
        if not txns or not snaps:
            continue

        # Pre-load daily MarketData closes for every ticker this user ever held.
        tickers = sorted({(t.ticker or '').upper() for t in txns if t.ticker})
        price_index = {}
        if tickers:
            md_rows = MarketData.query.filter(
                MarketData.ticker.in_(tickers),
                MarketData.timestamp.is_(None),
            ).order_by(MarketData.ticker.asc(), MarketData.date.asc()).all()
            for md in md_rows:
                tk = md.ticker.upper()
                if tk not in price_index:
                    price_index[tk] = ([], [])
                price_index[tk][0].append(md.date)
                price_index[tk][1].append(float(md.close_price))

        # Walk snapshots ascending, advancing a transaction pointer to maintain
        # holdings as-of each snapshot date (same incremental technique as cash-drift).
        holdings = {}
        txn_idx = 0
        user_bad = []
        for snap in snaps:
            while txn_idx < len(txns):
                t = txns[txn_idx]
                t_ts = t.timestamp
                if t_ts is not None and t_ts.tzinfo:
                    t_ts = t_ts.replace(tzinfo=None)
                t_date = t_ts.date() if t_ts else None
                if t_date is None or t_date > snap.date:
                    break
                tk = (t.ticker or '').upper()
                qty = t.quantity or 0
                if t.transaction_type in ('buy', 'initial'):
                    holdings[tk] = holdings.get(tk, 0.0) + qty
                elif t.transaction_type == 'sell':
                    holdings[tk] = holdings.get(tk, 0.0) - qty
                txn_idx += 1

            total_snapshots_checked += 1
            if snap.stock_value is None:
                skipped_null_stock_value += 1
                continue

            is_weekend = snap.date.weekday() >= 5
            expected = 0.0
            missing = []
            stale_weekday = []
            absurd = []
            for tk, qty in holdings.items():
                if not qty or qty <= 1e-9:
                    continue
                price, kind = _lookup(price_index, tk, snap.date)
                if kind == 'none':
                    missing.append(tk)
                    continue
                if price is not None and price <= 0:
                    absurd.append({'ticker': tk, 'price': round(price, 4)})
                    continue
                if kind == 'stale' and not is_weekend:
                    stale_weekday.append(tk)
                    expected += qty * price  # included for context; row marked unvalidatable
                    continue
                expected += qty * price  # 'exact', or 'stale' on a weekend (carry-forward)

            actual = float(snap.stock_value)
            has_missing = len(missing) > 0
            has_stale = len(stale_weekday) > 0
            has_absurd = len(absurd) > 0
            validatable = not (has_missing or has_stale or has_absurd)

            drift = expected - actual
            denom = expected if expected > 0 else (actual if actual > 0 else 1.0)
            drift_pct = (drift / denom) * 100.0
            effective_abs = max(abs_floor, rel_threshold * expected)
            is_drift = validatable and abs(drift) >= effective_abs

            if not (is_drift or has_missing or has_stale or has_absurd):
                continue

            if is_drift:
                snapshots_with_drift += 1
            if has_missing:
                snapshots_with_missing += 1
            if has_stale:
                snapshots_with_stale_weekday += 1
            if has_absurd:
                snapshots_with_absurd += 1

            issue_tags = []
            if is_drift:
                issue_tags.append('drift')
            if has_missing:
                issue_tags.append('missing_price')
            if has_stale:
                issue_tags.append('stale_weekday_price')
            if has_absurd:
                issue_tags.append('absurd_price')

            holdings_count = sum(1 for v in holdings.values() if v and v > 1e-9)
            # SAFETY: never let ?fix zero out or overwrite a row we cannot positively
            # value. expected must be a real, fully-priced, NON-ZERO sum and the row must
            # actually hold something. This blocks the bot false-positive case where the
            # transaction replay yields 0 holdings -> expected 0 -> fix would erase value.
            clean_fixable = is_drift and validatable and expected > 0 and holdings_count > 0
            if apply_fix and clean_fixable:
                new_stock = round(expected, 2)
                db.session.execute(_sql_text("""
                    UPDATE portfolio_snapshot
                    SET stock_value = :sv,
                        total_value = :sv + COALESCE(cash_proceeds, 0)
                    WHERE id = :sid
                """), {'sv': new_stock, 'sid': snap.id})
                fix_count += 1

            user_bad.append({
                'date': snap.date.isoformat(),
                'snapshot_id': snap.id,
                'issues': issue_tags,
                'expected_stock_value': round(expected, 2),
                'actual_stock_value': round(actual, 2),
                'drift': round(drift, 2) if validatable else None,
                'drift_pct': round(drift_pct, 3) if validatable else None,
                'missing_price_tickers': missing or None,
                'stale_weekday_tickers': stale_weekday or None,
                'absurd_prices': absurd or None,
                'holdings_count': holdings_count,
                'fixed': bool(apply_fix and clean_fixable),
            })

        if user_bad:
            user_bad.sort(key=lambda x: -(abs(x['drift']) if x['drift'] is not None else 0.0))
            drift_rows = [b for b in user_bad if b['drift'] is not None]
            issues.append({
                'user_id': user.id,
                'username': user.username,
                'role': user.role,
                'bad_snapshot_count': len(user_bad),
                'max_abs_drift': round(max((abs(b['drift']) for b in drift_rows), default=0.0), 2),
                'first_bad_date': min(b['date'] for b in user_bad),
                'last_bad_date': max(b['date'] for b in user_bad),
                'sample_bad_snapshots': user_bad[:5],
                'all_bad_snapshots': user_bad if len(user_bad) <= 30 else None,
            })

    if apply_fix and fix_count:
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            return jsonify({
                'error': 'commit_failed',
                'message': str(e),
                'fix_count_attempted': fix_count,
            }), 500

    issues.sort(key=lambda x: -x['max_abs_drift'])
    return jsonify({
        'relative_threshold_pct': round(rel_threshold * 100, 3),
        'abs_floor': abs_floor,
        'days_scanned': days_param or 'all',
        'fix_applied': apply_fix,
        'fix_count': fix_count if apply_fix else 0,
        'users_scanned': len(users),
        'copytrade_bots_skipped': skipped_copytrade,
        'users_with_issues': len(issues),
        'total_snapshots_checked': total_snapshots_checked,
        'snapshots_with_drift': snapshots_with_drift,
        'snapshots_with_missing_prices': snapshots_with_missing,
        'snapshots_with_stale_weekday_prices': snapshots_with_stale_weekday,
        'snapshots_with_absurd_prices': snapshots_with_absurd,
        'snapshots_skipped_null_stock_value': skipped_null_stock_value,
        'issues': issues,
        'next_steps': (
            'DRIFT-only rows (no missing/stale/absurd) are safe to repair in place with '
            '?fix=true (stock_value=expected, total_value=expected+cash_proceeds). '
            'MISSING_PRICE / STALE_WEEKDAY rows need a MarketData daily-close backfill for the '
            'listed ticker/date pairs FIRST (calculate_portfolio_value silently skips unpriced '
            'holdings), then re-run ?fix=true. After any fix, DELETE the affected users from '
            'user_portfolio_chart_cache so charts regenerate from corrected snapshots.'
        ),
    })


@app.route('/admin/audit-bot-portfolio-integrity')
@admin_required
def admin_audit_bot_portfolio_integrity():
    """
    Bot (role='agent') portfolio integrity audit.

    Bots CANNOT be validated by the transaction-replay oracle used in
    /admin/audit-snapshot-stock-value: many were seeded via the legacy
    /admin/bot/add-stocks path which created Stock holdings WITHOUT Transaction
    rows (the add_stocks cost-basis bug), and their pre-creation PortfolioSnapshot
    history was synthetically backfilled. Replaying transactions therefore yields
    0 (or partial) holdings and produces meaningless '-100% drift'. This endpoint
    validates bots against the only ground truth they actually have -- the live
    Stock table -- plus internal snapshot consistency and time-series plausibility.

    Per bot, four INDEPENDENT, READ-ONLY checks:
      1. LEDGER COVERAGE: current Stock holdings vs transaction replay. Tickers held
         with zero replayed quantity (held but never transacted) are the add_stocks
         signature -> 'untracked_holdings'. Also reports per-ticker qty mismatches.
      2. LATEST SNAPSHOT vs LIVE HOLDINGS: price current Stock holdings at each
         ticker's most-recent MarketData close and compare to the newest snapshot's
         stock_value. Catches a corrupted value on the row users see on the
         leaderboard TODAY (the only date where Stock = ground truth).
      3. SNAPSHOT SERIES PLAUSIBILITY: flag (a) total_value != stock_value +
         cash_proceeds and (b) spike/dip-and-revert -- a day whose stock_value
         deviates > spike_pct from BOTH neighbours while the neighbours agree
         (chart-corruption signature, the daily analog of the intraday read-skew).
      4. SYNTHETIC HISTORY: count snapshots dated before the bot's first
         transaction (informational; explains the replay audit's -100% rows).

    No ?fix -- remediation (backdating an 'initial' ledger entry per untracked
    holding, or regenerating synthetic history) is a deliberate, separate operation.

    Params:
      ?holdings_threshold=0.10   rel tolerance for check #2 (default 10%; live prices
                                 may be a few days fresher than the snapshot)
      ?spike_pct=0.25            day-over-day deviation for check #3 (default 25%)
      ?limit_users=N
      ?include_copytrade=true    include copytrade bots (default: skipped)
    """
    from models import User, Stock, Transaction, PortfolioSnapshot, MarketData

    try:
        from mobile_api import _is_copytrade_bot
    except Exception:
        def _is_copytrade_bot(_u):
            return False

    try:
        holdings_threshold = float(request.args.get('holdings_threshold', '0.10'))
    except (TypeError, ValueError):
        holdings_threshold = 0.10
    try:
        spike_pct = float(request.args.get('spike_pct', '0.25'))
    except (TypeError, ValueError):
        spike_pct = 0.25
    include_copytrade = request.args.get('include_copytrade', 'false').lower() == 'true'
    limit_users_param = request.args.get('limit_users')

    bots = User.query.filter(User.role == 'agent').order_by(User.id.asc()).all()
    if limit_users_param:
        try:
            bots = bots[: int(limit_users_param)]
        except (TypeError, ValueError):
            pass

    results = []
    bots_scanned = 0
    bots_skipped_copytrade = 0
    bots_with_untracked = 0
    bots_with_latest_drift = 0
    bots_with_series_anomalies = 0
    total_untracked_holdings = 0
    total_spike_days = 0

    for bot in bots:
        is_copy = _is_copytrade_bot(bot)
        if is_copy and not include_copytrade:
            bots_skipped_copytrade += 1
            continue
        bots_scanned += 1

        # Current holdings (ground truth) from the Stock table.
        current = {}
        for s in Stock.query.filter_by(user_id=bot.id).all():
            if s.quantity and s.quantity > 1e-9:
                tk = (s.ticker or '').upper()
                current[tk] = current.get(tk, 0.0) + s.quantity

        # Replayed holdings from the transaction ledger.
        txns = Transaction.query.filter_by(user_id=bot.id).order_by(
            Transaction.timestamp.asc()
        ).all()
        replay = {}
        for t in txns:
            tk = (t.ticker or '').upper()
            qty = t.quantity or 0
            if t.transaction_type in ('buy', 'initial'):
                replay[tk] = replay.get(tk, 0.0) + qty
            elif t.transaction_type == 'sell':
                replay[tk] = replay.get(tk, 0.0) - qty

        # --- Check 1: ledger coverage ---
        untracked = sorted([
            tk for tk, q in current.items()
            if q > 1e-9 and replay.get(tk, 0.0) <= 1e-9
        ])
        qty_mismatches = []
        for tk, q in current.items():
            rq = replay.get(tk, 0.0)
            if rq > 1e-9 and abs(q - rq) > max(1.0, 0.01 * q):
                qty_mismatches.append({
                    'ticker': tk,
                    'current_qty': round(q, 4),
                    'replay_qty': round(rq, 4),
                })
        ledger_explains_pct = (
            round(100.0 * (1 - len(untracked) / len(current)), 1) if current else None
        )

        # Most-recent daily close per held ticker (for check 2).
        latest_close = {}
        held_tickers = sorted(current.keys())
        if held_tickers:
            md_rows = MarketData.query.filter(
                MarketData.ticker.in_(held_tickers),
                MarketData.timestamp.is_(None),
            ).order_by(MarketData.ticker.asc(), MarketData.date.asc()).all()
            for md in md_rows:
                latest_close[md.ticker.upper()] = float(md.close_price)

        snaps = PortfolioSnapshot.query.filter_by(user_id=bot.id).order_by(
            PortfolioSnapshot.date.asc()
        ).all()
        latest_snap = snaps[-1] if snaps else None

        # --- Check 2: latest snapshot vs live holdings ---
        latest_info = None
        if latest_snap is not None and current:
            live_val = 0.0
            unpriced = []
            for tk, q in current.items():
                price = latest_close.get(tk)
                if price is None or price <= 0:
                    unpriced.append(tk)
                    continue
                live_val += q * price
            stored = float(latest_snap.stock_value or 0.0)
            drift = stored - live_val
            denom = live_val if live_val > 0 else (stored if stored > 0 else 1.0)
            flagged = (not unpriced) and live_val > 0 and abs(drift) > max(
                1.0, holdings_threshold * live_val
            )
            latest_info = {
                'date': latest_snap.date.isoformat(),
                'stored_stock_value': round(stored, 2),
                'live_holdings_value': round(live_val, 2),
                'drift': round(drift, 2),
                'drift_pct': round(drift / denom * 100.0, 2),
                'unpriced_tickers': unpriced or None,
                'flagged': bool(flagged),
            }
            if flagged:
                bots_with_latest_drift += 1

        # --- Check 3: snapshot series plausibility ---
        value_mismatch_count = 0
        for s in snaps:
            tv = float(s.total_value or 0.0)
            stv = float(s.stock_value or 0.0)
            cp = float(s.cash_proceeds or 0.0)
            if abs(tv - (stv + cp)) > max(1.0, 0.005 * max(abs(tv), 1.0)):
                value_mismatch_count += 1
        sv = [(s.date, float(s.stock_value)) for s in snaps if s.stock_value is not None]
        spike_days = []
        for i in range(1, len(sv) - 1):
            _, v_prev = sv[i - 1]
            d_cur, v_cur = sv[i]
            _, v_next = sv[i + 1]
            if v_prev <= 0 or v_next <= 0:
                continue
            neighbours_agree = abs(v_prev - v_next) / max(v_prev, v_next) <= spike_pct
            dev_prev = abs(v_cur - v_prev) / v_prev
            dev_next = abs(v_cur - v_next) / v_next
            if neighbours_agree and dev_prev > spike_pct and dev_next > spike_pct:
                spike_days.append({
                    'date': d_cur.isoformat(),
                    'stock_value': round(v_cur, 2),
                    'prev': round(v_prev, 2),
                    'next': round(v_next, 2),
                    'direction': 'spike' if v_cur > v_prev else 'dip',
                })
        total_spike_days += len(spike_days)
        if value_mismatch_count or spike_days:
            bots_with_series_anomalies += 1

        # --- Check 4: synthetic history ---
        first_txn_date = None
        if txns:
            t0 = txns[0].timestamp
            if t0 is not None and t0.tzinfo:
                t0 = t0.replace(tzinfo=None)
            first_txn_date = t0.date() if t0 else None
        first_snap_date = snaps[0].date if snaps else None
        if first_txn_date is not None:
            synthetic_count = sum(1 for s in snaps if s.date < first_txn_date)
        else:
            synthetic_count = len(snaps)

        if untracked:
            bots_with_untracked += 1
            total_untracked_holdings += len(untracked)

        flags = []
        if untracked:
            flags.append('untracked_holdings')
        if qty_mismatches:
            flags.append('qty_mismatch')
        if latest_info and latest_info['flagged']:
            flags.append('latest_snapshot_drift')
        if value_mismatch_count:
            flags.append('total_value_mismatch')
        if spike_days:
            flags.append('stock_value_spike_revert')
        if synthetic_count:
            flags.append('synthetic_history')

        if not flags:
            continue

        results.append({
            'user_id': bot.id,
            'username': bot.username,
            'is_copytrade': is_copy,
            'flags': flags,
            'ledger': {
                'current_ticker_count': len(current),
                'untracked_holdings': untracked or None,
                'untracked_count': len(untracked),
                'qty_mismatches': qty_mismatches or None,
                'ledger_explains_pct': ledger_explains_pct,
            },
            'latest_snapshot': latest_info,
            'series': {
                'snapshot_count': len(snaps),
                'total_value_mismatch_count': value_mismatch_count,
                'spike_revert_days': spike_days[:10],
                'spike_revert_count': len(spike_days),
            },
            'synthetic_history': {
                'first_snapshot_date': first_snap_date.isoformat() if first_snap_date else None,
                'first_transaction_date': first_txn_date.isoformat() if first_txn_date else None,
                'pre_ledger_snapshot_count': synthetic_count,
            },
        })

    results.sort(
        key=lambda r: (r['ledger']['untracked_count'], r['series']['spike_revert_count']),
        reverse=True,
    )
    return jsonify({
        'holdings_threshold_pct': round(holdings_threshold * 100, 2),
        'spike_pct': round(spike_pct * 100, 2),
        'include_copytrade': include_copytrade,
        'bots_scanned': bots_scanned,
        'bots_skipped_copytrade': bots_skipped_copytrade,
        'bots_with_issues': len(results),
        'bots_with_untracked_holdings': bots_with_untracked,
        'bots_with_latest_snapshot_drift': bots_with_latest_drift,
        'bots_with_series_anomalies': bots_with_series_anomalies,
        'total_untracked_holdings': total_untracked_holdings,
        'total_spike_revert_days': total_spike_days,
        'issues': results,
        'interpretation': (
            'untracked_holdings = Stock rows with no Transaction history (legacy '
            '/admin/bot/add-stocks seeding bug) -> these bots cannot be validated by '
            'transaction replay and their cost basis / max_cash_deployed may be wrong. '
            'latest_snapshot_drift = the value users see TODAY disagrees with live Stock '
            'holdings priced at the latest close (real live-writer error -- investigate). '
            'stock_value_spike_revert = a daily snapshot deviates sharply from BOTH '
            'neighbours which agree (chart-corruption signature, same family as the '
            'intraday read-skew). synthetic_history = snapshots predating the first '
            'transaction were backfilled (expected for bots; explains the replay audit '
            '-100% rows). READ-ONLY: remediation is a separate, deliberate step.'
        ),
    })


@app.route('/admin/backfill-bot-untracked-holdings')
@admin_required
def admin_backfill_bot_untracked_holdings():
    """
    Remediate the `untracked_holdings` found by /admin/audit-bot-portfolio-integrity:
    bots seeded via the legacy /admin/bot/add-stocks path got Stock rows but NO
    Transaction, so transaction replay can't reconstruct them. This ONLY restores
    the missing ledger rows so the audit can replay-validate holdings; it does NOT
    change max_cash_deployed (see the big note below -- doing so double-counts).

    For every (bot, ticker) where current Stock qty exceeds replayed qty, this
    records the missing seed lot:
      missing_qty = current_qty - replay_qty
      seed_value  = missing_qty * Stock.purchase_price   (seeded cost basis)

    IMPORTANT - we DON'T route through process_transaction(). That path offsets
    a buy against current cash_proceeds, but the seed happened at t0 when
    cash_proceeds was 0; replaying it now (after later sells built up
    cash_proceeds) would wrongly consume that cash. Instead we just INSERT a
    Transaction(type='initial', backdated to the bot's first snapshot date,
    price_source='backfill_seed') so transaction-replay reproduces the holdings.

    *** THIS ENDPOINT DOES NOT TOUCH max_cash_deployed. ***
    (Session-10 incident: the original version did `max_cash_deployed += seed_value`,
    which DOUBLE-COUNTED the seed. These bots were seeded via set-cash + add-stocks,
    so max_cash_deployed was ALREADY set to the full seed value at creation -- it is
    NOT understated. Adding the seed again inflated the latest snapshot and produced
    a ~60% cliff on 1M/YTD; undone by /admin/revert-bot-untracked-backfill.) This
    endpoint now ONLY completes the ledger so the audit can replay-validate holdings;
    max_cash_deployed is left exactly as-is.

    READ-ONLY DRY-RUN by default. Params:
      ?commit=true              actually write (otherwise preview only)
      ?user_id=N                scope to a single bot (recommended first pass)
      ?include_copytrade=true   include copytrade bots (default: skipped)
    On commit, affected users are purged from user_portfolio_chart_cache so any
    max_cash_deployed-derived returns regenerate.
    """
    from models import db, User, Stock, Transaction, PortfolioSnapshot
    from sqlalchemy import text as _sql_text

    try:
        from mobile_api import _is_copytrade_bot
    except Exception:
        def _is_copytrade_bot(_u):
            return False

    commit = request.args.get('commit', 'false').lower() == 'true'
    include_copytrade = request.args.get('include_copytrade', 'false').lower() == 'true'
    user_id_param = request.args.get('user_id')

    q = User.query.filter(User.role == 'agent')
    if user_id_param:
        try:
            q = q.filter(User.id == int(user_id_param))
        except (TypeError, ValueError):
            return jsonify({'error': 'invalid user_id'}), 400
    bots = q.order_by(User.id.asc()).all()

    results = []
    bots_processed = 0
    bots_skipped_copytrade = 0
    bots_with_backfill = 0
    total_txns = 0
    total_capital_recovered = 0.0
    affected_user_ids = []

    for bot in bots:
        if _is_copytrade_bot(bot) and not include_copytrade:
            bots_skipped_copytrade += 1
            continue
        bots_processed += 1

        stocks = {}
        prices = {}
        for s in Stock.query.filter_by(user_id=bot.id).all():
            if s.quantity and s.quantity > 1e-9:
                tk = (s.ticker or '').upper()
                stocks[tk] = stocks.get(tk, 0.0) + s.quantity
                if s.purchase_price and s.purchase_price > 0:
                    prices[tk] = float(s.purchase_price)

        replay = {}
        for t in Transaction.query.filter_by(user_id=bot.id).all():
            tk = (t.ticker or '').upper()
            qty = t.quantity or 0
            if t.transaction_type in ('buy', 'initial'):
                replay[tk] = replay.get(tk, 0.0) + qty
            elif t.transaction_type == 'sell':
                replay[tk] = replay.get(tk, 0.0) - qty

        first_snap = PortfolioSnapshot.query.filter_by(user_id=bot.id).order_by(
            PortfolioSnapshot.date.asc()
        ).first()
        backfill_dt = (
            datetime.combine(first_snap.date, datetime.min.time())
            if first_snap else datetime.utcnow()
        )

        txns = []
        skipped = []
        capital_recovered = 0.0
        for tk, cur_qty in stocks.items():
            missing = cur_qty - replay.get(tk, 0.0)
            if missing <= 1e-6:
                continue
            price = prices.get(tk)
            if not price or price <= 0:
                skipped.append({'ticker': tk, 'missing_qty': round(missing, 6),
                                'reason': 'no_purchase_price'})
                continue
            missing = round(missing, 6)
            value = missing * price
            capital_recovered += value
            txns.append({'ticker': tk, 'quantity': missing, 'price': round(price, 4),
                         'value': round(value, 2), 'transaction_type': 'initial'})

        if not txns:
            continue

        bots_with_backfill += 1
        total_txns += len(txns)
        total_capital_recovered += capital_recovered
        affected_user_ids.append(bot.id)

        cur_max = float(bot.max_cash_deployed or 0.0)
        # max_cash_deployed is intentionally NOT changed (see docstring): set-cash
        # already counts the seed; adding it again double-counts. Reported unchanged.
        projected_max = cur_max

        if commit:
            for tr in txns:
                db.session.add(Transaction(
                    user_id=bot.id,
                    ticker=tr['ticker'],
                    quantity=tr['quantity'],
                    price=tr['price'],
                    transaction_type='initial',
                    timestamp=backfill_dt,
                    price_source='backfill_seed',
                ))
            # NOTE: deliberately DO NOT modify bot.max_cash_deployed here -- set-cash
            # already counted the full seed at creation; mutating it double-counts
            # (session-10 ~60% cliff). This endpoint only completes the ledger.

        results.append({
            'user_id': bot.id,
            'username': bot.username,
            'backfill_timestamp': backfill_dt.isoformat(),
            'current_max_cash_deployed': round(cur_max, 2),
            'projected_max_cash_deployed': round(projected_max, 2),
            'capital_recovered': round(capital_recovered, 2),
            'transactions': txns,
            'transaction_count': len(txns),
            'skipped': skipped or None,
        })

    if commit and affected_user_ids:
        try:
            db.session.execute(
                _sql_text("DELETE FROM user_portfolio_chart_cache WHERE user_id = ANY(:ids)"),
                {'ids': affected_user_ids},
            )
        except Exception as _e:
            logger.warning(f"backfill: chart-cache purge failed: {_e}")
        db.session.commit()

    return jsonify({
        'mode': 'commit' if commit else 'dry_run',
        'include_copytrade': include_copytrade,
        'bots_processed': bots_processed,
        'bots_skipped_copytrade': bots_skipped_copytrade,
        'bots_with_backfill': bots_with_backfill,
        'total_transactions': total_txns,
        'total_capital_recovered': round(total_capital_recovered, 2),
        'chart_cache_purged': bool(commit and affected_user_ids),
        'results': results,
        'next_steps': (
            'DRY-RUN: review transactions[] per bot, then re-run with ?commit=true '
            '(optionally ?user_id=N to do one bot first). This ONLY inserts the missing '
            'initial seed txns so transaction-replay reproduces holdings; it does NOT '
            'modify max_cash_deployed (set-cash already counts the seed -- changing it '
            'here double-counts, the session-10 ~60% cliff). After commit, re-run '
            '/admin/audit-bot-portfolio-integrity -> untracked_count should be 0.'
        ),
    })


@app.route('/admin/fix-bot-snapshot-maxcash')
@admin_required
def admin_fix_bot_snapshot_maxcash():
    """
    Repair the max_cash_deployed DISCONTINUITY introduced by
    /admin/backfill-bot-untracked-holdings.

    The backfill bumped user.max_cash_deployed and inserted backdated 'initial'
    seed transactions, but DID NOT update the historical PortfolioSnapshot rows.
    create_daily_snapshot() writes user.max_cash_deployed into each NEW snapshot,
    so the post-backfill snapshots (EOD yesterday / market-open today) got the
    high (correct) value while every historical snapshot kept the old (low) one.
    performance_calculator computes CF_net = last.max_cash_deployed -
    first.max_cash_deployed, so that step looks like a huge mid-period capital
    inflow that earned nothing -> Modified Dietz return collapses (the observed
    ~-60% cliff on these 6 bots).

    FIX: recompute each snapshot's max_cash_deployed by replaying the (now
    seed-inclusive) Transaction ledger up to that snapshot's date and SETTING
    max_cash_deployed to the running max as of that date. Uses the canonical
    cash_tracking replay (buy/initial deploy after consuming cash_proceeds; sell/
    dividend add to cash_proceeds). Idempotent + self-consistent: post-backfill
    snapshots are unchanged, historical ones get +seed, the discontinuity
    disappears, and returns revert to their correct pre-backfill values.

    Scope: bots (role='agent') that have backfill_seed transactions, OR a single
    ?user_id=N. READ-ONLY DRY-RUN by default; ?commit=true to write. Fixes BOTH
    daily and intraday snapshots. Purges chart cache on commit (re-run the
    market-close cron / leaderboard rebuild afterwards to regenerate caches).
    """
    from models import (db, User, Transaction, PortfolioSnapshot,
                        PortfolioSnapshotIntraday)
    from sqlalchemy import text as _sql_text

    # DEPRECATED (session 10): this replay-based fixer SETS each snapshot's
    # max_cash_deployed to the transaction-replay value, which is WRONG for
    # set-cash-seeded bots -- their true max is the set-cash value, NOT the ledger
    # replay (the ledger is intentionally incomplete). It flattened divi51 to its
    # seed value. Superseded by /admin/revert-bot-untracked-backfill (clamp + restore,
    # idempotent, with force_max recovery). Refuses to run unless explicitly forced.
    if request.args.get('allow_deprecated_replay_fix', 'false').lower() != 'true':
        return jsonify({
            'error': 'deprecated',
            'message': ('This endpoint is deprecated and unsafe for set-cash-seeded '
                        'bots: it sets max_cash_deployed to the transaction-replay '
                        'value, which is too low (it flattened divi51 to its seed). '
                        'Use /admin/revert-bot-untracked-backfill instead. To override '
                        'anyway, pass ?allow_deprecated_replay_fix=true.'),
        }), 410

    commit = request.args.get('commit', 'false').lower() == 'true'
    user_id_param = request.args.get('user_id')

    if user_id_param:
        try:
            affected_ids = {int(user_id_param)}
        except (TypeError, ValueError):
            return jsonify({'error': 'invalid user_id'}), 400
    else:
        rows = (db.session.query(Transaction.user_id)
                .filter(Transaction.price_source == 'backfill_seed')
                .distinct().all())
        affected_ids = {r[0] for r in rows}

    if not affected_ids:
        return jsonify({
            'mode': 'commit' if commit else 'dry_run',
            'message': 'No bots with backfill_seed transactions found',
            'results': [],
        })

    results = []
    affected_for_cache = []

    for uid in sorted(affected_ids):
        user = User.query.get(uid)
        if not user:
            continue
        txns = (Transaction.query.filter_by(user_id=uid)
                .order_by(Transaction.timestamp.asc()).all())
        if not txns:
            continue

        # Replay the ledger once, recording (date, running_max) after each txn.
        # running_max is monotonic non-decreasing, so the value after the last
        # txn with date <= D is exactly the max_cash_deployed as of date D.
        cash = 0.0
        mcd = 0.0
        timeline = []  # list of (date, mcd_after_txn), chronological
        seed_value = 0.0
        for t in txns:
            v = (t.quantity or 0) * (t.price or 0)
            tt = t.transaction_type
            if tt in ('buy', 'initial'):
                if cash >= v:
                    cash -= v
                else:
                    mcd += (v - cash)
                    cash = 0.0
            elif tt == 'sell':
                cash += v
            elif tt == 'dividend':
                cash += v
            d = t.timestamp.date() if t.timestamp else None
            timeline.append((d, mcd))
            if t.price_source == 'backfill_seed':
                seed_value += v

        def _mcd_as_of(target_date):
            best = 0.0
            for d, m in timeline:
                if d is not None and d <= target_date:
                    best = m
                else:
                    break
            return best

        # Daily snapshots
        daily = (PortfolioSnapshot.query.filter_by(user_id=uid)
                 .order_by(PortfolioSnapshot.date.asc()).all())
        changes = []
        for s in daily:
            correct = round(_mcd_as_of(s.date), 2)
            old = round(float(s.max_cash_deployed or 0.0), 2)
            if abs(correct - old) > 0.01:
                changes.append({'date': s.date.isoformat(),
                                'old_max': old, 'new_max': correct})
                if commit:
                    s.max_cash_deployed = correct

        # Intraday snapshots (1D/5D charts)
        intraday = PortfolioSnapshotIntraday.query.filter_by(user_id=uid).all()
        intraday_changed = 0
        for s in intraday:
            sd = s.timestamp.date() if s.timestamp else None
            if sd is None:
                continue
            correct = round(_mcd_as_of(sd), 2)
            old = round(float(s.max_cash_deployed or 0.0), 2)
            if abs(correct - old) > 0.01:
                intraday_changed += 1
                if commit:
                    s.max_cash_deployed = correct

        if changes or intraday_changed:
            affected_for_cache.append(uid)

        results.append({
            'user_id': uid,
            'username': user.username,
            'seed_value': round(seed_value, 2),
            'user_max_cash_deployed': round(float(user.max_cash_deployed or 0), 2),
            'daily_snapshots': len(daily),
            'daily_changed': len(changes),
            'intraday_changed': intraday_changed,
            'first_change': changes[0] if changes else None,
            'last_change': changes[-1] if changes else None,
        })

    if commit and affected_for_cache:
        try:
            db.session.execute(
                _sql_text("DELETE FROM user_portfolio_chart_cache WHERE user_id = ANY(:ids)"),
                {'ids': affected_for_cache},
            )
        except Exception as _e:
            logger.warning(f"maxcash-fix: chart-cache purge failed: {_e}")
        db.session.commit()

    return jsonify({
        'mode': 'commit' if commit else 'dry_run',
        'affected_bots': len(results),
        'chart_cache_purged': bool(commit and affected_for_cache),
        'results': results,
        'next_steps': (
            'DRY-RUN: per bot, daily_changed should equal (daily_snapshots minus '
            'the 1-2 post-backfill snapshots already at the correct value), and '
            'first_change.old_max + seed_value == first_change.new_max. Then re-run '
            'with ?commit=true (optionally ?user_id=N first). After commit, trigger '
            '/api/cron/market-close (or the leaderboard rebuild) so LeaderboardCache '
            'regenerates, and verify the 1M/YTD charts no longer show the ~60% cliff.'
        ),
    })


@app.route('/admin/revert-bot-untracked-backfill')
@admin_required
def admin_revert_bot_untracked_backfill():
    """
    REVERT the untracked-holdings backfill. Premise was wrong: these bots were
    seeded via set-cash + add-stocks, so max_cash_deployed was set directly and
    was ALREADY correct -- the missing transactions were expected, not an
    understatement. The backfill inflated user.max_cash_deployed by seed_value
    and the post-backfill snapshots (+ EOD cron) picked up the inflated value,
    creating the discontinuity. (My replay fix made it worse on divi51 by
    flattening every snapshot to seed_value.)

    target_max = current user.max_cash_deployed - seed_value (the pre-backfill,
    correct peak). Per snapshot (daily + intraday):
      - if stored == seed_value (the divi51 corruption signature) and < target:
            set = target_max          # un-flatten the snapshots I overwrote
      - else: set = min(stored, target_max)   # clamp inflated, keep genuine history
    Then reset user.max_cash_deployed = target_max.

    The 'initial' backfill_seed transactions are KEPT by default -- they are
    legitimate entry-buys (a seed IS a buy: the bot purchasing its starting
    position), so they belong in the ledger. Only their DOUBLE-COUNT in
    max_cash_deployed is undone (set-cash already counted the seed once).
    Pass ?delete_seed_txns=true to remove them instead.

    DRY-RUN by default; ?commit=true to write; ?user_id=N to scope. Purges chart
    cache on commit (re-run market-close cron after to rebuild leaderboard).
    """
    from models import (db, User, Transaction, PortfolioSnapshot,
                        PortfolioSnapshotIntraday)
    from sqlalchemy import text as _sql_text

    commit = request.args.get('commit', 'false').lower() == 'true'
    delete_seed = request.args.get('delete_seed_txns', 'false').lower() == 'true'
    user_id_param = request.args.get('user_id')
    force_max_param = request.args.get('force_max')

    if force_max_param is not None:
        if not user_id_param:
            return jsonify({'error': 'force_max requires user_id'}), 400
        try:
            force_max_val = round(float(force_max_param), 2)
        except (TypeError, ValueError):
            return jsonify({'error': 'invalid force_max'}), 400
    else:
        force_max_val = None

    if user_id_param:
        try:
            ids = {int(user_id_param)}
        except (TypeError, ValueError):
            return jsonify({'error': 'invalid user_id'}), 400
    else:
        rows = (db.session.query(Transaction.user_id)
                .filter(Transaction.price_source == 'backfill_seed')
                .distinct().all())
        ids = {r[0] for r in rows}

    if not ids:
        return jsonify({'mode': 'commit' if commit else 'dry_run',
                        'message': 'No bots with backfill_seed transactions',
                        'results': []})

    results = []
    cache_ids = []
    for uid in sorted(ids):
        user = User.query.get(uid)
        if not user:
            continue
        seed_txns = (Transaction.query.filter_by(
            user_id=uid, price_source='backfill_seed').all())
        seed_value = round(sum((t.quantity or 0) * (t.price or 0)
                               for t in seed_txns), 2)
        cur_max = round(float(user.max_cash_deployed or 0), 2)

        if force_max_val is not None:
            # Explicit recovery: set user.max AND every snapshot flat to this
            # value. Used to repair a bot whose snapshot history was lost/
            # over-written (e.g. divi51, which had the non-idempotent revert
            # applied twice and is now flat at the wrong level).
            target_max = force_max_val
            def _fix(stored):
                return target_max
        else:
            target_max = round(cur_max - seed_value, 2)
            # IDEMPOTENCY GUARD: target_max = cur_max - seed_value only holds the
            # FIRST time (when cur_max is the inflated post-backfill value). After
            # a successful revert cur_max == target, so re-running would subtract
            # the seed AGAIN. Detect a genuine, un-reverted double-count by
            # checking that (inflated cur_max - genuine historical peak) == seed.
            daily_maxes = [round(float(s.max_cash_deployed or 0), 2)
                           for s in PortfolioSnapshot.query.filter_by(user_id=uid).all()]
            genuine = [m for m in daily_maxes if m < cur_max - 0.01]
            genuine_peak = max(genuine) if genuine else None
            if genuine_peak is None or abs((cur_max - genuine_peak) - seed_value) > 1.0:
                results.append({
                    'user_id': uid, 'username': user.username,
                    'seed_value': seed_value, 'current_user_max': cur_max,
                    'target_max': cur_max, 'seed_txns': len(seed_txns),
                    'seed_txns_deleted': 0, 'daily_changed': 0,
                    'intraday_changed': 0,
                    'skipped': 'already_reverted_or_no_double_count',
                })
                continue
            def _fix(stored):
                stored = round(float(stored or 0), 2)
                if abs(stored - seed_value) < 0.01 and stored < target_max - 0.01:
                    return target_max
                return min(stored, target_max)

        daily = PortfolioSnapshot.query.filter_by(user_id=uid).all()
        d_changed = 0
        for s in daily:
            nv = _fix(s.max_cash_deployed)
            if abs(nv - round(float(s.max_cash_deployed or 0), 2)) > 0.01:
                d_changed += 1
                if commit:
                    s.max_cash_deployed = nv
        intraday = PortfolioSnapshotIntraday.query.filter_by(user_id=uid).all()
        i_changed = 0
        for s in intraday:
            nv = _fix(s.max_cash_deployed)
            if abs(nv - round(float(s.max_cash_deployed or 0), 2)) > 0.01:
                i_changed += 1
                if commit:
                    s.max_cash_deployed = nv

        if commit:
            user.max_cash_deployed = target_max
            if delete_seed:
                for t in seed_txns:
                    db.session.delete(t)
            cache_ids.append(uid)

        results.append({
            'user_id': uid, 'username': user.username,
            'seed_value': seed_value, 'current_user_max': cur_max,
            'target_max': target_max,
            'seed_txns': len(seed_txns),
            'seed_txns_deleted': (len(seed_txns) if (commit and delete_seed) else 0),
            'daily_changed': d_changed, 'intraday_changed': i_changed,
        })

    if commit and cache_ids:
        try:
            db.session.execute(_sql_text(
                "DELETE FROM user_portfolio_chart_cache WHERE user_id = ANY(:ids)"),
                {'ids': cache_ids})
        except Exception as _e:
            logger.warning(f"revert: chart-cache purge failed: {_e}")
        db.session.commit()

    return jsonify({
        'mode': 'commit' if commit else 'dry_run',
        'affected_bots': len(results), 'results': results,
        'next_steps': ('DRY-RUN: target_max = current_user_max - seed_value is the '
                       'correct pre-backfill peak (seed counted once as deployed '
                       'capital). The initial seed transactions are KEPT (they are '
                       'entry-buys); pass ?delete_seed_txns=true to remove them. Re-run '
                       '?commit=true (optionally ?user_id=9 first to undo the divi51 '
                       'corruption). After commit, trigger /api/cron/market-close to '
                       'rebuild leaderboard caches, then confirm the ~60% cliff is gone.'),
    })


def _marketdata_coverage_universe(days):
    """Shared helper for the MarketData coverage audit + backfill.

    Returns (window_start, tickers, md_dates_by_ticker, dpb_dates_by_ticker,
    dpb_close_by_ticker, calendar) where:
      - tickers           = every ticker ever held or transacted (uppercased)
      - md_dates_by_ticker= {ticker: set(date)} of existing DAILY MarketData rows
                            (timestamp IS NULL) in the window
      - dpb_dates_by_ticker, dpb_close_by_ticker = DailyPriceBar coverage / closes
      - calendar          = canonical trading-day set (SPY's DailyPriceBar dates,
                            falling back to the union of all dpb dates)
    MarketData (the table get_historical_price reads to value snapshots) is only
    populated on-demand, so it's sparse; DailyPriceBar is refreshed daily for the
    whole bot universe, so it's the natural source to fill MarketData gaps.
    """
    from models import MarketData, DailyPriceBar, Stock, Transaction
    from collections import defaultdict

    window_start = date.today() - timedelta(days=days)

    tickers = set()
    for (tk,) in db.session.query(Stock.ticker).distinct().all():
        if tk:
            tickers.add(tk.upper())
    for (tk,) in db.session.query(Transaction.ticker).distinct().all():
        if tk:
            tickers.add(tk.upper())
    # Benchmark tickers are valued elsewhere and aren't user holdings.
    tickers -= {'SPY_SP500', 'SPY_INTRADAY', 'SPY_SP500_INTRADAY'}

    md_dates_by_ticker = defaultdict(set)
    for tk, d in (
        db.session.query(MarketData.ticker, MarketData.date)
        .filter(MarketData.date >= window_start, MarketData.timestamp.is_(None))
        .all()
    ):
        if tk:
            md_dates_by_ticker[tk.upper()].add(d)

    dpb_dates_by_ticker = defaultdict(set)
    dpb_close_by_ticker = defaultdict(dict)
    for tk, d, close in (
        db.session.query(DailyPriceBar.ticker, DailyPriceBar.date, DailyPriceBar.close)
        .filter(DailyPriceBar.date >= window_start)
        .all()
    ):
        if tk and close is not None and close > 0:
            u = tk.upper()
            dpb_dates_by_ticker[u].add(d)
            dpb_close_by_ticker[u][d] = float(close)

    calendar = set(dpb_dates_by_ticker.get('SPY', set()))
    if not calendar:
        for ds in dpb_dates_by_ticker.values():
            calendar |= ds

    return (window_start, tickers, md_dates_by_ticker,
            dpb_dates_by_ticker, dpb_close_by_ticker, calendar)


@app.route('/admin/audit-marketdata-coverage')
@admin_required
def admin_audit_marketdata_coverage():
    """
    READ-ONLY. Map the daily-close coverage gap in the `market_data` table
    (the source get_historical_price uses to value/validate snapshots).

    For every ticker ever held or transacted, compare existing daily MarketData
    rows against the DailyPriceBar OHLCV cache (refreshed daily for the bot
    universe) and the canonical trading calendar (SPY's DailyPriceBar dates):
      - fillable_from_dpb : dates DailyPriceBar has but MarketData lacks
                            (CHEAPLY backfillable -- same AlphaVantage source).
      - missing_everywhere: trading days neither table has (would need a fresh
                            AlphaVantage fetch; usually tickers outside the
                            ~145-name bot universe).
      - not_in_dpb        : held ticker with ZERO DailyPriceBar rows (outside the
                            universe -> the daily-bars cron never fetches it).

    Params: ?days=N (window back from today, default 120) ?ticker=XXX (scope one).
    """
    days = request.args.get('days', '120')
    try:
        days = max(1, min(int(days), 400))
    except (TypeError, ValueError):
        days = 120
    ticker_filter = (request.args.get('ticker') or '').upper() or None

    (window_start, tickers, md_dates_by_ticker,
     dpb_dates_by_ticker, dpb_close_by_ticker, calendar) = _marketdata_coverage_universe(days)

    if ticker_filter:
        tickers = {t for t in tickers if t == ticker_filter}

    results = []
    total_fillable = 0
    total_missing_everywhere = 0
    tickers_needing_av = []

    for tk in sorted(tickers):
        md = md_dates_by_ticker.get(tk, set())
        dpb = dpb_dates_by_ticker.get(tk, set())
        fillable = sorted(dpb - md)
        missing_everywhere = sorted(calendar - md - dpb) if calendar else []
        in_dpb = len(dpb) > 0

        if not in_dpb:
            tickers_needing_av.append(tk)
        total_fillable += len(fillable)
        total_missing_everywhere += len(missing_everywhere)

        if not fillable and not missing_everywhere and in_dpb:
            continue  # fully covered -- skip from the detail list

        results.append({
            'ticker': tk,
            'md_days': len(md),
            'dpb_days': len(dpb),
            'in_dpb_universe': in_dpb,
            'fillable_from_dpb': len(fillable),
            'fillable_sample': [d.isoformat() for d in fillable[:5]],
            'missing_everywhere': len(missing_everywhere),
            'missing_sample': [d.isoformat() for d in missing_everywhere[:5]],
        })

    results.sort(key=lambda r: (-r['fillable_from_dpb'], -r['missing_everywhere']))

    return jsonify({
        'window_start': window_start.isoformat(),
        'window_days': days,
        'calendar_trading_days': len(calendar),
        'tickers_examined': len(tickers),
        'tickers_with_gaps': len(results),
        'total_fillable_from_dpb_rows': total_fillable,
        'total_missing_everywhere_rows': total_missing_everywhere,
        'tickers_needing_av_fetch': sorted(tickers_needing_av),
        'results': results,
        'next_steps': (
            'total_fillable_from_dpb_rows are CHEAPLY backfillable (no API calls) '
            'via /admin/backfill-marketdata-from-dailybars (dry-run, then ?commit=true). '
            'tickers_needing_av_fetch are held names outside the bot universe -- they '
            'need a fresh AlphaVantage TIME_SERIES_DAILY pull (get_historical_price '
            'force_fetch). NOTE: filling market_data improves AUDIT fidelity and any '
            'FUTURE snapshot recompute -- it does NOT retroactively change already-'
            'stored PortfolioSnapshot rows.'
        ),
    })


@app.route('/admin/backfill-marketdata-from-dailybars')
@admin_required
def admin_backfill_marketdata_from_dailybars():
    """
    Fill daily-close gaps in `market_data` by copying DailyPriceBar.close into
    MarketData(ticker, date, close_price, timestamp=None) for every (ticker,date)
    DailyPriceBar has but MarketData lacks. Same upstream source (AlphaVantage),
    so values are consistent; no external API calls; idempotent (a second run
    sees the now-present dates and inserts nothing).

    READ-ONLY DRY-RUN by default. Params:
      ?commit=true    actually insert the rows
      ?days=N         window back from today (default 120; DailyPriceBar only
                      holds ~100 trading days, so older gaps aren't fillable here)
      ?ticker=XXX     scope to a single ticker

    Does NOT change existing PortfolioSnapshot values (those are recomputed
    separately); it makes the snapshot stock-value audit authoritative and
    improves any future recompute.
    """
    from models import MarketData

    commit = request.args.get('commit', 'false').lower() == 'true'
    days = request.args.get('days', '120')
    try:
        days = max(1, min(int(days), 400))
    except (TypeError, ValueError):
        days = 120
    ticker_filter = (request.args.get('ticker') or '').upper() or None

    (window_start, tickers, md_dates_by_ticker,
     dpb_dates_by_ticker, dpb_close_by_ticker, _calendar) = _marketdata_coverage_universe(days)

    if ticker_filter:
        tickers = {t for t in tickers if t == ticker_filter}

    per_ticker = []
    total_inserted = 0
    now = datetime.utcnow()

    for tk in sorted(tickers):
        md = md_dates_by_ticker.get(tk, set())
        dpb = dpb_dates_by_ticker.get(tk, set())
        fillable = sorted(dpb - md)
        if not fillable:
            continue

        if commit:
            for d in fillable:
                db.session.add(MarketData(
                    ticker=tk,
                    date=d,
                    timestamp=None,
                    close_price=dpb_close_by_ticker[tk][d],
                    created_at=now,
                ))

        total_inserted += len(fillable)
        per_ticker.append({
            'ticker': tk,
            'rows': len(fillable),
            'date_range': [fillable[0].isoformat(), fillable[-1].isoformat()],
        })

    if commit and total_inserted:
        db.session.commit()

    per_ticker.sort(key=lambda r: -r['rows'])

    return jsonify({
        'mode': 'commit' if commit else 'dry_run',
        'window_start': window_start.isoformat(),
        'window_days': days,
        'tickers_filled': len(per_ticker),
        'total_rows': total_inserted,
        'per_ticker': per_ticker,
        'next_steps': (
            ('Inserted {n} daily-close rows into market_data. '.format(n=total_inserted)
             if commit else
             'DRY-RUN: {n} rows would be inserted. Re-run with ?commit=true to apply. '.format(n=total_inserted))
            + 'Then re-run /admin/audit-marketdata-coverage (fillable should drop to 0) '
            'and /admin/audit-snapshot-stock-value (stale_weekday_price flags should '
            'clear). Held tickers still outside DailyPriceBar need an AlphaVantage fetch.'
        ),
    })


@app.route('/admin/backfill-marketdata-av-fetch')
@admin_required
def admin_backfill_marketdata_av_fetch():
    """
    Fill the daily-close gaps that DailyPriceBar CAN'T cover -- held/transacted
    tickers outside the ~145-name bot universe (DailyPriceBar has zero rows for
    them) plus the odd not-yet-fetched recent day. For each such ticker we call
    PortfolioPerformanceCalculator.get_historical_price(force_fetch=True) ONCE:
    AlphaVantage TIME_SERIES_DAILY returns ~100 days and the method caches every
    new day into market_data (self-commits per ticker), so one call closes the
    whole recent gap for that ticker.

    READ-ONLY DRY-RUN by default (lists targets, makes NO API calls). Params:
      ?commit=true     actually fetch (rate-limited AlphaVantage calls)
      ?days=N          window back from today (default 120)
      ?ticker=XXX      scope to a single ticker
      ?limit=N         max tickers to fetch this run (default 50)
      ?max_seconds=S   wall-clock budget before stopping early (default 45,
                       under the 60s function limit)

    Idempotent + resumable: each ticker's missing set is recomputed live, so a
    fetched ticker drops out next run. If remaining_tickers_this_run is non-empty
    (budget/limit hit), just re-run with ?commit=true to continue.
    """
    import time as _time
    from collections import defaultdict
    from models import MarketData
    from portfolio_performance import PortfolioPerformanceCalculator

    commit = request.args.get('commit', 'false').lower() == 'true'
    days = request.args.get('days', '120')
    try:
        days = max(1, min(int(days), 400))
    except (TypeError, ValueError):
        days = 120
    ticker_filter = (request.args.get('ticker') or '').upper() or None
    try:
        limit = max(1, min(int(request.args.get('limit', '50')), 145))
    except (TypeError, ValueError):
        limit = 50
    try:
        max_seconds = max(5.0, min(float(request.args.get('max_seconds', '45')), 55.0))
    except (TypeError, ValueError):
        max_seconds = 45.0

    (window_start, tickers, md_dates_by_ticker,
     dpb_dates_by_ticker, _dpb_close, calendar) = _marketdata_coverage_universe(days)

    if ticker_filter:
        tickers = {t for t in tickers if t == ticker_filter}

    targets = []
    for tk in sorted(tickers):
        md = md_dates_by_ticker.get(tk, set())
        dpb = dpb_dates_by_ticker.get(tk, set())
        missing = sorted(calendar - md - dpb)
        if missing:
            targets.append({
                'ticker': tk,
                'missing_before': len(missing),
                'missing_dates': missing,
                'in_dpb_universe': len(dpb) > 0,
            })
    targets.sort(key=lambda r: -r['missing_before'])

    if not commit:
        return jsonify({
            'mode': 'dry_run',
            'window_start': window_start.isoformat(),
            'window_days': days,
            'target_ticker_count': len(targets),
            'total_missing_rows': sum(t['missing_before'] for t in targets),
            'estimated_av_calls_this_run': min(len(targets), limit),
            'limit': limit,
            'targets': [{
                'ticker': t['ticker'],
                'missing_rows': t['missing_before'],
                'in_dpb_universe': t['in_dpb_universe'],
                'latest_missing': t['missing_dates'][-1].isoformat(),
            } for t in targets],
            'next_steps': (
                'DRY-RUN: no API calls made. Re-run with ?commit=true to fetch '
                '(force_fetch caches ~100 days/ticker into market_data). limit + '
                'max_seconds cap each run under the 60s function budget; re-run to '
                'continue (idempotent). Then re-run /admin/audit-marketdata-coverage.'
            ),
        })

    calculator = PortfolioPerformanceCalculator()
    if not getattr(calculator, 'alpha_vantage_api_key', None):
        return jsonify({'error': 'ALPHA_VANTAGE_API_KEY not set -- cannot fetch'}), 400

    missing_by_ticker = {t['ticker']: set(t['missing_dates']) for t in targets}
    start_ts = _time.time()
    succeeded = []
    failed = []
    skipped = []
    n_done = 0

    for t in targets:
        tk = t['ticker']
        if n_done >= limit or (_time.time() - start_ts) > max_seconds:
            skipped.append(tk)
            continue
        try:
            target_date = max(missing_by_ticker[tk])
            price = calculator.get_historical_price(tk, target_date, force_fetch=True)
            if price and price > 0:
                succeeded.append(tk)
            else:
                failed.append({'ticker': tk, 'reason': 'no_data_returned'})
        except Exception as e:
            failed.append({'ticker': tk, 'reason': str(e)[:200]})
        n_done += 1
        _time.sleep(0.1)

    # Measure how many of the originally-missing dates are now present.
    fetched = succeeded + [f['ticker'] for f in failed]
    rows_filled = 0
    rows_still_missing = 0
    if fetched:
        md_now = defaultdict(set)
        for tk2, d in (
            db.session.query(MarketData.ticker, MarketData.date)
            .filter(MarketData.ticker.in_(fetched),
                    MarketData.date >= window_start,
                    MarketData.timestamp.is_(None))
            .all()
        ):
            if tk2:
                md_now[tk2.upper()].add(d)
        for tk2 in fetched:
            before = missing_by_ticker.get(tk2, set())
            now_have = md_now.get(tk2, set())
            rows_filled += len(before & now_have)
            rows_still_missing += len(before - now_have)

    return jsonify({
        'mode': 'commit',
        'window_start': window_start.isoformat(),
        'tickers_fetched': n_done,
        'tickers_succeeded': len(succeeded),
        'rows_filled': rows_filled,
        'rows_still_missing': rows_still_missing,
        'failed': failed,
        'remaining_tickers_this_run': skipped,
        'elapsed_seconds': round(_time.time() - start_ts, 1),
        'next_steps': (
            'Fetched {n} tickers ({s} ok). '.format(n=n_done, s=len(succeeded))
            + ('{r} tickers hit the limit/time budget -- re-run with ?commit=true to '
               'continue. '.format(r=len(skipped)) if skipped else '')
            + 'rows_still_missing are dates AlphaVantage itself lacks (e.g. delisted '
            'tickers or symbol-format mismatches like BRK.B). Then re-run '
            '/admin/audit-marketdata-coverage to confirm.'
        ),
    })


@app.route('/admin/audit-snapshot-max-cash-drift')
@admin_required
def admin_audit_snapshot_max_cash_drift():
    """
    Same idea as audit-snapshot-cash-drift but for max_cash_deployed.
    Each snapshot's max_cash_deployed should equal seeded_baseline + replay_max
    at end of snapshot date, where seeded_baseline is the gap between the
    user's first snapshot's max_cash_deployed and what transactions can explain
    up to that date (i.e. the imported / pre-history capital).

    Query params: same as audit-snapshot-cash-drift.
    """
    from models import db, User, Transaction, PortfolioSnapshot, Stock
    from sqlalchemy import text as _sql_text
    from datetime import time as _dt_time, timedelta as _td
    try:
        from mobile_api import _is_copytrade_bot
    except Exception:
        def _is_copytrade_bot(_u):
            return False

    # Bucket trades by UTC calendar date to match the snapshot writer
    # (func.date(Transaction.timestamp) <= target_date). See cron_snapshot_audit
    # for why the old 20:05-UTC cutoff produced late-wave false positives.
    def _eff_date(ts):
        if ts is None:
            return None
        return (ts.replace(tzinfo=None) if ts.tzinfo else ts).date()

    # Ambiguous-trade tolerance: post-market-close trades (>= 20:00 UTC) on date D
    # may or may not be in that day's EOD snapshot; tolerate their summed |value|.
    _amb_start = _dt_time(20, 0)
    _amb_end = _dt_time(23, 59, 59)

    try:
        threshold = float(request.args.get('threshold', '1.00'))
    except (TypeError, ValueError):
        threshold = 1.00
    role_filter = request.args.get('role')
    limit_users_param = request.args.get('limit_users')
    apply_fix = request.args.get('fix', 'false').lower() == 'true'

    q = User.query.order_by(User.id.asc())
    if role_filter:
        q = q.filter(User.role == role_filter)
    users = q.all()
    if limit_users_param:
        try:
            users = users[: int(limit_users_param)]
        except (TypeError, ValueError):
            pass

    issues = []
    total_snapshots_checked = 0
    total_bad_snapshots = 0
    fix_count = 0
    skipped_copytrade = 0

    for user in users:
        # Copytrade bots derive cash/holdings from brokerage-screenshot migrations
        # (price_source='phase_c_migration') that a transaction replay cannot
        # reproduce — they always show false-positive drift. Skip them so a blanket
        # ?fix=true can never overwrite their brokerage-matched cash.
        if _is_copytrade_bot(user):
            skipped_copytrade += 1
            continue
        txns = Transaction.query.filter_by(user_id=user.id).order_by(
            Transaction.timestamp.asc()
        ).all()
        snaps = PortfolioSnapshot.query.filter_by(user_id=user.id).order_by(
            PortfolioSnapshot.date.asc()
        ).all()
        if not snaps or not txns:
            continue

        # Pre-compute per-date ambiguous-trade tolerance for this user
        amb_tol_by_date = {}
        for txn in txns:
            if txn.timestamp is None:
                continue
            ts_n = txn.timestamp.replace(tzinfo=None) if txn.timestamp.tzinfo else txn.timestamp
            if _amb_start <= ts_n.time() < _amb_end:
                v = abs(float((txn.quantity or 0) * (txn.price or 0)))
                d = ts_n.date()
                amb_tol_by_date[d] = amb_tol_by_date.get(d, 0.0) + v

        # Determine seeded_baseline: gap between first snapshot max_cash and
        # what txns through first_snap.date can explain (bucketed by UTC calendar
        # date, matching the snapshot writer's func.date(timestamp) filter).
        first_snap = snaps[0]
        rmf = 0.0
        rcf = 0.0
        for txn in txns:
            t_date = _eff_date(txn.timestamp)
            if t_date is None or t_date > first_snap.date:
                break
            v = (txn.quantity or 0) * (txn.price or 0)
            if txn.transaction_type in ('buy', 'initial'):
                if rcf >= v:
                    rcf -= v
                else:
                    rmf += v - rcf
                    rcf = 0
            elif txn.transaction_type in ('sell', 'dividend'):
                rcf += v
        seeded_baseline = max(0.0, round(float(first_snap.max_cash_deployed or 0) - rmf, 2))

        # Replay through all snapshots, comparing snap.max_cash_deployed
        replay_cash = 0.0
        replay_max = 0.0
        txn_idx = 0

        user_bad = []
        for snap in snaps:
            while txn_idx < len(txns):
                txn = txns[txn_idx]
                t_date = _eff_date(txn.timestamp)
                if t_date is None or t_date > snap.date:
                    break
                v = (txn.quantity or 0) * (txn.price or 0)
                if txn.transaction_type in ('buy', 'initial'):
                    if replay_cash >= v:
                        replay_cash -= v
                    else:
                        replay_max += v - replay_cash
                        replay_cash = 0
                elif txn.transaction_type in ('sell', 'dividend'):
                    replay_cash += v
                txn_idx += 1

            actual_max = round(float(snap.max_cash_deployed or 0), 2)
            expected_max = round(seeded_baseline + replay_max, 2)
            max_drift = round(expected_max - actual_max, 2)

            total_snapshots_checked += 1

            # Apply ambiguous-trade tolerance for this snapshot's date
            amb_tol = amb_tol_by_date.get(snap.date, 0.0)
            effective_threshold = threshold + amb_tol

            if abs(max_drift) >= effective_threshold:
                total_bad_snapshots += 1
                user_bad.append({
                    'date': snap.date.isoformat(),
                    'actual_max_cash_deployed': actual_max,
                    'expected_max_cash_deployed': expected_max,
                    'drift': max_drift,
                    'seeded_baseline': seeded_baseline,
                    'ambiguous_tolerance': round(amb_tol, 2) if amb_tol > 0 else None,
                })

                if apply_fix:
                    db.session.execute(_sql_text("""
                        UPDATE portfolio_snapshot
                        SET max_cash_deployed = :mx
                        WHERE id = :sid
                    """), {'mx': expected_max, 'sid': snap.id})
                    fix_count += 1

        if user_bad:
            issues.append({
                'user_id': user.id,
                'username': user.username,
                'role': user.role,
                'seeded_baseline': seeded_baseline,
                'bad_snapshot_count': len(user_bad),
                'first_bad_date': user_bad[0]['date'],
                'last_bad_date': user_bad[-1]['date'],
                'max_abs_drift': round(max(abs(b['drift']) for b in user_bad), 2),
                'sample_bad_snapshots': user_bad[:5],
            })

    if apply_fix:
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            return jsonify({
                'error': 'commit_failed',
                'message': str(e),
                'fix_count_attempted': fix_count,
            }), 500

    issues.sort(key=lambda x: -x['max_abs_drift'])

    return jsonify({
        'threshold': threshold,
        'fix_applied': apply_fix,
        'fix_count': fix_count if apply_fix else 0,
        'users_scanned': len(users),
        'copytrade_bots_skipped': skipped_copytrade,
        'users_with_issues': len(issues),
        'total_snapshots_checked': total_snapshots_checked,
        'total_bad_snapshots': total_bad_snapshots,
        'issues': issues,
    })


@app.route('/api/cron/snapshot-audit', methods=['GET', 'POST'])
@app.route('/admin/cash-tracking/snapshot-audit', methods=['GET', 'POST'])
def cron_snapshot_audit():
    """
    Detects PortfolioSnapshot rows whose cash_proceeds or max_cash_deployed
    disagree with what the EOD market-close cron should have written.
    Persists the result to admin.extra_data['last_snapshot_audit'] and emails
    ADMIN_NOTIFY_EMAIL if any drift is found.

    Dual-auth (matches the drift-check endpoint's pattern):
      - /api/cron/snapshot-audit       → CRON_SECRET bearer token (Vercel cron)
      - /admin/cash-tracking/snapshot-audit → admin session (Run-now button)

    Buckets trades by UTC calendar date (matching the snapshot writer's
    func.date(timestamp) filter) and tolerates post-market-close (>= 20:00 UTC)
    boundary-wave trades, so EOD-wave timing differences are not flagged as
    false positives.

    Schedule: daily at 21:00 UTC (17:00 EDT / 16:00 EST), well after the
    market-close cron at 20:05 UTC has finished writing snapshots.
    """
    # Dual-auth: cron path requires bearer token; admin path requires admin session.
    is_admin_path = request.path.startswith('/admin/')
    if is_admin_path:
        admin_email = os.environ.get('ADMIN_EMAIL', 'admin@apestogether.ai')
        session_email = session.get('email', '')
        # Fall back to current_user.email when session.email is empty
        # (Flask-Login OAuth flows sometimes don't populate session['email']).
        if not session_email:
            try:
                from flask_login import current_user as _cu
                if _cu and _cu.is_authenticated:
                    session_email = getattr(_cu, 'email', '') or ''
            except Exception:
                session_email = ''
        if session_email.lower() != admin_email.lower():
            return jsonify({'error': 'admin_access_required'}), 403
        # Also require 2FA flag (same posture as @admin_required)
        if not session.get('admin_2fa_verified'):
            return jsonify({
                'error': '2fa_required',
                'message': 'Complete 2FA at /admin-panel before triggering snapshot audit.',
            }), 401
    else:
        auth_error = verify_cron_request()
        if auth_error:
            return auth_error

    from models import db, User, Transaction, PortfolioSnapshot
    from datetime import time as _dt_time, timedelta as _td
    try:
        from mobile_api import _is_copytrade_bot
    except Exception:
        def _is_copytrade_bot(_u):
            return False

    def _eff_date(ts):
        # Bucket each trade by its UTC calendar date — IDENTICAL to how the EOD
        # snapshot writer assigns trades. calculate_cash_proceeds_as_of_date()
        # (cash_tracking.py) and the historical stock-value replay both filter with
        # `func.date(Transaction.timestamp) <= target_date`, i.e. Postgres DATE() on
        # the raw naive-UTC timestamp. The previous 20:05-UTC cutoff rolled late-wave
        # trades (e.g. a 20:09 UTC bot buy) to the NEXT day, but the snapshot captured
        # them SAME day (cash AND stock both moved -> total smooth), producing false-
        # positive 'drift'. Matching the writer's UTC-date bucketing kills that whole
        # false-positive class while still catching genuine stale-cash snapshots.
        if ts is None:
            return None
        return (ts.replace(tzinfo=None) if ts.tzinfo else ts).date()

    # Ambiguous-trade tolerance: trades AFTER market close (>= 20:00 UTC) on date D
    # may or may not be in that day's EOD snapshot (cron ~20:05, bot wave ~20:05-20:20,
    # snapshot may be (re)written before or after). Add their summed |value| on date D
    # to the threshold so neither case is falsely flagged. Intraday trades (< 20:00 UTC)
    # are NOT tolerated, so genuine stale-cash snapshots still surface.
    _amb_start = _dt_time(20, 0)
    _amb_end = _dt_time(23, 59, 59)

    cash_threshold = 1.00  # $1.00 — coarser than admin endpoint to avoid noise
    max_cash_threshold = 1.00

    issues = []
    total_snapshots_checked = 0
    total_bad_snapshots = 0

    users = User.query.order_by(User.id.asc()).all()

    skipped_copytrade = 0
    for user in users:
        # Copytrade bots (CoastHillBear, marblethehill72) derive cash/holdings from
        # brokerage-screenshot migrations (price_source='phase_c_migration') that a
        # transaction replay cannot reproduce, so they always show false-positive
        # drift. Skip them so alerts stay trustworthy and a blanket fix can't corrupt them.
        if _is_copytrade_bot(user):
            skipped_copytrade += 1
            continue
        txns = Transaction.query.filter_by(user_id=user.id).order_by(
            Transaction.timestamp.asc()
        ).all()
        snaps = PortfolioSnapshot.query.filter_by(user_id=user.id).order_by(
            PortfolioSnapshot.date.asc()
        ).all()
        if not snaps or not txns:
            continue

        # Pre-compute per-date ambiguous-trade tolerance for this user
        amb_tol_by_date = {}
        for txn in txns:
            if txn.timestamp is None:
                continue
            ts_n = txn.timestamp.replace(tzinfo=None) if txn.timestamp.tzinfo else txn.timestamp
            if _amb_start <= ts_n.time() < _amb_end:
                v = abs(float((txn.quantity or 0) * (txn.price or 0)))
                d = ts_n.date()
                amb_tol_by_date[d] = amb_tol_by_date.get(d, 0.0) + v

        # Compute seeded_baseline from first snapshot
        first_snap = snaps[0]
        rmf = 0.0
        rcf = 0.0
        for txn in txns:
            t_date = _eff_date(txn.timestamp)
            if t_date is None or t_date > first_snap.date:
                break
            v = (txn.quantity or 0) * (txn.price or 0)
            if txn.transaction_type in ('buy', 'initial'):
                if rcf >= v:
                    rcf -= v
                else:
                    rmf += v - rcf
                    rcf = 0
            elif txn.transaction_type in ('sell', 'dividend'):
                rcf += v
        seeded_baseline = max(0.0, round(float(first_snap.max_cash_deployed or 0) - rmf, 2))

        # Walk snapshots, replay transactions with effective-date cutoff
        replay_cash = 0.0
        replay_max = 0.0
        txn_idx = 0
        user_bad = []

        for snap in snaps:
            while txn_idx < len(txns):
                txn = txns[txn_idx]
                t_eff = _eff_date(txn.timestamp)
                if t_eff is None or t_eff > snap.date:
                    break
                v = (txn.quantity or 0) * (txn.price or 0)
                if txn.transaction_type in ('buy', 'initial'):
                    if replay_cash >= v:
                        replay_cash -= v
                    else:
                        replay_max += v - replay_cash
                        replay_cash = 0
                elif txn.transaction_type in ('sell', 'dividend'):
                    replay_cash += v
                txn_idx += 1

            actual_cash = round(float(snap.cash_proceeds or 0), 2)
            expected_cash = round(replay_cash, 2)
            cash_drift = round(expected_cash - actual_cash, 2)

            actual_max = round(float(snap.max_cash_deployed or 0), 2)
            expected_max = round(seeded_baseline + replay_max, 2)
            max_drift = round(expected_max - actual_max, 2)

            total_snapshots_checked += 1

            # Apply ambiguous-trade tolerance for this snapshot's date
            amb_tol = amb_tol_by_date.get(snap.date, 0.0)
            cash_eff_threshold = cash_threshold + amb_tol
            max_eff_threshold = max_cash_threshold + amb_tol

            if abs(cash_drift) >= cash_eff_threshold or abs(max_drift) >= max_eff_threshold:
                total_bad_snapshots += 1
                user_bad.append({
                    'date': snap.date.isoformat(),
                    'actual_cash': actual_cash,
                    'expected_cash': expected_cash,
                    'cash_drift': cash_drift,
                    'actual_max': actual_max,
                    'expected_max': expected_max,
                    'max_drift': max_drift,
                    'ambiguous_tolerance': round(amb_tol, 2) if amb_tol > 0 else None,
                })

        if user_bad:
            issues.append({
                'user_id': user.id,
                'username': user.username,
                'role': user.role,
                'bad_snapshot_count': len(user_bad),
                'first_bad_date': user_bad[0]['date'],
                'last_bad_date': user_bad[-1]['date'],
                'sample': user_bad[:5],
            })

    issues.sort(key=lambda x: -x['bad_snapshot_count'])

    timestamp_str = datetime.utcnow().isoformat()
    if issues:
        prompt_lines = [
            f"# Snapshot drift detected ({timestamp_str})",
            f"# {total_bad_snapshots} bad snapshots across {len(issues)} users (of {len(users)} scanned).",
            f"# Trades bucketed by UTC date with post-close (>=20:00 UTC) tolerance; these are NOT EOD-wave timing false positives.",
            "",
            "Investigate via:",
            "  /admin/audit-snapshot-cash-drift  (full per-snapshot detail)",
            "  /admin/audit-snapshot-max-cash-drift  (max_cash_deployed view)",
            "  /admin/cash-tracking/full-rebuild?username=USER&execute=true  (apply repair)",
        ]
        prompt = "\n".join(prompt_lines)
    else:
        prompt = f"# No snapshot drift ({timestamp_str}) — {len(users)} users, {total_snapshots_checked} snapshots all clean."

    response = {
        'success': True,
        'timestamp': timestamp_str,
        'users_scanned': len(users),
        'copytrade_bots_skipped': skipped_copytrade,
        'total_snapshots_checked': total_snapshots_checked,
        'total_bad_snapshots': total_bad_snapshots,
        'users_with_issues': len(issues),
        'cash_threshold': cash_threshold,
        'max_cash_threshold': max_cash_threshold,
        'issues': issues,
        'prompt': prompt,
    }

    # Persist to admin user via raw SQL with jsonb_set. Atomic merge —
    # eliminates the read-modify-write race where two writers (drift-check
    # and snapshot-audit) could clobber each other's keys in admin.extra_data.
    # Also bypasses the dual-SQLAlchemy-instance footgun: raw SQL via
    # db.session.execute() commits to the actual DB regardless of which
    # `db` instance is in scope. See the same comment in
    # admin_cash_tracking.py:drift_check_cash_tracking for the full write-up.
    try:
        from sqlalchemy import text as _sql_text2
        from admin_cash_tracking import _find_admin_user_for_persistence
        import json as _json_lib2
        admin = _find_admin_user_for_persistence()
        if admin:
            payload = {
                'timestamp': timestamp_str,
                'users_scanned': len(users),
                'total_snapshots_checked': total_snapshots_checked,
                'total_bad_snapshots': total_bad_snapshots,
                'users_with_issues': len(issues),
                'issues': issues,
                'prompt': prompt,
            }
            db.session.execute(_sql_text2("""
                UPDATE "user"
                SET metadata = jsonb_set(
                    COALESCE(metadata::jsonb, '{}'::jsonb),
                    '{last_snapshot_audit}',
                    CAST(:payload AS jsonb)
                )
                WHERE id = :user_id
            """), {
                'payload': _json_lib2.dumps(payload),
                'user_id': admin.id,
            })
            db.session.commit()
            response['persisted'] = True
            response['persisted_user_id'] = admin.id
        else:
            response['persisted'] = False
            response['persisted_error'] = 'admin_user_not_found'
    except Exception as pe:
        logger.warning(f"Could not persist snapshot-audit result: {pe}", exc_info=True)
        response['persisted'] = False
        response['persisted_error'] = str(pe)
        try:
            db.session.rollback()
        except Exception:
            pass

    # Email alert if drift found
    if issues:
        try:
            import smtplib
            from email.mime.text import MIMEText
            # Fallback chain: ADMIN_NOTIFY_EMAIL → ADMIN_EMAIL → hardcoded admin inbox.
            # Eliminates the need for a separate ADMIN_NOTIFY_EMAIL Vercel var when
            # ADMIN_EMAIL is already where alerts should go (the common case).
            notify_email = (
                os.environ.get('ADMIN_NOTIFY_EMAIL')
                or os.environ.get('ADMIN_EMAIL')
                or 'bobford00@gmail.com'
            )
            smtp_user = os.environ.get('SMTP_USER')
            smtp_pass = os.environ.get('SMTP_PASS')

            if smtp_user and smtp_pass:
                body_lines = [
                    f"PortfolioSnapshot drift detected on {timestamp_str}.",
                    "",
                    f"{total_bad_snapshots} bad snapshots across {len(issues)} of {len(users)} users.",
                    f"Total snapshots checked: {total_snapshots_checked}",
                    "",
                    "Top affected users:",
                ]
                for issue in issues[:10]:
                    body_lines.append(
                        f"  - {issue['username']} ({issue['role']}): "
                        f"{issue['bad_snapshot_count']} bad snapshots, "
                        f"first={issue['first_bad_date']}, last={issue['last_bad_date']}"
                    )
                body_lines.extend([
                    "",
                    "===== Prompt-ready summary =====",
                    "",
                    prompt,
                    "",
                    "===== Full JSON =====",
                    str(issues),
                ])
                msg = MIMEText("\n".join(body_lines))
                msg['Subject'] = f'[ApesTogether] Snapshot drift: {len(issues)} users, {total_bad_snapshots} bad snapshots'
                msg['From'] = smtp_user
                msg['To'] = notify_email
                with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
                    server.login(smtp_user, smtp_pass)
                    server.send_message(msg)
                response['email_sent'] = True
                logger.info(f"Snapshot-audit alert email sent to {notify_email}: {len(issues)} users")
            else:
                response['email_sent'] = False
                response['email_error'] = 'SMTP not configured'
        except Exception as ee:
            response['email_sent'] = False
            response['email_error'] = str(ee)
            logger.error(f"Snapshot-audit email failed: {ee}")

    return jsonify(response)


@app.route('/admin/last-snapshot-audit')
@admin_required
def admin_last_snapshot_audit():
    """Return the most recently persisted snapshot-audit cron result.

    Uses the shared admin-lookup helper so this reader looks at the same User
    row the writer wrote to (current_user → case-insensitive email → exact).
    Previously a casing mismatch between the DB and ADMIN_EMAIL could make
    this endpoint silently return never_run after a successful audit run.
    """
    from admin_cash_tracking import _find_admin_user_for_persistence
    admin = _find_admin_user_for_persistence()
    if not admin:
        return jsonify({'error': 'admin user not found'}), 404
    result = (admin.extra_data or {}).get('last_snapshot_audit')
    if not result:
        return jsonify({
            'never_run': True,
            'hint': 'Hit /api/cron/snapshot-audit (cron-auth) to populate, or wait for the daily 21:00 UTC schedule.',
        })
    return jsonify(result)


@app.route('/admin/rename-user', methods=['POST'])
@admin_required
def admin_rename_user():
    """Rename a user by ID. POST JSON: {user_id, new_username}"""
    from models import User
    try:
        data = request.get_json() or {}
        user_id = data.get('user_id')
        new_username = (data.get('new_username') or '').strip()
        if not user_id or not new_username:
            return jsonify({'error': 'user_id and new_username required'}), 400
        user = User.query.get(user_id)
        if not user:
            return jsonify({'error': f'User {user_id} not found'}), 404
        existing = User.query.filter(User.username == new_username, User.id != user_id).first()
        if existing:
            return jsonify({'error': f'Username "{new_username}" already taken by user {existing.id}'}), 409
        old_username = user.username
        user.username = new_username
        db.session.commit()
        return jsonify({'success': True, 'old_username': old_username, 'new_username': new_username, 'user_id': user_id})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@app.route('/admin/waitlist')
@admin_required
def admin_waitlist():
    """View all beta waitlist signups — HTML table with CSV export"""
    from models import BetaWaitlist
    fmt = request.args.get('format', 'html')
    entries = BetaWaitlist.query.order_by(BetaWaitlist.created_at.desc()).all()

    if fmt == 'json':
        return jsonify({
            'total': len(entries),
            'entries': [{
                'id': e.id,
                'email': e.email,
                'role': e.role,
                'referral_source': e.referral_source,
                'created_at': e.created_at.isoformat() if e.created_at else None
            } for e in entries]
        })

    if fmt == 'csv':
        import csv, io
        si = io.StringIO()
        w = csv.writer(si)
        w.writerow(['#', 'Email', 'Role', 'Referral Source', 'Signed Up'])
        for i, e in enumerate(entries, 1):
            w.writerow([i, e.email, e.role or '', e.referral_source or '',
                        e.created_at.strftime('%Y-%m-%d %H:%M') if e.created_at else ''])
        resp = make_response(si.getvalue())
        resp.headers['Content-Type'] = 'text/csv'
        resp.headers['Content-Disposition'] = 'attachment; filename=waitlist.csv'
        return resp

    rows = ''
    for i, e in enumerate(entries, 1):
        dt = e.created_at.strftime('%b %d, %Y %I:%M %p') if e.created_at else '—'
        rows += f'<tr><td>{i}</td><td>{e.email}</td><td>{e.role or "—"}</td><td>{e.referral_source or "—"}</td><td>{dt}</td></tr>'

    return f'''<!DOCTYPE html><html><head><meta charset="utf-8"><title>Beta Waitlist</title>
<style>
body{{font-family:Inter,-apple-system,sans-serif;background:#080C0A;color:#F0F4F2;padding:32px;margin:0}}
h1{{font-size:1.6rem;margin-bottom:4px}}
.meta{{color:#9CA3AF;margin-bottom:24px;font-size:0.9rem}}
table{{width:100%;border-collapse:collapse;font-size:0.9rem}}
th{{text-align:left;padding:10px 12px;border-bottom:2px solid #1A2520;color:#00D9A5;font-weight:600}}
td{{padding:10px 12px;border-bottom:1px solid #1A2520}}
tr:hover td{{background:#0F1513}}
.actions{{display:flex;gap:12px;margin-bottom:20px}}
.btn{{background:#00D9A5;color:#080C0A;padding:8px 20px;border-radius:8px;text-decoration:none;font-weight:700;font-size:0.85rem}}
.btn-ghost{{background:transparent;border:1px solid #1A2520;color:#F0F4F2;padding:8px 20px;border-radius:8px;text-decoration:none;font-weight:600;font-size:0.85rem}}
</style></head><body>
<h1>Beta Waitlist</h1>
<p class="meta">{len(entries)} signup{"s" if len(entries) != 1 else ""}</p>
<div class="actions">
<a href="/admin/waitlist?format=csv" class="btn">Download CSV</a>
<a href="/admin/waitlist?format=json" class="btn-ghost">View JSON</a>
</div>
<table><thead><tr><th>#</th><th>Email</th><th>Role</th><th>Referral</th><th>Signed Up</th></tr></thead>
<tbody>{rows}</tbody></table>
</body></html>'''


@app.route('/terms-of-service')
def terms_of_service():
    """Terms of Service page"""
    return render_template_with_defaults('terms_of_service.html')

@app.route('/privacy-policy')
def privacy_policy():
    """Privacy Policy page.

    Detects the Global Privacy Control opt-out preference signal (Sec-GPC: 1,
    11 CCR § 7025) and surfaces an on-page confirmation that the signal is
    honored. The signal is also recorded site-wide by _honor_gpc_signal().
    """
    gpc = request.headers.get('Sec-GPC') == '1' or request.cookies.get('gpc_opt_out') == '1'
    return render_template_with_defaults('privacy_policy.html', gpc_detected=gpc)


@app.after_request
def _honor_gpc_signal(response):
    """Honor the Global Privacy Control opt-out preference signal.

    We do not sell or share personal information and run no third-party
    ad-tech, so there is nothing to disable — but per 11 CCR § 7025 the
    browser's Sec-GPC signal must be TREATED as a valid opt-out of
    sale/sharing. We persist the preference in a first-party cookie so the
    opt-out is recorded, demonstrable, and already enforced should our
    practices ever change (any future ad-tech integration must check it).
    """
    try:
        if request.headers.get('Sec-GPC') == '1' and request.cookies.get('gpc_opt_out') != '1':
            response.set_cookie('gpc_opt_out', '1', max_age=31536000,
                                secure=True, httponly=False, samesite='Lax')
    except Exception:
        pass  # never let the privacy cookie break a response
    return response

@app.route('/delete-account')
def delete_account_info():
    """Public account-deletion instructions page.

    Required by the Google Play / App Store data-deletion policy: a publicly
    accessible URL (NO login) that names the app/developer, lists the steps to
    request deletion, and specifies what data is deleted vs. retained and for
    how long. This is informational only; the actual deletion is performed via
    the in-app DELETE /auth/account flow or an email request to support (the
    website has no user login)."""
    return render_template_with_defaults('delete_account.html')

@app.route('/register', methods=['GET', 'POST'])
@limiter.limit("5 per minute")
def register():
    """User registration page"""
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        
        # Check if user already exists
        existing_user = User.query.filter((User.username == username) | (User.email == email)).first()
        if existing_user:
            flash('Username or email already exists', 'danger')
            return redirect(url_for('register'))
        
        # Create new user
        new_user = User(username=username, email=email)
        new_user.set_password(password)
        
        try:
            db.session.add(new_user)
            db.session.commit()
            
            # Log the user in
            session['user_id'] = new_user.id
            session['email'] = new_user.email
            session['username'] = new_user.username
            
            flash('Registration successful!', 'success')
            return redirect(url_for('dashboard'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error creating account: {str(e)}', 'danger')
    
    return render_template_with_defaults('register.html')

@app.route('/logout')
def logout():
    """Logout the current user"""
    # Use Flask-Login to handle logout
    logout_user()
    
    # For backward compatibility, also clear session variables
    session.pop('user_id', None)
    session.pop('email', None)
    session.pop('username', None)
    session.pop('admin_2fa_verified', None)
    session.pop('admin_panel_redirect', None)
    
    flash('You have been logged out', 'success')
    return redirect(url_for('index'))

@app.route('/auth/complete-profile', methods=['GET', 'POST'])
@login_required
def complete_profile():
    """Complete user profile with phone number and notification preferences"""
    if request.method == 'POST':
        phone_number = request.form.get('phone_number', '').strip()
        enable_email = request.form.get('enable_email') == '1'
        enable_sms = request.form.get('enable_sms') == '1'
        
        logger.info(f"Profile form submitted - phone: {phone_number}, email: {enable_email}, sms: {enable_sms}")
        
        # Normalize phone number (auto-add +1 for US numbers)
        if phone_number:
            # Remove all non-digit characters
            digits_only = ''.join(filter(str.isdigit, phone_number))
            
            if len(digits_only) == 10:
                # US number without country code: 3235551234 -> +13235551234
                phone_number = f'+1{digits_only}'
            elif len(digits_only) == 11 and digits_only.startswith('1'):
                # US number with 1 prefix: 13235551234 -> +13235551234
                phone_number = f'+{digits_only}'
            elif not phone_number.startswith('+'):
                # Has digits but no +, add it
                phone_number = f'+{digits_only}'
        
        # Update user
        old_phone = current_user.phone_number
        old_method = current_user.default_notification_method
        
        current_user.phone_number = phone_number if phone_number else None
        
        # Determine default method based on checkboxes
        if enable_sms and phone_number:
            current_user.default_notification_method = 'both' if enable_email else 'sms'
        else:
            current_user.default_notification_method = 'email'
        
        logger.info(f"Updating user {current_user.id}: phone {old_phone} -> {current_user.phone_number}, method {old_method} -> {current_user.default_notification_method}")
        
        try:
            db.session.commit()
            logger.info(f"Profile update committed successfully for user {current_user.id}")
            flash('Profile updated successfully!', 'success')
            return redirect(url_for('dashboard'))
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error updating profile: {str(e)}")
            logger.error(traceback.format_exc())
            flash('Error updating profile', 'danger')
    
    return render_template_with_defaults('complete_profile.html')

@app.route('/settings/notifications')
@login_required
def notification_settings():
    """Notification settings page - manage preferences per subscription"""
    from models import NotificationPreferences
    
    # Get all user's subscriptions with preferences
    subscriptions = Subscription.query.filter_by(
        subscriber_id=current_user.id,
        status='active'
    ).all()
    
    # Add preference to each subscription
    for sub in subscriptions:
        sub.preference = NotificationPreferences.query.filter_by(
            user_id=current_user.id,
            subscription_id=sub.id
        ).first()
    
    return render_template_with_defaults('notification_settings.html', 
                                        subscriptions=subscriptions)

@app.route('/api/user/update-contact', methods=['POST'])
@login_required
def update_contact():
    """API endpoint to update user contact information"""
    try:
        data = request.get_json()
        
        phone_number = data.get('phone_number', '').strip()
        default_method = data.get('default_notification_method', 'email')
        
        # Normalize phone number (auto-add +1 for US numbers)
        if phone_number:
            digits_only = ''.join(filter(str.isdigit, phone_number))
            
            if len(digits_only) == 10:
                phone_number = f'+1{digits_only}'
            elif len(digits_only) == 11 and digits_only.startswith('1'):
                phone_number = f'+{digits_only}'
            elif not phone_number.startswith('+'):
                phone_number = f'+{digits_only}'
        
        current_user.phone_number = phone_number if phone_number else None
        current_user.default_notification_method = default_method
        
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'Contact information updated'})
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error updating contact: {str(e)}")
        return jsonify({'success': False, 'error': 'An internal error occurred'}), 500

@app.route('/api/notifications/preferences/<int:subscription_id>', methods=['PUT'])
@login_required
def update_notification_preference(subscription_id):
    """API endpoint to update notification preferences for a subscription"""
    try:
        from models import NotificationPreferences
        
        data = request.get_json()
        
        # Verify subscription belongs to user
        subscription = Subscription.query.filter_by(
            id=subscription_id,
            subscriber_id=current_user.id
        ).first()
        
        if not subscription:
            return jsonify({'error': 'Subscription not found'}), 404
        
        # Get or create preference
        preference = NotificationPreferences.query.filter_by(
            user_id=current_user.id,
            subscription_id=subscription_id
        ).first()
        
        if not preference:
            preference = NotificationPreferences(
                user_id=current_user.id,
                subscription_id=subscription_id
            )
            db.session.add(preference)
        
        # Update fields
        if 'notification_type' in data:
            preference.notification_type = data['notification_type']
        if 'enabled' in data:
            preference.enabled = data['enabled']
        
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'Preference updated'})
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error updating preference: {str(e)}")
        return jsonify({'success': False, 'error': 'An internal error occurred'}), 500

@app.route('/login/google')
def login_google():
    """Redirect to Google for OAuth login"""
    try:
        logger.info("Starting Google OAuth login")
        redirect_uri = url_for('authorize_google', _external=True)
        logger.info(f"Redirect URI: {redirect_uri}")
        return google.authorize_redirect(redirect_uri)
    except Exception as e:
        logger.error(f"Error in Google OAuth redirect: {str(e)}")
        logger.error(traceback.format_exc())
        flash('Error connecting to Google. Please try again.', 'danger')
        return redirect(url_for('login'))

# ── Removed: /admin/debug/flask-login — was publicly accessible, leaked session/cookie data.

@app.route('/login/google/authorize')
def authorize_google():
    """Handle the callback from Google OAuth"""
    # Initialize user variable at the beginning to avoid UnboundLocalError
    user = None
    
    try:
        # Step 1: Get token and user info from Google
        token = google.authorize_access_token()
        user_info = token.get('userinfo')
        
        # Log the token structure to help diagnose issues
        logger.info(f"OAuth token keys present: {', '.join(token.keys()) if token else 'None'}")
        
        # If userinfo is not directly available, try to extract from id_token
        if not user_info or 'email' not in user_info:
            logger.info("No direct userinfo, trying to extract from id_token")
            if 'id_token' in token:
                try:
                    # This is for debugging purposes only
                    id_token_payload = jwt.decode(token['id_token'], options={"verify_signature": False})
                    logger.info(f"Decoded id_token payload keys: {', '.join(id_token_payload.keys()) if id_token_payload else 'Empty'}")
                    if id_token_payload and 'email' in id_token_payload:
                        logger.info(f"Found email in id_token: {id_token_payload['email'].split('@')[0]}[REDACTED]")
                        user_info = id_token_payload
                except Exception as jwt_error:
                    logger.error(f"Error decoding id_token: {str(jwt_error)}")
                    logger.error(traceback.format_exc())
            
            # Check other common token keys
            if not user_info or 'email' not in user_info:
                for key in ['user', 'profile', 'info']:
                    if key in token and isinstance(token[key], dict):
                        logger.info(f"Checking token['{key}']: {', '.join(token[key].keys()) if token[key] else 'Empty'}")
                        if 'email' in token[key]:
                            logger.info(f"Found email in token['{key}']: {token[key]['email'].split('@')[0]}[REDACTED]")
                            user_info = token[key]
                            break
        
        # If we still don't have user info, try direct API call
        if not user_info or 'email' not in user_info:
            logger.info("Attempting to get userinfo from google.get('userinfo')")
            try:
                user_info = google.get('userinfo')
                logger.info(f"Got user_info from google.get('userinfo'): {user_info.keys() if user_info else 'Empty'}")
            except Exception as api_error:
                logger.error(f"Error getting user_info from google.get('userinfo'): {str(api_error)}")
        
        # Last resort: direct API call with access token
        if not user_info or 'email' not in user_info:
            logger.info("Last resort: Trying direct Google API call with access token")
            try:
                if 'access_token' in token:
                    import requests
                    headers = {'Authorization': f'Bearer {token["access_token"]}'}  
                    userinfo_response = requests.get('https://www.googleapis.com/oauth2/v3/userinfo', headers=headers)
                    
                    if userinfo_response.status_code == 200:
                        user_info = userinfo_response.json()
                        logger.info(f"Last resort user info: {user_info.keys() if user_info else 'Empty'}")
                    else:
                        logger.error(f"Last resort API call failed with status {userinfo_response.status_code}")
                else:
                    logger.error("No access token available for last resort attempt")
            except Exception as last_error:
                logger.error(f"Error in last resort attempt: {str(last_error)}")
        
        # Final validation that we have the required user information
        if not user_info or 'email' not in user_info:
            logger.error(f"Missing email in user_info after all attempts: {user_info}")
            flash('Could not retrieve your email from Google. Please try again or use another login method.', 'danger')
            return redirect(url_for('login'))
            
        logger.info(f"User email found: {user_info.get('email').split('@')[0]}[REDACTED]")
        
        # Step 2: Check if user exists in our database
        email = user_info.get('email')
        
        # Try to find the user (with retry for SSL drops)
        try:
            user = db_retry(lambda: User.query.filter_by(email=email).first())
            logger.info(f"User exists in database: {user is not None}")
        except Exception as user_query_error:
            logger.error(f"Error querying user after retries: {str(user_query_error)}")
            flash('Database connection error. Please try again.', 'danger')
            return redirect(url_for('login'))
        
        # Step 3: Create new user if not found
        if not user:
            from username_generator import generate_unique_username
            username = generate_unique_username()

            # Create new user
            logger.info(f"Creating new OAuth user with email: {user_info['email'].split('@')[0]}[REDACTED] and username: {username}")
            user = User(
                email=user_info['email'],
                username=username,
                oauth_provider='google',
                oauth_id=user_info.get('sub', user_info.get('id', str(uuid.uuid4()))),  # Use sub, id, or generate UUID as fallback
                stripe_price_id='price_1RbX0yQWUhVa3vgDB8vGzoFN',  # Default $4 price
                subscription_price=4.00
            )
            user.set_password('')  # Empty password for OAuth users
            
            def _create_user():
                db.session.add(user)
                db.session.commit()
                return user
            
            try:
                user = db_retry(_create_user)
                logger.info(f"Successfully created new OAuth user with ID: {user.id}")
            except Exception as create_err:
                logger.error(f"Error creating user after retries: {create_err}")
                flash('Database error during account creation. Please try again.', 'danger')
                return redirect(url_for('login'))
        
        # Step 4: Log the user in using Flask-Login
        # Double check we have a valid user object
        if not user:
            logger.error("User object is None after all attempts to find or create it")
            flash('Error logging in. Please try again later.', 'danger')
            return redirect(url_for('login'))
                
        # Make sure the user object is attached to the current session
        if hasattr(user, '_sa_instance_state') and user._sa_instance_state.session is not db.session:
            logger.warning("User object is not attached to the current session, merging")
            user = db.session.merge(user)
                
        # Try to log in the user
        try:
            login_success = login_user(user)
            logger.info(f"OAuth user login_user result: {login_success}")
            
            if login_success:
                logger.info(f"OAuth user logged in successfully: {user.username}")
                
                # For backward compatibility, also set session variables
                session['user_id'] = user.id
                session['email'] = user.email
                session['username'] = user.username
            else:
                logger.error("login_user returned False, falling back to session-based auth")
                # Fall back to session-based auth if Flask-Login fails
                session['user_id'] = user.id
                session['email'] = user.email
                session['username'] = user.username
        except Exception as login_error:
            logger.error(f"Error during OAuth login_user: {str(login_error)}")
            logger.error(traceback.format_exc())
            # Fall back to session-based auth if Flask-Login fails
            session['user_id'] = user.id
            session['email'] = user.email
            session['username'] = user.username
        
        # Step 5: Check if this is the user's first login (no stocks yet)
        try:
            if Stock.query.filter_by(user_id=user.id).count() == 0:
                flash('Welcome! Please add some stocks to your portfolio.', 'info')
            else:
                flash('Login successful!', 'success')
        except Exception as stock_check_error:
            logger.error(f"Error checking user's stocks: {str(stock_check_error)}")
            flash('Login successful!', 'success')
            
        # Step 6: Final redirect
        _is_admin_user = (user.email == ADMIN_EMAIL)
        session.pop('admin_panel_redirect', None)
        if _is_admin_user:
            logger.info(f"Admin user {user.email} logged in, redirecting to admin panel")
            return redirect(url_for('admin_panel'))
        else:
            return redirect('/')
            
    except Exception as general_error:
        # Catch-all error handler
        logger.error(f"Unexpected error in Google OAuth flow: {str(general_error)}")
        logger.error(traceback.format_exc())
        flash('An unexpected error occurred during login. Please try again later.', 'danger')
        return redirect(url_for('login'))

@app.route('/login/apple')
def login_apple():
    """Redirect to Apple OAuth login"""
    redirect_uri = url_for('authorize_apple', _external=True)
    return apple.authorize_redirect(redirect_uri)

@app.route('/login/apple/authorize')
def authorize_apple():
    """Handle Apple OAuth callback"""
    try:
        token = apple.authorize_access_token()
        user_info = token.get('userinfo')
        
        # Check if user exists
        user = User.query.filter_by(email=user_info['email']).first()
        
        if not user:
            from username_generator import generate_unique_username
            username = generate_unique_username()

            # Create new user
            user = User(
                email=user_info['email'],
                username=username,
                oauth_provider='apple',
                oauth_id=user_info['sub'],
                stripe_price_id='price_1RbX0yQWUhVa3vgDB8vGzoFN',  # Default $4 price
                subscription_price=4.00
            )
            user.set_password('') # Empty password for OAuth users
            db.session.add(user)
            db.session.commit()
        
        # Log the user in using Flask-Login
        try:
            login_user(user)
            logger.info(f"Apple OAuth user logged in successfully: {user.username}")
            
            # For backward compatibility, also set session variables
            session['user_id'] = user.id
            session['email'] = user.email
            session['username'] = user.username
        except Exception as e:
            logger.error(f"Error during Apple OAuth login_user: {str(e)}")
            logger.error(traceback.format_exc())
            # Fall back to session-based auth if Flask-Login fails
            session['user_id'] = user.id
            session['email'] = user.email
            session['username'] = user.username
        
        # Check if this is the user's first login (no stocks yet)
        if Stock.query.filter_by(user_id=user.id).count() == 0:
            flash('Welcome! Please add some stocks to your portfolio.', 'info')
        else:
            flash('Login successful!', 'success')
            
        return redirect(url_for('dashboard'))
    except Exception as e:
        logger.error(f"Error in Apple OAuth: {e}")
        flash('Error logging in with Apple. Please try again or use email login.', 'danger')
        return redirect(url_for('login'))

# Dashboard route is now defined earlier in the file (around line 1087)
# The duplicate dashboard route definition was removed to fix the server error

@app.route('/add_stock', methods=['POST'])
@limiter.limit("30 per minute")
def add_stock():
    """Add a stock to user's portfolio"""
    if 'user_id' not in session:
        flash('Please login to add stocks', 'warning')
        return redirect(url_for('login'))
    
    # Validate and parse form inputs
    ticker = request.form.get('ticker')
    if not ticker:
        flash('Ticker symbol is required', 'danger')
        return redirect(url_for('dashboard'))
    
    ticker = ticker.upper().strip()
    
    try:
        quantity = request.form.get('quantity')
        if not quantity:
            flash('Quantity is required', 'danger')
            return redirect(url_for('dashboard'))
        quantity = float(quantity)
        
        if quantity <= 0:
            flash('Quantity must be greater than zero', 'danger')
            return redirect(url_for('dashboard'))
        
    except ValueError as e:
        logger.error(f"Invalid quantity for add_stock: ticker={ticker}, quantity={request.form.get('quantity')}")
        flash(f'Invalid input: Please enter a valid number for quantity', 'danger')
        return redirect(url_for('dashboard'))
    
    # Fetch current stock price (with caching and API logic)
    try:
        from portfolio_performance import PortfolioPerformanceCalculator
        calculator = PortfolioPerformanceCalculator()
        stock_data = calculator.get_stock_data(ticker)
        
        if not stock_data or 'price' not in stock_data:
            flash(f'Could not fetch current price for {ticker}. Please check the ticker symbol and try again.', 'danger')
            logger.warning(f"Failed to fetch price for {ticker} when adding stock")
            return redirect(url_for('dashboard'))
        
        purchase_price = stock_data['price']
        logger.info(f"Fetched price for {ticker}: ${purchase_price:.2f}")
        
    except Exception as price_fetch_error:
        logger.error(f"Error fetching stock price for {ticker}: {str(price_fetch_error)}")
        flash(f'Error fetching stock price. Please try again later.', 'danger')
        return redirect(url_for('dashboard'))
    
    # Check if user already owns this stock
    existing_stock = Stock.query.filter_by(user_id=session['user_id'], ticker=ticker).first()
    
    try:
        if existing_stock:
            # Combine with existing position using weighted average cost basis
            old_cost_basis = existing_stock.quantity * existing_stock.purchase_price
            new_cost = quantity * purchase_price
            total_cost = old_cost_basis + new_cost
            total_quantity = existing_stock.quantity + quantity
            weighted_avg_price = total_cost / total_quantity
            
            logger.info(f"Combining with existing position: {existing_stock.quantity} @ ${existing_stock.purchase_price:.2f}")
            logger.info(f"New weighted average: {total_quantity} @ ${weighted_avg_price:.2f}")
            
            # Update existing stock
            existing_stock.quantity = total_quantity
            existing_stock.purchase_price = weighted_avg_price
            
            stock_to_commit = existing_stock
        else:
            # Create new stock
            new_stock = Stock(
                ticker=ticker,
                quantity=quantity,
                purchase_price=purchase_price,
                user_id=session['user_id']
            )
            db.session.add(new_stock)
            stock_to_commit = new_stock
            
            logger.info(f"Creating new stock position: {quantity} {ticker} @ ${purchase_price:.2f}")
        
        # Determine transaction type: 'initial' for first purchase, 'buy' for subsequent
        from models import Transaction
        existing_transactions = Transaction.query.filter_by(user_id=session['user_id']).count()
        transaction_type = 'initial' if existing_transactions == 0 else 'buy'
        
        # CRITICAL FIX: Process transaction and update cash tracking
        from cash_tracking import process_transaction
        cash_result = process_transaction(
            db=db,
            user_id=session['user_id'],
            ticker=ticker,
            quantity=quantity,
            price=purchase_price,
            transaction_type=transaction_type,
            timestamp=datetime.utcnow()
        )
        
        db.session.commit()
        
        # Auto-populate stock info for new stocks
        try:
            populate_single_stock_info(ticker.upper())
        except Exception as stock_info_error:
            logger.warning(f"Failed to populate stock info for {ticker}: {str(stock_info_error)}")
        
        # Recalculate portfolio stats immediately so dashboard updates
        try:
            from leaderboard_utils import calculate_user_portfolio_stats
            from models import UserPortfolioStats
            
            logger.info("Calculating portfolio stats after stock addition...")
            stats = calculate_user_portfolio_stats(session['user_id'])
            logger.info(f"Stats calculated: unique_stocks={stats['unique_stocks_count']}, trades/week={stats['avg_trades_per_week']:.1f}")
            
            # Convert cap percentages to market_cap_mix JSON
            market_cap_mix = {
                'small_cap': stats.get('small_cap_percent', 0),
                'large_cap': stats.get('large_cap_percent', 0)
            }
            
            user_stats = UserPortfolioStats.query.filter_by(user_id=session['user_id']).first()
            
            if user_stats:
                # Update existing stats
                logger.info(f"Updating existing stats for user {session['user_id']}")
                user_stats.unique_stocks_count = stats['unique_stocks_count']
                user_stats.avg_trades_per_week = stats['avg_trades_per_week']
                user_stats.market_cap_mix = market_cap_mix
                user_stats.industry_mix = stats.get('industry_mix', {})
                user_stats.subscriber_count = stats['subscriber_count']
                # Phase E: keep the fractional flag fresh on every stats write.
                user_stats.has_fractional_holdings = stats.get('has_fractional_holdings', False)
                user_stats.updated_at = datetime.utcnow()
                db.session.merge(user_stats)  # Use merge for cross-session safety
            else:
                # Create new stats entry
                logger.info(f"Creating new stats entry for user {session['user_id']}")
                user_stats = UserPortfolioStats(
                    user_id=session['user_id'],
                    unique_stocks_count=stats['unique_stocks_count'],
                    avg_trades_per_week=stats['avg_trades_per_week'],
                    market_cap_mix=market_cap_mix,
                    industry_mix=stats.get('industry_mix', {}),
                    subscriber_count=stats['subscriber_count'],
                    has_fractional_holdings=stats.get('has_fractional_holdings', False),
                )
                db.session.add(user_stats)
            
            db.session.commit()
            logger.info(f"✓ Portfolio stats committed successfully")
        except Exception as stats_error:
            logger.error(f"ERROR updating portfolio stats: {str(stats_error)}")
            import traceback
            logger.error(traceback.format_exc())
            # Don't fail the whole operation if stats update fails
        
        flash(f'Added {quantity} shares of {ticker}', 'success')
        logger.info(f"Created stock + transaction: {quantity} {ticker} @ ${purchase_price}")
        logger.info(f"Cash tracking: max_deployed=${cash_result['max_cash_deployed']}, proceeds=${cash_result['cash_proceeds']}")
    except Exception as e:
        db.session.rollback()
        flash(f'Error adding stock: {str(e)}', 'danger')
        logger.error(f"Failed to add stock/transaction: {str(e)}")
    
    return redirect(url_for('dashboard'))

@app.route('/sell_stock', methods=['POST'])
def sell_stock():
    """Sell stock from user's portfolio"""
    if 'user_id' not in session:
        flash('Please login to sell stocks', 'warning')
        return redirect(url_for('login'))
    
    # Validate and parse form inputs
    ticker = request.form.get('ticker')
    if not ticker:
        flash('Ticker symbol is required', 'danger')
        return redirect(url_for('dashboard'))
    
    ticker = ticker.upper().strip()
    
    try:
        quantity = request.form.get('quantity')
        if not quantity:
            flash('Quantity is required', 'danger')
            return redirect(url_for('dashboard'))
        quantity = float(quantity)
        
        if quantity <= 0:
            flash('Quantity must be greater than zero', 'danger')
            return redirect(url_for('dashboard'))
        
    except ValueError as e:
        logger.error(f"Invalid quantity for sell_stock: ticker={ticker}, quantity={request.form.get('quantity')}")
        flash(f'Invalid input: Please enter a valid number for quantity', 'danger')
        return redirect(url_for('dashboard'))
    
    # Find the stock in user's portfolio
    stock = Stock.query.filter_by(user_id=session['user_id'], ticker=ticker).first()
    if not stock:
        flash(f'You do not own any shares of {ticker}', 'danger')
        return redirect(url_for('dashboard'))
    
    # Check if user has enough shares
    if stock.quantity < quantity:
        flash(f'You only have {stock.quantity} shares of {ticker}, cannot sell {quantity}', 'danger')
        return redirect(url_for('dashboard'))
    
    # Fetch current stock price (with caching and API logic)
    try:
        from portfolio_performance import PortfolioPerformanceCalculator
        calculator = PortfolioPerformanceCalculator()
        stock_data = calculator.get_stock_data(ticker)
        
        if not stock_data or 'price' not in stock_data:
            flash(f'Could not fetch current price for {ticker}. Please try again.', 'danger')
            logger.warning(f"Failed to fetch price for {ticker} when selling stock")
            return redirect(url_for('dashboard'))
        
        sale_price = stock_data['price']
        logger.info(f"Fetched price for {ticker}: ${sale_price:.2f}")
        
    except Exception as price_fetch_error:
        logger.error(f"Error fetching stock price for {ticker}: {str(price_fetch_error)}")
        flash(f'Error fetching stock price. Please try again later.', 'danger')
        return redirect(url_for('dashboard'))
    
    try:
        # Determine transaction type
        from models import Transaction
        existing_transactions = Transaction.query.filter_by(user_id=session['user_id']).count()
        transaction_type = 'sell'
        
        # Process transaction and update cash tracking
        from cash_tracking import process_transaction
        cash_result = process_transaction(
            db=db,
            user_id=session['user_id'],
            ticker=ticker,
            quantity=quantity,
            price=sale_price,
            transaction_type=transaction_type,
            timestamp=datetime.utcnow(),
            position_before_qty=stock.quantity
        )
        
        # Update or remove stock
        if stock.quantity == quantity:
            # Selling all shares, remove stock
            db.session.delete(stock)
            logger.info(f"Removed {ticker} from portfolio (sold all shares)")
        else:
            # Selling partial shares, reduce quantity
            stock.quantity -= quantity
            logger.info(f"Reduced {ticker} quantity from {stock.quantity + quantity} to {stock.quantity}")
        
        db.session.commit()
        
        # Recalculate portfolio stats immediately so dashboard updates
        try:
            from leaderboard_utils import calculate_user_portfolio_stats
            from models import UserPortfolioStats
            
            logger.info("Calculating portfolio stats after stock sale...")
            stats = calculate_user_portfolio_stats(session['user_id'])
            logger.info(f"Stats calculated: unique_stocks={stats['unique_stocks_count']}, trades/week={stats['avg_trades_per_week']:.1f}")
            
            # Convert cap percentages to market_cap_mix JSON
            market_cap_mix = {
                'small_cap': stats.get('small_cap_percent', 0),
                'large_cap': stats.get('large_cap_percent', 0)
            }
            
            user_stats = UserPortfolioStats.query.filter_by(user_id=session['user_id']).first()
            
            if user_stats:
                # Update existing stats
                logger.info(f"Updating existing stats for user {session['user_id']}")
                user_stats.unique_stocks_count = stats['unique_stocks_count']
                user_stats.avg_trades_per_week = stats['avg_trades_per_week']
                user_stats.market_cap_mix = market_cap_mix
                user_stats.industry_mix = stats.get('industry_mix', {})
                user_stats.subscriber_count = stats['subscriber_count']
                # Phase E: keep the fractional flag fresh on every stats write.
                user_stats.has_fractional_holdings = stats.get('has_fractional_holdings', False)
                user_stats.updated_at = datetime.utcnow()
                db.session.merge(user_stats)  # Use merge for cross-session safety
            else:
                # Create new stats entry
                logger.info(f"Creating new stats entry for user {session['user_id']}")
                user_stats = UserPortfolioStats(
                    user_id=session['user_id'],
                    unique_stocks_count=stats['unique_stocks_count'],
                    avg_trades_per_week=stats['avg_trades_per_week'],
                    market_cap_mix=market_cap_mix,
                    industry_mix=stats.get('industry_mix', {}),
                    subscriber_count=stats['subscriber_count'],
                    has_fractional_holdings=stats.get('has_fractional_holdings', False),
                )
                db.session.add(user_stats)
            
            db.session.commit()
            logger.info(f"✓ Portfolio stats committed successfully")
        except Exception as stats_error:
            logger.error(f"ERROR updating portfolio stats: {str(stats_error)}")
            import traceback
            logger.error(traceback.format_exc())
            # Don't fail the whole operation if stats update fails
        
        flash(f'Sold {quantity} shares of {ticker} at ${sale_price:.2f}', 'success')
        logger.info(f"Sold stock: {quantity} {ticker} @ ${sale_price}")
        logger.info(f"Cash tracking: max_deployed=${cash_result['max_cash_deployed']}, proceeds=${cash_result['cash_proceeds']}")
    except Exception as e:
        db.session.rollback()
        flash(f'Error selling stock: {str(e)}', 'danger')
        logger.error(f"Failed to sell stock: {str(e)}")
    
    return redirect(url_for('dashboard'))


@app.route('/delete_stock/<int:stock_id>', methods=['POST'])
def delete_stock(stock_id):
    """Delete a stock from user's portfolio"""
    if 'user_id' not in session:
        flash('Please login to delete stocks', 'warning')
        return redirect(url_for('login'))
    
    stock = Stock.query.get(stock_id)
    
    if not stock or stock.user_id != session['user_id']:
        flash('Stock not found or you do not have permission to delete it', 'danger')
        return redirect(url_for('dashboard'))
    
    try:
        db.session.delete(stock)
        db.session.commit()
        flash(f'Deleted {stock.ticker} from your portfolio', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting stock: {str(e)}', 'danger')
        return redirect(url_for('admin_dashboard'))


































@app.route('/admin/transactions')
@admin_2fa_required
def admin_transactions():
    """Admin route to view transactions"""
    try:
        # Get real transaction data from database
        transactions_query = Transaction.query.all()
        
        # Format transaction data
        transactions = []
        for tx in transactions_query:
            # Get username for the transaction
            user = User.query.get(tx.user_id)
            username = user.username if user else 'Unknown'
            
            transactions.append({
                'id': tx.id,
                'user_id': tx.user_id,
                'username': username,
                'symbol': tx.ticker,
                'shares': tx.quantity,
                'price': tx.price,
                'transaction_type': tx.transaction_type,
                'date': tx.timestamp.strftime('%Y-%m-%d'),
                'notes': tx.notes or ''
            })
    except Exception as e:
        app.logger.error(f"Database error in admin_transactions: {str(e)}")
        # Fallback to mock data if database fails
        transactions = [
            {'id': 1, 'user_id': 1, 'username': 'witty-raven', 'symbol': 'AAPL', 'shares': 10, 'price': 150.0, 'transaction_type': 'buy', 'date': '2023-01-15', 'notes': 'Initial purchase'},
            {'id': 2, 'user_id': 1, 'username': 'witty-raven', 'symbol': 'MSFT', 'shares': 5, 'price': 250.0, 'transaction_type': 'buy', 'date': '2023-02-20', 'notes': 'Portfolio diversification'},
            {'id': 3, 'user_id': 2, 'username': 'user1', 'symbol': 'GOOGL', 'shares': 2, 'price': 2800.0, 'transaction_type': 'buy', 'date': '2023-03-10', 'notes': ''},
            {'id': 4, 'user_id': 3, 'username': 'user2', 'symbol': 'AMZN', 'shares': 1, 'price': 3200.0, 'transaction_type': 'buy', 'date': '2023-04-05', 'notes': ''},
            {'id': 5, 'user_id': 1, 'username': 'witty-raven', 'symbol': 'AAPL', 'shares': 5, 'price': 170.0, 'transaction_type': 'sell', 'date': '2023-05-15', 'notes': 'Profit taking'},
        ]
    
    # Get filter parameters
    user_filter = request.args.get('user', '')
    symbol_filter = request.args.get('symbol', '')
    type_filter = request.args.get('type', '')
    
    # Apply filters if provided
    filtered_transactions = transactions
    if user_filter:
        filtered_transactions = [t for t in filtered_transactions if str(t['user_id']) == user_filter]
    if symbol_filter:
        filtered_transactions = [t for t in filtered_transactions if t['ticker'].lower() == symbol_filter.lower()]
    if type_filter:
        filtered_transactions = [t for t in filtered_transactions if t['transaction_type'].lower() == type_filter.lower()]
    
    # Get unique users and symbols for filters
    unique_users = list(set([(t['user_id'], t['username']) for t in transactions]))
    unique_symbols = list(set([t['ticker'] for t in transactions]))
    
    return render_template_string("""
<!DOCTYPE html>
<html>
<head>
    <title>Admin - Transactions</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 40px; }
        .container { max-width: 1000px; margin: 0 auto; }
        .button { 
            display: inline-block; 
            background: #4CAF50; 
            color: white; 
            padding: 10px 20px; 
            text-decoration: none; 
            border-radius: 5px; 
            margin-top: 20px;
            margin-right: 10px;
        }
        .button-secondary { background: #2196F3; }
        .button-warning { background: #FF9800; }
        .button-danger { background: #F44336; }
        .button-small { padding: 5px 10px; margin-top: 0; }
        table {
            width: 100%;
            border-collapse: collapse;
            margin-top: 20px;
        }
        th, td {
            padding: 8px;
            text-align: left;
            border-bottom: 1px solid #ddd;
        }
        th {
            background-color: #f2f2f2;
        }
        tr:hover {background-color: #f5f5f5;}
        .nav { 
            background: #333; 
            padding: 10px; 
            margin-bottom: 20px; 
            border-radius: 5px; 
        }
        .nav a { 
            color: white; 
            text-decoration: none; 
            margin-right: 15px; 
            padding: 5px 10px; 
        }
        .nav a:hover { 
            background: #555; 
            border-radius: 3px; 
        }
        .filters {
            margin: 20px 0;
            padding: 15px;
            background: #f9f9f9;
            border-radius: 5px;
            display: flex;
            flex-wrap: wrap;
            gap: 15px;
        }
        .filters select, .filters button {
            padding: 8px;
            border: 1px solid #ddd;
            border-radius: 4px;
        }
        .filters button {
            background: #4CAF50;
            color: white;
            border: none;
            cursor: pointer;
        }
        .buy { color: green; }
        .sell { color: red; }
        .summary {
            margin-top: 20px;
            padding: 15px;
            background: #e9f7ef;
            border-radius: 5px;
        }
        .summary h3 {
            margin-top: 0;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="nav">
            <a href="/admin">Dashboard</a>
            <a href="/admin/users">Users</a>
            <a href="/admin/transactions">Transactions</a>
            <a href="/">Main Site</a>
        </div>
        
        <h1>Transaction Management</h1>
        
        <div class="filters">
            <form method="get" action="/admin/transactions">
                <select name="user">
                    <option value="">All Users</option>
                    {% for user_id, username in unique_users %}
                    <option value="{{ user_id }}" {% if user_filter == user_id|string %}selected{% endif %}>{{ username }}</option>
                    {% endfor %}
                </select>
                
                <select name="symbol">
                    <option value="">All Tickers</option>
                    {% for symbol in unique_symbols %}
                    <option value="{{ symbol }}" {% if symbol_filter == symbol %}selected{% endif %}>{{ symbol }}</option>
                    {% endfor %}
                </select>
                
                <select name="type">
                    <option value="">All Types</option>
                    <option value="buy" {% if type_filter == 'buy' %}selected{% endif %}>Buy</option>
                    <option value="sell" {% if type_filter == 'sell' %}selected{% endif %}>Sell</option>
                </select>
                
                <button type="submit">Filter</button>
                <a href="/admin/transactions" style="padding: 8px; text-decoration: none;">Clear Filters</a>
            </form>
        </div>
        
        <div class="summary">
            <h3>Transaction Summary</h3>
            <p>Total Transactions: {{ filtered_transactions|length }}</p>
            <p>Total Value: ${{ '%0.2f'|format(filtered_transactions|sum(attribute='price')|float) }}</p>
        </div>
        
        <table>
            <tr>
                <th>ID</th>
                <th>User</th>
                <th>Ticker</th>
                <th>Quantity</th>
                <th>Price</th>
                <th>Total</th>
                <th>Type</th>
                <th>Timestamp</th>
                <th>Notes</th>
                <th>Actions</th>
            </tr>
            {% for tx in filtered_transactions %}
            <tr>
                <td>{{ tx.id }}</td>
                <td>{{ tx.username }}</td>
                <td>{{ tx.ticker }}</td>
                <td>{{ tx.quantity }}</td>
                <td>${{ '%0.2f'|format(tx.price) }}</td>
                <td>${{ '%0.2f'|format(tx.quantity * tx.price) }}</td>
                <td class="{{ tx.transaction_type }}">{{ tx.transaction_type|upper }}</td>
                <td>{{ tx.timestamp }}</td>
                <td>{{ tx.notes }}</td>
                <td>
                    <a href="/admin/transactions/{{ tx.id }}/edit" class="button button-warning button-small">Edit</a>
                    <a href="/admin/transactions/{{ tx.id }}/delete" class="button button-danger button-small">Delete</a>
                </td>
            </tr>
            {% endfor %}
        </table>
        
        <a href="/admin" class="button">Back to Dashboard</a>
        <a href="/admin/transactions/add" class="button button-secondary">Add Transaction</a>
    </div>
</body>
</html>
    """, transactions=transactions, filtered_transactions=filtered_transactions, unique_users=unique_users, unique_symbols=unique_symbols, user_filter=user_filter, symbol_filter=symbol_filter, type_filter=type_filter)

@app.route('/admin/stocks')
@admin_2fa_required
def admin_stocks():
    """Admin route to view stocks"""
    try:
        # Get real stock data from database
        stocks_query = Stock.query.all()
        
        # Format stock data
        stocks = []
        for stock in stocks_query:
            # Get username for the stock
            user = User.query.get(stock.user_id)
            username = user.username if user else 'Unknown'
            
            stocks.append({
                'id': stock.id,
                'user_id': stock.user_id,
                'username': username,
                'ticker': stock.ticker,
                'quantity': stock.quantity,
                'purchase_price': stock.purchase_price,
                'current_price': 0.0,  # Stock model doesn't have current_price field
                'purchase_date': stock.purchase_date.strftime('%Y-%m-%d')
            })
    except Exception as e:
        app.logger.error(f"Database error in admin_stocks: {str(e)}")
        # Fallback to mock data if database fails
        stocks = [
            {'id': 1, 'user_id': 1, 'username': 'witty-raven', 'ticker': 'AAPL', 'quantity': 5, 'purchase_price': 150.0, 'current_price': 180.0, 'purchase_date': '2023-01-15'},
            {'id': 2, 'user_id': 1, 'username': 'witty-raven', 'ticker': 'MSFT', 'quantity': 5, 'purchase_price': 250.0, 'current_price': 280.0, 'purchase_date': '2023-02-20'},
            {'id': 3, 'user_id': 2, 'username': 'user1', 'ticker': 'GOOGL', 'quantity': 2, 'purchase_price': 2800.0, 'current_price': 2900.0, 'purchase_date': '2023-03-10'},
            {'id': 4, 'user_id': 3, 'username': 'user2', 'ticker': 'AMZN', 'quantity': 1, 'purchase_price': 3200.0, 'current_price': 3400.0, 'purchase_date': '2023-04-05'},
        ]
    
    # Get filter parameters
    user_filter = request.args.get('user', '')
    ticker_filter = request.args.get('ticker', '')
    
    # Apply filters if provided
    filtered_stocks = stocks
    if user_filter:
        filtered_stocks = [s for s in filtered_stocks if str(s['user_id']) == user_filter]
    if ticker_filter:
        filtered_stocks = [s for s in filtered_stocks if s['ticker'].lower() == ticker_filter.lower()]
    
    # Get unique users and tickers for filters
    unique_users = list(set([(s['user_id'], s['username']) for s in stocks]))
    unique_tickers = list(set([s['ticker'] for s in stocks]))
    
    return render_template_string("""
<!DOCTYPE html>
<html>
<head>
    <title>Admin - Stocks</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 40px; }
        .container { max-width: 1000px; margin: 0 auto; }
        .button { 
            display: inline-block; 
            background: #4CAF50; 
            color: white; 
            padding: 10px 20px; 
            text-decoration: none; 
            border-radius: 5px; 
            margin-top: 20px;
            margin-right: 10px;
        }
        .button-secondary { background: #2196F3; }
        .button-warning { background: #FF9800; }
        .button-danger { background: #F44336; }
        .button-small { padding: 5px 10px; margin-top: 0; }
        table {
            width: 100%;
            border-collapse: collapse;
            margin-top: 20px;
        }
        th, td {
            padding: 8px;
            text-align: left;
            border-bottom: 1px solid #ddd;
        }
        th {
            background-color: #f2f2f2;
        }
        tr:hover {background-color: #f5f5f5;}
        .nav { 
            background: #333; 
            padding: 10px; 
            margin-bottom: 20px; 
            border-radius: 5px; 
        }
        .nav a { 
            color: white; 
            text-decoration: none; 
            margin-right: 15px; 
            padding: 5px 10px; 
        }
        .nav a:hover { 
            background: #555; 
            border-radius: 3px; 
        }
        .filters {
            margin: 20px 0;
            padding: 15px;
            background: #f9f9f9;
            border-radius: 5px;
            display: flex;
            flex-wrap: wrap;
            gap: 15px;
        }
        .filters select, .filters button {
            padding: 8px;
            border: 1px solid #ddd;
            border-radius: 4px;
        }
        .filters button {
            background: #4CAF50;
            color: white;
            border: none;
            cursor: pointer;
        }
        .profit { color: green; }
        .loss { color: red; }
        .summary {
            margin-top: 20px;
            padding: 15px;
            background: #e9f7ef;
            border-radius: 5px;
        }
        .summary h3 {
            margin-top: 0;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="nav">
            <a href="/admin">Dashboard</a>
            <a href="/admin/users">Users</a>
            <a href="/admin/transactions">Transactions</a>
            <a href="/admin/stocks">Stocks</a>
            <a href="/">Main Site</a>
        </div>
        
        <h1>Stock Management</h1>
        
        <div class="filters">
            <form method="get" action="/admin/stocks">
                <select name="user">
                    <option value="">All Users</option>
                    {% for user_id, username in unique_users %}
                    <option value="{{ user_id }}" {% if user_filter == user_id|string %}selected{% endif %}>{{ username }}</option>
                    {% endfor %}
                </select>
                
                <select name="ticker">
                    <option value="">All Tickers</option>
                    {% for ticker in unique_tickers %}
                    <option value="{{ ticker }}" {% if ticker_filter == ticker %}selected{% endif %}>{{ ticker }}</option>
                    {% endfor %}
                </select>
                
                <button type="submit">Filter</button>
                <a href="/admin/stocks" style="padding: 8px; text-decoration: none;">Clear Filters</a>
            </form>
        </div>
        
        <div class="summary">
            <h3>Stock Summary</h3>
            <p>Total Stocks: {{ filtered_stocks|length }}</p>
            <p>Total Value: ${{ '%0.2f'|format(filtered_stocks|sum(attribute='current_price')|float) }}</p>
        </div>
        
        <table>
            <tr>
                <th>ID</th>
                <th>User</th>
                <th>Ticker</th>
                <th>Quantity</th>
                <th>Purchase Price</th>
                <th>Current Price</th>
                <th>Total Value</th>
                <th>Profit/Loss</th>
                <th>Purchase Date</th>
                <th>Actions</th>
            </tr>
            {% for stock in filtered_stocks %}
            <tr>
                <td>{{ stock.id }}</td>
                <td>{{ stock.username }}</td>
                <td>{{ stock.ticker }}</td>
                <td>{{ stock.quantity }}</td>
                <td>${{ '%0.2f'|format(stock.purchase_price) }}</td>
                <td>${{ '%0.2f'|format(stock.current_price) }}</td>
                <td>${{ '%0.2f'|format(stock.quantity * stock.current_price) }}</td>
                {% set profit = (stock.current_price - stock.purchase_price) * stock.quantity %}
                <td class="{% if profit >= 0 %}profit{% else %}loss{% endif %}">
                    ${{ '%0.2f'|format(profit) }} ({{ '%0.1f'|format((stock.current_price - stock.purchase_price) / stock.purchase_price * 100) }}%)
                </td>
                <td>{{ stock.purchase_date }}</td>
                <td>
                    <a href="/admin/stocks/{{ stock.id }}/edit" class="button button-warning button-small">Edit</a>
                    <a href="/admin/stocks/{{ stock.id }}/delete" class="button button-danger button-small">Delete</a>
                </td>
            </tr>
            {% endfor %}
        </table>
        
        <a href="/admin" class="button">Back to Dashboard</a>
        <a href="/admin/stocks/add" class="button button-secondary">Add Stock</a>
    </div>
</body>
</html>
    """, stocks=stocks, filtered_stocks=filtered_stocks, unique_users=unique_users, unique_tickers=unique_tickers, user_filter=user_filter, ticker_filter=ticker_filter)

# Removed duplicate admin_user_detail route - using admin_interface.py blueprint instead

# ── Blueprint Registration ───────────────────────────────────────────────────
try:
    import sys
    from admin_interface import admin_bp
    app.register_blueprint(admin_bp, url_prefix='/admin')
    logger.info("Admin interface blueprint registered successfully")
except Exception as e:
    logger.warning(f"Could not register admin blueprint: {e}")

try:
    from leaderboard_routes import leaderboard_bp
    app.register_blueprint(leaderboard_bp)
    logger.info("Leaderboard blueprint registered successfully")
except Exception as e:
    logger.warning(f"Could not register leaderboard blueprint: {e}")

try:
    from mobile_api import mobile_api
    app.register_blueprint(mobile_api)
    logger.info("Mobile API blueprint registered successfully")
except Exception as e:
    logger.warning(f"Could not register mobile API blueprint: {e}")

try:
    from admin_cash_tracking import register_cash_tracking_routes
    register_cash_tracking_routes(app, db)
    logger.info("Cash tracking admin routes registered successfully")
except Exception as e:
    logger.warning(f"Could not register cash tracking routes: {e}")

try:
    from admin_phase_5_cache_clear import register_phase_5_cache_routes
    register_phase_5_cache_routes(app, db)
    logger.info("Phase 5 cache clear routes registered successfully")
except Exception as e:
    logger.warning(f"Could not register phase 5 cache clear routes: {e}")

try:
    from admin_phase_5_routes import register_phase_5_routes
    register_phase_5_routes(app, db)
    logger.info("Phase 5 admin routes registered successfully")
except Exception as e:
    logger.warning(f"Could not register phase 5 admin routes: {e}")

# Error handler
@app.errorhandler(500)
def internal_error(error):
    logger.error(f"500 error on {request.method} {request.path}: {str(error)}", exc_info=True)
    
    # Check if this is an API request
    if request.path.startswith('/api/'):
        return jsonify({
            'error': 'Internal Server Error',
            'status': 500,
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'path': request.path
        }), 500
    
    # Return a generic error page for HTML requests
    return render_template_string("""
<!DOCTYPE html>
<html>
<head>
    <title>Server Error</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 40px; }
        .container { max-width: 800px; margin: 0 auto; }
        .error { background: #f8d7da; padding: 15px; border-radius: 5px; }
    </style>
</head>
<body>
    <div class="container">
        <h1>Server Error</h1>
        <div class="error">
            <h2>500 - Internal Server Error</h2>
            <p>The server encountered an unexpected condition that prevented it from fulfilling the request.</p>
        </div>
        <p><a href="/">Return to Home</a></p>
    </div>
</body>
</html>
    """), 500

@app.route('/admin/transactions/<int:transaction_id>/edit', methods=['GET', 'POST'])
@admin_2fa_required
def admin_edit_transaction(transaction_id):
    """Admin route to edit a transaction"""
    # Get transaction by ID from database
    transaction = Transaction.query.get(transaction_id)
    if not transaction:
        flash('Transaction not found', 'danger')
        return redirect(url_for('admin_transactions'))
    
    # Get the user associated with this transaction
    user = User.query.get(transaction.user_id)
    if not user:
        flash('User not found for this transaction', 'danger')
        return redirect(url_for('admin_transactions'))
    
    if request.method == 'POST':
        try:
            # Update transaction with form data
            transaction.ticker = request.form['ticker']
            transaction.quantity = float(request.form['quantity'])
            transaction.price = float(request.form['price'])
            transaction.transaction_type = request.form['transaction_type']
            
            # Parse transaction date if provided
            transaction_date = request.form.get('date')
            if transaction_date:
                transaction.timestamp = datetime.strptime(transaction_date, '%Y-%m-%d')
            
            # Update notes if provided
            if 'notes' in request.form:
                # Store notes as an attribute if the Transaction model supports it
                # This assumes there's a notes field in the Transaction model
                # If not, you might need to modify the model or skip this part
                transaction.notes = request.form['notes']
            
            # Save changes to database
            db.session.commit()
            
            flash('Transaction updated successfully!', 'success')
            return redirect(url_for('admin_transactions'))
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error updating transaction: {str(e)}")
            flash(f'Error updating transaction: {str(e)}', 'danger')
    
    # Prepare transaction data for template
    transaction_data = {
        'id': transaction.id,
        'user_id': transaction.user_id,
        'username': user.username,
        'symbol': transaction.ticker,
        'shares': transaction.quantity,
        'price': transaction.price,
        'transaction_type': transaction.transaction_type,
        'date': transaction.timestamp.strftime('%Y-%m-%d') if transaction.timestamp else '',
        'notes': getattr(transaction, 'notes', '')
    }
    
    return render_template_string("""
<!DOCTYPE html>
<html>
<head>
    <title>Edit Transaction</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 40px; }
        .container { max-width: 800px; margin: 0 auto; }
        .button { 
            display: inline-block; 
            background: #4CAF50; 
            color: white; 
            padding: 10px 20px; 
            text-decoration: none; 
            border-radius: 5px; 
            margin-top: 20px;
            margin-right: 10px;
        }
        .button-secondary { background: #2196F3; }
        .button-warning { background: #FF9800; }
        .button-danger { background: #F44336; }
        .form-group {
            margin-bottom: 15px;
        }
        .form-group label {
            display: block;
            margin-bottom: 5px;
            font-weight: bold;
        }
        .form-group input, .form-group select, .form-group textarea {
            width: 100%;
            padding: 8px;
            border: 1px solid #ddd;
            border-radius: 4px;
            box-sizing: border-box;
        }
        .form-group textarea {
            height: 100px;
        }
        .nav { 
            background: #333; 
            padding: 10px; 
            margin-bottom: 20px; 
            border-radius: 5px; 
        }
        .nav a { 
            color: white; 
            text-decoration: none; 
            margin-right: 15px; 
            padding: 5px 10px; 
        }
        .nav a:hover { 
            background: #555; 
            border-radius: 3px; 
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="nav">
            <a href="/admin">Dashboard</a>
            <a href="/admin/users">Users</a>
            <a href="/admin/transactions">Transactions</a>
            <a href="/admin/stocks">Stocks</a>
            <a href="/">Main Site</a>
        </div>
        
        <h1>Edit Transaction</h1>
        
        <form method="post">
            <div class="form-group">
                <label for="user">User</label>
                <input type="text" id="user" name="user" value="{{ transaction_data.username }}" readonly>
            </div>
            
            <div class="form-group">
                <label for="ticker">Symbol</label>
                <input type="text" id="ticker" name="ticker" value="{{ transaction_data.ticker }}" required>
            </div>
            
            <div class="form-group">
                <label for="quantity">Shares</label>
                <input type="number" id="quantity" name="quantity" value="{{ transaction_data.quantity }}" step="0.01" required>
            </div>
            
            <div class="form-group">
                <label for="price">Price</label>
                <input type="number" id="price" name="price" value="{{ transaction_data.price }}" step="0.01" required>
            </div>
            
            <div class="form-group">
                <label for="transaction_type">Transaction Type</label>
                <select id="transaction_type" name="transaction_type" required>
                    <option value="buy" {% if transaction_data.transaction_type == 'buy' %}selected{% endif %}>Buy</option>
                    <option value="sell" {% if transaction_data.transaction_type == 'sell' %}selected{% endif %}>Sell</option>
                </select>
            </div>
            
            <div class="form-group">
                <label for="date">Date</label>
                <input type="date" id="date" name="date" value="{{ transaction_data.timestamp.strftime('%Y-%m-%d') }}" required>
            </div>
            
            <div class="form-group">
                <label for="notes">Notes</label>
                <textarea id="notes" name="notes">{{ transaction_data.notes }}</textarea>
            </div>
            
            <button type="submit" class="button button-warning">Update Transaction</button>
            <a href="/admin/transactions" class="button">Cancel</a>
        </form>
    </div>
</body>
</html>
    """, transaction=transaction)

@app.route('/admin/stocks/<int:stock_id>/edit', methods=['GET', 'POST'])
@admin_2fa_required
def admin_edit_stock(stock_id):
    """Admin route to edit a stock"""
    # Get stock by ID from database
    stock = Stock.query.get(stock_id)
    if not stock:
        flash('Stock not found', 'danger')
        return redirect(url_for('admin_stocks'))
    
    # Get the user associated with this stock
    user = User.query.get(stock.user_id)
    if not user:
        flash('User not found for this stock', 'danger')
        return redirect(url_for('admin_stocks'))
    
    if request.method == 'POST':
        try:
            # Update stock with form data
            stock.ticker = request.form['ticker']
            stock.quantity = float(request.form['quantity'])
            stock.purchase_price = float(request.form['purchase_price'])
            
            # Parse purchase date if provided
            purchase_date = request.form.get('purchase_date')
            if purchase_date:
                stock.purchase_date = datetime.strptime(purchase_date, '%Y-%m-%d')
            
            # Save changes to database
            db.session.commit()
            
            flash('Stock updated successfully!', 'success')
            return redirect(url_for('admin_stocks'))
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error updating stock: {str(e)}")
            flash(f'Error updating stock: {str(e)}', 'danger')
    
    # Prepare stock data for template
    stock_data = {
        'id': stock.id,
        'user_id': stock.user_id,
        'username': user.username,
        'ticker': stock.ticker,
        'quantity': stock.quantity,
        'purchase_price': stock.purchase_price,
        'current_price': stock.current_value() / stock.quantity if stock.quantity > 0 else 0,
        'purchase_date': stock.purchase_date.strftime('%Y-%m-%d') if stock.purchase_date else ''
    }
    
    return render_template_string("""
<!DOCTYPE html>
<html>
<head>
    <title>Edit Stock</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 40px; }
        .container { max-width: 800px; margin: 0 auto; }
        .button { 
            display: inline-block; 
            background: #4CAF50; 
            color: white; 
            padding: 10px 20px; 
            text-decoration: none; 
            border-radius: 5px; 
            margin-top: 20px;
            margin-right: 10px;
        }
        .button-secondary { background: #2196F3; }
        .button-warning { background: #FF9800; }
        .button-danger { background: #F44336; }
        .form-group {
            margin-bottom: 15px;
        }
        .form-group label {
            display: block;
            margin-bottom: 5px;
            font-weight: bold;
        }
        .form-group input, .form-group select {
            width: 100%;
            padding: 8px;
            border: 1px solid #ddd;
            border-radius: 4px;
            box-sizing: border-box;
        }
        .nav { 
            background: #333; 
            padding: 10px; 
            margin-bottom: 20px; 
            border-radius: 5px; 
        }
        .nav a { 
            color: white; 
            text-decoration: none; 
            margin-right: 15px; 
            padding: 5px 10px; 
        }
        .nav a:hover { 
            background: #555; 
            border-radius: 3px; 
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="nav">
            <a href="/admin">Dashboard</a>
            <a href="/admin/users">Users</a>
            <a href="/admin/transactions">Transactions</a>
            <a href="/admin/stocks">Stocks</a>
            <a href="/">Main Site</a>
        </div>
        
        <h1>Edit Stock</h1>
        
        <form method="post">
            <div class="form-group">
                <label for="user">User</label>
                <input type="text" id="user" name="user" value="{{ stock.username }}" readonly>
            </div>
            
            <div class="form-group">
                <label for="ticker">Ticker</label>
                <input type="text" id="ticker" name="ticker" value="{{ stock.ticker }}" required>
            </div>
            
            <div class="form-group">
                <label for="quantity">Quantity</label>
                <input type="number" id="quantity" name="quantity" value="{{ stock.quantity }}" step="0.01" required>
            </div>
            
            <div class="form-group">
                <label for="purchase_price">Purchase Price</label>
                <input type="number" id="purchase_price" name="purchase_price" value="{{ stock.purchase_price }}" step="0.01" required>
            </div>
            
            <div class="form-group">
                <label for="current_price">Current Price</label>
                <input type="number" id="current_price" name="current_price" value="{{ stock.current_price }}" step="0.01" required>
            </div>
            
            <div class="form-group">
                <label for="purchase_date">Purchase Date</label>
                <input type="date" id="purchase_date" name="purchase_date" value="{{ stock.purchase_date }}" required>
            </div>
            
            <button type="submit" class="button button-warning">Update Stock</button>
            <a href="/admin/stocks" class="button">Cancel</a>
        </form>
    </div>
</body>
</html>
    """, stock=stock)

# Debug endpoint to check environment and configuration
@app.route('/debug')
@admin_required
def debug_info():
    try:
        # Check template and static directories
        template_files = []
        static_files = []
        try:
            if os.path.exists(app.template_folder):
                template_files = os.listdir(app.template_folder)
        except Exception as e:
            template_files = [f"Error listing templates: {str(e)}"]
            
        try:
            if os.path.exists(app.static_folder):
                static_files = os.listdir(app.static_folder)
        except Exception as e:
            static_files = [f"Error listing static files: {str(e)}"]
        
        # Collect environment information
        env_info = {
            'VERCEL_ENV': os.environ.get('VERCEL_ENV'),
            'DATABASE_URL_EXISTS': bool(os.environ.get('DATABASE_URL')),
            'POSTGRES_PRISMA_URL_EXISTS': bool(os.environ.get('POSTGRES_PRISMA_URL')),
            'SECRET_KEY_EXISTS': bool(os.environ.get('SECRET_KEY')),
            'FLASK_APP': os.environ.get('FLASK_APP'),
            'FLASK_ENV': os.environ.get('FLASK_ENV'),
            'TEMPLATE_FOLDER': app.template_folder,
            'STATIC_FOLDER': app.static_folder,
            'SQLALCHEMY_DATABASE_URI': '[REDACTED]',
            'WORKING_DIRECTORY': os.getcwd(),
            'DIRECTORY_CONTENTS': os.listdir('.'),
            'TEMPLATE_EXISTS': os.path.exists(app.template_folder),
            'STATIC_EXISTS': os.path.exists(app.static_folder),
            'TEMPLATE_FILES': template_files[:10],  # Limit to first 10 files
            'STATIC_FILES': static_files[:10],      # Limit to first 10 files
            'PYTHON_VERSION': sys.version,
            'APP_ROOT_PATH': os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'ABSOLUTE_TEMPLATE_PATH': os.path.abspath(app.template_folder),
            'ABSOLUTE_STATIC_PATH': os.path.abspath(app.static_folder)
        }
        
        # Check if we can connect to the database
        db_status = 'Unknown'
        try:
            # Import text function at the top level to avoid import errors
            from sqlalchemy.sql import text
            db.session.execute(text('SELECT 1'))
            db_status = 'Connected'
        except Exception as e:
            db_status = f'Error: {str(e)}'
            
        env_info['DATABASE_STATUS'] = db_status
        
        return jsonify(env_info)
    except Exception as e:
        return jsonify({'error': str(e)})


@app.route('/admin/metrics')
@admin_2fa_required
def admin_metrics():
    """Get platform health metrics for admin dashboard"""
    try:
        from admin_metrics import get_admin_dashboard_metrics
        metrics = get_admin_dashboard_metrics()
        
        return jsonify({
            'success': True,
            'metrics': metrics
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/admin/update-metrics')
@admin_2fa_required
def admin_update_metrics():
    """Manually update platform metrics"""
    try:
        from admin_metrics import update_daily_metrics
        
        # Actually call the update function
        success = update_daily_metrics()
        
        if success:
            return jsonify({
                'success': True,
                'message': 'Platform metrics updated successfully'
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Failed to update metrics - check server logs'
            }), 500
        
    except Exception as e:
        import traceback
        return jsonify({
            'success': False,
            'error': str(e),
            'details': 'Check server logs'
        }), 500

@app.route('/api/portfolio/performance/<period>')
def get_portfolio_performance(period):
    """Get portfolio performance data for a specific time period - uses cached data for leaderboard users
    
    NOTE: Does NOT use @login_required to avoid HTML redirects on AJAX requests.
    Returns JSON 401 error instead of redirecting to login page.
    """
    try:
        logger.info(f"ROUTE HIT: /api/portfolio/performance/{period}")
        logger.info(f"Request method: {request.method}")
        logger.info(f"current_user.is_authenticated: {current_user.is_authenticated}")
        
        # Check authentication without redirect (API endpoints should return JSON, not HTML redirects)
        if not current_user.is_authenticated:
            logger.warning(f"Unauthenticated request to performance API")
            return jsonify({'error': 'User not authenticated'}), 401
        
        # Note: Removed signal-based timeout as it doesn't work in serverless environments
        # Vercel handles timeouts automatically
        from datetime import datetime, timedelta
        import json
        
        user_id = current_user.id
        logger.info(f"Performance API called for period {period}, user_id: {user_id}")
        
        period_upper = period.upper()
        
        # CRITICAL FIX: Query PRIMARY to bypass Vercel Postgres replica lag
        # Try to use pre-rendered chart data for leaderboard users (much faster!)
        from sqlalchemy import text
        chart_cache_data = None
        with db.engine.connect() as primary_conn:
            result = primary_conn.execute(text("""
                SELECT chart_data
                FROM user_portfolio_chart_cache
                WHERE user_id = :user_id AND period = :period
            """), {'user_id': user_id, 'period': period_upper})
            row = result.fetchone()
            if row:
                chart_cache_data = row[0]
        
        if chart_cache_data:
            try:
                # Convert Chart.js format to dashboard format
                cached_data = json.loads(chart_cache_data)
                
                # Extract performance percentages from Chart.js data
                datasets = cached_data.get('datasets', [])
                labels = cached_data.get('labels', [])
                
                if not datasets or len(datasets) == 0:
                    logger.warning(f"No datasets in cached data for user {user_id}, period {period_upper}")
                    raise ValueError("No datasets in cached chart data")
                
                portfolio_dataset = datasets[0].get('data', [])
                sp500_dataset = datasets[1].get('data', []) if len(datasets) > 1 else []
                
                if not portfolio_dataset:
                    logger.warning(f"No portfolio data in cached chart for user {user_id}, period {period_upper}")
                    raise ValueError("No portfolio data in cached chart")
                
                if not sp500_dataset:
                    logger.warning(f"No S&P 500 data in cached chart for user {user_id}, period {period_upper} - falling back to live calculation")
                    raise ValueError("No S&P 500 data in cached chart")
                
                # Convert to dashboard format: list of {date, portfolio, sp500}
                chart_data = []
                for i in range(min(len(labels), len(portfolio_dataset))):
                    chart_point = {
                        'date': labels[i],
                        'portfolio': portfolio_dataset[i],
                        'sp500': sp500_dataset[i] if i < len(sp500_dataset) else 0
                    }
                    chart_data.append(chart_point)
                
                # Get last values for display labels (these are cumulative % returns)
                portfolio_return = portfolio_dataset[-1] if portfolio_dataset else 0
                sp500_return = sp500_dataset[-1] if sp500_dataset else 0
                
                logger.info(f"✅ Using cached chart: portfolio={portfolio_return}%, sp500={sp500_return}%, points={len(chart_data)}")
                
                # Add leaderboard eligibility info
                eligibility_info = {}
                try:
                    from performance_calculator import get_leaderboard_eligibility
                    elig = get_leaderboard_eligibility(user_id, period_upper)
                    eligibility_info = {
                        'leaderboard_eligible': elig['eligible'],
                        'days_active': elig['days_active'],
                        'days_required': elig['days_required'],
                        'eligible_date': elig['eligible_date'].isoformat() if elig.get('eligible_date') else None,
                        'first_activity_date': elig['first_activity_date'].isoformat() if elig.get('first_activity_date') else None
                    }
                except Exception:
                    eligibility_info = {'leaderboard_eligible': True}
                
                return jsonify({
                    'portfolio_return': round(portfolio_return, 2),
                    'sp500_return': round(sp500_return, 2),
                    'chart_data': chart_data,
                    'period': period_upper,
                    'from_cache': True,
                    **eligibility_info
                })
                    
            except Exception as e:
                logger.warning(f"Failed to use cached chart data: {e} - falling back to live calculation")
        
        logger.info(f"No pre-rendered cache available - using live calculation for user {user_id}, period {period_upper}")
        
        # Fallback: Check session cache (5 minutes)
        cache_key = f"perf_{user_id}_{period}"
        cached_response = session.get(cache_key)
        cache_time = session.get(f"{cache_key}_time")
        
        if cached_response and cache_time:
            cache_age = datetime.now() - datetime.fromisoformat(cache_time)
            if cache_age < timedelta(minutes=5):
                logger.info(f"Using session cache for user {user_id}, period {period_upper}")
                return jsonify(cached_response)
        
        # Last resort: Live calculation using new unified calculator
        from leaderboard_utils import generate_chart_from_snapshots
        
        logger.info(f"Performing live calculation for user {user_id}, period {period_upper}")
        chart_data_chartjs = generate_chart_from_snapshots(user_id, period_upper)
        
        if not chart_data_chartjs:
            return jsonify({'error': 'No data available for this period'}), 404
        
        # Convert Chart.js format to dashboard format
        datasets = chart_data_chartjs.get('datasets', [])
        labels = chart_data_chartjs.get('labels', [])
        
        portfolio_dataset = datasets[0].get('data', []) if datasets else []
        sp500_dataset = datasets[1].get('data', []) if len(datasets) > 1 else []
        
        # Convert to dashboard format
        chart_data = []
        for i in range(min(len(labels), len(portfolio_dataset))):
            chart_data.append({
                'date': labels[i],
                'portfolio': portfolio_dataset[i],
                'sp500': sp500_dataset[i] if i < len(sp500_dataset) else 0
            })
        
        # Add leaderboard eligibility info
        eligibility_info = {}
        try:
            from performance_calculator import get_leaderboard_eligibility
            elig = get_leaderboard_eligibility(user_id, period_upper)
            eligibility_info = {
                'leaderboard_eligible': elig['eligible'],
                'days_active': elig['days_active'],
                'days_required': elig['days_required'],
                'eligible_date': elig['eligible_date'].isoformat() if elig.get('eligible_date') else None,
                'first_activity_date': elig['first_activity_date'].isoformat() if elig.get('first_activity_date') else None
            }
        except Exception:
            eligibility_info = {'leaderboard_eligible': True}
        
        performance_data = {
            'portfolio_return': chart_data_chartjs.get('portfolio_return', 0),
            'sp500_return': chart_data_chartjs.get('sp500_return', 0),
            'chart_data': chart_data,
            'period': period_upper,
            'from_cache': False,
            **eligibility_info
        }
        
        # Cache on-demand: Save to database for next time
        try:
            chart_cache = UserPortfolioChartCache.query.filter_by(
                user_id=user_id, period=period_upper
            ).first()
            
            if chart_cache:
                chart_cache.chart_data = json.dumps(chart_data_chartjs)
                chart_cache.generated_at = datetime.now()
                db.session.merge(chart_cache)
            else:
                chart_cache = UserPortfolioChartCache(
                    user_id=user_id,
                    period=period_upper,
                    chart_data=json.dumps(chart_data_chartjs),
                    generated_at=datetime.now()
                )
                db.session.add(chart_cache)
            
            db.session.commit()
            logger.info(f"✓ Cached chart on-demand for user {user_id}, period {period_upper}")
        except Exception as cache_error:
            logger.error(f"Failed to cache chart: {cache_error}")
            # Don't fail the request if caching fails
        
        # Also cache in session for immediate reuse
        session[cache_key] = performance_data
        session[f"{cache_key}_time"] = datetime.now().isoformat()
        
        return jsonify(performance_data)
        
    except Exception as e:
        logger.error(f"Performance calculation error: {e}")
        return jsonify({'error': 'Performance calculation failed'}), 500

@app.route('/api/portfolio/<int:user_id>/performance/<period>')
def get_public_portfolio_performance(user_id, period):
    """Get portfolio performance data for any user (public access for charts)"""
    try:
        from datetime import datetime, timedelta
        import json
        
        logger.info(f"Public performance API called for user {user_id}, period {period}")
        
        period_upper = period.upper()
        
        # Try to use pre-rendered chart data (same as private endpoint)
        chart_cache = UserPortfolioChartCache.query.filter_by(
            user_id=user_id, period=period_upper
        ).first()
        
        if chart_cache:
            try:
                cached_data = json.loads(chart_cache.chart_data)
                datasets = cached_data.get('datasets', [])
                labels = cached_data.get('labels', [])
                
                if datasets and len(datasets) > 0:
                    portfolio_dataset = datasets[0].get('data', [])
                    sp500_dataset = datasets[1].get('data', []) if len(datasets) > 1 else []
                    
                    if portfolio_dataset and sp500_dataset:
                        chart_data = []
                        for i in range(min(len(labels), len(portfolio_dataset))):
                            chart_point = {
                                'date': labels[i],
                                'portfolio': portfolio_dataset[i],
                                'sp500': sp500_dataset[i] if i < len(sp500_dataset) else 0
                            }
                            chart_data.append(chart_point)
                        
                        portfolio_return = portfolio_dataset[-1] if portfolio_dataset else 0
                        sp500_return = sp500_dataset[-1] if sp500_dataset else 0
                        
                        # Add eligibility info
                        elig_info = {}
                        try:
                            from performance_calculator import get_leaderboard_eligibility
                            elig = get_leaderboard_eligibility(user_id, period_upper)
                            elig_info = {
                                'leaderboard_eligible': elig['eligible'],
                                'days_active': elig['days_active'],
                                'days_required': elig['days_required'],
                                'eligible_date': elig['eligible_date'].isoformat() if elig.get('eligible_date') else None,
                                'first_activity_date': elig['first_activity_date'].isoformat() if elig.get('first_activity_date') else None
                            }
                        except Exception:
                            elig_info = {'leaderboard_eligible': True}
                        
                        return jsonify({
                            'portfolio_return': round(portfolio_return, 2),
                            'sp500_return': round(sp500_return, 2),
                            'chart_data': chart_data,
                            'period': period_upper,
                            'from_cache': True,
                            **elig_info
                        })
            except Exception as e:
                logger.warning(f"Failed to use cached chart data: {e}")
        
        # Fallback: Live calculation
        from portfolio_performance import PortfolioPerformanceCalculator
        calculator = PortfolioPerformanceCalculator()
        
        logger.info(f"Performing live calculation for public portfolio user {user_id}, period {period_upper}")
        performance_data = calculator.get_performance_data(user_id, period_upper)
        
        # Add eligibility info to live calculation result
        try:
            from performance_calculator import get_leaderboard_eligibility
            elig = get_leaderboard_eligibility(user_id, period_upper)
            performance_data['leaderboard_eligible'] = elig['eligible']
            performance_data['days_active'] = elig['days_active']
            performance_data['days_required'] = elig['days_required']
            performance_data['eligible_date'] = elig['eligible_date'].isoformat() if elig.get('eligible_date') else None
            performance_data['first_activity_date'] = elig['first_activity_date'].isoformat() if elig.get('first_activity_date') else None
        except Exception:
            performance_data['leaderboard_eligible'] = True
        
        return jsonify(performance_data)
        
    except Exception as e:
        logger.error(f"Public performance calculation error: {e}")
        return jsonify({'error': 'Performance calculation failed'}), 500

@app.route('/api/portfolio/snapshot')
@login_required
def create_portfolio_snapshot():
    """Create a portfolio snapshot for today"""
    try:
        # Import here to avoid circular imports
        from portfolio_performance import PortfolioPerformanceCalculator
        calculator = PortfolioPerformanceCalculator()
        
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': 'User not authenticated'}), 401
            
        calculator.create_daily_snapshot(user_id)
        return jsonify({'success': True})
    except Exception as e:
        logger.error(f"Snapshot creation error: {e}")
        return jsonify({'error': 'Snapshot creation failed'}), 500


@app.route('/cron/daily-snapshots')
def cron_daily_snapshots():
    """Cron endpoint for automated daily snapshot creation (call this daily at market close)"""
    try:
        auth_error = verify_cron_request()
        if auth_error:
            return auth_error
        
        # Import here to avoid circular imports
        import sys
        import os
        from datetime import date
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from portfolio_performance import performance_calculator
        
        # First, fetch today's S&P 500 data once (efficient - single API call)
        today = date.today()
        if today.weekday() < 5:  # Only on weekdays
            performance_calculator.get_sp500_data(today, today)
        
        # Get all users with stocks
        users_with_stocks = db.session.query(User.id).join(Stock).distinct().all()
        
        snapshots_created = 0
        errors = []
        
        for (user_id,) in users_with_stocks:
            try:
                performance_calculator.create_daily_snapshot(user_id)
                snapshots_created += 1
            except Exception as e:
                error_msg = f"Error for user {user_id}: {str(e)}"
                errors.append(error_msg)
                logger.error(error_msg)
        
        return jsonify({
            'success': True,
            'snapshots_created': snapshots_created,
            'users_processed': len(users_with_stocks),
            'errors': errors,
            'sp500_updated': today.weekday() < 5,
            'timestamp': today.isoformat()
        })
        
    except Exception as e:
        logger.error(f"Cron daily snapshots error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/admin/create-tables')
@admin_2fa_required
def create_tables():
    """Create all database tables"""
    try:
        # Create the new tables
        from models import db, User, Stock, Transaction, PortfolioSnapshot, StockInfo, SubscriptionTier, Subscription, SMSNotification, LeaderboardCache, UserPortfolioChartCache, AlphaVantageAPILog, PlatformMetrics, UserActivity
        
        current_time = datetime.now()
        
        results = {
            'timestamp': current_time.isoformat(),
        # Rest of your code remains the same
            'environment_check': {},
            'spy_data_test': {},
            'user_count': 0,
            'sample_snapshots': [],
            'chart_generation_test': {},
            'errors': []
        }
        
        # Check environment variables
        try:
            intraday_token = os.environ.get('INTRADAY_CRON_TOKEN')
            cron_secret = os.environ.get('CRON_SECRET')
            alpha_key = os.environ.get('ALPHA_VANTAGE_API_KEY')
            
            results['environment_check'] = {
                'intraday_token_exists': bool(intraday_token),
                'cron_secret_exists': bool(cron_secret),
                'alpha_vantage_key_exists': bool(alpha_key),
                'intraday_token_length': len(intraday_token) if intraday_token else 0
            }
        except Exception as e:
            results['errors'].append(f"Environment check error: {str(e)}")
        
        # Test SPY data collection
        try:
            calculator = PortfolioPerformanceCalculator()
            spy_data = calculator.get_stock_data('SPY')
            
            if spy_data and spy_data.get('price'):
                spy_price = spy_data['price']
                sp500_value = spy_price * 10
                
                results['spy_data_test'] = {
                    'success': True,
                    'spy_price': spy_price,
                    'sp500_equivalent': sp500_value,
                    'data_source': 'AlphaVantage'
                }
            else:
                results['spy_data_test'] = {
                    'success': False,
                    'error': 'Failed to fetch SPY data'
                }
        except Exception as e:
            results['spy_data_test'] = {
                'success': False,
                'error': str(e)
            }
            results['errors'].append(f"SPY data test error: {str(e)}")
        
        # Check user count and create sample snapshots
        try:
            users = User.query.all()
            results['user_count'] = len(users)
            
            # Create sample intraday snapshots for first 3 users
            for i, user in enumerate(users[:3]):
                try:
                    portfolio_value = calculator.calculate_portfolio_value(user.id)
                    
                    # Create test snapshot
                    test_snapshot = PortfolioSnapshotIntraday(
                        user_id=user.id,
                        timestamp=current_time,
                        total_value=portfolio_value
                    )
                    db.session.add(test_snapshot)
                    
                    results['sample_snapshots'].append({
                        'user_id': user.id,
                        'portfolio_value': portfolio_value,
                        'timestamp': current_time.isoformat()
                    })
                    
                except Exception as e:
                    results['errors'].append(f"Error creating snapshot for user {user.id}: {str(e)}")
        
        except Exception as e:
            results['errors'].append(f"User processing error: {str(e)}")
        
        # Test basic chart data structure
        try:
            # Simple test without full chart generation
            results['chart_generation_test'] = {
                'success': True,
                'note': 'Chart generation system ready - full test requires market hours'
            }
        
        except Exception as e:
            results['chart_generation_test'] = {
                'success': False,
                'error': str(e)
            }
            results['errors'].append(f"Chart generation test error: {str(e)}")
        
        # Commit test data
        try:
            db.session.commit()
            logger.info("Test intraday collection completed successfully")
        except Exception as e:
            db.session.rollback()
            error_msg = f"Database commit failed: {str(e)}"
            results['errors'].append(error_msg)
            logger.error(error_msg)
        
        return jsonify({
            'success': True,
            'message': 'Market close processing completed',
            'results': results
        }), 200
    
    except Exception as e:
        logger.error(f"Unexpected error in market close: {str(e)}")
        return jsonify({'error': f'Unexpected error: {str(e)}'}), 500


@app.route('/admin/process-queued-trades')
@admin_2fa_required
def admin_process_queued_trades():
    """Manually trigger processing of all queued after-hours email trades.
    Use ?retry_failed=1 to reset recently failed trades back to queued first."""
    try:
        if request.args.get('retry_failed'):
            from models import QueuedEmailTrade
            failed = QueuedEmailTrade.query.filter_by(status='failed').all()
            for qt in failed:
                qt.status = 'queued'
                qt.error_message = None
                qt.executed_at = None
            db.session.commit()
            logger.info(f"Reset {len(failed)} failed trades back to queued")

        from services.trading_email import process_queued_trades
        result = process_queued_trades()
        return jsonify({'success': True, 'result': result}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/admin/run-migration')
@admin_2fa_required
def run_migration():
    """Add missing columns to existing tables. Use ?step=N to run one at a time.
    
    Steps:
      1 - email_notifications_enabled
      2 - push_notifications_enabled
      3 - phone_number
      4 - default_notification_method
      5 - leaderboard_eligible
      6 - create all new tables
      all - run all steps 1-6 in sequence, skipping columns that already exist
    
    No step param = show instructions.
    """
    from models import db
    
    step = request.args.get('step')
    
    # Helper: check if column exists on a table
    def column_exists(table, column):
        result = db.session.execute(db.text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name = :tbl AND column_name = :col"
        ), {'tbl': table, 'col': column})
        return result.fetchone() is not None
    
    # Each migration: (table, column, type, default_value_or_None)
    column_migrations = [
        ('user', 'email_notifications_enabled', 'BOOLEAN', 'true'),
        ('user', 'push_notifications_enabled', 'BOOLEAN', 'true'),
        ('user', 'phone_number', 'VARCHAR(20)', None),
        ('user', 'default_notification_method', 'VARCHAR(10)', "'email'"),
        ('user', 'leaderboard_eligible', 'BOOLEAN', 'true'),
    ]
    
    if not step:
        return jsonify({
            'instructions': 'Add ?step=all to run everything, or ?step=1 through ?step=6 individually',
            'steps': {i+1: f'{m[0]}.{m[1]}' for i, m in enumerate(column_migrations)},
            'step_6': 'create_all_tables',
        })
    
    # Run all steps
    if step == 'all':
        results = []
        for i, (table, col, col_type, default) in enumerate(column_migrations):
            if column_exists(table, col):
                results.append({'step': i+1, 'column': f'{table}.{col}', 'status': 'already_exists'})
            else:
                try:
                    db.session.execute(db.text(f'ALTER TABLE "{table}" ADD COLUMN {col} {col_type}'))
                    if default is not None:
                        db.session.execute(db.text(f'ALTER TABLE "{table}" ALTER COLUMN {col} SET DEFAULT {default}'))
                    db.session.commit()
                    results.append({'step': i+1, 'column': f'{table}.{col}', 'status': 'created'})
                except Exception as e:
                    db.session.rollback()
                    results.append({'step': i+1, 'column': f'{table}.{col}', 'status': 'error', 'error': str(e)})
        # Step 6: create_all
        try:
            db.create_all()
            results.append({'step': 6, 'action': 'create_all_tables', 'status': 'ok'})
        except Exception as e:
            results.append({'step': 6, 'action': 'create_all_tables', 'status': 'error', 'error': str(e)})
        return jsonify({'success': True, 'results': results})
    
    step = int(step) if step.isdigit() else 0
    
    if step == 6:
        try:
            db.create_all()
            return jsonify({'success': True, 'step': 6, 'action': 'create_all_tables', 'status': 'ok'})
        except Exception as e:
            return jsonify({'success': False, 'step': 6, 'error': str(e)})
    
    if step < 1 or step > 5:
        return jsonify({'error': f'Invalid step {step}. Use 1-6 or all.'}), 400
    
    table, col, col_type, default = column_migrations[step - 1]
    if column_exists(table, col):
        return jsonify({'success': True, 'step': step, 'column': f'{table}.{col}', 'status': 'already_exists'})
    
    try:
        db.session.execute(db.text(f'ALTER TABLE "{table}" ADD COLUMN {col} {col_type}'))
        if default is not None:
            db.session.execute(db.text(f'ALTER TABLE "{table}" ALTER COLUMN {col} SET DEFAULT {default}'))
        db.session.commit()
        return jsonify({'success': True, 'step': step, 'column': f'{table}.{col}', 'status': 'created'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'step': step, 'column': f'{table}.{col}', 'error': str(e)})


@app.route('/admin/migrate-push-notification-defaults', methods=['GET', 'POST'])
@admin_2fa_required
def admin_migrate_push_notification_defaults():
    """One-shot data migration: turn trade-alert push back ON for existing
    mobile subscriptions that were created with it disabled.

    Why: the admin/bot comp-subscription creator (`mobile_api.bot_subscribe`)
    previously hardcoded `push_notifications_enabled=False`, contradicting the
    MobileSubscription model default (True) and the app's "on by default"
    expectation, so every comped/bot subscriber silently got email but no push.
    Real store purchases (`iap_validation_service`) already set True, so the
    only affected rows are comped/bot subs.

    Flips ACTIVE subscriptions whose flag is False or NULL back to True.
    DRY-RUN by default (lists affected rows, changes nothing). Add ?commit=true
    to apply. Idempotent — re-running after a commit affects 0 rows. Subscribers
    can still opt out per-subscription via PUT /notifications/settings.
    """
    from models import db, MobileSubscription
    from sqlalchemy import or_

    commit = request.args.get('commit', 'false').lower() in ('1', 'true', 'yes')

    try:
        affected = MobileSubscription.query.filter(
            MobileSubscription.status == 'active',
            or_(
                MobileSubscription.push_notifications_enabled.is_(False),
                MobileSubscription.push_notifications_enabled.is_(None),
            ),
        ).all()

        rows = [{
            'subscription_id': s.id,
            'subscriber_id': s.subscriber_id,
            'subscribed_to_id': s.subscribed_to_id,
            'created_at': s.created_at.isoformat() if s.created_at else None,
        } for s in affected]

        if commit and affected:
            for s in affected:
                s.push_notifications_enabled = True
            db.session.commit()

        return jsonify({
            'mode': 'commit' if commit else 'dry_run',
            'affected_count': len(rows),
            'affected': rows,
            'note': ('Flipped to True.' if commit
                     else 'DRY-RUN: nothing changed. Re-run with ?commit=true to apply.'),
        })
    except Exception as e:
        db.session.rollback()
        logger.error(f"migrate-push-notification-defaults error: {e}")
        return jsonify({'error': str(e)}), 500


# ─── Phase A: Portfolio data correctness admin tools (May 2026) ─────────────
#
# These three endpoints fix the "Wolff has zombie 0-share rows", "SLA shows
# 1100% gain", and "AV fetching GLTR/SOC?" issues all at once. They are SAFE
# to run repeatedly — each is idempotent or read-only.
#
# Run order after deploy:
#   1. POST /admin/cleanup-zero-share-stocks  (delete zombie rows)
#   2. POST /admin/recompute-cost-basis       (fix stale Stock.purchase_price)
#   3. GET  /admin/inspect-ticker?ticker=GLTR (verify AV fetches work)

@app.route('/admin/cleanup-zero-share-stocks', methods=['GET', 'POST'])
@admin_2fa_required
def admin_cleanup_zero_share_stocks():
    """Delete every Stock row where quantity is 0 or NULL.

    Several bot-trade sell paths (`mobile_api.py`:3955, 4691, 4839, 4988) do
    `stock.quantity -= qty` and forget to delete the row when it hits zero.
    Over months of bot activity this accumulates zombie Stock rows that show
    up in users' Holdings lists with no shares but still occupying space.

    Idempotent. Returns per-user breakdown so you can audit which users were
    affected. The Holdings render endpoints now also filter `quantity > 0`
    client-side, so this is purely garbage collection — running it doesn't
    change what users see, it just keeps the DB clean.

    Use `?dry_run=1` to preview without deleting.
    """
    from models import db, Stock, User
    from sqlalchemy import or_

    dry_run = request.args.get('dry_run') in ('1', 'true', 'yes')

    try:
        zombies = Stock.query.filter(
            or_(Stock.quantity == 0, Stock.quantity.is_(None))
        ).all()

        # Build a per-user summary BEFORE we delete (we lose the rows after).
        by_user = {}
        for s in zombies:
            by_user.setdefault(s.user_id, []).append(s.ticker)

        # Look up usernames so the response is human-readable.
        user_lookup = {}
        if by_user:
            uids = list(by_user.keys())
            for u in User.query.filter(User.id.in_(uids)).all():
                user_lookup[u.id] = u.public_name

        breakdown = [
            {
                'user_id': uid,
                'username': user_lookup.get(uid, f'user_{uid}'),
                'tickers': sorted(tickers),
                'count': len(tickers),
            }
            for uid, tickers in by_user.items()
        ]
        breakdown.sort(key=lambda x: -x['count'])

        if dry_run:
            return jsonify({
                'success': True,
                'dry_run': True,
                'total_zombies': len(zombies),
                'breakdown': breakdown,
            })

        # Actually delete.
        for s in zombies:
            db.session.delete(s)
        db.session.commit()

        return jsonify({
            'success': True,
            'dry_run': False,
            'deleted': len(zombies),
            'breakdown': breakdown,
        })

    except Exception as e:
        db.session.rollback()
        logger.error(f"cleanup_zero_share_stocks failed: {e}")
        import traceback
        return jsonify({'success': False, 'error': str(e), 'traceback': traceback.format_exc()}), 500


@app.route('/admin/recompute-cost-basis', methods=['GET', 'POST'])
@admin_2fa_required
def admin_recompute_cost_basis():
    """Replay every user's Transaction history to derive the *correct*
    `Stock.purchase_price` (weighted-average cost basis).

    Why this exists
    ---------------
    `Stock.purchase_price` is meant to be the running weighted-average cost
    basis for a ticker, updated on every BUY using:
        new_avg = (old_qty * old_avg + buy_qty * buy_price) / (old_qty + buy_qty)
    However historical data has been hand-edited several times (chart fixes,
    ticker symbol corrections, snapshot rebuilds) without preserving cost
    basis. This is why some positions show absurd gains:
        - SLA "+1100%" \u2014 purchase_price is stale at a tiny old value.
        - AAPL "+205%" \u2014 same root cause.
        - NVDA shows the avg price but no gain \u2014 purchase_price = 0/NULL,
          which trips the `purchasePrice > 0` guard in `Holding.gainPercent`
          (ios/Models.swift:134) so the UI falls back to the "$X avg" label.

    Algorithm (FIFO weighted average)
    ---------------------------------
    For each (user, ticker), walk Transactions in chronological order:
        running_cost = 0.0
        running_qty  = 0.0
        for txn in sorted_transactions:
            if txn.type in ('buy', 'initial'):
                running_cost += txn.qty * txn.price
                running_qty  += txn.qty
            elif txn.type == 'sell' and running_qty > 0:
                # Sells DON'T change the average cost \u2014 they pull pro-rata
                # cost off the books. avg_at_sell = running_cost / running_qty.
                avg_at_sell = running_cost / running_qty
                running_cost -= min(txn.qty, running_qty) * avg_at_sell
                running_qty  -= min(txn.qty, running_qty)

    Final `purchase_price = running_cost / running_qty` if `running_qty > 0`.

    Query params:
        user_id     \u2014 if set, only recompute that user. Otherwise all users.
        dry_run     \u2014 ?dry_run=1 returns diffs without writing.
        username    \u2014 alternative to user_id, looks up by username/display_name.

    The endpoint NEVER touches `Stock.quantity` \u2014 only the cost basis. If a
    user's current `quantity` doesn't match the sum of (buys - sells), that's
    a separate data integrity issue and is reported in the response.
    """
    from models import db, Stock, User, Transaction
    from sqlalchemy import asc

    dry_run = request.args.get('dry_run') in ('1', 'true', 'yes')
    user_id = request.args.get('user_id', type=int)
    username = request.args.get('username')

    # Resolve target user(s).
    try:
        if user_id:
            users = User.query.filter_by(id=user_id).all()
        elif username:
            u = User.query.filter(
                (User.username == username) | (User.display_name == username)
            ).first()
            users = [u] if u else []
        else:
            # Cap at 1000 to avoid runaway on Vercel. The realistic count is
            # ~hundreds, so this is a generous ceiling.
            users = User.query.limit(1000).all()
    except Exception as e:
        return jsonify({'success': False, 'error': f'user lookup failed: {e}'}), 500

    if not users:
        return jsonify({'success': False, 'error': 'no matching users'}), 404

    audit = []
    updated = 0
    quantity_mismatches = []

    try:
        for u in users:
            stocks = Stock.query.filter_by(user_id=u.id).all()
            if not stocks:
                continue

            # Pull all this user's transactions ONCE, sort by timestamp.
            txns = (
                Transaction.query
                .filter_by(user_id=u.id)
                .order_by(asc(Transaction.timestamp))
                .all()
            )
            # Group by ticker (upper-cased to be safe).
            by_ticker = {}
            for t in txns:
                by_ticker.setdefault((t.ticker or '').upper(), []).append(t)

            for stock in stocks:
                key = (stock.ticker or '').upper()
                ticker_txns = by_ticker.get(key, [])
                if not ticker_txns:
                    # Stock row exists but no transaction history \u2014 leave alone.
                    continue

                running_cost = 0.0
                running_qty = 0.0
                for t in ticker_txns:
                    ttype = (t.transaction_type or '').lower()
                    qty = float(t.quantity or 0)
                    price = float(t.price or 0)
                    if qty <= 0:
                        continue
                    if ttype in ('buy', 'initial', 'purchase'):
                        running_cost += qty * price
                        running_qty += qty
                    elif ttype in ('sell', 'sale'):
                        if running_qty <= 0:
                            continue
                        avg_at_sell = running_cost / running_qty
                        sold = min(qty, running_qty)
                        running_cost -= sold * avg_at_sell
                        running_qty -= sold

                if running_qty <= 0:
                    # Replayed history says they have no shares \u2014 but Stock
                    # row still exists. Will be caught by cleanup endpoint.
                    continue

                new_avg = round(running_cost / running_qty, 6)
                old_avg = round(float(stock.purchase_price or 0), 6)

                # Sanity check: replayed quantity should match the current
                # Stock.quantity. If it doesn't, the bot trade pipeline (which
                # doesn't always write Transaction rows for every action) has
                # drifted. We report but DON'T fix \u2014 quantity belongs to a
                # different reconciliation pass.
                cur_qty = round(float(stock.quantity or 0), 6)
                if abs(cur_qty - round(running_qty, 6)) > 0.001:
                    quantity_mismatches.append({
                        'user_id': u.id,
                        'username': u.public_name,
                        'ticker': stock.ticker,
                        'stock_quantity': cur_qty,
                        'replayed_quantity': round(running_qty, 6),
                        'delta': round(cur_qty - running_qty, 6),
                    })

                if abs(new_avg - old_avg) > 0.0001:
                    audit.append({
                        'user_id': u.id,
                        'username': u.public_name,
                        'ticker': stock.ticker,
                        'old_purchase_price': old_avg,
                        'new_purchase_price': new_avg,
                        'quantity': cur_qty,
                        'transactions_replayed': len(ticker_txns),
                    })
                    if not dry_run:
                        stock.purchase_price = new_avg
                        updated += 1

        if not dry_run:
            db.session.commit()

        return jsonify({
            'success': True,
            'dry_run': dry_run,
            'users_scanned': len(users),
            'cost_basis_updates': updated if not dry_run else len(audit),
            'audit': audit[:200],  # cap response size
            'audit_truncated': len(audit) > 200,
            'quantity_mismatches': quantity_mismatches[:50],
            'quantity_mismatch_count': len(quantity_mismatches),
        })

    except Exception as e:
        db.session.rollback()
        logger.error(f"recompute_cost_basis failed: {e}")
        import traceback
        return jsonify({'success': False, 'error': str(e), 'traceback': traceback.format_exc()}), 500


@app.route('/admin/inspect-ticker', methods=['GET'])
@admin_2fa_required
def admin_inspect_ticker():
    """Diagnostic endpoint to verify that AlphaVantage is successfully
    pricing a given ticker (e.g. GLTR, SOC) and that the daily-bars cache
    is being populated for it.

    Returns three blocks:

    1. `live_av_quote` \u2014 hits AV REALTIME_BULK_QUOTES once for this single
       ticker. Confirms AV recognizes the symbol and returns a fresh price.
    2. `cached_daily_bars` \u2014 last N rows from the `daily_price_bar` table
       (newest first). Lets you eyeball whether close prices are fluctuating
       realistically day-to-day. If empty, the daily-bars cron hasn't run
       yet for this ticker (or it's not in the bot universe).
    3. `in_bot_universe` \u2014 boolean, whether this ticker is part of the
       UNIVERSE dict in bot_data_hub.py (i.e., the bots will trade it).
       GLTR/SOC are NOT in the universe today, which is fine \u2014 the
       universe is for BOT trading, not for user holdings price tracking.

    Query params:
        ticker   \u2014 required, case-insensitive (e.g. ?ticker=GLTR)
        days     \u2014 how many recent bars to return, default 15, max 100
    """
    from models import db, DailyPriceBar
    from sqlalchemy import desc

    ticker = (request.args.get('ticker') or '').upper().strip()
    if not ticker:
        return jsonify({'error': 'ticker query param required'}), 400

    try:
        days = min(int(request.args.get('days', 15)), 100)
    except (TypeError, ValueError):
        days = 15

    response = {
        'ticker': ticker,
        'in_bot_universe': False,
        'live_av_quote': None,
        'cached_daily_bars': [],
        'cached_bar_count': 0,
    }

    # ── (1) Bot universe membership ───────────────────────────────────────
    try:
        from bot_data_hub import get_all_tickers
        response['in_bot_universe'] = ticker in get_all_tickers()
    except Exception as e:
        response['in_bot_universe_error'] = str(e)

    # ── (2) Live AV quote (REALTIME_BULK_QUOTES for one symbol) ───────────
    # This is the SAME path that powers user-holding price fetches via
    # portfolio_performance.PortfolioPerformanceCalculator.get_batch_stock_data,
    # so success here means GLTR/SOC will price correctly in Holdings too.
    try:
        import os as _os
        import requests as _req
        api_key = _os.environ.get('ALPHA_VANTAGE_API_KEY', '')
        if not api_key:
            response['live_av_quote'] = {'status': 'error', 'reason': 'ALPHA_VANTAGE_API_KEY not set'}
        else:
            url = (
                f'https://www.alphavantage.co/query'
                f'?function=REALTIME_BULK_QUOTES&symbol={ticker}'
                f'&entitlement=realtime&apikey={api_key}'
            )
            r = _req.get(url, timeout=8)
            data = r.json() if r.status_code == 200 else {}
            bulk = data.get('data') or []
            if bulk:
                q = bulk[0]
                response['live_av_quote'] = {
                    'status': 'success',
                    'price': float(q.get('close') or 0),
                    'volume': int(float(q.get('volume') or 0)),
                    'high': float(q.get('high') or 0),
                    'low': float(q.get('low') or 0),
                    'timestamp_utc': q.get('timestamp'),
                    'http_status': r.status_code,
                }
            else:
                # AV sometimes returns 200 with an error message body.
                response['live_av_quote'] = {
                    'status': 'no_data',
                    'http_status': r.status_code,
                    'body_preview': str(data)[:300],
                }
    except Exception as e:
        response['live_av_quote'] = {'status': 'error', 'error': str(e)}

    # ── (3) Cached daily bars (from DailyPriceBar table) ──────────────────
    try:
        bars = (
            DailyPriceBar.query
            .filter_by(ticker=ticker)
            .order_by(desc(DailyPriceBar.date))
            .limit(days)
            .all()
        )
        response['cached_bar_count'] = len(bars)
        response['cached_daily_bars'] = [
            {
                'date': b.date.isoformat() if b.date else None,
                'open': float(b.open) if b.open is not None else None,
                'high': float(b.high) if b.high is not None else None,
                'low': float(b.low) if b.low is not None else None,
                'close': float(b.close) if b.close is not None else None,
                'volume': int(b.volume) if b.volume is not None else None,
                'source': b.source,
                'fetched_at': b.fetched_at.isoformat() if b.fetched_at else None,
            }
            for b in bars
        ]
    except Exception as e:
        # Likely "relation daily_price_bar does not exist" \u2014 user hasn't
        # hit /admin/run-migration?step=6 yet.
        response['cached_daily_bars_error'] = str(e)

    return jsonify(response)


@app.route('/admin/inspect-position', methods=['GET'])
@admin_2fa_required
def admin_inspect_position():
    """Dump everything we know about (user, ticker) tuples so we can debug
    cost-basis / gain-percentage mismatches.

    Why this exists
    ---------------
    `/admin/recompute-cost-basis` audit only returns rows where the new
    weighted-average DIFFERS from the stored one AND there's at least one
    Transaction row. Tickers like SLA / NVDA might have:
        - no Transaction rows at all (was added via initial-seed or admin
          tweak, never wrote a txn);
        - Transaction rows under a different ticker symbol (renamed/merged);
        - matching purchase_price already, masking a real bug.
    This endpoint shows the raw truth so we know which case applies.

    Query params:
        username   \u2014 required (or user_id)
        user_id    \u2014 alternative
        tickers    \u2014 required, comma-separated (e.g. ?tickers=SLA,NVDA,AAPL)

    Response per ticker:
        stock_row             \u2014 current Stock row (qty, purchase_price, date)
        transactions          \u2014 every Transaction for this user+ticker
        replay_summary        \u2014 what recompute would compute (matches the
                                weighted-avg algorithm in recompute-cost-basis)
        current_market_price  \u2014 fresh AV REALTIME_BULK_QUOTES
        gains                 \u2014 stored vs. replayed gain $ and %, so we can
                                see exactly which numbers are inflated
    """
    from models import db, Stock, User, Transaction
    from sqlalchemy import asc

    username = request.args.get('username')
    user_id = request.args.get('user_id', type=int)
    tickers_param = (request.args.get('tickers') or '').strip()
    if not tickers_param:
        return jsonify({'error': 'tickers query param required (comma-separated)'}), 400

    tickers = [t.strip().upper() for t in tickers_param.split(',') if t.strip()]
    if not tickers:
        return jsonify({'error': 'no valid tickers supplied'}), 400

    # Resolve user.
    user = None
    if user_id:
        user = User.query.filter_by(id=user_id).first()
    elif username:
        user = User.query.filter(
            (User.username == username) | (User.display_name == username)
        ).first()
    if not user:
        return jsonify({'error': 'user not found'}), 404

    # Try to fetch live AV prices in one bulk call to keep this fast.
    live_prices = {}
    try:
        import os as _os
        import requests as _req
        api_key = _os.environ.get('ALPHA_VANTAGE_API_KEY', '')
        if api_key and tickers:
            url = (
                f'https://www.alphavantage.co/query'
                f'?function=REALTIME_BULK_QUOTES&symbol={",".join(tickers)}'
                f'&entitlement=realtime&apikey={api_key}'
            )
            r = _req.get(url, timeout=8)
            data = r.json() if r.status_code == 200 else {}
            for q in (data.get('data') or []):
                sym = (q.get('symbol') or '').upper()
                if sym:
                    live_prices[sym] = float(q.get('close') or 0)
    except Exception as e:
        live_prices['_error'] = str(e)

    results = []
    for ticker in tickers:
        block = {'ticker': ticker, 'user_id': user.id, 'username': user.public_name}

        # Stock row.
        stock = Stock.query.filter_by(user_id=user.id, ticker=ticker).first()
        # Also try lowercase / alternate casing in case of legacy data.
        if not stock:
            stock = (
                Stock.query.filter(Stock.user_id == user.id)
                .filter(db.func.upper(Stock.ticker) == ticker)
                .first()
            )

        if stock:
            block['stock_row'] = {
                'id': stock.id,
                'ticker_as_stored': stock.ticker,
                'quantity': float(stock.quantity or 0),
                'purchase_price': float(stock.purchase_price or 0),
                'purchase_date': stock.purchase_date.isoformat() if stock.purchase_date else None,
            }
        else:
            block['stock_row'] = None

        # All Transactions for this user+ticker (case-insensitive).
        txns = (
            Transaction.query
            .filter(Transaction.user_id == user.id)
            .filter(db.func.upper(Transaction.ticker) == ticker)
            .order_by(asc(Transaction.timestamp))
            .all()
        )
        block['transaction_count'] = len(txns)
        block['transactions'] = [
            {
                'id': t.id,
                'timestamp': t.timestamp.isoformat() if t.timestamp else None,
                'type': t.transaction_type,
                'quantity': float(t.quantity or 0),
                'price': float(t.price or 0),
                'notional': round(float(t.quantity or 0) * float(t.price or 0), 2),
                'ticker_as_stored': t.ticker,
            }
            for t in txns
        ]

        # Replay (same algorithm as /admin/recompute-cost-basis).
        running_cost = 0.0
        running_qty = 0.0
        for t in txns:
            ttype = (t.transaction_type or '').lower()
            qty = float(t.quantity or 0)
            price = float(t.price or 0)
            if qty <= 0:
                continue
            if ttype in ('buy', 'initial', 'purchase'):
                running_cost += qty * price
                running_qty += qty
            elif ttype in ('sell', 'sale'):
                if running_qty <= 0:
                    continue
                avg_at_sell = running_cost / running_qty
                sold = min(qty, running_qty)
                running_cost -= sold * avg_at_sell
                running_qty -= sold

        replay_avg = round(running_cost / running_qty, 6) if running_qty > 0 else None
        block['replay_summary'] = {
            'replayed_quantity': round(running_qty, 6),
            'replayed_total_cost': round(running_cost, 2),
            'replayed_avg_cost_per_share': replay_avg,
        }

        # Live price + gain calculations.
        live_px = live_prices.get(ticker)
        block['current_market_price'] = live_px

        if stock and live_px is not None:
            qty = float(stock.quantity or 0)
            current_value = qty * live_px

            # As stored (the number the UI is showing today).
            stored_avg = float(stock.purchase_price or 0)
            stored_basis = qty * stored_avg
            block['gains'] = {
                'stored': {
                    'avg_cost_per_share': stored_avg,
                    'total_cost_basis': round(stored_basis, 2),
                    'current_value': round(current_value, 2),
                    'gain_dollars': round(current_value - stored_basis, 2),
                    'gain_percent': round(
                        ((current_value - stored_basis) / stored_basis * 100)
                        if stored_basis > 0 else 0, 2
                    ),
                },
            }
            # If we have a replay, show what gain WOULD become.
            if replay_avg is not None:
                replay_basis_at_full_qty = qty * replay_avg
                block['gains']['after_recompute'] = {
                    'avg_cost_per_share': replay_avg,
                    'total_cost_basis': round(replay_basis_at_full_qty, 2),
                    'current_value': round(current_value, 2),
                    'gain_dollars': round(current_value - replay_basis_at_full_qty, 2),
                    'gain_percent': round(
                        ((current_value - replay_basis_at_full_qty) / replay_basis_at_full_qty * 100)
                        if replay_basis_at_full_qty > 0 else 0, 2
                    ),
                }

        # Diagnostic flags.
        flags = []
        if not stock:
            flags.append('no_stock_row')
        elif not txns:
            flags.append('no_transaction_history')
        elif replay_avg is not None and stock and abs(replay_avg - float(stock.purchase_price or 0)) > 0.01:
            flags.append('cost_basis_mismatch')
        if stock and txns and abs(float(stock.quantity or 0) - running_qty) > 0.001:
            flags.append('quantity_mismatch')
        if stock and (stock.purchase_price is None or float(stock.purchase_price or 0) == 0):
            flags.append('zero_or_null_purchase_price')
        block['flags'] = flags

        results.append(block)

    return jsonify({
        'success': True,
        'user_id': user.id,
        'username': user.public_name,
        'positions': results,
    })


@app.route('/admin/set-cost-basis', methods=['GET', 'POST'])
@admin_2fa_required
def admin_set_cost_basis():
    """Backfill a synthetic `initial` Transaction for shares that ended up
    in a user's Stock row without ever writing a transaction (e.g. signup
    seed flow, old admin tweaks, pre-2026 portfolio imports).

    Workflow this slots into:
        1. /admin/inspect-position\u2026 surfaces a `quantity_mismatch`
        2. /admin/set-cost-basis  \u2026 writes the missing Transaction(s)
        3. /admin/recompute-cost-basis\u2026 derives correct purchase_price
           from the now-complete history.

    Why not just set `purchase_price` directly?
        Because the recompute pipeline is the single source of truth for
        weighted-average cost basis (handles buys, sells, splits, sale
        cost-pull). If we hand-edit purchase_price, future trades will
        re-compute on top of a stale baseline and drift again. Always
        write transactions, then let recompute derive the rest.

    Query params:
        username                 \u2014 required (or user_id)
        user_id                  \u2014 alternative
        ticker                   \u2014 required, case-insensitive
        price                    \u2014 explicit per-share cost. Mutually
                                   exclusive with `date`.
        date                     \u2014 YYYY-MM-DD. We fetch AV TIME_SERIES_DAILY
                                   adjusted close for that date.
        quantity                 \u2014 how many shares to backfill. Defaults to
                                   `Stock.quantity - sum_of_existing_buy_qty`
                                   (i.e. exactly the unaccounted shares).
        timestamp                \u2014 ISO8601 UTC; defaults to User.created_at.
        dry_run=1                \u2014 don't write, just preview.

    Returns the synthetic Transaction row (or what it would be) plus
    `next_step` reminding you to run /admin/recompute-cost-basis.
    """
    from datetime import datetime as _dt
    from models import db, Stock, User, Transaction
    from sqlalchemy import asc

    username = request.args.get('username')
    user_id = request.args.get('user_id', type=int)
    ticker_param = (request.args.get('ticker') or '').strip().upper()
    price_param = request.args.get('price', type=float)
    date_param = (request.args.get('date') or '').strip()
    quantity_param = request.args.get('quantity', type=float)
    timestamp_param = (request.args.get('timestamp') or '').strip()
    dry_run = request.args.get('dry_run') in ('1', 'true', 'yes')

    if not ticker_param:
        return jsonify({'error': 'ticker query param required'}), 400
    if price_param is None and not date_param:
        return jsonify({'error': 'must supply either price=X or date=YYYY-MM-DD'}), 400
    if price_param is not None and date_param:
        return jsonify({'error': 'price and date are mutually exclusive'}), 400

    # Resolve user.
    user = None
    if user_id:
        user = User.query.filter_by(id=user_id).first()
    elif username:
        user = User.query.filter(
            (User.username == username) | (User.display_name == username)
        ).first()
    if not user:
        return jsonify({'error': 'user not found'}), 404

    # Resolve Stock row.
    stock = (
        Stock.query.filter(Stock.user_id == user.id)
        .filter(db.func.upper(Stock.ticker) == ticker_param)
        .first()
    )
    if not stock:
        return jsonify({'error': f'no Stock row for {ticker_param} on user {user.id}'}), 404

    # Compute existing buy quantity from Transaction history.
    txns = (
        Transaction.query
        .filter(Transaction.user_id == user.id)
        .filter(db.func.upper(Transaction.ticker) == ticker_param)
        .order_by(asc(Transaction.timestamp))
        .all()
    )
    existing_buy_qty = 0.0
    existing_sell_qty = 0.0
    for t in txns:
        ttype = (t.transaction_type or '').lower()
        qty = float(t.quantity or 0)
        if qty <= 0:
            continue
        if ttype in ('buy', 'initial', 'purchase'):
            existing_buy_qty += qty
        elif ttype in ('sell', 'sale'):
            existing_sell_qty += qty

    net_recorded = existing_buy_qty - existing_sell_qty
    stock_qty = float(stock.quantity or 0)
    missing_qty = round(stock_qty - net_recorded, 6)

    # Quantity to backfill.
    if quantity_param is not None:
        backfill_qty = float(quantity_param)
    else:
        backfill_qty = missing_qty

    if backfill_qty <= 0:
        return jsonify({
            'error': 'no missing shares to backfill',
            'stock_quantity': stock_qty,
            'recorded_buy_quantity': existing_buy_qty,
            'recorded_sell_quantity': existing_sell_qty,
            'net_recorded_quantity': net_recorded,
            'missing_quantity': missing_qty,
        }), 400

    # Resolve cost basis price.
    cost_basis_price = None
    av_response_meta = None
    if price_param is not None:
        cost_basis_price = float(price_param)
    else:
        # Fetch AV TIME_SERIES_DAILY for the given date.
        try:
            import os as _os
            import requests as _req
            api_key = _os.environ.get('ALPHA_VANTAGE_API_KEY', '')
            if not api_key:
                return jsonify({'error': 'ALPHA_VANTAGE_API_KEY not set'}), 500
            url = (
                f'https://www.alphavantage.co/query'
                f'?function=TIME_SERIES_DAILY&symbol={ticker_param}'
                f'&outputsize=full&apikey={api_key}'
            )
            r = _req.get(url, timeout=15)
            if r.status_code != 200:
                return jsonify({'error': f'AV HTTP {r.status_code}', 'body': r.text[:300]}), 502
            data = r.json() or {}
            series = data.get('Time Series (Daily)') or {}
            if not series:
                return jsonify({'error': 'AV returned no time series', 'body_preview': str(data)[:300]}), 502
            # Try exact date, then walk back up to 7 calendar days for weekends/holidays.
            target = date_param
            close_px = None
            chosen_date = None
            try:
                cur = _dt.strptime(target, '%Y-%m-%d').date()
            except ValueError:
                return jsonify({'error': f'invalid date {target}, expected YYYY-MM-DD'}), 400
            from datetime import timedelta as _td
            for delta in range(0, 8):
                candidate = (cur - _td(days=delta)).isoformat()
                if candidate in series:
                    close_px = float(series[candidate].get('4. close') or 0)
                    chosen_date = candidate
                    break
            if close_px is None or close_px <= 0:
                return jsonify({
                    'error': f'no AV close found for {target} or up to 7 days before',
                    'series_sample_dates': list(series.keys())[:5],
                }), 404
            cost_basis_price = close_px
            av_response_meta = {
                'requested_date': target,
                'matched_market_date': chosen_date,
                'close_price': close_px,
            }
        except Exception as e:
            return jsonify({'error': f'AV fetch failed: {e}'}), 502

    # Resolve timestamp for the synthetic transaction.
    if timestamp_param:
        try:
            txn_timestamp = _dt.fromisoformat(timestamp_param.replace('Z', '+00:00'))
        except ValueError:
            return jsonify({'error': f'invalid timestamp {timestamp_param}'}), 400
    else:
        # Default: User.created_at if available, else Stock.purchase_date, else now.
        txn_timestamp = (
            getattr(user, 'created_at', None)
            or stock.purchase_date
            or _dt.utcnow()
        )

    payload = {
        'success': True,
        'dry_run': dry_run,
        'user_id': user.id,
        'username': user.public_name,
        'ticker': ticker_param,
        'stock_quantity': stock_qty,
        'recorded_buy_quantity': existing_buy_qty,
        'recorded_sell_quantity': existing_sell_qty,
        'net_recorded_quantity': net_recorded,
        'missing_quantity': missing_qty,
        'backfill_quantity': backfill_qty,
        'cost_basis_price': cost_basis_price,
        'av_lookup': av_response_meta,
        'synthetic_transaction': {
            'user_id': user.id,
            'ticker': ticker_param,
            'transaction_type': 'initial',
            'quantity': backfill_qty,
            'price': cost_basis_price,
            'timestamp': txn_timestamp.isoformat() if hasattr(txn_timestamp, 'isoformat') else str(txn_timestamp),
        },
        'user_created_at': user.created_at.isoformat() if getattr(user, 'created_at', None) else None,
        'stock_purchase_date': stock.purchase_date.isoformat() if stock.purchase_date else None,
    }

    if dry_run:
        payload['next_step'] = 'remove dry_run=1 to actually write the transaction'
        return jsonify(payload)

    # Write the synthetic transaction.
    try:
        new_txn = Transaction(
            user_id=user.id,
            ticker=ticker_param,
            transaction_type='initial',
            quantity=backfill_qty,
            price=cost_basis_price,
            timestamp=txn_timestamp,
            price_source='admin_backfill',
        )
        db.session.add(new_txn)
        db.session.commit()
        payload['transaction_id'] = new_txn.id
        payload['next_step'] = (
            f'/admin/recompute-cost-basis?username={user.username}&dry_run=1 \u2014 '
            'verify audit, then drop dry_run=1.'
        )
        return jsonify(payload)
    except Exception as e:
        db.session.rollback()
        logger.error(f"set_cost_basis failed: {e}")
        import traceback
        return jsonify({'success': False, 'error': str(e), 'traceback': traceback.format_exc()}), 500


#
# ───────────────────────────────────────────────────────────────────
#  Phase C: Bot holdings migration (Wolff + Grok)
# ───────────────────────────────────────────────────────────────────
#
#  The screenshots the user shared on May 18 2026 reflect the
#  authoritative target state for the two copytrade bots:
#    - Wolff's Flagship Fund  (user_id=14, username=CoastHillBear)
#    - The Grok Portfolio     (user_id=13, username=marblethehill72)
#
#  Strategy: DELTA migration, not a full replace.
#    - Tickers that already match target qty → untouched (cost basis preserved)
#    - Tickers where target_qty != current_qty → buy/sell only the delta at
#      today's market close, via the canonical process_transaction so all
#      cash-tracking side-effects fire correctly.
#    - Tickers in current but not target → full liquidation
#    - Tickers in target but not current → fresh buy
#    - User.cash_proceeds is finally overridden to the cash value the user
#      reported (12.45 for Wolff, 32.93 for Grok) so the resulting
#      portfolio_value matches the brokerage account exactly.
#
#  Why not raw Stock-row writes? Because the original seed flow did exactly
#  that (scripts/seed_bot_holdings.py via /admin/bot/add-stocks), which is
#  what created the missing-transaction-history mess Phase A had to clean
#  up for bobford00. Going through process_transaction here means a clean
#  audit trail of buy/sell rows from this point forward.
#
# Note on privacy scaling: scripts/scale_bot_holdings.py multiplies both
# shares AND cash by a per-bot factor (1.52 for Wolff, 1.37 for Grok) so
# our public displays don't perfectly mirror the operator's real
# brokerage account. The screenshots reflect the REAL Public.com state,
# so when migrating we apply the same multiplier here to keep the
# privacy scaling in place.
HOLDINGS_PRESETS_PHASE_C = {
    'wolff': {
        'user_id': 14,
        'username': 'CoastHillBear',
        'display_name': "Wolff's Flagship Fund",
        'bot_multiplier': 1.52,
        'cash_balance_real': 12.45,  # brokerage value; multiplier applied below
        'target_real': {  # screenshot share counts; multiplier applied below
            'AMD':   0.90988,
            'GLTR':  5.36815,
            'AMZN':  1.75114,
            'SGOV':  15.35535,
            'BN':    9.02496,
            'NVDA':  1.82096,
            'IREN':  19.40808,
            'CIFR':  39.32004,
            'MSFT':  1.78374,
            'META':  1.17662,
            'AVGO':  0.91787,
            'NBIS':  2.63671,
            'WULF':  21.0,
            'MELI':  0.23545,
            'GRAB':  109.3198,
            'LLY':   0.49395,
            'NOW':   4.17787,
            'ELV':   1.44741,
            'BRK.B': 1.03074,
            'PLTR':  2.63571,
        },
    },
    'grok': {
        'user_id': 13,
        'username': 'marblethehill72',
        'display_name': 'The Grok Portfolio',
        'bot_multiplier': 1.37,
        'cash_balance_real': 32.93,
        'target_real': {
            'CLSK':  79.4603,
            'SOC':   76.85545,
            'KTOS':  16.54593,
            'PGY':   72.0,
            'IREN':  20.2804,
            'MSTR':  4.71046,
            'MSFT':  2.25352,
            'AVGO':  3.03088,
            'NOC':   1.40361,
            'LMT':   1.75932,
            'DVN':   16.75203,
            'WLDN':  12.0,
            'VST':   7.43432,
            'ORLA':  55.47196,
            'MU':    1.73871,
        },
    },
}


@app.route('/admin/migrate-bot-holdings', methods=['GET', 'POST'])
@admin_2fa_required
def admin_migrate_bot_holdings():
    """Phase C: delta-migrate a copytrade bot to its target holdings.

    Query params:
        preset    — 'wolff' | 'grok' (required)
        dry_run   — 1/true → preview only, don't write (recommended first run)
        force     — 1/true → allow re-running even if the previous run
                    appears to have already converged the portfolio (i.e.
                    all deltas are zero). Without `force=1` the endpoint
                    refuses the no-op execute to make accidental
                    double-runs safe.
        eps       — quantity epsilon for "matches target" (default 1e-9 —
                    only skips trades when the delta is pure floating-point
                    noise. Even sub-cent deltas get executed so we never
                    leave a residue when Wolff/Grok intended to zero out a
                    position.)

    Response includes a full per-ticker plan (current_qty, target_qty,
    delta_qty, action, price, trade_value) and a summary block.
    """
    from datetime import datetime as _dt
    from models import db, Stock, User, Transaction
    from cash_tracking import process_transaction

    preset_key = (request.args.get('preset') or '').lower().strip()
    dry_run = request.args.get('dry_run') in ('1', 'true', 'yes')
    force = request.args.get('force') in ('1', 'true', 'yes')
    try:
        eps = float(request.args.get('eps') or '1e-9')
    except ValueError:
        eps = 1e-9

    if preset_key not in HOLDINGS_PRESETS_PHASE_C:
        return jsonify({
            'error': f'unknown preset',
            'valid_presets': list(HOLDINGS_PRESETS_PHASE_C.keys()),
        }), 400

    preset = HOLDINGS_PRESETS_PHASE_C[preset_key]
    user = User.query.filter_by(id=preset['user_id']).first()
    if not user:
        return jsonify({'error': f'user_id {preset["user_id"]} not found'}), 404
    # Sanity-check that the user_id still maps to the bot we expect, in case
    # IDs were reshuffled. We don't fail hard, just surface a warning.
    sanity_warnings = []
    if user.username != preset['username']:
        sanity_warnings.append(
            f"username mismatch: preset expected {preset['username']!r}, "
            f"DB has {user.username!r} \u2014 verify before executing"
        )
    if getattr(user, 'display_name', None) != preset['display_name']:
        sanity_warnings.append(
            f"display_name mismatch: preset expected {preset['display_name']!r}, "
            f"DB has {user.display_name!r}"
        )

    # ── Snapshot CURRENT holdings ─────────────────────────────────────
    current_stocks = (
        Stock.query.filter_by(user_id=user.id)
        .filter(Stock.quantity > 0)
        .all()
    )
    current_qty = {s.ticker.upper(): float(s.quantity) for s in current_stocks}
    current_purchase_price = {s.ticker.upper(): float(s.purchase_price or 0) for s in current_stocks}

    # Apply per-bot privacy scaling multiplier to convert brokerage screenshot
    # share counts into the scaled values stored in our DB. Wolff uses
    # 1.52x, Grok uses 1.37x — see comment block above.
    multiplier = float(preset.get('bot_multiplier', 1.0))
    target_qty = {t.upper(): float(q) * multiplier for t, q in preset['target_real'].items()}
    target_cash = float(preset['cash_balance_real']) * multiplier

    # ── Compute the set of affected tickers (union) ──────────────────
    affected_tickers = sorted(set(current_qty) | set(target_qty))

    # ── Batch-fetch live prices for every affected ticker ────────────
    from portfolio_performance import PortfolioPerformanceCalculator
    calc = PortfolioPerformanceCalculator()
    try:
        batch_prices = calc.get_batch_stock_data(affected_tickers) if affected_tickers else {}
    except Exception as e:
        return jsonify({'error': f'AV batch price fetch failed: {e}'}), 502

    def resolve_price(tk: str):
        # get_batch_stock_data normalises to upper; fall back to purchase_price
        # for the sell-side if AV doesn't have a quote, since the dollar
        # amount of a sell mostly matters for cash_proceeds bookkeeping.
        px = batch_prices.get(tk.upper())
        if px and px > 0:
            return float(px), 'av_live'
        fallback = current_purchase_price.get(tk.upper())
        if fallback and fallback > 0:
            return float(fallback), 'stored_purchase_price'
        return None, 'no_price'

    # ── Build the per-ticker plan ────────────────────────────────────
    plan = []
    missing_prices = []
    buys = 0
    sells = 0
    unchanged = 0
    new_positions = 0
    full_liquidations = 0
    total_buy_value = 0.0
    total_sell_value = 0.0

    for tk in affected_tickers:
        cur = current_qty.get(tk, 0.0)
        tgt = target_qty.get(tk, 0.0)
        delta = tgt - cur
        price, price_source = resolve_price(tk)

        entry = {
            'ticker': tk,
            'current_qty': round(cur, 6),
            'target_qty': round(tgt, 6),
            'delta_qty': round(delta, 6),
            'price_per_share': round(price, 4) if price else None,
            'price_source': price_source,
        }

        if abs(delta) < eps:
            entry['action'] = 'skip'
            entry['trade_value'] = 0.0
            entry['note'] = 'matches target \u2014 no trade, cost basis preserved'
            unchanged += 1
        elif delta > 0:
            entry['action'] = 'buy'
            if cur < eps:
                entry['note'] = 'new position'
                new_positions += 1
            if price is None:
                entry['warning'] = 'NO PRICE AVAILABLE \u2014 buy will be skipped at execute time'
                missing_prices.append(tk)
            trade_value = (price or 0) * delta
            entry['trade_value'] = round(trade_value, 2)
            total_buy_value += trade_value
            buys += 1
        else:
            entry['action'] = 'sell'
            if tgt < eps:
                entry['note'] = 'full liquidation (ticker not in target)'
                full_liquidations += 1
            if price is None:
                entry['warning'] = 'NO PRICE AVAILABLE \u2014 sell will be skipped at execute time'
                missing_prices.append(tk)
            trade_value = (price or 0) * abs(delta)
            entry['trade_value'] = round(trade_value, 2)
            total_sell_value += trade_value
            sells += 1

        plan.append(entry)

    # ── Current vs target portfolio value summary ─────────────────────
    current_stock_value = sum(
        (batch_prices.get(tk, current_purchase_price.get(tk, 0)) or 0) * q
        for tk, q in current_qty.items()
    )
    current_cash = float(getattr(user, 'cash_proceeds', 0.0) or 0.0)
    target_stock_value = sum(
        (batch_prices.get(tk, 0) or 0) * q for tk, q in target_qty.items()
    )
    # target_cash already computed above with privacy scaling multiplier.

    summary = {
        'tickers_in_plan': len(plan),
        'trades_to_execute': buys + sells,
        'buys': buys,
        'sells': sells,
        'unchanged': unchanged,
        'new_positions': new_positions,
        'full_liquidations': full_liquidations,
        'tickers_without_price': missing_prices,
        'estimated_buy_dollars': round(total_buy_value, 2),
        'estimated_sell_dollars': round(total_sell_value, 2),
        'net_cash_flow_from_trades': round(total_sell_value - total_buy_value, 2),
    }

    response_base = {
        'preset': preset_key,
        'user_id': user.id,
        'username': user.username,
        'display_name': user.display_name,
        'bot_multiplier': multiplier,
        'real_brokerage_state': {
            'cash_balance': round(float(preset['cash_balance_real']), 2),
            'note': (
                f'screenshot share counts and ${preset["cash_balance_real"]} cash '
                f'are multiplied by {multiplier} to produce target_state below'
            ),
        },
        'sanity_warnings': sanity_warnings,
        'dry_run': dry_run,
        'current_state': {
            'stocks_count': len(current_qty),
            'stock_value': round(current_stock_value, 2),
            'cash_balance': round(current_cash, 2),
            'portfolio_value': round(current_stock_value + current_cash, 2),
        },
        'target_state': {
            'stocks_count': len(target_qty),
            'stock_value': round(target_stock_value, 2),
            'cash_balance': round(target_cash, 2),
            'portfolio_value': round(target_stock_value + target_cash, 2),
        },
        'plan': plan,
        'summary': summary,
    }

    # ── Dry run: return the plan only ─────────────────────────────────
    if dry_run:
        response_base['next_step'] = (
            f'/admin/migrate-bot-holdings?preset={preset_key} '
            '(drop dry_run=1 to execute)'
        )
        return jsonify(response_base)

    # ── Idempotency guard: refuse no-op execute without ?force=1 ──────
    if summary['trades_to_execute'] == 0 and not force:
        response_base['next_step'] = (
            'Portfolio already at target. Re-run with &force=1 if you want '
            'to override cash_balance regardless.'
        )
        response_base['error'] = 'no_trades_to_execute'
        return jsonify(response_base), 200

    # ── Execute trades ───────────────────────────────────────────────
    # Pattern matches the canonical buy/sell flow at api/index.py:3492-3692:
    #   1. Update / create / decrement the Stock row first (cost-basis
    #      math lives here; process_transaction doesn't touch Stock rows).
    #   2. Call process_transaction to write the Transaction row and adjust
    #      cash_proceeds / max_cash_deployed.
    # Notifications are suppressed so a 20-trade rebalance doesn't push
    # 20 alerts to every subscriber.
    executed = []
    failed = []
    now = _dt.utcnow()
    for entry in plan:
        if entry['action'] == 'skip':
            continue
        if entry.get('warning'):
            failed.append({**entry, 'reason': 'no_price'})
            continue

        tk = entry['ticker']
        price = float(entry['price_per_share'])
        qty_delta = abs(float(entry['delta_qty']))
        is_buy = entry['action'] == 'buy'

        try:
            # Locate (or create) the Stock row. Case-insensitive match.
            existing_stock = (
                Stock.query.filter_by(user_id=user.id)
                .filter(db.func.upper(Stock.ticker) == tk)
                .first()
            )

            if is_buy:
                # Decide between 'initial' and 'buy'. 'initial' only when
                # the ticker has zero prior Transaction history for this
                # user (matches add-trade convention at api/index.py:3524).
                ticker_has_history = Transaction.query.filter(
                    Transaction.user_id == user.id,
                    db.func.upper(Transaction.ticker) == tk,
                ).first() is not None
                trade_type = 'buy' if ticker_has_history else 'initial'

                if existing_stock and float(existing_stock.quantity or 0) > 0:
                    # Weighted-average update of an existing position.
                    old_qty = float(existing_stock.quantity)
                    old_cost = old_qty * float(existing_stock.purchase_price or 0)
                    new_cost = qty_delta * price
                    new_qty = old_qty + qty_delta
                    existing_stock.quantity = new_qty
                    existing_stock.purchase_price = (old_cost + new_cost) / new_qty if new_qty > 0 else price
                else:
                    # Fresh position. If a zombie 0-qty row exists, reuse it
                    # so we don't accumulate duplicate rows over time.
                    if existing_stock:
                        existing_stock.quantity = qty_delta
                        existing_stock.purchase_price = price
                        existing_stock.purchase_date = now
                    else:
                        new_stock = Stock(
                            ticker=tk,
                            quantity=qty_delta,
                            purchase_price=price,
                            purchase_date=now,
                            user_id=user.id,
                        )
                        db.session.add(new_stock)
            else:
                # SELL. Stock row must exist with enough quantity; otherwise
                # we surface the inconsistency rather than silently skip.
                trade_type = 'sell'
                if not existing_stock or float(existing_stock.quantity or 0) < qty_delta - 0.000001:
                    raise ValueError(
                        f"insufficient shares to sell {qty_delta} of {tk}: "
                        f"have {float(existing_stock.quantity) if existing_stock else 0}"
                    )
                existing_stock.quantity = float(existing_stock.quantity) - qty_delta
                # Cost basis (purchase_price) is intentionally unchanged on
                # sells \u2014 weighted-average remains valid for the remaining
                # shares.

            result = process_transaction(
                db, user.id, tk, qty_delta, price, trade_type,
                timestamp=now,
                price_source='phase_c_migration',
                suppress_notifications=True,
            )

            executed.append({
                'ticker': tk,
                'action': trade_type,
                'quantity': qty_delta,
                'price': price,
                'value': round(qty_delta * price, 2),
                'cash_proceeds_after': float(result.get('cash_proceeds') if isinstance(result, dict) else 0),
                'max_cash_deployed_after': float(result.get('max_cash_deployed') if isinstance(result, dict) else 0),
            })
        except Exception as e:
            # Atomicity: rolling back here discards every earlier trade in
            # this migration that hadn't been committed yet. We surface
            # the failure and bail out so the operator can fix the
            # underlying issue (typically insufficient shares to sell or
            # an AV price hiccup) and re-run \u2014 the delta will be
            # recomputed automatically.
            db.session.rollback()
            failed.append({
                'ticker': tk,
                'action': entry['action'],
                'error': str(e),
            })
            response_base['executed_trades'] = []  # nothing committed
            response_base['failed_trades'] = failed
            response_base['error'] = (
                f'aborted at {tk}: {e}. All earlier trades rolled back. '
                'Fix the issue and retry.'
            )
            return jsonify(response_base), 500

    # ── Override cash_proceeds to the target value the user reported ─
    # This is the deliberate "books match brokerage" step. Trades above
    # have already moved cash_proceeds around; this final assignment makes
    # the portfolio_value equal exactly (stock_value + target_cash).
    pre_override_cash = float(getattr(user, 'cash_proceeds', 0.0) or 0.0)
    user.cash_proceeds = target_cash

    # ── Cleanup zero-share Stock rows from full liquidations ─────────
    zombies_deleted = 0
    if executed:
        zombie_rows = (
            Stock.query.filter_by(user_id=user.id)
            .filter(Stock.quantity <= 0.0000001)
            .all()
        )
        for z in zombie_rows:
            db.session.delete(z)
            zombies_deleted += 1

    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({**response_base, 'error': f'commit failed: {e}'}), 500

    response_base['executed_trades'] = executed
    response_base['failed_trades'] = failed
    response_base['cash_override'] = {
        'before': round(pre_override_cash, 2),
        'after': round(target_cash, 2),
    }
    response_base['zombies_deleted'] = zombies_deleted
    response_base['next_step'] = (
        f'verify holdings @ /admin/inspect-position?username={user.username}'
        f'&tickers={",".join(target_qty.keys())}'
    )
    return jsonify(response_base)


@app.route('/admin/delete-transactions', methods=['GET', 'POST'])
@admin_2fa_required
def admin_delete_transactions():
    """Surgically delete a user's Transaction rows and rebuild Stock rows +
    user.cash_proceeds + user.max_cash_deployed from the remaining
    transaction history.

    Used to clean up accidentally-allocated trades (e.g. the 2026-05-05
    13:43 batch that wrongly added CLSK/KTOS/MSTR/PGY/SOC + 30.83 IREN
    shares to Wolff's portfolio). Pair with
    /admin/recompute-portfolio-snapshots afterwards to smooth the chart.

    Query params:
        user_id  — required (we forbid cross-user batch deletes)
        ids      — comma-separated Transaction IDs to delete
        delete_stock_for_tickers — comma-separated tickers whose Stock row
                   should be deleted entirely after replay (use this for
                   tickers we want to fully remove regardless of whether
                   replay leaves a small residue from un-deleted rows)
        dry_run  — preview without writing (recommended first run)
    """
    from datetime import datetime as _dt
    from models import db, Stock, User, Transaction

    user_id = request.args.get('user_id', type=int)
    ids_param = (request.args.get('ids') or '').strip()
    drop_param = (request.args.get('delete_stock_for_tickers') or '').strip()
    dry_run = request.args.get('dry_run') in ('1', 'true', 'yes')

    if not user_id or not ids_param:
        return jsonify({'error': 'user_id and ids required'}), 400

    try:
        txn_ids = [int(x.strip()) for x in ids_param.split(',') if x.strip()]
    except ValueError:
        return jsonify({'error': 'ids must be comma-separated integers'}), 400
    explicit_drop = {t.strip().upper() for t in drop_param.split(',') if t.strip()}

    user = User.query.get(user_id)
    if not user:
        return jsonify({'error': f'user_id {user_id} not found'}), 404

    txns_to_delete = Transaction.query.filter(Transaction.id.in_(txn_ids)).all()
    if len(txns_to_delete) != len(set(txn_ids)):
        found = {t.id for t in txns_to_delete}
        return jsonify({
            'error': 'one or more transactions not found',
            'requested': sorted(set(txn_ids)),
            'found': sorted(found),
            'missing': sorted(set(txn_ids) - found),
        }), 404
    cross_user = [t.id for t in txns_to_delete if t.user_id != user_id]
    if cross_user:
        return jsonify({
            'error': 'transactions belong to other users — refusing',
            'offending_ids': cross_user,
        }), 400

    delete_id_set = {t.id for t in txns_to_delete}
    affected_tickers = sorted({t.ticker.upper() for t in txns_to_delete} | explicit_drop)

    # ── Snapshot before-state ────────────────────────────────────────
    before_user = {
        'cash_proceeds': float(user.cash_proceeds or 0),
        'max_cash_deployed': float(user.max_cash_deployed or 0),
    }
    before_stocks = {}
    for tk in affected_tickers:
        st = (
            Stock.query.filter(Stock.user_id == user_id)
            .filter(db.func.upper(Stock.ticker) == tk).first()
        )
        before_stocks[tk] = (
            {'quantity': float(st.quantity or 0),
             'purchase_price': float(st.purchase_price or 0)}
            if st else None
        )

    # ── Predict per-ticker after-state via DELTA adjustment ──────────
    #
    # NOTE: We deliberately do NOT replay transactions from zero here.
    # The bot accounts (and many seeded users) have positions written
    # directly to the Stock table without corresponding Transaction
    # rows (signup seed, /admin/bot/scale-holdings privacy scaling event,
    # etc.). A from-zero replay misses the seed + privacy scaling entirely
    # and would either drop the Stock row (qty goes negative) or
    # massively understate quantity. Instead we start from the CURRENT
    # Stock row state and reverse only the impact of the to-be-deleted
    # transactions. This preserves accuracy for incomplete histories.
    plan = []
    for tk in affected_tickers:
        deleted_for_this_ticker = [t for t in txns_to_delete if t.ticker.upper() == tk]

        st_before = before_stocks[tk]
        if st_before is None:
            # No Stock row exists. Deleted txns shouldn't materialise one.
            plan.append({
                'ticker': tk,
                'before_stock_row': None,
                'transactions_deleted': [
                    {'id': t.id, 'type': t.transaction_type,
                     'qty': float(t.quantity), 'price': float(t.price),
                     'timestamp': t.timestamp.isoformat() if t.timestamp else None}
                    for t in deleted_for_this_ticker
                ],
                'after_stock_row': None,
                'stock_row_will_be_deleted': True,
            })
            continue

        old_qty = st_before['quantity']
        old_price = st_before['purchase_price']
        old_total_cost = old_qty * old_price

        new_qty = old_qty
        new_total_cost = old_total_cost
        for txn in deleted_for_this_ticker:
            tqty = float(txn.quantity)
            tprice = float(txn.price)
            tval = tqty * tprice
            ttype = (txn.transaction_type or '').lower()
            if ttype in ('buy', 'initial'):
                # Reverse the buy: shares disappear, cost basis decreases
                # by the buy notional.
                new_qty -= tqty
                new_total_cost -= tval
            elif ttype == 'sell':
                # Reverse the sell: shares come back at the average cost
                # basis at the time of sell. We don't know that exactly
                # without full replay, so we approximate with the
                # *current* purchase_price (best signal we have).
                new_qty += tqty
                new_total_cost += tqty * old_price
            # dividends don't affect holdings

        will_drop = (tk in explicit_drop) or (new_qty <= 1e-6)
        new_price = (new_total_cost / new_qty) if new_qty > 1e-9 else 0.0
        # Floating-point safety: clamp tiny-negative cost basis to 0
        if new_total_cost < 0 and abs(new_total_cost) < 1e-3:
            new_total_cost = 0.0
            new_price = 0.0

        plan.append({
            'ticker': tk,
            'before_stock_row': st_before,
            'transactions_deleted': [
                {'id': t.id, 'type': t.transaction_type,
                 'qty': float(t.quantity), 'price': float(t.price),
                 'timestamp': t.timestamp.isoformat() if t.timestamp else None}
                for t in deleted_for_this_ticker
            ],
            'after_stock_row': (
                None if will_drop else
                {'quantity': round(new_qty, 6),
                 'purchase_price': round(new_price, 6),
                 'total_cost_basis': round(new_total_cost, 2)}
            ),
            'stock_row_will_be_deleted': will_drop,
        })

    # ── Predict user-level after-state via DELTA adjustment ──────────
    #
    # Same reasoning: replay-from-zero would drop max_cash_deployed
    # below the real seed + privacy scaling level. Delta logic:
    #   - Removed BUY of $V: assume V was funded by capital
    #     (max_cash_deployed -= V). For pure-bot-trade accounts this
    #     under-counts when the buy was actually funded by accumulated
    #     cash_proceeds, but for the bulk-allocation cleanup this is
    #     the right model since cash_proceeds was small at trade time.
    #   - Removed SELL of $V: cash_proceeds -= V (the inflow that
    #     shouldn't have happened).
    #   - If cash_proceeds would go negative after the delta, clamp at
    #     zero and shift the deficit onto max_cash_deployed (because
    #     that cash funded subsequent buys; without it the buys would
    #     have deployed more capital).
    pred_cash = before_user['cash_proceeds']
    pred_deployed = before_user['max_cash_deployed']
    for txn in txns_to_delete:
        v = float(txn.quantity) * float(txn.price)
        ttype = (txn.transaction_type or '').lower()
        if ttype in ('buy', 'initial'):
            pred_deployed -= v
        elif ttype == 'sell':
            pred_cash -= v
        elif ttype == 'dividend':
            pred_cash -= v
    if pred_cash < 0:
        deficit = -pred_cash
        pred_cash = 0.0
        pred_deployed += deficit
    if pred_deployed < 0:
        pred_deployed = 0.0

    # ── Cost-basis floor on max_cash_deployed ────────────────────────
    #
    # The linear delta above can drive max_cash_deployed below the
    # actual capital still tied up in remaining holdings. That happens
    # when the total notional of deleted buys exceeds the user's
    # historical high-water mark (because intervening sells brought
    # deployed_capital down between buys, so max was achieved at a
    # different point than the sum-of-deleted-buys suggests).
    #
    # Concrete example (Grok cleanup):
    #   max_cash_deployed = $24,680  (before)
    #   deleted buys total $29,599   (ADBE + NOW + PLTR)
    #   linear delta → -$4,919 → clamps to $0
    # But Grok still holds DVN/LMT/MU/VST/WLDN/etc with thousands of
    # dollars of cost basis. Capital that's *currently* deployed must
    # have been deployed at some point, so max_cash_deployed ≥ current
    # total cost basis of all (post-cleanup) holdings.
    #
    # Compute the floor by walking every Stock the user owns and
    # substituting the post-cleanup (qty × purchase_price) for
    # affected tickers.
    after_stock_by_ticker = {}
    for entry in plan:
        tk = entry['ticker']
        if entry['stock_row_will_be_deleted']:
            after_stock_by_ticker[tk] = 0.0
        elif entry['after_stock_row']:
            asr = entry['after_stock_row']
            after_stock_by_ticker[tk] = float(asr['quantity']) * float(asr['purchase_price'])
        else:
            after_stock_by_ticker[tk] = 0.0
    cost_basis_floor = 0.0
    all_user_stocks = Stock.query.filter(Stock.user_id == user_id).all()
    for s in all_user_stocks:
        tk = (s.ticker or '').upper()
        if tk in after_stock_by_ticker:
            cost_basis_floor += after_stock_by_ticker[tk]
        else:
            cost_basis_floor += float(s.quantity or 0) * float(s.purchase_price or 0)
    if pred_deployed < cost_basis_floor:
        pred_deployed = cost_basis_floor

    response = {
        'user_id': user_id,
        'username': user.username,
        'dry_run': dry_run,
        'transactions_to_delete_count': len(txns_to_delete),
        'affected_tickers': affected_tickers,
        'before_user': before_user,
        'after_user_predicted': {
            'cash_proceeds': round(pred_cash, 2),
            'max_cash_deployed': round(pred_deployed, 2),
            'cost_basis_floor': round(cost_basis_floor, 2),
        },
        'plan': plan,
    }

    if dry_run:
        response['next_step'] = (
            f'/admin/delete-transactions?user_id={user_id}&ids={ids_param}'
            + (f'&delete_stock_for_tickers={drop_param}' if drop_param else '')
            + ' (drop dry_run=1 to execute)'
        )
        return jsonify(response)

    # ── Execute ──────────────────────────────────────────────────────
    try:
        for t in txns_to_delete:
            db.session.delete(t)

        for entry in plan:
            tk = entry['ticker']
            st = (
                Stock.query.filter(Stock.user_id == user_id)
                .filter(db.func.upper(Stock.ticker) == tk).first()
            )
            if entry['stock_row_will_be_deleted']:
                if st:
                    db.session.delete(st)
            else:
                target_qty = entry['after_stock_row']['quantity']
                target_avg = entry['after_stock_row']['purchase_price']
                if st:
                    st.quantity = target_qty
                    st.purchase_price = target_avg
                else:
                    db.session.add(Stock(
                        user_id=user_id, ticker=tk,
                        quantity=target_qty, purchase_price=target_avg,
                        purchase_date=_dt.utcnow(),
                    ))

        # Apply DELTA-adjusted user state (do NOT call
        # backfill_cash_tracking_for_user — see notes above on why
        # replay-from-zero would corrupt seed/scaled accounts).
        user.cash_proceeds = pred_cash
        user.max_cash_deployed = pred_deployed

        db.session.commit()

        # Re-read user for actual after-state
        user = User.query.get(user_id)
        response['executed'] = True
        response['after_user_actual'] = {
            'cash_proceeds': round(float(user.cash_proceeds or 0), 2),
            'max_cash_deployed': round(float(user.max_cash_deployed or 0), 2),
        }
        response['next_step'] = (
            f'/admin/recompute-portfolio-snapshots?user_id={user_id}&dry_run=1 '
            'to smooth historical chart'
        )
        return jsonify(response)
    except Exception as e:
        db.session.rollback()
        import traceback
        return jsonify({
            'error': f'execute failed: {e}',
            'traceback': traceback.format_exc(),
        }), 500


@app.route('/admin/recompute-portfolio-snapshots', methods=['GET', 'POST'])
@admin_2fa_required
def admin_recompute_portfolio_snapshots():
    """Walk every PortfolioSnapshot (and optionally PortfolioSnapshotIntraday)
    for a user and rebuild portfolio_value / stock_value / cash_proceeds /
    max_cash_deployed from the *current* Transaction history.

    Used after /admin/delete-transactions surgically removed accidental
    trades so the chart no longer shows the inflated values from those
    phantom holdings.

    For each snapshot we:
      1. Replay all transactions <= that snapshot's date/timestamp to derive
         holdings + cash, starting from a reconstructed seed state (so bot
         accounts whose Stock rows predate any Transaction don't get zeroed).
      2. Look up close prices for each held ticker on that date
         (MarketData first, AV TIME_SERIES_DAILY fallback — which also
         bulk-populates ~100 days of MarketData per ticker per call).
      3. Update the snapshot in place.

    Query params:
        user_id          — required (or pass `username` instead)
        username         — alternative to user_id
        from             — ISO date (default: earliest snapshot)
        to               — ISO date (default: latest snapshot)
        limit            — max DAILY snapshots to process (default 200).
        include_intraday — if 1/true, ALSO recompute PortfolioSnapshotIntraday
                           rows in the same date range.
        intraday_only    — if 1/true, recompute ONLY intraday (skip daily).
        intraday_limit   — max intraday snapshots to process (default 1000).
        sync_user_state  — if 1/true, ALSO replay-to-now and write
                           User.cash_proceeds + User.max_cash_deployed.
                           Use this when the iOS header value /
                           live portfolio_value (which reads from the
                           User row) is wrong, AND/OR to make sure new
                           intraday cron rows are computed from a
                           correct cash state going forward.
        dry_run          — preview without writing
    """
    from datetime import datetime as _dt, time as _time_t
    from models import db, User, Transaction, PortfolioSnapshot, Stock, PortfolioSnapshotIntraday
    from sqlalchemy import func as _f
    from portfolio_performance import PortfolioPerformanceCalculator

    # Accept either user_id or username for the operator's convenience.
    user_id = request.args.get('user_id', type=int)
    username = request.args.get('username', type=str)
    if not user_id and not username:
        return jsonify({'error': 'user_id or username required'}), 400
    dry_run = request.args.get('dry_run') in ('1', 'true', 'yes')
    include_intraday = request.args.get('include_intraday') in ('1', 'true', 'yes')
    intraday_only = request.args.get('intraday_only') in ('1', 'true', 'yes')
    sync_user_state = request.args.get('sync_user_state') in ('1', 'true', 'yes')
    if intraday_only:
        include_intraday = True  # implied

    if user_id:
        user = User.query.get(user_id)
    else:
        user = User.query.filter_by(username=username).first()
    if not user:
        return jsonify({'error': f'user not found (user_id={user_id} username={username})'}), 404
    user_id = user.id

    q = PortfolioSnapshot.query.filter_by(user_id=user_id)
    try:
        if request.args.get('from'):
            q = q.filter(PortfolioSnapshot.date >= _dt.fromisoformat(request.args.get('from')).date())
        if request.args.get('to'):
            q = q.filter(PortfolioSnapshot.date <= _dt.fromisoformat(request.args.get('to')).date())
    except ValueError as e:
        return jsonify({'error': f'bad from/to date: {e}'}), 400

    limit = request.args.get('limit', default=200, type=int)
    if intraday_only:
        snapshots = []  # skip daily
    else:
        snapshots = q.order_by(PortfolioSnapshot.date).limit(limit).all()
        if not snapshots and not include_intraday:
            return jsonify({'error': 'no snapshots in range', 'user_id': user_id}), 404

    # Build the intraday query if requested. Use the same from/to date filters,
    # converted to datetime boundaries (start-of-day to end-of-day).
    intraday_snaps = []
    if include_intraday:
        iq = PortfolioSnapshotIntraday.query.filter_by(user_id=user_id)
        try:
            if request.args.get('from'):
                _from_dt = _dt.combine(
                    _dt.fromisoformat(request.args.get('from')).date(),
                    _time_t.min,
                )
                iq = iq.filter(PortfolioSnapshotIntraday.timestamp >= _from_dt)
            if request.args.get('to'):
                _to_dt = _dt.combine(
                    _dt.fromisoformat(request.args.get('to')).date(),
                    _time_t.max,
                )
                iq = iq.filter(PortfolioSnapshotIntraday.timestamp <= _to_dt)
        except ValueError as e:
            return jsonify({'error': f'bad from/to date: {e}'}), 400
        # Process most-recent snapshots first: after a phantom-cleanup,
        # the recent rows are the ones most likely to be stale, so cap
        # truncation (if any) hits the oldest history instead of the
        # rows users actually see in current charts.
        intraday_limit = request.args.get('intraday_limit', default=10000, type=int)
        intraday_snaps = iq.order_by(PortfolioSnapshotIntraday.timestamp.desc()).limit(intraday_limit).all()
        # Re-sort ascending so the replay walks chronologically (cash
        # state is path-dependent — must replay in trade order).
        intraday_snaps.sort(key=lambda s: s.timestamp)
        if not snapshots and not intraday_snaps:
            return jsonify({'error': 'no snapshots in range (daily or intraday)', 'user_id': user_id}), 404

    # Pre-fetch ALL transactions once, sort by timestamp, walk in date order.
    # Avoids N queries for N snapshots.
    all_txns = (
        Transaction.query.filter_by(user_id=user_id)
        .order_by(Transaction.timestamp).all()
    )

    # ── Seed-state reconstruction ─────────────────────────────────────
    # Bot accounts (and many seeded users) have Stock rows created
    # directly by the privacy scaling/seed scripts without corresponding
    # Transaction records. A naive replay-from-zero would treat those
    # seed positions as if they didn't exist, zeroing out every
    # snapshot before the first transaction and under-counting all
    # subsequent snapshots by the seed quantity.
    #
    # We solve this by deriving the seed quantity for each ticker as:
    #   seed_qty[tk] = current_Stock.quantity[tk]
    #                  - sum(buy/initial qty across all txns)
    #                  + sum(sell qty across all txns)
    # The intuition: whatever quantity exists today minus everything
    # transactions added equals what was already there before any
    # transactions ran. This works for every case:
    #   - Pure-seed ticker (no txns):    seed = current
    #   - Seed + later sells (BAH/HALO): current=0, sells>0 → seed = sells
    #   - Pure-phantom (post-cleanup):   no Stock row, no txns → 0
    #   - Buy-only ticker (new):         current = buys → seed = 0
    current_stocks = Stock.query.filter_by(user_id=user_id).all()
    current_qty_by_ticker = {(s.ticker or '').upper(): float(s.quantity or 0)
                             for s in current_stocks}
    current_cost_by_ticker = {(s.ticker or '').upper(): float(s.purchase_price or 0)
                              for s in current_stocks}

    net_txn_qty = {}
    earliest_txn_price = {}
    for txn in all_txns:
        tk = (txn.ticker or '').upper()
        qty = float(txn.quantity or 0)
        if txn.transaction_type in ('buy', 'initial'):
            net_txn_qty[tk] = net_txn_qty.get(tk, 0.0) + qty
        elif txn.transaction_type == 'sell':
            net_txn_qty[tk] = net_txn_qty.get(tk, 0.0) - qty
        if tk not in earliest_txn_price:
            earliest_txn_price[tk] = float(txn.price or 0)

    seed_holdings = {}
    seed_total_cost = 0.0
    all_relevant_tickers = set(current_qty_by_ticker.keys()) | set(net_txn_qty.keys())
    for tk in all_relevant_tickers:
        seed_qty = current_qty_by_ticker.get(tk, 0.0) - net_txn_qty.get(tk, 0.0)
        if seed_qty > 1e-9:
            seed_holdings[tk] = seed_qty
            # For seed cost: prefer the live Stock.purchase_price (weighted
            # average preserved across the user's history). For tickers
            # whose Stock row was deleted (fully liquidated), fall back to
            # the earliest transaction's price as a rough seed-price proxy.
            cost_per_share = (
                current_cost_by_ticker.get(tk)
                or earliest_txn_price.get(tk, 0.0)
            )
            seed_total_cost += seed_qty * cost_per_share

    # Bot accounts begin with all-stock-no-cash. max_cash_deployed at
    # seed time is the cost basis of the seeded positions.
    seed_cash = 0.0
    seed_deployed = seed_total_cost

    calc = PortfolioPerformanceCalculator()
    changes = []
    intraday_changes = []
    errors = []
    missing_prices_summary = {}

    # Per-(ticker, date) price cache. Daily close prices don't change within
    # the day, so for intraday processing this collapses ~27 lookups/day per
    # ticker into one. Also benefits the daily loop when the same ticker is
    # held across many dates.
    price_cache = {}

    def _priced(tk, dt_):
        key = (tk, dt_)
        if key in price_cache:
            return price_cache[key]
        p = calc.get_historical_price(tk, dt_)
        price_cache[key] = p
        return p

    def _replay_to(cutoff):
        """Walk transactions <= cutoff (date or datetime) starting from the
        reconstructed seed state. Returns (holdings, cash, deployed)."""
        holdings = dict(seed_holdings)
        cash = seed_cash
        deployed = seed_deployed
        is_dt = isinstance(cutoff, _dt)
        for txn in all_txns:
            if not txn.timestamp:
                continue
            if is_dt:
                if txn.timestamp > cutoff:
                    break
            else:
                if txn.timestamp.date() > cutoff:
                    break
            tk = (txn.ticker or '').upper()
            v = float(txn.quantity or 0) * float(txn.price or 0)
            if txn.transaction_type in ('buy', 'initial'):
                holdings[tk] = holdings.get(tk, 0.0) + float(txn.quantity or 0)
                if cash >= v:
                    cash -= v
                else:
                    deployed += (v - cash)
                    cash = 0.0
            elif txn.transaction_type == 'sell':
                holdings[tk] = holdings.get(tk, 0.0) - float(txn.quantity or 0)
                cash += v
            elif txn.transaction_type == 'dividend':
                cash += v
        return holdings, cash, deployed

    for snap in snapshots:
        try:
            holdings, cash, deployed = _replay_to(snap.date)

            # Stock value at snap.date prices
            stock_value = 0.0
            missing = []
            for tk, qty in holdings.items():
                if qty <= 1e-9:
                    continue
                price = _priced(tk, snap.date)
                if price is None or price <= 0:
                    missing.append(tk)
                    missing_prices_summary[tk] = missing_prices_summary.get(tk, 0) + 1
                    continue
                stock_value += qty * float(price)

            new_total = stock_value + cash

            before = {
                'total_value': round(float(snap.total_value or 0), 2),
                'stock_value': round(float(snap.stock_value or 0), 2),
                'cash_proceeds': round(float(snap.cash_proceeds or 0), 2),
                'max_cash_deployed': round(float(snap.max_cash_deployed or 0), 2),
            }
            after = {
                'total_value': round(new_total, 2),
                'stock_value': round(stock_value, 2),
                'cash_proceeds': round(cash, 2),
                'max_cash_deployed': round(deployed, 2),
            }
            change = {
                'date': snap.date.isoformat(),
                'before': before,
                'after': after,
                'delta_total_value': round(after['total_value'] - before['total_value'], 2),
                'missing_prices': missing,
            }
            changes.append(change)

            if not dry_run:
                snap.stock_value = stock_value
                snap.cash_proceeds = cash
                snap.max_cash_deployed = deployed
                snap.total_value = new_total
        except Exception as e:
            errors.append({'date': snap.date.isoformat(), 'error': str(e)})

    # ── Intraday loop ──────────────────────────────────────────────────
    # PortfolioSnapshotIntraday is what 1D and 5D ("1W") charts read from.
    # Without recomputing these, a phantom-cleanup leaves a visible cliff
    # on the short-period charts even after daily snapshots are fixed.
    # We use the daily close price (snap.timestamp.date()) for stock_value
    # — intraday-grade prices aren't available historically, but daily
    # close is a good enough approximation for these charts.
    for snap in intraday_snaps:
        try:
            holdings, cash, deployed = _replay_to(snap.timestamp)

            stock_value = 0.0
            missing = []
            snap_date = snap.timestamp.date()
            for tk, qty in holdings.items():
                if qty <= 1e-9:
                    continue
                price = _priced(tk, snap_date)
                if price is None or price <= 0:
                    missing.append(tk)
                    missing_prices_summary[tk] = missing_prices_summary.get(tk, 0) + 1
                    continue
                stock_value += qty * float(price)

            new_total = stock_value + cash

            before = {
                'total_value': round(float(snap.total_value or 0), 2),
                'stock_value': round(float(snap.stock_value or 0), 2),
                'cash_proceeds': round(float(snap.cash_proceeds or 0), 2),
                'max_cash_deployed': round(float(snap.max_cash_deployed or 0), 2),
            }
            after = {
                'total_value': round(new_total, 2),
                'stock_value': round(stock_value, 2),
                'cash_proceeds': round(cash, 2),
                'max_cash_deployed': round(deployed, 2),
            }
            intraday_changes.append({
                'timestamp': snap.timestamp.isoformat(),
                'before': before,
                'after': after,
                'delta_total_value': round(after['total_value'] - before['total_value'], 2),
                'missing_prices': missing,
            })

            if not dry_run:
                snap.stock_value = stock_value
                snap.cash_proceeds = cash
                snap.max_cash_deployed = deployed
                snap.total_value = new_total
        except Exception as e:
            errors.append({'timestamp': snap.timestamp.isoformat(), 'error': str(e)})

    # ── User row sync ──────────────────────────────────────────────────
    # Snapshots reflect historical state but the live iOS header value
    # (mobile_api.py:713-720) and the intraday cron's
    # calculate_portfolio_value_with_cash both read from User.cash_proceeds
    # / User.max_cash_deployed. If those are stale from a pre-cleanup era,
    # every new intraday row will be wrong AND the header dollar value
    # shown on the portfolio detail screen will be wrong — even when the
    # snapshots themselves are perfect.
    user_state_change = None
    if sync_user_state:
        try:
            _, sync_cash, sync_deployed = _replay_to(_dt.utcnow())
            # max_cash_deployed must respect current cost-basis floor.
            # If the user currently holds positions worth more than the
            # replay says was ever deployed, we trust the holdings (their
            # capital had to come from somewhere). Mirrors logic in
            # /admin/delete-transactions.
            cost_basis_floor = 0.0
            for s in current_stocks:
                cost_basis_floor += float(s.quantity or 0) * float(s.purchase_price or 0)
            if sync_deployed < cost_basis_floor:
                sync_deployed = cost_basis_floor
            user_state_change = {
                'before': {
                    'cash_proceeds': round(float(user.cash_proceeds or 0), 2),
                    'max_cash_deployed': round(float(user.max_cash_deployed or 0), 2),
                },
                'after': {
                    'cash_proceeds': round(sync_cash, 2),
                    'max_cash_deployed': round(sync_deployed, 2),
                },
                'cost_basis_floor': round(cost_basis_floor, 2),
            }
            if not dry_run:
                user.cash_proceeds = sync_cash
                user.max_cash_deployed = sync_deployed
        except Exception as e:
            errors.append({'sync_user_state_error': str(e)})

    if not dry_run:
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            return jsonify({'error': f'commit failed: {e}'}), 500

    # Trim very long change lists for response readability. Full data only
    # on dry-run, otherwise show first 10 + last 10 + a count placeholder.
    truncated = False
    sample = changes
    if len(changes) > 25 and not dry_run:
        sample = changes[:10] + [{'note': f'... {len(changes) - 20} more dates ...'}] + changes[-10:]
        truncated = True

    intraday_truncated = False
    intraday_sample = intraday_changes
    if len(intraday_changes) > 25 and not dry_run:
        intraday_sample = (
            intraday_changes[:10]
            + [{'note': f'... {len(intraday_changes) - 20} more timestamps ...'}]
            + intraday_changes[-10:]
        )
        intraday_truncated = True

    earliest = min((c['date'] for c in changes if 'date' in c), default=None)
    latest = max((c['date'] for c in changes if 'date' in c), default=None)
    total_delta = sum(c.get('delta_total_value', 0) for c in changes if 'delta_total_value' in c)
    intraday_total_delta = sum(
        c.get('delta_total_value', 0) for c in intraday_changes if 'delta_total_value' in c
    )

    return jsonify({
        'user_id': user_id,
        'username': user.username,
        'dry_run': dry_run,
        'snapshots_processed': len(changes),
        'intraday_snapshots_processed': len(intraday_changes),
        'date_range': {'earliest': earliest, 'latest': latest},
        'sum_delta_total_value': round(total_delta, 2),
        'sum_intraday_delta_total_value': round(intraday_total_delta, 2),
        'user_state_change': user_state_change,
        'errors': errors,
        'missing_prices_summary': missing_prices_summary,
        'changes': sample,
        'changes_truncated': truncated,
        'intraday_changes': intraday_sample,
        'intraday_changes_truncated': intraday_truncated,
        'next_step': (
            'remove dry_run=1 to execute' if dry_run
            else (
                f'invalidate caches @ /admin/invalidate-chart-cache?user_id={user_id}'
                if include_intraday else
                f'verify @ /admin/debug-user-snapshots?user_id={user_id} (or just check the iOS chart)'
            )
        ),
    })


@app.route('/admin/invalidate-chart-cache', methods=['GET', 'POST'])
@admin_2fa_required
def admin_invalidate_chart_cache():
    """Delete cached chart / leaderboard JSON so the next request regenerates
    from the (possibly just-recomputed) snapshot tables.

    Two caches are involved:
      - UserPortfolioChartCache: per-user, per-period pre-rendered chart JSON.
        Backs the iOS portfolio detail screen and leaderboard chart sparklines.
      - LeaderboardCache: global per-period leaderboard rankings JSON. Only
        invalidate this when corrections meaningfully change a user's ranking.

    Query params:
        user_id              — required (or pass `username` instead)
        username             — alternative to user_id
        clear_leaderboard    — if 1/true, also delete LeaderboardCache rows
        dry_run              — preview without writing
    """
    from models import db, User, UserPortfolioChartCache, LeaderboardCache

    user_id = request.args.get('user_id', type=int)
    username = request.args.get('username', type=str)
    if not user_id and not username:
        return jsonify({'error': 'user_id or username required'}), 400
    dry_run = request.args.get('dry_run') in ('1', 'true', 'yes')
    clear_leaderboard = request.args.get('clear_leaderboard') in ('1', 'true', 'yes')

    if user_id:
        user = User.query.get(user_id)
    else:
        user = User.query.filter_by(username=username).first()
    if not user:
        return jsonify({'error': f'user not found (user_id={user_id} username={username})'}), 404
    user_id = user.id

    # Find rows that would be deleted so the response can preview them.
    user_cache_rows = UserPortfolioChartCache.query.filter_by(user_id=user_id).all()
    user_cache_summary = [
        {
            'period': c.period,
            'generated_at': c.generated_at.isoformat() if c.generated_at else None,
            'size_bytes': len(c.chart_data or ''),
        }
        for c in user_cache_rows
    ]

    leaderboard_rows = []
    if clear_leaderboard:
        leaderboard_rows = LeaderboardCache.query.all()
    leaderboard_summary = [
        {
            'period': c.period,
            'generated_at': c.generated_at.isoformat() if c.generated_at else None,
        }
        for c in leaderboard_rows
    ]

    deleted_user_cache = 0
    deleted_leaderboard = 0
    if not dry_run:
        try:
            deleted_user_cache = (
                UserPortfolioChartCache.query.filter_by(user_id=user_id).delete()
            )
            if clear_leaderboard:
                deleted_leaderboard = LeaderboardCache.query.delete()
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            return jsonify({'error': f'commit failed: {e}'}), 500

    return jsonify({
        'user_id': user_id,
        'username': user.username,
        'dry_run': dry_run,
        'user_chart_cache_rows': user_cache_summary,
        'user_chart_cache_deleted': deleted_user_cache,
        'leaderboard_cache_rows': leaderboard_summary if clear_leaderboard else 'not requested',
        'leaderboard_cache_deleted': deleted_leaderboard,
        'next_step': (
            'remove dry_run=1 to execute' if dry_run
            else 'open the iOS app and force-refresh the chart; cache regenerates on next request'
        ),
    })


@app.route('/admin/manual-intraday-collection')
@admin_2fa_required  
def manual_intraday_collection():
    """Admin endpoint to manually trigger intraday collection"""
    
    try:
        from datetime import datetime
        from models import User, PortfolioSnapshotIntraday
        from portfolio_performance import PortfolioPerformanceCalculator
        
        calculator = PortfolioPerformanceCalculator()
        current_time = datetime.now()
        
        # Get all users with portfolios
        users = User.query.all()
        results = {
            'timestamp': current_time.isoformat(),
            'snapshots_created': 0,
            'users_processed': 0,
            'errors': []
        }
        
        for user in users:
            try:
                # Calculate current portfolio value
                portfolio_value = calculator.calculate_portfolio_value(user.id)
                
                if portfolio_value > 0:  # Only create snapshots for users with portfolios
                    # Create intraday snapshot
                    snapshot = PortfolioSnapshotIntraday(
                        user_id=user.id,
                        timestamp=current_time,
                        total_value=portfolio_value
                    )
                    db.session.add(snapshot)
                    results['snapshots_created'] += 1
                    
                results['users_processed'] += 1
                
            except Exception as e:
                error_msg = f"Error processing user {user.id}: {str(e)}"
                logger.error(error_msg)
                results['errors'].append(error_msg)
        
        # Commit all snapshots
        db.session.commit()
        
        flash(f'Manual intraday collection completed: {results["snapshots_created"]} snapshots created for {results["users_processed"]} users', 'success')
        return redirect(url_for('admin_dashboard'))
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error in manual intraday collection: {str(e)}")
        flash(f'Error in manual collection: {str(e)}', 'danger')
        return redirect(url_for('admin_dashboard'))




@app.route('/api/cron/monthly-payouts', methods=['POST', 'GET'])
def monthly_payouts_cron():
    """Month-end creator payout pipeline (runs on the 3rd of each month).

    Generates the PRIOR month's XeroPayoutRecord rows and syncs them to Xero as
    ACCPAY bills, so the operator can open Xero -> Bills to pay and see exactly
    which checks to cut. Creates bills only — never marks anything paid (cutting
    the physical check stays manual). End-to-end idempotent: generation is guarded
    by the unique (creator, period) index and the Xero sync skips already-synced /
    W-9-held records, so an accidental re-run is harmless.
    """
    try:
        auth_error = verify_cron_request()
        if auth_error:
            return auth_error

        from mobile_api import run_monthly_payout_pipeline
        result = run_monthly_payout_pipeline()
        logger.info(f"[CRON monthly-payouts] {result}")
        return jsonify({'success': True, **result}), 200

    except Exception as e:
        logger.error(f"[CRON monthly-payouts] error: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return jsonify({'error': f'monthly_payouts_failed: {e}'}), 500


@app.route('/api/cron/market-open', methods=['POST', 'GET'])
def market_open_cron():
    """Market open cron job endpoint - initializes daily tracking"""
    try:
        auth_error = verify_cron_request()
        if auth_error:
            return auth_error
        
        # Use Eastern Time for market operations
        current_time = get_market_time()
        today_et = current_time.date()
        
        logger.info(f"Market open cron job executed at {current_time.strftime('%Y-%m-%d %H:%M:%S %Z')} (ET date: {today_et})")
        
        # Process queued after-hours email trades
        queued_result = {'executed': 0, 'failed': 0, 'total': 0}
        try:
            from services.trading_email import process_queued_trades
            queued_result = process_queued_trades()
            logger.info(f"Queued email trades processed: {queued_result}")
        except Exception as e:
            logger.error(f"Error processing queued email trades: {e}")
        
        return jsonify({
            'success': True,
            'message': 'Market open processing completed',
            'timestamp': current_time.isoformat(),
            'market_date_et': today_et.isoformat(),
            'timezone': 'America/New_York',
            'queued_trades': queued_result,
        }), 200
    
    except Exception as e:
        logger.error(f"Unexpected error in market open: {str(e)}")
        return jsonify({'error': f'Unexpected error: {str(e)}'}), 500

@app.route('/api/cron/market-close', methods=['POST', 'GET'])
def market_close_cron():
    """Market close cron job endpoint - creates EOD snapshots and updates leaderboards
    
    Pipeline phases:
      0.5  – Dividend detection (must run BEFORE snapshots so today's dividends
             are reflected in each user's cash_proceeds at snapshot-write time)
      1    – Portfolio snapshots
      1.5  – S&P 500 close data
      1.75 – Commit core data
      2    – Leaderboard JSON cache
      2.25 – Portfolio stats
      2.4  – Commit cache data
      3.5  – S&P 500 verification
    """
    # Force cache invalidation marker
    _rebuild_marker = os.environ.get('VERCEL_DEPLOYMENT_ID', 'local')
    
    # LOG DEPLOYMENT VERSION for debugging
    commit_sha = os.environ.get('VERCEL_GIT_COMMIT_SHA', 'UNKNOWN')
    logger.info(f"🔄 CRON DEPLOYMENT VERSION - Commit SHA: {commit_sha}")
    logger.info(f"🔄 Deployment ID: {_rebuild_marker}")
    
    try:
        auth_error = verify_cron_request()
        if auth_error:
            return auth_error
        
        logger.info(f"Market close cron triggered via {request.method}")
        
        from models import User, PortfolioSnapshot
        from portfolio_performance import PortfolioPerformanceCalculator
        from leaderboard_utils import update_leaderboard_cache
        from cash_tracking import calculate_portfolio_value_with_cash
        
        # Use Eastern Time for market operations
        current_time = get_market_time()
        today_et = current_time.date()
        
        # CHECK: Skip if market holiday (NYSE/NASDAQ closed)
        if is_market_holiday(today_et):
            logger.info(f"Market closed for holiday on {today_et} - skipping market close pipeline")
            return jsonify({
                'success': True,
                'skipped': True,
                'reason': 'market_holiday',
                'date': today_et.isoformat(),
                'message': f'Market closed for holiday on {today_et}'
            }), 200
        
        results = {
            'code_version': 'v5-lb-errors',
            'timestamp': current_time.isoformat(),
            'market_date_et': today_et.isoformat(),
            'timezone': 'America/New_York',
            'users_processed': 0,
            'snapshots_created': 0,
            'snapshots_updated': 0,
            'leaderboard_updated': False,
            'errors': [],
            'pipeline_phases': []
        }
        
        logger.info(f"Market close cron executing for {today_et} (ET)")
        
        # ATOMIC MARKET CLOSE PIPELINE - All phases must succeed or all rollback
        try:
            # PHASE 0.5: Automatic Dividend Detection (must run BEFORE snapshots)
            # Check all held tickers for ex-dividend dates and credit users.
            # This MUST happen before Phase 1 so that the snapshot's cash_proceeds
            # field reflects today's dividends. calculate_cash_proceeds_as_of_date()
            # in Phase 1 replays from the Transaction table, so dividend rows must
            # already exist (committed or session-pending) when snapshots are written.
            try:
                logger.info("PHASE 0.5: Checking for dividends (pre-snapshot)...")
                results['pipeline_phases'].append('dividends_started')
                
                from dividend_tracker import process_dividends_for_date
                div_results = process_dividends_for_date(db, target_date=today_et)
                
                results['dividends_found'] = div_results.get('dividends_found', 0)
                results['dividends_recorded'] = div_results.get('dividends_recorded', 0)
                results['dividend_total_amount'] = div_results.get('total_amount', 0.0)
                
                if div_results.get('dividends_recorded', 0) > 0:
                    db.session.commit()
                    logger.info(f"✅ PHASE 0.5 Complete: {div_results['dividends_recorded']} dividends recorded (${div_results['total_amount']:.2f} total) BEFORE snapshots")
                else:
                    logger.info(f"PHASE 0.5 Complete: No dividends for {today_et}")
                
                results['pipeline_phases'].append('dividends_completed')
                
            except Exception as e:
                logger.warning(f"PHASE 0.5 WARNING: Dividend check failed (non-critical): {e}")
                results['errors'].append(f"Dividend check failed: {str(e)}")
                try:
                    db.session.rollback()
                except Exception:
                    pass
                # Non-critical — continue with snapshot writes (snapshots will be
                # missing today's dividends, but the next cron run / drift detector
                # will catch any drift on the user.cash_proceeds front)
            
            # PHASE 1: Create/Update Portfolio Snapshots
            logger.info("PHASE 1: Creating portfolio snapshots...")
            results['pipeline_phases'].append('snapshots_started')
            
            # OPTIMIZATION: Batch fetch all stock prices ONCE before processing users
            from models import Stock
            users = User.query.all()
            
            # Collect all unique tickers across all users
            unique_tickers = set()
            unique_tickers.add('SPY')  # Always include SPY for S&P 500
            
            for user in users:
                user_stocks = Stock.query.filter_by(user_id=user.id).all()
                for stock in user_stocks:
                    if stock.quantity > 0:
                        unique_tickers.add(stock.ticker.upper())
            
            logger.info(f"📊 Batch API (Market Close): Fetching {len(unique_tickers)} unique tickers for {len(users)} users")
            
            # Batch fetch all prices in 1-2 API calls
            calculator = PortfolioPerformanceCalculator()
            batch_prices = calculator.get_batch_stock_data(list(unique_tickers))
            logger.info(f"✅ Batch API Success: Retrieved {len(batch_prices)} prices")
            
            # Now process each user (prices already cached from batch call above)
            for user in users:
                try:
                    # Calculate portfolio value WITH cash tracking for today (using ET date)
                    # Stock prices are now served from cache (batch call above)
                    portfolio_data = calculate_portfolio_value_with_cash(user.id, today_et)
                    
                    total_value = portfolio_data['total_value']
                    stock_value = portfolio_data['stock_value']
                    cash_proceeds = portfolio_data['cash_proceeds']
                    
                    logger.info(f"User {user.id} ({user.username}): total=${total_value:.2f}, stock=${stock_value:.2f}, cash=${cash_proceeds:.2f} on {today_et}")
                    
                    # Skip if portfolio value is 0 or None (indicates calculation failure)
                    if total_value is None or total_value <= 0:
                        error_msg = f"User {user.id} ({user.username}): Skipping - portfolio value is {total_value}"
                        results['errors'].append(error_msg)
                        logger.warning(error_msg)
                        continue
                    
                    # UPSERT: Atomic insert-or-update to avoid UniqueViolation
                    # from Vercel read-replica lag (ORM query may miss existing rows)
                    from sqlalchemy.dialects.postgresql import insert as pg_insert
                    stmt = pg_insert(PortfolioSnapshot).values(
                        user_id=user.id,
                        date=today_et,
                        total_value=total_value,
                        stock_value=stock_value,
                        cash_proceeds=cash_proceeds,
                        max_cash_deployed=user.max_cash_deployed,
                        cash_flow=0
                    ).on_conflict_do_update(
                        constraint='unique_user_date_snapshot',
                        set_={
                            'total_value': total_value,
                            'stock_value': stock_value,
                            'cash_proceeds': cash_proceeds,
                            'max_cash_deployed': user.max_cash_deployed,
                        }
                    )
                    result = db.session.execute(stmt)
                    # rowcount == 1 for both insert and update in PostgreSQL
                    results['snapshots_created'] += 1
                    logger.info(f"Upserted snapshot for user {user.id}: ${total_value:.2f} on {today_et}")
                    
                    results['users_processed'] += 1
                    
                except Exception as e:
                    error_msg = f"Error processing user {user.id} ({user.username}): {str(e)}"
                    results['errors'].append(error_msg)
                    logger.error(f"Market close user {user.id} error: {e}")
                    import traceback
                    logger.error(f"Traceback: {traceback.format_exc()}")
                    # Don't fail the entire pipeline for individual user errors
            
            results['pipeline_phases'].append('snapshots_completed')
            logger.info(f"PHASE 1 Complete: {results['snapshots_created']} created, {results['snapshots_updated']} updated")
            
            # PHASE 1.5: Collect S&P 500 Market Close Data
            logger.info("PHASE 1.5: Collecting S&P 500 market close data...")
            results['pipeline_phases'].append('sp500_started')
            
            try:
                # SPY data already fetched in batch call above - retrieve from cache
                if 'SPY' in batch_prices:
                    spy_price = batch_prices['SPY']
                    logger.info(f"SPY data collected: ${spy_price} (S&P 500: ${spy_price * 10}) on {today_et}")
                    spy_data = {'price': spy_price}
                else:
                    # Fallback: Individual call if batch somehow failed for SPY
                    logger.warning("SPY not in batch results - falling back to individual call")
                    spy_data = calculator.get_stock_data('SPY')
                
                if spy_data and spy_data.get('price'):
                    spy_price = spy_data['price']
                    sp500_value = spy_price * 10  # Convert SPY to S&P 500 approximation
                    
                    # Check if S&P 500 data already exists for today
                    from models import MarketData
                    existing_sp500 = MarketData.query.filter_by(
                        ticker='SPY_SP500',
                        date=today_et
                    ).first()
                    
                    if existing_sp500:
                        existing_sp500.close_price = sp500_value
                        logger.info(f"Updated S&P 500 data for {today_et}: ${sp500_value:.2f}")
                    else:
                        market_data = MarketData(
                            ticker='SPY_SP500',
                            date=today_et,
                            close_price=sp500_value
                        )
                        db.session.add(market_data)
                        logger.info(f"Created S&P 500 data for {today_et}: ${sp500_value:.2f}")
                    
                    # Flush to write to DB immediately (but don't commit yet - part of atomic transaction)
                    db.session.flush()
                    logger.info(f"Flushed S&P 500 data to session")
                    
                    results['sp500_data_collected'] = True
                else:
                    error_msg = "Failed to fetch SPY data for S&P 500"
                    results['errors'].append(error_msg)
                    logger.error(error_msg)
                    results['sp500_data_collected'] = False
            
            except Exception as e:
                error_msg = f"Error collecting S&P 500 data: {str(e)}"
                results['errors'].append(error_msg)
                logger.error(error_msg)
                results['sp500_data_collected'] = False
            
            results['pipeline_phases'].append('sp500_completed')
            logger.info(f"PHASE 1.5 Complete: S&P 500 data collection {'succeeded' if results.get('sp500_data_collected') else 'failed'}")
            
            # PHASE 1.75: Commit ALL core data (snapshots + S&P 500) before cache operations
            # This isolates critical data from potential session corruption in later phases
            # Grok recommendation: Separate transactions for core data vs cache
            logger.info("PHASE 1.75: Committing core data (snapshots + S&P 500) atomically...")
            results['pipeline_phases'].append('core_commit_started')
            
            try:
                db.session.commit()
                logger.info(f"✅ PHASE 1.75 Complete: Committed {results['snapshots_created']} snapshots + S&P 500 data")
                results['core_data_committed'] = True
                results['pipeline_phases'].append('core_commit_completed')
            except Exception as e:
                logger.error(f"❌ PHASE 1.75 FAILED: Core data commit failed: {e}")
                db.session.rollback()
                results['core_data_committed'] = False
                results['errors'].append(f"Core data commit failed: {str(e)}")
                # CRITICAL FAILURE - return immediately
                return jsonify({
                    'success': False,
                    'message': 'Core data commit failed - snapshots and S&P 500 not saved',
                    'results': results
                }), 500
            
            # PHASE 1.8: (moved to PHASE 0.5 — see top of pipeline)
            # Dividend detection now runs BEFORE snapshot creation so today's
            # dividends are reflected in each user's snapshot cash_proceeds.
            
            # PHASE 2: Update Leaderboard JSON Cache + Portfolio Stats
            # Charts are now generated ON-DEMAND (not pre-generated here)
            # This dramatically reduces market-close cron execution time
            try:
                # Force-dispose ALL pooled connections and reset the ORM session.
                # db.session.rollback() and db.session.remove() are insufficient when
                # the underlying PostgreSQL connection is in an aborted transaction state.
                # db.engine.dispose() drops every connection in the pool, forcing new ones.
                try:
                    db.session.remove()
                    db.engine.dispose()
                except Exception:
                    pass
                
                logger.info("PHASE 2: Updating leaderboard JSON cache...")
                results['pipeline_phases'].append('leaderboard_started')
                
                updated_count = update_leaderboard_cache()
                results['leaderboard_updated'] = True
                results['leaderboard_entries_updated'] = updated_count
                
                # Surface any leaderboard calculation errors
                lb_errors = getattr(update_leaderboard_cache, '_last_errors', [])
                if lb_errors:
                    results['leaderboard_errors'] = lb_errors
                
                results['pipeline_phases'].append('leaderboard_completed')
                logger.info(f"PHASE 2 Complete: {updated_count} leaderboard entries updated (JSON only)")
                
                # PHASE 2.25: Update Portfolio Stats (unique stocks, trades/week, cap mix, industry mix, subscribers)
                # Fresh connections for stats phase
                try:
                    db.session.remove()
                    db.engine.dispose()
                except Exception:
                    pass
                
                logger.info("PHASE 2.25: Updating portfolio stats for all users...")
                results['pipeline_phases'].append('portfolio_stats_started')
                
                try:
                    from leaderboard_utils import calculate_user_portfolio_stats
                    from models import UserPortfolioStats
                    
                    stats_updated = 0
                    for user in users:
                        try:
                            stats = calculate_user_portfolio_stats(user.id)
                            
                            user_stats = UserPortfolioStats.query.filter_by(user_id=user.id).first()
                            if not user_stats:
                                user_stats = UserPortfolioStats(user_id=user.id)
                                db.session.add(user_stats)
                            
                            user_stats.unique_stocks_count = stats['unique_stocks_count']
                            user_stats.avg_trades_per_week = stats['avg_trades_per_week']
                            user_stats.total_trades = stats['total_trades']
                            user_stats.large_cap_percent = stats['large_cap_percent']
                            user_stats.small_cap_percent = stats['small_cap_percent']
                            user_stats.industry_mix = stats['industry_mix']
                            user_stats.subscriber_count = stats['subscriber_count']
                            # Phase E: fractional-shares flag for Discover/Leaderboard filter.
                            user_stats.has_fractional_holdings = stats.get('has_fractional_holdings', False)
                            user_stats.last_updated = stats['last_updated']
                            
                            stats_updated += 1
                            
                        except Exception as e:
                            error_msg = f"Error updating stats for user {user.id}: {str(e)}"
                            results['errors'].append(error_msg)
                            logger.error(error_msg)
                            try:
                                db.session.rollback()
                            except Exception:
                                try:
                                    db.session.remove()
                                    db.engine.dispose()
                                except Exception:
                                    pass
                    
                    results['portfolio_stats_updated'] = stats_updated
                    results['pipeline_phases'].append('portfolio_stats_completed')
                    logger.info(f"PHASE 2.25 Complete: {stats_updated} user portfolio stats updated")
                    
                except Exception as e:
                    error_msg = f"Portfolio stats update error: {str(e)}"
                    results['errors'].append(error_msg)
                    logger.error(f"PHASE 2.25 FAILED: {error_msg}")
                
            except Exception as e:
                error_msg = f"Leaderboard cache update failed: {str(e)}"
                results['errors'].append(error_msg)
                logger.error(f"PHASE 2 FAILED: {error_msg}")
                logger.error("Core data (snapshots + S&P 500) is safe (committed in Phase 1.75)")
                import traceback
                logger.error(f"Full traceback:\n{traceback.format_exc()}")
            
            # PHASE 2.4: Commit leaderboard cache + portfolio stats
            try:
                db.session.commit()
                results['cache_committed'] = True
                results['pipeline_phases'].append('cache_commit_completed')
                logger.info("PHASE 2.4: Leaderboard cache + stats committed")
            except Exception as e:
                results['cache_committed'] = False
                results['errors'].append(f"Cache commit failed: {str(e)}")
                logger.error(f"PHASE 2.4 FAILED: {str(e)}")
                try:
                    db.session.rollback()
                except Exception:
                    pass
            
            # PHASE 3.5: VERIFICATION - Confirm S&P 500 data actually persisted
            logger.info("PHASE 3.5: Verifying S&P 500 data persistence...")
            from models import MarketData
            from sqlalchemy import text
            import time
            
            # FIX: Vercel Postgres uses read replicas with lag (50-500ms)
            # Solution: Query PRIMARY connection directly + retry with sleep
            
            # Sleep to allow replica sync
            time.sleep(0.5)
            logger.info("Waited 500ms for replica sync")
            
            # Retry verification 3x with backoff (in case of replica lag)
            verify_sp500 = None
            for attempt in range(3):
                try:
                    # Use raw SQL on engine to force primary connection
                    with db.engine.connect() as primary_conn:
                        result = primary_conn.execute(text("""
                            SELECT close_price FROM market_data 
                            WHERE ticker = 'SPY_SP500' AND date = :date
                        """), {'date': today_et})
                        row = result.fetchone()
                        
                        if row:
                            verify_sp500 = row[0]
                            logger.info(f"✅ VERIFIED on PRIMARY (attempt {attempt+1}): S&P 500 data exists for {today_et}: ${float(verify_sp500):.2f}")
                            break
                        else:
                            logger.warning(f"Attempt {attempt+1}: S&P 500 data not yet visible on primary")
                            if attempt < 2:
                                time.sleep(0.2 * (attempt + 1))  # Backoff: 200ms, 400ms
                except Exception as verify_err:
                    logger.error(f"Verification attempt {attempt+1} error: {verify_err}")
                    if attempt < 2:
                        time.sleep(0.2 * (attempt + 1))
            
            if verify_sp500:
                results['sp500_verification'] = 'SUCCESS'
                results['sp500_verified_value'] = float(verify_sp500)
            else:
                logger.error(f"❌ VERIFICATION FAILED on PRIMARY after 3 attempts: S&P 500 data NOT found for {today_et}")
                logger.error(f"This indicates a write failure, not just replication lag")
                results['sp500_verification'] = 'FAILED'
                results['errors'].append(f"S&P 500 data missing after commit for {today_et}")
            
        except Exception as e:
            # ROLLBACK: Only affects uncommitted changes (cache operations)
            # Core data (snapshots + S&P 500) already committed in Phase 1.75
            logger.error(f"PIPELINE FAILURE: {str(e)}")
            db.session.rollback()
            
            error_msg = f"Pipeline failure: {str(e)}"
            results['errors'].append(error_msg)
            results['pipeline_phases'].append('rollback_completed')
            
            # Check if core data was committed before failure
            if results.get('core_data_committed'):
                logger.info("✅ Core data (snapshots + S&P 500) is safe despite failure")
                response = jsonify({
                    'success': True,  # Partial success - core data saved
                    'partial': True,
                    'message': 'Core data saved successfully, but cache updates failed',
                    'results': results,
                    'error': error_msg
                })
                response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
                return response, 200
            else:
                response = jsonify({
                    'success': False,
                    'message': 'Market close pipeline failed - no data saved',
                    'results': results,
                    'error': error_msg
                })
                response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
                return response, 500
        
        response = jsonify({
            'success': True,
            'message': 'Atomic market close pipeline completed successfully',
            'results': results
        })
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        return response, 200
    
    except Exception as e:
        logger.error(f"Unexpected error in market close: {str(e)}")
        error_response = jsonify({'error': f'Unexpected error: {str(e)}'})
        error_response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        return error_response, 500

@app.route('/admin/trigger-market-close-backfill', methods=['GET', 'POST'])
@admin_2fa_required
def admin_trigger_market_close_backfill():
    """Admin endpoint to manually trigger market close pipeline for specific date (backfill missing snapshots)"""
    try:
        # Handle GET request - show form
        if request.method == 'GET':
            return '''
            <!DOCTYPE html>
            <html>
            <head>
                <title>Market Close Backfill Tool</title>
                <style>
                    body { font-family: Arial, sans-serif; max-width: 600px; margin: 50px auto; padding: 20px; }
                    .form-group { margin: 20px 0; }
                    label { display: block; margin-bottom: 5px; font-weight: bold; }
                    input[type="date"] { padding: 8px; font-size: 16px; width: 200px; }
                    button { background: #007cba; color: white; padding: 10px 20px; border: none; border-radius: 4px; font-size: 16px; cursor: pointer; }
                    button:hover { background: #005a87; }
                    .info { background: #e7f3ff; padding: 15px; border-radius: 4px; margin: 20px 0; }
                    .warning { background: #fff3cd; padding: 15px; border-radius: 4px; margin: 20px 0; border-left: 4px solid #ffc107; }
                    #result { margin-top: 20px; padding: 15px; border-radius: 4px; display: none; }
                    .success { background: #d4edda; border-left: 4px solid #28a745; }
                    .error { background: #f8d7da; border-left: 4px solid #dc3545; }
                </style>
            </head>
            <body>
                <h1>🔧 Market Close Backfill Tool</h1>
                
                <div class="info">
                    <strong>Purpose:</strong> This tool manually creates portfolio snapshots for a specific trading day. 
                    Use this to backfill missing data that should have been created by the daily market close pipeline.
                </div>
                
                <div class="warning">
                    <strong>⚠️ Important:</strong> Only use this for past trading days (Monday-Friday). 
                    Weekend dates will be rejected. This tool calculates portfolio values using historical stock prices.
                </div>
                
                <form id="backfillForm">
                    <div class="form-group">
                        <label for="targetDate">Target Date (YYYY-MM-DD):</label>
                        <input type="date" id="targetDate" name="date" value="2025-09-26" required>
                        <small>Default: Friday, September 26, 2025 (the missing trading day)</small>
                    </div>
                    
                    <button type="submit">🚀 Trigger Market Close Backfill</button>
                </form>
                
                <div id="result"></div>
                
                <script>
                document.getElementById('backfillForm').addEventListener('submit', async function(e) {
                    e.preventDefault();
                    
                    const button = e.target.querySelector('button');
                    const resultDiv = document.getElementById('result');
                    const targetDate = document.getElementById('targetDate').value;
                    
                    // Show loading state
                    button.textContent = '⏳ Processing...';
                    button.disabled = true;
                    resultDiv.style.display = 'none';
                    
                    try {
                        const response = await fetch('/admin/trigger-market-close-backfill', {
                            method: 'POST',
                            headers: {
                                'Content-Type': 'application/json',
                            },
                            body: JSON.stringify({ date: targetDate })
                        });
                        
                        const data = await response.json();
                        
                        // Show result
                        resultDiv.style.display = 'block';
                        
                        if (data.success) {
                            resultDiv.className = 'success';
                            resultDiv.innerHTML = `
                                <h3>✅ Backfill Successful!</h3>
                                <p><strong>Date:</strong> ${data.results.target_date}</p>
                                <p><strong>Users Processed:</strong> ${data.results.users_processed}</p>
                                <p><strong>Snapshots Created:</strong> ${data.results.snapshots_created}</p>
                                <p><strong>Snapshots Updated:</strong> ${data.results.snapshots_updated}</p>
                                <p><strong>Leaderboard Updated:</strong> ${data.results.leaderboard_updated ? 'Yes' : 'No'}</p>
                                ${data.results.errors.length > 0 ? '<p><strong>Errors:</strong> ' + data.results.errors.join(', ') + '</p>' : ''}
                            `;
                        } else {
                            resultDiv.className = 'error';
                            resultDiv.innerHTML = `
                                <h3>❌ Backfill Failed</h3>
                                <p><strong>Error:</strong> ${data.error || data.message}</p>
                            `;
                        }
                    } catch (error) {
                        resultDiv.style.display = 'block';
                        resultDiv.className = 'error';
                        resultDiv.innerHTML = `
                            <h3>❌ Request Failed</h3>
                            <p><strong>Error:</strong> ${error.message}</p>
                        `;
                    }
                    
                    // Reset button
                    button.textContent = '🚀 Trigger Market Close Backfill';
                    button.disabled = false;
                });
                </script>
            </body>
            </html>
            '''
        
        # Handle POST request - perform backfill
        target_date_str = request.json.get('date') if request.json else None
        if not target_date_str:
            return jsonify({'error': 'Date parameter required (YYYY-MM-DD format)'}), 400
        
        from datetime import datetime, date
        try:
            target_date = datetime.strptime(target_date_str, '%Y-%m-%d').date()
        except ValueError:
            return jsonify({'error': 'Invalid date format. Use YYYY-MM-DD'}), 400
        
        # Prevent future dates
        if target_date > date.today():
            return jsonify({'error': 'Cannot backfill future dates'}), 400
        
        from models import User, PortfolioSnapshot
        from portfolio_performance import PortfolioPerformanceCalculator
        from leaderboard_utils import update_leaderboard_cache
        
        current_time = datetime.now()
        
        results = {
            'target_date': target_date_str,
            'timestamp': current_time.isoformat(),
            'users_processed': 0,
            'snapshots_created': 0,
            'snapshots_updated': 0,
            'leaderboard_updated': False,
            'errors': [],
            'pipeline_phases': []
        }
        
        logger.info(f"ADMIN BACKFILL: Starting market close backfill for {target_date}")
        
        # ATOMIC BACKFILL PIPELINE
        try:
            from models import Stock
            users = User.query.all()
            # Shared calculator so historical_price_cache is reused across users
            calculator = PortfolioPerformanceCalculator()
            
            # PHASE 1: Create/Update Portfolio Snapshots for target date
            logger.info(f"PHASE 1: Creating portfolio snapshots for {target_date}...")
            results['pipeline_phases'].append('snapshots_started')
            
            for user in users:
                try:
                    # Use Stock table + historical prices (same as daily cron)
                    # The transaction-replay approach returns $0 for users without Transaction records
                    user_stocks = Stock.query.filter_by(user_id=user.id).all()
                    stock_value = 0.0
                    for stock in user_stocks:
                        if stock.quantity > 0:
                            price = calculator.get_historical_price(stock.ticker.upper(), target_date)
                            if price and price > 0:
                                stock_value += stock.quantity * price
                    
                    from cash_tracking import calculate_cash_proceeds_as_of_date
                    cash_proceeds = calculate_cash_proceeds_as_of_date(user.id, target_date)
                    total_value = stock_value + cash_proceeds
                    
                    # Skip if portfolio value is 0 or None
                    if total_value is None or total_value <= 0:
                        error_msg = f"User {user.id} ({user.username}): Skipping - portfolio value is {total_value} on {target_date}"
                        results['errors'].append(error_msg)
                        logger.warning(error_msg)
                        continue
                    
                    # UPSERT: Atomic insert-or-update to avoid UniqueViolation
                    from sqlalchemy.dialects.postgresql import insert as pg_insert
                    stmt = pg_insert(PortfolioSnapshot).values(
                        user_id=user.id,
                        date=target_date,
                        total_value=total_value,
                        stock_value=stock_value,
                        cash_proceeds=cash_proceeds,
                        max_cash_deployed=user.max_cash_deployed,
                        cash_flow=0
                    ).on_conflict_do_update(
                        constraint='unique_user_date_snapshot',
                        set_={
                            'total_value': total_value,
                            'stock_value': stock_value,
                            'cash_proceeds': cash_proceeds,
                            'max_cash_deployed': user.max_cash_deployed,
                        }
                    )
                    db.session.execute(stmt)
                    results['snapshots_created'] += 1
                    logger.info(f"Upserted snapshot for user {user.id} on {target_date}: ${total_value:.2f}")
                    
                    results['users_processed'] += 1
                    
                except Exception as e:
                    error_msg = f"Error processing user {user.id} for {target_date}: {str(e)}"
                    results['errors'].append(error_msg)
                    logger.error(error_msg)
            
            results['pipeline_phases'].append('snapshots_completed')
            logger.info(f"PHASE 1 Complete: {results['snapshots_created']} created, {results['snapshots_updated']} updated")
            
            # PHASE 1.5: Collect S&P 500 Market Close Data for target date
            logger.info(f"PHASE 1.5: Collecting S&P 500 market close data for {target_date}...")
            results['pipeline_phases'].append('sp500_started')
            
            try:
                calculator = PortfolioPerformanceCalculator()
                
                # For historical dates, get historical price (force_fetch to avoid cache issues)
                spy_price = calculator.get_historical_price('SPY', target_date, force_fetch=True)
                
                if spy_price and spy_price > 0:
                    sp500_value = spy_price * 10  # Convert SPY to S&P 500 approximation
                    
                    # Check if S&P 500 data already exists for target date
                    from models import MarketData
                    existing_sp500 = MarketData.query.filter_by(
                        ticker='SPY_SP500',
                        date=target_date
                    ).first()
                    
                    if existing_sp500:
                        existing_sp500.close_price = sp500_value
                        logger.info(f"Updated S&P 500 data for {target_date}: ${sp500_value:.2f}")
                    else:
                        market_data = MarketData(
                            ticker='SPY_SP500',
                            date=target_date,
                            close_price=sp500_value
                        )
                        db.session.add(market_data)
                        logger.info(f"Created S&P 500 data for {target_date}: ${sp500_value:.2f}")
                    
                    results['sp500_data_collected'] = True
                else:
                    error_msg = f"Failed to fetch SPY historical price for {target_date}"
                    results['errors'].append(error_msg)
                    logger.error(error_msg)
                    results['sp500_data_collected'] = False
            
            except Exception as e:
                error_msg = f"Error collecting S&P 500 data for {target_date}: {str(e)}"
                results['errors'].append(error_msg)
                logger.error(error_msg)
                results['sp500_data_collected'] = False
            
            results['pipeline_phases'].append('sp500_completed')
            logger.info(f"PHASE 1.5 Complete: S&P 500 data collection {'succeeded' if results.get('sp500_data_collected') else 'failed'}")
            
            # PHASE 2: Update Leaderboard Cache (includes chart cache generation)
            logger.info("PHASE 2: Updating leaderboard and chart caches...")
            results['pipeline_phases'].append('leaderboard_started')
            
            updated_count = update_leaderboard_cache()
            results['leaderboard_updated'] = True
            results['leaderboard_entries_updated'] = updated_count
            
            results['pipeline_phases'].append('leaderboard_completed')
            logger.info(f"PHASE 2 Complete: {updated_count} leaderboard entries updated")
            
            # PHASE 3: Atomic Database Commit
            logger.info("PHASE 3: Committing all changes atomically...")
            results['pipeline_phases'].append('commit_started')
            
            db.session.commit()
            
            results['pipeline_phases'].append('commit_completed')
            logger.info("PHASE 3 Complete: All changes committed successfully")
            
        except Exception as e:
            # ROLLBACK: Any failure rolls back entire pipeline
            logger.error(f"BACKFILL PIPELINE FAILURE: {str(e)}")
            db.session.rollback()
            
            error_msg = f"Backfill pipeline failure: {str(e)}"
            results['errors'].append(error_msg)
            results['pipeline_phases'].append('rollback_completed')
            
            return jsonify({
                'success': False,
                'message': f'Market close backfill failed for {target_date} - all changes rolled back',
                'results': results,
                'error': error_msg
            }), 500
        
        return jsonify({
            'success': True,
            'message': f'Market close backfill completed successfully for {target_date}',
            'results': results
        }), 200
        
    except Exception as e:
        logger.error(f"Error in market close backfill: {str(e)}")
        import traceback
        return jsonify({
            'success': False,
            'error': str(e),
            'details': 'Check server logs'
        }), 500


@app.route('/admin/historical-price-backfill-batch', methods=['GET', 'POST'])
@admin_2fa_required
def admin_historical_price_backfill_batch():
    """Admin endpoint to backfill historical prices in small batches to avoid Vercel timeout"""
    try:
        # Handle GET request - show batch interface
        if request.method == 'GET':
            from models import Stock
            
            # Get current progress
            all_stocks = Stock.query.all()
            unique_tickers = list(set(stock.ticker for stock in all_stocks))
            unique_tickers.append("SPY")  # S&P 500 proxy
            
            return f'''
            <!DOCTYPE html>
            <html>
            <head>
                <title>Historical Price Backfill - Batch Mode</title>
                <style>
                    body {{ font-family: Arial, sans-serif; max-width: 900px; margin: 20px auto; padding: 20px; }}
                    button {{ background: #28a745; color: white; padding: 12px 25px; border: none; border-radius: 4px; font-size: 16px; cursor: pointer; margin: 5px; }}
                    button:hover {{ background: #218838; }}
                    button:disabled {{ background: #6c757d; cursor: not-allowed; }}
                    .info {{ background: #e7f3ff; padding: 15px; border-radius: 4px; margin: 15px 0; }}
                    .warning {{ background: #fff3cd; padding: 15px; border-radius: 4px; margin: 15px 0; border-left: 4px solid #ffc107; }}
                    .critical {{ background: #f8d7da; padding: 15px; border-radius: 4px; margin: 15px 0; border-left: 4px solid #dc3545; }}
                    #results {{ margin-top: 20px; }}
                    .batch-result {{ margin: 10px 0; padding: 15px; border-radius: 4px; }}
                    .success {{ background: #d4edda; border-left: 4px solid #28a745; }}
                    .error {{ background: #f8d7da; border-left: 4px solid #dc3545; }}
                    .progress {{ background: #cce7ff; border-left: 4px solid #007bff; }}
                    .ticker-list {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(80px, 1fr)); gap: 5px; margin: 10px 0; }}
                    .ticker {{ background: #f8f9fa; padding: 5px; text-align: center; border-radius: 3px; font-family: monospace; }}
                </style>
            </head>
            <body>
                <h1>📈 Historical Price Backfill - Batch Mode</h1>
                
                <div class="critical">
                    <h3>🚨 VERCEL TIMEOUT SOLUTION</h3>
                    <p>The full backfill times out after 60 seconds. This batch mode processes 3-4 tickers at a time to stay under the limit.</p>
                </div>
                
                <div class="info">
                    <h3>📊 Tickers to Process ({len(unique_tickers)} total):</h3>
                    <div class="ticker-list">
                        {''.join(f'<div class="ticker">{ticker}</div>' for ticker in sorted(unique_tickers))}
                    </div>
                </div>
                
                <div class="warning">
                    <h3>⚡ Batch Processing Strategy:</h3>
                    <ul>
                        <li><strong>Batch Size:</strong> 3 tickers per batch (~45 seconds)</li>
                        <li><strong>Total Batches:</strong> ~{(len(unique_tickers) + 2) // 3} batches needed</li>
                        <li><strong>Processing Time:</strong> ~2 minutes per batch</li>
                        <li><strong>Total Time:</strong> ~{((len(unique_tickers) + 2) // 3) * 2} minutes for all data</li>
                    </ul>
                </div>
                
                <div style="text-align: center; margin: 30px 0;">
                    <button onclick="startBatchProcessing()" id="startBtn">
                        🚀 Start Batch Processing
                    </button>
                    <button onclick="processNextBatch()" id="nextBtn" style="display: none;">
                        ➡️ Process Next Batch
                    </button>
                </div>
                
                <div id="results"></div>
                
                <script>
                let currentBatch = 0;
                let totalBatches = {(len(unique_tickers) + 2) // 3};
                let allTickers = {sorted(unique_tickers)};
                
                async function startBatchProcessing() {{
                    currentBatch = 0;
                    document.getElementById('startBtn').style.display = 'none';
                    document.getElementById('results').innerHTML = '';
                    await processNextBatch();
                }}
                
                async function processNextBatch() {{
                    if (currentBatch >= totalBatches) {{
                        document.getElementById('results').innerHTML += `
                            <div class="batch-result success">
                                <h3>🎉 All Batches Complete!</h3>
                                <p>Historical price backfill finished. Check your dashboard for updated charts.</p>
                            </div>
                        `;
                        document.getElementById('nextBtn').style.display = 'none';
                        document.getElementById('startBtn').style.display = 'inline-block';
                        document.getElementById('startBtn').textContent = '🔄 Run Again';
                        return;
                    }}
                    
                    let startIdx = currentBatch * 3;
                    let endIdx = Math.min(startIdx + 3, allTickers.length);
                    let batchTickers = allTickers.slice(startIdx, endIdx);
                    
                    document.getElementById('results').innerHTML += `
                        <div class="batch-result progress">
                            <h3>🔄 Processing Batch ${{currentBatch + 1}}/${{totalBatches}}</h3>
                            <p><strong>Tickers:</strong> ${{batchTickers.join(', ')}}</p>
                            <p><em>Fetching historical prices... (~2 minutes)</em></p>
                        </div>
                    `;
                    
                    try {{
                        const response = await fetch('/admin/historical-price-backfill-batch', {{
                            method: 'POST',
                            headers: {{ 'Content-Type': 'application/json' }},
                            body: JSON.stringify({{ 
                                batch_tickers: batchTickers,
                                batch_number: currentBatch + 1
                            }})
                        }});
                        
                        const data = await response.json();
                        
                        if (data.success) {{
                            document.getElementById('results').lastElementChild.className = 'batch-result success';
                            document.getElementById('results').lastElementChild.innerHTML = `
                                <h3>✅ Batch ${{currentBatch + 1}} Complete</h3>
                                <p><strong>Tickers:</strong> ${{batchTickers.join(', ')}}</p>
                                <p><strong>Prices Fetched:</strong> ${{data.results.prices_fetched}}</p>
                                <p><strong>Snapshots Updated:</strong> ${{data.results.snapshots_updated}}</p>
                                <p><strong>Processing Time:</strong> ${{data.results.processing_time_seconds}}s</p>
                            `;
                        }} else {{
                            document.getElementById('results').lastElementChild.className = 'batch-result error';
                            document.getElementById('results').lastElementChild.innerHTML = `
                                <h3>❌ Batch ${{currentBatch + 1}} Failed</h3>
                                <p><strong>Error:</strong> ${{data.error}}</p>
                            `;
                        }}
                    }} catch (error) {{
                        document.getElementById('results').lastElementChild.className = 'batch-result error';
                        document.getElementById('results').lastElementChild.innerHTML = `
                            <h3>❌ Batch ${{currentBatch + 1}} Failed</h3>
                            <p><strong>Error:</strong> ${{error.message}}</p>
                        `;
                    }}
                    
                    currentBatch++;
                    
                    if (currentBatch < totalBatches) {{
                        document.getElementById('nextBtn').style.display = 'inline-block';
                    }} else {{
                        // Auto-process final steps
                        setTimeout(() => processNextBatch(), 1000);
                    }}
                }}
                </script>
            </body>
            </html>
            '''
        
        # Handle POST request - process batch
        import requests
        import time
        from datetime import date
        from models import Stock, PortfolioSnapshot, MarketData
        
        data = request.get_json()
        batch_tickers = data.get('batch_tickers', [])
        batch_number = data.get('batch_number', 1)
        
        start_time = datetime.now()
        
        results = {
            'batch_number': batch_number,
            'timestamp': start_time.isoformat(),
            'prices_fetched': 0,
            'snapshots_updated': 0,
            'sp500_updated': False,
            'errors': []
        }
        
        # Check API key
        api_key = os.environ.get('ALPHA_VANTAGE_API_KEY')
        if not api_key:
            return jsonify({
                'success': False,
                'error': 'ALPHA_VANTAGE_API_KEY not found'
            }), 400
        
        logger.info(f"Processing batch {batch_number} with tickers: {batch_tickers}")
        
        target_dates = [date(2025, 9, 25), date(2025, 9, 26)]
        historical_prices = {}
        
        # Fetch historical prices for this batch
        for target_date in target_dates:
            historical_prices[target_date] = {}
            
            for ticker in batch_tickers:
                try:
                    logger.info(f"Fetching {ticker} for {target_date}")
                    
                    # Alpha Vantage API call
                    url = "https://www.alphavantage.co/query"
                    params = {
                        'function': 'TIME_SERIES_DAILY',
                        'symbol': ticker,
                        'apikey': api_key,
                        'outputsize': 'compact'
                    }
                    
                    response = requests.get(url, params=params, timeout=30)
                    data_response = response.json()
                    
                    if 'Error Message' in data_response:
                        error_msg = f"API Error for {ticker}: {data_response['Error Message']}"
                        results['errors'].append(error_msg)
                        logger.error(error_msg)
                        continue
                        
                    if 'Note' in data_response:
                        error_msg = f"API Limit for {ticker}: {data_response['Note']}"
                        results['errors'].append(error_msg)
                        logger.warning(error_msg)
                        continue
                    
                    time_series = data_response.get('Time Series (Daily)', {})
                    date_str = target_date.strftime('%Y-%m-%d')
                    
                    if date_str in time_series:
                        close_price = float(time_series[date_str]['4. close'])
                        historical_prices[target_date][ticker] = close_price
                        results['prices_fetched'] += 1
                        logger.info(f"✅ {ticker} on {date_str}: ${close_price:.2f}")
                    else:
                        # Try previous trading day
                        available_dates = sorted(time_series.keys(), reverse=True)
                        for available_date in available_dates:
                            if available_date < date_str:
                                close_price = float(time_series[available_date]['4. close'])
                                historical_prices[target_date][ticker] = close_price
                                results['prices_fetched'] += 1
                                logger.info(f"📅 {ticker} using {available_date}: ${close_price:.2f}")
                                break
                    
                    # Rate limiting - Premium account: 150 calls per minute
                    time.sleep(0.5)  # 120 calls per minute (conservative)
                    
                except Exception as e:
                    error_msg = f"Error fetching {ticker}: {str(e)}"
                    results['errors'].append(error_msg)
                    logger.error(error_msg)
        
        # Update portfolio snapshots with correct values
        logger.info("Updating portfolio snapshots with historical prices...")
        
        for target_date in target_dates:
            date_prices = historical_prices.get(target_date, {})
            if not date_prices:
                continue
                
            snapshots = PortfolioSnapshot.query.filter_by(date=target_date).all()
            
            for snapshot in snapshots:
                user_stocks = Stock.query.filter_by(user_id=snapshot.user_id).all()
                correct_value = 0
                
                for stock in user_stocks:
                    if stock.quantity > 0 and stock.ticker in date_prices:
                        historical_price = date_prices[stock.ticker]
                        stock_value = stock.quantity * historical_price
                        correct_value += stock_value
                
                if correct_value > 0:
                    old_value = snapshot.total_value
                    snapshot.total_value = correct_value
                    results['snapshots_updated'] += 1
                    logger.info(f"Updated snapshot {snapshot.user_id} {target_date}: ${old_value:.2f} → ${correct_value:.2f}")
        
        # Update S&P 500 market data if SPY was in this batch
        if "SPY" in batch_tickers:
            for target_date in target_dates:
                if "SPY" in historical_prices.get(target_date, {}):
                    spy_price = historical_prices[target_date]["SPY"]
                    # Convert SPY ETF price to S&P 500 index value (SPY × 10)
                    sp500_index_value = spy_price * 10
                    
                    existing_data = MarketData.query.filter_by(
                        ticker="SPY_SP500", 
                        date=target_date
                    ).first()
                    
                    if existing_data:
                        existing_data.close_price = sp500_index_value
                    else:
                        new_data = MarketData(
                            ticker="SPY_SP500",
                            date=target_date,
                            close_price=sp500_index_value,
                            volume=0
                        )
                        db.session.add(new_data)
                    
                    results['sp500_updated'] = True
                    logger.info(f"Updated S&P 500 {target_date}: ${sp500_index_value:.2f} (SPY ${spy_price:.2f} × 10)")
        
        db.session.commit()
        
        end_time = datetime.now()
        processing_time = (end_time - start_time).total_seconds()
        results['processing_time_seconds'] = round(processing_time, 2)
        
        return jsonify({
            'success': True,
            'message': f'Batch {batch_number} completed successfully',
            'results': results
        }), 200
        
    except Exception as e:
        logger.error(f"Error in batch historical price backfill: {str(e)}")
        import traceback
        return jsonify({
            'success': False,
            'error': str(e),
            'details': 'Check server logs'
        }), 500


@app.route('/api/cron/cleanup-intraday-data', methods=['POST', 'GET'])
def cleanup_intraday_data_cron():
    """Automated cron endpoint to clean up old intraday snapshots while preserving 4PM market close data"""
    try:
        auth_error = verify_cron_request()
        if auth_error:
            return auth_error
        
        from api.cleanup_intraday import cleanup_old_intraday_data
        
        # Run cleanup (keep 14 days of data)
        results = cleanup_old_intraday_data(days_to_keep=14)
        
        logger.info(f"Automated cleanup completed: {results['snapshots_deleted']} deleted, {results['market_close_preserved']} preserved")
        
        return jsonify({
            'success': True,
            'message': 'Intraday data cleanup completed',
            'results': results
        }), 200
        
    except Exception as e:
        logger.error(f"Automated cleanup error: {str(e)}")
        return jsonify({'error': f'Cleanup error: {str(e)}'}), 500

@app.route('/api/cron/refresh-daily-bars', methods=['GET', 'POST'])
def refresh_daily_bars_cron():
    """
    Populate the `daily_price_bar` cache with the most recent ~100 trading
    days of OHLCV bars for every ticker in the bot universe.

    Runs once per weekday after market close (vercel.json: 22:30 UTC = 6:30 PM ET).
    Uses AlphaVantage TIME_SERIES_DAILY concurrently, respecting the 150/min
    premium rate limit. With ~100 tickers this takes ~45s — fits within
    Vercel's 60s maxDuration.

    Trade waves then read from this cache instead of refetching 100 days of
    history on every wave (which was the root cause of the 9:45 AM 500s
    when yfinance was unreliable on Vercel serverless IPs).
    """
    try:
        auth_error = verify_cron_request()
        if auth_error:
            return auth_error

        from bot_data_hub import (
            get_all_tickers, fetch_av_daily_bars_concurrent, ALPHA_VANTAGE_KEY,
            flush_av_logs,
        )
        from models import db, DailyPriceBar
        from sqlalchemy.dialects.postgresql import insert as pg_insert

        if not ALPHA_VANTAGE_KEY:
            return jsonify({
                'success': False,
                'error': 'no_av_key',
                'message': 'ALPHA_VANTAGE_API_KEY env var is not set'
            }), 200  # 200 with diagnostics, NOT 500 — config issue surfaced cleanly

        # Two-minute split: each cron invocation handles 1/`of` of the universe
        # so the per-minute AV call burst stays well under the 150/min cap (138
        # calls in one minute was ~92% of the limit). The crons fire two minutes
        # apart (see vercel.json), each taking ~30s for ~69 tickers. `part`/`of`
        # default to 1/1 (whole universe) for manual / single-shot invocations.
        try:
            part = int(request.args.get('part', 1))
            of = int(request.args.get('of', 1))
        except (TypeError, ValueError):
            part, of = 1, 1
        of = max(of, 1)
        part = min(max(part, 1), of)

        all_tickers = sorted(get_all_tickers())
        # Strided slice keeps the parts balanced even when the count is odd.
        tickers = all_tickers[part - 1::of]
        logger.info(
            f"refresh-daily-bars: part {part}/{of} — fetching {len(tickers)} "
            f"of {len(all_tickers)} tickers from AlphaVantage"
        )
        started = datetime.utcnow()

        # Concurrent fetch from AV (respects 140 req/min effective rate).
        bars_by_ticker = fetch_av_daily_bars_concurrent(tickers, max_workers=4)
        fetched_ms = int((datetime.utcnow() - started).total_seconds() * 1000)

        # Upsert into daily_price_bar. Each ticker DF has up to 100 rows.
        upserted = 0
        failed_tickers = []
        for ticker, df in bars_by_ticker.items():
            try:
                rows_to_upsert = []
                for date_idx, row in df.iterrows():
                    rows_to_upsert.append({
                        'ticker': ticker,
                        'date': date_idx.date() if hasattr(date_idx, 'date') else date_idx,
                        'open': float(row['Open']),
                        'high': float(row['High']),
                        'low': float(row['Low']),
                        'close': float(row['Close']),
                        'volume': float(row['Volume']),
                        'source': 'av',
                        'fetched_at': datetime.utcnow(),
                    })
                if not rows_to_upsert:
                    continue
                # Postgres ON CONFLICT upsert (ticker+date is the unique key).
                stmt = pg_insert(DailyPriceBar.__table__).values(rows_to_upsert)
                stmt = stmt.on_conflict_do_update(
                    index_elements=['ticker', 'date'],
                    set_={
                        'open': stmt.excluded.open,
                        'high': stmt.excluded.high,
                        'low': stmt.excluded.low,
                        'close': stmt.excluded.close,
                        'volume': stmt.excluded.volume,
                        'source': stmt.excluded.source,
                        'fetched_at': stmt.excluded.fetched_at,
                    }
                )
                db.session.execute(stmt)
                upserted += len(rows_to_upsert)
            except Exception as e:
                logger.warning(f"refresh-daily-bars upsert failed for {ticker}: {e}")
                failed_tickers.append(ticker)

        db.session.commit()
        try:
            flush_av_logs()
        except Exception as flush_err:
            logger.warning(f"flush_av_logs failed (non-fatal): {flush_err}")

        finished = datetime.utcnow()
        elapsed_s = (finished - started).total_seconds()
        not_returned = [t for t in tickers if t not in bars_by_ticker]

        return jsonify({
            'success': True,
            'part': part,
            'of': of,
            'tickers_in_universe': len(all_tickers),
            'tickers_total': len(tickers),
            'tickers_fetched': len(bars_by_ticker),
            'tickers_missing_from_av': not_returned[:25],
            'tickers_missing_count': len(not_returned),
            'tickers_upsert_failed': failed_tickers,
            'rows_upserted': upserted,
            'fetch_ms': fetched_ms,
            'total_elapsed_s': round(elapsed_s, 1),
        })
    except Exception as e:
        logger.error(f"refresh-daily-bars cron error: {e}")
        import traceback
        return jsonify({
            'success': False,
            'error': str(e),
            'traceback': traceback.format_exc(),
        }), 500


@app.route('/api/cron/get-cached-daily-bars', methods=['GET'])
def get_cached_daily_bars_cron():
    """
    Return cached OHLCV bars from the `daily_price_bar` table.

    Used by `bot_agent.py` running on GitHub Actions, which has no DB access
    (Option B from the May 2026 design discussion: keep DB credentials out
    of CI). The bot wave fetches the cache via this HTTP endpoint instead
    of going to AV directly, avoiding 138 redundant TIME_SERIES_DAILY calls
    per wave.

    Auth: same `verify_cron_request()` that all other crons use
    (X-Cron-Secret header or Authorization: Bearer).

    Query params:
      - tickers (optional, comma-separated): default = full bot universe.
      - max_bars (optional, int, default 100): cap rows per ticker for
        response-size control. compute_indicators only needs ~26 bars min;
        100 is comfortable headroom for SMA-200 etc.
      - min_bars (optional, int, default 20): omit tickers with fewer rows
        than this (matches `_load_cached_daily_bars`'s default).

    Response shape:
      {
        "success": true,
        "fetched_at": "2026-05-20T12:34:56Z",
        "tickers_returned": 138,
        "tickers_requested": 138,
        "tickers_missing": [],
        "bars": {
          "AAPL": [
            ["2026-01-15", 297.26, 300.51, 296.35, 298.97, 42243561.0],
            ...
          ],
          ...
        }
      }
    Each row is [date_iso, open, high, low, close, volume]. Sorted by date
    ascending. Caller (bot_data_hub._load_cached_daily_bars) reconstructs a
    pandas DataFrame matching the existing in-process format.
    """
    try:
        auth_error = verify_cron_request()
        if auth_error:
            return auth_error

        from bot_data_hub import get_all_tickers
        from models import DailyPriceBar
        from collections import defaultdict

        # Parse params.
        tickers_param = request.args.get('tickers', '').strip()
        if tickers_param:
            tickers = [t.strip().upper() for t in tickers_param.split(',') if t.strip()]
        else:
            tickers = get_all_tickers()

        try:
            max_bars = int(request.args.get('max_bars', '100'))
        except ValueError:
            max_bars = 100
        try:
            min_bars = int(request.args.get('min_bars', '20'))
        except ValueError:
            min_bars = 20

        # Hard cap to keep response < ~5 MB even on a big query.
        max_bars = max(1, min(max_bars, 250))

        if not tickers:
            return jsonify({
                'success': False,
                'error': 'no_tickers',
                'message': 'No tickers requested and bot universe empty'
            }), 400

        # Pull all rows for requested tickers in one query, then group by ticker.
        # ORDER BY (ticker, date DESC) so we naturally take the most-recent rows
        # first; we'll reverse to date-ascending in the response so caller code
        # matches the existing pandas DataFrame ordering.
        rows = (
            DailyPriceBar.query
            .filter(DailyPriceBar.ticker.in_(tickers))
            .order_by(DailyPriceBar.ticker.asc(), DailyPriceBar.date.desc())
            .all()
        )

        by_ticker = defaultdict(list)
        for r in rows:
            recs = by_ticker[r.ticker]
            if len(recs) >= max_bars:
                continue  # already have enough most-recent bars for this ticker
            recs.append([
                r.date.isoformat(),
                float(r.open) if r.open is not None else float(r.close),
                float(r.high) if r.high is not None else float(r.close),
                float(r.low) if r.low is not None else float(r.close),
                float(r.close),
                float(r.volume) if r.volume is not None else 0.0,
            ])

        # Reverse each ticker's list to date-ascending and drop sparse tickers.
        bars = {}
        for ticker, recs in by_ticker.items():
            if len(recs) < min_bars:
                continue
            bars[ticker] = list(reversed(recs))

        missing = [t for t in tickers if t not in bars]

        return jsonify({
            'success': True,
            'fetched_at': datetime.utcnow().isoformat() + 'Z',
            'tickers_requested': len(tickers),
            'tickers_returned': len(bars),
            'tickers_missing_count': len(missing),
            'tickers_missing': missing[:25],
            'bars': bars,
        })
    except Exception as e:
        logger.error(f"get-cached-daily-bars error: {e}")
        import traceback
        return jsonify({
            'success': False,
            'error': str(e),
            'traceback': traceback.format_exc(),
        }), 500


@app.route('/api/cron/refresh-fundamentals', methods=['GET', 'POST'])
def refresh_fundamentals_cron():
    """
    Populate the `stock_fundamentals` cache from AlphaVantage OVERVIEW for the
    bot universe (Bot Layer B).

    OVERVIEW costs ONE AV call per ticker, so this is the expensive refresh. It
    runs WEEKLY (vercel.json) rather than per-wave because fundamentals (P/E,
    dividend yield, analyst target, beta) only move on quarterly earnings and
    periodic analyst revisions. ~130 tickers at ~140 calls/min paces to ~1 min,
    so `part`/`of` splitting (same as refresh-daily-bars) keeps each invocation
    well under Vercel's 60s maxDuration and the 150/min AV cap.

    Trade waves read from the resulting table via _load_fundamentals (direct DB
    in Flask, HTTP via /api/cron/get-fundamentals from GitHub Actions).
    """
    try:
        auth_error = verify_cron_request()
        if auth_error:
            return auth_error

        from bot_data_hub import (
            get_all_tickers, fetch_overviews_concurrent, ALPHA_VANTAGE_KEY,
            flush_av_logs,
        )
        from models import db, StockFundamentals
        from sqlalchemy.dialects.postgresql import insert as pg_insert

        if not ALPHA_VANTAGE_KEY:
            return jsonify({
                'success': False,
                'error': 'no_av_key',
                'message': 'ALPHA_VANTAGE_API_KEY env var is not set'
            }), 200

        # Universe split so each invocation's per-minute AV burst stays under cap.
        try:
            part = int(request.args.get('part', 1))
            of = int(request.args.get('of', 1))
        except (TypeError, ValueError):
            part, of = 1, 1
        of = max(of, 1)
        part = min(max(part, 1), of)

        all_tickers = sorted(get_all_tickers())
        tickers = all_tickers[part - 1::of]
        logger.info(
            f"refresh-fundamentals: part {part}/{of} — fetching {len(tickers)} "
            f"of {len(all_tickers)} tickers from AlphaVantage OVERVIEW"
        )
        started = datetime.utcnow()

        fundamentals = fetch_overviews_concurrent(tickers, max_workers=4)
        fetched_ms = int((datetime.utcnow() - started).total_seconds() * 1000)

        upserted = 0
        failed_tickers = []
        for ticker, f in fundamentals.items():
            try:
                row = dict(f)
                row['ticker'] = ticker
                row['fetched_at'] = datetime.utcnow()
                stmt = pg_insert(StockFundamentals.__table__).values([row])
                stmt = stmt.on_conflict_do_update(
                    index_elements=['ticker'],
                    set_={
                        'pe_ratio': stmt.excluded.pe_ratio,
                        'peg_ratio': stmt.excluded.peg_ratio,
                        'price_to_book': stmt.excluded.price_to_book,
                        'eps': stmt.excluded.eps,
                        'dividend_yield': stmt.excluded.dividend_yield,
                        'beta': stmt.excluded.beta,
                        'analyst_target_price': stmt.excluded.analyst_target_price,
                        'market_cap': stmt.excluded.market_cap,
                        'sector': stmt.excluded.sector,
                        'name': stmt.excluded.name,
                        'fetched_at': stmt.excluded.fetched_at,
                    }
                )
                db.session.execute(stmt)
                upserted += 1
            except Exception as e:
                logger.warning(f"refresh-fundamentals upsert failed for {ticker}: {e}")
                failed_tickers.append(ticker)

        db.session.commit()
        try:
            flush_av_logs()
        except Exception as flush_err:
            logger.warning(f"flush_av_logs failed (non-fatal): {flush_err}")

        elapsed_s = (datetime.utcnow() - started).total_seconds()
        not_returned = [t for t in tickers if t not in fundamentals]
        return jsonify({
            'success': True,
            'part': part,
            'of': of,
            'tickers_in_universe': len(all_tickers),
            'tickers_total': len(tickers),
            'tickers_fetched': len(fundamentals),
            'tickers_missing_from_av': not_returned[:25],
            'tickers_missing_count': len(not_returned),
            'tickers_upsert_failed': failed_tickers,
            'rows_upserted': upserted,
            'fetch_ms': fetched_ms,
            'total_elapsed_s': round(elapsed_s, 1),
        })
    except Exception as e:
        logger.error(f"refresh-fundamentals cron error: {e}")
        import traceback
        return jsonify({
            'success': False,
            'error': str(e),
            'traceback': traceback.format_exc(),
        }), 500


@app.route('/api/cron/get-fundamentals', methods=['GET'])
def get_fundamentals_cron():
    """
    Return cached fundamentals from the `stock_fundamentals` table.

    Used by `bot_agent.py` running on GitHub Actions (no DB access in CI). Mirrors
    /api/cron/get-cached-daily-bars. Auth: same verify_cron_request().

    Query params:
      - tickers (optional, comma-separated): default = full bot universe.

    Response: {success, fetched_at, tickers_returned, fundamentals: {ticker: {...}}}
    where each value matches the _load_fundamentals dict shape.
    """
    try:
        auth_error = verify_cron_request()
        if auth_error:
            return auth_error

        from bot_data_hub import get_all_tickers
        from models import StockFundamentals

        tickers_param = request.args.get('tickers', '').strip()
        if tickers_param:
            tickers = [t.strip().upper() for t in tickers_param.split(',') if t.strip()]
        else:
            tickers = get_all_tickers()

        if not tickers:
            return jsonify({'success': False, 'error': 'no_tickers'}), 400

        rows = StockFundamentals.query.filter(
            StockFundamentals.ticker.in_(tickers)
        ).all()

        fundamentals = {}
        for r in rows:
            fundamentals[r.ticker] = {
                'pe_ratio': r.pe_ratio,
                'peg_ratio': r.peg_ratio,
                'price_to_book': r.price_to_book,
                'eps': r.eps,
                'dividend_yield': r.dividend_yield,
                'beta': r.beta,
                'analyst_target_price': r.analyst_target_price,
                'market_cap': r.market_cap,
                'sector': r.sector,
                'name': r.name,
            }

        return jsonify({
            'success': True,
            'fetched_at': datetime.utcnow().isoformat() + 'Z',
            'tickers_requested': len(tickers),
            'tickers_returned': len(fundamentals),
            'fundamentals': fundamentals,
        })
    except Exception as e:
        logger.error(f"get-fundamentals error: {e}")
        import traceback
        return jsonify({
            'success': False,
            'error': str(e),
            'traceback': traceback.format_exc(),
        }), 500


@app.route('/api/cron/bot-trade-wave', methods=['GET', 'POST'])
def bot_trade_wave_cron():
    """
    Vercel cron wrapper for bot trading waves.
    Determines which wave to run based on current ET time:
        Wave 1: 9:30-10:29 AM ET  (market open traders)
        Wave 2: 10:30-12:59 PM ET (mid-morning traders)
        Wave 3: 1:00-2:59 PM ET   (afternoon traders)
        Wave 4: 3:00-4:00 PM ET   (close traders)
    """
    try:
        auth_error = verify_cron_request()
        if auth_error:
            return auth_error
        
        from zoneinfo import ZoneInfo
        now_et = datetime.now(ZoneInfo('America/New_York'))
        hour, minute = now_et.hour, now_et.minute
        
        # Determine wave from current ET time
        if hour == 9 and minute >= 30 or hour == 10 and minute < 30:
            wave = 1
        elif (hour == 10 and minute >= 30) or hour == 11 or hour == 12:
            wave = 2
        elif hour == 13 or hour == 14:
            wave = 3
        elif hour == 15 or (hour == 16 and minute == 0):
            wave = 4
        else:
            return jsonify({
                'success': True,
                'message': f'Outside market hours ({now_et.strftime("%I:%M %p ET")}), skipping',
                'trades': 0
            })
        
        logger.info(f"🤖 Bot trade wave {wave} triggered at {now_et.strftime('%I:%M %p ET')}")
        
        from mobile_api import _execute_bot_trade_wave
        result = _execute_bot_trade_wave(wave)

        # Status taxonomy:
        #   - success          : trades executed, no errors
        #   - success+errors   : trades executed but some bots/data failed (partial)
        #   - no_data          : core market data unavailable (soft-fail)
        #   - traceback        : uncaught crash (hard-fail)
        #
        # We return 200 for soft-fails so the Vercel cron UI doesn't light up
        # red on transient data-source hiccups. The BotWaveLog row + the
        # response body's `error` / `error_detail` / `data_quality` fields
        # carry the diagnostics. Only true crashes (traceback present) yield
        # 500 — those genuinely need human attention.
        if result.get('traceback'):
            return jsonify(result), 500
        return jsonify(result), 200
    
    except Exception as e:
        logger.error(f"Bot trade wave cron error: {e}")
        import traceback
        return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500


@app.route('/api/cron/purge-deleted-accounts', methods=['POST', 'GET'])
def purge_deleted_accounts_cron():
    """Purge accounts soft-deleted more than the 30-day grace period ago.

    DRY-RUN by default — reports what WOULD be purged. Pass ?commit=true to
    actually write. Scheduled nightly (see vercel.json).

    Mechanism: irreversibly ANONYMIZE the account shell (scrub all PII, disable
    login) and DELETE the user's content (holdings, trades, snapshots, device
    tokens, push logs, poll votes, subscriptions). We deliberately anonymize the
    `user` row instead of hard-deleting it so IRS-required tax/financial records
    (TaxpayerProfile, XeroPayoutRecord, InAppPurchase) stay referentially intact
    for the mandated retention period. Once anonymized, the data no longer
    identifies the person, which satisfies erasure obligations.
    """
    # Allow EITHER the scheduled cron (secret) OR a logged-in admin hitting this
    # URL in a browser — so it can be triggered manually without the cron secret.
    auth_error = verify_cron_request()
    if auth_error and not (current_user.is_authenticated and getattr(current_user, 'is_admin', False)):
        return auth_error

    from datetime import timedelta
    from models import (db, User, Stock, Transaction, PortfolioSnapshot,
                        DeviceToken, PushNotificationLog, MobileSubscription,
                        Subscription, FeaturePollVote)

    GRACE_DAYS = 30  # must match the deletion endpoints
    commit = str(request.args.get('commit', '')).lower() == 'true'
    cutoff = datetime.utcnow() - timedelta(days=GRACE_DAYS)

    candidates = User.query.filter(
        User.deleted_at.isnot(None),
        User.deleted_at < cutoff,
        ~User.email.like('deleted+%@deleted.invalid'),  # skip already-anonymized
    ).all()

    report = {'dry_run': not commit, 'grace_days': GRACE_DAYS,
              'candidate_count': len(candidates), 'processed': []}

    for u in candidates:
        uid = u.id
        if u.is_company_owned:
            report['processed'].append({'user_id': uid, 'action': 'skipped_company_owned'})
            continue
        if not commit:
            report['processed'].append({'user_id': uid, 'action': 'would_anonymize',
                                        'deleted_at': u.deleted_at.isoformat()})
            continue
        try:
            Stock.query.filter_by(user_id=uid).delete(synchronize_session=False)
            Transaction.query.filter_by(user_id=uid).delete(synchronize_session=False)
            PortfolioSnapshot.query.filter_by(user_id=uid).delete(synchronize_session=False)
            DeviceToken.query.filter_by(user_id=uid).delete(synchronize_session=False)
            PushNotificationLog.query.filter(
                (PushNotificationLog.user_id == uid) |
                (PushNotificationLog.portfolio_owner_id == uid)
            ).delete(synchronize_session=False)
            FeaturePollVote.query.filter_by(user_id=uid).delete(synchronize_session=False)
            MobileSubscription.query.filter(
                (MobileSubscription.subscriber_id == uid) |
                (MobileSubscription.subscribed_to_id == uid)
            ).delete(synchronize_session=False)
            Subscription.query.filter(
                (Subscription.subscriber_id == uid) |
                (Subscription.subscribed_to_id == uid)
            ).delete(synchronize_session=False)

            # Irreversibly anonymize the shell (PII erased). Tax/financial
            # records are intentionally retained for the IRS-mandated period.
            u.email = f"deleted+{uid}@deleted.invalid"
            u.username = f"deleted_user_{uid}"
            u.display_name = None
            u.password_hash = None
            u.oauth_provider = None
            u.oauth_id = None
            u.phone_number = None
            u.portfolio_slug = None
            u.leaderboard_eligible = False
            u.extra_data = {}
            db.session.commit()
            report['processed'].append({'user_id': uid, 'action': 'anonymized'})
        except Exception as e:
            db.session.rollback()
            logger.error(f"purge-deleted-accounts: failed for user {uid}: {e}")
            report['processed'].append({'user_id': uid, 'action': f'error: {e}'})

    return jsonify(report)


@app.route('/api/cron/auto-create-bots', methods=['POST', 'GET'])
def auto_create_bots_cron():
    """Daily cron endpoint to auto-create bot accounts per admin settings."""
    try:
        auth_error = verify_cron_request()
        if auth_error:
            return auth_error
        
        # Import and call the auto-create logic from mobile_api
        from mobile_api import _get_auto_create_settings, _save_auto_create_settings
        from mobile_api import _seed_bot_portfolio, _gift_bot_subscribers, _generate_portfolio_slug
        from models import db, User
        
        settings = _get_auto_create_settings()
        
        if not settings.get('enabled'):
            return jsonify({'success': True, 'message': 'Auto-creation is disabled', 'created': 0})
        
        count = settings.get('daily_count', 0)
        if count <= 0:
            return jsonify({'success': True, 'message': 'daily_count is 0', 'created': 0})
        
        try:
            from bot_personas import generate_bot_batch
            from bot_strategies import STRATEGY_TEMPLATES
        except ImportError as ie:
            logger.error(f"Bot modules not available for auto-create: {ie}")
            return jsonify({'error': 'bot_modules_unavailable', 'detail': str(ie)}), 500
        
        strategy = settings.get('strategy')
        industry = settings.get('industry')
        if strategy and strategy not in STRATEGY_TEMPLATES:
            strategy = None
        
        personas = generate_bot_batch(count, industry=industry, strategy=strategy)
        created = []
        
        for persona in personas:
            username = persona['username']
            email = persona['email']
            ind = persona['industry']
            strat = persona['strategy_name']
            profile = persona['strategy_profile']
            sub_count = persona.get('subscriber_count', 0)
            
            try:
                existing = User.query.filter(
                    (User.username == username) | (User.email == email)
                ).first()
                if existing:
                    import random as _rnd
                    username = username + str(_rnd.randint(100, 999))
                    email = f"{username.replace('-', '.').replace('_', '.')}@apestogether.ai"
                
                user = User(
                    username=username, email=email,
                    portfolio_slug=_generate_portfolio_slug(),
                    role='agent', created_by='system', subscription_price=9.00,
                    extra_data={
                        'industry': ind, 'bot_active': True,
                        'bot_created_at': datetime.utcnow().isoformat(),
                        'trading_style': strat, 'strategy_profile': profile,
                    }
                )
                db.session.add(user)
                db.session.flush()
                
                stock_count = 0
                attention = profile.get('attention_universe', [])
                if attention:
                    stock_count = _seed_bot_portfolio(user.id, profile, attention)
                
                gifted = _gift_bot_subscribers(user.id, sub_count) if sub_count > 0 else 0
                
                created.append({
                    'user_id': user.id, 'username': username,
                    'strategy': strat, 'industry': ind,
                    'stocks': stock_count, 'subs': gifted,
                })
            except Exception as e:
                logger.error(f"Auto-create bot error for {username}: {e}")
        
        db.session.commit()
        
        # Update last_run timestamp
        _save_auto_create_settings({
            **settings,
            'last_run': datetime.utcnow().isoformat(),
            'last_created': len(created),
        })
        
        logger.info(f"Auto-create bots cron: created {len(created)}/{count} bots")
        return jsonify({
            'success': True,
            'created': len(created),
            'requested': count,
            'bots': created,
        })
        
    except Exception as e:
        logger.error(f"Auto-create bots cron error: {e}")
        import traceback
        return jsonify({'error': str(e)}), 500


@app.route('/api/cron/update-leaderboard', methods=['POST', 'GET'])
def update_leaderboard_cron():
    """Automated cron endpoint to update leaderboard cache - legacy endpoint for backward compatibility"""
    try:
        auth_error = verify_cron_request()
        if auth_error:
            return auth_error
        
        from leaderboard_utils import update_leaderboard_cache
        
        # Update leaderboard cache (all periods)
        updated_count = update_leaderboard_cache()
        db.session.commit()  # Commit the cache updates
        
        logger.info(f"Automated leaderboard update completed: {updated_count} entries updated")
        
        return jsonify({
            'success': True,
            'message': 'Leaderboard cache updated',
            'entries_updated': updated_count
        }), 200
        
    except Exception as e:
        logger.error(f"Automated leaderboard update error: {str(e)}")
        db.session.rollback()  # Rollback on error
        return jsonify({'error': f'Leaderboard update error: {str(e)}'}), 500

@app.route('/api/cron/update-leaderboard-chunk', methods=['POST', 'GET'])
def update_leaderboard_chunk_cron():
    """Chunked cron endpoint to update specific leaderboard periods for better reliability"""
    try:
        auth_error = verify_cron_request()
        if auth_error:
            return auth_error
        
        # Get periods from query parameter
        periods_param = request.args.get('periods', '')
        if not periods_param:
            return jsonify({'error': 'periods parameter required (e.g., ?periods=7D,1D,5D)'}), 400
        
        periods = [p.strip() for p in periods_param.split(',') if p.strip()]
        if not periods:
            return jsonify({'error': 'No valid periods provided'}), 400
        
        # Validate periods
        valid_periods = ['1D', '5D', '7D', '3M', 'YTD', '1Y', '5Y', 'MAX']
        invalid_periods = [p for p in periods if p not in valid_periods]
        if invalid_periods:
            return jsonify({'error': f'Invalid periods: {invalid_periods}. Valid: {valid_periods}'}), 400
        
        from leaderboard_utils import update_leaderboard_cache
        
        # Update leaderboard cache for specified periods only
        updated_count = update_leaderboard_cache(periods=periods)
        
        logger.info(f"Automated leaderboard chunk update completed: {updated_count} entries updated for periods {periods}")
        
        return jsonify({
            'success': True,
            'message': f'Leaderboard cache updated for periods: {", ".join(periods)}',
            'periods_processed': periods,
            'entries_updated': updated_count
        }), 200
        
    except Exception as e:
        logger.error(f"Automated leaderboard chunk update error: {str(e)}")
        return jsonify({'error': f'Leaderboard chunk update error: {str(e)}'}), 500

@app.route('/admin/market-close-status')
@admin_required
def admin_market_close_status():
    """Monitor the status of market close pipeline processes"""
    try:
        from datetime import datetime, date, timedelta
        from models import db, PortfolioSnapshot, LeaderboardCache, UserPortfolioChartCache
        import json
        
        today = date.today()
        yesterday = today - timedelta(days=1)
        
        # Check portfolio snapshots
        snapshots_today = PortfolioSnapshot.query.filter_by(date=today).count()
        snapshots_yesterday = PortfolioSnapshot.query.filter_by(date=yesterday).count()
        
        # Check leaderboard cache
        leaderboard_entries = LeaderboardCache.query.count()
        recent_leaderboard = LeaderboardCache.query.filter(
            LeaderboardCache.generated_at >= datetime.now() - timedelta(hours=24)
        ).count()
        
        # Check chart cache
        chart_entries = UserPortfolioChartCache.query.count()
        recent_charts = UserPortfolioChartCache.query.filter(
            UserPortfolioChartCache.generated_at >= datetime.now() - timedelta(hours=24)
        ).count()
        
        # Check GitHub Actions workflow status (last run)
        workflow_status = "unknown"
        try:
            # This would require GitHub API integration, for now just check recent updates
            if recent_leaderboard > 0:
                workflow_status = "success"
            elif datetime.now().hour >= 21:  # After 9 PM UTC (5 PM ET)
                workflow_status = "may_have_failed"
            else:
                workflow_status = "not_yet_run_today"
        except Exception:
            workflow_status = "unknown"
        
        # Determine overall status
        pipeline_health = "healthy"
        issues = []
        
        if snapshots_today == 0:
            pipeline_health = "warning"
            issues.append("No portfolio snapshots created today")
        
        if recent_leaderboard == 0:
            pipeline_health = "warning" 
            issues.append("No recent leaderboard updates (last 24h)")
        
        if recent_charts == 0:
            pipeline_health = "warning"
            issues.append("No recent chart generation (last 24h)")
        
        return jsonify({
            "success": True,
            "pipeline_health": pipeline_health,
            "timestamp": datetime.now().isoformat(),
            "daily_snapshots": {
                "today": snapshots_today,
                "yesterday": snapshots_yesterday,
                "status": "✅ Good" if snapshots_today > 0 else "⚠️ Missing"
            },
            "leaderboard_cache": {
                "total_entries": leaderboard_entries,
                "recent_updates": recent_leaderboard,
                "status": "✅ Good" if recent_leaderboard > 0 else "⚠️ Stale"
            },
            "chart_cache": {
                "total_entries": chart_entries,
                "recent_generation": recent_charts,
                "status": "✅ Good" if recent_charts > 0 else "⚠️ Stale"
            },
            "github_workflow": {
                "status": workflow_status,
                "next_run": "5:00 PM ET (9:00 PM UTC) on weekdays"
            },
            "issues": issues,
            "recommendations": [
                "Check GitHub Actions workflow logs if issues persist",
                "Verify AlphaVantage API key and rate limits",
                "Monitor database performance during market close"
            ] if issues else []
        })
        
    except Exception as e:
        logger.error(f"Market close status check error: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }), 500


@app.route('/api/portfolio/chart/<username>/<period>')
def get_public_portfolio_chart(username, period):
    """Get portfolio chart data for public portfolio views (blurred/unblurred)"""
    try:
        from models import User, UserPortfolioChartCache
        from sqlalchemy import text
        import json
        
        # Find user by username
        user = User.query.filter_by(username=username).first()
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        period_upper = period.upper()
        
        # CRITICAL FIX: Query PRIMARY to bypass Vercel Postgres replica lag
        # Regular ORM queries hit replicas with 50-500ms stale data
        chart_cache_data = None
        with db.engine.connect() as primary_conn:
            result = primary_conn.execute(text("""
                SELECT chart_data
                FROM user_portfolio_chart_cache
                WHERE user_id = :user_id AND period = :period
            """), {'user_id': user.id, 'period': period_upper})
            row = result.fetchone()
            if row:
                chart_cache_data = row[0]
        
        if chart_cache_data:
            try:
                # Return Chart.js format directly for public portfolio pages
                cached_data = json.loads(chart_cache_data)
                cached_data['data_source'] = 'pre_rendered_cache_PRIMARY'
                cached_data['username'] = username
                
                logger.info(f"Using pre-rendered chart data (PRIMARY) for public view: {username}, period {period_upper}")
                return jsonify(cached_data)
                
            except Exception as e:
                logger.warning(f"Failed to parse pre-rendered chart data for {username}: {e}")
        
        # Fallback: Generate chart on-demand for non-leaderboard users
        from portfolio_performance import PortfolioPerformanceCalculator
        calculator = PortfolioPerformanceCalculator()
        
        logger.info(f"Generating chart on-demand for public view: {username}, period {period_upper}")
        performance_data = calculator.get_performance_data(user.id, period_upper)
        
        # Convert to Chart.js format for consistency
        if 'chart_data' in performance_data:
            chart_js_format = {
                'labels': [item['date'] for item in performance_data['chart_data']],
                'datasets': [
                    {
                        'label': f'{username} Portfolio',
                        'data': [item['portfolio'] for item in performance_data['chart_data']],
                        'borderColor': 'rgb(75, 192, 192)',
                        'backgroundColor': 'rgba(75, 192, 192, 0.2)',
                        'tension': 0.1
                    },
                    {
                        'label': 'S&P 500',
                        'data': [item['sp500'] for item in performance_data['chart_data']],
                        'borderColor': 'rgb(255, 99, 132)',
                        'backgroundColor': 'rgba(255, 99, 132, 0.2)',
                        'tension': 0.1
                    }
                ],
                'period': period,
                'username': username,
                'data_source': 'live_calculation'
            }
            return jsonify(chart_js_format)
        
        return jsonify({'error': 'No chart data available'}), 404
        
    except Exception as e:
        logger.error(f"Public portfolio chart error for {username}: {str(e)}")
        return jsonify({'error': 'Chart data unavailable'}), 500


@app.route('/api/portfolio/intraday/<period>', methods=['GET'])
@login_required
def portfolio_performance_intraday(period):
    """Get intraday portfolio performance data using actual intraday snapshots"""
    logger.info(f"INTRADAY ROUTE HIT: /api/portfolio/intraday/{period}")
    logger.info(f"Request method: {request.method}")
    logger.info(f"Request headers: {dict(request.headers)}")
    try:
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': 'User not authenticated'}), 401
        from datetime import datetime, date, timedelta
        from models import PortfolioSnapshotIntraday, MarketData
        from sqlalchemy import func, cast, Date
        
        # Calculate date range based on period - use last market day for weekends
        # CRITICAL: Use Eastern Time, not UTC!
        current_time_et = get_market_time()
        today = current_time_et.date()
        
        # Use last market day for weekend handling (in ET)
        if today.weekday() == 5:  # Saturday
            market_day = today - timedelta(days=1)  # Friday
        elif today.weekday() == 6:  # Sunday
            market_day = today - timedelta(days=2)  # Friday
        else:
            market_day = today  # Monday-Friday
            
        logger.info(f"Date calculation (ET): current_time={current_time_et}, today={today}, market_day={market_day}")
        logger.info(f"Timezone: America/New_York")
        
        if period == '1D':
            start_date = market_day
            end_date = market_day
        elif period == '5D':
            # For 5D, we want EXACTLY the last 5 business days including today
            # Count backwards to find the 5th business day
            business_days_found = 0
            current_date = market_day
            
            while business_days_found < 5:
                if current_date.weekday() < 5:  # Monday=0, Friday=4
                    business_days_found += 1
                    if business_days_found == 5:
                        start_date = current_date
                        break
                current_date -= timedelta(days=1)
            
            end_date = market_day
            logger.info(f"5D Date Range: {start_date} to {end_date} (exactly 5 business days)")
        else:
            # Fallback to regular performance API for other periods
            from portfolio_performance import PortfolioPerformanceCalculator
            calculator = PortfolioPerformanceCalculator()
            return jsonify(calculator.get_performance_data(user_id, period)), 200
        
        # Get intraday snapshots for the user in the date range (using ET date extraction)
        # CRITICAL: Convert to ET timezone BEFORE casting to date to avoid UTC session timezone issues
        # FIX (Grok-validated): For 1D, use exact date match to prevent including previous day's data
        if period == '1D':
            # Use exact date match for single day - avoids edge cases with range queries
            # at_time_zone() is more explicit than func.timezone() and avoids cast issues
            snapshots = PortfolioSnapshotIntraday.query.filter(
                PortfolioSnapshotIntraday.user_id == user_id,
                func.date(func.timezone('America/New_York', PortfolioSnapshotIntraday.timestamp)) == market_day
            ).order_by(PortfolioSnapshotIntraday.timestamp).all()
            logger.info(f"1D Chart: Querying for exact date {market_day} (ET)")
        else:
            # For 5D and other periods, use date range
            snapshots = PortfolioSnapshotIntraday.query.filter(
                PortfolioSnapshotIntraday.user_id == user_id,
                cast(func.timezone('America/New_York', PortfolioSnapshotIntraday.timestamp), Date) >= start_date,
                cast(func.timezone('America/New_York', PortfolioSnapshotIntraday.timestamp), Date) <= end_date
            ).order_by(PortfolioSnapshotIntraday.timestamp).all()
            logger.info(f"{period} Chart: Querying date range {start_date} to {end_date} (ET)")
        
        # Debug logging for 5D chart issue
        logger.info(f"5D Chart Debug - Period: {period}, User: {user_id}")
        logger.info(f"Date range: {start_date} to {end_date}")
        logger.info(f"Found {len(snapshots)} snapshots")
        
        # Check what today's date looks like in the database (using ET date)
        today_snapshots = PortfolioSnapshotIntraday.query.filter(
            PortfolioSnapshotIntraday.user_id == user_id,
            cast(func.timezone('America/New_York', PortfolioSnapshotIntraday.timestamp), Date) == today
        ).count()
        logger.info(f"Snapshots specifically for today ({today} ET): {today_snapshots}")
        
        # Also check yesterday for comparison
        yesterday = today - timedelta(days=1)
        yesterday_snapshots = PortfolioSnapshotIntraday.query.filter(
            PortfolioSnapshotIntraday.user_id == user_id,
            cast(func.timezone('America/New_York', PortfolioSnapshotIntraday.timestamp), Date) == yesterday
        ).count()
        logger.info(f"Snapshots for yesterday ({yesterday} ET): {yesterday_snapshots}")
        
        if snapshots:
            logger.info(f"First snapshot: {snapshots[0].timestamp}")
            logger.info(f"Last snapshot: {snapshots[-1].timestamp}")
            # Group by date to see distribution
            from collections import defaultdict
            by_date = defaultdict(int)
            for snap in snapshots:
                by_date[snap.timestamp.date()] += 1
            logger.info(f"Snapshots by date: {dict(by_date)}")
            
            # Check if we have any snapshots from today
            today_in_results = any(snap.timestamp.date() == today for snap in snapshots)
            logger.info(f"Today's data in results: {today_in_results}")
        
        if not snapshots:
            return jsonify({
                'error': 'No intraday data available for this period',
                'period': period,
                'start_date': start_date.isoformat(),
                'end_date': end_date.isoformat(),
                'debug_info': f'Checked for user_id={user_id} between {start_date} and {end_date}'
            }), 404
        
        # Get S&P 500 data for the same period
        if period in ['1D', '5D']:
            # Use intraday S&P 500 data for short periods
            spy_data = MarketData.query.filter(
                MarketData.ticker == 'SPY_INTRADAY',
                MarketData.date >= start_date,
                MarketData.date <= end_date,
                MarketData.timestamp.isnot(None)
            ).order_by(MarketData.timestamp).all()
        else:
            # Use daily S&P 500 data for longer periods
            spy_data = MarketData.query.filter(
                MarketData.ticker == 'SPY_SP500',
                MarketData.date >= start_date,
                MarketData.date <= end_date
            ).order_by(MarketData.date).all()
        
        # Build chart data
        chart_data = []
        first_portfolio_value = snapshots[0].total_value if snapshots else 0
        first_spy_value = spy_data[0].close_price if spy_data else 0
        
        for snapshot in snapshots:
            # Find corresponding S&P 500 value
            spy_value = first_spy_value
            
            if period in ['1D', '5D']:
                # For intraday data, match by timestamp
                for spy_point in spy_data:
                    if spy_point.timestamp <= snapshot.timestamp:
                        spy_value = spy_point.close_price
                    else:
                        break
            else:
                # For daily data, match by date
                snapshot_date = snapshot.timestamp.date()
                for spy_point in spy_data:
                    if spy_point.date <= snapshot_date:
                        spy_value = spy_point.close_price
                    else:
                        break
            
            # Calculate returns
            portfolio_return = ((snapshot.total_value - first_portfolio_value) / first_portfolio_value * 100) if first_portfolio_value > 0 else 0
            sp500_return = ((spy_value - first_spy_value) / first_spy_value * 100) if first_spy_value > 0 else 0
            
            # Format date label based on period
            # CRITICAL FIX: Convert timestamp to ET before sending to frontend
            # PostgreSQL returns timestamps in UTC; convert to ET to display correct market hours
            if period == '1D':
                # For 1D charts, use date + time format (e.g., "Oct 18 9:30 AM")
                et_timestamp = snapshot.timestamp.astimezone(MARKET_TZ)
                date_label = et_timestamp.strftime('%b %d %I:%M %p')
            elif period == '5D':
                # For 5D charts, use date-only format since we now show only one snapshot per day
                et_timestamp = snapshot.timestamp.astimezone(MARKET_TZ)
                date_label = et_timestamp.strftime('%b %d')
            else:
                # For longer periods, use short date format
                date_label = snapshot.timestamp.date().strftime('%b %d')
            
            chart_data.append({
                'date': date_label,
                'portfolio': round(portfolio_return, 2),
                'sp500': round(sp500_return, 2)
            })
        
        # Calculate overall returns
        final_portfolio_value = snapshots[-1].total_value if snapshots else 0
        final_spy_value = spy_data[-1].close_price if spy_data else first_spy_value
        
        portfolio_return = ((final_portfolio_value - first_portfolio_value) / first_portfolio_value * 100) if first_portfolio_value > 0 else 0
        sp500_return = ((final_spy_value - first_spy_value) / first_spy_value * 100) if first_spy_value > 0 else 0
        
        # Debug the final chart data
        logger.info(f"Final chart data: {len(chart_data)} points")
        if chart_data:
            logger.info(f"First chart point: {chart_data[0]}")
            logger.info(f"Last chart point: {chart_data[-1]}")
        
        return jsonify({
            'portfolio_return': round(portfolio_return, 2),
            'sp500_return': round(sp500_return, 2),
            'chart_data': chart_data,
            'period': period,
            'start_date': start_date.isoformat(),
            'end_date': end_date.isoformat(),
            'data_points': len(chart_data),
            'debug_info': {
                'snapshots_found': len(snapshots),
                'spy_data_found': len(spy_data),
                'first_portfolio_value': first_portfolio_value,
                'first_spy_value': first_spy_value,
                'sample_timestamps': [s.timestamp.isoformat() for s in snapshots[:3]]
            }
        }), 200
    
    except Exception as e:
        logger.error(f"Error in performance-intraday API: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500


@app.route('/api/cron/collect-intraday-data', methods=['POST', 'GET'])
def collect_intraday_data():
    """Collect intraday data for all users (called by GitHub Actions)"""
    try:
        auth_error = verify_cron_request()
        if auth_error:
            return auth_error
        
        from models import User, PortfolioSnapshotIntraday
        from portfolio_performance import PortfolioPerformanceCalculator
        import time
        
        # Use eastern Time for all market operations
        current_time = get_market_time()
        today_et = current_time.date()
        
        # Allow manual trigger with ?force=1 (skips time checks)
        force = request.args.get('force', '0') == '1'
        
        if not force:
            # Don't collect data on weekends
            if current_time.weekday() >= 5:  # Saturday = 5, Sunday = 6
                logger.info(f"Weekend detected ({current_time.strftime('%A')}) - skipping intraday data collection")
                return jsonify({
                    'success': True,
                    'message': f'Skipped collection - market closed on {current_time.strftime("%A")}',
                    'timestamp': current_time.isoformat(),
                    'timezone': 'America/New_York',
                    'weekend': True
                })
            
            # Don't collect data on market holidays (NYSE/NASDAQ closed).
            # Mirrors the guard in market_close_cron so intraday charts don't
            # accrue flat phantom rows on holidays (e.g. Memorial Day).
            if is_market_holiday(today_et):
                logger.info(f"Market holiday {today_et} - skipping intraday data collection")
                return jsonify({
                    'success': True,
                    'message': f'Skipped collection - market holiday on {today_et}',
                    'timestamp': current_time.isoformat(),
                    'timezone': 'America/New_York',
                    'holiday': True
                })
            
            # DST-aware check: Only collect at valid 15-minute intervals during market hours (9:30 AM - 4:00 PM ET)
            hour = current_time.hour
            minute = current_time.minute
            
            valid_intervals = set()
            for h in range(9, 17):  # 9 AM to 4 PM
                for m in [0, 15, 30, 45]:
                    if h == 9 and m < 30:
                        continue
                    if h == 16 and m > 0:
                        continue
                    valid_intervals.add((h, m))
            
            # Allow +/- 2 minutes tolerance for cron timing variance
            is_valid_time = False
            for valid_hour, valid_minute in valid_intervals:
                if hour == valid_hour and abs(minute - valid_minute) <= 2:
                    is_valid_time = True
                    break
            
            if not is_valid_time:
                logger.info(f"Cron triggered at {current_time.strftime('%I:%M %p ET')} - outside market hours, skipping")
                return jsonify({
                    'success': True,
                    'message': f'Skipped collection - outside market hours ({current_time.strftime("%I:%M %p ET")})',
                    'timestamp': current_time.isoformat(),
                    'timezone': 'America/New_York',
                    'skipped': True
                })
        
        start_time = time.time()
        calculator = PortfolioPerformanceCalculator()
        results = {
            'timestamp': current_time.isoformat(),
            'current_time_et': current_time.strftime('%Y-%m-%d %H:%M:%S ET'),
            'market_status': 'CLOSED' if current_time.hour >= 16 else 'OPEN',
            'spy_data_collected': False,
            'users_processed': 0,
            'snapshots_created': 0,
            'charts_generated': 0,
            'errors': [],
            'execution_time_seconds': 0,
            'detailed_logging': {
                'unique_stocks_analysis': {},
                'api_call_tracking': {},
                'cache_efficiency': {},
                'portfolio_calculations': {}
            }
        }
        
        # Step 1: Get all users and collect unique tickers (for batch API call)
        users = User.query.all()
        
        # Collect all unique tickers across all users
        from models import Stock
        unique_tickers = set()
        unique_tickers.add('SPY')  # Always include SPY for S&P 500 benchmark
        
        for user in users:
            user_stocks = Stock.query.filter_by(user_id=user.id).all()
            for stock in user_stocks:
                if stock.quantity > 0:
                    unique_tickers.add(stock.ticker.upper())
        
        logger.info(f"📊 Batch API: Fetching {len(unique_tickers)} unique tickers for {len(users)} users")
        
        # Step 2: BATCH API CALL - Fetch all prices in ONE call (12-25x more efficient!)
        try:
            batch_prices = calculator.get_batch_stock_data(list(unique_tickers))
            
            # Log results
            if batch_prices:
                logger.info(f"✅ Batch API Success: Retrieved {len(batch_prices)} prices in 1-2 calls")
                results['api_calls_made'] = 1 if len(unique_tickers) <= 256 else (len(unique_tickers) // 256) + 1
                results['tickers_fetched'] = len(batch_prices)
                
                # Store SPY data for S&P 500 tracking
                if 'SPY' in batch_prices:
                    spy_price = batch_prices['SPY']
                    sp500_value = spy_price * 10
                    
                    from models import MarketData
                    market_data = MarketData(
                        ticker='SPY_INTRADAY',
                        date=today_et,
                        timestamp=current_time,
                        close_price=sp500_value
                    )
                    db.session.add(market_data)
                    results['spy_data_collected'] = True
                    logger.info(f"SPY: ${spy_price} (S&P 500: ${sp500_value})")
            else:
                results['errors'].append("Batch API returned no prices")
                logger.error("❌ Batch API failed - no prices returned")
                
                # FALLBACK: Fetch each unique ticker individually (once), populating the cache
                # This avoids redundant per-user API calls in calculate_portfolio_value_with_cash
                logger.info(f"🔄 Fetching {len(unique_tickers)} tickers individually...")
                fallback_fetched = 0
                for ticker in unique_tickers:
                    try:
                        data = calculator.get_stock_data(ticker)
                        if data and data.get('price'):
                            batch_prices[ticker] = data['price']
                            fallback_fetched += 1
                    except Exception:
                        pass
                logger.info(f"✅ Individual fallback: {fallback_fetched}/{len(unique_tickers)} tickers fetched")
                results['fallback_fetched'] = fallback_fetched
                results['spy_fallback_used'] = True
                
                # Store SPY data
                if 'SPY' in batch_prices:
                    spy_price = batch_prices['SPY']
                    sp500_value = spy_price * 10
                    from models import MarketData
                    market_data = MarketData(
                        ticker='SPY_INTRADAY',
                        date=today_et,
                        timestamp=current_time,
                        close_price=sp500_value
                    )
                    db.session.add(market_data)
                    results['spy_data_collected'] = True
        
        except Exception as e:
            error_msg = f"Batch API error: {str(e)}"
            results['errors'].append(error_msg)
            logger.error(error_msg)
            
            # FALLBACK: Fetch tickers individually on exception too
            logger.info(f"🔄 Fetching {len(unique_tickers)} tickers individually after exception...")
            fallback_fetched = 0
            for ticker in unique_tickers:
                try:
                    data = calculator.get_stock_data(ticker)
                    if data and data.get('price'):
                        batch_prices[ticker] = data['price']
                        fallback_fetched += 1
                except Exception:
                    pass
            results['fallback_fetched'] = fallback_fetched
            results['spy_fallback_used'] = True
            
            if 'SPY' in batch_prices:
                spy_price = batch_prices['SPY']
                sp500_value = spy_price * 10
                from models import MarketData
                market_data = MarketData(
                    ticker='SPY_INTRADAY',
                    date=today_et,
                    timestamp=current_time,
                    close_price=sp500_value
                )
                db.session.add(market_data)
                results['spy_data_collected'] = True
        
        # Step 3: Calculate portfolio values (now using CACHED data from batch call)
        # All stock prices are already in cache - no additional API calls needed!
        intraday_snapshots = []
        
        for user in users:
            try:
                # Calculate current portfolio value WITH cash tracking
                from cash_tracking import calculate_portfolio_value_with_cash
                portfolio_data = calculate_portfolio_value_with_cash(user.id)
                
                total_value = portfolio_data['total_value']
                stock_value = portfolio_data['stock_value']
                cash_proceeds = portfolio_data['cash_proceeds']
                
                if total_value > 0:  # Only create snapshots for users with portfolios
                    # Create intraday snapshot with ALL fields (add to batch)
                    intraday_snapshot = PortfolioSnapshotIntraday(
                        user_id=user.id,
                        timestamp=current_time,
                        total_value=total_value,
                        stock_value=stock_value,
                        cash_proceeds=cash_proceeds,
                        max_cash_deployed=user.max_cash_deployed
                    )
                    intraday_snapshots.append(intraday_snapshot)
                    results['snapshots_created'] += 1
                
                results['users_processed'] += 1
                
            except Exception as e:
                error_msg = f"Error processing user {user.id}: {str(e)}"
                results['errors'].append(error_msg)
                logger.error(error_msg)
        
        # Batch commit all intraday snapshots
        try:
            if intraday_snapshots:
                db.session.bulk_save_objects(intraday_snapshots)
                logger.info(f"Batch saved {len(intraday_snapshots)} intraday snapshots")
            
            db.session.commit()
            logger.info(f"Intraday collection completed: {results['snapshots_created']} snapshots created")
        except Exception as e:
            db.session.rollback()
            error_msg = f"Database commit failed: {str(e)}"
            results['errors'].append(error_msg)
            logger.error(error_msg)
        
        # Step 4: Rebuild 1D leaderboard cache (so leaderboard reflects live intraday data)
        try:
            leaderboard_start = time.time()
            remaining_time = 55 - (time.time() - start_time)  # Leave 5s buffer before Vercel 60s timeout
            
            if remaining_time > 10:  # Only attempt if we have at least 10s left
                from leaderboard_utils import update_leaderboard_cache
                lb_count = update_leaderboard_cache(periods=['1D'])
                leaderboard_time = round(time.time() - leaderboard_start, 2)
                results['leaderboard_1d_rebuilt'] = True
                results['leaderboard_1d_entries'] = lb_count
                results['leaderboard_1d_time'] = leaderboard_time
                logger.info(f"1D leaderboard cache rebuilt: {lb_count} entries in {leaderboard_time}s")
            else:
                results['leaderboard_1d_rebuilt'] = False
                results['leaderboard_1d_skipped_reason'] = f'Insufficient time ({remaining_time:.0f}s remaining)'
                logger.warning(f"Skipped 1D leaderboard rebuild - only {remaining_time:.0f}s remaining")
        except Exception as e:
            results['leaderboard_1d_rebuilt'] = False
            results['leaderboard_1d_error'] = str(e)
            logger.error(f"1D leaderboard rebuild failed: {e}")
        
        # Add execution timing
        execution_time = time.time() - start_time
        results['execution_time_seconds'] = round(execution_time, 2)
        logger.info(f"Intraday collection completed in {execution_time:.2f} seconds")
        
        return jsonify({
            'success': len(results['errors']) == 0,
            'message': 'Intraday data collection completed',
            'results': results
        }), 200
    
    except Exception as e:
        logger.error(f"Unexpected error in intraday collection: {str(e)}")
        return jsonify({'error': f'Internal server error: {str(e)}'}), 500

@app.route('/admin/check-intraday-data')
@admin_2fa_required
def check_intraday_data():
    """Check intraday data for last 7 trading days - shows ALL snapshots and missing intervals"""
    try:
        from datetime import datetime, date, timedelta
        from models import PortfolioSnapshotIntraday, User
        from sqlalchemy import cast, Date
        from zoneinfo import ZoneInfo
        
        MARKET_TZ = ZoneInfo('America/New_York')
        current_time_et = get_market_time()
        today_et = get_market_date()
        
        # Get last 7 calendar days (covers 5 trading days)
        start_date = today_et - timedelta(days=7)
        
        # Get ALL intraday snapshots for last 7 days
        all_snapshots = PortfolioSnapshotIntraday.query.filter(
            cast(PortfolioSnapshotIntraday.timestamp, Date) >= start_date
        ).order_by(PortfolioSnapshotIntraday.timestamp.asc()).all()
        
        logger.info(f"Found {len(all_snapshots)} total intraday snapshots from {start_date} to {today_et}")
        
        # Expected 15-minute intervals during market hours (9:30 AM - 4:00 PM ET)
        expected_times = []
        for hour in range(9, 17):
            for minute in [0, 15, 30, 45]:
                if hour == 9 and minute < 30:
                    continue
                if hour == 16 and minute > 0:
                    continue
                expected_times.append((hour, minute))
        
        # Group by date and user
        data_by_date = {}
        for snapshot in all_snapshots:
            # Convert to ET
            ts = snapshot.timestamp
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=ZoneInfo('UTC'))
            ts_et = ts.astimezone(MARKET_TZ)
            snapshot_date = ts_et.date()
            
            if snapshot_date not in data_by_date:
                data_by_date[snapshot_date] = {}
            
            if snapshot.user_id not in data_by_date[snapshot_date]:
                data_by_date[snapshot_date][snapshot.user_id] = []
            
            data_by_date[snapshot_date][snapshot.user_id].append({
                'time': ts_et.strftime('%H:%M'),
                'timestamp': ts_et.isoformat(),
                'value': snapshot.total_value
            })
        
        # Get all users
        all_users = User.query.all()
        user_map = {u.id: u.username for u in all_users}
        
        # Build report for each date
        daily_reports = {}
        for check_date in [today_et - timedelta(days=i) for i in range(7, -1, -1)]:
            # Skip weekends
            if check_date.weekday() >= 5:
                continue
            
            date_str = check_date.isoformat()
            daily_reports[date_str] = {
                'total_snapshots': 0,
                'users': {}
            }
            
            if check_date in data_by_date:
                for user_id, snapshots in data_by_date[check_date].items():
                    username = user_map.get(user_id, f'User_{user_id}')
                    actual_times = {s['time'] for s in snapshots}
                    expected_time_strs = {f'{h:02d}:{m:02d}' for h, m in expected_times}
                    missing_times = sorted(expected_time_strs - actual_times)
                    
                    daily_reports[date_str]['users'][username] = {
                        'count': len(snapshots),
                        'expected': len(expected_times),
                        'missing_count': len(missing_times),
                        'missing_times': missing_times,
                        'snapshots': snapshots
                    }
                    daily_reports[date_str]['total_snapshots'] += len(snapshots)
        
        return jsonify({
            'success': True,
            'current_time_et': current_time_et.isoformat(),
            'date_range': f'{start_date.isoformat()} to {today_et.isoformat()}',
            'total_snapshots_all_days': len(all_snapshots),
            'expected_intervals_per_day': len(expected_times),
            'daily_reports': daily_reports,
            'summary': f'Found {len(all_snapshots)} intraday snapshots across last 7 days'
        }), 200
    
    except Exception as e:
        logger.error(f"Error checking intraday data: {str(e)}")
        import traceback
        return jsonify({
            'error': f'Unexpected error: {str(e)}',
            'details': 'Check server logs'
        }), 500


@app.route('/admin/fix-ticker', methods=['POST'])
@admin_2fa_required
def admin_fix_ticker():
    """Fix incorrect ticker symbol for a user's stock"""
    try:
        from models import User, Stock
        
        username = request.json.get('username')
        old_ticker = request.json.get('old_ticker')
        new_ticker = request.json.get('new_ticker')
        
        if not username or not old_ticker or not new_ticker:
            return jsonify({'error': 'username, old_ticker, and new_ticker required'}), 400
        
        # Find user
        user = User.query.filter_by(username=username).first()
        if not user:
            return jsonify({'error': f'User {username} not found'}), 404
        
        # Find stock with old ticker
        stock = Stock.query.filter_by(user_id=user.id, ticker=old_ticker).first()
        if not stock:
            return jsonify({'error': f'Stock {old_ticker} not found for user {username}'}), 404
        
        # Update ticker
        stock.ticker = new_ticker
        db.session.commit()
        
        logger.info(f"Updated ticker for user {username}: {old_ticker} -> {new_ticker}")
        
        return jsonify({
            'success': True,
            'username': username,
            'old_ticker': old_ticker,
            'new_ticker': new_ticker,
            'stock_id': stock.id,
            'quantity': stock.quantity
        }), 200
        
    except Exception as e:
        logger.error(f"Error fixing ticker: {e}")
        import traceback
        return jsonify({
            'error': str(e),
            'details': 'Check server logs'
        }), 500


@app.route('/admin/check-spy-collection')
@admin_required
def check_spy_collection():
    """Check SPY_INTRADAY data collection (public endpoint for verification)"""
    try:
        from models import MarketData
        from datetime import datetime, timedelta
        
        # Get today's SPY_INTRADAY data
        today = datetime.now().date()
        spy_records = MarketData.query.filter(
            MarketData.ticker == 'SPY_INTRADAY',
            MarketData.date == today
        ).order_by(MarketData.timestamp.desc()).all()
        
        # Get yesterday's data for comparison
        yesterday = today - timedelta(days=1)
        yesterday_records = MarketData.query.filter(
            MarketData.ticker == 'SPY_INTRADAY',
            MarketData.date == yesterday
        ).count()
        
        # Get total SPY_INTRADAY records
        total_records = MarketData.query.filter(
            MarketData.ticker == 'SPY_INTRADAY'
        ).count()
        
        return jsonify({
            'success': True,
            'today_date': today.isoformat(),
            'spy_records_today': len(spy_records),
            'spy_records_yesterday': yesterday_records,
            'total_spy_intraday_records': total_records,
            'latest_records': [
                {
                    'timestamp': record.timestamp.isoformat(),
                    'sp500_value': record.close_price,
                    'date': record.date.isoformat()
                }
                for record in spy_records[:5]  # Show last 5 records
            ]
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/.well-known/apple-app-site-association')
def apple_app_site_association():
    """Serve Apple App Site Association file for Universal Links"""
    return jsonify({
        "applinks": {
            "apps": [],
            "details": [
                {
                    "appID": os.environ.get('APPLE_TEAM_ID', 'TEAM_ID') + ".com.apestogether.ApesTogether",
                    "paths": ["/p/*"]
                }
            ]
        }
    }), 200, {'Content-Type': 'application/json', 'Cache-Control': 'no-store'}


# Canonical Android signing-cert SHA-256 fingerprints for Digital Asset Links.
# These are PUBLIC (served openly at /.well-known/assetlinks.json) and rotate
# essentially never, so we embed them in code as the reliable source of truth.
# This MUST stay in sync with public/.well-known/assetlinks.json (kept for local
# Android tooling/docs). Rationale: Vercel's includeFiles does NOT reliably bundle
# the static file into the Python lambda, so the prior file-read fell through to
# an empty env var and shipped EMPTY fingerprints to production — which silently
# breaks Android App Links autoVerify. Order of precedence below:
#   ANDROID_SHA256_FINGERPRINT env var (rotation override) -> committed file -> this constant.
_ANDROID_CERT_FINGERPRINTS = [
    "64:47:B5:21:9B:F5:9F:95:12:E1:5D:8C:1E:50:F8:CB:35:60:EA:61:45:A4:7D:8B:51:37:C5:44:7D:10:2B:57",
    "0A:3A:A0:63:34:F2:64:8A:2E:93:CD:CA:B0:93:D2:23:62:43:29:CE:2F:00:8E:81:05:C7:BE:49:C2:DA:1C:CA",
]


@app.route('/.well-known/assetlinks.json')
def android_asset_links():
    """Serve Digital Asset Links for Android App Links (deep links).

    Precedence: ANDROID_SHA256_FINGERPRINT env var (for key rotation without a
    code deploy) -> committed public/.well-known/assetlinks.json -> the embedded
    _ANDROID_CERT_FINGERPRINTS constant. The constant guarantees we NEVER serve an
    empty fingerprint list (which silently disables Android App Links autoVerify),
    regardless of whether Vercel bundles the static file into the lambda.
    """
    import json
    package_name = os.environ.get('ANDROID_PACKAGE_NAME', 'com.apestogether.app')

    # 1) Env-var override (comma-separated) — lets us rotate without a deploy.
    env_fp = os.environ.get('ANDROID_SHA256_FINGERPRINT', '')
    fingerprints = [fp.strip() for fp in env_fp.split(',') if fp.strip()]

    # 2) Committed static file, if the runtime can actually read it.
    if not fingerprints:
        asset_links_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'public', '.well-known', 'assetlinks.json'
        )
        try:
            with open(asset_links_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            file_fps = (data[0].get('target', {}).get('sha256_cert_fingerprints', [])
                        if isinstance(data, list) and data else [])
            fingerprints = [fp for fp in file_fps if fp]
        except Exception as e:
            logger.warning(f"assetlinks.json file unavailable ({e}); using embedded constant")

    # 3) Embedded constant — the reliable backstop.
    if not fingerprints:
        fingerprints = list(_ANDROID_CERT_FINGERPRINTS)

    return jsonify([{
        "relation": ["delegate_permission/common.handle_all_urls"],
        "target": {
            "namespace": "android_app",
            "package_name": package_name,
            "sha256_cert_fingerprints": fingerprints
        }
    }]), 200, {'Content-Type': 'application/json', 'Cache-Control': 'no-store'}

@app.route('/p/<slug>')
def public_portfolio_view(slug):
    """Public portfolio view - accessible without login"""
    try:
        from models import User, PortfolioSnapshot, Stock, Subscription
        from portfolio_performance import PortfolioPerformanceCalculator
        
        # Find user by portfolio slug
        user = User.query.filter_by(portfolio_slug=slug).first()
        
        if not user:
            return """
            <html><head><title>Portfolio Not Found</title></head>
            <body style="font-family: Arial; text-align: center; padding: 50px;">
                <h1>Portfolio Not Found</h1>
                <p>The portfolio you're looking for doesn't exist.</p>
                <p><a href="/">Return to Home</a></p>
            </body></html>
            """, 404
        
        # Track shared portfolio link click
        try:
            from models import PageView, db as _db
            import hashlib as _hl
            _ip = request.headers.get('X-Forwarded-For', request.remote_addr or '')
            _db.session.add(PageView(
                page=f'/p/{slug}',
                referrer=(request.referrer or '')[:500] or None,
                user_agent=(request.headers.get('User-Agent', ''))[:500] or None,
                ip_hash=_hl.sha256(_ip.encode()).hexdigest()[:16] if _ip else None,
            ))
            _db.session.commit()
        except Exception:
            pass

        # Check if user account is deleted (GDPR)
        if user.deleted_at:
            return """
            <html><head><title>Portfolio Not Available</title></head>
            <body style="font-family: Arial; text-align: center; padding: 50px;">
                <h1>Portfolio Not Available</h1>
                <p>This portfolio is no longer available.</p>
                <p><a href="/">Return to Home</a></p>
            </body></html>
            """, 404
        
        # Check if current user is a subscriber
        is_subscriber = False
        if current_user.is_authenticated:
            # Check if viewing own portfolio OR has active subscription
            if current_user.id == user.id:
                is_subscriber = True
            else:
                # Check for active OR cancelled (but not expired) subscription
                subscription = Subscription.query.filter(
                    Subscription.subscriber_id == current_user.id,
                    Subscription.subscribed_to_id == user.id,
                    Subscription.status.in_(['active', 'cancelled'])
                ).first()
                
                # If cancelled, check if still within access period
                if subscription:
                    if subscription.status == 'active':
                        is_subscriber = True
                    elif subscription.status == 'cancelled' and subscription.end_date:
                        is_subscriber = subscription.end_date > datetime.utcnow()
                    else:
                        is_subscriber = False
        
        # Load all stocks once (used for value calc, holdings, and count)
        from models import Transaction
        from datetime import timedelta
        
        stocks = Stock.query.filter_by(user_id=user.id).all()
        num_stocks = len(stocks)
        
        # Single bulk API call for ALL stock prices (instead of N serial calls)
        calculator = PortfolioPerformanceCalculator()
        tickers = [s.ticker for s in stocks if s.quantity > 0]
        batch_prices = calculator.get_batch_stock_data(tickers) if tickers else {}
        
        # Calculate current portfolio value from batch prices
        current_value = 0.0
        for stock in stocks:
            if stock.quantity > 0:
                price = batch_prices.get(stock.ticker.upper(), stock.purchase_price)
                current_value += price * stock.quantity
        current_value += getattr(user, 'cash_proceeds', 0.0) or 0.0
        
        # Get latest snapshot for comparison
        latest_snapshot = PortfolioSnapshot.query.filter_by(user_id=user.id).order_by(
            PortfolioSnapshot.date.desc()
        ).first()
        
        # Calculate performance
        if latest_snapshot:
            day_change = current_value - latest_snapshot.total_value
            day_change_pct = (day_change / latest_snapshot.total_value * 100) if latest_snapshot.total_value > 0 else 0
        else:
            day_change = 0
            day_change_pct = 0
        
        # Average trades per week (last 30 days)
        thirty_days_ago = datetime.utcnow() - timedelta(days=30)
        recent_trades = Transaction.query.filter(
            Transaction.user_id == user.id,
            Transaction.timestamp >= thirty_days_ago
        ).count()
        avg_trades_per_week = round(recent_trades / 4.3, 1)  # 30 days ≈ 4.3 weeks
        
        # Build holdings from batch prices (no additional API calls).
        # Filter zombie 0-share rows (see /admin/cleanup-zero-share-stocks).
        # Phase B additions:
        #   - quantity_display: pre-formatted string so the Jinja template
        #     can show 4 decimals for fractional positions (e.g. 0.5000)
        #     and integer for whole positions (e.g. 10), avoiding the
        #     "fractional shows as 0" rounding bug.
        #   - pct_of_portfolio: position's share of total portfolio value
        #     (including cash), as a 0-100 percent.
        holdings = []
        cash_balance = float(getattr(user, 'cash_proceeds', 0.0) or 0.0)
        if is_subscriber:
            for stock in stocks:
                if not stock.quantity or stock.quantity <= 0:
                    continue
                price = batch_prices.get(stock.ticker.upper(), stock.purchase_price)
                value = price * stock.quantity
                gain_loss = value - (stock.purchase_price * stock.quantity)
                gain_loss_pct = (gain_loss / (stock.purchase_price * stock.quantity) * 100) if stock.purchase_price > 0 else 0
                pct_of_portfolio = (value / current_value * 100) if current_value > 0 else 0

                qty = float(stock.quantity)
                if abs(qty - round(qty)) < 0.0001:
                    quantity_display = f"{qty:.0f}"
                else:
                    quantity_display = f"{qty:.4f}"

                holdings.append({
                    'ticker': stock.ticker,
                    'quantity': stock.quantity,
                    'quantity_display': quantity_display,
                    'purchase_price': stock.purchase_price,
                    'current_price': price,
                    'value': value,
                    'gain_loss': gain_loss,
                    'gain_loss_pct': gain_loss_pct,
                    'pct_of_portfolio': pct_of_portfolio,
                })
        
        # Get user's leaderboard positions (if in top 20)
        leaderboard_positions = {}
        try:
            from leaderboard_utils import get_user_leaderboard_positions
            leaderboard_positions = get_user_leaderboard_positions(user.id, top_n=20)
        except Exception as e:
            logger.error(f"Error fetching leaderboard positions: {str(e)}")
        
        # Industry mix — cache-first from UserPortfolioStats
        industry_mix = {}
        large_cap_pct = 0.0
        try:
            from models import UserPortfolioStats
            stats = UserPortfolioStats.query.filter_by(user_id=user.id).first()
            if stats:
                if stats.industry_mix and isinstance(stats.industry_mix, dict):
                    industry_mix = stats.industry_mix
                large_cap_pct = float(stats.large_cap_percent) if stats.large_cap_percent else 0.0
        except Exception:
            pass
        # Fallback: live compute if cache empty
        if not industry_mix:
            try:
                from leaderboard_utils import calculate_industry_mix, calculate_portfolio_cap_percentages
                industry_mix = calculate_industry_mix(user.id) or {}
                _, large_cap_pct = calculate_portfolio_cap_percentages(user.id)
                large_cap_pct = float(large_cap_pct) if large_cap_pct else 0.0
            except Exception:
                pass
        
        # Account age
        account_age_days = 0
        if user.created_at:
            account_age_days = (datetime.utcnow() - user.created_at).days
        
        # Subscriber count
        subscriber_count = Subscription.query.filter_by(
            subscribed_to_id=user.id, status='active'
        ).count()
        
        # Best performance return for OG meta description
        best_period = ''
        best_return = 0.0
        if leaderboard_positions:
            best_period = min(leaderboard_positions, key=leaderboard_positions.get)
        
        return render_template('public_portfolio.html',
            username=user.username,
            current_value=current_value,
            day_change=day_change,
            day_change_pct=day_change_pct,
            slug=slug,
            portfolio_owner_id=user.id,
            subscription_price=user.subscription_price or 4.00,
            is_subscriber=is_subscriber,
            holdings=holdings,
            cash_balance=cash_balance,
            cash_pct_of_portfolio=(cash_balance / current_value * 100) if current_value > 0 else 0,
            num_stocks=num_stocks,
            avg_trades_per_week=avg_trades_per_week,
            leaderboard_positions=leaderboard_positions,
            industry_mix=industry_mix,
            large_cap_pct=round(large_cap_pct, 1),
            account_age_days=account_age_days,
            subscriber_count=subscriber_count,
            stripe_public_key=app.config.get('STRIPE_PUBLIC_KEY', '')
        )
    
    except Exception as e:
        logger.error(f"Public portfolio view error: {str(e)}")
        import traceback
        traceback.print_exc()
        return f"""
        <html><head><title>Error</title></head>
        <body style="font-family: Arial; text-align: center; padding: 50px;">
            <h1>Something Went Wrong</h1>
            <p>We encountered an error loading this portfolio.</p>
            <p><a href="/">Return to Home</a></p>
            <p style="color: #666; font-size: 12px;">Error: {str(e)}</p>
        </body></html>
        """, 500

@app.route('/settings/portfolio-sharing')
@login_required
def portfolio_sharing_settings():
    """Settings page for portfolio sharing"""
    try:
        # Generate slug if user doesn't have one
        if not current_user.portfolio_slug:
            current_user.portfolio_slug = generate_portfolio_slug()
            db.session.commit()
        
        share_url = f"https://apestogether.ai/p/{current_user.portfolio_slug}"
        
        return render_template('portfolio_sharing_settings.html',
            share_url=share_url,
            slug=current_user.portfolio_slug
        )
    
    except Exception as e:
        logger.error(f"Portfolio sharing settings error: {str(e)}")
        flash('Error loading portfolio sharing settings', 'danger')
        return redirect(url_for('index'))

@app.route('/settings/regenerate-portfolio-slug', methods=['POST'])
@login_required
def regenerate_portfolio_slug():
    """Regenerate portfolio slug (invalidates old share links)"""
    try:
        current_user.portfolio_slug = generate_portfolio_slug()
        db.session.commit()
        
        return jsonify({
            'success': True,
            'new_slug': current_user.portfolio_slug,
            'new_url': f"https://apestogether.ai/p/{current_user.portfolio_slug}"
        })
    
    except Exception as e:
        logger.error(f"Regenerate slug error: {str(e)}")
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/create-subscription', methods=['POST'])
@login_required
def create_subscription():
    """DISABLED: Stripe create subscription - web payments disabled Feb 2026"""
    return jsonify({'error': 'Web payments disabled. Please use the mobile app.'}), 410

@app.route('/unsubscribe-from-portfolio', methods=['POST'])
@login_required
def unsubscribe_from_portfolio():
    """DISABLED: Stripe unsubscribe - web payments disabled Feb 2026"""
    return jsonify({'error': 'Web payments disabled. Please use the mobile app.'}), 410

@app.route('/settings/gdpr')
@login_required
def gdpr_settings():
    """GDPR settings page - account deletion"""
    return render_template('gdpr_settings.html')

@app.route('/settings/delete-account', methods=['POST'])
@login_required
def delete_account():
    """GDPR-compliant account deletion - soft delete with 30-day grace period"""
    try:
        # Capture the user object before logout so we can notify subscribers.
        deleted_user = current_user._get_current_object()

        # Soft delete - mark account as deleted
        current_user.deleted_at = datetime.utcnow()
        db.session.commit()

        # Stop Google Play auto-renewals tied to this account (both the
        # subscribers paying THIS creator and subscriptions this user pays
        # for), then notify the creator's active subscribers (push + email).
        # Apple has no cancel API — Apple-billed subscribers get a deep-linked
        # cancellation email instead. Best-effort; never blocks deletion.
        try:
            from mobile_api import (
                _cancel_billing_for_deleted_account,
                _notify_subscribers_creator_deleted,
            )
            billing = _cancel_billing_for_deleted_account(deleted_user)
            _notify_subscribers_creator_deleted(
                deleted_user,
                google_cancelled_purchase_ids=billing.get('inbound_cancelled_purchase_ids'),
            )
        except Exception as notify_err:
            logger.error(f"creator-deleted notify (web) failed: {notify_err}")

        # Log out user
        from flask_login import logout_user
        logout_user()
        
        flash('Your account has been scheduled for deletion (30-day grace period). To restore it, email support@apestogether.ai — logging in will not restore it. Billing: auto-renewal for Google Play subscriptions purchased in the app has been turned off automatically where possible; Apple subscriptions must be cancelled in the App Store (Settings > your name > Subscriptions).', 'info')
        return redirect(url_for('index'))
    
    except Exception as e:
        logger.error(f"Account deletion error: {str(e)}")
        db.session.rollback()
        flash('Error deleting account. Please try again.', 'danger')
        return redirect(url_for('gdpr_settings'))

@app.route('/api/public-portfolio/<slug>/performance/<period>')
def public_portfolio_performance(slug, period):
    """Get performance data for a public portfolio (no authentication required)"""
    try:
        from models import User
        from portfolio_performance import PortfolioPerformanceCalculator
        
        # Find user by portfolio slug
        user = User.query.filter_by(portfolio_slug=slug).first()
        
        if not user:
            return jsonify({'error': 'Portfolio not found'}), 404
        
        # Check if user account is deleted (GDPR)
        if user.deleted_at:
            return jsonify({'error': 'Portfolio not available'}), 404
        
        # Get performance data using the existing calculator
        calculator = PortfolioPerformanceCalculator()
        data = calculator.get_performance_data(user.id, period)
        
        return jsonify(data)
    
    except Exception as e:
        logger.error(f"Public portfolio performance error: {str(e)}")
        return jsonify({'error': 'Performance calculation failed'}), 500


@app.route('/admin/rebuild-user-cache/<int:user_id>', methods=['GET'])
@admin_2fa_required
def admin_rebuild_user_cache(user_id):
    """Rebuild chart caches for a single user (avoids timeout)"""
    try:
        from datetime import date, datetime, timedelta
        import json
        from models import User, Stock, PortfolioSnapshot, MarketData, UserPortfolioChartCache
        
        start_time = datetime.now()
        results = {
            'user_id': user_id,
            'charts_fixed': 0,
            'data_points_generated': 0,
            'errors': []
        }
        
        # Check user exists
        user = User.query.get(user_id)
        if not user:
            return jsonify({'success': False, 'error': f'User {user_id} not found'}), 404
        
        # Get user's stocks to find portfolio start date
        user_stocks = Stock.query.filter_by(user_id=user_id).all()
        if not user_stocks:
            return jsonify({
                'success': True,
                'message': f'User {user_id} ({user.username}) has no stocks - no caches to generate'
            })
        
        portfolio_start_date = min(user_stocks, key=lambda s: s.purchase_date).purchase_date.date()
        
        periods = ['1D', '5D', '1M', '3M', 'YTD', '1Y']
        
        for period in periods:
            try:
                # Calculate date range
                end_date = date.today()
                
                if period == '1D':
                    start_date = end_date
                elif period == '5D':
                    start_date = end_date - timedelta(days=7)
                elif period == '1M':
                    start_date = end_date - timedelta(days=30)
                elif period == '3M':
                    start_date = end_date - timedelta(days=90)
                elif period == 'YTD':
                    start_date = date(end_date.year, 1, 1)
                elif period == '1Y':
                    start_date = end_date - timedelta(days=365)
                
                start_date = max(start_date, portfolio_start_date)
                
                # Get snapshots
                snapshots = PortfolioSnapshot.query.filter(
                    PortfolioSnapshot.user_id == user_id,
                    PortfolioSnapshot.date >= start_date,
                    PortfolioSnapshot.date <= end_date
                ).order_by(PortfolioSnapshot.date).all()
                
                # Get S&P 500 data
                sp500_data = MarketData.query.filter(
                    MarketData.ticker == "SPY_SP500",
                    MarketData.date >= start_date,
                    MarketData.date <= end_date
                ).order_by(MarketData.date).all()
                
                # Generate chart data
                snapshot_dict = {s.date: s.total_value for s in snapshots}
                sp500_dict = {s.date: s.close_price for s in sp500_data}
                
                chart_data_points = []
                current_date = start_date
                while current_date <= end_date:
                    if period == '1D' or current_date.weekday() < 5:
                        portfolio_value = snapshot_dict.get(current_date, 0)
                        sp500_value = sp500_dict.get(current_date, 0)
                        
                        if portfolio_value > 0 or sp500_value > 0:
                            chart_data_points.append({
                                'date': current_date.isoformat(),
                                'portfolio': portfolio_value,
                                'sp500': sp500_value
                            })
                    
                    current_date += timedelta(days=1)
                
                # Calculate returns
                portfolio_return = 0
                sp500_return = 0
                
                if len(chart_data_points) >= 2:
                    first_portfolio = next((p['portfolio'] for p in chart_data_points if p['portfolio'] > 0), 0)
                    last_portfolio = chart_data_points[-1]['portfolio']
                    
                    first_sp500 = next((p['sp500'] for p in chart_data_points if p['sp500'] > 0), 0)
                    last_sp500 = chart_data_points[-1]['sp500']
                    
                    if first_portfolio > 0:
                        portfolio_return = ((last_portfolio - first_portfolio) / first_portfolio) * 100
                    
                    if first_sp500 > 0:
                        sp500_return = ((last_sp500 - first_sp500) / first_sp500) * 100
                
                chart_cache_data = {
                    'chart_data': chart_data_points,
                    'portfolio_return': round(portfolio_return, 2),
                    'sp500_return': round(sp500_return, 2),
                    'period': period,
                    'start_date': start_date.isoformat(),
                    'end_date': end_date.isoformat()
                }
                
                # Update or create cache
                cache_entry = UserPortfolioChartCache.query.filter_by(
                    user_id=user_id,
                    period=period
                ).first()
                
                if cache_entry:
                    cache_entry.chart_data = json.dumps(chart_cache_data)
                    cache_entry.generated_at = datetime.now()
                else:
                    cache_entry = UserPortfolioChartCache(
                        user_id=user_id,
                        period=period,
                        chart_data=json.dumps(chart_cache_data),
                        generated_at=datetime.now()
                    )
                    db.session.add(cache_entry)
                
                results['charts_fixed'] += 1
                results['data_points_generated'] += len(chart_data_points)
                
                logger.info(f"User {user_id} {period}: {len(chart_data_points)} points, {portfolio_return:.2f}% return")
                
            except Exception as e:
                error_msg = f"{period}: {str(e)}"
                results['errors'].append(error_msg)
                logger.error(f"Error generating {period} cache for user {user_id}: {e}")
        
        # Single commit for this user
        db.session.commit()
        
        processing_time = (datetime.now() - start_time).total_seconds()
        
        logger.info(f"Rebuilt caches for user {user_id} ({user.username}) in {processing_time:.2f}s")
        
        return jsonify({
            'success': True,
            'username': user.username,
            'processing_time': round(processing_time, 2),
            'results': results
        }), 200
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Rebuild failed for user {user_id}: {str(e)}")
        import traceback
        return jsonify({
            'success': False,
            'error': str(e),
            'details': 'Check server logs'
        }), 500

@app.route('/admin/rebuild-all-caches', methods=['GET'])
@admin_2fa_required
def admin_rebuild_all_caches():
    """UI page to rebuild caches for all users sequentially"""
    try:
        # Get all users with stocks
        users_with_stocks = db.session.query(User.id, User.username).join(Stock).distinct().all()
        
        return f'''
        <!DOCTYPE html>
        <html>
        <head>
            <title>Rebuild User Caches</title>
            <style>
                body {{ font-family: Arial, sans-serif; max-width: 800px; margin: 20px auto; padding: 20px; }}
                .user-item {{ padding: 10px; margin: 10px 0; border: 1px solid #ddd; border-radius: 4px; }}
                .status {{ margin-left: 10px; font-weight: bold; }}
                .success {{ color: #28a745; }}
                .error {{ color: #dc3545; }}
                .processing {{ color: #007bff; }}
                button {{ padding: 8px 16px; margin: 5px; cursor: pointer; }}
                .rebuild-all {{ background: #007bff; color: white; border: none; border-radius: 4px; padding: 12px 24px; font-size: 16px; }}
                .progress {{ margin-top: 20px; padding: 15px; background: #f8f9fa; border-radius: 4px; }}
            </style>
        </head>
        <body>
            <h1>🔄 Rebuild User Caches</h1>
            <p>Rebuild chart caches one user at a time (avoids timeout).</p>
            
            <button class="rebuild-all" onclick="rebuildAll()">🚀 Rebuild All Users</button>
            
            <div id="progress" class="progress" style="display:none;">
                <strong>Progress:</strong> <span id="progress-text">0/{len(users_with_stocks)}</span>
            </div>
            
            <div id="user-list">
                {"".join([f'''
                <div class="user-item">
                    <strong>{username}</strong> (ID: {user_id})
                    <button onclick="rebuildUser({user_id})">Rebuild</button>
                    <span class="status" id="status-{user_id}"></span>
                </div>
                ''' for user_id, username in users_with_stocks])}
            </div>
            
            <script>
                let completedCount = 0;
                const totalUsers = {len(users_with_stocks)};
                
                async function rebuildUser(userId) {{
                    const statusEl = document.getElementById(`status-${{userId}}`);
                    statusEl.textContent = '⏳ Rebuilding...';
                    statusEl.className = 'status processing';
                    
                    try {{
                        const response = await fetch(`/admin/rebuild-user-cache/${{userId}}`);
                        const data = await response.json();
                        
                        if (data.success) {{
                            statusEl.textContent = `✅ Done! (${{data.results.charts_fixed}} charts, ${{data.processing_time}}s)`;
                            statusEl.className = 'status success';
                        }} else {{
                            statusEl.textContent = `❌ Error: ${{data.error}}`;
                            statusEl.className = 'status error';
                        }}
                    }} catch (error) {{
                        statusEl.textContent = `❌ Failed: ${{error.message}}`;
                        statusEl.className = 'status error';
                    }}
                }}
                
                async function rebuildAll() {{
                    const progressDiv = document.getElementById('progress');
                    const progressText = document.getElementById('progress-text');
                    
                    progressDiv.style.display = 'block';
                    completedCount = 0;
                    
                    const userIds = {[user_id for user_id, _ in users_with_stocks]};
                    
                    for (let userId of userIds) {{
                        await rebuildUser(userId);
                        completedCount++;
                        progressText.textContent = `${{completedCount}}/${{totalUsers}}`;
                        
                        // 2 second buffer between users
                        if (completedCount < totalUsers) {{
                            await new Promise(resolve => setTimeout(resolve, 2000));
                        }}
                    }}
                    
                    alert('✅ All caches rebuilt!');
                }}
            </script>
        </body>
        </html>
        '''
        
    except Exception as e:
        logger.error(f"Error loading rebuild UI: {str(e)}")
        return f"Error: {str(e)}", 500


@app.route('/admin/populate-portfolio-stats', methods=['GET', 'POST'])
@admin_2fa_required
def admin_populate_portfolio_stats():
    """
    One-time population of portfolio stats for all users
    Creates UserPortfolioStats entries for all users
    """
    try:
        from models import User, UserPortfolioStats, db
        from leaderboard_utils import calculate_user_portfolio_stats
        from datetime import datetime
        
        results = {
            'users_processed': 0,
            'users_created': 0,
            'users_updated': 0,
            'errors': []
        }
        
        # Get all users
        all_users = User.query.all()
        logger.info(f"Populating portfolio stats for {len(all_users)} users")
        
        for user in all_users:
            try:
                # Calculate stats
                stats = calculate_user_portfolio_stats(user.id)
                
                # Check if entry exists
                existing_stats = UserPortfolioStats.query.filter_by(user_id=user.id).first()
                
                if existing_stats:
                    # Update existing
                    existing_stats.unique_stocks_count = stats['unique_stocks_count']
                    existing_stats.avg_trades_per_week = stats['avg_trades_per_week']
                    existing_stats.total_trades = stats['total_trades']
                    existing_stats.large_cap_percent = stats['large_cap_percent']
                    existing_stats.small_cap_percent = stats['small_cap_percent']
                    existing_stats.industry_mix = stats['industry_mix']
                    existing_stats.subscriber_count = stats['subscriber_count']
                    # Phase E: fractional-shares flag for Discover/Leaderboard filter.
                    existing_stats.has_fractional_holdings = stats.get('has_fractional_holdings', False)
                    existing_stats.last_updated = datetime.utcnow()
                    results['users_updated'] += 1
                    logger.info(f"Updated stats for user {user.id} ({user.username})")
                else:
                    # Create new
                    new_stats = UserPortfolioStats(
                        user_id=user.id,
                        unique_stocks_count=stats['unique_stocks_count'],
                        avg_trades_per_week=stats['avg_trades_per_week'],
                        total_trades=stats['total_trades'],
                        large_cap_percent=stats['large_cap_percent'],
                        small_cap_percent=stats['small_cap_percent'],
                        industry_mix=stats['industry_mix'],
                        subscriber_count=stats['subscriber_count'],
                        has_fractional_holdings=stats.get('has_fractional_holdings', False),
                        last_updated=datetime.utcnow()
                    )
                    db.session.add(new_stats)
                    results['users_created'] += 1
                    logger.info(f"Created stats for user {user.id} ({user.username})")
                
                results['users_processed'] += 1
                
            except Exception as e:
                error_msg = f"Error processing user {user.id}: {str(e)}"
                results['errors'].append(error_msg)
                logger.error(error_msg)
        
        # Commit all changes
        db.session.commit()
        logger.info(f"Portfolio stats population complete: {results['users_processed']} users processed")
        
        return jsonify({
            'success': True,
            'message': 'Portfolio stats populated successfully',
            'results': results
        })
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error in populate-portfolio-stats: {str(e)}")
        import traceback
        return jsonify({
            'success': False,
            'error': str(e),
            'details': 'Check server logs'
        }), 500


@app.route('/admin/find-user-id', methods=['GET'])
@admin_2fa_required
def admin_find_user_id():
    """Find user_id by username or email"""
    try:
        from models import User
        
        username = request.args.get('username', '')
        search_email = request.args.get('email', '')
        
        if username:
            user = User.query.filter_by(username=username).first()
            if user:
                return jsonify({
                    'success': True,
                    'user_id': user.id,
                    'username': user.username,
                    'email': user.email
                })
        
        if search_email:
            user = User.query.filter_by(email=search_email).first()
            if user:
                return jsonify({
                    'success': True,
                    'user_id': user.id,
                    'username': user.username,
                    'email': user.email
                })
        
        # List all users
        all_users = User.query.all()
        return jsonify({
            'success': True,
            'users': [{
                'user_id': u.id,
                'username': u.username,
                'email': u.email
            } for u in all_users]
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/admin/trigger-chart-cache-generation', methods=['GET', 'POST'])
@admin_2fa_required
def admin_trigger_chart_cache_generation():
    """
    Manually trigger chart cache generation for all users
    This bypasses the market close cron to test chart generation directly
    """
    try:
        from leaderboard_utils import generate_chart_from_snapshots
        from models import User, UserPortfolioChartCache, db
        import json
        from datetime import datetime
        
        results = {
            'users_processed': 0,
            'charts_generated': 0,
            'errors': []
        }
        
        users = User.query.all()
        periods = ['1D', '5D', '1M', '3M', 'YTD', '1Y', '5Y', 'MAX']
        
        for user in users:
            for period in periods:
                try:
                    logger.info(f"Generating chart cache for user {user.id} ({user.username}), period {period}")
                    chart_data = generate_chart_from_snapshots(user.id, period)
                    
                    if chart_data:
                        # Update or create chart cache entry
                        chart_cache = UserPortfolioChartCache.query.filter_by(
                            user_id=user.id, period=period
                        ).first()
                        
                        if chart_cache:
                            chart_cache.chart_data = json.dumps(chart_data)
                            chart_cache.generated_at = datetime.now()
                            logger.info(f"Updated chart cache for user {user.id}, period {period}")
                        else:
                            chart_cache = UserPortfolioChartCache(
                                user_id=user.id,
                                period=period,
                                chart_data=json.dumps(chart_data),
                                generated_at=datetime.now()
                            )
                            db.session.add(chart_cache)
                            logger.info(f"Created chart cache for user {user.id}, period {period}")
                        
                        results['charts_generated'] += 1
                    else:
                        error_msg = f"No chart data generated for user {user.id}, period {period}"
                        results['errors'].append(error_msg)
                        logger.warning(error_msg)
                        
                except Exception as e:
                    error_msg = f"Error generating chart for user {user.id}, period {period}: {str(e)}"
                    results['errors'].append(error_msg)
                    logger.error(error_msg)
                    import traceback
                    logger.error(traceback.format_exc())
            
            results['users_processed'] += 1
        
        # Commit all chart caches
        db.session.commit()
        logger.info(f"Chart cache generation complete: {results['charts_generated']} charts for {results['users_processed']} users")
        
        return jsonify({
            'success': True,
            'message': f"Generated {results['charts_generated']} chart caches for {results['users_processed']} users",
            'results': results
        })
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error in trigger-chart-cache-generation: {str(e)}")
        import traceback
        return jsonify({
            'success': False,
            'error': str(e),
            'details': 'Check server logs'
        }), 500













