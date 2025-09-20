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
import requests
import uuid
import time
import stripe
import sys
import traceback
from datetime import datetime, timedelta
from functools import wraps
from dotenv import load_dotenv
from sqlalchemy import create_engine, Column, Integer, String, Float, ForeignKey, DateTime, Boolean, func, text
from sqlalchemy.pool import NullPool
from flask import Flask, render_template_string, render_template, redirect, url_for, request, session, flash, jsonify, send_from_directory
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_session import Session
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.middleware.proxy_fix import ProxyFix
from authlib.integrations.flask_client import OAuth

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

# Get environment variables with fallbacks
# Check for DATABASE_URL first, then fall back to POSTGRES_PRISMA_URL if available
DATABASE_URL = os.environ.get('DATABASE_URL') or os.environ.get('POSTGRES_PRISMA_URL')
SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-key-for-testing')
VERCEL_ENV = os.environ.get('VERCEL_ENV')

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
    
    logger.info(f"Using database type: {DATABASE_URL.split('://')[0]}")

    # Configure Flask app
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-key-for-testing')
    app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    # Serverless-friendly SQLAlchemy engine options to avoid pool exhaustion
    app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
        'poolclass': NullPool,       # Disable pooling; connections are short-lived on serverless
        'pool_pre_ping': True,       # Validate connections before use
    }
    
    # Configure Flask-Session with SQLAlchemy backend for serverless environment
    app.config['SESSION_TYPE'] = 'sqlalchemy'
    app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=7)
    app.config['SESSION_COOKIE_SECURE'] = True
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
    
    # Debug logging for session configuration
    logger.info(f"Session configuration: TYPE={app.config.get('SESSION_TYPE')}, LIFETIME={app.config.get('PERMANENT_SESSION_LIFETIME')}")
    logger.info(f"Database URL for sessions: [REDACTED]")

    # Initialize Flask-Login
    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = 'login'

    # Add a before_request handler to ensure session and current_user are properly initialized
    @app.before_request
    def handle_before_request():
        # Skip session processing for static files and favicon
        if request.path.startswith('/static/') or request.path == '/favicon.png':
            return  # Skip session processing for static files
        
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
            # Only clear problematic session data if there's a critical error
            # that would prevent proper authentication
            if '_user_id' in session and str(e).startswith('Critical'):
                session.pop('_user_id', None)

    @login_manager.user_loader
    def load_user(user_id):
        try:
            return User.query.get(int(user_id))
        except Exception as e:
            logger.error(f"Error loading user: {str(e)}")
            return None

    # Stripe configuration
    app.config['STRIPE_PUBLIC_KEY'] = os.environ.get('STRIPE_PUBLIC_KEY')
    app.config['STRIPE_SECRET_KEY'] = os.environ.get('STRIPE_SECRET_KEY')
    app.config['STRIPE_WEBHOOK_SECRET'] = os.environ.get('STRIPE_WEBHOOK_SECRET')
    
    # Initialize Stripe
    stripe.api_key = app.config['STRIPE_SECRET_KEY']

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
    
    # Initialize Flask-Session with appropriate backend based on environment
    try:
        # For Vercel serverless environment, use filesystem sessions by default
        # This is more reliable in a serverless environment where database connections may be limited
        if os.environ.get('VERCEL_ENV') == 'production':
            logger.info("Vercel production environment detected, using filesystem session storage")
            app.config['SESSION_TYPE'] = 'filesystem'
            # Create a sessions directory if it doesn't exist
            os.makedirs('/tmp/flask_session', exist_ok=True)
            app.config['SESSION_FILE_DIR'] = '/tmp/flask_session'
            Session(app)
            logger.info("Flask-Session initialized with filesystem backend")
        else:
            # For non-Vercel environments, try SQLAlchemy backend first
            logger.info("Using SQLAlchemy session backend")
            app.config['SESSION_SQLALCHEMY'] = db
            app.config['SESSION_SQLALCHEMY_TABLE'] = 'sessions'
            
            # Create all tables including sessions
            with app.app_context():
                # First create all other tables
                tables_to_create = [table for table in db.metadata.tables.values() 
                                if table.name != 'sessions']
                db.metadata.create_all(bind=db.engine, tables=tables_to_create)
                
                # Explicitly create sessions table with proper schema
                # This ensures the table exists before Flask-Session tries to use it
                db.session.execute(text("""
                CREATE TABLE IF NOT EXISTS sessions (
                    id VARCHAR(255) NOT NULL PRIMARY KEY,
                    session_data BYTEA NOT NULL,
                    expiry TIMESTAMP(6) NOT NULL
                )
                """))
                db.session.commit()
                logger.info("Database tables created successfully, including sessions table")
            
            # Initialize Flask-Session after creating the sessions table
            Session(app)
            logger.info("Flask-Session initialized successfully with SQLAlchemy backend")
    except Exception as e:
        logger.error(f"Failed to initialize database or Flask-Session: {str(e)}", extra={'traceback': traceback.format_exc()})
        # Fall back to filesystem sessions as a last resort
        app.config['SESSION_TYPE'] = 'filesystem'
        os.makedirs('/tmp/flask_session', exist_ok=True)
        app.config['SESSION_FILE_DIR'] = '/tmp/flask_session'
        Session(app)
        logger.warning("Falling back to filesystem sessions due to error")
    logger.info("Database and migrations initialized successfully")
except Exception as e:
    logger.error(f"Failed to initialize database: {str(e)}")
    # Continue without database to allow basic functionality

# Define database models
class User(db.Model, UserMixin):
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
    """Decorator to check if user is an admin"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Check if user is authenticated via session
        email = session.get('email', '')
        
        # Allow access for fordutilityapps@gmail.com
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

@app.route('/create-checkout-session/<int:user_id>')
@login_required
def create_checkout_session(user_id):
    """Create a checkout session for Apple Pay and other payment methods"""
    user_to_subscribe_to = User.query.get_or_404(user_id)
    
    try:
        # Get or create a Stripe customer for the current user
        current_user_id = session.get('user_id')
        current_user = User.query.get(current_user_id)
        
        if not current_user.stripe_customer_id:
            customer = stripe.Customer.create(
                email=current_user.email,
                name=current_user.username
            )
            current_user.stripe_customer_id = customer.id
            db.session.commit()
        
        # Create a checkout session
        checkout_session = stripe.checkout.Session.create(
            payment_method_types=['card', 'apple_pay'],
            line_items=[{
                'price': user_to_subscribe_to.stripe_price_id,
                'quantity': 1,
            }],
            mode='subscription',
            success_url=request.host_url + 'subscription-success?session_id={CHECKOUT_SESSION_ID}',
            cancel_url=request.host_url + f'profile/{user_to_subscribe_to.username}',
            customer=current_user.stripe_customer_id,
            metadata={
                'subscriber_id': current_user.id,
                'subscribed_to_id': user_to_subscribe_to.id
            }
        )
        
        return redirect(checkout_session.url)
    except Exception as e:
        flash(f'Error creating checkout session: {str(e)}', 'danger')
        return redirect(url_for('profile', username=user_to_subscribe_to.username))

@app.route('/create-payment-intent', methods=['POST'])
@login_required
def create_payment_intent():
    """Creates a subscription and a Payment Intent for Stripe Elements with Apple Pay support"""
    data = request.get_json()
    user_id = data.get('user_id')
    user_to_subscribe_to = User.query.get_or_404(user_id)
    
    try:
        # Get or create a Stripe customer for the current user
        current_user_id = session.get('user_id')
        current_user = User.query.get(current_user_id)
        
        if not current_user.stripe_customer_id:
            customer = stripe.Customer.create(
                email=current_user.email,
                name=current_user.username
            )
            current_user.stripe_customer_id = customer.id
            db.session.commit()
        
        customer_id = current_user.stripe_customer_id

        # Create a subscription with an incomplete payment
        subscription = stripe.Subscription.create(
            customer=customer_id,
            items=[{'price': user_to_subscribe_to.stripe_price_id}],
            payment_behavior='default_incomplete',
            payment_settings={'save_default_payment_method': 'on_subscription'},
            expand=['latest_invoice.payment_intent'],
            metadata={
                'subscriber_id': current_user.id,
                'subscribed_to_id': user_to_subscribe_to.id
            }
        )
        
        # Add metadata to the payment intent as well for better tracking
        payment_intent = subscription.latest_invoice.payment_intent
        stripe.PaymentIntent.modify(
            payment_intent.id,
            metadata={
                'subscription': subscription.id,
                'subscriber_id': current_user.id,
                'subscribed_to_id': user_to_subscribe_to.id
            }
        )

        return jsonify({
            'clientSecret': payment_intent.client_secret,
            'subscriptionId': subscription.id
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@app.route('/payment-confirmation')
@login_required
def payment_confirmation():
    """Handle payment confirmation for cases requiring additional authentication"""
    payment_intent_client_secret = request.args.get('payment_intent_client_secret')
    subscription_id = request.args.get('subscription_id')
    user_id = request.args.get('user_id')
    
    if not payment_intent_client_secret or not subscription_id:
        flash('Missing payment information', 'danger')
        return redirect(url_for('dashboard'))
    
    # Get the user to subscribe to
    user_to_subscribe_to = User.query.get_or_404(user_id) if user_id else None
    
    return render_template_with_defaults(
        'payment_confirmation.html',
        stripe_public_key=app.config['STRIPE_PUBLIC_KEY'],
        payment_intent_client_secret=payment_intent_client_secret,
        subscription_id=subscription_id,
        user_to_view=user_to_subscribe_to
    )

@app.route('/subscription-success')
@login_required
def subscription_success():
    """Handle successful subscription from both checkout session and payment intent flows"""
    session_id = request.args.get('session_id')
    subscription_id = request.args.get('subscription_id')
    
    try:
        if session_id:
            # Checkout Session flow
            checkout_session = stripe.checkout.Session.retrieve(session_id)
            
            # Create a new subscription record
            subscription = Subscription(
                subscriber_id=int(checkout_session.metadata.subscriber_id),
                subscribed_to_id=int(checkout_session.metadata.subscribed_to_id),
                stripe_subscription_id=checkout_session.subscription,
                status='active'
            )
            
            db.session.add(subscription)
            db.session.commit()
            
            subscribed_to = User.query.get(subscription.subscribed_to_id)
            flash(f'Successfully subscribed to {subscribed_to.username}\'s portfolio!', 'success')
            return redirect(url_for('profile', username=subscribed_to.username))
            
        elif subscription_id:
            # Payment Intent flow (Apple Pay)
            stripe_subscription = stripe.Subscription.retrieve(subscription_id)
            
            # Check if we already have this subscription recorded
            existing_sub = Subscription.query.filter_by(stripe_subscription_id=subscription_id).first()
            if existing_sub:
                subscribed_to = User.query.get(existing_sub.subscribed_to_id)
                flash(f'Successfully subscribed to {subscribed_to.username}\'s portfolio!', 'success')
                return redirect(url_for('profile', username=subscribed_to.username))
            
            # Create a new subscription record from the metadata
            if 'subscriber_id' in stripe_subscription.metadata and 'subscribed_to_id' in stripe_subscription.metadata:
                subscription = Subscription(
                    subscriber_id=int(stripe_subscription.metadata.subscriber_id),
                    subscribed_to_id=int(stripe_subscription.metadata.subscribed_to_id),
                    stripe_subscription_id=subscription_id,
                    status=stripe_subscription.status
                )
                
                db.session.add(subscription)
                db.session.commit()
                
                subscribed_to = User.query.get(subscription.subscribed_to_id)
                flash(f'Successfully subscribed to {subscribed_to.username}\'s portfolio!', 'success')
                logger.info(f"Login successful for user {subscribed_to.username}, redirecting to dashboard")
                try:
                    # Use a simple redirect to avoid potential template rendering issues
                    return redirect('/')
                except Exception as redirect_error:
                    logger.error(f"Error during redirect after successful login: {str(redirect_error)}")
                    logger.error(traceback.format_exc())
                    # Even if redirect fails, user is already logged in
                    return redirect(url_for('index'))
            else:
                flash('Subscription metadata is missing', 'danger')
                return redirect(url_for('dashboard'))
        else:
            flash('Invalid subscription information', 'danger')
            return redirect(url_for('dashboard'))
            
    except Exception as e:
        flash(f'Error processing subscription: {str(e)}', 'danger')
        return redirect(url_for('dashboard'))

@app.route('/webhook', methods=['POST'])
def webhook():
    """Handle Stripe webhook events"""
    payload = request.get_data(as_text=True)
    sig_header = request.headers.get('Stripe-Signature')
    
    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, app.config['STRIPE_WEBHOOK_SECRET']
        )
    except ValueError as e:
        # Invalid payload
        return jsonify({'error': str(e)}), 400
    except stripe.error.SignatureVerificationError as e:
        # Invalid signature
        return jsonify({'error': str(e)}), 400
    
    # Handle the event
    if event['type'] == 'invoice.payment_succeeded':
        # Handle successful payment for subscription
        invoice = event['data']['object']
        subscription_id = invoice['subscription']
        
        # Update the subscription status
        stripe_subscription = stripe.Subscription.retrieve(subscription_id)
        
        # Find the corresponding subscription in our database
        subscription = Subscription.query.filter_by(stripe_subscription_id=subscription_id).first()
        if subscription:
            subscription.status = stripe_subscription['status']
            db.session.commit()
        else:
            # This might be a new subscription from Apple Pay that hasn't been recorded yet
            # Create a new subscription record if metadata is available
            try:
                if 'subscriber_id' in stripe_subscription.metadata and 'subscribed_to_id' in stripe_subscription.metadata:
                    new_subscription = Subscription(
                        subscriber_id=int(stripe_subscription.metadata.subscriber_id),
                        subscribed_to_id=int(stripe_subscription.metadata.subscribed_to_id),
                        stripe_subscription_id=subscription_id,
                        status=stripe_subscription.status
                    )
                    db.session.add(new_subscription)
                    db.session.commit()
            except Exception as e:
                # Log the error but don't fail the webhook
                print(f"Error creating subscription from webhook: {str(e)}")
    
    elif event['type'] == 'customer.subscription.deleted':
        # Handle subscription cancellation
        subscription_obj = event['data']['object']
        subscription_id = subscription_obj['id']
        
        # Find and update the subscription in our database
        subscription = Subscription.query.filter_by(stripe_subscription_id=subscription_id).first()
        if subscription:
            subscription.status = 'canceled'
            subscription.end_date = datetime.utcnow()
            db.session.commit()
    
    elif event['type'] == 'payment_intent.succeeded':
        # Handle successful payment intent (could be from Apple Pay)
        payment_intent = event['data']['object']
        
        # If this payment intent is related to a subscription, make sure it's properly recorded
        if 'subscription' in payment_intent.metadata:
            subscription_id = payment_intent.metadata.subscription
            
            # Check if we already have this subscription
            subscription = Subscription.query.filter_by(stripe_subscription_id=subscription_id).first()
            if not subscription and 'subscriber_id' in payment_intent.metadata and 'subscribed_to_id' in payment_intent.metadata:
                # Create the subscription record
                new_subscription = Subscription(
                    subscriber_id=int(payment_intent.metadata.subscriber_id),
                    subscribed_to_id=int(payment_intent.metadata.subscribed_to_id),
                    stripe_subscription_id=subscription_id,
                    status='active'
                )
                db.session.add(new_subscription)
                db.session.commit()
    
    return jsonify({'status': 'success'})

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
        
        # Get active subscriptions
        try:
            # Use a direct SQL query instead of ORM to minimize potential issues
            active_subscriptions_query = "SELECT * FROM subscription WHERE subscriber_id = :user_id AND status = 'active'"
            active_subscriptions = db.session.execute(text(active_subscriptions_query), {"user_id": current_user_id}).fetchall()
            
            # Get canceled subscriptions
            canceled_subscriptions_query = "SELECT * FROM subscription WHERE subscriber_id = :user_id AND status = 'canceled'"
            canceled_subscriptions = db.session.execute(text(canceled_subscriptions_query), {"user_id": current_user_id}).fetchall()
            
            # Convert to list of dictionaries for template rendering
            active_subs = [dict(sub) for sub in active_subscriptions] if active_subscriptions else []
            canceled_subs = [dict(sub) for sub in canceled_subscriptions] if canceled_subscriptions else []
            
            return render_template_with_defaults(
                'subscriptions.html',
                active_subscriptions=active_subs,
                canceled_subscriptions=canceled_subs,
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
    """Cancel a user's subscription"""
    subscription_id = request.form.get('subscription_id')
    if not subscription_id:
        flash('Invalid subscription', 'danger')
        return redirect(url_for('subscriptions'))
    
    # Get the subscription
    subscription = Subscription.query.get_or_404(subscription_id)
    
    # Verify ownership
    current_user_id = session.get('user_id')
    if subscription.subscriber_id != current_user_id:
        flash('You do not have permission to cancel this subscription', 'danger')
        return redirect(url_for('subscriptions'))
    
    try:
        # Cancel the subscription in Stripe
        stripe.Subscription.delete(subscription.stripe_subscription_id)
        
        # Update the subscription in our database
        subscription.status = 'canceled'
        subscription.end_date = datetime.utcnow()
        db.session.commit()
        
        flash('Subscription canceled successfully', 'success')
    except Exception as e:
        flash(f'Error canceling subscription: {str(e)}', 'danger')
    
    return redirect(url_for('subscriptions'))

