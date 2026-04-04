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

def admin_required(f):
    """Decorator: requires the user to be logged in AND be the admin."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash('Please log in to access this page', 'danger')
            return redirect(url_for('login', next=request.url))
        if getattr(current_user, 'email', None) != ADMIN_EMAIL:
            return jsonify({'error': 'Admin access required'}), 403
        return f(*args, **kwargs)
    return decorated_function

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

# Admin authentication check
def admin_required(f):
    """Decorator to check if user is an admin (login + email check)"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Check session cookie FIRST (no DB query needed)
        email = session.get('email', '')
        if email == ADMIN_EMAIL:
            return f(*args, **kwargs)
        # Fallback: check Flask-Login current_user (triggers DB query via load_user)
        # Wrap in try/except so SSL drops here don't poison the session for the route
        if not email:
            try:
                if current_user.is_authenticated:
                    email = getattr(current_user, 'email', '')
            except Exception:
                # DB error loading user — clean up so route's db_retry starts fresh
                app._nuke_session()
        
        # Allow access only for admin email
        if email == ADMIN_EMAIL:
            return f(*args, **kwargs)
            
        # Show access denied page with login form instead of redirecting
        return render_template_string("""
<!DOCTYPE html>
<html>
<head>
    <title>Admin Access</title>
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
        }
        .error {
            background-color: #ffdddd;
            border-left: 6px solid #f44336;
            margin-bottom: 15px;
            padding: 10px;
            border-radius: 5px;
        }
        .form {
            background-color: #f9f9f9;
            padding: 20px;
            border-radius: 5px;
        }
        input[type=text] {
            width: 100%;
            padding: 12px 20px;
            margin: 8px 0;
            box-sizing: border-box;
        }
        input[type=submit] {
            background-color: #4CAF50;
            color: white;
            padding: 14px 20px;
            margin: 8px 0;
            border: none;
            border-radius: 4px;
            cursor: pointer;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>Admin Access</h1>
        
        <div class="error">
            <h2>Access Denied</h2>
            <p>You must be logged in with the admin email to access this page.</p>
        </div>
        
        <div class="form">
            <h2>Admin Login</h2>
            <form action="/login" method="post">
                <label for="email">Admin Email:</label>
                <input type="text" id="email" name="email" placeholder="Enter admin email">
                <input type="submit" value="Login">
            </form>
        </div>
        
        <a href="/" class="button">Back to Home</a>
    </div>
</body>
</html>
    """)
    return decorated_function

def admin_2fa_required(f):
    """Decorator: requires admin login + 2FA verification (admin_2fa_verified session flag).
    Use this for endpoints that expose sensitive data (bot info, user data) or mutate state."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # First check admin login
        email = session.get('email', '')
        if not email:
            try:
                if current_user.is_authenticated:
                    email = getattr(current_user, 'email', '')
            except Exception:
                pass
        if email != ADMIN_EMAIL:
            return jsonify({'error': 'admin_login_required'}), 403
        # Then check 2FA
        if not session.get('admin_2fa_verified'):
            return jsonify({'error': '2fa_required', 'message': 'Visit /admin-panel and complete 2FA first'}), 401
        return f(*args, **kwargs)
    decorated_function.__name__ = f.__name__
    return decorated_function

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
    """Privacy Policy page"""
    return render_template_with_defaults('privacy_policy.html')

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
                    subscriber_count=stats['subscriber_count']
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
                    subscriber_count=stats['subscriber_count']
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
                
                return jsonify({
                    'portfolio_return': round(portfolio_return, 2),
                    'sp500_return': round(sp500_return, 2),
                    'chart_data': chart_data,
                    'period': period_upper,
                    'from_cache': True
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
        
        performance_data = {
            'portfolio_return': chart_data_chartjs.get('portfolio_return', 0),
            'sp500_return': chart_data_chartjs.get('sp500_return', 0),
            'chart_data': chart_data,
            'period': period_upper,
            'from_cache': False
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
                        
                        return jsonify({
                            'portfolio_return': round(portfolio_return, 2),
                            'sp500_return': round(sp500_return, 2),
                            'chart_data': chart_data,
                            'period': period_upper,
                            'from_cache': True
                        })
            except Exception as e:
                logger.warning(f"Failed to use cached chart data: {e}")
        
        # Fallback: Live calculation
        from portfolio_performance import PortfolioPerformanceCalculator
        calculator = PortfolioPerformanceCalculator()
        
        logger.info(f"Performing live calculation for public portfolio user {user_id}, period {period_upper}")
        performance_data = calculator.get_performance_data(user_id, period_upper)
        
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
      1    – Portfolio snapshots
      1.5  – S&P 500 close data
      1.75 – Commit core data
      1.8  – Dividend detection
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
            
            # PHASE 1.8: Automatic Dividend Detection
            # Check all held tickers for ex-dividend dates and credit users
            try:
                logger.info("PHASE 1.8: Checking for dividends...")
                results['pipeline_phases'].append('dividends_started')
                
                from dividend_tracker import process_dividends_for_date
                div_results = process_dividends_for_date(db, target_date=today_et)
                
                results['dividends_found'] = div_results.get('dividends_found', 0)
                results['dividends_recorded'] = div_results.get('dividends_recorded', 0)
                results['dividend_total_amount'] = div_results.get('total_amount', 0.0)
                
                if div_results.get('dividends_recorded', 0) > 0:
                    db.session.commit()
                    logger.info(f"✅ PHASE 1.8 Complete: {div_results['dividends_recorded']} dividends recorded (${div_results['total_amount']:.2f} total)")
                else:
                    logger.info(f"PHASE 1.8 Complete: No dividends for {today_et}")
                
                results['pipeline_phases'].append('dividends_completed')
                
            except Exception as e:
                logger.warning(f"PHASE 1.8 WARNING: Dividend check failed (non-critical): {e}")
                results['errors'].append(f"Dividend check failed: {str(e)}")
                try:
                    db.session.rollback()
                except Exception:
                    pass
                # Non-critical — continue with leaderboard updates
            
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
        if 'error' in result:
            return jsonify(result), 500
        return jsonify(result)
    
    except Exception as e:
        logger.error(f"Bot trade wave cron error: {e}")
        import traceback
        return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500


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
    }), 200, {'Content-Type': 'application/json'}

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
        
        # Get current portfolio value
        calculator = PortfolioPerformanceCalculator()
        current_value = calculator.calculate_portfolio_value(user.id)
        
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
        
        # Calculate portfolio statistics
        from models import Transaction
        from datetime import timedelta
        
        # Number of unique stocks held
        num_stocks = Stock.query.filter_by(user_id=user.id).count()
        
        # Average trades per week (last 30 days)
        thirty_days_ago = datetime.utcnow() - timedelta(days=30)
        recent_trades = Transaction.query.filter(
            Transaction.user_id == user.id,
            Transaction.timestamp >= thirty_days_ago
        ).count()
        avg_trades_per_week = round(recent_trades / 4.3, 1)  # 30 days ≈ 4.3 weeks
        
        # Get holdings if subscriber
        holdings = []
        if is_subscriber:
            stocks = Stock.query.filter_by(user_id=user.id).all()
            for stock in stocks:
                # Get current price from API
                stock_data = get_stock_data(stock.ticker)
                current_price = stock_data.get('price', stock.purchase_price) if stock_data else stock.purchase_price
                value = current_price * stock.quantity
                gain_loss = value - (stock.purchase_price * stock.quantity)
                gain_loss_pct = (gain_loss / (stock.purchase_price * stock.quantity) * 100) if stock.purchase_price > 0 else 0
                
                holdings.append({
                    'ticker': stock.ticker,
                    'quantity': stock.quantity,
                    'purchase_price': stock.purchase_price,
                    'current_price': current_price,
                    'value': value,
                    'gain_loss': gain_loss,
                    'gain_loss_pct': gain_loss_pct
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
        # Soft delete - mark account as deleted
        current_user.deleted_at = datetime.utcnow()
        db.session.commit()
        
        # Log out user
        from flask_login import logout_user
        logout_user()
        
        flash('Your account has been scheduled for deletion. You have 30 days to cancel by logging in again.', 'info')
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