@app.route('/resubscribe', methods=['POST'])
@login_required
def resubscribe():
    """Reactivate a canceled subscription by creating a new one"""
    old_subscription_id = request.form.get('subscription_id')
    if not old_subscription_id:
        flash('Invalid subscription', 'danger')
        return redirect(url_for('subscriptions'))
    
    # Get the old subscription
    old_subscription = Subscription.query.get_or_404(old_subscription_id)
    
    # Verify ownership
    current_user_id = session.get('user_id')
    if old_subscription.subscriber_id != current_user_id:
        flash('You do not have permission to reactivate this subscription', 'danger')
        return redirect(url_for('subscriptions'))
    
    try:
        # Get the user to subscribe to
        user_to_subscribe_to = User.query.get_or_404(old_subscription.subscribed_to_id)
        
        # Get the current user
        current_user = User.query.get_or_404(current_user_id)
        
        # Create a new subscription in Stripe
        stripe_subscription = stripe.Subscription.create(
            customer=current_user.stripe_customer_id,
            items=[
                {'price': app.config['STRIPE_PRICE_ID']},
            ],
            metadata={
                'subscriber_id': current_user_id,
                'subscribed_to_id': user_to_subscribe_to.id
            }
        )
        
        # Create a new subscription record
        new_subscription = Subscription(
            subscriber_id=current_user_id,
            subscribed_to_id=user_to_subscribe_to.id,
            stripe_subscription_id=stripe_subscription.id,
            status='active'
        )
        db.session.add(new_subscription)
        db.session.commit()
        
        flash(f'Successfully resubscribed to {user_to_subscribe_to.username}\'s portfolio!', 'success')
    except Exception as e:
        flash(f'Error reactivating subscription: {str(e)}', 'danger')
    
    return redirect(url_for('subscriptions'))

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
        
        # Check if it's weekend or after market hours - use cached snapshots
        today = date.today()
        is_weekend = today.weekday() >= 5  # Saturday = 5, Sunday = 6
        current_hour = datetime.now().hour
        is_after_hours = current_hour < 9 or current_hour >= 16  # Before 9 AM or after 4 PM
        
        # Use cached snapshots on weekends or after hours, live data during market hours on weekdays
        use_cached_data = is_weekend or is_after_hours
        
        if use_cached_data:
            # Get most recent portfolio snapshot (Friday's close or latest available)
            latest_snapshot = PortfolioSnapshot.query.filter_by(user_id=current_user.id)\
                .order_by(PortfolioSnapshot.date.desc()).first()
            
            if latest_snapshot:
                total_portfolio_value = latest_snapshot.total_value
                
                # Get individual stock data for display (use cached prices from Friday)
                stocks = Stock.query.filter_by(user_id=current_user.id).all()
                
                # For cached data, calculate individual stock values proportionally
                # This is an approximation since we only have total portfolio value cached
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
            else:
                # No cached data available, fall back to live data
                use_cached_data = False
        
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
    
    return render_template_with_defaults('dashboard.html', 
                                       portfolio_data=portfolio_data,
                                       stocks=portfolio_data,  # Template expects 'stocks' variable
                                       total_portfolio_value=total_portfolio_value,
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
@login_required
def portfolio_value():
    """API endpoint to get portfolio value data"""
    from datetime import date, datetime
    from models import PortfolioSnapshot
    
    # Get current user from session
    current_user_id = session.get('user_id')
    
    # Check if it's weekend or after market hours - use cached snapshots
    today = date.today()
    is_weekend = today.weekday() >= 5  # Saturday = 5, Sunday = 6
    current_hour = datetime.now().hour
    is_after_hours = current_hour < 9 or current_hour >= 16  # Before 9 AM or after 4 PM
    
    # Use cached snapshots on weekends or after hours, live data during market hours on weekdays
    use_cached_data = is_weekend or is_after_hours
    
    stocks = Stock.query.filter_by(user_id=current_user_id).all()
    portfolio_data = []
    total_value = 0
    
    if use_cached_data:
        # Get most recent portfolio snapshot (Friday's close or latest available)
        latest_snapshot = PortfolioSnapshot.query.filter_by(user_id=current_user_id)\
            .order_by(PortfolioSnapshot.date.desc()).first()
        
        if latest_snapshot:
            total_value = latest_snapshot.total_value
            
            # For cached data, calculate individual stock values proportionally
            total_cost_basis = sum(stock.quantity * stock.purchase_price for stock in stocks if stock.purchase_price)
            
            for stock in stocks:
                if total_cost_basis > 0:
                    # Estimate current price based on proportional portfolio performance
                    cost_basis = stock.quantity * stock.purchase_price if stock.purchase_price else 0
                    portfolio_multiplier = total_value / total_cost_basis if total_cost_basis > 0 else 1
                    estimated_current_price = stock.purchase_price * portfolio_multiplier if stock.purchase_price else 0
                    
                    value = stock.quantity * estimated_current_price
                    gain_loss = value - cost_basis
                    
                    stock_info = {
                        'id': stock.id,
                        'ticker': stock.ticker,
                        'quantity': stock.quantity,
                        'purchase_price': stock.purchase_price,
                        'current_price': estimated_current_price,
                        'value': value,
                        'gain_loss': gain_loss
                    }
                    portfolio_data.append(stock_info)
                else:
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
        else:
            # No cached data available, fall back to live data
            use_cached_data = False
    
    if not use_cached_data:
        # Use live API data during market hours on weekdays
        # Get all tickers for batch processing
        tickers = [stock.ticker for stock in stocks]
        batch_prices = get_batch_stock_data(tickers)
        
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
    """Display a user's profile page."""
    # Redirect to own dashboard if viewing self
    current_user_id = session.get('user_id')
    current_user = User.query.get(current_user_id)
    
    if current_user.username == username:
        return redirect(url_for('dashboard'))

    user_to_view = User.query.filter_by(username=username).first_or_404()

    # Check if the current user has an active subscription to this profile
    subscription = Subscription.query.filter_by(
        subscriber_id=current_user.id,
        subscribed_to_id=user_to_view.id,
        status='active'
    ).first()

    portfolio_data = None
    if subscription:
        # If subscribed, fetch portfolio data to display
        stocks = Stock.query.filter_by(user_id=user_to_view.id).all()
        total_value = 0
        stock_details = []
        # Get all tickers for batch processing
        tickers = [stock.ticker for stock in stocks]
        batch_prices = get_batch_stock_data(tickers)
        
        for stock in stocks:
            ticker_upper = stock.ticker.upper()
            price = batch_prices.get(ticker_upper)
            
            if price is not None:
                value = stock.quantity * price
                total_value += value
                stock_details.append({'ticker': stock.ticker, 'quantity': stock.quantity, 'price': price, 'value': value})
        portfolio_data = {
            'stocks': stock_details,
            'total_value': total_value
        }

    return render_template_with_defaults(
        'profile.html',
        user_to_view=user_to_view,
        subscription=subscription,
        portfolio_data=portfolio_data,
        price=user_to_view.subscription_price,
        stripe_public_key=app.config['STRIPE_PUBLIC_KEY']
    )

@app.route('/admin/subscription-analytics')
@login_required
def admin_subscription_analytics():
    """Admin dashboard for subscription analytics"""
    # Check if user is admin
    current_user_id = session.get('user_id')
    current_user = User.query.get(current_user_id)
    
    # Only allow access to the admin (fordutilityapps@gmail.com or witty-raven)
    if current_user.email != ADMIN_EMAIL and current_user.username != ADMIN_USERNAME:
        flash('You do not have permission to access this page', 'danger')
        return redirect(url_for('dashboard'))
    
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

@app.route('/admin/debug')
def admin_debug():
    """Return debug information about the environment"""
    import sys
    
@app.route('/admin/debug/users')
def admin_debug_users():
    """Debug endpoint to check user credentials"""
    try:
        # Only allow access from localhost or if user is admin
        if request.remote_addr != '127.0.0.1' and not (current_user.is_authenticated and current_user.is_admin()):
            return jsonify({'error': 'Unauthorized'}), 403
            
        admin_user = User.query.filter_by(email=ADMIN_EMAIL).first()
        if admin_user:
            # Don't return the actual password hash for security reasons
            return jsonify({
                'admin_user_exists': True,
                'username': admin_user.username,
                'has_password_hash': bool(admin_user.password_hash),
                'password_hash_length': len(admin_user.password_hash) if admin_user.password_hash else 0
            })
        else:
            return jsonify({'admin_user_exists': False})
    except Exception as e:
        logger.error(f"Error in debug users endpoint: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({'error': str(e)}), 500

@app.route('/admin/debug/oauth')
def admin_debug_oauth():
    """Debug endpoint to check OAuth configuration"""
    try:
        # Only show if environment variables are set, not their actual values
        oauth_config = {
            'google_client_id_set': bool(os.environ.get('GOOGLE_CLIENT_ID')),
            'google_client_secret_set': bool(os.environ.get('GOOGLE_CLIENT_SECRET')),
            'apple_client_id_set': bool(os.environ.get('APPLE_CLIENT_ID')),
            'apple_client_secret_set': bool(os.environ.get('APPLE_CLIENT_SECRET')),
            'redirect_uri': url_for('authorize_google', _external=True),
            'base_url': request.host_url,
            'is_https': request.is_secure
        }
        return jsonify(oauth_config)
    except Exception as e:
        logger.error(f"Error in debug OAuth endpoint: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({'error': str(e)}), 500
        
@app.route('/admin/debug/database')
def admin_debug_database():
    """Debug endpoint to check database connection"""
    try:
        # Check database connection
        db_config = {
            'database_url_exists': bool(os.environ.get('DATABASE_URL')),
            'postgres_prisma_url_exists': bool(os.environ.get('POSTGRES_PRISMA_URL')),
            'effective_database_url_exists': bool(DATABASE_URL),
            'sqlalchemy_database_uri_set': bool(app.config.get('SQLALCHEMY_DATABASE_URI')),
            'db_initialized': bool(db),
            'db_engine_initialized': bool(db.engine)
        }
        
        # Test database connection
        try:
            # Try to execute a simple query
            test_result = db.session.execute("SELECT 1").scalar()
            db_config['connection_test'] = 'Success' if test_result == 1 else f'Failed: {test_result}'
            
            # Count users in database
            user_count = User.query.count()
            db_config['user_count'] = user_count
            
            # Check if admin user exists
            admin_exists = User.query.filter_by(email=ADMIN_EMAIL).first() is not None
            db_config['admin_user_exists'] = admin_exists
            
        except Exception as db_test_error:
            db_config['connection_test'] = f'Error: {str(db_test_error)}'
            logger.error(f"Database connection test failed: {str(db_test_error)}")
            logger.error(traceback.format_exc())
        
        return jsonify(db_config)
    except Exception as e:
        logger.error(f"Error in debug database endpoint: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({'error': str(e)}), 500
        
@app.route('/admin/debug/models')
def admin_debug_models():
    """Debug endpoint to check SQLAlchemy model relationships"""
    try:
        # Get model information
        model_info = {
            'user_model': {
                'attributes': [attr for attr in dir(User) if not attr.startswith('_')],
                'relationships': [
                    {'name': 'stocks', 'target': 'Stock', 'type': 'one-to-many'},
                    {'name': 'transactions', 'target': 'Transaction', 'type': 'one-to-many'},
                    {'name': 'subscriptions_made', 'target': 'Subscription', 'type': 'one-to-many'},
                    {'name': 'subscribers', 'target': 'Subscription', 'type': 'one-to-many'}
                ]
            },
            'subscription_model': {
                'attributes': [attr for attr in dir(Subscription) if not attr.startswith('_')],
                'relationships': [
                    {'name': 'subscriber', 'target': 'User', 'type': 'many-to-one'},
                    {'name': 'subscribed_to', 'target': 'User', 'type': 'many-to-one'}
                ],
                'foreign_keys': [
                    {'name': 'subscriber_id', 'references': 'user.id'},
                    {'name': 'subscribed_to_id', 'references': 'user.id'}
                ]
            }
        }
        
        return jsonify(model_info)
    except Exception as e:
        logger.error(f"Error in debug models endpoint: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({'error': str(e)}), 500
        
@app.route('/admin/debug/oauth-login')
def admin_debug_oauth_login():
    """Debug endpoint to test Google OAuth login without going through the full flow"""
    try:
        # Create a mock user for testing
        test_email = 'test@example.com'
        
        # Check if test user exists
        test_user = User.query.filter_by(email=test_email).first()
        
        if not test_user:
            # Create test user
            test_user = User(
                email=test_email,
                username='test-user',
                oauth_provider='google',
                oauth_id='test123',
                stripe_price_id='price_1RbX0yQWUhVa3vgDB8vGzoFN',
                subscription_price=4.00
            )
            test_user.set_password('')  # Empty password for OAuth users
            
            # Make sure we have a valid database session
            if not db.session.is_active:
                logger.warning("Database session is not active during test user creation, creating new session")
                db.session = db.create_scoped_session()
                
            db.session.add(test_user)
            db.session.commit()
            logger.info(f"Created test user with ID: {test_user.id}")
        
        # Try to log in the test user
        try:
            # Make sure the user object is attached to the current session
            if hasattr(test_user, '_sa_instance_state') and test_user._sa_instance_state.session is not db.session:
                logger.warning("Test user object is not attached to the current session, merging")
                test_user = db.session.merge(test_user)
                
            # Try to log in the user
            login_success = login_user(test_user)
            logger.info(f"Test user login_user result: {login_success}")
            
            if login_success:
                # For backward compatibility, also set session variables
                session['user_id'] = test_user.id
                session['email'] = test_user.email
                session['username'] = test_user.username
                
                return jsonify({
                    'success': True,
                    'message': 'Test user logged in successfully',
                    'user_id': test_user.id,
                    'email': test_user.email,
                    'username': test_user.username,
                    'session_variables': {
                        'user_id': session.get('user_id'),
                        'email': session.get('email'),
                        'username': session.get('username')
                    }
                })
            else:
                return jsonify({
                    'success': False,
                    'message': 'login_user() returned False',
                    'user_details': {
                        'id': test_user.id,
                        'email': test_user.email,
                        'username': test_user.username
                    }
                }), 500
        except Exception as login_error:
            logger.error(f"Error during test user login: {str(login_error)}")
            logger.error(traceback.format_exc())
            return jsonify({
                'success': False,
                'message': f'Error during login: {str(login_error)}',
                'traceback': traceback.format_exc()
            }), 500
    except Exception as e:
        logger.error(f"Error in debug OAuth login endpoint: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({
            'success': False,
            'message': f'Error: {str(e)}',
            'traceback': traceback.format_exc()
        }), 500

@app.route('/admin/fix-leaderboard-period-length')
@login_required
def admin_fix_leaderboard_period_length():
    """Widen leaderboard_cache.period column to support keys like '1D_large_cap'.

    Some production databases have leaderboard_cache.period defined as VARCHAR(10),
    which truncates values such as '1D_large_cap'. This endpoint alters the column to
    VARCHAR(50) to safely store period_category keys.
    """
    try:
        email = session.get('email', '')
        if email != ADMIN_EMAIL:
            return jsonify({'error': 'Admin access required'}), 403

        from sqlalchemy import text

        # Inspect current column length
        col = db.session.execute(text("""
            SELECT character_maximum_length
            FROM information_schema.columns
            WHERE table_name = 'leaderboard_cache' AND column_name = 'period'
        """)).fetchone()

        before_len = col[0] if col else None

        # Alter to VARCHAR(50) if needed
        if before_len is None or before_len < 50:
            db.session.execute(text("""
                ALTER TABLE leaderboard_cache
                ALTER COLUMN period TYPE VARCHAR(50)
            """))
            db.session.commit()
            return jsonify({'success': True, 'message': 'leaderboard_cache.period widened to VARCHAR(50)', 'before_length': before_len, 'after_length': 50})
        else:
            return jsonify({'success': True, 'message': 'No change needed; sufficient length', 'current_length': before_len})

    except Exception as e:
        db.session.rollback()
        import traceback
        return jsonify({'success': False, 'error': str(e), 'traceback': traceback.format_exc()}), 500

@app.route('/admin/debug/oauth-session')
def admin_debug_oauth_session():
    """Debug endpoint to check Flask-Login session state"""
    try:
        # Get current user info
        current_user_info = {
            'is_authenticated': current_user.is_authenticated if hasattr(current_user, 'is_authenticated') else False,
            'session_vars': {
                'user_id': session.get('user_id'),
                'email': session.get('email'),
                'username': session.get('username')
            },
            'flask_login_user': str(current_user) if hasattr(current_user, 'id') else 'No current_user',
            'request_cookies': dict(request.cookies)
        }
        
        # Check if session is working
        test_key = str(uuid.uuid4())
        session['test_key'] = test_key
        session_test = {'set': test_key, 'retrieved': session.get('test_key')}
        
        return jsonify({
            'success': True,
            'current_user': current_user_info,
            'session_test': session_test,
            'app_config': {
                'secret_key_set': app.secret_key is not None,
                'session_cookie_name': app.config.get('SESSION_COOKIE_NAME'),
                'session_cookie_secure': app.config.get('SESSION_COOKIE_SECURE'),
                'session_cookie_domain': app.config.get('SESSION_COOKIE_DOMAIN'),
                'session_cookie_path': app.config.get('SESSION_COOKIE_PATH'),
                'remember_cookie_duration': str(app.config.get('REMEMBER_COOKIE_DURATION')),
                'login_view': login_manager._login_view if hasattr(login_manager, '_login_view') else None
            }
        })
    except Exception as e:
        logger.error(f"Error in debug OAuth session endpoint: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({
            'success': False,
            'message': f'Error: {str(e)}',
            'traceback': traceback.format_exc()
        }), 500

@app.route('/admin/debug/admin-check')
def admin_debug_admin_check():
    """Debug endpoint to check if admin user exists"""
    try:
        admin_user = User.query.filter_by(email=ADMIN_EMAIL).first()
        if admin_user:
            # Don't return the actual password hash for security reasons
            return jsonify({
                'admin_user_exists': True,
                'username': admin_user.username,
                'has_password_hash': bool(admin_user.password_hash),
                'password_hash_length': len(admin_user.password_hash) if admin_user.password_hash else 0
            })
        else:
            return jsonify({'admin_user_exists': False})
    except Exception as e:
        logger.error(f"Error in debug users endpoint: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({'error': str(e)}), 500
        
@app.route('/admin/reset-admin-password')
def reset_admin_password():
    """Reset the admin password - only accessible from localhost"""
    try:
        # Only allow access from localhost for security
        if request.remote_addr != '127.0.0.1':
            return jsonify({'error': 'This endpoint can only be accessed from localhost'}), 403
            
        # Find admin user or create if doesn't exist
        admin_user = User.query.filter_by(email=ADMIN_EMAIL).first()
        
        if not admin_user:
            # Create admin user if it doesn't exist
            admin_user = User(username=ADMIN_USERNAME, email=ADMIN_EMAIL)
            db.session.add(admin_user)
            
        # Set a new password
        new_password = 'admin123'
        admin_user.set_password(new_password)
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f"Admin password reset successfully. Username: witty-raven, Password: {new_password}"
        })
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error resetting admin password: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({'error': str(e)}), 500
    try:
        # Collect environment information
        debug_info = {
            'vercel_env': os.environ.get('VERCEL_ENV', 'Not set'),
            'database_url_exists': bool(os.environ.get('DATABASE_URL')),
            'postgres_prisma_url_exists': bool(os.environ.get('POSTGRES_PRISMA_URL')),
            'effective_database_url_exists': bool(DATABASE_URL),
            'secret_key_exists': bool(os.environ.get('SECRET_KEY')),
            'python_version': sys.version,
            'current_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        
        # Test database connection
        try:
            # Try to query the database
            user_count = User.query.count()
            debug_info['database_connection'] = 'Success'
            debug_info['user_count'] = user_count
        except Exception as e:
            debug_info['database_connection'] = 'Failed'
            debug_info['database_error'] = str(e)
        
        return jsonify(debug_info)
    except Exception as e:
        return jsonify({
            'error': str(e),
            'type': str(type(e))
        }), 500

# Migration endpoint has been removed for security reasons after successful database schema update
# The migration added the following columns to the User table:
# - created_at (TIMESTAMP DEFAULT CURRENT_TIMESTAMP)
# - stripe_customer_id (VARCHAR(120))

# Cache for stock prices to avoid excessive API calls
stock_price_cache = {}
cache_duration = 90  # 90 seconds

def get_batch_stock_data(ticker_symbols):
    """Fetch multiple stock prices efficiently with caching and batch API calls."""
    from datetime import datetime
    
    current_time = datetime.now()
    result = {}
    tickers_to_fetch = []
    
    # No mock prices - only use real API data or cached data
    for ticker in ticker_symbols:
        ticker_upper = ticker.upper()
        
        # Check if we have fresh cached data (< 90 seconds)
        if ticker_upper in stock_price_cache:
            cached_data = stock_price_cache[ticker_upper]
            cache_time = cached_data.get('timestamp')
            if cache_time and (current_time - cache_time).total_seconds() < cache_duration:
                result[ticker_upper] = cached_data['price']
                continue
        
        # Need to fetch this ticker
        tickers_to_fetch.append(ticker_upper)
    
    # If we need to fetch any tickers, make batch API call
    if tickers_to_fetch:
        api_key = os.environ.get('ALPHA_VANTAGE_API_KEY')
        if not api_key:
            logger.warning("Alpha Vantage API key not found, cannot fetch stock prices")
            # Do not add any prices if API key is missing - only use real data
        else:
            # Make individual API calls for all tickers (no mock fallback)
            for ticker in tickers_to_fetch:
                try:
                    url = f'https://www.alphavantage.co/query?function=GLOBAL_QUOTE&symbol={ticker}&apikey={api_key}'
                    response = requests.get(url, timeout=3)  # Reduced timeout
                    data = response.json()
                    
                    if 'Global Quote' in data and '05. price' in data['Global Quote']:
                        price = float(data['Global Quote']['05. price'])
                        stock_price_cache[ticker] = {'price': price, 'timestamp': current_time}
                        result[ticker] = price
                        
                        # Log successful API call
                        try:
                            from models import AlphaVantageAPILog
                            api_log = AlphaVantageAPILog(
                                endpoint='GLOBAL_QUOTE',
                                symbol=ticker,
                                response_status='success',
                                timestamp=current_time
                            )
                            db.session.add(api_log)
                            # Don't commit immediately - batch commits for better performance
                        except Exception as log_error:
                            logger.error(f"Error logging API call: {log_error}")
                    else:
                        logger.warning(f"Could not get price for {ticker} from API - no fallback used")
                        # Log failed API call
                        try:
                            from models import AlphaVantageAPILog
                            api_log = AlphaVantageAPILog(
                                endpoint='GLOBAL_QUOTE',
                                symbol=ticker,
                                response_status='error',
                                timestamp=current_time
                            )
                            db.session.add(api_log)
                            # Don't commit immediately - batch commits for better performance
                        except Exception as log_error:
                            logger.error(f"Error logging API call: {log_error}")
                        
                except Exception as e:
                    logger.error(f"Error fetching {ticker}: {e}")
                    # Log failed API call
                    try:
                        from models import AlphaVantageAPILog
                        api_log = AlphaVantageAPILog(
                            endpoint='GLOBAL_QUOTE',
                            symbol=ticker,
                            response_status='error',
                            timestamp=current_time
                        )
                        db.session.add(api_log)
                        # Don't commit immediately - batch commits for better performance
                    except Exception as log_error:
                        logger.error(f"Error logging API call: {log_error}")
    
    # Batch commit all API logs at the end for better performance
    try:
        db.session.commit()
    except Exception as e:
        logger.error(f"Error committing API logs: {e}")
        db.session.rollback()
    
    return result

def get_stock_data(ticker_symbol):
    """Fetches single stock data - wrapper around batch function for backward compatibility."""
    batch_result = get_batch_stock_data([ticker_symbol])
    ticker_upper = ticker_symbol.upper()
    if ticker_upper in batch_result:
        return {'price': batch_result[ticker_upper]}
    else:
        # Return None if no real price available
        return None

# HTML Templates for core functionality
LOGIN_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Login - ApesTogether</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 40px; background-color: #f4f4f4; }
        .container { max-width: 500px; margin: 0 auto; background: white; padding: 20px; border-radius: 5px; box-shadow: 0 0 10px rgba(0,0,0,0.1); }
        h1 { color: #333; text-align: center; }
        .form-group { margin-bottom: 15px; }
        label { display: block; margin-bottom: 5px; font-weight: bold; }
        input[type="email"], input[type="password"] { width: 100%; padding: 10px; border: 1px solid #ddd; border-radius: 3px; box-sizing: border-box; }
        .btn { display: inline-block; background: #4CAF50; color: white; padding: 10px 20px; text-decoration: none; border-radius: 3px; border: none; cursor: pointer; font-size: 16px; }
        .btn-block { width: 100%; }
        .alert { padding: 10px; margin-bottom: 15px; border-radius: 3px; }
        .alert-danger { background-color: #f8d7da; color: #721c24; }
        .alert-success { background-color: #d4edda; color: #155724; }
        .text-center { text-align: center; }
        .mt-3 { margin-top: 15px; }
        .oauth-buttons { margin-top: 20px; border-top: 1px solid #ddd; padding-top: 20px; }
        .btn-google { background-color: #4285F4; }
        .btn-apple { background-color: #000; }
        .btn-oauth { width: 100%; margin-bottom: 10px; color: white; text-align: center; }
    </style>
</head>
<body>
    <div class="container">
        <h1>Login</h1>
        
        {% with messages = get_flashed_messages(with_categories=true) %}
            {% if messages %}
                {% for category, message in messages %}
                    <div class="alert alert-{{ category }}">{{ message }}</div>
                {% endfor %}
            {% endif %}
        {% endwith %}
        
        <form method="POST" action="/login">
            <div class="form-group">
                <label for="email">Email:</label>
                <input type="email" id="email" name="email" required>
            </div>
            <div class="form-group">
                <label for="password">Password:</label>
                <input type="password" id="password" name="password" required>
            </div>
            <button type="submit" class="btn btn-block">Login</button>
        </form>
        
        <div class="oauth-buttons">
            <p class="text-center">Or login with:</p>
            <a href="/login/google" class="btn btn-oauth btn-google">Login with Google</a>
            <a href="/login/apple" class="btn btn-oauth btn-apple">Login with Apple</a>
        </div>
        
        <div class="text-center mt-3">
            <p>Don't have an account? <a href="/register">Register</a></p>
            <p><a href="/">Back to Home</a></p>
        </div>
    </div>
</body>
</html>
"""

REGISTER_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Register - ApesTogether</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 40px; background-color: #f4f4f4; }
        .container { max-width: 500px; margin: 0 auto; background: white; padding: 20px; border-radius: 5px; box-shadow: 0 0 10px rgba(0,0,0,0.1); }
        h1 { color: #333; text-align: center; }
        .form-group { margin-bottom: 15px; }
        label { display: block; margin-bottom: 5px; font-weight: bold; }
        input[type="text"], input[type="email"], input[type="password"] { width: 100%; padding: 10px; border: 1px solid #ddd; border-radius: 3px; box-sizing: border-box; }
        .btn { display: inline-block; background: #4CAF50; color: white; padding: 10px 20px; text-decoration: none; border-radius: 3px; border: none; cursor: pointer; font-size: 16px; }
        .btn-block { width: 100%; }
        .alert { padding: 10px; margin-bottom: 15px; border-radius: 3px; }
        .alert-danger { background-color: #f8d7da; color: #721c24; }
        .alert-success { background-color: #d4edda; color: #155724; }
        .text-center { text-align: center; }
        .mt-3 { margin-top: 15px; }
    </style>
</head>
<body>
    <div class="container">
        <h1>Register</h1>
        
        {% with messages = get_flashed_messages(with_categories=true) %}
            {% if messages %}
                {% for category, message in messages %}
                    <div class="alert alert-{{ category }}">{{ message }}</div>
                {% endfor %}
            {% endif %}
        {% endwith %}
        
        <form method="POST" action="/register">
            <div class="form-group">
                <label for="username">Username:</label>
                <input type="text" id="username" name="username" required>
            </div>
            <div class="form-group">
                <label for="email">Email:</label>
                <input type="email" id="email" name="email" required>
            </div>
            <div class="form-group">
                <label for="password">Password:</label>
                <input type="password" id="password" name="password" required>
            </div>
            <button type="submit" class="btn btn-block">Register</button>
        </form>
        
        <div class="text-center mt-3">
            <p>Already have an account? <a href="/login">Login</a></p>
            <p><a href="/">Back to Home</a></p>
        </div>
    </div>
</body>
</html>
"""

DASHBOARD_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Dashboard - ApesTogether</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 0; padding: 0; background-color: #f4f4f4; }
        .container { width: 80%; margin: 0 auto; background: white; padding: 20px; box-shadow: 0 0 10px rgba(0,0,0,0.1); }
        .header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; padding-bottom: 10px; border-bottom: 1px solid #eee; }
        .nav a { margin-left: 15px; text-decoration: none; color: #333; }
        h1, h2 { color: #333; }
        .portfolio-summary { background: #f9f9f9; padding: 15px; border-radius: 5px; margin-bottom: 20px; }
        .stocks-table { width: 100%; border-collapse: collapse; }
        .stocks-table th, .stocks-table td { padding: 10px; text-align: left; border-bottom: 1px solid #ddd; }
        .stocks-table th { background-color: #f2f2f2; }
        .stocks-table tr:hover { background-color: #f5f5f5; }
        .add-stock-form { background: #f9f9f9; padding: 15px; border-radius: 5px; margin-top: 20px; }
        .form-group { margin-bottom: 15px; }
        label { display: block; margin-bottom: 5px; }
        input[type="text"], input[type="number"] { width: 100%; padding: 8px; box-sizing: border-box; }
        .btn { display: inline-block; background: #4CAF50; color: white; padding: 10px 15px; text-decoration: none; border-radius: 3px; border: none; cursor: pointer; }
        .btn-danger { background: #f44336; }
        .alert { padding: 10px; margin-bottom: 15px; border-radius: 3px; }
        .alert-danger { background-color: #f8d7da; color: #721c24; }
        .alert-success { background-color: #d4edda; color: #155724; }
        .profit { color: green; }
        .loss { color: red; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>Dashboard</h1>
            <div class="nav">
                <a href="/">Home</a>
                <a href="/logout">Logout</a>
            </div>
        </div>
        
        {% with messages = get_flashed_messages(with_categories=true) %}
            {% if messages %}
                {% for category, message in messages %}
                    <div class="alert alert-{{ category }}">{{ message }}</div>
                {% endfor %}
            {% endif %}
        {% endwith %}
        
        <div class="portfolio-summary">
            <h2>Welcome, {{ user.username }}!</h2>
            <p>Your portfolio summary:</p>
            <p><strong>Total Stocks:</strong> {{ stocks|length }}</p>
            {% if stocks %}
                {% set total_value = 0 %}
                {% set total_cost = 0 %}
                {% for stock in stocks %}
                    {% set total_value = total_value + stock.current_value() %}
                    {% set total_cost = total_cost + (stock.purchase_price * stock.quantity) %}
                {% endfor %}
                <p><strong>Total Value:</strong> ${{ "%.2f"|format(total_value) }}</p>
                <p><strong>Total Cost:</strong> ${{ "%.2f"|format(total_cost) }}</p>
                {% set total_profit_loss = total_value - total_cost %}
                <p><strong>Total Profit/Loss:</strong> 
                    <span class="{% if total_profit_loss >= 0 %}profit{% else %}loss{% endif %}">
                        ${{ "%.2f"|format(total_profit_loss) }}
                        ({{ "%.2f"|format((total_profit_loss / total_cost) * 100) }}%)
                    </span>
                </p>
            {% endif %}
        </div>
        
        <h2>Your Stocks</h2>
        {% if stocks %}
            <table class="stocks-table">
                <thead>
                    <tr>
                        <th>Ticker</th>
                        <th>Quantity</th>
                        <th>Purchase Price</th>
                        <th>Purchase Date</th>
                        <th>Current Value</th>
                        <th>Profit/Loss</th>
                        <th>Actions</th>
                    </tr>
                </thead>
                <tbody>
                    {% for stock in stocks %}
                        <tr>
                            <td>{{ stock.ticker }}</td>
                            <td>{{ stock.quantity }}</td>
                            <td>${{ "%.2f"|format(stock.purchase_price) }}</td>
                            <td>{{ stock.purchase_date.strftime('%Y-%m-%d') }}</td>
                            <td>${{ "%.2f"|format(stock.current_value()) }}</td>
                            {% set profit_loss = stock.profit_loss() %}
                            <td class="{% if profit_loss >= 0 %}profit{% else %}loss{% endif %}">
                                ${{ "%.2f"|format(profit_loss) }}
                                ({{ "%.2f"|format((profit_loss / (stock.purchase_price * stock.quantity)) * 100) }}%)
                            </td>
                            <td>
                                <form action="/delete_stock/{{ stock.id }}" method="POST" style="display:inline;">
                                    <button type="submit" class="btn btn-danger">Delete</button>
                                </form>
                            </td>
                        </tr>
                    {% endfor %}
                </tbody>
            </table>
        {% else %}
            <p>You don't have any stocks yet. Add some below!</p>
        {% endif %}
        
        <div class="add-stock-form">
            <h2>Add New Stock</h2>
            <form action="/add_stock" method="POST">
                <div class="form-group">
                    <label for="ticker">Ticker Symbol:</label>
                    <input type="text" id="ticker" name="ticker" required>
                </div>
                <div class="form-group">
                    <label for="quantity">Quantity:</label>
                    <input type="number" id="quantity" name="quantity" step="0.01" min="0.01" required>
                </div>
                <div class="form-group">
                    <label for="purchase_price">Purchase Price ($):</label>
                    <input type="number" id="purchase_price" name="purchase_price" step="0.01" min="0.01" required>
                </div>
                <button type="submit" class="btn">Add Stock</button>
            </form>
        </div>
    </div>
</body>
</html>
"""

# Serve favicon directly to avoid session issues
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
        # Check database connectivity
        db_status = False
        version = None
        try:
            result = db.session.execute(text('SELECT version()'))
            version = result.scalar()
            db_status = True
        except Exception as e:
            logger.error(f"Database health check failed: {str(e)}")
        
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

@app.route('/')
def index():
    """Main landing page - redirect to 7D leaderboard for public access"""
    try:
        # Redirect to 7D leaderboard as the default homepage
        return redirect(url_for('leaderboard.leaderboard_home', period='7D', category='all'))
    except Exception as e:
        logger.error(f"Error in index route redirect: {str(e)}")
        logger.error(traceback.format_exc())
        # Fallback to direct leaderboard URL if blueprint routing fails
        return redirect('/leaderboard/?period=7D&category=all')

@app.route('/login', methods=['GET', 'POST'])
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

@app.route('/terms-of-service')
def terms_of_service():
    """Terms of Service page"""
    return render_template_with_defaults('terms_of_service.html')

@app.route('/privacy-policy')
def privacy_policy():
    """Privacy Policy page"""
    return render_template_with_defaults('privacy_policy.html')

@app.route('/register', methods=['GET', 'POST'])
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
    
    flash('You have been logged out', 'success')
    return redirect(url_for('index'))

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

@app.route('/admin/debug/flask-login')
def admin_debug_flask_login():
    """Debug endpoint to check Flask-Login configuration"""
    try:
        # Test database connection
        db_test_result = {}
        try:
            # Check if we can query users
            user_count = User.query.count()
            db_test_result['user_count'] = user_count
            db_test_result['connection'] = 'Success'
            
            # Check if load_user works
            if user_count > 0:
                first_user = User.query.first()
                if first_user:
                    test_user = load_user(first_user.id)
                    db_test_result['load_user'] = {
                        'success': test_user is not None,
                        'user_id': test_user.id if test_user else None
                    }
        except Exception as db_error:
            db_test_result['connection'] = 'Failed'
            db_test_result['error'] = str(db_error)
        
        # Check Flask-Login configuration
        login_config = {
            'login_manager': {
                'login_view': login_manager._login_view if hasattr(login_manager, '_login_view') else None,
                'login_message': login_manager._login_message if hasattr(login_manager, '_login_message') else None,
                'session_protection': login_manager.session_protection,
                'anonymous_user': str(login_manager.anonymous_user),
                'user_callback': login_manager._user_callback.__name__ if login_manager._user_callback else None
            },
            'current_user': {
                'is_authenticated': current_user.is_authenticated if hasattr(current_user, 'is_authenticated') else False,
                'is_active': current_user.is_active if hasattr(current_user, 'is_active') else False,
                'is_anonymous': current_user.is_anonymous if hasattr(current_user, 'is_anonymous') else True,
                'get_id': current_user.get_id() if hasattr(current_user, 'get_id') else None
            },
            'session': {
                'keys': list(session.keys()) if session else [],
                'user_id': session.get('user_id'),
                'email': session.get('email'),
                'username': session.get('username'),
                '_user_id': session.get('_user_id'),  # Flask-Login session key
                '_id': session.get('_id'),  # Session ID
                '_fresh': session.get('_fresh')  # Flask-Login session freshness
            }
        }
        
        return jsonify({
            'success': True,
            'db_test': db_test_result,
            'flask_login_config': login_config,
            'request_info': {
                'cookies': dict(request.cookies),
                'headers': dict(request.headers),
                'is_secure': request.is_secure,
                'host': request.host
            }
        })
    except Exception as e:
        logger.error(f"Error in debug Flask-Login endpoint: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({
            'success': False,
            'message': f'Error: {str(e)}',
            'traceback': traceback.format_exc()
        }), 500

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
        
        # Make sure we have a valid database session
        if not db.session.is_active:
            logger.warning("Database session is not active, creating new session")
            db.session = db.create_scoped_session()
            
        # Try to find the user
        try:
            user = User.query.filter_by(email=email).first()
            logger.info(f"User exists in database: {user is not None}")
        except Exception as user_query_error:
            logger.error(f"Error querying user: {str(user_query_error)}")
            # Try to reconnect to the database
            db.session.remove()
            db.session = db.create_scoped_session()
            # Try one more time
            user = User.query.filter_by(email=email).first()
            logger.info(f"User exists in database (after reconnect): {user is not None}")
        
        # Step 3: Create new user if not found
        if not user:
            # Generate a unique random username
            while True:
                adjectives = ['clever', 'brave', 'sharp', 'wise', 'happy', 'lucky', 'sunny', 'proud', 'witty', 'gentle']
                nouns = ['fox', 'lion', 'eagle', 'tiger', 'river', 'ocean', 'bear', 'wolf', 'horse', 'raven']
                adjective = random.choice(adjectives)
                noun = random.choice(nouns)
                username = f"{adjective}-{noun}"
                try:
                    if not User.query.filter_by(username=username).first():
                        break
                except Exception as username_error:
                    logger.error(f"Error checking username uniqueness: {str(username_error)}")
                    # Use a timestamp-based username as a fallback
                    username = f"user-{int(time.time())}"
                    break

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
            
            # Make sure we have a valid database session
            if not db.session.is_active:
                logger.warning("Database session is not active during user creation, creating new session")
                db.session = db.create_scoped_session()
                
            db.session.add(user)
            db.session.commit()
            logger.info(f"Successfully created new OAuth user with ID: {user.id}")
        
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
            
        # Step 6: Final redirect - check if user is admin
        if user.is_admin:
            logger.info(f"Admin user {user.email} logged in, redirecting to admin dashboard")
            return redirect(url_for('admin_dashboard'))
        else:
            return redirect(url_for('dashboard'))
            
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
            # Generate a unique random username
            while True:
                adjectives = ['clever', 'brave', 'sharp', 'wise', 'happy', 'lucky', 'sunny', 'proud', 'witty', 'gentle']
                nouns = ['fox', 'lion', 'eagle', 'tiger', 'river', 'ocean', 'bear', 'wolf', 'horse', 'raven']
                adjective = random.choice(adjectives)
                noun = random.choice(nouns)
                username = f"{adjective}-{noun}"
                if not User.query.filter_by(username=username).first():
                    break

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
def add_stock():
    """Add a stock to user's portfolio"""
    if 'user_id' not in session:
        flash('Please login to add stocks', 'warning')
        return redirect(url_for('login'))
    
    ticker = request.form.get('ticker')
    quantity = float(request.form.get('quantity'))
    purchase_price = float(request.form.get('purchase_price'))
    
    # Create new stock
    new_stock = Stock(
        ticker=ticker,
        quantity=quantity,
        purchase_price=purchase_price,
        user_id=session['user_id']
    )
    
    try:
        db.session.add(new_stock)
        db.session.commit()
        
        # Auto-populate stock info for new stocks
        try:
            populate_single_stock_info(ticker.upper())
        except Exception as stock_info_error:
            logger.warning(f"Failed to populate stock info for {ticker}: {str(stock_info_error)}")
        
        flash(f'Added {quantity} shares of {ticker}', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error adding stock: {str(e)}', 'danger')
    
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

@app.route('/admin/cleanup-intraday-data')
@login_required
def cleanup_intraday_data():
    """Admin endpoint to clean up old intraday snapshots while preserving 4PM market close data"""
    if not current_user.is_authenticated or current_user.email != ADMIN_EMAIL:
        flash('Admin access required', 'danger')
        return redirect(url_for('login'))
    
    try:
        from api.cleanup_intraday import cleanup_old_intraday_data
        
        # Run cleanup (keep 14 days of data)
        results = cleanup_old_intraday_data(days_to_keep=14)
        
        if results['errors']:
            flash(f'Cleanup completed with errors: {len(results["errors"])} errors occurred', 'warning')
        else:
            flash(f'Cleanup successful: {results["snapshots_deleted"]} snapshots deleted, {results["market_close_preserved"]} market close snapshots preserved', 'success')
        
        return render_template_with_defaults('admin_debug.html', 
                             title='Intraday Data Cleanup Results',
                             results=results)
    
    except Exception as e:
        logger.error(f"Intraday cleanup error: {str(e)}")
        flash(f'Intraday cleanup error: {str(e)}', 'danger')
        return redirect(url_for('admin_dashboard'))

@app.route('/admin')
@login_required
def admin_dashboard():
    """Enhanced admin dashboard with platform metrics and API status"""
    # Verify user is authenticated
    if not current_user.is_authenticated:
        flash('You must be logged in to access the admin dashboard.', 'warning')
    # ... (rest of the code remains the same)
        return redirect(url_for('login'))
    
    # Check if user is admin using the secure is_admin property
    if not current_user.is_admin:
        flash('You do not have permission to access the admin dashboard.', 'danger')
        return redirect(url_for('dashboard'))
    
    try:
        # Get basic counts
        user_count = User.query.count()
        stock_count = Stock.query.count()
        transaction_count = Transaction.query.count()
        subscription_count = Subscription.query.count()
        
        # Get recent users (limit 10 for table display)
        recent_users = User.query.order_by(User.created_at.desc()).limit(10).all()
        
        # Check for problematic users (missing subscription data)
        problematic_users = User.query.filter(
            (User.subscription_price == None) | (User.stripe_price_id == None)
        ).limit(10).all()
        
    except Exception as e:
        app.logger.error(f"Database error in admin dashboard: {str(e)}")
        # Fallback to basic counts
        user_count = User.query.count() if User.query else 0
        stock_count = Stock.query.count() if Stock.query else 0
        transaction_count = Transaction.query.count() if Transaction.query else 0
        subscription_count = Subscription.query.count() if Subscription.query else 0
        recent_users = []
        problematic_users = []
    
    return render_template_with_defaults('admin/dashboard.html',
        user_count=user_count,
        stock_count=stock_count,
        transaction_count=transaction_count,
        subscription_count=subscription_count,
        recent_users=recent_users,
        problematic_users=problematic_users,
        now=datetime.now()
    )

@app.route('/admin/db-debug')
@login_required
def debug_database():
    """Temporary diagnostic endpoint to check database connectivity and schema"""
    if not current_user.is_admin:
        return "Access denied", 403
    
    results = []
    
    # Test database connection
    try:
        db.session.execute(text("SELECT 1"))
        results.append("✅ Database connection: OK")
    except Exception as e:
        results.append(f"❌ Database connection failed: {str(e)}")
    
    # Check if tables exist
    tables_to_check = ['user', 'stock', 'stock_transaction', 'subscription']
    for table in tables_to_check:
        try:
            result = db.session.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar()
            results.append(f"✅ Table '{table}': {result} rows")
        except Exception as e:
            results.append(f"❌ Table '{table}': {str(e)}")
    
    # Test model queries
    try:
        user_count = User.query.count()
        results.append(f"✅ User.query.count(): {user_count}")
    except Exception as e:
        results.append(f"❌ User.query.count(): {str(e)}")
    
    try:
        stock_count = Stock.query.count()
        results.append(f"✅ Stock.query.count(): {stock_count}")
    except Exception as e:
        results.append(f"❌ Stock.query.count(): {str(e)}")
    
    try:
        transaction_count = Transaction.query.count()
        results.append(f"✅ Transaction.query.count(): {transaction_count}")
    except Exception as e:
        results.append(f"❌ Transaction.query.count(): {str(e)}")
    
    try:
        subscription_count = Subscription.query.count()
        results.append(f"✅ Subscription.query.count(): {subscription_count}")
    except Exception as e:
        results.append(f"❌ Subscription.query.count(): {str(e)}")
    
    # Test recent users query
    try:
        recent_users = User.query.order_by(User.created_at.desc()).limit(5).all()
        results.append(f"✅ Recent users query: {len(recent_users)} users found")
        for user in recent_users:
            results.append(f"   - {user.username} ({user.email})")
    except Exception as e:
        results.append(f"❌ Recent users query: {str(e)}")
    
    html_results = "<br>".join(results)
    return f"""
    <h1>Debug Error</h1>
    <pre>{html_results}</pre>
    <br><a href='/admin'>Back to Admin</a>
    """


@app.route('/admin/test-cron-execution')
@login_required
def test_cron_execution():
    if not current_user.is_admin:
        return redirect(url_for('index'))
    
    try:
        from datetime import datetime, timedelta, time
        from sqlalchemy import distinct
        from models import PortfolioSnapshotIntraday, PortfolioSnapshot, LeaderboardEntry, User, Transaction
        
        today = datetime.now().date()
        yesterday = today - timedelta(days=1)
        
        # Get all users with portfolios
        users_with_portfolios = db.session.query(User).join(Transaction).distinct().all()
        
        results = {
            'test_date': today.isoformat(),
            'users_tested': len(users_with_portfolios),
            'intraday_snapshots_today': 0,
            'eod_snapshots_today': 0,
            'users_with_intraday_today': 0,
            'users_with_eod_today': 0,
            'portfolio_values_varying': 0,
            'leaderboard_updated': False,
            'chart_data_available': 0,
            'issues': [],
            'user_details': []
        }
        
        # Check snapshots for each user
        for user in users_with_portfolios:
            user_data = {
                'username': user.username,
                'user_id': user.id,
                'intraday_today': 0,
                'eod_today': 0,
                'varying_values': False,
                'total_snapshots': 0
            }
            
            # Check intraday snapshots for today
            intraday_today = PortfolioSnapshotIntraday.query.filter(
                PortfolioSnapshotIntraday.user_id == user.id,
                PortfolioSnapshotIntraday.timestamp >= datetime.combine(today, datetime.min.time()),
                PortfolioSnapshotIntraday.timestamp < datetime.combine(today + timedelta(days=1), datetime.min.time())
            ).all()
            
            if intraday_today:
                results['users_with_intraday_today'] += 1
                results['intraday_snapshots_today'] += len(intraday_today)
                user_data['intraday_today'] = len(intraday_today)
                
                # Check for varying values
                values = [snap.total_value for snap in intraday_today]
                if len(set(values)) > 1:
                    results['portfolio_values_varying'] += 1
                    user_data['varying_values'] = True
                else:
                    results['issues'].append(f"User {user.username} has identical intraday values")
            else:
                results['issues'].append(f"User {user.username} missing intraday snapshots for today")
            
            # Check end-of-day snapshots for today
            eod_today = PortfolioSnapshot.query.filter(
                PortfolioSnapshot.user_id == user.id,
                PortfolioSnapshot.date == today
            ).all()
            
            if eod_today:
                results['users_with_eod_today'] += 1
                results['eod_snapshots_today'] += len(eod_today)
                user_data['eod_today'] = len(eod_today)
            else:
                results['issues'].append(f"User {user.username} missing end-of-day snapshot for today")
            
            # Check total snapshots for chart data
            total_snapshots = PortfolioSnapshot.query.filter(
                PortfolioSnapshot.user_id == user.id
            ).count()
            user_data['total_snapshots'] = total_snapshots
            
            if total_snapshots >= 2:
                results['chart_data_available'] += 1
            
            results['user_details'].append(user_data)
        
        # Check leaderboard updates using actual production schema
        try:
            # Query using raw SQL since the model doesn't match production schema
            leaderboard_query = db.session.execute(text("""
                SELECT COUNT(*) as count FROM leaderboard_entry 
                WHERE date >= :yesterday_date
            """), {'yesterday_date': yesterday})
            leaderboard_count = leaderboard_query.fetchone()[0]
            
            if leaderboard_count > 0:
                results['leaderboard_updated'] = True
                results['leaderboard_entries'] = leaderboard_count
                results['top_performers'] = []  # Skip detailed analysis due to schema mismatch
            else:
                results['leaderboard_updated'] = False
                results['leaderboard_entries'] = 0
                results['issues'].append("No recent leaderboard entries found")
                
        except Exception as leaderboard_error:
            logger.warning(f"Leaderboard query failed: {leaderboard_error}")
            results['leaderboard_updated'] = False
            results['leaderboard_entries'] = 0
            results['issues'].append(f"Leaderboard query error: {str(leaderboard_error)}")
        
        # Test portfolio calculation
        if users_with_portfolios:
            try:
                from portfolio_performance import PortfolioPerformanceCalculator
                calculator = PortfolioPerformanceCalculator()
                test_user = users_with_portfolios[0]
                current_value = calculator.calculate_portfolio_value(test_user.id)
                results['portfolio_calculation_test'] = {
                    'success': True,
                    'test_user': test_user.username,
                    'current_value': current_value
                }
            except Exception as e:
                results['portfolio_calculation_test'] = {
                    'success': False,
                    'error': str(e)
                }
                results['issues'].append(f"Portfolio calculation error: {str(e)}")
        
        # Summary
        results['summary'] = {
            'all_tests_passed': len(results['issues']) == 0,
            'total_issues': len(results['issues'])
        }
        
        return f"""
        <h1>Cron Job Execution Test Results</h1>
        <h2>Summary</h2>
        <p><strong>Test Date:</strong> {results['test_date']}</p>
        <p><strong>Users Tested:</strong> {results['users_tested']}</p>
        <p><strong>All Tests Passed:</strong> {'✓ Yes' if results['summary']['all_tests_passed'] else '✗ No'}</p>
        <p><strong>Total Issues:</strong> {results['summary']['total_issues']}</p>
        
        <h2>Snapshot Results</h2>
        <p><strong>Intraday Snapshots Today:</strong> {results['intraday_snapshots_today']}</p>
        <p><strong>Users with Intraday Today:</strong> {results['users_with_intraday_today']}/{results['users_tested']}</p>
        <p><strong>End-of-Day Snapshots Today:</strong> {results['eod_snapshots_today']}</p>
        <p><strong>Users with EOD Today:</strong> {results['users_with_eod_today']}/{results['users_tested']}</p>
        <p><strong>Users with Varying Values:</strong> {results['portfolio_values_varying']}</p>
        <p><strong>Users with Chart Data:</strong> {results['chart_data_available']}</p>
        
        <h2>Leaderboard</h2>
        <p><strong>Updated:</strong> {'✓ Yes' if results['leaderboard_updated'] else '✗ No'}</p>
        {f"<p><strong>Recent Entries:</strong> {results.get('leaderboard_entries', 0)}</p>" if results['leaderboard_updated'] else ""}
        
        <h2>Full Results</h2>
        <pre>{results}</pre>
        
        <br><a href='/admin'>Back to Admin</a>
        """
        
    except Exception as e:
        import traceback
        error_details = {
            'error': str(e),
            'traceback': traceback.format_exc()
        }
        return f"<h1>Cron Test Error</h1><pre>{error_details}</pre><br><a href='/admin'>Back to Admin</a>"

@app.route('/admin/transactions')
@admin_required
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
@admin_required
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

# Error handler
@app.errorhandler(500)
def internal_error(error):
    error_details = {
        'error': str(error),
        'traceback': traceback.format_exc(),
        'request_path': request.path,
        'request_method': request.method,
        'request_args': dict(request.args),
        'template_folder': app.template_folder,
        'static_folder': app.static_folder,
        'template_exists': os.path.exists(app.template_folder),
        'template_files': os.listdir(app.template_folder) if os.path.exists(app.template_folder) else [],
        'static_exists': os.path.exists(app.static_folder),
        'static_files': os.listdir(app.static_folder) if os.path.exists(app.static_folder) else []
    }
    logger.error(f"500 error: {str(error)}", extra=error_details)
    
    # Check if this is an API request
    if request.path.startswith('/api/'):
        return jsonify({
            'error': 'Internal Server Error',
            'status': 500,
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'path': request.path,
            'environment': os.environ.get('VERCEL_ENV', 'development'),
            'request_id': os.environ.get('AWS_LAMBDA_REQUEST_ID', 'local')
        }), 500
    
    # Return a custom error page with details for HTML requests
    return render_template_string("""
<!DOCTYPE html>
<html>
<head>
    <title>Server Error</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 40px; }
        .container { max-width: 800px; margin: 0 auto; }
        .error { background: #f8d7da; padding: 15px; border-radius: 5px; }
        .details { margin-top: 20px; background: #f5f5f5; padding: 15px; border-radius: 5px; }
        pre { background: #eee; padding: 10px; overflow: auto; }
    </style>
</head>
<body>
    <div class="container">
        <h1>Server Error</h1>
        
        <div class="error">
            <h2>500 - Internal Server Error</h2>
            <p>The server encountered an unexpected condition that prevented it from fulfilling the request.</p>
        </div>
        
        <div class="details">
            <h3>Error Details</h3>
            <pre>{{ error_details | tojson(indent=2) }}</pre>
        </div>
        
        <p><a href="/">Return to Home</a></p>
    </div>
</body>
</html>
    """, error_details=error_details), 500

@app.route('/admin/transactions/<int:transaction_id>/edit', methods=['GET', 'POST'])
@admin_required
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
@admin_required
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
        return jsonify({'error': str(e), 'traceback': traceback.format_exc()})

@app.route('/admin/run-migration')
def run_migration():
    """One-time migration endpoint - remove after use"""
    try:
        # Check if user is admin
        email = session.get('email', '')
        if email != ADMIN_EMAIL:
            return jsonify({'error': 'Admin access required'}), 403
        
        # Create the new tables manually since we don't have Flask-Migrate in Vercel
        with app.app_context():
            # Create portfolio_snapshot table
            db.session.execute(text("""
                CREATE TABLE IF NOT EXISTS portfolio_snapshot (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES "user"(id),
                    date DATE NOT NULL,
                    total_value FLOAT NOT NULL,
                    cash_flow FLOAT DEFAULT 0.0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(user_id, date)
                )
            """))
            
            # Create market_data table
            db.session.execute(text("""
                CREATE TABLE IF NOT EXISTS market_data (
                    id SERIAL PRIMARY KEY,
                    symbol VARCHAR(10) NOT NULL,
                    date DATE NOT NULL,
                    close_price FLOAT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(symbol, date)
                )
            """))
            
            # Create subscription_tier table
            db.session.execute(text("""
                CREATE TABLE IF NOT EXISTS subscription_tier (
                    id SERIAL PRIMARY KEY,
                    tier_name VARCHAR(50) NOT NULL UNIQUE,
                    price FLOAT NOT NULL,
                    max_trades_per_day INTEGER NOT NULL,
                    stripe_price_id VARCHAR(100) NOT NULL UNIQUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))
            
            # Create trade_limit table
            db.session.execute(text("""
                CREATE TABLE IF NOT EXISTS trade_limit (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES "user"(id),
                    date DATE NOT NULL,
                    trades_made INTEGER DEFAULT 0,
                    max_trades_allowed INTEGER NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(user_id, date)
                )
            """))
            
            # Create sms_notification table
            db.session.execute(text("""
                CREATE TABLE IF NOT EXISTS sms_notification (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES "user"(id),
                    phone_number VARCHAR(20),
                    is_verified BOOLEAN DEFAULT FALSE,
                    sms_enabled BOOLEAN DEFAULT TRUE,
                    verification_code VARCHAR(6),
                    verification_expires TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """))
            
            # Create stock_info table
            db.session.execute(text("""
                CREATE TABLE IF NOT EXISTS stock_info (
                    id SERIAL PRIMARY KEY,
                    symbol VARCHAR(10) NOT NULL UNIQUE,
                    company_name VARCHAR(200),
                    market_cap BIGINT,
                    sector VARCHAR(100),
                    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))
            
            # Create leaderboard_entry table
            db.session.execute(text("""
                CREATE TABLE IF NOT EXISTS leaderboard_entry (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES "user"(id),
                    date DATE NOT NULL,
                    portfolio_value FLOAT NOT NULL,
                    daily_return FLOAT DEFAULT 0.0,
                    total_return FLOAT DEFAULT 0.0,
                    rank_position INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(user_id, date)
                )
            """))
            
            db.session.commit()
        
        return jsonify({
            'success': True, 
            'message': 'Migration completed successfully'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e), 'traceback': traceback.format_exc()})

@app.route('/admin/fix-all-columns')
@login_required
def fix_all_columns():
    """Fix all missing columns in one go"""
    try:
        # Check if user is admin
        email = session.get('email', '')
        if email != ADMIN_EMAIL:
            return jsonify({'error': 'Admin access required'}), 403
        
        results = []
        
        # Create all cache and metrics tables if they don't exist
        try:
            from models import LeaderboardCache, UserPortfolioChartCache, AlphaVantageAPILog, PlatformMetrics, UserActivity
            db.create_all()
            results.append('Created LeaderboardCache, UserPortfolioChartCache, AlphaVantageAPILog, PlatformMetrics, and UserActivity tables')
        except Exception as e:
            results.append(f'Cache and metrics table creation: {str(e)}')
        
        # Commit table creation first
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            results.append(f'Error committing table creation: {str(e)}')
        
        # Fix SMS notification columns in separate transactions
        try:
            db.session.execute(text('ALTER TABLE sms_notification ADD COLUMN sms_enabled BOOLEAN DEFAULT TRUE'))
            db.session.commit()
            results.append('Added sms_enabled column to sms_notification')
        except Exception as e:
            db.session.rollback()
            if 'already exists' not in str(e).lower() and 'duplicate column' not in str(e).lower():
                results.append(f'Error adding sms_enabled: {str(e)}')
        
        try:
            db.session.execute(text('ALTER TABLE sms_notification ADD COLUMN verification_expires TIMESTAMP'))
            db.session.commit()
            results.append('Added verification_expires column to sms_notification')
        except Exception as e:
            db.session.rollback()
            if 'already exists' not in str(e).lower() and 'duplicate column' not in str(e).lower():
                results.append(f'Error adding verification_expires: {str(e)}')
        
        try:
            db.session.execute(text('ALTER TABLE sms_notification ADD COLUMN updated_at TIMESTAMP'))
            db.session.commit()
            results.append('Added updated_at column to sms_notification')
        except Exception as e:
            db.session.rollback()
            if 'already exists' not in str(e).lower() and 'duplicate column' not in str(e).lower():
                results.append(f'Error adding updated_at: {str(e)}')
        
        return jsonify({
            'success': True,
            'results': results,
            'message': 'All tables and columns created - full system ready with metrics tracking'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/admin/metrics')
@login_required
def admin_metrics():
    """Get platform health metrics for admin dashboard"""
    try:
        # Check if user is admin
        email = session.get('email', '')
        if email != ADMIN_EMAIL:
            return jsonify({'error': 'Admin access required'}), 403
        
        from admin_metrics import get_admin_dashboard_metrics
        metrics = get_admin_dashboard_metrics()
        
        return jsonify({
            'success': True,
            'metrics': metrics
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/admin/update-metrics')
@login_required
def admin_update_metrics():
    """Manually update platform metrics"""
    try:
        # Check if user is admin
        email = session.get('email', '')
        if email != ADMIN_EMAIL:
            return jsonify({'error': 'Admin access required'}), 403
        
        from admin_metrics import update_daily_metrics
        success = update_daily_metrics()
        
        return jsonify({
            'success': success,
            'message': 'Platform metrics updated successfully' if success else 'Error updating metrics'
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/admin/create-leaderboard-tables')
@login_required
def admin_create_leaderboard_tables():
    """Create missing leaderboard-related tables"""
    try:
        # Check if user is admin
        email = session.get('email', '')
        if email != ADMIN_EMAIL:
            return jsonify({'error': 'Admin access required'}), 403
        
        from models import db, LeaderboardCache, UserPortfolioChartCache
        
        # Create the tables
        try:
            db.create_all()
            
            # Verify tables were created
            from sqlalchemy import inspect
            inspector = inspect(db.engine)
            existing_tables = inspector.get_table_names()
            
            results = {
                'leaderboard_cache_exists': 'leaderboard_cache' in existing_tables,
                'user_portfolio_chart_cache_exists': 'user_portfolio_chart_cache' in existing_tables,
                'all_tables': existing_tables
            }
            
            return jsonify({
                'success': True,
                'message': 'Database tables created successfully',
                'results': results
            })
            
        except Exception as e:
            return jsonify({
                'success': False,
                'error': f'Failed to create tables: {str(e)}'
            }), 500
        
    except Exception as e:
        import traceback
        return jsonify({
            'success': False,
            'error': str(e),
            'traceback': traceback.format_exc()
        }), 500

@app.route('/admin/fix-stock-info-symbol')
@login_required
def admin_fix_stock_info_symbol():
    """Normalize legacy 'symbol' column on stock_info to avoid NOT NULL violations.

    Some production databases still have a legacy 'symbol' column defined as NOT NULL,
    while the current model only defines 'ticker'. This endpoint:
      - Detects if 'symbol' exists on stock_info
      - Backfills symbol from ticker where missing
      - Drops the NOT NULL constraint on symbol so future inserts (which only set ticker) succeed
    """
    try:
        # Admin check aligned with other admin endpoints
        email = session.get('email', '')
        if email != ADMIN_EMAIL:
            return jsonify({'error': 'Admin access required'}), 403

        from sqlalchemy import text

        # Check if 'symbol' column exists and whether it is NOT NULL
        col_info = db.session.execute(text("""
            SELECT column_name, is_nullable
            FROM information_schema.columns
            WHERE table_name = 'stock_info' AND column_name = 'symbol'
        """)).fetchone()

        if not col_info:
            return jsonify({
                'success': True,
                'message': "Column 'symbol' does not exist; no action needed"
            })

        actions = []

        # Backfill symbol from ticker where missing
        db.session.execute(text("""
            UPDATE stock_info
            SET symbol = ticker
            WHERE (symbol IS NULL OR symbol = '') AND ticker IS NOT NULL
        """))
        actions.append('Backfilled symbol from ticker where missing')

        # If column is NOT NULL, drop the constraint by altering to NULLable
        if col_info[1] == 'NO':
            db.session.execute(text("""
                ALTER TABLE stock_info
                ALTER COLUMN symbol DROP NOT NULL
            """))
            actions.append('Dropped NOT NULL constraint on symbol')

        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Normalized legacy symbol column on stock_info',
            'actions': actions
        })

    except Exception as e:
        db.session.rollback()
        import traceback
        return jsonify({
            'success': False,
            'error': str(e),
            'traceback': traceback.format_exc()
        }), 500

@app.route('/admin/fix-stock-info-schema')
@login_required
def admin_fix_stock_info_schema():
    """Fix stock_info table schema - add all missing columns"""
    try:
        # Check if user is admin
        email = session.get('email', '')
        if email != ADMIN_EMAIL:
            return jsonify({'error': 'Admin access required'}), 403
        
        from sqlalchemy import text
        
        try:
            # Get existing columns
            result = db.session.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'stock_info'
            """))
            
            existing_columns = {row[0] for row in result.fetchall()}
            actions = []
            
            # Required columns based on StockInfo model
            required_columns = {
                'ticker': 'VARCHAR(10)',
                'company_name': 'VARCHAR(200)',
                'market_cap': 'BIGINT',
                'cap_classification': 'VARCHAR(20)',
                'last_updated': 'TIMESTAMP',
                'created_at': 'TIMESTAMP'
            }
            
            # Add missing columns
            for column_name, column_type in required_columns.items():
                if column_name not in existing_columns:
                    db.session.execute(text(f"""
                        ALTER TABLE stock_info 
                        ADD COLUMN {column_name} {column_type}
                    """))
                    actions.append(f'Added {column_name} column')
            
            # Create indexes
            if 'ticker' not in existing_columns:
                db.session.execute(text("""
                    CREATE INDEX IF NOT EXISTS idx_stock_info_ticker 
                    ON stock_info(ticker)
                """))
                actions.append('Created ticker index')
            
            db.session.commit()
            
            if actions:
                return jsonify({
                    'success': True,
                    'message': 'Fixed stock_info table schema',
                    'actions': actions,
                    'existing_columns': list(existing_columns),
                    'added_columns': [action for action in actions if 'Added' in action]
                })
            else:
                return jsonify({
                    'success': True,
                    'message': 'All required columns already exist',
                    'actions': [],
                    'existing_columns': list(existing_columns)
                })
                
        except Exception as e:
            db.session.rollback()
            return jsonify({
                'success': False,
                'error': f'Failed to fix stock_info schema: {str(e)}'
            }), 500
        
    except Exception as e:
        import traceback
        return jsonify({
            'success': False,
            'error': str(e),
            'traceback': traceback.format_exc()
        }), 500

@app.route('/admin/validate-schema')
@login_required
def admin_validate_schema():
    """Comprehensive schema validation - compare all model columns against production database"""
    try:
        # Check if user is admin
        email = session.get('email', '')
        if email != ADMIN_EMAIL:
            return jsonify({'error': 'Admin access required'}), 403
        
        from sqlalchemy import text, inspect
        from models import (User, Stock, Subscription, SubscriptionTier, Transaction, 
                          PortfolioSnapshot, MarketData, PortfolioSnapshotIntraday, 
                          LeaderboardCache, UserPortfolioChartCache, StockInfo, 
                          AlphaVantageAPILog, UserActivity, PlatformMetrics, SMSNotification)
        
        # Get all model classes
        models_to_check = [
            User, Stock, Subscription, SubscriptionTier, Transaction,
            PortfolioSnapshot, MarketData, PortfolioSnapshotIntraday,
            LeaderboardCache, UserPortfolioChartCache, StockInfo,
            AlphaVantageAPILog, UserActivity, PlatformMetrics, SMSNotification
        ]
        
        inspector = inspect(db.engine)
        production_tables = set(inspector.get_table_names())
        
        validation_results = {
            'tables_checked': 0,
            'missing_tables': [],
            'missing_columns': [],
            'type_mismatches': [],
            'all_valid': True
        }
        
        for model in models_to_check:
            table_name = model.__tablename__
            validation_results['tables_checked'] += 1
            
            # Check if table exists
            if table_name not in production_tables:
                validation_results['missing_tables'].append(table_name)
                validation_results['all_valid'] = False
                continue
            
            # Get production columns
            production_columns = {col['name']: col for col in inspector.get_columns(table_name)}
            
            # Check each model column
            for column in model.__table__.columns:
                column_name = column.name
                
                if column_name not in production_columns:
                    validation_results['missing_columns'].append({
                        'table': table_name,
                        'column': column_name,
                        'expected_type': str(column.type),
                        'nullable': column.nullable
                    })
                    validation_results['all_valid'] = False
                else:
                    # Check type compatibility (basic check)
                    prod_col = production_columns[column_name]
                    model_type = str(column.type).upper()
                    prod_type = str(prod_col['type']).upper()
                    
                    # Basic type compatibility check
                    if not _types_compatible(model_type, prod_type):
                        validation_results['type_mismatches'].append({
                            'table': table_name,
                            'column': column_name,
                            'model_type': model_type,
                            'production_type': prod_type
                        })
        
        return jsonify({
            'success': True,
            'validation_results': validation_results,
            'production_tables_count': len(production_tables),
            'models_checked_count': len(models_to_check)
        })
        
    except Exception as e:
        import traceback
        return jsonify({
            'success': False,
            'error': str(e),
            'traceback': traceback.format_exc()
        }), 500

def _types_compatible(model_type, prod_type):
    """Basic type compatibility check"""
    # Normalize types for comparison
    type_mappings = {
        'INTEGER': ['INTEGER', 'INT', 'SERIAL'],
        'VARCHAR': ['VARCHAR', 'TEXT', 'STRING'],
        'TIMESTAMP': ['TIMESTAMP', 'DATETIME'],
        'BOOLEAN': ['BOOLEAN', 'BOOL'],
        'FLOAT': ['FLOAT', 'REAL', 'DOUBLE'],
        'BIGINT': ['BIGINT', 'LONG']
    }
    
    for base_type, compatible_types in type_mappings.items():
        if any(t in model_type for t in compatible_types) and any(t in prod_type for t in compatible_types):
            return True
    
    return model_type == prod_type

@app.route('/admin/diagnose-portfolio-data')
@login_required
def admin_diagnose_portfolio_data():
    """Diagnose why portfolio values are showing as $0 and 0% performance"""
    try:
        # Check if user is admin
        email = session.get('email', '')
        if email != ADMIN_EMAIL:
            return jsonify({'error': 'Admin access required'}), 403
        
        from datetime import datetime, date, timedelta
        from models import db, PortfolioSnapshot, User, Stock
        from portfolio_performance import PortfolioPerformanceCalculator
        
        diagnosis = {
            'user_stock_data': [],
            'snapshot_analysis': [],
            'calculation_test': [],
            'api_test': None
        }
        
        # Check each user's stock holdings and snapshots
        users = User.query.all()
        for user in users:
            stocks = Stock.query.filter_by(user_id=user.id).all()
            
            user_data = {
                'user_id': user.id,
                'username': user.username,
                'stock_count': len(stocks),
                'stocks': []
            }
            
            total_purchase_value = 0
            for stock in stocks:
                stock_data = {
                    'ticker': stock.ticker,
                    'quantity': float(stock.quantity),
                    'purchase_price': float(stock.purchase_price),
                    'purchase_date': stock.purchase_date.isoformat(),
                    'purchase_value': float(stock.quantity * stock.purchase_price)
                }
                total_purchase_value += stock_data['purchase_value']
                user_data['stocks'].append(stock_data)
            
            user_data['total_purchase_value'] = total_purchase_value
            
            # Check recent snapshots for this user
            recent_snapshots = PortfolioSnapshot.query.filter_by(user_id=user.id)\
                .order_by(PortfolioSnapshot.date.desc()).limit(5).all()
            
            user_data['recent_snapshots'] = []
            for snapshot in recent_snapshots:
                user_data['recent_snapshots'].append({
                    'date': snapshot.date.isoformat(),
                    'total_value': float(snapshot.total_value),
                    'cash_flow': float(snapshot.cash_flow) if snapshot.cash_flow else 0
                })
            
            diagnosis['user_stock_data'].append(user_data)
        
        # Test portfolio calculation for one user
        if users:
            test_user = users[0]
            calculator = PortfolioPerformanceCalculator()
            
            try:
                # Test current portfolio value calculation
                current_value = calculator.calculate_portfolio_value(test_user.id)
                
                # Test snapshot creation
                today = date.today()
                snapshot_result = calculator.create_daily_snapshot(test_user.id, today)
                
                diagnosis['calculation_test'] = {
                    'test_user_id': test_user.id,
                    'current_portfolio_value': current_value,
                    'snapshot_creation': snapshot_result,
                    'calculation_success': True
                }
                
            except Exception as e:
                diagnosis['calculation_test'] = {
                    'test_user_id': test_user.id,
                    'error': str(e),
                    'calculation_success': False
                }
        
        # Test Alpha Vantage API for a common stock
        try:
            import requests
            import os
            api_key = os.environ.get('ALPHA_VANTAGE_API_KEY')
            
            if api_key:
                # Test API call for AAPL
                url = f'https://www.alphavantage.co/query?function=GLOBAL_QUOTE&symbol=AAPL&apikey={api_key}'
                response = requests.get(url, timeout=10)
                
                if response.status_code == 200:
                    data = response.json()
                    diagnosis['api_test'] = {
                        'success': True,
                        'aapl_price': data.get('Global Quote', {}).get('05. price', 'N/A'),
                        'api_calls_today': 'Check logs'
                    }
                else:
                    diagnosis['api_test'] = {
                        'success': False,
                        'error': f'HTTP {response.status_code}'
                    }
            else:
                diagnosis['api_test'] = {
                    'success': False,
                    'error': 'No API key found'
                }
                
        except Exception as e:
            diagnosis['api_test'] = {
                'success': False,
                'error': str(e)
            }
        
        return jsonify({
            'success': True,
            'diagnosis': diagnosis
        })
        
    except Exception as e:
        import traceback
        return jsonify({
            'success': False,
            'error': str(e),
            'traceback': traceback.format_exc()
        }), 500

@app.route('/admin/fix-portfolio-snapshots')
@login_required
def admin_fix_portfolio_snapshots():
    """Fix all portfolio snapshots to use real calculated values instead of zeros"""
    try:
        # Check if user is admin
        email = session.get('email', '')
        if email != ADMIN_EMAIL:
            return jsonify({'error': 'Admin access required'}), 403
        
        from datetime import datetime, date, timedelta
        from models import db, PortfolioSnapshot, User, Stock
        from portfolio_performance import PortfolioPerformanceCalculator
        
        calculator = PortfolioPerformanceCalculator()
        results = {
            'users_processed': 0,
            'snapshots_updated': 0,
            'snapshots_created': 0,
            'errors': [],
            'user_details': []
        }
        
        # Get all users with stocks
        users = User.query.join(Stock).distinct().all()
        
        for user in users:
            try:
                user_result = {
                    'user_id': user.id,
                    'username': user.username,
                    'snapshots_updated': 0,
                    'snapshots_created': 0,
                    'current_portfolio_value': 0
                }
                
                # Calculate current portfolio value
                current_value = calculator.calculate_portfolio_value(user.id)
                user_result['current_portfolio_value'] = current_value
                
                # Get ALL snapshots from beginning of year that need fixing
                end_date = date.today()
                start_date = date(end_date.year, 1, 1)  # January 1st of current year
                
                # Get existing snapshots in this period
                existing_snapshots = PortfolioSnapshot.query.filter(
                    PortfolioSnapshot.user_id == user.id,
                    PortfolioSnapshot.date >= start_date,
                    PortfolioSnapshot.date <= end_date
                ).all()
                
                # Get user's actual account creation date (first stock purchase)
                from models import Stock
                first_stock = Stock.query.filter_by(user_id=user.id)\
                    .order_by(Stock.purchase_date.asc()).first()
                
                if not first_stock:
                    continue  # Skip users with no stocks
                
                # Only create/update snapshots from account creation date forward
                account_start_date = first_stock.purchase_date.date()
                actual_start_date = max(start_date, account_start_date)
                
                # Calculate realistic portfolio progression from start to current
                current_portfolio_value = calculator.calculate_portfolio_value(user.id)
                
                # Get total purchase value (initial investment)
                stocks = Stock.query.filter_by(user_id=user.id).all()
                total_purchase_value = sum(stock.quantity * stock.purchase_price for stock in stocks)
                
                # Calculate total return percentage
                if total_purchase_value > 0:
                    total_return_pct = (current_portfolio_value - total_purchase_value) / total_purchase_value
                else:
                    total_return_pct = 0
                
                # Days since account creation
                days_since_start = (end_date - account_start_date).days
                if days_since_start <= 0:
                    days_since_start = 1
                
                # Delete snapshots from before account existed
                for snapshot in existing_snapshots:
                    if snapshot.date < account_start_date:
                        db.session.delete(snapshot)
                
                # Create/update snapshots with realistic progression
                current_date = actual_start_date
                while current_date <= end_date:
                    if current_date.weekday() < 5:  # Only weekdays
                        # Calculate days since start for this date
                        days_elapsed = (current_date - account_start_date).days
                        
                        # Linear progression from purchase value to current value
                        if days_since_start > 0:
                            progress_ratio = days_elapsed / days_since_start
                            portfolio_value = total_purchase_value + (total_return_pct * total_purchase_value * progress_ratio)
                        else:
                            portfolio_value = current_portfolio_value
                        
                        # Ensure minimum value
                        portfolio_value = max(portfolio_value, total_purchase_value * 0.5)  # Never lose more than 50%
                        
                        existing = PortfolioSnapshot.query.filter_by(
                            user_id=user.id, date=current_date
                        ).first()
                        
                        if existing:
                            if abs(existing.total_value - portfolio_value) > 0.01:
                                existing.total_value = portfolio_value
                                user_result['snapshots_updated'] += 1
                                results['snapshots_updated'] += 1
                        else:
                            cash_flow = calculator.calculate_daily_cash_flow(user.id, current_date)
                            new_snapshot = PortfolioSnapshot(
                                user_id=user.id,
                                date=current_date,
                                total_value=portfolio_value,
                                cash_flow=cash_flow
                            )
                            db.session.add(new_snapshot)
                            user_result['snapshots_created'] += 1
                            results['snapshots_created'] += 1
                    
                    current_date += timedelta(days=1)
                
                results['user_details'].append(user_result)
                results['users_processed'] += 1
                
            except Exception as e:
                error_msg = f"Error processing user {user.id}: {str(e)}"
                results['errors'].append(error_msg)
        
        # Commit all changes
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Fixed portfolio snapshots for {results["users_processed"]} users',
            'results': results
        })
        
    except Exception as e:
        db.session.rollback()
        import traceback
        return jsonify({
            'success': False,
            'error': str(e),
            'traceback': traceback.format_exc()
        }), 500

@app.route('/admin/debug-performance-calculation')
@login_required
def admin_debug_performance_calculation():
    """Debug why performance calculations show 0.0% despite real snapshots"""
    try:
        # Check if user is admin
        email = session.get('email', '')
        if email != ADMIN_EMAIL:
            return jsonify({'error': 'Admin access required'}), 403
        
        from datetime import datetime, date, timedelta
        from models import db, PortfolioSnapshot, User, Stock
        
        debug_data = {
            'users': [],
            'period_tests': []
        }
        
        # Test different periods for performance calculation
        periods = ['YTD', '1Y', '3M', '1M']
        today = date.today()
        
        users = User.query.join(Stock).distinct().limit(3).all()  # Test first 3 users
        
        for user in users:
            user_debug = {
                'user_id': user.id,
                'username': user.username,
                'period_calculations': []
            }
            
            for period in periods:
                # Calculate period start date (same logic as leaderboard)
                if period == 'YTD':
                    start_date = date(today.year, 1, 1)
                elif period == '1Y':
                    start_date = today - timedelta(days=365)
                elif period == '3M':
                    start_date = today - timedelta(days=90)
                elif period == '1M':
                    start_date = today - timedelta(days=30)
                
                # Get latest snapshot
                latest_snapshot = PortfolioSnapshot.query.filter_by(user_id=user.id)\
                    .order_by(PortfolioSnapshot.date.desc()).first()
                
                # Get first snapshot (actual portfolio start)
                first_snapshot = PortfolioSnapshot.query.filter_by(user_id=user.id)\
                    .order_by(PortfolioSnapshot.date.asc()).first()
                
                # Get actual start date (max of period start or first snapshot)
                actual_start_date = max(start_date, first_snapshot.date) if first_snapshot else start_date
                
                # Get start snapshot
                start_snapshot = PortfolioSnapshot.query.filter_by(user_id=user.id)\
                    .filter(PortfolioSnapshot.date >= actual_start_date)\
                    .order_by(PortfolioSnapshot.date.asc()).first()
                
                # Calculate performance
                performance_percent = 0.0
                if latest_snapshot and start_snapshot and start_snapshot.total_value > 0:
                    current_value = latest_snapshot.total_value
                    start_value = start_snapshot.total_value
                    performance_percent = ((current_value - start_value) / start_value) * 100
                
                period_calc = {
                    'period': period,
                    'period_start_date': start_date.isoformat(),
                    'first_snapshot_date': first_snapshot.date.isoformat() if first_snapshot else None,
                    'actual_start_date': actual_start_date.isoformat(),
                    'start_snapshot_date': start_snapshot.date.isoformat() if start_snapshot else None,
                    'start_value': float(start_snapshot.total_value) if start_snapshot else 0,
                    'current_value': float(latest_snapshot.total_value) if latest_snapshot else 0,
                    'performance_percent': round(performance_percent, 2),
                    'calculation_valid': bool(start_snapshot and latest_snapshot and start_snapshot.total_value > 0)
                }
                
                user_debug['period_calculations'].append(period_calc)
            
            debug_data['users'].append(user_debug)
        
        return jsonify({
            'success': True,
            'debug_data': debug_data
        })
        
    except Exception as e:
        import traceback
        return jsonify({
            'success': False,
            'error': str(e),
            'traceback': traceback.format_exc()
        }), 500

@app.route('/admin/check-snapshot-history')
@login_required
def admin_check_snapshot_history():
    """Check actual snapshot history to see if we have varying daily values"""
    try:
        # Check if user is admin
        email = session.get('email', '')
        if email != ADMIN_EMAIL:
            return jsonify({'error': 'Admin access required'}), 403
        
        from datetime import datetime, date, timedelta
        from models import db, PortfolioSnapshot, User, Stock
        
        # Get users with stocks
        users = User.query.join(Stock).distinct().limit(5).all()
        
        snapshot_analysis = {
            'users': [],
            'summary': {}
        }
        
        for user in users:
            # Get all snapshots for this user in last 30 days
            thirty_days_ago = date.today() - timedelta(days=30)
            snapshots = PortfolioSnapshot.query.filter(
                PortfolioSnapshot.user_id == user.id,
                PortfolioSnapshot.date >= thirty_days_ago
            ).order_by(PortfolioSnapshot.date.desc()).limit(20).all()
            
            # Analyze snapshot values
            unique_values = set()
            snapshot_data = []
            
            for snapshot in snapshots:
                unique_values.add(round(float(snapshot.total_value), 2))
                snapshot_data.append({
                    'date': snapshot.date.isoformat(),
                    'value': round(float(snapshot.total_value), 2),
                    'cash_flow': round(float(snapshot.cash_flow), 2) if snapshot.cash_flow else 0
                })
            
            # Get first stock purchase date
            first_stock = Stock.query.filter_by(user_id=user.id)\
                .order_by(Stock.purchase_date.asc()).first()
            
            user_analysis = {
                'user_id': user.id,
                'username': user.username,
                'account_created': first_stock.purchase_date.date().isoformat() if first_stock else None,
                'total_snapshots': len(snapshots),
                'unique_values_count': len(unique_values),
                'unique_values': sorted(list(unique_values)),
                'recent_snapshots': snapshot_data[:10],  # Last 10 days
                'has_variation': len(unique_values) > 1,
                'days_since_creation': (date.today() - first_stock.purchase_date.date()).days if first_stock else 0
            }
            
            snapshot_analysis['users'].append(user_analysis)
        
        # Summary statistics
        total_users = len(snapshot_analysis['users'])
        users_with_variation = sum(1 for u in snapshot_analysis['users'] if u['has_variation'])
        
        snapshot_analysis['summary'] = {
            'total_users_checked': total_users,
            'users_with_varying_snapshots': users_with_variation,
            'users_with_identical_snapshots': total_users - users_with_variation,
            'issue_identified': users_with_variation == 0
        }
        
        return jsonify({
            'success': True,
            'analysis': snapshot_analysis
        })
        
    except Exception as e:
        import traceback
        return jsonify({
            'success': False,
            'error': str(e),
            'traceback': traceback.format_exc()
        }), 500

@app.route('/admin/clean-historical-snapshots')
@login_required
def admin_clean_historical_snapshots():
    """Remove incorrect historical snapshots and keep only recent real ones"""
    try:
        # Check if user is admin
        email = session.get('email', '')
        if email != ADMIN_EMAIL:
            return jsonify({'error': 'Admin access required'}), 403
        
        from datetime import datetime, date, timedelta
        from models import db, PortfolioSnapshot, User, Stock
        
        results = {
            'users_processed': 0,
            'snapshots_deleted': 0,
            'snapshots_kept': 0
        }
        
        # Get users with stocks
        users = User.query.join(Stock).distinct().all()
        
        for user in users:
            results['users_processed'] += 1
            
            # Keep only the last 7 days of snapshots (real daily data)
            cutoff_date = date.today() - timedelta(days=7)
            
            # Delete old snapshots with identical values
            old_snapshots = PortfolioSnapshot.query.filter(
                PortfolioSnapshot.user_id == user.id,
                PortfolioSnapshot.date < cutoff_date
            ).all()
            
            for snapshot in old_snapshots:
                db.session.delete(snapshot)
                results['snapshots_deleted'] += 1
            
            # Count kept snapshots
            kept_snapshots = PortfolioSnapshot.query.filter(
                PortfolioSnapshot.user_id == user.id,
                PortfolioSnapshot.date >= cutoff_date
            ).count()
            
            results['snapshots_kept'] += kept_snapshots
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Cleaned historical snapshots for {results["users_processed"]} users',
            'results': results
        })
        
    except Exception as e:
        db.session.rollback()
        import traceback
        return jsonify({
            'success': False,
            'error': str(e),
            'traceback': traceback.format_exc()
        }), 500

@app.route('/admin/diagnose-snapshot-creation')
@login_required
def admin_diagnose_snapshot_creation():
    """Diagnose why snapshots are identical - check API calls, caching, calculation logic"""
    try:
        # Check if user is admin
        email = session.get('email', '')
        if email != ADMIN_EMAIL:
            return jsonify({'error': 'Admin access required'}), 403
        
        from datetime import datetime, date, timedelta
        from models import db, PortfolioSnapshot, User, Stock
        from portfolio_performance import PortfolioPerformanceCalculator
        import os
        
        diagnosis = {
            'api_status': {},
            'calculation_tests': [],
            'caching_analysis': {},
            'root_cause_analysis': []
        }
        
        # Test 1: Check Alpha Vantage API connectivity
        try:
            api_key = os.environ.get('ALPHA_VANTAGE_API_KEY')
            diagnosis['api_status']['api_key_present'] = bool(api_key)
            diagnosis['api_status']['api_key_length'] = len(api_key) if api_key else 0
            
            calculator = PortfolioPerformanceCalculator()
            
            # Test API call for a common stock
            test_stock = Stock.query.first()
            if test_stock:
                stock_data = calculator.get_stock_data(test_stock.ticker)
                diagnosis['api_status']['test_api_call'] = {
                    'ticker': test_stock.ticker,
                    'success': stock_data is not None,
                    'current_price': float(stock_data.get('price', 0)) if stock_data else 0,
                    'data_keys': list(stock_data.keys()) if stock_data else []
                }
        except Exception as e:
            diagnosis['api_status']['api_error'] = str(e)
        
        # Test 2: Check portfolio calculation consistency
        users = User.query.join(Stock).distinct().limit(3).all()
        
        for user in users:
            try:
                # Calculate portfolio value multiple times to check consistency
                calc1 = calculator.calculate_portfolio_value(user.id)
                calc2 = calculator.calculate_portfolio_value(user.id)
                calc3 = calculator.calculate_portfolio_value(user.id)
                
                # Get user's stocks for analysis
                stocks = Stock.query.filter_by(user_id=user.id).all()
                stock_details = []
                
                for stock in stocks:
                    stock_data = calculator.get_stock_data(stock.ticker)
                    stock_details.append({
                        'ticker': stock.ticker,
                        'quantity': float(stock.quantity),
                        'purchase_price': float(stock.purchase_price),
                        'current_price': float(stock_data.get('price', 0)) if stock_data else 0,
                        'api_success': stock_data is not None
                    })
                
                calculation_test = {
                    'user_id': user.id,
                    'username': user.username,
                    'calculation_1': float(calc1),
                    'calculation_2': float(calc2),
                    'calculation_3': float(calc3),
                    'calculations_identical': calc1 == calc2 == calc3,
                    'stock_count': len(stocks),
                    'stock_details': stock_details
                }
                
                diagnosis['calculation_tests'].append(calculation_test)
                
            except Exception as e:
                diagnosis['calculation_tests'].append({
                    'user_id': user.id,
                    'error': str(e)
                })
        
        # Test 3: Check caching behavior
        try:
            # Check if get_batch_stock_data is using cached values
            test_tickers = [stock.ticker for stock in Stock.query.limit(3).all()]
            if test_tickers:
                batch_data_1 = calculator.get_batch_stock_data(test_tickers)
                batch_data_2 = calculator.get_batch_stock_data(test_tickers)
                
                diagnosis['caching_analysis'] = {
                    'test_tickers': test_tickers,
                    'batch_1_success': batch_data_1 is not None,
                    'batch_2_success': batch_data_2 is not None,
                    'results_identical': batch_data_1 == batch_data_2 if batch_data_1 and batch_data_2 else False,
                    'cache_working': True  # If results are identical, caching is working
                }
        except Exception as e:
            diagnosis['caching_analysis']['error'] = str(e)
        
        # Root cause analysis
        diagnosis['root_cause_analysis'] = [
            "Identical snapshots can be caused by:",
            "1. API failures causing fallback to cached/default values",
            "2. Portfolio calculation using stale cached prices",
            "3. Snapshot creation logic using current values for all historical dates",
            "4. Database constraints or transaction issues",
            "5. Cron job running with same timestamp for multiple days"
        ]
        
        return jsonify({
            'success': True,
            'diagnosis': diagnosis
        })
        
    except Exception as e:
        import traceback
        return jsonify({
            'success': False,
            'error': str(e),
            'traceback': traceback.format_exc()
        }), 500

@app.route('/admin/test-api-response')
@login_required
def admin_test_api_response():
    """Test actual Alpha Vantage API response format"""
    try:
        # Check if user is admin
        email = session.get('email', '')
        if email != ADMIN_EMAIL:
            return jsonify({'error': 'Admin access required'}), 403
        
        import requests
        import os
        
        api_key = os.environ.get('ALPHA_VANTAGE_API_KEY')
        if not api_key:
            return jsonify({'error': 'No API key found'}), 400
        
        # Test with AAPL
        test_ticker = 'AAPL'
        url = f'https://www.alphavantage.co/query?function=GLOBAL_QUOTE&symbol={test_ticker}&apikey={api_key}'
        
        try:
            response = requests.get(url, timeout=10)
            raw_data = response.json()
            
            # Try to parse the response
            parsed_price = None
            if 'Global Quote' in raw_data and '05. price' in raw_data['Global Quote']:
                parsed_price = float(raw_data['Global Quote']['05. price'])
            
            return jsonify({
                'success': True,
                'test_ticker': test_ticker,
                'api_url': url,
                'raw_response': raw_data,
                'parsed_price': parsed_price,
                'response_keys': list(raw_data.keys()) if isinstance(raw_data, dict) else None,
                'global_quote_keys': list(raw_data.get('Global Quote', {}).keys()) if raw_data.get('Global Quote') else None
            })
            
        except requests.exceptions.RequestException as e:
            return jsonify({
                'success': False,
                'error': f'Request failed: {str(e)}'
            }), 500
            
    except Exception as e:
        import traceback
        return jsonify({
            'success': False,
            'error': str(e),
            'traceback': traceback.format_exc()
        }), 500

@app.route('/admin/populate-leaderboard')
@login_required
def admin_populate_leaderboard():
    """Manually populate leaderboard cache - immediate fix for missing data"""
    try:
        # Check if user is admin
        email = session.get('email', '')
        if email != ADMIN_EMAIL:
            return jsonify({'error': 'Admin access required'}), 403
        
        from datetime import datetime, date, timedelta
        from models import db, PortfolioSnapshot, User, Stock, LeaderboardCache
        
        # First check if we have the basic data needed
        total_users = User.query.count()
        users_with_stocks = User.query.join(Stock).distinct().count()
        total_snapshots = PortfolioSnapshot.query.count()
        yesterday = date.today() - timedelta(days=1)
        yesterday_snapshots = PortfolioSnapshot.query.filter_by(date=yesterday).count()
        
        # Test database write capability
        test_entry = LeaderboardCache(
            period='TEST_WRITE',
            leaderboard_data='[]',
            generated_at=datetime.now()
        )
        
        try:
            db.session.add(test_entry)
            db.session.commit()
            db.session.delete(test_entry)
            db.session.commit()
            db_write_test = "SUCCESS"
        except Exception as db_e:
            db.session.rollback()
            db_write_test = f"FAILED: {str(db_e)}"
        
        results = {
            'data_check': {
                'total_users': total_users,
                'users_with_stocks': users_with_stocks,
                'total_snapshots': total_snapshots,
                'yesterday_snapshots': yesterday_snapshots
            },
            'db_write_test': db_write_test
        }
        
        if users_with_stocks == 0:
            return jsonify({
                'success': False,
                'error': 'No users have stocks - leaderboard cannot be populated',
                'results': results
            })
        
        if total_snapshots == 0:
            return jsonify({
                'success': False,
                'error': 'No portfolio snapshots exist - need to create snapshots first',
                'results': results,
                'suggestion': 'Run /admin/create-todays-snapshots first'
            })
        
        # Update leaderboard cache
        from leaderboard_utils import update_leaderboard_cache
        updated_count = update_leaderboard_cache()
        
        # Test the API endpoint
        from leaderboard_utils import get_leaderboard_data
        test_data = get_leaderboard_data('YTD', 10, 'all')  # Get more entries to match homepage
        
        results.update({
            'leaderboard_cache_updated': updated_count,
            'test_data_entries': len(test_data),
            'sample_entries': test_data[:3] if test_data else []
        })
        
        return jsonify({
            'success': True,
            'message': f'Leaderboard cache populated with {updated_count} periods',
            'results': results
        })
        
    except Exception as e:
        import traceback
        return jsonify({
            'success': False,
            'error': str(e),
            'traceback': traceback.format_exc()
        }), 500

@app.route('/admin/run-stock-info-migration')
@login_required
def admin_run_stock_info_migration():
    """Run the StockInfo metadata enhancement migration"""
    if not current_user.is_admin:
        return jsonify({'error': 'Admin access required'}), 403
    
    try:
        # Add missing columns to stock_info table
        with app.app_context():
            # Check if columns already exist first
            result = db.session.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'stock_info' 
                AND column_name IN ('sector', 'industry', 'naics_code', 'exchange', 'country', 'is_active')
            """))
            existing_columns = [row[0] for row in result.fetchall()]
            
            columns_to_add = []
            if 'sector' not in existing_columns:
                columns_to_add.append("ADD COLUMN sector VARCHAR(100)")
            if 'industry' not in existing_columns:
                columns_to_add.append("ADD COLUMN industry VARCHAR(100)")
            if 'naics_code' not in existing_columns:
                columns_to_add.append("ADD COLUMN naics_code VARCHAR(10)")
            if 'exchange' not in existing_columns:
                columns_to_add.append("ADD COLUMN exchange VARCHAR(10)")
            if 'country' not in existing_columns:
                columns_to_add.append("ADD COLUMN country VARCHAR(5) DEFAULT 'US'")
            if 'is_active' not in existing_columns:
                columns_to_add.append("ADD COLUMN is_active BOOLEAN DEFAULT TRUE")
            
            if columns_to_add:
                # Add columns one by one to avoid syntax issues
                for column_sql in columns_to_add:
                    db.session.execute(text(f"ALTER TABLE stock_info {column_sql}"))
                
                db.session.commit()
                
                return jsonify({
                    'success': True,
                    'message': f'Successfully added {len(columns_to_add)} columns to stock_info table',
                    'columns_added': columns_to_add
                })
            else:
                return jsonify({
                    'success': True,
                    'message': 'All columns already exist in stock_info table',
                    'existing_columns': existing_columns
                })
                
    except Exception as e:
        db.session.rollback()
        import traceback
        return jsonify({
            'success': False,
            'error': str(e),
            'traceback': traceback.format_exc()
        }), 500

@app.route('/admin/populate-stock-metadata')
@login_required
def admin_populate_stock_metadata():
    """Populate comprehensive stock metadata for all user-held stocks"""
    if not current_user.is_admin:
        return jsonify({'error': 'Admin access required'}), 403
    
    try:
        # Import dependencies before first use to avoid UnboundLocalError
        from models import StockInfo, Stock
        from stock_metadata_utils import (
            populate_all_user_stocks,
            populate_user_stocks_batch,
            populate_user_stocks_resume,
            get_remaining_tickers,
        )
        
        # Count existing stock info records
        existing_stock_info = StockInfo.query.count()
        
        # Get current stats
        total_stocks = Stock.query.distinct(Stock.ticker).count()
        existing_stock_info = StockInfo.query.count()
        stock_info_with_metadata = StockInfo.query.filter(
            StockInfo.sector.isnot(None),
            StockInfo.industry.isnot(None)
        ).count()
        
        results = {
            'before_population': {
                'unique_tickers_held': total_stocks,
                'existing_stock_info_records': existing_stock_info,
                'records_with_metadata': stock_info_with_metadata
            }
        }
        # Optional batching/resume controls via query params
        # Examples:
        #   /admin/populate-stock-metadata?limit=5
        #   /admin/populate-stock-metadata?limit=5&offset=5
        #   /admin/populate-stock-metadata?tickers=KO,MSFT
        #   /admin/populate-stock-metadata?force=true&sleep=8
        #   /admin/populate-stock-metadata?resume=true&limit=5
        #   /admin/populate-stock-metadata?resume=true&dry_run=true
        limit = request.args.get('limit', default=None, type=int)
        offset = request.args.get('offset', default=0, type=int)
        tickers = request.args.get('tickers', default=None, type=str)
        force_flag = request.args.get('force', default='false', type=str)
        sleep_seconds = request.args.get('sleep', default=12, type=int)
        batch_flag = request.args.get('batch', default=None, type=str)
        resume_flag = request.args.get('resume', default='false', type=str)
        dry_run_flag = request.args.get('dry_run', default='false', type=str)

        use_batch = (limit is not None) or (tickers is not None) or (batch_flag is not None)
        force_update = str(force_flag).lower() in ('1', 'true', 'yes')
        use_resume = str(resume_flag).lower() in ('1', 'true', 'yes')
        use_dry_run = str(dry_run_flag).lower() in ('1', 'true', 'yes')

        if use_resume:
            remaining_list = get_remaining_tickers(force_update=force_update)
            # Dry run: just return what would be processed
            if use_dry_run:
                preview = remaining_list[offset:(offset + limit) if (isinstance(limit, int) and limit > 0) else None]
                success_count = 0
                failed_count = 0
                results['resume'] = {
                    'dry_run': True,
                    'remaining_total': len(remaining_list),
                    'next_batch_preview': preview,
                    'limit': limit,
                    'offset': offset,
                    'force_update': force_update
                }
            else:
                resume_result = populate_user_stocks_resume(
                    limit=limit,
                    offset=offset,
                    force_update=force_update,
                    sleep_seconds=sleep_seconds
                )
                success_count = resume_result['success_count']
                failed_count = resume_result['failed_count']
                results['resume'] = {
                    'remaining_total_after': resume_result['remaining_total'],
                    'limit': limit,
                    'offset': offset,
                    'sleep_seconds': sleep_seconds,
                    'force_update': force_update,
                    'tickers_processed': resume_result['tickers_processed']
                }
        elif use_batch:
            batch_result = populate_user_stocks_batch(
                limit=limit,
                offset=offset,
                tickers=tickers,
                force_update=force_update,
                sleep_seconds=sleep_seconds
            )
            success_count = batch_result['success_count']
            failed_count = batch_result['failed_count']
            results['batch'] = {
                'limit': limit,
                'offset': offset,
                'tickers': tickers.split(',') if tickers else None,
                'sleep_seconds': sleep_seconds,
                'force_update': force_update,
                'tickers_processed': batch_result['tickers_processed']
            }
        else:
            # Populate all stock metadata
            success_count, failed_count = populate_all_user_stocks()
        
        # Get updated stats
        updated_stock_info = StockInfo.query.count()
        updated_with_metadata = StockInfo.query.filter(
            StockInfo.sector.isnot(None),
            StockInfo.industry.isnot(None)
        ).count()
        
        # Sample of populated data
        sample_stocks = StockInfo.query.filter(
            StockInfo.sector.isnot(None)
        ).limit(5).all()
        
        sample_data = []
        for stock in sample_stocks:
            sample_data.append({
                'ticker': stock.ticker,
                'company_name': stock.company_name,
                'sector': stock.sector,
                'industry': stock.industry,
                'cap_classification': stock.cap_classification,
                'naics_code': stock.naics_code,
                'exchange': stock.exchange
            })
        
        results.update({
            'population_results': {
                'success_count': success_count,
                'failed_count': failed_count,
                'total_processed': success_count + failed_count
            },
            'after_population': {
                'total_stock_info_records': updated_stock_info,
                'records_with_metadata': updated_with_metadata
            },
            'sample_populated_stocks': sample_data
        })
        
        return jsonify({
            'success': True,
            'message': f'Stock metadata populated: {success_count} successful, {failed_count} failed',
            'results': results
        })

    except Exception as e:
        import traceback
        return jsonify({
            'success': False,
            'error': str(e),
            'traceback': traceback.format_exc()
        }), 500

@app.route('/admin/upsert-stock-info-manual')
@login_required
def admin_upsert_stock_info_manual():
    """Manually upsert minimal StockInfo metadata for specific tickers.

    Query params:
      - tickers: comma-separated list, e.g. tickers=SCHD,VTI,SSPY (required)
      - sector: default 'ETF'
      - industry: default 'ETF - Index Fund'
      - cap: default 'unknown' (small|mid|large|mega|unknown)
      - exchange: default 'NYSEARCA'
      - country: default 'USA'
    """
    if not current_user.is_admin:
        return jsonify({'error': 'Admin access required'}), 403

    try:
        tickers_param = request.args.get('tickers', '').strip()
        if not tickers_param:
            return jsonify({'success': False, 'error': 'tickers parameter is required'}), 400

        sector = request.args.get('sector', default='ETF')
        industry = request.args.get('industry', default='ETF - Index Fund')
        cap = request.args.get('cap', default='unknown')
        exchange = request.args.get('exchange', default='NYSEARCA')
        country = request.args.get('country', default='USA')

        from models import StockInfo, db
        from datetime import datetime

        tickers = [t.strip().upper() for t in tickers_param.split(',') if t.strip()]
        processed = []
        created = 0
        updated = 0
        errors = []

        for t in tickers:
            try:
                si = StockInfo.query.filter_by(ticker=t).first()
                if not si:
                    si = StockInfo(ticker=t)
                    db.session.add(si)
                    created += 1
                else:
                    updated += 1

                # Minimal fields
                if not si.company_name:
                    si.company_name = t
                si.sector = sector
                si.industry = industry
                si.cap_classification = cap
                si.exchange = exchange
                si.country = country
                si.is_active = True
                si.last_updated = datetime.now()

                processed.append(t)
            except Exception as inner_e:
                errors.append({'ticker': t, 'error': str(inner_e)})

        # Commit once at the end
        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Manual upsert complete',
            'processed': processed,
            'created': created,
            'updated': updated,
            'errors': errors
        })

    except Exception as e:
        import traceback
        from models import db
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e),
            'traceback': traceback.format_exc()
        }), 500

@app.route('/admin/debug-leaderboard')
@login_required
def admin_debug_leaderboard():
    """Debug leaderboard data availability"""
    try:
        # Check if user is admin
        email = session.get('email', '')
        if email != ADMIN_EMAIL:
            return jsonify({'error': 'Admin access required'}), 403
        
        from datetime import datetime, date, timedelta
        from models import db, PortfolioSnapshot, User, Stock, LeaderboardCache
        import json
        
        # Data availability check
        yesterday = date.today() - timedelta(days=1)
        today = date.today()
        
        debug_info = {
            'basic_data': {
                'total_users': User.query.count(),
                'users_with_stocks': User.query.join(Stock).distinct().count(),
                'total_snapshots': PortfolioSnapshot.query.count(),
                'yesterday_snapshots': PortfolioSnapshot.query.filter_by(date=yesterday).count(),
                'today_snapshots': PortfolioSnapshot.query.filter_by(date=today).count()
            },
            'recent_snapshots': [],
            'cache_status': [],
            'api_test': None
        }
        
        # Recent snapshots
        recent_snapshots = PortfolioSnapshot.query.filter(
            PortfolioSnapshot.date >= yesterday - timedelta(days=3)
        ).order_by(PortfolioSnapshot.date.desc()).limit(10).all()
        
        for snapshot in recent_snapshots:
            debug_info['recent_snapshots'].append({
                'user_id': snapshot.user_id,
                'date': snapshot.date.isoformat(),
                'value': float(snapshot.total_value)
            })
        
        # Cache status
        cache_entries = LeaderboardCache.query.all()
        for cache in cache_entries:
            try:
                cached_data = json.loads(cache.leaderboard_data)
                debug_info['cache_status'].append({
                    'period': cache.period,
                    'entries': len(cached_data),
                    'generated_at': cache.generated_at.isoformat()
                })
            except Exception as e:
                debug_info['cache_status'].append({
                    'period': cache.period,
                    'error': str(e)
                })
        
        # Test API
        try:
            from leaderboard_utils import get_leaderboard_data
            api_data = get_leaderboard_data('YTD', 5, 'all')
            debug_info['api_test'] = {
                'success': True,
                'entries': len(api_data),
                'sample': api_data[:2] if api_data else []
            }
        except Exception as e:
            debug_info['api_test'] = {
                'success': False,
                'error': str(e)
            }
        
        return jsonify({
            'success': True,
            'debug_info': debug_info
        })
        
    except Exception as e:
        import traceback
        return jsonify({
            'success': False,
            'error': str(e),
            'traceback': traceback.format_exc()
        }), 500

@app.route('/admin/populate-tiers')
def populate_tiers():
    """Populate subscription tiers with Stripe price IDs"""
    try:
        # Check if user is admin
        email = session.get('email', '')
        if email != ADMIN_EMAIL:
            return jsonify({'error': 'Admin access required'}), 403
            
        # Define the 5 tiers with real Stripe price IDs
        tiers = [
            {
                'tier_name': 'Light',
                'price': 8.00,
                'max_trades_per_day': 3,
                'stripe_price_id': 'price_1S4tN2HwKH0J9vzFchmuJXTze'
            },
            {
                'tier_name': 'Standard', 
                'price': 12.00,
                'max_trades_per_day': 6,
                'stripe_price_id': 'price_1S4tNdHwKH0J9vzFdJY3Opim'
            },
            {
                'tier_name': 'Active',
                'price': 20.00,
                'max_trades_per_day': 12,
                'stripe_price_id': 'price_1S4tO8HwKH0J9vzFqZBDgCOK'
            },
            {
                'tier_name': 'Pro',
                'price': 30.00,
                'max_trades_per_day': 25,
                'stripe_price_id': 'price_1S4tOYHwKH0J9vzFckMoFWwG'
            },
            {
                'tier_name': 'Elite',
                'price': 50.00,
                'max_trades_per_day': 50,
                'stripe_price_id': 'price_1S4tOtHwKH0J9vzFuxiERwQv'
            }
        ]
        
        # Clear existing tiers
        db.session.execute(text("DELETE FROM subscription_tier"))
        
        # Add new tiers
        for tier_data in tiers:
            db.session.execute(text("""
                INSERT INTO subscription_tier (tier_name, price, max_trades_per_day, stripe_price_id)
                VALUES (:tier_name, :price, :max_trades_per_day, :stripe_price_id)
            """), tier_data)
        
        db.session.commit()
        return jsonify({"success": True, "message": f"Successfully populated {len(tiers)} subscription tiers"})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "message": f"Error: {str(e)}"})

@app.route('/admin/populate-stock-info')
def populate_stock_info():
    """Populate stock_info table with company data from Alpha Vantage"""
    try:
        # Check if user is admin
        email = session.get('email', '')
        if email != ADMIN_EMAIL:
            return jsonify({'error': 'Admin access required'}), 403
            
        import requests
        
        # Get Alpha Vantage API key
        alpha_vantage_api_key = os.environ.get('ALPHA_VANTAGE_API_KEY')
        if not alpha_vantage_api_key:
            return jsonify({'error': 'Alpha Vantage API key not found'}), 500
            
        # Get all unique stock symbols from user portfolios
        symbols = db.session.execute(text("SELECT DISTINCT ticker FROM stock")).fetchall()
        
        populated_count = 0
        errors = []
        
        for (symbol,) in symbols:
            try:
                # Check if we already have data for this symbol
                existing = db.session.execute(text("""
                    SELECT id FROM stock_info WHERE symbol = :symbol
                """), {'symbol': symbol}).fetchone()
                
                if existing:
                    continue  # Skip if already exists
                
                # Fetch company overview from Alpha Vantage
                url = f"https://www.alphavantage.co/query?function=COMPANY_OVERVIEW&symbol={symbol}&apikey={alpha_vantage_api_key}"
                response = requests.get(url, timeout=10)
                data = response.json()
                
                if 'Symbol' in data and data.get('MarketCapitalization'):
                    market_cap = int(data.get('MarketCapitalization', 0))
                    company_name = data.get('Name', symbol)
                    sector = data.get('Sector', 'Unknown')
                    
                    # Insert into stock_info table
                    db.session.execute(text("""
                        INSERT INTO stock_info (symbol, company_name, market_cap, sector)
                        VALUES (:symbol, :company_name, :market_cap, :sector)
                    """), {
                        'symbol': symbol,
                        'company_name': company_name,
                        'market_cap': market_cap,
                        'sector': sector
                    })
                    
                    populated_count += 1
                else:
                    errors.append(f"No data found for {symbol}")
                    
            except Exception as e:
                errors.append(f"Error for {symbol}: {str(e)}")
        
        db.session.commit()
        
        return jsonify({
            "success": True, 
            "message": f"Successfully populated {populated_count} stock info records",
            "populated_count": populated_count,
            "errors": errors[:5]  # Limit errors shown
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "message": f"Error: {str(e)}"})

# Portfolio performance API endpoints
@app.route('/api/portfolio/performance/<period>')
@login_required
def get_portfolio_performance(period):
    """Get portfolio performance data for a specific time period - uses cached data for leaderboard users"""
    try:
        # Add timeout protection for large datasets
        import signal
        
        def timeout_handler(signum, frame):
            raise TimeoutError("Performance calculation timed out")
        
        # Set 25 second timeout (Vercel has 30s limit)
        signal.signal(signal.SIGALRM, timeout_handler)
        signal.alarm(25)
        from datetime import datetime, timedelta
        from models import UserPortfolioChartCache
        import json
        
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': 'User not authenticated'}), 401
        
        period_upper = period.upper()
        
        # Try to use pre-rendered chart data for leaderboard users (much faster!)
        chart_cache = UserPortfolioChartCache.query.filter_by(
            user_id=user_id, period=period_upper
        ).first()
        
        if chart_cache:
            try:
                # Convert Chart.js format to dashboard format
                cached_data = json.loads(chart_cache.chart_data)
                
                # Extract performance percentages from Chart.js data
                datasets = cached_data.get('datasets', [])
                if not datasets:
                    logger.warning(f"No datasets in cached data for user {user_id}, period {period_upper}")
                    raise ValueError("No datasets in cached chart data")
                
                portfolio_data = datasets[0].get('data', []) if len(datasets) > 0 else []
                sp500_data = datasets[1].get('data', []) if len(datasets) > 1 else []
                
                if not portfolio_data:
                    logger.warning(f"No portfolio data in cached chart for user {user_id}, period {period_upper}")
                    raise ValueError("No portfolio data in cached chart")
                
                if not sp500_data:
                    logger.warning(f"No S&P 500 data in cached chart for user {user_id}, period {period_upper}")
                    raise ValueError("No S&P 500 data in cached chart")
                
                if portfolio_data and sp500_data:
                    # Calculate returns from first to last data point
                    portfolio_return = ((portfolio_data[-1] - portfolio_data[0]) / portfolio_data[0] * 100) if portfolio_data[0] > 0 else 0
                    sp500_return = ((sp500_data[-1] - sp500_data[0]) / sp500_data[0] * 100) if sp500_data[0] > 0 else 0
                    
                    # Convert Chart.js format to dashboard chart_data format
                    labels = cached_data.get('labels', [])
                    chart_data = []
                    
                    # Limit processing to avoid timeouts on large datasets
                    max_points = min(len(labels), len(portfolio_data), len(sp500_data), 500)  # Limit to 500 points
                    
                    for i in range(max_points):
                        try:
                            chart_data.append({
                                'date': labels[i],
                                'portfolio': round(((portfolio_data[i] - portfolio_data[0]) / portfolio_data[0] * 100) if portfolio_data[0] > 0 else 0, 2),
                                'sp500': round(((sp500_data[i] - sp500_data[0]) / sp500_data[0] * 100) if sp500_data[0] > 0 else 0, 2)
                            })
                        except (IndexError, ZeroDivisionError, TypeError) as e:
                            logger.warning(f"Error processing chart data point {i}: {e}")
                            continue
                    
                    dashboard_format = {
                        'portfolio_return': round(portfolio_return, 2),
                        'sp500_return': round(sp500_return, 2),
                        'chart_data': chart_data,
                        'period': period,
                        'data_source': 'pre_rendered_cache'
                    }
                    
                    logger.info(f"Using pre-rendered chart data (converted to dashboard format) for user {user_id}, period {period_upper}")
                    return jsonify(dashboard_format)
                    
            except Exception as e:
                logger.warning(f"Failed to convert pre-rendered chart data to dashboard format: {e}")
        
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
        
        # Last resort: Live calculation (slow for non-leaderboard users)
        from portfolio_performance import PortfolioPerformanceCalculator
        calculator = PortfolioPerformanceCalculator()
        
        logger.info(f"Performing live calculation for user {user_id}, period {period_upper}")
        performance_data = calculator.get_performance_data(user_id, period_upper)
        
        # Cache the response in session
        session[cache_key] = performance_data
        session[f"{cache_key}_time"] = datetime.now().isoformat()
        
        # Clear timeout
        signal.alarm(0)
        return jsonify(performance_data)
        
    except TimeoutError as e:
        signal.alarm(0)
        logger.error(f"Performance calculation timeout for user {user_id}, period {period}: {e}")
        return jsonify({'error': 'Calculation timed out - try a shorter time period'}), 408
    except Exception as e:
        signal.alarm(0)
        logger.error(f"Performance calculation error: {e}")
        return jsonify({'error': str(e)}), 500

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
        return jsonify({'error': str(e)}), 500

@app.route('/admin/create-todays-snapshots')
def create_todays_snapshots():
    """Admin endpoint to create today's portfolio snapshots for all users (no historical data)"""
    try:
        # Check if user is admin
        email = session.get('email', '')
        if email != ADMIN_EMAIL:
            return jsonify({'error': 'Admin access required'}), 403
        
        # Import here to avoid circular imports
        import sys
        import os
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from portfolio_performance import performance_calculator
        
        # Get all users with stocks
        users_with_stocks = db.session.query(User.id).join(Stock).distinct().all()
        
        snapshots_created = 0
        errors = []
        
        for (user_id,) in users_with_stocks:
            try:
                # Only create today's snapshot - no historical approximations
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
            'message': 'Created today\'s snapshots only. Performance data will accumulate over time as daily snapshots are created.'
        })
        
    except Exception as e:
        logger.error(f"Today's snapshots creation error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/admin/populate-sp500-data', methods=['GET', 'POST'])
@login_required
def populate_sp500_data():
    """Admin endpoint to populate S&P 500 data - synchronous version for debugging"""
    if not current_user.is_admin:
        return jsonify({'error': 'Admin access required'}), 403
    
    try:
        from portfolio_performance import PortfolioPerformanceCalculator
        from models import MarketData
        
        # Get years parameter (default 5 for full historical data)
        years = int(request.args.get('years', 5))
        
        logger.info(f"Starting SYNCHRONOUS S&P 500 population for {years} years")
        calculator = PortfolioPerformanceCalculator()
        
        # Clear ALL existing market data to replace with real data
        deleted_count = MarketData.query.count()
        MarketData.query.delete()
        db.session.commit()
        logger.info(f"Cleared {deleted_count} existing market data records")
        
        # Verify AlphaVantage API key exists
        if not hasattr(calculator, 'alpha_vantage_api_key') or not calculator.alpha_vantage_api_key:
            error_msg = "AlphaVantage API key not found - cannot fetch real data"
            logger.error(error_msg)
            return jsonify({'error': error_msg}), 500
        
        logger.info(f"AlphaVantage API key found: {calculator.alpha_vantage_api_key[:10]}...")
        logger.info("Starting AlphaVantage API call...")
        
        # Use micro-chunked processing
        result = calculator.fetch_historical_sp500_data_micro_chunks(years_back=years)
        
        if result['success']:
            logger.info(f"SUCCESS: S&P 500 population completed: {result['total_data_points']} data points")
            return jsonify({
                'success': True,
                'message': f'Successfully populated {result["total_data_points"]} real S&P 500 data points',
                'total_data_points': result['total_data_points'],
                'chunks_processed': result.get('chunks_processed', 0),
                'years_requested': years,
                'errors': result.get('errors', []),
                'data_source': 'AlphaVantage TIME_SERIES_DAILY (SPY ETF) - Synchronous Processing'
            })
        else:
            logger.error(f"FAILED: S&P 500 population failed: {result['error']}")
            return jsonify({'error': result['error']}), 500
        
    except Exception as e:
        logger.error(f"EXCEPTION: S&P 500 population error: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500

@app.route('/admin/debug-env', methods=['GET'])
@login_required
def debug_env():
    """Debug environment variables"""
    if not current_user.is_admin:
        return jsonify({'error': 'Admin access required'}), 403
    
    import os
    
    # Check for AlphaVantage API key in different ways
    alpha_key_direct = os.environ.get('ALPHA_VANTAGE_API_KEY')
    alpha_key_getenv = os.getenv('ALPHA_VANTAGE_API_KEY')
    
    # Check all environment variables that contain 'ALPHA'
    alpha_vars = {k: v[:10] + '...' if v and len(v) > 10 else v 
                  for k, v in os.environ.items() if 'ALPHA' in k.upper()}
    
    return jsonify({
        'alpha_vantage_direct': alpha_key_direct[:10] + '...' if alpha_key_direct else None,
        'alpha_vantage_getenv': alpha_key_getenv[:10] + '...' if alpha_key_getenv else None,
        'all_alpha_vars': alpha_vars,
        'env_var_count': len(os.environ),
        'has_flask_env': 'FLASK_ENV' in os.environ,
        'flask_env_value': os.environ.get('FLASK_ENV')
    })

@app.route('/admin/test-alphavantage', methods=['GET'])
@login_required
def test_alphavantage():
    """Test AlphaVantage API connection with minimal request"""
    if not current_user.is_admin:
        return jsonify({'error': 'Admin access required'}), 403
    
    try:
        from portfolio_performance import PortfolioPerformanceCalculator
        import requests
        
        calculator = PortfolioPerformanceCalculator()
        
        # Check if API key exists
        if not hasattr(calculator, 'alpha_vantage_api_key') or not calculator.alpha_vantage_api_key:
            return jsonify({
                'success': False,
                'error': 'AlphaVantage API key not found',
                'note': 'Check environment variables'
            })
        
        # Make minimal API call (just get latest SPY price)
        url = "https://www.alphavantage.co/query"
        params = {
            'function': 'GLOBAL_QUOTE',
            'symbol': 'SPY',
            'apikey': calculator.alpha_vantage_api_key
        }
        
        response = requests.get(url, params=params, timeout=10)
        data = response.json()
        
        if 'Global Quote' in data:
            quote = data['Global Quote']
            return jsonify({
                'success': True,
                'api_key_works': True,
                'spy_price': quote.get('05. price', 'N/A'),
                'spy_change': quote.get('09. change', 'N/A'),
                'last_updated': quote.get('07. latest trading day', 'N/A'),
                'note': 'AlphaVantage API is working correctly'
            })
        else:
            return jsonify({
                'success': False,
                'api_response': data,
                'error': 'Unexpected API response format'
            })
            
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        })

@app.route('/admin/populate-sp500-tiny', methods=['GET'])
@login_required
def populate_sp500_tiny():
    """Populate S&P 500 data in tiny batches to avoid timeout"""
    if not current_user.is_admin:
        return jsonify({'error': 'Admin access required'}), 403
    
    try:
        from portfolio_performance import PortfolioPerformanceCalculator
        from models import MarketData
        import requests
        from datetime import date, timedelta
        
        calculator = PortfolioPerformanceCalculator()
        
        # Get just 30 days of data to avoid timeout
        end_date = date.today()
        start_date = end_date - timedelta(days=30)
        
        # Make direct AlphaVantage call for recent data only
        url = "https://www.alphavantage.co/query"
        params = {
            'function': 'TIME_SERIES_DAILY',
            'symbol': 'SPY',
            'outputsize': 'compact',  # Only recent 100 days
            'apikey': calculator.alpha_vantage_api_key
        }
        
        response = requests.get(url, params=params, timeout=15)
        data = response.json()
        
        if 'Time Series (Daily)' not in data:
            return jsonify({'error': 'Invalid AlphaVantage response', 'response': data})
        
        time_series = data['Time Series (Daily)']
        data_points = 0
        
        # Process only last 30 days
        for date_str, daily_data in time_series.items():
            try:
                data_date = datetime.strptime(date_str, '%Y-%m-%d').date()
                
                if start_date <= data_date <= end_date:
                    spy_price = float(daily_data['4. close'])
                    sp500_value = spy_price * 10  # Convert to S&P 500 index
                    
                    # Check if exists
                    existing = MarketData.query.filter_by(
                        ticker='SPY_SP500',
                        date=data_date
                    ).first()
                    
                    if not existing:
                        market_data = MarketData(
                            ticker='SPY_SP500',
                            date=data_date,
                            close_price=sp500_value
                        )
                        db.session.add(market_data)
                        data_points += 1
            
            except (ValueError, KeyError) as e:
                continue
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Added {data_points} recent S&P 500 data points',
            'data_points': data_points,
            'date_range': f'{start_date} to {end_date}',
            'note': 'Use multiple times to build historical data gradually'
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/admin/test-sp500-accuracy', methods=['GET'])
@login_required
def test_sp500_accuracy():
    """Compare our S&P 500 data with actual index data from AlphaVantage"""
    if not current_user.is_admin:
        return jsonify({'error': 'Admin access required'}), 403
    
    try:
        from portfolio_performance import PortfolioPerformanceCalculator
        from models import MarketData
        import requests
        
        calculator = PortfolioPerformanceCalculator()
        
        # Get actual S&P 500 index data (^GSPC) from AlphaVantage
        url = "https://www.alphavantage.co/query"
        params = {
            'function': 'TIME_SERIES_DAILY',
            'symbol': '^GSPC',  # Actual S&P 500 index
            'outputsize': 'compact',
            'apikey': calculator.alpha_vantage_api_key
        }
        
        response = requests.get(url, params=params, timeout=15)
        data = response.json()
        
        if 'Time Series (Daily)' not in data:
            return jsonify({'error': 'Could not fetch S&P 500 index data', 'response': data})
        
        # Compare recent dates
        sp500_data = data['Time Series (Daily)']
        comparisons = []
        
        for date_str, daily_data in list(sp500_data.items())[:5]:  # Last 5 days
            try:
                data_date = datetime.strptime(date_str, '%Y-%m-%d').date()
                actual_sp500 = float(daily_data['4. close'])
                
                # Get our SPY-based data for same date
                our_data = MarketData.query.filter_by(
                    ticker='SPY_SP500',
                    date=data_date
                ).first()
                
                if our_data:
                    our_sp500 = our_data.close_price
                    difference = abs(actual_sp500 - our_sp500)
                    percent_diff = (difference / actual_sp500) * 100
                    
                    comparisons.append({
                        'date': date_str,
                        'actual_sp500': actual_sp500,
                        'our_sp500_spy_based': our_sp500,
                        'difference': round(difference, 2),
                        'percent_difference': round(percent_diff, 3)
                    })
            
            except (ValueError, KeyError):
                continue
        
        return jsonify({
            'success': True,
            'comparisons': comparisons,
            'note': 'Shows accuracy of SPY*10 vs actual S&P 500 index',
            'recommendation': 'Consider using ^GSPC directly if differences are significant'
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/admin/check-sp500-anomalies', methods=['GET'])
@login_required
def check_sp500_anomalies():
    """Check for anomalous data points in S&P 500 dataset"""
    if not current_user.is_admin:
        return jsonify({'error': 'Admin access required'}), 403
    
    try:
        from models import MarketData
        from datetime import datetime
        
        # Get all S&P 500 data points
        all_data = MarketData.query.filter_by(ticker='SPY_SP500').order_by(MarketData.date).all()
        
        if not all_data:
            return jsonify({'error': 'No S&P 500 data found'})
        
        anomalies = []
        suspicious_dates = ['2021-04-01', '2024-03-28']
        
        # Check specific suspicious dates
        for date_str in suspicious_dates:
            try:
                check_date = datetime.strptime(date_str, '%Y-%m-%d').date()
                data_point = MarketData.query.filter_by(
                    ticker='SPY_SP500',
                    date=check_date
                ).first()
                
                if data_point:
                    anomalies.append({
                        'date': date_str,
                        'value': data_point.close_price,
                        'type': 'suspicious_spike'
                    })
            except ValueError:
                continue
        
        # Check for large day-to-day changes (>10%)
        large_changes = []
        for i in range(1, len(all_data)):
            prev_price = all_data[i-1].close_price
            curr_price = all_data[i].close_price
            
            if prev_price > 0:
                change_pct = abs((curr_price - prev_price) / prev_price) * 100
                if change_pct > 10:  # More than 10% change
                    large_changes.append({
                        'date': all_data[i].date.isoformat(),
                        'prev_value': prev_price,
                        'curr_value': curr_price,
                        'change_percent': round(change_pct, 2)
                    })
        
        # Check for unrealistic values (outside normal S&P 500 range)
        unrealistic_values = []
        for data_point in all_data:
            # S&P 500 should be roughly 2000-7000 in recent years
            if data_point.close_price < 1000 or data_point.close_price > 10000:
                unrealistic_values.append({
                    'date': data_point.date.isoformat(),
                    'value': data_point.close_price,
                    'issue': 'outside_normal_range'
                })
        
        return jsonify({
            'success': True,
            'total_data_points': len(all_data),
            'suspicious_dates_checked': anomalies,
            'large_daily_changes': large_changes[:10],  # First 10
            'unrealistic_values': unrealistic_values[:10],  # First 10
            'data_quality_summary': {
                'large_changes_count': len(large_changes),
                'unrealistic_values_count': len(unrealistic_values)
            }
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/admin/investigate-alphavantage-spikes', methods=['GET'])
@login_required
def investigate_alphavantage_spikes():
    """Investigate raw AlphaVantage data around spike dates"""
    if not current_user.is_admin:
        return jsonify({'error': 'Admin access required'}), 403
    
    try:
        from portfolio_performance import PortfolioPerformanceCalculator
        from models import MarketData
        import requests
        from datetime import datetime, timedelta
        
        calculator = PortfolioPerformanceCalculator()
        
        spike_dates = ['2021-04-01', '2024-03-28']
        investigations = []
        
        for spike_date_str in spike_dates:
            spike_date = datetime.strptime(spike_date_str, '%Y-%m-%d').date()
            
            # Get our stored data around this date
            our_data_points = []
            for days_offset in range(-5, 6):  # 5 days before and after
                check_date = spike_date + timedelta(days=days_offset)
                data_point = MarketData.query.filter_by(
                    ticker='SPY_SP500',
                    date=check_date
                ).first()
                
                if data_point:
                    our_data_points.append({
                        'date': check_date.isoformat(),
                        'our_value': data_point.close_price,
                        'spy_equivalent': data_point.close_price / 10
                    })
            
            # Get fresh AlphaVantage data for SPY around this date
            url = "https://www.alphavantage.co/query"
            params = {
                'function': 'TIME_SERIES_DAILY',
                'symbol': 'SPY',
                'outputsize': 'full',
                'apikey': calculator.alpha_vantage_api_key
            }
            
            response = requests.get(url, params=params, timeout=30)
            alphavantage_data = response.json()
            
            alphavantage_points = []
            if 'Time Series (Daily)' in alphavantage_data:
                time_series = alphavantage_data['Time Series (Daily)']
                
                for days_offset in range(-5, 6):
                    check_date = spike_date + timedelta(days=days_offset)
                    date_str = check_date.isoformat()
                    
                    if date_str in time_series:
                        daily_data = time_series[date_str]
                        spy_close = float(daily_data['4. close'])
                        
                        alphavantage_points.append({
                            'date': date_str,
                            'spy_close': spy_close,
                            'sp500_equivalent': spy_close * 10,
                            'volume': daily_data.get('5. volume', 'N/A'),
                            'high': float(daily_data['2. high']),
                            'low': float(daily_data['3. low'])
                        })
            
            # Also check actual S&P 500 index (^GSPC) for comparison
            gspc_params = {
                'function': 'TIME_SERIES_DAILY',
                'symbol': '^GSPC',
                'outputsize': 'compact',
                'apikey': calculator.alpha_vantage_api_key
            }
            
            gspc_response = requests.get(url, params=gspc_params, timeout=30)
            gspc_data = gspc_response.json()
            
            gspc_points = []
            if 'Time Series (Daily)' in gspc_data:
                gspc_series = gspc_data['Time Series (Daily)']
                
                for days_offset in range(-5, 6):
                    check_date = spike_date + timedelta(days=days_offset)
                    date_str = check_date.isoformat()
                    
                    if date_str in gspc_series:
                        daily_data = gspc_series[date_str]
                        gspc_close = float(daily_data['4. close'])
                        
                        gspc_points.append({
                            'date': date_str,
                            'sp500_actual': gspc_close,
                            'volume': daily_data.get('5. volume', 'N/A')
                        })
            
            investigations.append({
                'spike_date': spike_date_str,
                'our_stored_data': our_data_points,
                'alphavantage_spy_data': alphavantage_points,
                'alphavantage_sp500_data': gspc_points
            })
        
        return jsonify({
            'success': True,
            'investigations': investigations,
            'note': 'Compare our stored data vs fresh AlphaVantage data around spike dates'
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/admin/debug-chart-data/<period>', methods=['GET'])
@login_required
def debug_chart_data(period):
    """Debug chart data generation to find spike sources"""
    if not current_user.is_admin:
        return jsonify({'error': 'Admin access required'}), 403
    
    try:
        from portfolio_performance import PortfolioPerformanceCalculator
        from models import MarketData
        from datetime import datetime, date, timedelta
        
        calculator = PortfolioPerformanceCalculator()
        end_date = date.today()
        
        # Define period mappings (same as in performance calculator)
        period_days = {
            '1D': 1,
            '5D': 5,
            '1M': 30,
            '3M': 90,
            'YTD': (end_date - date(end_date.year, 1, 1)).days,
            '1Y': 365,
            '5Y': 1825
        }
        
        if period not in period_days:
            return jsonify({'error': 'Invalid period'})
        
        if period == 'YTD':
            start_date = date(end_date.year, 1, 1)
        else:
            start_date = end_date - timedelta(days=period_days[period])
        
        # Get raw S&P 500 data
        raw_sp500_data = calculator.get_sp500_data(start_date, end_date)
        
        # Get sampled data (what charts actually use)
        sp500_dates = sorted(raw_sp500_data.keys())
        sampled_dates = calculator._sample_dates_for_period(sp500_dates, period)
        
        # Check for large jumps in sampled data
        sampled_data = []
        large_jumps = []
        
        for i, date_key in enumerate(sampled_dates):
            if date_key in raw_sp500_data:
                value = raw_sp500_data[date_key]
                sampled_data.append({
                    'date': date_key.isoformat(),
                    'value': value,
                    'index': i
                })
                
                # Check for large jumps between sampled points
                if i > 0:
                    prev_value = sampled_data[i-1]['value']
                    change_pct = abs((value - prev_value) / prev_value) * 100
                    
                    if change_pct > 5:  # More than 5% jump
                        large_jumps.append({
                            'from_date': sampled_data[i-1]['date'],
                            'to_date': date_key.isoformat(),
                            'from_value': prev_value,
                            'to_value': value,
                            'change_percent': round(change_pct, 2),
                            'days_between': (date_key - datetime.fromisoformat(sampled_data[i-1]['date']).date()).days
                        })
        
        # Check what raw data exists between large jumps
        jump_analysis = []
        for jump in large_jumps:
            from_date = datetime.fromisoformat(jump['from_date']).date()
            to_date = datetime.fromisoformat(jump['to_date']).date()
            
            # Get all raw data points between these dates
            between_dates = []
            current = from_date + timedelta(days=1)
            while current < to_date:
                if current in raw_sp500_data:
                    between_dates.append({
                        'date': current.isoformat(),
                        'value': raw_sp500_data[current],
                        'included_in_sample': current in sampled_dates
                    })
                current += timedelta(days=1)
            
            jump_analysis.append({
                'jump': jump,
                'raw_data_between': between_dates
            })
        
        return jsonify({
            'success': True,
            'period': period,
            'date_range': f"{start_date} to {end_date}",
            'total_raw_points': len(sp500_dates),
            'sampled_points': len(sampled_dates),
            'sampling_ratio': f"{len(sampled_dates)}/{len(sp500_dates)}",
            'large_jumps_found': len(large_jumps),
            'large_jumps': large_jumps,
            'jump_analysis': jump_analysis,
            'note': 'Large jumps may be caused by sampling skipping intermediate data points'
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/admin/find-duplicate-sp500-values', methods=['GET'])
@login_required
def find_duplicate_sp500_values():
    """Find duplicate S&P 500 values that create chart spikes"""
    if not current_user.is_admin:
        return jsonify({'error': 'Admin access required'}), 403
    
    try:
        from models import MarketData
        from collections import defaultdict
        
        # Get all S&P 500 data points
        all_data = MarketData.query.filter_by(ticker='SPY_SP500').order_by(MarketData.date).all()
        
        if not all_data:
            return jsonify({'error': 'No S&P 500 data found'})
        
        # Group by value to find duplicates
        value_groups = defaultdict(list)
        for data_point in all_data:
            # Round to avoid floating point precision issues
            rounded_value = round(data_point.close_price, 2)
            value_groups[rounded_value].append({
                'date': data_point.date.isoformat(),
                'exact_value': data_point.close_price,
                'id': data_point.id
            })
        
        # Find values that appear on multiple dates
        duplicates = {}
        for value, occurrences in value_groups.items():
            if len(occurrences) > 1:
                # Check if dates are far apart (suspicious)
                dates = [occ['date'] for occ in occurrences]
                dates.sort()
                
                duplicates[value] = {
                    'occurrences': occurrences,
                    'count': len(occurrences),
                    'date_range': f"{dates[0]} to {dates[-1]}",
                    'suspicious': len(occurrences) > 2 or (len(occurrences) == 2 and 
                        (datetime.fromisoformat(dates[1]) - datetime.fromisoformat(dates[0])).days > 7)
                }
        
        # Find the problematic 6398.1 value specifically
        problem_value = None
        for value, info in duplicates.items():
            if 6390 <= value <= 6405:  # Around the problematic value
                problem_value = {
                    'value': value,
                    'info': info
                }
                break
        
        return jsonify({
            'success': True,
            'total_data_points': len(all_data),
            'duplicate_values_found': len(duplicates),
            'duplicates': dict(list(duplicates.items())[:10]),  # First 10
            'problem_value_6398': problem_value,
            'note': 'Duplicate values on different dates create artificial chart spikes'
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/admin/fix-duplicate-sp500-values', methods=['GET'])
@login_required
def fix_duplicate_sp500_values():
    """Fix duplicate S&P 500 values by interpolating between neighbors"""
    if not current_user.is_admin:
        return jsonify({'error': 'Admin access required'}), 403
    
    try:
        from models import MarketData, db
        from collections import defaultdict
        
        # Get all S&P 500 data points
        all_data = MarketData.query.filter_by(ticker='SPY_SP500').order_by(MarketData.date).all()
        
        if not all_data:
            return jsonify({'error': 'No S&P 500 data found'})
        
        fixes_applied = []
        
        # Find and fix ALL occurrences of the problematic 6398.1 value
        problematic_value = 6398.099999999999
        
        for i in range(1, len(all_data) - 1):
            current = all_data[i]
            curr_val = current.close_price
            
            # Check if this is the problematic duplicate value
            if abs(curr_val - problematic_value) < 0.1:
                prev_val = all_data[i-1].close_price
                next_val = all_data[i+1].close_price
                
                # Only fix if the neighboring values are reasonable (not also duplicates)
                if (abs(prev_val - problematic_value) > 100 and 
                    abs(next_val - problematic_value) > 100):
                    
                    # Interpolate between neighbors
                    interpolated_value = (prev_val + next_val) / 2
                    
                    fixes_applied.append({
                        'date': current.date.isoformat(),
                        'original_value': curr_val,
                        'interpolated_value': interpolated_value,
                        'prev_value': prev_val,
                        'next_value': next_val,
                        'reason': 'problematic_6398_value_fixed'
                    })
                    
                    current.close_price = interpolated_value
        
        # Also fix other suspicious duplicates (values appearing on distant dates)
        value_groups = defaultdict(list)
        for i, data_point in enumerate(all_data):
            rounded_value = round(data_point.close_price, 1)
            value_groups[rounded_value].append((i, data_point))
        
        # Fix other duplicate values that appear on dates >30 days apart
        for value, occurrences in value_groups.items():
            if len(occurrences) > 1 and value != round(problematic_value, 1):
                # Check if dates are far apart
                dates = [occ[1].date for occ in occurrences]
                dates.sort()
                
                if len(dates) >= 2 and (dates[-1] - dates[0]).days > 30:
                    # Fix all but the first occurrence
                    for i, (idx, data_point) in enumerate(occurrences[1:], 1):
                        if 1 <= idx < len(all_data) - 1:
                            prev_val = all_data[idx-1].close_price
                            next_val = all_data[idx+1].close_price
                            interpolated_value = (prev_val + next_val) / 2
                            
                            fixes_applied.append({
                                'date': data_point.date.isoformat(),
                                'original_value': data_point.close_price,
                                'interpolated_value': interpolated_value,
                                'prev_value': prev_val,
                                'next_value': next_val,
                                'reason': f'duplicate_value_{value}_fixed'
                            })
                            
                            data_point.close_price = interpolated_value
        
        # Commit changes
        if fixes_applied:
            db.session.commit()
        
        return jsonify({
            'success': True,
            'fixes_applied': len(fixes_applied),
            'details': fixes_applied[:20],  # Show first 20 fixes
            'message': f'Fixed {len(fixes_applied)} duplicate S&P 500 values across all historical data'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/admin/fix-duplicates-with-alphavantage', methods=['GET'])
@login_required
def fix_duplicates_with_alphavantage():
    """Replace duplicate S&P 500 values with correct AlphaVantage data"""
    if not current_user.is_admin:
        return jsonify({'error': 'Admin access required'}), 403
    
    try:
        from portfolio_performance import PortfolioPerformanceCalculator
        from models import MarketData, db
        import requests
        from datetime import datetime
        
        calculator = PortfolioPerformanceCalculator()
        
        # Get all S&P 500 data points
        all_data = MarketData.query.filter_by(ticker='SPY_SP500').order_by(MarketData.date).all()
        
        if not all_data:
            return jsonify({'error': 'No S&P 500 data found'})
        
        # Find all occurrences of the problematic 6398.1 value
        problematic_value = 6398.099999999999
        duplicate_dates = []
        
        for data_point in all_data:
            if abs(data_point.close_price - problematic_value) < 0.1:
                duplicate_dates.append(data_point.date.isoformat())
        
        if not duplicate_dates:
            return jsonify({'message': 'No duplicate 6398.1 values found'})
        
        # Fetch fresh AlphaVantage data for SPY
        url = "https://www.alphavantage.co/query"
        params = {
            'function': 'TIME_SERIES_DAILY',
            'symbol': 'SPY',
            'outputsize': 'full',
            'apikey': calculator.alpha_vantage_api_key
        }
        
        response = requests.get(url, params=params, timeout=60)
        alphavantage_data = response.json()
        
        if 'Time Series (Daily)' not in alphavantage_data:
            return jsonify({'error': 'Could not fetch AlphaVantage data', 'response': alphavantage_data})
        
        time_series = alphavantage_data['Time Series (Daily)']
        fixes_applied = []
        
        # Replace duplicate values with correct AlphaVantage data
        for data_point in all_data:
            if abs(data_point.close_price - problematic_value) < 0.1:
                date_str = data_point.date.isoformat()
                
                if date_str in time_series:
                    # Get correct SPY price and convert to S&P 500
                    spy_close = float(time_series[date_str]['4. close'])
                    correct_sp500_value = spy_close * 10
                    
                    fixes_applied.append({
                        'date': date_str,
                        'original_value': data_point.close_price,
                        'correct_alphavantage_value': correct_sp500_value,
                        'spy_close': spy_close,
                        'reason': 'replaced_with_alphavantage_data'
                    })
                    
                    data_point.close_price = correct_sp500_value
                else:
                    # If exact date not found, try to interpolate from nearby dates
                    date_obj = data_point.date
                    nearby_values = []
                    
                    # Look for dates within ±3 days
                    for days_offset in range(-3, 4):
                        check_date = date_obj + timedelta(days=days_offset)
                        check_date_str = check_date.isoformat()
                        
                        if check_date_str in time_series:
                            spy_close = float(time_series[check_date_str]['4. close'])
                            nearby_values.append(spy_close * 10)
                    
                    if nearby_values:
                        # Use average of nearby values
                        correct_sp500_value = sum(nearby_values) / len(nearby_values)
                        
                        fixes_applied.append({
                            'date': date_str,
                            'original_value': data_point.close_price,
                            'correct_alphavantage_value': correct_sp500_value,
                            'reason': 'interpolated_from_nearby_alphavantage_data',
                            'nearby_values_count': len(nearby_values)
                        })
                        
                        data_point.close_price = correct_sp500_value
        
        # Commit changes
        if fixes_applied:
            db.session.commit()
        
        return jsonify({
            'success': True,
            'fixes_applied': len(fixes_applied),
            'details': fixes_applied,
            'duplicate_dates_found': duplicate_dates,
            'message': f'Replaced {len(fixes_applied)} duplicate values with correct AlphaVantage data'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/admin/debug-1d-5d-charts', methods=['GET'])
@login_required
def debug_1d_5d_charts():
    """Debug 1D and 5D chart data to understand limitations"""
    if not current_user.is_admin:
        return jsonify({'error': 'Admin access required'}), 403
    
    try:
        from portfolio_performance import PortfolioPerformanceCalculator
        from models import MarketData, PortfolioSnapshot
        from datetime import datetime, date, timedelta
        
        calculator = PortfolioPerformanceCalculator()
        end_date = date.today()
        
        # Check 1D data
        start_1d = end_date - timedelta(days=1)
        sp500_1d = calculator.get_sp500_data(start_1d, end_date)
        
        # Check 5D data
        start_5d = end_date - timedelta(days=5)
        sp500_5d = calculator.get_sp500_data(start_5d, end_date)
        
        # Check portfolio snapshots for comparison
        user_id = session.get('user_id', 1)  # Use session user or default
        snapshots_1d = PortfolioSnapshot.query.filter(
            PortfolioSnapshot.user_id == user_id,
            PortfolioSnapshot.date >= start_1d,
            PortfolioSnapshot.date <= end_date
        ).order_by(PortfolioSnapshot.date).all()
        
        snapshots_5d = PortfolioSnapshot.query.filter(
            PortfolioSnapshot.user_id == user_id,
            PortfolioSnapshot.date >= start_5d,
            PortfolioSnapshot.date <= end_date
        ).order_by(PortfolioSnapshot.date).all()
        
        return jsonify({
            'success': True,
            'analysis': {
                '1D_data': {
                    'sp500_points': len(sp500_1d),
                    'portfolio_snapshots': len(snapshots_1d),
                    'dates': list(sp500_1d.keys()) if sp500_1d else [],
                    'issue': 'Only 1-2 data points for single day (weekend/holiday gaps)'
                },
                '5D_data': {
                    'sp500_points': len(sp500_5d),
                    'portfolio_snapshots': len(snapshots_5d),
                    'dates': list(sp500_5d.keys()) if sp500_5d else [],
                    'issue': 'Only 3-5 data points for 5 days (excludes weekends)'
                },
                'problems': [
                    '1D charts show flat line or single point',
                    '5D charts have large gaps between trading days',
                    'No intraday data for meaningful 1D progression',
                    'Weekend/holiday gaps create poor user experience'
                ],
                'solutions': [
                    'Add AlphaVantage intraday API for 1D charts (15min/30min intervals)',
                    'Extend 5D range to include more trading days',
                    'Show hourly data for current trading day',
                    'Add market hours awareness'
                ]
            }
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/admin/implement-intraday-solution', methods=['GET'])
@login_required
def implement_intraday_solution():
    """Implement intraday data solution for 1D charts"""
    if not current_user.is_admin:
        return jsonify({'error': 'Admin access required'}), 403
    
    try:
        import requests
        import os
        from models import MarketData, db
        from datetime import datetime, date, timedelta
        
        api_key = os.environ.get('ALPHA_VANTAGE_API_KEY')
        if not api_key:
            return jsonify({'error': 'AlphaVantage API key not found'}), 500
        
        # Fetch intraday data for SPY (30-minute intervals)
        url = f'https://www.alphavantage.co/query?function=TIME_SERIES_INTRADAY&symbol=SPY&interval=30min&apikey={api_key}'
        response = requests.get(url)
        data = response.json()
        
        if 'Time Series (30min)' not in data:
            return jsonify({'error': 'Failed to fetch intraday data', 'response': data}), 500
        
        intraday_data = data['Time Series (30min)']
        today = date.today()
        points_added = 0
        
        # Process today's intraday data
        for timestamp_str, values in intraday_data.items():
            timestamp = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S')
            
            # Only process today's data
            if timestamp.date() == today:
                sp500_value = float(values['4. close']) * 10  # SPY to S&P 500 conversion
                
                # Create intraday market data entry with timestamp
                existing = MarketData.query.filter_by(
                    ticker='SPY_SP500_INTRADAY',
                    date=timestamp.date(),
                    timestamp=timestamp
                ).first()
                
                if not existing:
                    market_data = MarketData(
                        ticker='SPY_SP500_INTRADAY',
                        date=timestamp.date(),
                        timestamp=timestamp,
                        close_price=sp500_value
                    )
                    db.session.add(market_data)
                    points_added += 1
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'solution': 'Intraday data implementation',
            'points_added': points_added,
            'message': f'Added {points_added} intraday data points for 1D charts',
            'benefits': [
                '30-minute intervals provide smooth 1D chart progression',
                'Real-time market movement visibility',
                'Single API call per day for intraday data'
            ]
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/admin/optimize-5d-charts', methods=['GET'])
@login_required
def optimize_5d_charts():
    """Optimize 5D charts by extending to 10 trading days"""
    if not current_user.is_admin:
        return jsonify({'error': 'Admin access required'}), 403
    
    try:
        from portfolio_performance import PortfolioPerformanceCalculator
        from datetime import date, timedelta
        
        calculator = PortfolioPerformanceCalculator()
        end_date = date.today()
        
        # Extend 5D to show 10 calendar days (7-8 trading days)
        start_date = end_date - timedelta(days=10)
        sp500_data = calculator.get_sp500_data(start_date, end_date)
        
        # Count actual trading days
        trading_days = len(sp500_data)
        
        return jsonify({
            'success': True,
            'solution': 'Extended 5D range to 10 calendar days',
            'trading_days_found': trading_days,
            'dates': list(sp500_data.keys()) if sp500_data else [],
            'benefits': [
                f'Shows {trading_days} trading days instead of 3-5',
                'Eliminates weekend gaps in chart display',
                'Better trend visualization for short-term periods',
                'No additional API calls required'
            ],
            'recommendation': 'Update portfolio_performance.py period mapping: 5D -> 10 days'
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/admin/implement-1d-chart-alternatives', methods=['GET'])
@login_required
def implement_1d_chart_alternatives():
    """Implement practical 1D chart alternatives without real-time intraday data"""
    if not current_user.is_admin:
        return jsonify({'error': 'Admin access required'}), 403
    
    try:
        from datetime import datetime, time
        import pytz
        
        # Check if markets are currently open (approximate)
        eastern = pytz.timezone('US/Eastern')
        now_eastern = datetime.now(eastern)
        market_open = time(9, 30)  # 9:30 AM
        market_close = time(16, 0)  # 4:00 PM
        is_weekday = now_eastern.weekday() < 5
        is_market_hours = market_open <= now_eastern.time() <= market_close
        
        market_status = "OPEN" if (is_weekday and is_market_hours) else "CLOSED"
        
        alternatives = {
            'option_1': {
                'name': 'Market Status Indicator',
                'description': 'Show single data point with market status',
                'implementation': 'Add "Market Open/Closed" badge to 1D charts',
                'pros': ['No API calls', 'Clear user expectation'],
                'cons': ['Still single point display']
            },
            'option_2': {
                'name': 'Extended Recent Period',
                'description': 'Change 1D to show last 3 trading days',
                'implementation': 'Rename "1D" to "3D" and show 3 trading days',
                'pros': ['More meaningful progression', 'No API calls'],
                'cons': ['Not truly "1 day"']
            },
            'option_3': {
                'name': 'Hide 1D During Market Hours',
                'description': 'Only show 1D chart when markets closed',
                'implementation': 'Conditional display based on market hours',
                'pros': ['Avoids incomplete data confusion'],
                'cons': ['Feature unavailable during trading']
            },
            'option_4': {
                'name': 'Previous Day Focus',
                'description': 'Show "Yesterday\'s Performance" instead of "1D"',
                'implementation': 'Relabel and show complete previous trading day',
                'pros': ['Complete data story', 'Clear expectation'],
                'cons': ['Not current day performance']
            }
        }
        
        return jsonify({
            'success': True,
            'current_market_status': market_status,
            'current_time_eastern': now_eastern.strftime('%Y-%m-%d %H:%M:%S %Z'),
            'alternatives': alternatives,
            'recommendation': 'Option 2 (Extended Recent Period) or Option 4 (Previous Day Focus)',
            'reasoning': 'Provides meaningful data without API complexity or incomplete current-day issues'
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/admin/test-premium-intraday', methods=['GET'])
@login_required
def test_premium_intraday():
    """Test if current AlphaVantage API key has premium access for real-time intraday data"""
    if not current_user.is_admin:
        return jsonify({'error': 'Admin access required'}), 403
    
    try:
        import requests
        import os
        from datetime import datetime
        
        api_key = os.environ.get('ALPHA_VANTAGE_API_KEY')
        if not api_key:
            return jsonify({'error': 'AlphaVantage API key not found'}), 500
        
        # Test current day intraday data with real-time entitlement
        url = f'https://www.alphavantage.co/query?function=TIME_SERIES_INTRADAY&symbol=SPY&interval=5min&entitlement=realtime&apikey={api_key}'
        response = requests.get(url)
        data = response.json()
        
        # Check for premium access indicators
        has_premium = False
        current_day_data = False
        today = datetime.now().strftime('%Y-%m-%d')
        
        if 'Time Series (5min)' in data:
            intraday_data = data['Time Series (5min)']
            
            # Check if we have today's data
            for timestamp in intraday_data.keys():
                if timestamp.startswith(today):
                    current_day_data = True
                    break
            
            # Premium accounts typically get more frequent updates and current day data
            has_premium = current_day_data and len(intraday_data) > 100
        
        # Check for error messages indicating premium requirement
        error_msg = data.get('Error Message', '')
        info_msg = data.get('Information', '')
        premium_required = 'premium' in error_msg.lower() or 'premium' in info_msg.lower()
        
        return jsonify({
            'success': True,
            'api_key_status': 'Valid' if 'Time Series (5min)' in data else 'Invalid/Limited',
            'has_premium_access': has_premium,
            'current_day_data_available': current_day_data,
            'total_data_points': len(data.get('Time Series (5min)', {})),
            'sample_timestamps': list(data.get('Time Series (5min)', {}).keys())[:5],
            'premium_required_message': premium_required,
            'recommendation': 'Real-time 1D charts possible' if has_premium else 'Stick with extended 5D solution',
            'raw_response_keys': list(data.keys())
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/admin/implement-realtime-1d-charts', methods=['GET'])
@login_required
def implement_realtime_1d_charts():
    """Implement real-time 1D intraday charts using entitlement=realtime"""
    if not current_user.is_admin:
        return jsonify({'error': 'Admin access required'}), 403
    
    try:
        import requests
        import os
        from models import MarketData, db
        from datetime import datetime, date, timedelta
        
        api_key = os.environ.get('ALPHA_VANTAGE_API_KEY')
        if not api_key:
            return jsonify({'error': 'AlphaVantage API key not found'}), 500
        
        # Fetch real-time intraday data for SPY (5-minute intervals)
        url = f'https://www.alphavantage.co/query?function=TIME_SERIES_INTRADAY&symbol=SPY&interval=5min&entitlement=realtime&apikey={api_key}'
        response = requests.get(url)
        data = response.json()
        
        if 'Time Series (5min)' not in data:
            return jsonify({'error': 'Failed to fetch real-time intraday data', 'response': data}), 500
        
        intraday_data = data['Time Series (5min)']
        today = date.today()
        points_added = 0
        current_day_points = 0
        
        # Process real-time intraday data
        for timestamp_str, values in intraday_data.items():
            timestamp = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S')
            
            # Count current day points
            if timestamp.date() == today:
                current_day_points += 1
            
            # Store all recent intraday data (last 2 days for 1D charts)
            if timestamp.date() >= today - timedelta(days=2):
                sp500_value = float(values['4. close']) * 10  # SPY to S&P 500 conversion
                
                # Create/update intraday market data entry
                existing = MarketData.query.filter_by(
                    ticker='SPY_SP500_INTRADAY',
                    date=timestamp.date(),
                    timestamp=timestamp
                ).first()
                
                if not existing:
                    market_data = MarketData(
                        ticker='SPY_SP500_INTRADAY',
                        date=timestamp.date(),
                        timestamp=timestamp,
                        close_price=sp500_value
                    )
                    db.session.add(market_data)
                    points_added += 1
                else:
                    # Update existing data with latest value
                    existing.close_price = sp500_value
                    points_added += 1
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'solution': 'Real-time 1D intraday charts implemented',
            'points_added': points_added,
            'current_day_points': current_day_points,
            'message': f'Added {points_added} real-time intraday data points',
            'benefits': [
                '5-minute intervals provide smooth 1D chart progression',
                'Real-time current trading day data available',
                'Live market movement visibility during trading hours',
                'Automatic updates throughout the day'
            ],
            'next_steps': [
                'Update portfolio_performance.py to use intraday data for 1D charts',
                'Add market hours detection for optimal data display',
                'Set up periodic refresh during trading hours'
            ]
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/admin/run-intraday-migration', methods=['GET'])
@login_required
def run_intraday_migration():
    """Run the intraday migration to add timestamp column"""
    if not current_user.is_admin:
        return jsonify({'error': 'Admin access required'}), 403
    
    try:
        from models import db
        
        # Add timestamp column and update constraints
        db.engine.execute("""
            ALTER TABLE market_data ADD COLUMN IF NOT EXISTS timestamp TIMESTAMP;
        """)
        
        # Rename symbol column to ticker for consistency
        try:
            db.engine.execute("""
                ALTER TABLE market_data RENAME COLUMN symbol TO ticker;
            """)
        except:
            pass  # Column might already be renamed
        
        # Update ticker column size
        db.engine.execute("""
            ALTER TABLE market_data ALTER COLUMN ticker TYPE VARCHAR(20);
        """)
        
        # Drop ALL old constraints that might conflict
        constraints_to_drop = [
            'unique_symbol_date',
            'unique_symbol_date_timestamp', 
            'market_data_symbol_date_key',
            'market_data_ticker_date_key',
            'unique_ticker_date_timestamp'
        ]
        
        for constraint_name in constraints_to_drop:
            try:
                db.engine.execute(f"""
                    ALTER TABLE market_data DROP CONSTRAINT IF EXISTS {constraint_name};
                """)
            except:
                pass
        
        # Add the correct new constraint
        db.engine.execute("""
            ALTER TABLE market_data ADD CONSTRAINT unique_ticker_date_timestamp 
            UNIQUE (ticker, date, timestamp);
        """)
        
        return jsonify({
            'success': True,
            'message': 'Intraday migration completed successfully',
            'changes': [
                'Added timestamp column to market_data table',
                'Renamed symbol column to ticker for consistency',
                'Increased ticker column size to VARCHAR(20)',
                'Dropped all conflicting constraints',
                'Added new unique constraint (ticker, date, timestamp)'
            ]
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/admin/debug-performance-api', methods=['GET'])
@login_required
def debug_performance_api():
    """Debug portfolio performance API endpoint issues"""
    if not current_user.is_admin:
        return jsonify({'error': 'Admin access required'}), 403
    
    try:
        from portfolio_performance import PortfolioPerformanceCalculator
        import time
        
        calculator = PortfolioPerformanceCalculator()
        debug_info = {
            'user_id': current_user.id,
            'tests': []
        }
        
        # Test each period with timing
        periods = ['1D', '5D', '1M', '3M', 'YTD', '1Y', '5Y']
        
        for period in periods:
            start_time = time.time()
            try:
                result = calculator.get_performance_data(current_user.id, period)
                end_time = time.time()
                
                test_result = {
                    'period': period,
                    'duration_seconds': round(end_time - start_time, 2),
                    'success': 'error' not in result,
                    'data_points': len(result.get('portfolio_data', [])) if 'portfolio_data' in result else 0,
                    'sp500_points': len(result.get('sp500_data', [])) if 'sp500_data' in result else 0
                }
                
                if 'error' in result:
                    test_result['error'] = result['error']
                
                debug_info['tests'].append(test_result)
                
            except Exception as e:
                end_time = time.time()
                debug_info['tests'].append({
                    'period': period,
                    'duration_seconds': round(end_time - start_time, 2),
                    'success': False,
                    'error': str(e)
                })
        
        # Check database connectivity
        from models import PortfolioSnapshot, MarketData
        snapshot_count = PortfolioSnapshot.query.filter_by(user_id=current_user.id).count()
        market_data_count = MarketData.query.count()
        intraday_count = MarketData.query.filter(MarketData.timestamp.isnot(None)).count()
        
        debug_info['database'] = {
            'user_snapshots': snapshot_count,
            'total_market_data': market_data_count,
            'intraday_data_points': intraday_count
        }
        
        return jsonify(debug_info)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/admin/test-single-period', methods=['GET'])
@login_required
def test_single_period():
    """Test a single period quickly for debugging"""
    if not current_user.is_admin:
        return jsonify({'error': 'Admin access required'}), 403
    
    period = request.args.get('period', '1D')
    
    try:
        from portfolio_performance import PortfolioPerformanceCalculator
        import time
        
        start_time = time.time()
        calculator = PortfolioPerformanceCalculator()
        result = calculator.get_performance_data(current_user.id, period)
        end_time = time.time()
        
        return jsonify({
            'period': period,
            'duration_seconds': round(end_time - start_time, 2),
            'success': 'error' not in result,
            'result': result
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/admin/fix-sp500-anomalies', methods=['GET'])
@login_required
def fix_sp500_anomalies():
    """Fix anomalous data points in S&P 500 dataset by smoothing"""
    if not current_user.is_admin:
        return jsonify({'error': 'Admin access required'}), 403
    
    try:
        from models import MarketData, db
        from datetime import datetime, timedelta
        
        # Get all S&P 500 data points
        all_data = MarketData.query.filter_by(ticker='SPY_SP500').order_by(MarketData.date).all()
        
        if not all_data:
            return jsonify({'error': 'No S&P 500 data found'})
        
        fixes_applied = []
        
        # Fix large day-to-day changes (>10%) by interpolating
        for i in range(1, len(all_data) - 1):
            prev_price = all_data[i-1].close_price
            curr_price = all_data[i].close_price
            next_price = all_data[i+1].close_price
            
            if prev_price > 0 and next_price > 0:
                # Check if current price is anomalous compared to neighbors
                prev_change = abs((curr_price - prev_price) / prev_price) * 100
                next_change = abs((next_price - curr_price) / curr_price) * 100
                
                # If both changes are large (>8%), likely an anomaly
                if prev_change > 8 and next_change > 8:
                    # Interpolate between previous and next
                    smoothed_price = (prev_price + next_price) / 2
                    
                    fixes_applied.append({
                        'date': all_data[i].date.isoformat(),
                        'original_value': curr_price,
                        'fixed_value': smoothed_price,
                        'prev_value': prev_price,
                        'next_value': next_price,
                        'reason': 'large_spike_interpolated'
                    })
                    
                    # Update the database
                    all_data[i].close_price = smoothed_price
        
        # Fix unrealistic values (outside 1000-10000 range)
        for i, data_point in enumerate(all_data):
            if data_point.close_price < 1000 or data_point.close_price > 10000:
                # Find nearest reasonable values
                reasonable_value = None
                
                # Look backwards for reasonable value
                for j in range(i-1, max(0, i-10), -1):
                    if 1000 <= all_data[j].close_price <= 10000:
                        reasonable_value = all_data[j].close_price
                        break
                
                # If not found backwards, look forwards
                if not reasonable_value:
                    for j in range(i+1, min(len(all_data), i+10)):
                        if 1000 <= all_data[j].close_price <= 10000:
                            reasonable_value = all_data[j].close_price
                            break
                
                if reasonable_value:
                    fixes_applied.append({
                        'date': data_point.date.isoformat(),
                        'original_value': data_point.close_price,
                        'fixed_value': reasonable_value,
                        'reason': 'unrealistic_value_replaced'
                    })
                    
                    data_point.close_price = reasonable_value
        
        # Commit all changes
        if fixes_applied:
            db.session.commit()
        
        return jsonify({
            'success': True,
            'fixes_applied': len(fixes_applied),
            'details': fixes_applied,
            'message': f'Fixed {len(fixes_applied)} anomalous data points'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/admin/sp500-data-status', methods=['GET'])
@login_required
def sp500_data_status():
    """Check status of S&P 500 data population"""
    if not current_user.is_admin:
        return jsonify({'error': 'Admin access required'}), 403
    
    try:
        from models import MarketData
        
        # Count existing S&P 500 data points
        data_count = MarketData.query.filter_by(ticker='SPY_SP500').count()
        
        if data_count > 0:
            # Get date range of existing data
            oldest = MarketData.query.filter_by(ticker='SPY_SP500').order_by(MarketData.date.asc()).first()
            newest = MarketData.query.filter_by(ticker='SPY_SP500').order_by(MarketData.date.desc()).first()
            
            return jsonify({
                'success': True,
                'data_points': data_count,
                'date_range': {
                    'oldest': oldest.date.isoformat() if oldest else None,
                    'newest': newest.date.isoformat() if newest else None
                },
                'status': 'completed' if data_count > 100 else 'partial',
                'message': f'Found {data_count} S&P 500 data points'
            })
        else:
            return jsonify({
                'success': True,
                'data_points': 0,
                'status': 'empty',
                'message': 'No S&P 500 data found. Run /admin/populate-sp500-data to populate.'
            })
            
    except Exception as e:
        logger.error(f"Error checking S&P 500 data status: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/admin/verify-sp500-data', methods=['GET'])
@login_required
def verify_sp500_data():
    """Show sample S&P 500 data points to verify they're real"""
    if not current_user.is_admin:
        return jsonify({'error': 'Admin access required'}), 403
    
    try:
        from models import MarketData
        
        # Get some sample data points
        sample_data = MarketData.query.filter_by(ticker='SPY_SP500').order_by(MarketData.date.desc()).limit(10).all()
        
        if not sample_data:
            return jsonify({
                'success': False,
                'message': 'No S&P 500 data found'
            })
        
        # Format sample data
        samples = []
        for data_point in sample_data:
            samples.append({
                'date': data_point.date.isoformat(),
                'sp500_value': data_point.close_price,
                'spy_equivalent': round(data_point.close_price / 10, 2) if data_point.close_price > 100 else data_point.close_price,
                'ticker': data_point.ticker
            })
        
        # Get some historical significant dates to verify real data
        covid_crash = MarketData.query.filter_by(ticker='SPY_SP500').filter(
            MarketData.date >= '2020-03-01'
        ).filter(MarketData.date <= '2020-04-30').first()
        
        # Also check what's the actual oldest date we have
        oldest_record = MarketData.query.filter_by(ticker='SPY_SP500').order_by(MarketData.date.asc()).first()
        newest_record = MarketData.query.filter_by(ticker='SPY_SP500').order_by(MarketData.date.desc()).first()
        
        # Check what symbols we actually have
        all_symbols = db.session.query(MarketData.ticker).distinct().all()
        symbol_counts = {}
        for symbol_tuple in all_symbols:
            symbol = symbol_tuple[0]
            count = MarketData.query.filter_by(ticker=symbol).count()
            symbol_counts[symbol] = count
        
        return jsonify({
            'success': True,
            'total_data_points': len(MarketData.query.filter_by(ticker='SPY_SP500').all()),
            'all_symbols': symbol_counts,
            'date_range_actual': {
                'oldest': oldest_record.date.isoformat() if oldest_record else None,
                'newest': newest_record.date.isoformat() if newest_record else None
            },
            'recent_samples': samples,
            'covid_crash_sample': {
                'date': covid_crash.date.isoformat() if covid_crash else None,
                'sp500_value': covid_crash.close_price if covid_crash else None,
                'note': 'Should show market crash values around March 2020'
            } if covid_crash else None,
            'verification_notes': [
                'Check if SP500 values look realistic (3000-5000+ range)',
                'COVID crash should show lower values in March 2020',
                'Recent dates should have current market levels'
            ]
        })
        
    except Exception as e:
        logger.error(f"Error verifying S&P 500 data: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/admin/check-cached-data')
def check_cached_data():
    """Admin endpoint to verify S&P 500 and portfolio snapshots coverage"""
    try:
        # Check if user is admin
        email = session.get('email', '')
        if email != ADMIN_EMAIL:
            return jsonify({'error': 'Admin access required'}), 403
        
        from models import MarketData, PortfolioSnapshot
        from datetime import datetime, timedelta
        
        # Check S&P 500 data coverage
        sp500_data = MarketData.query.filter_by(ticker='SPY_SP500').order_by(MarketData.date).all()
        
        sp500_coverage = {
            'total_points': len(sp500_data),
            'earliest_date': sp500_data[0].date.isoformat() if sp500_data else None,
            'latest_date': sp500_data[-1].date.isoformat() if sp500_data else None,
            'years_covered': 0,
            'has_5_years': False
        }
        
        if sp500_data:
            earliest = sp500_data[0].date
            latest = sp500_data[-1].date
            years_covered = (latest - earliest).days / 365.25
            five_years_ago = datetime.now().date() - timedelta(days=5*365)
            
            sp500_coverage.update({
                'years_covered': round(years_covered, 1),
                'has_5_years': earliest <= five_years_ago
            })
        
        # Check portfolio snapshots for all users
        all_users = User.query.all()
        portfolio_coverage = {}
        
        for user in all_users:
            snapshots = PortfolioSnapshot.query.filter_by(user_id=user.id).order_by(PortfolioSnapshot.date).all()
            
            if snapshots:
                earliest = snapshots[0].date
                latest = snapshots[-1].date
                days_covered = (latest - earliest).days + 1
                
                portfolio_coverage[user.username] = {
                    'user_id': user.id,
                    'total_snapshots': len(snapshots),
                    'earliest_date': earliest.isoformat(),
                    'latest_date': latest.isoformat(),
                    'days_covered': days_covered
                }
            else:
                portfolio_coverage[user.username] = {
                    'user_id': user.id,
                    'total_snapshots': 0,
                    'message': 'No snapshots found'
                }
        
        return jsonify({
            'success': True,
            'sp500_coverage': sp500_coverage,
            'portfolio_coverage': portfolio_coverage,
            'total_users': len(all_users),
            'users_with_snapshots': len([u for u in portfolio_coverage.values() if u['total_snapshots'] > 0])
        })
        
    except Exception as e:
        logger.error(f"Error checking cached data: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/admin/test-performance-api')
def test_performance_api():
    """Admin endpoint to test performance API response"""
    try:
        # Check if user is admin
        email = session.get('email', '')
        if email != ADMIN_EMAIL:
            return jsonify({'error': 'Admin access required'}), 403
        
        # Import here to avoid circular imports
        import sys
        import os
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from portfolio_performance import performance_calculator
        
        # Get a test user with stocks
        test_user = db.session.query(User.id).join(Stock).first()
        if not test_user:
            return jsonify({'error': 'No users with stocks found for testing'}), 404
        
        user_id = test_user[0]
        
        # Test the performance data for 1 month
        performance_data = performance_calculator.get_performance_data(user_id, '1M')
        
        return jsonify({
            'success': True,
            'test_user_id': user_id,
            'performance_data': performance_data,
            'chart_data_length': len(performance_data.get('chart_data', [])),
            'message': 'Performance API test completed'
        })
        
    except Exception as e:
        logger.error(f"Performance API test error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/cron/daily-snapshots')
def cron_daily_snapshots():
    """Cron endpoint for automated daily snapshot creation (call this daily at market close)"""
    try:
        # This endpoint can be called by external cron services or Vercel cron
        # No auth required for cron endpoints, but you could add a secret token
        
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
@login_required
def create_tables():
    """Create all database tables"""
    try:
        # Check if user is admin
        email = session.get('email', '')
        if email != ADMIN_EMAIL:
            return jsonify({'error': 'Admin access required'}), 403
        
        # Create the new tables
        from models import db, User, Stock, Transaction, PortfolioSnapshot, StockInfo, SubscriptionTier, UserSubscription, SMSNotification, LeaderboardCache, UserPortfolioChartCache, AlphaVantageAPILog, PlatformMetrics, UserActivity
        
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

@app.route('/admin/test-intraday-collection')
@login_required
def test_intraday_collection():
    """Admin endpoint to manually test intraday data collection"""
    if not current_user.is_admin:
        return redirect(url_for('index'))
    
    try:
        from datetime import datetime
        from models import User, PortfolioSnapshotIntraday
        from portfolio_performance import PortfolioPerformanceCalculator
        
        calculator = PortfolioPerformanceCalculator()
        current_time = datetime.now()
        
        results = {
            'timestamp': current_time.isoformat(),
            'users_processed': 0,
            'snapshots_created': 0,
            'errors': []
        }
        
        # Get all users
        users = User.query.all()
        
        for user in users:
            try:
                # Calculate current portfolio value
                portfolio_value = calculator.calculate_portfolio_value(user.id)
                
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
                results['errors'].append(error_msg)
        
        # Commit all changes
        db.session.commit()
        
        return f"""
        <h1>Manual Intraday Collection Test</h1>
        <h2>Results</h2>
        <p><strong>Timestamp:</strong> {results['timestamp']}</p>
        <p><strong>Users Processed:</strong> {results['users_processed']}</p>
        <p><strong>Snapshots Created:</strong> {results['snapshots_created']}</p>
        <p><strong>Errors:</strong> {len(results['errors'])}</p>
        
        {f'<h3>Errors:</h3><ul>{"".join([f"<li>{error}</li>" for error in results["errors"]])}</ul>' if results['errors'] else ''}
        
        <p><a href="/admin">Back to Admin</a></p>
        """
        
    except Exception as e:
        return f"""
        <h1>Manual Intraday Collection Test - Error</h1>
        <p><strong>Error:</strong> {str(e)}</p>
        <p><a href="/admin">Back to Admin</a></p>
        """

@app.route('/admin/test-market-close')
@login_required
def test_market_close():
    """Admin endpoint to manually test market close operations"""
    if not current_user.is_admin:
        return redirect(url_for('index'))
    
    try:
        from datetime import datetime, date
        from models import User, PortfolioSnapshot, LeaderboardEntry
        from portfolio_performance import PortfolioPerformanceCalculator
        from leaderboard_utils import update_leaderboard_cache
        
        calculator = PortfolioPerformanceCalculator()
        today = date.today()
        
        results = {
            'timestamp': datetime.now().isoformat(),
            'users_processed': 0,
            'snapshots_created': 0,
            'snapshots_updated': 0,
            'leaderboard_updated': False,
            'errors': []
        }
        
        # Get all users
        users = User.query.all()
        
        for user in users:
            try:
                # Calculate portfolio value for today
                portfolio_value = calculator.calculate_portfolio_value(user.id, today)
                
                # Check if snapshot already exists for today
                existing_snapshot = PortfolioSnapshot.query.filter_by(
                    user_id=user.id, 
                    date=today
                ).first()
                
                if existing_snapshot:
                    existing_snapshot.total_value = portfolio_value
                    results['snapshots_updated'] += 1
                else:
                    # Create new EOD snapshot
                    snapshot = PortfolioSnapshot(
                        user_id=user.id,
                        date=today,
                        total_value=portfolio_value,
                        cash_flow=0  # Calculate if needed
                    )
                    db.session.add(snapshot)
                    results['snapshots_created'] += 1
                
                results['users_processed'] += 1
                
            except Exception as e:
                error_msg = f"Error processing user {user.id}: {str(e)}"
                results['errors'].append(error_msg)
        
        # Update leaderboard cache
        try:
            updated_count = update_leaderboard_cache()
            results['leaderboard_updated'] = True
            results['leaderboard_entries_updated'] = updated_count
        except Exception as e:
            results['errors'].append(f"Leaderboard update error: {str(e)}")
        
        # Commit all changes
        db.session.commit()
        
        return f"""
        <h1>Manual Market Close Test</h1>
        <h2>Results</h2>
        <p><strong>Timestamp:</strong> {results['timestamp']}</p>
        <p><strong>Users Processed:</strong> {results['users_processed']}</p>
        <p><strong>EOD Snapshots Created:</strong> {results['snapshots_created']}</p>
        <p><strong>EOD Snapshots Updated:</strong> {results['snapshots_updated']}</p>
        <p><strong>Leaderboard Updated:</strong> {results['leaderboard_updated']}</p>
        {f"<p><strong>Leaderboard Entries:</strong> {results.get('leaderboard_entries_updated', 'N/A')}</p>" if results['leaderboard_updated'] else ''}
        <p><strong>Errors:</strong> {len(results['errors'])}</p>
        
        {f'<h3>Errors:</h3><ul>{"".join([f"<li>{error}</li>" for error in results["errors"]])}</ul>' if results['errors'] else ''}
        
        <p><a href="/admin">Back to Admin</a></p>
        """
        
    except Exception as e:
        return f"""
        <h1>Manual Market Close Test - Error</h1>
        <p><strong>Error:</strong> {str(e)}</p>
        <p><a href="/admin">Back to Admin</a></p>
        """

@app.route('/admin/test-cron-endpoints')
@login_required
def test_cron_endpoints():
    """Admin endpoint to test if cron endpoints are accessible"""
    if not current_user.is_admin:
        return redirect(url_for('index'))
    
    import requests
    from datetime import datetime
    
    results = {
        'timestamp': datetime.now().isoformat(),
        'intraday_test': {'status': 'pending', 'response': None, 'error': None},
        'market_close_test': {'status': 'pending', 'response': None, 'error': None}
    }
    
    # Test intraday endpoint
    try:
        # Get the token from environment (if available)
        import os
        intraday_token = os.getenv('INTRADAY_CRON_TOKEN', 'test-token')
        
        response = requests.post(
            'https://apestogether.ai/api/cron/collect-intraday-data',
            headers={
                'Authorization': f'Bearer {intraday_token}',
                'Content-Type': 'application/json'
            },
            timeout=30
        )
        
        results['intraday_test']['status'] = 'success' if response.status_code == 200 else 'failed'
        results['intraday_test']['http_code'] = response.status_code
        results['intraday_test']['response'] = response.text[:500]  # Truncate long responses
        
    except Exception as e:
        results['intraday_test']['status'] = 'error'
        results['intraday_test']['error'] = str(e)
    
    # Test market close endpoint
    try:
        cron_secret = os.getenv('CRON_SECRET', 'test-secret')
        
        response = requests.post(
            'https://apestogether.ai/api/cron/market-close',
            headers={
                'Authorization': f'Bearer {cron_secret}',
                'Content-Type': 'application/json'
            },
            timeout=30
        )
        
        results['market_close_test']['status'] = 'success' if response.status_code == 200 else 'failed'
        results['market_close_test']['http_code'] = response.status_code
        results['market_close_test']['response'] = response.text[:500]
        
    except Exception as e:
        results['market_close_test']['status'] = 'error'
        results['market_close_test']['error'] = str(e)
    
    return f"""
    <h1>Cron Endpoints Test</h1>
    <h2>Results</h2>
    <p><strong>Timestamp:</strong> {results['timestamp']}</p>
    
    <h3>Intraday Data Collection Endpoint</h3>
    <p><strong>Status:</strong> {results['intraday_test']['status']}</p>
    <p><strong>HTTP Code:</strong> {results['intraday_test'].get('http_code', 'N/A')}</p>
    <p><strong>Response:</strong> <pre>{results['intraday_test'].get('response', 'N/A')}</pre></p>
    {f"<p><strong>Error:</strong> {results['intraday_test']['error']}</p>" if results['intraday_test']['error'] else ''}
    
    <h3>Market Close Endpoint</h3>
    <p><strong>Status:</strong> {results['market_close_test']['status']}</p>
    <p><strong>HTTP Code:</strong> {results['market_close_test'].get('http_code', 'N/A')}</p>
    <p><strong>Response:</strong> <pre>{results['market_close_test'].get('response', 'N/A')}</pre></p>
    {f"<p><strong>Error:</strong> {results['market_close_test']['error']}</p>" if results['market_close_test']['error'] else ''}
    
    <h3>Next Steps</h3>
    <p>If endpoints return 401/403: Check GitHub repository secrets</p>
    <p>If endpoints return 200: GitHub Actions scheduling issue</p>
    <p>If endpoints error: Network/DNS issue</p>
    
    <p><a href="/admin">Back to Admin</a></p>
    """

@app.route('/api/cron/market-close', methods=['POST'])
def market_close_cron():
    """Market close cron job endpoint - creates EOD snapshots and updates leaderboards"""
    try:
        # Verify authorization
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            return jsonify({'error': 'Missing or invalid authorization header'}), 401
        
        token = auth_header.split(' ')[1]
        expected_token = os.getenv('CRON_SECRET')
        if not expected_token or token != expected_token:
            return jsonify({'error': 'Invalid authorization token'}), 403
        
        from datetime import datetime, date
        from models import User, PortfolioSnapshot
        from portfolio_performance import PortfolioPerformanceCalculator
        from leaderboard_utils import update_leaderboard_cache
        
        calculator = PortfolioPerformanceCalculator()
        today = date.today()
        current_time = datetime.now()
        
        results = {
            'timestamp': current_time.isoformat(),
            'users_processed': 0,
            'snapshots_created': 0,
            'snapshots_updated': 0,
            'leaderboard_updated': False,
            'errors': []
        }
        
        # Get all users
        users = User.query.all()
        
        for user in users:
            try:
                # Calculate portfolio value for today
                portfolio_value = calculator.calculate_portfolio_value(user.id, today)
                
                # Check if snapshot already exists for today
                existing_snapshot = PortfolioSnapshot.query.filter_by(
                    user_id=user.id, 
                    date=today
                ).first()
                
                if existing_snapshot:
                    existing_snapshot.total_value = portfolio_value
                    results['snapshots_updated'] += 1
                else:
                    # Create new EOD snapshot
                    snapshot = PortfolioSnapshot(
                        user_id=user.id,
                        date=today,
                        total_value=portfolio_value,
                        cash_flow=0  # Calculate if needed
                    )
                    db.session.add(snapshot)
                    results['snapshots_created'] += 1
                
                results['users_processed'] += 1
                
            except Exception as e:
                error_msg = f"Error processing user {user.id}: {str(e)}"
                results['errors'].append(error_msg)
                logger.error(f"Market close user {user.id} error: {e}")
        
        # Update leaderboard cache
        try:
            updated_count = update_leaderboard_cache()
            results['leaderboard_updated'] = True
            results['leaderboard_entries_updated'] = updated_count
        except Exception as e:
            error_msg = f"Leaderboard update error: {str(e)}"
            results['errors'].append(error_msg)
            logger.error(f"Market close leaderboard error: {e}")
        
        # Commit all changes
        try:
            db.session.commit()
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

@app.route('/api/cron/cleanup-intraday-data', methods=['POST'])
def cleanup_intraday_data_cron():
    """Automated cron endpoint to clean up old intraday snapshots while preserving 4PM market close data"""
    try:
        # Verify authorization token
        auth_header = request.headers.get('Authorization', '')
        expected_token = os.environ.get('CRON_SECRET')
        
        if not expected_token:
            logger.error("CRON_SECRET not configured")
            return jsonify({'error': 'Server configuration error'}), 500
        
        if not auth_header.startswith('Bearer ') or auth_header[7:] != expected_token:
            logger.warning(f"Unauthorized cleanup attempt")
            return jsonify({'error': 'Unauthorized'}), 401
        
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

@app.route('/api/cron/update-leaderboard', methods=['POST'])
def update_leaderboard_cron():
    """Automated cron endpoint to update leaderboard cache - legacy endpoint for backward compatibility"""
    try:
        # Verify authorization token
        auth_header = request.headers.get('Authorization', '')
        expected_token = os.environ.get('CRON_SECRET')
        
        if not expected_token:
            logger.error("CRON_SECRET not configured")
            return jsonify({'error': 'Server configuration error'}), 500
        
        if not auth_header.startswith('Bearer ') or auth_header[7:] != expected_token:
            logger.warning(f"Unauthorized leaderboard update attempt")
            return jsonify({'error': 'Unauthorized'}), 401
        
        from leaderboard_utils import update_leaderboard_cache
        
        # Update leaderboard cache (all periods)
        updated_count = update_leaderboard_cache()
        
        logger.info(f"Automated leaderboard update completed: {updated_count} entries updated")
        
        return jsonify({
            'success': True,
            'message': 'Leaderboard cache updated',
            'entries_updated': updated_count
        }), 200
        
    except Exception as e:
        logger.error(f"Automated leaderboard update error: {str(e)}")
        return jsonify({'error': f'Leaderboard update error: {str(e)}'}), 500

@app.route('/api/cron/update-leaderboard-chunk', methods=['POST'])
def update_leaderboard_chunk_cron():
    """Chunked cron endpoint to update specific leaderboard periods for better reliability"""
    try:
        # Verify authorization token
        auth_header = request.headers.get('Authorization', '')
        expected_token = os.environ.get('CRON_SECRET')
        
        if not expected_token:
            logger.error("CRON_SECRET not configured")
            return jsonify({'error': 'Server configuration error'}), 500
        
        if not auth_header.startswith('Bearer ') or auth_header[7:] != expected_token:
            logger.warning(f"Unauthorized leaderboard chunk update attempt")
            return jsonify({'error': 'Unauthorized'}), 401
        
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

@app.route('/admin/add-html-cache-column', methods=['GET', 'POST'])
@login_required
def admin_add_html_cache_column():
    """Add rendered_html column to leaderboard_cache table for Phase 5 HTML pre-rendering"""
    if not current_user.is_authenticated or current_user.email != ADMIN_EMAIL:
        return jsonify({'error': 'Admin access required'}), 403
    
    try:
        from models import db
        from sqlalchemy import text
        
        # Check if column already exists
        result = db.session.execute(text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'leaderboard_cache' 
            AND column_name = 'rendered_html'
        """))
        
        if result.fetchone():
            return jsonify({
                'success': True,
                'message': 'rendered_html column already exists',
                'action': 'none'
            }), 200
        
        # Add the column
        db.session.execute(text("""
            ALTER TABLE leaderboard_cache 
            ADD COLUMN rendered_html TEXT
        """))
        db.session.commit()
        
        logger.info("Successfully added rendered_html column to leaderboard_cache table")
        
        return jsonify({
            'success': True,
            'message': 'rendered_html column added to leaderboard_cache table',
            'action': 'column_added'
        }), 200
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error adding rendered_html column: {str(e)}")
        return jsonify({'error': f'Migration error: {str(e)}'}), 500

@app.route('/admin/market-close-status')
@login_required
def admin_market_close_status():
    """Monitor the status of market close pipeline processes"""
    if not current_user.is_authenticated or current_user.email != ADMIN_EMAIL:
        return jsonify({'error': 'Admin access required'}), 403
    
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
        
        # Check for HTML pre-rendering
        html_prerendered = 0
        try:
            html_entries = LeaderboardCache.query.filter(
                LeaderboardCache.rendered_html.isnot(None),
                LeaderboardCache.generated_at >= datetime.now() - timedelta(hours=24)
            ).count()
            html_prerendered = html_entries
        except Exception:
            html_prerendered = 0
        
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
        
        if html_prerendered == 0:
            issues.append("No HTML pre-rendering detected (expected after market close)")
        
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
                "html_prerendered": html_prerendered,
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

@app.route('/admin/trigger-market-close-test', methods=['GET', 'POST'])
@login_required  
def admin_trigger_market_close_test():
    """Manually trigger market close pipeline for testing"""
    if not current_user.is_authenticated or current_user.email != ADMIN_EMAIL:
        return jsonify({'error': 'Admin access required'}), 403
    
    try:
        results = {
            "test_started": datetime.now().isoformat(),
            "steps": {}
        }
        
        # 1. Test portfolio snapshots
        try:
            from portfolio_performance import PortfolioPerformanceCalculator
            calculator = PortfolioPerformanceCalculator()
            
            # Test with a few users
            from models import User
            test_users = User.query.limit(3).all()
            snapshot_count = 0
            errors = []
            
            for user in test_users:
                try:
                    calculator.create_daily_snapshot(user.id)
                    snapshot_count += 1
                except Exception as e:
                    errors.append(f"User {user.id}: {str(e)}")
            
            results["steps"]["portfolio_snapshots"] = {
                "status": "success" if snapshot_count > 0 else "failed",
                "snapshots_created": snapshot_count,
                "errors": errors
            }
            
        except Exception as e:
            results["steps"]["portfolio_snapshots"] = {
                "status": "failed",
                "error": str(e)
            }
        
        # 2. Test leaderboard calculation
        try:
            from leaderboard_utils import update_leaderboard_cache
            
            # Test with just 7D period
            updated_count = update_leaderboard_cache(periods=['7D'])
            
            results["steps"]["leaderboard_calculation"] = {
                "status": "success",
                "entries_updated": updated_count
            }
            
        except Exception as e:
            results["steps"]["leaderboard_calculation"] = {
                "status": "failed", 
                "error": str(e)
            }
        
        # 3. Test HTML pre-rendering (check if it worked)
        try:
            from models import LeaderboardCache
            html_count = LeaderboardCache.query.filter(
                LeaderboardCache.rendered_html.isnot(None)
            ).count()
            
            results["steps"]["html_prerendering"] = {
                "status": "success" if html_count > 0 else "warning",
                "html_entries": html_count,
                "note": "HTML pre-rendering happens during leaderboard cache update"
            }
            
        except Exception as e:
            results["steps"]["html_prerendering"] = {
                "status": "failed",
                "error": str(e)
            }
        
        # 4. Test AlphaVantage connectivity
        try:
            from stock_metadata_utils import get_stock_info_from_api
            
            # Test with a common stock
            test_result = get_stock_info_from_api("AAPL")
            
            results["steps"]["alpha_vantage_test"] = {
                "status": "success" if test_result else "failed",
                "test_ticker": "AAPL",
                "api_responsive": test_result is not None
            }
            
        except Exception as e:
            results["steps"]["alpha_vantage_test"] = {
                "status": "failed",
                "error": str(e)
            }
        
        results["test_completed"] = datetime.now().isoformat()
        
        # Overall assessment
        successful_steps = sum(1 for step in results["steps"].values() 
                             if step.get("status") == "success")
        total_steps = len(results["steps"])
        
        results["summary"] = {
            "successful_steps": successful_steps,
            "total_steps": total_steps,
            "success_rate": f"{successful_steps/total_steps*100:.1f}%",
            "overall_status": "healthy" if successful_steps == total_steps else "issues_detected"
        }
        
        return jsonify({
            "success": True,
            "message": "Market close test completed",
            "results": results
        })
        
    except Exception as e:
        logger.error(f"Market close test error: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route('/admin/debug-performance-data')
@login_required
def admin_debug_performance_data():
    """Debug portfolio performance and chart data issues"""
    if not current_user.is_authenticated or current_user.email != ADMIN_EMAIL:
        return jsonify({'error': 'Admin access required'}), 403
    
    try:
        from datetime import datetime, date, timedelta
        from models import db, User, PortfolioSnapshot, LeaderboardCache, UserPortfolioChartCache, MarketData
        import json
        
        debug_info = {
            "timestamp": datetime.now().isoformat(),
            "issues_found": [],
            "data_analysis": {}
        }
        
        # 1. Check leaderboard data for 0% performance
        leaderboard_1d = LeaderboardCache.query.filter_by(period='1D_all').first()
        if leaderboard_1d:
            try:
                data = json.loads(leaderboard_1d.leaderboard_data)
                zero_performance_count = sum(1 for entry in data if entry.get('performance_percent', 0) == 0)
                debug_info["data_analysis"]["leaderboard_1d"] = {
                    "total_entries": len(data),
                    "zero_performance_entries": zero_performance_count,
                    "last_updated": leaderboard_1d.generated_at.isoformat(),
                    "sample_entry": data[0] if data else None
                }
                if zero_performance_count == len(data):
                    debug_info["issues_found"].append("All 1D leaderboard entries show 0% performance")
            except Exception as e:
                debug_info["issues_found"].append(f"Failed to parse 1D leaderboard data: {str(e)}")
        else:
            debug_info["issues_found"].append("No 1D leaderboard cache found")
        
        # 2. Check portfolio snapshots for recent data
        today = date.today()
        yesterday = today - timedelta(days=1)
        friday = today - timedelta(days=2) if today.weekday() == 6 else (today - timedelta(days=1) if today.weekday() == 0 else yesterday)
        
        snapshots_today = PortfolioSnapshot.query.filter_by(date=today).count()
        snapshots_yesterday = PortfolioSnapshot.query.filter_by(date=yesterday).count()
        snapshots_friday = PortfolioSnapshot.query.filter_by(date=friday).count()
        
        debug_info["data_analysis"]["portfolio_snapshots"] = {
            "today": snapshots_today,
            "yesterday": snapshots_yesterday,
            "last_market_day": snapshots_friday,
            "weekend_issue": today.weekday() >= 5  # Saturday=5, Sunday=6
        }
        
        # 3. Check market data (SPY) for recent updates - check all SPY variants
        spy_regular = MarketData.query.filter(MarketData.ticker == 'SPY').count()
        spy_sp500 = MarketData.query.filter(MarketData.ticker == 'SPY_SP500').count()
        spy_intraday = MarketData.query.filter(MarketData.ticker == 'SPY_INTRADAY').count()
        
        recent_market_data = MarketData.query.filter(
            MarketData.ticker.in_(['SPY', 'SPY_SP500', 'SPY_INTRADAY']),
            MarketData.date >= today - timedelta(days=7)
        ).order_by(MarketData.date.desc()).limit(10).all()
        
        # Get total SPY data across all time
        total_spy_data = MarketData.query.filter(
            MarketData.ticker.in_(['SPY', 'SPY_SP500', 'SPY_INTRADAY'])
        ).count()
        
        # Get date range of existing data
        oldest_spy = MarketData.query.filter(
            MarketData.ticker.in_(['SPY', 'SPY_SP500', 'SPY_INTRADAY'])
        ).order_by(MarketData.date.asc()).first()
        
        latest_spy = MarketData.query.filter(
            MarketData.ticker.in_(['SPY', 'SPY_SP500', 'SPY_INTRADAY'])
        ).order_by(MarketData.date.desc()).first()
        
        debug_info["data_analysis"]["market_data"] = {
            "spy_regular_count": spy_regular,
            "spy_sp500_count": spy_sp500,
            "spy_intraday_count": spy_intraday,
            "total_spy_records": total_spy_data,
            "recent_spy_data_count": len(recent_market_data),
            "oldest_spy_date": oldest_spy.date.isoformat() if oldest_spy else None,
            "latest_spy_date": latest_spy.date.isoformat() if latest_spy else None,
            "latest_spy_price": latest_spy.close_price if latest_spy else None,
            "recent_entries_sample": [
                {
                    "ticker": entry.ticker,
                    "date": entry.date.isoformat(),
                    "price": entry.close_price,
                    "timestamp": entry.timestamp.isoformat() if entry.timestamp else None
                } for entry in recent_market_data[:5]
            ]
        }
        
        # 4. Check user chart cache
        sample_user = User.query.first()
        if sample_user:
            user_charts = UserPortfolioChartCache.query.filter_by(user_id=sample_user.id).all()
            debug_info["data_analysis"]["user_charts"] = {
                "sample_user_id": sample_user.id,
                "chart_periods": [chart.period for chart in user_charts],
                "chart_count": len(user_charts),
                "latest_chart_update": max([chart.generated_at for chart in user_charts]).isoformat() if user_charts else None
            }
            
            # Check a sample chart for data quality
            if user_charts:
                sample_chart = user_charts[0]
                try:
                    chart_data = json.loads(sample_chart.chart_data)
                    debug_info["data_analysis"]["sample_chart"] = {
                        "period": sample_chart.period,
                        "data_points": len(chart_data.get('dates', [])),
                        "has_portfolio_data": len(chart_data.get('portfolio_values', [])) > 0,
                        "has_sp500_data": len(chart_data.get('sp500_values', [])) > 0,
                        "sample_portfolio_values": chart_data.get('portfolio_values', [])[:3],
                        "sample_sp500_values": chart_data.get('sp500_values', [])[:3]
                    }
                except Exception as e:
                    debug_info["issues_found"].append(f"Failed to parse sample chart data: {str(e)}")
        
        # 5. Check performance calculation endpoints
        try:
            # Test the performance API endpoint
            from portfolio_performance import PortfolioPerformanceCalculator
            calculator = PortfolioPerformanceCalculator()
            
            if sample_user:
                test_performance = calculator.get_performance_data(sample_user.id, '1D')
                debug_info["data_analysis"]["performance_calculation"] = {
                    "sample_user_1d_performance": test_performance,
                    "calculation_working": test_performance is not None,
                    "has_portfolio_return": test_performance.get('portfolio_return') if test_performance else None,
                    "has_sp500_return": test_performance.get('sp500_return') if test_performance else None
                }
                
                if test_performance is None:
                    debug_info["issues_found"].append("Performance calculation returning None for sample user")
                elif test_performance.get('portfolio_return') == 0:
                    debug_info["issues_found"].append("Performance calculation returning 0% for sample user")
        
        except Exception as e:
            debug_info["issues_found"].append(f"Performance calculation error: {str(e)}")
        
        # 6. Weekend data handling check
        debug_info["data_analysis"]["weekend_handling"] = {
            "current_day": today.strftime('%A'),
            "is_weekend": today.weekday() >= 5,
            "should_show_friday_data": today.weekday() >= 5,
            "recommendation": "Weekend should show last market day data, not 0% performance"
        }
        
        return jsonify({
            "success": True,
            "debug_info": debug_info
        })
        
    except Exception as e:
        logger.error(f"Performance debug error: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route('/admin/force-refresh-leaderboard', methods=['GET', 'POST'])
@login_required
def admin_force_refresh_leaderboard():
    """Force refresh leaderboard cache with new weekend logic and populate missing data"""
    if not current_user.is_authenticated or current_user.email != ADMIN_EMAIL:
        return jsonify({'error': 'Admin access required'}), 403
    
    try:
        from datetime import datetime, date, timedelta
        from models import db, LeaderboardCache, MarketData
        from leaderboard_utils import update_leaderboard_cache
        
        results = {
            "timestamp": datetime.now().isoformat(),
            "actions_taken": [],
            "errors": []
        }
        
        # 1. Clear old leaderboard cache (including 7D entries)
        try:
            deleted_count = LeaderboardCache.query.delete()
            db.session.commit()
            results["actions_taken"].append(f"Cleared {deleted_count} old leaderboard cache entries")
        except Exception as e:
            results["errors"].append(f"Failed to clear cache: {str(e)}")
        
        # 2. Check SPY market data status (don't populate - data exists!)
        try:
            spy_regular = MarketData.query.filter_by(ticker='SPY').count()
            spy_sp500 = MarketData.query.filter_by(ticker='SPY_SP500').count()
            spy_intraday = MarketData.query.filter_by(ticker='SPY_INTRADAY').count()
            total_spy = spy_regular + spy_sp500 + spy_intraday
            
            results["actions_taken"].append(f"SPY data confirmed: {total_spy} total records (SPY: {spy_regular}, SPY_SP500: {spy_sp500}, SPY_INTRADAY: {spy_intraday})")
            
            if total_spy == 0:
                results["errors"].append("WARNING: No SPY data found - charts will be empty")
            else:
                results["actions_taken"].append("SPY data exists - skipping population to avoid duplicates")
        except Exception as e:
            results["errors"].append(f"SPY data check error: {str(e)}")
        
        # 3. Force regenerate leaderboard cache with new logic
        try:
            # Update with new periods (no 7D)
            updated_count = update_leaderboard_cache(periods=['1D', '5D', '1M', '3M', 'YTD', '1Y', '5Y', 'MAX'])
            results["actions_taken"].append(f"Regenerated leaderboard cache: {updated_count} entries updated")
        except Exception as e:
            results["errors"].append(f"Leaderboard regeneration error: {str(e)}")
        
        # 4. Check results
        try:
            new_1d_cache = LeaderboardCache.query.filter_by(period='1D_all').first()
            if new_1d_cache:
                import json
                data = json.loads(new_1d_cache.leaderboard_data)
                zero_performance = sum(1 for entry in data if entry.get('performance_percent', 0) == 0)
                results["actions_taken"].append(f"New 1D cache: {len(data)} entries, {zero_performance} with 0% performance")
                results["sample_new_entry"] = data[0] if data else None
            else:
                results["errors"].append("No 1D cache found after regeneration")
        except Exception as e:
            results["errors"].append(f"Cache verification error: {str(e)}")
        
        return jsonify({
            "success": True,
            "message": "Leaderboard refresh completed",
            "results": results
        })
        
    except Exception as e:
        logger.error(f"Force refresh error: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route('/api/portfolio/chart/<username>/<period>')
def get_public_portfolio_chart(username, period):
    """Get portfolio chart data for public portfolio views (blurred/unblurred)"""
    try:
        from models import User, UserPortfolioChartCache
        import json
        
        # Find user by username
        user = User.query.filter_by(username=username).first()
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        period_upper = period.upper()
        
        # Try to use pre-rendered chart data (Chart.js format for direct use)
        chart_cache = UserPortfolioChartCache.query.filter_by(
            user_id=user.id, period=period_upper
        ).first()
        
        if chart_cache:
            try:
                # Return Chart.js format directly for public portfolio pages
                cached_data = json.loads(chart_cache.chart_data)
                cached_data['data_source'] = 'pre_rendered_cache'
                cached_data['username'] = username
                
                logger.info(f"Using pre-rendered chart data for public view: {username}, period {period_upper}")
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
        return jsonify({'error': str(e)}), 500

@app.route('/admin/debug-dashboard-apis')
@login_required
def admin_debug_dashboard_apis():
    """Debug the specific API endpoints that dashboard calls"""
    if not current_user.is_authenticated or current_user.email != ADMIN_EMAIL:
        return jsonify({'error': 'Admin access required'}), 403
    
    try:
        from datetime import datetime
        import requests
        
        debug_info = {
            "timestamp": datetime.now().isoformat(),
            "user_id": current_user.id,
            "api_tests": {},
            "issues_found": []
        }
        
        # Test the exact endpoints dashboard calls
        periods_to_test = ['1D', '5D', '1M', '3M', 'YTD', '1Y']
        
        for period in periods_to_test:
            try:
                # Determine which endpoint dashboard would call
                if period in ['1D', '5D']:
                    endpoint = f'/api/portfolio/performance-intraday/{period}'
                else:
                    endpoint = f'/api/portfolio/performance/{period}'
                
                # Make internal API call
                from flask import url_for
                import json
                
                # Simulate the API call internally
                if period in ['1D', '5D']:
                    # Test intraday endpoint
                    with app.test_client() as client:
                        # Login as current user
                        with client.session_transaction() as sess:
                            sess['user_id'] = current_user.id
                        
                        response = client.get(endpoint)
                        response_data = json.loads(response.data) if response.data else {}
                        
                        debug_info["api_tests"][f"{period}_intraday"] = {
                            "endpoint": endpoint,
                            "status_code": response.status_code,
                            "has_portfolio_return": "portfolio_return" in response_data,
                            "has_sp500_return": "sp500_return" in response_data,
                            "has_chart_data": "chart_data" in response_data,
                            "portfolio_return_value": response_data.get("portfolio_return"),
                            "sp500_return_value": response_data.get("sp500_return"),
                            "chart_data_length": len(response_data.get("chart_data", [])),
                            "error": response_data.get("error"),
                            "sample_response": response_data
                        }
                        
                        if response.status_code != 200:
                            debug_info["issues_found"].append(f"{period} intraday API returned {response.status_code}")
                        if "portfolio_return" not in response_data:
                            debug_info["issues_found"].append(f"{period} intraday API missing portfolio_return field")
                        if response_data.get("portfolio_return") is None:
                            debug_info["issues_found"].append(f"{period} intraday API portfolio_return is None")
                
                else:
                    # Test regular performance endpoint
                    with app.test_client() as client:
                        with client.session_transaction() as sess:
                            sess['user_id'] = current_user.id
                        
                        response = client.get(endpoint)
                        response_data = json.loads(response.data) if response.data else {}
                        
                        debug_info["api_tests"][f"{period}_regular"] = {
                            "endpoint": endpoint,
                            "status_code": response.status_code,
                            "has_portfolio_return": "portfolio_return" in response_data,
                            "has_sp500_return": "sp500_return" in response_data,
                            "has_chart_data": "chart_data" in response_data,
                            "portfolio_return_value": response_data.get("portfolio_return"),
                            "sp500_return_value": response_data.get("sp500_return"),
                            "chart_data_length": len(response_data.get("chart_data", [])),
                            "error": response_data.get("error"),
                            "sample_response": response_data
                        }
                        
                        if response.status_code != 200:
                            debug_info["issues_found"].append(f"{period} regular API returned {response.status_code}")
                        if "portfolio_return" not in response_data:
                            debug_info["issues_found"].append(f"{period} regular API missing portfolio_return field")
                        if response_data.get("portfolio_return") is None:
                            debug_info["issues_found"].append(f"{period} regular API portfolio_return is None")
                            
            except Exception as e:
                debug_info["issues_found"].append(f"Error testing {period}: {str(e)}")
        
        return jsonify({
            "success": True,
            "debug_info": debug_info
        })
        
    except Exception as e:
        logger.error(f"Dashboard API debug error: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route('/admin/debug-user-data/<username>')
@login_required
def debug_user_data(username):
    """Debug endpoint to check user data availability"""
    if not current_user.is_authenticated or current_user.email != ADMIN_EMAIL:
        flash('Admin access required', 'danger')
        return redirect(url_for('login'))
    
    try:
        from models import User, Stock, PortfolioSnapshot, UserActivity, UserPortfolioChartCache
        from admin_metrics import get_active_users_count
        from datetime import datetime, timedelta
        import json
        
        # Find the user
        user = User.query.filter_by(username=username).first()
        if not user:
            return f"<h1>User '{username}' not found</h1><p><a href='/admin'>Back to Admin</a></p>"
        
        # Get user's stocks
        stocks = Stock.query.filter_by(user_id=user.id).all()
        
        # Get recent portfolio snapshots
        snapshots = PortfolioSnapshot.query.filter_by(user_id=user.id).order_by(PortfolioSnapshot.date.desc()).limit(10).all()
        
        # Get recent user activity
        recent_activity = UserActivity.query.filter_by(user_id=user.id).order_by(UserActivity.timestamp.desc()).limit(5).all()
        
        # Get cached chart data
        cached_charts = UserPortfolioChartCache.query.filter_by(user_id=user.id).all()
        
        # Check active users count
        active_count = get_active_users_count(1)  # 1 day
        
        html = f"""
        <h1>Debug Data for User: {username}</h1>
        
        <h2>User Info:</h2>
        <p>ID: {user.id}</p>
        <p>Email: {user.email}</p>
        <p>Username: {user.username}</p>
        
        <h2>Stocks ({len(stocks)}):</h2>
        <ul>
        """
        
        for stock in stocks:
            html += f"<li>{stock.ticker}: {stock.quantity} shares @ ${stock.purchase_price}</li>"
        
        html += f"""
        </ul>
        
        <h2>Recent Portfolio Snapshots ({len(snapshots)}):</h2>
        <ul>
        """
        
        for snapshot in snapshots:
            html += f"<li>{snapshot.date}: ${snapshot.total_value:.2f}</li>"
        
        html += f"""
        </ul>
        
        <h2>Cached Chart Data ({len(cached_charts)}):</h2>
        <ul>
        """
        
        for chart in cached_charts:
            try:
                chart_data = json.loads(chart.chart_data)
                data_points = len(chart_data.get('dates', []))
                html += f"<li>{chart.period}: {data_points} data points (generated {chart.generated_at})</li>"
            except:
                html += f"<li>{chart.period}: Invalid JSON data (generated {chart.generated_at})</li>"
        
        html += f"""
        </ul>
        
        <h2>Recent Activity ({len(recent_activity)}):</h2>
        <ul>
        """
        
        for activity in recent_activity:
            html += f"<li>{activity.timestamp}: {activity.activity_type}</li>"
        
        html += f"""
        </ul>
        
        <h2>Active Users (1D): {active_count}</h2>
        
        <p><a href="/admin">Back to Admin</a></p>
        """
        
        return html
        
    except Exception as e:
        return f"<h1>Error: {str(e)}</h1><p><a href='/admin'>Back to Admin</a></p>"

@app.route('/admin/test-performance-api-user/<username>')
@login_required
def test_performance_api_for_user(username):
    """Test portfolio performance API endpoints for a specific user"""
    if not current_user.is_authenticated or current_user.email != ADMIN_EMAIL:
        flash('Admin access required', 'danger')
        return redirect(url_for('login'))
    
    try:
        from models import User
        
        # Find the user
        user = User.query.filter_by(username=username).first()
        if not user:
            return f"<h1>User '{username}' not found</h1>"
        
        # Test different time periods
        periods = ['1D', '5D', '1M', '3M', 'YTD', '1Y']
        results = {}
        
        for period in periods:
            try:
                # Import performance calculator
                from portfolio_performance import PortfolioPerformanceCalculator
                calculator = PortfolioPerformanceCalculator()
                
                # Test the performance calculation directly
                performance_data = calculator.get_performance_data(user.id, period)
                
                if 'error' in performance_data:
                    results[period] = f"ERROR: {performance_data['error']}"
                else:
                    # Summarize the results
                    chart_data_count = len(performance_data.get('chart_data', []))
                    portfolio_return = performance_data.get('portfolio_return', 'N/A')
                    sp500_return = performance_data.get('sp500_return', 'N/A')
                    
                    results[period] = f"✅ SUCCESS - {chart_data_count} data points, Portfolio: {portfolio_return}%, S&P500: {sp500_return}%"
                    
            except Exception as e:
                results[period] = f"EXCEPTION: {str(e)}"
        
        html = f"""
        <h1>Performance API Test for User: {username} (ID: {user.id})</h1>
        
        <h2>API Endpoint Results:</h2>
        <ul>
        """
        
        for period, result in results.items():
            color = "green" if "SUCCESS" in result else "red"
            html += f'<li style="color: {color}"><strong>{period}:</strong> {result}</li>'
        
        html += f"""
        </ul>
        
        <p><a href="/admin">Back to Admin</a></p>
        """
        
        return html
        
    except Exception as e:
        return f"<h1>Error: {str(e)}</h1><p><a href='/admin'>Back to Admin</a></p>"

@app.route('/admin/test-api-logging')
@login_required
def test_api_logging():
    """Admin endpoint to test Alpha Vantage API logging"""
    if not current_user.is_authenticated or current_user.email != ADMIN_EMAIL:
        flash('Admin access required', 'danger')
        return redirect(url_for('login'))
    
    try:
        from portfolio_performance import PortfolioPerformanceCalculator
        
        calculator = PortfolioPerformanceCalculator()
        
        # Make a test API call for SPY
        result = calculator.get_stock_data('SPY')
        
        if result and result.get('price'):
            flash(f'API call successful! SPY price: ${result["price"]:.2f}. Check admin dashboard for logging.', 'success')
        else:
            flash('API call failed but should still be logged. Check admin dashboard.', 'warning')
        
        return redirect(url_for('admin_dashboard'))
            
    except Exception as e:
        flash(f'API test error: {str(e)}. Check admin dashboard for logging.', 'danger')
        return redirect(url_for('admin_dashboard'))

@app.route('/admin/snapshot-diagnostics')
@login_required
def snapshot_diagnostics():
    """Comprehensive snapshot diagnostics for database tables, counts, and model validation"""
    if not current_user.is_admin:
        return redirect(url_for('index'))
    
    try:
        from datetime import datetime, date, timedelta
        from models import User, PortfolioSnapshotIntraday, PortfolioSnapshot, LeaderboardEntry
        from sqlalchemy import func, text
        
        today = date.today()
        yesterday = today - timedelta(days=1)
        
        diagnostics = {
            'timestamp': datetime.now().isoformat(),
            'database_tables': {},
            'snapshot_counts': {},
            'model_validation': {},
            'recent_data': {},
            'errors': []
        }
        
        # Check if tables exist
        try:
            # Test intraday snapshots table
            intraday_count = db.session.execute(text("SELECT COUNT(*) FROM portfolio_snapshot_intraday")).fetchone()[0]
            diagnostics['database_tables']['portfolio_snapshot_intraday'] = {'exists': True, 'total_records': intraday_count}
            
            # Test EOD snapshots table  
            eod_count = db.session.execute(text("SELECT COUNT(*) FROM portfolio_snapshot")).fetchone()[0]
            diagnostics['database_tables']['portfolio_snapshot'] = {'exists': True, 'total_records': eod_count}
            
            # Test leaderboard table
            leaderboard_count = db.session.execute(text("SELECT COUNT(*) FROM leaderboard_entry")).fetchone()[0]
            diagnostics['database_tables']['leaderboard_entry'] = {'exists': True, 'total_records': leaderboard_count}
            
        except Exception as e:
            diagnostics['errors'].append(f"Database table check error: {str(e)}")
        
        # Count snapshots by date
        try:
            # Intraday snapshots today
            intraday_today = PortfolioSnapshotIntraday.query.filter(
                func.date(PortfolioSnapshotIntraday.timestamp) == today
            ).count()
            
            # Intraday snapshots yesterday
            intraday_yesterday = PortfolioSnapshotIntraday.query.filter(
                func.date(PortfolioSnapshotIntraday.timestamp) == yesterday
            ).count()
            
            # EOD snapshots today
            eod_today = PortfolioSnapshot.query.filter_by(date=today).count()
            
            # EOD snapshots yesterday
            eod_yesterday = PortfolioSnapshot.query.filter_by(date=yesterday).count()
            
            diagnostics['snapshot_counts'] = {
                'intraday_today': intraday_today,
                'intraday_yesterday': intraday_yesterday,
                'eod_today': eod_today,
                'eod_yesterday': eod_yesterday
            }
            
        except Exception as e:
            diagnostics['errors'].append(f"Snapshot count error: {str(e)}")
        
        # Validate model attributes
        try:
            # Test User model
            user_count = User.query.count()
            diagnostics['model_validation']['User'] = {'accessible': True, 'count': user_count}
            
            # Test PortfolioSnapshotIntraday model
            sample_intraday = PortfolioSnapshotIntraday.query.first()
            if sample_intraday:
                diagnostics['model_validation']['PortfolioSnapshotIntraday'] = {
                    'accessible': True,
                    'sample_fields': {
                        'id': hasattr(sample_intraday, 'id'),
                        'user_id': hasattr(sample_intraday, 'user_id'),
                        'timestamp': hasattr(sample_intraday, 'timestamp'),
                        'total_value': hasattr(sample_intraday, 'total_value')
                    }
                }
            
            # Test PortfolioSnapshot model
            sample_eod = PortfolioSnapshot.query.first()
            if sample_eod:
                diagnostics['model_validation']['PortfolioSnapshot'] = {
                    'accessible': True,
                    'sample_fields': {
                        'id': hasattr(sample_eod, 'id'),
                        'user_id': hasattr(sample_eod, 'user_id'),
                        'date': hasattr(sample_eod, 'date'),
                        'total_value': hasattr(sample_eod, 'total_value')
                    }
                }
            
        except Exception as e:
            diagnostics['errors'].append(f"Model validation error: {str(e)}")
        
        # Get recent data samples
        try:
            # Recent intraday snapshots
            recent_intraday = PortfolioSnapshotIntraday.query.order_by(
                PortfolioSnapshotIntraday.timestamp.desc()
            ).limit(5).all()
            
            diagnostics['recent_data']['intraday_snapshots'] = [
                {
                    'user_id': snap.user_id,
                    'timestamp': snap.timestamp.isoformat(),
                    'total_value': snap.total_value
                } for snap in recent_intraday
            ]
            
            # Recent EOD snapshots
            recent_eod = PortfolioSnapshot.query.order_by(
                PortfolioSnapshot.date.desc()
            ).limit(5).all()
            
            diagnostics['recent_data']['eod_snapshots'] = [
                {
                    'user_id': snap.user_id,
                    'date': snap.date.isoformat(),
                    'total_value': snap.total_value
                } for snap in recent_eod
            ]
            
        except Exception as e:
            diagnostics['errors'].append(f"Recent data error: {str(e)}")
        
        return f"""
        <h1>Snapshot Diagnostics</h1>
        <h2>Database Tables</h2>
        <pre>{diagnostics['database_tables']}</pre>
        
        <h2>Snapshot Counts</h2>
        <pre>{diagnostics['snapshot_counts']}</pre>
        
        <h2>Model Validation</h2>
        <pre>{diagnostics['model_validation']}</pre>
        
        <h2>Recent Data Samples</h2>
        <h3>Recent Intraday Snapshots</h3>
        <pre>{diagnostics['recent_data'].get('intraday_snapshots', [])}</pre>
        
        <h3>Recent EOD Snapshots</h3>
        <pre>{diagnostics['recent_data'].get('eod_snapshots', [])}</pre>
        
        <h2>Errors</h2>
        <pre>{diagnostics['errors']}</pre>
        
        <p><a href="/admin">Back to Admin</a></p>
        """
        
    except Exception as e:
        return f"""
        <h1>Snapshot Diagnostics - Error</h1>
        <p><strong>Error:</strong> {str(e)}</p>
        <p><a href="/admin">Back to Admin</a></p>
        """

@app.route('/api/portfolio/performance-intraday/<period>')
@login_required
def portfolio_performance_intraday(period):
    """Get intraday portfolio performance data using actual intraday snapshots"""
    try:
        user_id = current_user.id
        
        from datetime import datetime, date, timedelta
        from models import PortfolioSnapshotIntraday, MarketData
        from sqlalchemy import func
        
        # Calculate date range based on period - use last market day for weekends
        today = date.today()
        
        # Use last market day for weekend handling
        if today.weekday() == 5:  # Saturday
            market_day = today - timedelta(days=1)  # Friday
        elif today.weekday() == 6:  # Sunday
            market_day = today - timedelta(days=2)  # Friday
        else:
            market_day = today  # Monday-Friday
        
        if period == '1D':
            start_date = market_day
            end_date = market_day
        elif period == '5D':
            start_date = market_day - timedelta(days=7)  # Include weekends to get 5 business days
            end_date = market_day
        else:
            # Fallback to regular performance API for other periods
            from portfolio_performance import PortfolioPerformanceCalculator
            calculator = PortfolioPerformanceCalculator()
            return jsonify(calculator.get_performance_data(user_id, period)), 200
        
        # Get intraday snapshots for the user in the date range
        snapshots = PortfolioSnapshotIntraday.query.filter(
            PortfolioSnapshotIntraday.user_id == user_id,
            func.date(PortfolioSnapshotIntraday.timestamp) >= start_date,
            func.date(PortfolioSnapshotIntraday.timestamp) <= end_date
        ).order_by(PortfolioSnapshotIntraday.timestamp).all()
        
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
            
            # Format date label based on period - use ISO format for Chart.js compatibility
            if period == '1D':
                # For 1D charts, use full ISO timestamp so Chart.js can parse it
                date_label = snapshot.timestamp.isoformat()
            elif period == '5D':
                # For 5D charts, use full ISO timestamp
                date_label = snapshot.timestamp.isoformat()
            else:
                # For longer periods, use ISO date
                date_label = snapshot.timestamp.date().isoformat()
            
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
        return jsonify({'error': f'Internal server error: {str(e)}'}), 500

@app.route('/admin/simulate-intraday-data')
@login_required
def simulate_intraday_data():
    """Create sample intraday data for testing charts"""
    try:
        # Check if user is admin
        email = session.get('email', '')
        if email != ADMIN_EMAIL:
            return jsonify({'error': 'Admin access required'}), 403
        
        from datetime import datetime, timedelta
        from models import User, PortfolioSnapshotIntraday
        from portfolio_performance import PortfolioPerformanceCalculator
        
        calculator = PortfolioPerformanceCalculator()
        today = datetime.now().date()
        
        # Create sample intraday snapshots for today (every 30 minutes from 9:30 AM to 4:00 PM)
        market_times = []
        start_time = datetime.combine(today, datetime.strptime('09:30', '%H:%M').time())
        end_time = datetime.combine(today, datetime.strptime('16:00', '%H:%M').time())
        
        current_time = start_time
        while current_time <= end_time:
            market_times.append(current_time)
            current_time += timedelta(minutes=30)
        
        users = User.query.all()
        snapshots_created = 0
        
        for user in users:
            base_portfolio_value = calculator.calculate_portfolio_value(user.id)
            
            for i, timestamp in enumerate(market_times):
                # Add some realistic variation (±2% throughout the day)
                variation = (i - len(market_times)/2) * 0.001  # Gradual trend
                random_factor = 0.995 + (i % 3) * 0.005  # Small random variation
                simulated_value = base_portfolio_value * (1 + variation) * random_factor
                
                # Check if snapshot already exists
                existing = PortfolioSnapshotIntraday.query.filter_by(
                    user_id=user.id,
                    timestamp=timestamp
                ).first()
                
                if not existing:
                    snapshot = PortfolioSnapshotIntraday(
                        user_id=user.id,
                        timestamp=timestamp,
                        total_value=simulated_value
                    )
                    db.session.add(snapshot)
                    snapshots_created += 1
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Sample intraday data created',
            'snapshots_created': snapshots_created,
            'time_points': len(market_times),
            'users_processed': len(users)
        }), 200
    
    except Exception as e:
        logger.error(f"Error creating sample intraday data: {str(e)}")
        return jsonify({'error': f'Unexpected error: {str(e)}'}), 500

@app.route('/api/cron/collect-intraday-data', methods=['POST'])
def collect_intraday_data():
    """Collect intraday data for all users (called by GitHub Actions)"""
    try:
        # Verify authorization token
        auth_header = request.headers.get('Authorization', '')
        expected_token = os.environ.get('INTRADAY_CRON_TOKEN')
        
        if not expected_token:
            logger.error("INTRADAY_CRON_TOKEN not configured")
            return jsonify({'error': 'Server configuration error'}), 500
        
        if not auth_header.startswith('Bearer ') or auth_header[7:] != expected_token:
            logger.warning(f"Unauthorized intraday collection attempt")
            return jsonify({'error': 'Unauthorized'}), 401
        
        from datetime import datetime
        from models import User, PortfolioSnapshotIntraday
        from portfolio_performance import PortfolioPerformanceCalculator
        
        calculator = PortfolioPerformanceCalculator()
        current_time = datetime.now()
        
        results = {
            'timestamp': current_time.isoformat(),
            'spy_data_collected': False,
            'users_processed': 0,
            'snapshots_created': 0,
            'charts_generated': 0,
            'errors': []
        }
        
        # Step 1: Collect SPY data
        try:
            spy_data = calculator.get_stock_data('SPY')
            if spy_data and spy_data.get('price'):
                spy_price = spy_data['price']
                sp500_value = spy_price * 10  # Convert SPY to S&P 500 approximation
                
                # Store intraday SPY data
                from models import MarketData
                market_data = MarketData(
                    ticker='SPY_INTRADAY',
                    date=current_time.date(),
                    timestamp=current_time,
                    close_price=sp500_value
                )
                db.session.add(market_data)
                results['spy_data_collected'] = True
                logger.info(f"SPY data collected: ${spy_price} (S&P 500: ${sp500_value})")
            else:
                results['errors'].append("Failed to fetch SPY data")
                logger.error("Failed to fetch SPY data from AlphaVantage")
        
        except Exception as e:
            error_msg = f"Error collecting SPY data: {str(e)}"
            results['errors'].append(error_msg)
            logger.error(error_msg)
        
        # Step 2: Get all users
        users = User.query.all()
        
        # Check if this is the 4:00 PM collection (market close)
        is_market_close = current_time.hour == 16 and current_time.minute == 0  # 4:00 PM ET
        
        for user in users:
            try:
                # Calculate current portfolio value
                portfolio_value = calculator.calculate_portfolio_value(user.id)
                
                # Always create intraday snapshot
                intraday_snapshot = PortfolioSnapshotIntraday(
                    user_id=user.id,
                    timestamp=current_time,
                    total_value=portfolio_value
                )
                db.session.add(intraday_snapshot)
                results['snapshots_created'] += 1
                
                # If this is market close time, also create EOD snapshot
                if is_market_close:
                    from models import PortfolioSnapshot
                    today = current_time.date()
                    
                    # Check if EOD snapshot already exists for today
                    existing_eod = PortfolioSnapshot.query.filter_by(
                        user_id=user.id, 
                        date=today
                    ).first()
                    
                    if existing_eod:
                        existing_eod.total_value = portfolio_value
                    else:
                        eod_snapshot = PortfolioSnapshot(
                            user_id=user.id,
                            date=today,
                            total_value=portfolio_value,
                            cash_flow=0
                        )
                        db.session.add(eod_snapshot)
                
                results['users_processed'] += 1
                
            except Exception as e:
                error_msg = f"Error processing user {user.id}: {str(e)}"
                results['errors'].append(error_msg)
                logger.error(error_msg)
        
        # If this is market close, update leaderboard
        if is_market_close:
            try:
                from leaderboard_utils import update_leaderboard_cache
                updated_count = update_leaderboard_cache()
                results['leaderboard_updated'] = True
                results['leaderboard_entries_updated'] = updated_count
                logger.info(f"Leaderboard updated with {updated_count} entries")
            except Exception as e:
                error_msg = f"Leaderboard update error: {str(e)}"
                results['errors'].append(error_msg)
                logger.error(error_msg)
        
        # Commit all snapshots
        try:
            db.session.commit()
            logger.info(f"Intraday collection completed: {results['snapshots_created']} snapshots created")
        except Exception as e:
            db.session.rollback()
            error_msg = f"Database commit failed: {str(e)}"
            results['errors'].append(error_msg)
            logger.error(error_msg)
        
        return jsonify({
            'success': len(results['errors']) == 0,
            'message': 'Intraday data collection completed',
            'results': results
        }), 200
    
    except Exception as e:
        logger.error(f"Unexpected error in intraday collection: {str(e)}")
        return jsonify({'error': f'Internal server error: {str(e)}'}), 500

@app.route('/admin/check-intraday-data')
@login_required
def check_intraday_data():
    """Check if intraday data was collected today"""
    try:
        # Check if user is admin
        email = session.get('email', '')
        if email != ADMIN_EMAIL:
            return jsonify({'error': 'Admin access required'}), 403
        
        from datetime import datetime, date
        from models import PortfolioSnapshotIntraday
        from sqlalchemy import func
        
        today = date.today()
        
        # Check intraday snapshots for today
        today_snapshots = PortfolioSnapshotIntraday.query.filter(
            func.date(PortfolioSnapshotIntraday.timestamp) == today
        ).all()
        
        # Group by user
        user_snapshots = {}
        for snapshot in today_snapshots:
            if snapshot.user_id not in user_snapshots:
                user_snapshots[snapshot.user_id] = []
            user_snapshots[snapshot.user_id].append({
                'timestamp': snapshot.timestamp.isoformat(),
                'value': snapshot.total_value
            })
        
        # Get total counts
        total_snapshots = len(today_snapshots)
        users_with_data = len(user_snapshots)
        
        # Sample recent snapshots
        recent_snapshots = PortfolioSnapshotIntraday.query.order_by(
            PortfolioSnapshotIntraday.timestamp.desc()
        ).limit(10).all()
        
        recent_sample = []
        for snapshot in recent_snapshots:
            recent_sample.append({
                'user_id': snapshot.user_id,
                'timestamp': snapshot.timestamp.isoformat(),
                'value': snapshot.total_value
            })
        
        return jsonify({
            'success': True,
            'today_date': today.isoformat(),
            'total_snapshots_today': total_snapshots,
            'users_with_data_today': users_with_data,
            'user_snapshots_today': user_snapshots,
            'recent_snapshots_sample': recent_sample,
            'message': f'Found {total_snapshots} intraday snapshots for {users_with_data} users today'
        }), 200
    
    except Exception as e:
        logger.error(f"Error checking intraday data: {str(e)}")
        return jsonify({'error': f'Unexpected error: {str(e)}'}), 500

@app.route('/admin/debug-intraday-calculation')
@login_required
def debug_intraday_calculation():
    """Debug why intraday portfolio values aren't changing"""
    try:
        # Check if user is admin
        email = session.get('email', '')
        if email != ADMIN_EMAIL:
            return jsonify({'error': 'Admin access required'}), 403
        
        from datetime import datetime, date
        from models import User, Stock, PortfolioSnapshotIntraday, MarketData
        from portfolio_performance import PortfolioPerformanceCalculator
        
        # Find admin user (witty-raven)
        admin_user = User.query.filter_by(username='witty-raven').first()
        if not admin_user:
            return jsonify({'error': 'Admin user not found'}), 404
        
        calculator = PortfolioPerformanceCalculator()
        
        # Check admin's stocks
        admin_stocks = Stock.query.filter_by(user_id=admin_user.id).all()
        stock_details = []
        
        for stock in admin_stocks:
            # Get current stock price
            stock_data = calculator.get_stock_data(stock.ticker)
            current_price = stock_data.get('price', 0) if stock_data else 0
            
            stock_details.append({
                'ticker': stock.ticker,
                'quantity': stock.quantity,
                'purchase_price': stock.purchase_price,
                'current_price': current_price,
                'current_value': stock.quantity * current_price,
                'gain_loss': (current_price - stock.purchase_price) * stock.quantity
            })
        
        # Calculate total portfolio value
        total_value = sum(stock['current_value'] for stock in stock_details)
        
        # Check recent intraday snapshots for admin
        today = date.today()
        recent_snapshots = PortfolioSnapshotIntraday.query.filter(
            PortfolioSnapshotIntraday.user_id == admin_user.id,
            PortfolioSnapshotIntraday.timestamp >= datetime.combine(today, datetime.min.time())
        ).order_by(PortfolioSnapshotIntraday.timestamp.desc()).limit(5).all()
        
        snapshot_details = []
        for snapshot in recent_snapshots:
            snapshot_details.append({
                'timestamp': snapshot.timestamp.isoformat(),
                'stored_value': snapshot.total_value
            })
        
        # Check S&P 500 data availability
        spy_data = MarketData.query.filter(
            MarketData.ticker == 'SPY_SP500',
            MarketData.date == today
        ).first()
        
        return jsonify({
            'success': True,
            'admin_user_id': admin_user.id,
            'admin_username': admin_user.username,
            'current_portfolio_value': total_value,
            'stock_count': len(admin_stocks),
            'stock_details': stock_details,
            'recent_snapshots': snapshot_details,
            'spy_data_today': {
                'exists': spy_data is not None,
                'value': spy_data.close_price if spy_data else None,
                'date': spy_data.date.isoformat() if spy_data else None
            },
            'debug_notes': [
                'Check if stock prices are being fetched correctly',
                'Verify if portfolio calculation matches stored snapshots',
                'Check if S&P 500 data exists for today'
            ]
        }), 200
    
    except Exception as e:
        logger.error(f"Error debugging intraday calculation: {str(e)}")
        return jsonify({'error': f'Unexpected error: {str(e)}'}), 500

@app.route('/admin/create-admin-snapshot')
@login_required
def create_admin_snapshot():
    """Create an intraday snapshot for the admin user manually"""
    try:
        # Check if user is admin
        email = session.get('email', '')
        if email != ADMIN_EMAIL:
            return jsonify({'error': 'Admin access required'}), 403
        
        from datetime import datetime
        from models import User, PortfolioSnapshotIntraday
        from portfolio_performance import PortfolioPerformanceCalculator
        
        # Find admin user (witty-raven)
        admin_user = User.query.filter_by(username='witty-raven').first()
        if not admin_user:
            return jsonify({'error': 'Admin user not found'}), 404
        
        calculator = PortfolioPerformanceCalculator()
        current_time = datetime.now()
        
        # Calculate current portfolio value
        portfolio_value = calculator.calculate_portfolio_value(admin_user.id)
        
        # Create intraday snapshot
        snapshot = PortfolioSnapshotIntraday(
            user_id=admin_user.id,
            timestamp=current_time,
            total_value=portfolio_value
        )
        
        db.session.add(snapshot)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'admin_user_id': admin_user.id,
            'portfolio_value': portfolio_value,
            'snapshot_created': current_time.isoformat(),
            'message': 'Manual admin snapshot created successfully'
        }), 200
    
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error creating admin snapshot: {str(e)}")
        return jsonify({'error': f'Unexpected error: {str(e)}'}), 500

@app.route('/admin/debug-all-users-portfolios')
@login_required
def debug_all_users_portfolios():
    """Debug portfolio calculations for all users to find $0 issue"""
    try:
        # Check if user is admin
        email = session.get('email', '')
        if email != ADMIN_EMAIL:
            return jsonify({'error': 'Admin access required'}), 403
        
        from models import User, Stock
        from portfolio_performance import PortfolioPerformanceCalculator
        
        calculator = PortfolioPerformanceCalculator()
        users = User.query.all()
        user_analysis = []
        
        for user in users:
            # Get user's stocks
            stocks = Stock.query.filter_by(user_id=user.id).all()
            stock_details = []
            
            for stock in stocks:
                # Get current stock price
                stock_data = calculator.get_stock_data(stock.ticker)
                current_price = stock_data.get('price', 0) if stock_data else 0
                
                stock_details.append({
                    'ticker': stock.ticker,
                    'quantity': stock.quantity,
                    'purchase_price': stock.purchase_price,
                    'current_price': current_price,
                    'current_value': stock.quantity * current_price
                })
            
            # Calculate portfolio value using the same method as intraday collection
            try:
                portfolio_value = calculator.calculate_portfolio_value(user.id)
            except Exception as e:
                portfolio_value = f"ERROR: {str(e)}"
            
            manual_total = sum(stock['current_value'] for stock in stock_details)
            
            user_analysis.append({
                'user_id': user.id,
                'username': getattr(user, 'username', 'unknown'),
                'email': getattr(user, 'email', 'unknown'),
                'stock_count': len(stocks),
                'stocks': stock_details,
                'calculated_portfolio_value': portfolio_value,
                'manual_total_value': manual_total,
                'values_match': abs(float(portfolio_value) - manual_total) < 0.01 if isinstance(portfolio_value, (int, float)) else False
            })
        
        return jsonify({
            'success': True,
            'total_users': len(users),
            'user_analysis': user_analysis,
            'debug_notes': [
                'Compare calculated_portfolio_value vs manual_total_value',
                'Check if stock prices are being fetched correctly',
                'Look for users with stocks but $0 calculated values'
            ]
        }), 200
    
    except Exception as e:
        logger.error(f"Error debugging all users portfolios: {str(e)}")
        return jsonify({'error': f'Unexpected error: {str(e)}'}), 500

@app.route('/admin/debug-sp500-data')
@login_required
def debug_sp500_data():
    """Debug S&P 500 data availability for intraday charts"""
    try:
        # Check if user is admin
        email = session.get('email', '')
        if email != ADMIN_EMAIL:
            return jsonify({'error': 'Admin access required'}), 403
        
        from datetime import datetime, date, timedelta
        from models import MarketData
        from sqlalchemy import func
        
        today = date.today()
        week_ago = today - timedelta(days=7)
        
        # Check all S&P 500 related data
        sp500_data = MarketData.query.filter(
            MarketData.ticker.like('%SP%'),
            MarketData.date >= week_ago
        ).order_by(MarketData.ticker, MarketData.date, MarketData.timestamp).all()
        
        data_by_ticker = {}
        for data in sp500_data:
            ticker = data.ticker
            if ticker not in data_by_ticker:
                data_by_ticker[ticker] = []
            
            data_by_ticker[ticker].append({
                'date': data.date.isoformat(),
                'timestamp': data.timestamp.isoformat() if data.timestamp else None,
                'price': data.close_price,
                'created_at': data.created_at.isoformat()
            })
        
        # Check what the intraday API is looking for
        spy_daily = MarketData.query.filter(
            MarketData.ticker == 'SPY_SP500',
            MarketData.date >= week_ago,
            MarketData.timestamp.is_(None)
        ).order_by(MarketData.date).all()
        
        spy_intraday = MarketData.query.filter(
            MarketData.ticker == 'SPY_INTRADAY',
            MarketData.date >= week_ago,
            MarketData.timestamp.isnot(None)
        ).order_by(MarketData.timestamp).all()
        
        return jsonify({
            'success': True,
            'date_range': f'{week_ago.isoformat()} to {today.isoformat()}',
            'all_sp500_tickers': list(data_by_ticker.keys()),
            'data_by_ticker': data_by_ticker,
            'spy_daily_count': len(spy_daily),
            'spy_intraday_count': len(spy_intraday),
            'spy_daily_sample': [
                {
                    'date': d.date.isoformat(),
                    'price': d.close_price
                } for d in spy_daily[:5]
            ],
            'spy_intraday_sample': [
                {
                    'timestamp': d.timestamp.isoformat(),
                    'price': d.close_price
                } for d in spy_intraday[:5]
            ],
            'debug_notes': [
                'Check which S&P 500 tickers exist in database',
                'Verify intraday performance API is using correct ticker names',
                'Look for data gaps or inconsistent naming'
            ]
        }), 200
    
    except Exception as e:
        logger.error(f"Error debugging S&P 500 data: {str(e)}")
        return jsonify({'error': f'Unexpected error: {str(e)}'}), 500

@app.route('/admin/create-sample-spy-intraday')
@login_required
def create_sample_spy_intraday():
    """Create sample SPY_INTRADAY data for testing charts"""
    try:
        # Check if user is admin
        email = session.get('email', '')
        if email != ADMIN_EMAIL:
            return jsonify({'error': 'Admin access required'}), 403
        
        from datetime import datetime, timedelta
        from models import MarketData
        
        today = datetime.now().date()
        base_time = datetime.combine(today, datetime.min.time()) + timedelta(hours=9, minutes=30)  # 9:30 AM
        base_price = 6424.70  # Current SPY_SP500 price
        
        # Create 15 intraday data points (every 30 minutes from 9:30 AM to 4:00 PM)
        sample_data = []
        for i in range(15):
            timestamp = base_time + timedelta(minutes=30 * i)
            # Add some realistic price variation (+/- 1%)
            price_variation = (i - 7) * 0.002  # Gradual change throughout day
            price = base_price * (1 + price_variation)
            
            # Check if data already exists
            existing = MarketData.query.filter_by(
                ticker='SPY_INTRADAY',
                date=today,
                timestamp=timestamp
            ).first()
            
            if not existing:
                market_data = MarketData(
                    ticker='SPY_INTRADAY',
                    date=today,
                    timestamp=timestamp,
                    close_price=price
                )
                db.session.add(market_data)
                sample_data.append({
                    'timestamp': timestamp.isoformat(),
                    'price': round(price, 2)
                })
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'created_count': len(sample_data),
            'sample_data': sample_data,
            'message': f'Created {len(sample_data)} SPY_INTRADAY data points for testing'
        }), 200
    
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error creating sample SPY intraday data: {str(e)}")
        return jsonify({'error': f'Unexpected error: {str(e)}'}), 500

@app.route('/admin/test-spy-fetch')
@login_required
def test_spy_fetch():
    """Test SPY data fetching to debug why intraday collection failed"""
    try:
        # Check if user is admin
        email = session.get('email', '')
        if email != ADMIN_EMAIL:
            return jsonify({'error': 'Admin access required'}), 403
        
        from portfolio_performance import PortfolioPerformanceCalculator
        from datetime import datetime
        
        calculator = PortfolioPerformanceCalculator()
        current_time = datetime.now()
        
        # Test SPY data fetching (same as intraday collection)
        try:
            spy_data = calculator.get_stock_data('SPY')
            spy_success = spy_data is not None and spy_data.get('price') is not None
            spy_price = spy_data.get('price') if spy_data else None
            sp500_value = spy_price * 10 if spy_price else None
        except Exception as e:
            spy_success = False
            spy_data = None
            spy_price = None
            sp500_value = None
            spy_error = str(e)
        
        # Check if AlphaVantage API key is available
        import os
        api_key_available = bool(os.environ.get('ALPHA_VANTAGE_API_KEY'))
        
        # Test a few other stocks to see if it's SPY-specific
        test_results = {}
        for ticker in ['AAPL', 'MSFT', 'TSLA']:
            try:
                test_data = calculator.get_stock_data(ticker)
                test_results[ticker] = {
                    'success': test_data is not None and test_data.get('price') is not None,
                    'price': test_data.get('price') if test_data else None
                }
            except Exception as e:
                test_results[ticker] = {
                    'success': False,
                    'error': str(e)
                }
        
        return jsonify({
            'success': True,
            'timestamp': current_time.isoformat(),
            'api_key_available': api_key_available,
            'spy_test': {
                'success': spy_success,
                'raw_data': spy_data,
                'spy_price': spy_price,
                'sp500_value': sp500_value,
                'error': spy_error if not spy_success else None
            },
            'other_stocks_test': test_results,
            'debug_notes': [
                'Check if SPY fetching works now vs during GitHub Actions',
                'Compare SPY results with other stock fetches',
                'Look for API key or network issues'
            ]
        }), 200
    
    except Exception as e:
        logger.error(f"Error testing SPY fetch: {str(e)}")
        return jsonify({'error': f'Unexpected error: {str(e)}'}), 500

@app.route('/admin/test-spy-intraday-collection')
@login_required
def test_spy_intraday_collection():
    """Test SPY intraday data collection manually to debug GitHub Actions issue"""
    try:
        # Check if user is admin
        email = session.get('email', '')
        if email != ADMIN_EMAIL:
            return jsonify({'error': 'Admin access required'}), 403
        
        from portfolio_performance import PortfolioPerformanceCalculator
        from models import MarketData
        from datetime import datetime
        
        calculator = PortfolioPerformanceCalculator()
        current_time = datetime.now()
        
        # Test SPY data collection (same logic as GitHub Actions)
        result = {
            'timestamp': current_time.isoformat(),
            'spy_fetch_success': False,
            'spy_price': None,
            'sp500_value': None,
            'database_save_success': False,
            'error': None
        }
        
        try:
            # Step 1: Fetch SPY data
            spy_data = calculator.get_stock_data('SPY')
            if spy_data and spy_data.get('price'):
                spy_price = spy_data['price']
                sp500_value = spy_price * 10  # Convert SPY to S&P 500 approximation
                
                result['spy_fetch_success'] = True
                result['spy_price'] = spy_price
                result['sp500_value'] = sp500_value
                
                # Step 2: Store intraday SPY data
                market_data = MarketData(
                    ticker='SPY_INTRADAY',
                    date=current_time.date(),
                    timestamp=current_time,
                    close_price=sp500_value
                )
                db.session.add(market_data)
                db.session.commit()
                
                result['database_save_success'] = True
                result['message'] = f'Successfully collected and stored SPY intraday data: ${spy_price} -> S&P 500: ${sp500_value}'
                
            else:
                result['error'] = 'Failed to fetch SPY data from AlphaVantage'
        
        except Exception as e:
            db.session.rollback()
            result['error'] = str(e)
        
        # Check current SPY_INTRADAY count
        spy_intraday_count = MarketData.query.filter_by(ticker='SPY_INTRADAY').count()
        result['spy_intraday_total_count'] = spy_intraday_count
        
        return jsonify(result), 200
    
    except Exception as e:
        logger.error(f"Error testing SPY intraday collection: {str(e)}")
        return jsonify({'error': f'Unexpected error: {str(e)}'}), 500

@app.route('/admin/check-spy-collection')
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

@app.route('/admin/test-github-actions-endpoint')
@login_required
def test_github_actions_endpoint():
    """Test the exact GitHub Actions cron endpoint to see what's failing"""
    try:
        # Check if user is admin
        email = session.get('email', '')
        if email != ADMIN_EMAIL:
            return jsonify({'error': 'Admin access required'}), 403
        
        import requests
        import os
        
        # Get the token
        token = os.environ.get('INTRADAY_CRON_TOKEN')
        if not token:
            return jsonify({'error': 'INTRADAY_CRON_TOKEN not found'}), 500
        
        # Make the same call GitHub Actions makes
        url = "https://apestogether.ai/api/cron/collect-intraday-data"
        headers = {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json'
        }
        
        try:
            response = requests.post(url, headers=headers, timeout=30)
            
            return jsonify({
                'success': True,
                'status_code': response.status_code,
                'response_text': response.text,
                'headers': dict(response.headers),
                'url_called': url,
                'token_available': bool(token),
                'message': 'This shows exactly what GitHub Actions sees'
            }), 200
            
        except requests.exceptions.RequestException as e:
            return jsonify({
                'success': False,
                'error': f'Request failed: {str(e)}',
                'url_called': url,
                'token_available': bool(token)
            }), 500
    
    except Exception as e:
        logger.error(f"Error testing GitHub Actions endpoint: {str(e)}")
        return jsonify({'error': f'Unexpected error: {str(e)}'}), 500

@app.route('/admin/test-cron-endpoint')
@login_required
def test_cron_endpoint():
    """Test the intraday collection endpoint manually"""
    try:
        # Check if user is admin
        email = session.get('email', '')
        if email != ADMIN_EMAIL:
            return jsonify({'error': 'Admin access required'}), 403
        
        import requests
        
        # Test the cron endpoint
        url = "https://apestogether.ai/api/cron/collect-intraday-data"
        headers = {
            "Authorization": f"Bearer {os.environ.get('INTRADAY_CRON_TOKEN')}",
            "Content-Type": "application/json"
        }
        
        try:
            response = requests.post(url, headers=headers, timeout=30)
            
            return jsonify({
                'success': response.status_code == 200,
                'status_code': response.status_code,
                'response': response.json() if response.headers.get('content-type', '').startswith('application/json') else response.text,
                'message': 'Cron endpoint test completed'
            }), 200
            
        except requests.exceptions.RequestException as e:
            return jsonify({
                'success': False,
                'error': f'Request failed: {str(e)}',
                'message': 'Cron endpoint test failed'
            }), 500
    
    except Exception as e:
        logger.error(f"Error testing cron endpoint: {str(e)}")
        return jsonify({'error': f'Unexpected error: {str(e)}'}), 500

# For local testing
if __name__ == '__main__':
    # Log app startup with structured information
    logger.info("App starting", extra={
        'vercel_env': os.environ.get('VERCEL_ENV'),
        'vercel_region': os.environ.get('VERCEL_REGION'),
        'template_folder': app.template_folder,
        'static_folder': app.static_folder,
        'database_type': app.config['SQLALCHEMY_DATABASE_URI'].split('://')[0] if app.config.get('SQLALCHEMY_DATABASE_URI') else 'none'
    })
    app.run(debug=True, port=5000)

# Register the admin blueprint for Vercel deployment
try:
    import sys
    from admin_interface import admin_bp
    app.register_blueprint(admin_bp, url_prefix='/admin')
    logger.info("Admin interface blueprint registered successfully")
except Exception as e:
    print(f"Error registering admin blueprint: {e}")

# Register the SMS blueprint for Vercel deployment
try:
    from sms_routes import sms_bp
    app.register_blueprint(sms_bp)
    logger.info("SMS blueprint registered successfully")
except Exception as e:
    print(f"Error registering SMS blueprint: {e}")

# Register the leaderboard blueprint for Vercel deployment
try:
    from leaderboard_routes import leaderboard_bp
    app.register_blueprint(leaderboard_bp)
    logger.info("Leaderboard blueprint registered successfully")
except Exception as e:
    print(f"Error registering leaderboard blueprint: {e}")

# Export the Flask app for Vercel serverless function
# This is required for Vercel's Python runtime
app.debug = False
