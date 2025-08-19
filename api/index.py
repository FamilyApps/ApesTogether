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

# Subscription model is already defined above

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
    # Get user's portfolio
    portfolio_data = []
    total_portfolio_value = 0
    
    if current_user.is_authenticated:
        # Get user's stocks from database
        stocks = Stock.query.filter_by(user_id=current_user.id).all()
        
        for stock in stocks:
            # In a real app, you would fetch current prices from an API
            # For now, we'll use a simple mock price
            current_price = stock.purchase_price * (1 + (random.random() - 0.5) * 0.1)  # +/- 5% from purchase price
            value = stock.quantity * current_price
            gain_loss = value - (stock.quantity * stock.purchase_price)
            gain_loss_percent = (gain_loss / (stock.quantity * stock.purchase_price)) * 100
            
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
    
    return render_template_with_defaults('dashboard.html', stocks=portfolio_data, total_portfolio_value=total_portfolio_value, current_user=current_user)

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
    # Get current user from session
    current_user_id = session.get('user_id')
    
    stocks = Stock.query.filter_by(user_id=current_user_id).all()
    portfolio_data = []
    total_value = 0

    for stock in stocks:
        stock_data = get_stock_data(stock.ticker)
        if stock_data and stock_data.get('price') is not None:
            current_price = stock_data['price']
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
        for stock in stocks:
            stock_data = get_stock_data(stock.ticker)
            if stock_data and stock_data.get('price') is not None:
                price = stock_data['price']
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

def get_stock_data(ticker_symbol):
    """Fetches real-time stock data from Alpha Vantage."""
    # Default mock prices for common stocks
    mock_prices = {
        'AAPL': 185.92,
        'MSFT': 420.45,
        'GOOGL': 175.33,
        'AMZN': 182.81,
        'TSLA': 248.29,
        'META': 475.12,
        'NVDA': 116.64,
    }
    
    try:
        api_key = os.environ.get('ALPHA_VANTAGE_API_KEY')
        if not api_key:
            logger.warning("Alpha Vantage API key not found, using mock data")
            # Return mock data if no API key is available
            price = mock_prices.get(ticker_symbol.upper(), 100.00)
            return {'price': price}
        
        # Use Alpha Vantage API to get real stock data
        url = f'https://www.alphavantage.co/query?function=GLOBAL_QUOTE&symbol={ticker_symbol}&apikey={api_key}'
        response = requests.get(url, timeout=5)  # Add timeout to prevent hanging
        data = response.json()
        
        if 'Global Quote' in data and '05. price' in data['Global Quote']:
            price = float(data['Global Quote']['05. price'])
            return {'price': price}
        else:
            logger.warning(f"Could not get price for {ticker_symbol}, using fallback")
            # Fallback to mock data if API doesn't return expected format
            price = mock_prices.get(ticker_symbol.upper(), 100.00)
            return {'price': price}
    except Exception as e:
        logger.error(f"Error getting stock data for {ticker_symbol}: {str(e)}")
        # Return a default price if there's an error
        price = mock_prices.get(ticker_symbol.upper(), 100.00)
        return {'price': price}

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
    """Main landing page"""
    try:
        logger.info("Rendering index page")
        logger.info(f"Template folder: {app.template_folder}")
        logger.info(f"Template exists: {os.path.exists(os.path.join(app.template_folder, 'index.html'))}")
        
        # Try to list template files
        try:
            template_files = os.listdir(app.template_folder)
            logger.info(f"Template files: {template_files}")
        except Exception as e:
            logger.error(f"Error listing template files: {str(e)}")
        
        # Use the helper function to ensure consistent template variables
        return render_template_with_defaults('index.html')
    except Exception as e:
        logger.error(f"Error in index route: {str(e)}")
        logger.error(traceback.format_exc())
        return render_template_string("""<html><body><h1>Error rendering index page</h1><p>{{ error }}</p></body></html>""", error=str(e))

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
    
    return redirect(url_for('dashboard'))

@app.route('/admin')
@login_required
def admin_dashboard():
    """Secure admin dashboard - requires Google OAuth authentication"""
    # Verify user is authenticated
    if not current_user.is_authenticated:
        flash('You must be logged in to access the admin dashboard.', 'warning')
        return redirect(url_for('login'))
    
    # Check if user is admin using the secure is_admin property
    if not current_user.is_admin:
        flash('You do not have permission to access the admin dashboard.', 'danger')
        return redirect(url_for('dashboard'))
    
    try:
        # Get real data from database
        user_count = User.query.count()
        stock_count = Stock.query.count()
        transaction_count = Transaction.query.count()
        subscription_count = Subscription.query.count()
        
        # Get recent users
        recent_users = User.query.order_by(User.created_at.desc()).limit(5).all()
    except Exception as e:
        # If database connection fails, use mock data
        app.logger.error(f"Database error: {str(e)}")
        user_count = 15
        stock_count = 42
        transaction_count = 87
        subscription_count = 10
        
        # Mock recent users
        recent_users = [
            {'id': 1, 'username': 'user1', 'email': 'user1@example.com'},
            {'id': 2, 'username': 'user2', 'email': 'user2@example.com'},
            {'id': 3, 'username': 'user3', 'email': 'user3@example.com'},
        ]
    
    return render_template_string("""
<!DOCTYPE html>
<html>
<head>
    <title>Admin Dashboard</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 40px; background-color: #f5f5f5; }
        .container { max-width: 1200px; margin: 0 auto; background: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
        .header { border-bottom: 2px solid #4CAF50; padding-bottom: 20px; margin-bottom: 30px; }
        .stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; margin-bottom: 30px; }
        .stat-card { background: linear-gradient(135deg, #4CAF50, #45a049); color: white; padding: 20px; border-radius: 8px; text-align: center; }
        .stat-number { font-size: 2em; font-weight: bold; margin-bottom: 5px; }
        .stat-label { font-size: 0.9em; opacity: 0.9; }
        .section { margin-bottom: 30px; }
        .section h3 { color: #333; border-bottom: 1px solid #ddd; padding-bottom: 10px; }
        .user-list { background: #f9f9f9; padding: 15px; border-radius: 5px; }
        .user-item { padding: 8px 0; border-bottom: 1px solid #eee; }
        .user-item:last-child { border-bottom: none; }
        .button { display: inline-block; background: #4CAF50; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; margin: 5px; }
        .button:hover { background: #45a049; }
        .nav-buttons { margin-top: 20px; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🚀 Admin Dashboard</h1>
            <p>Welcome, {current_user.email}! You have admin access to ApesTogether.</p>
        </div>
        
        <div class="stats">
            <div class="stat-card">
                <div class="stat-number">{user_count}</div>
                <div class="stat-label">Total Users</div>
            </div>
            <div class="stat-card">
                <div class="stat-number">{stock_count}</div>
                <div class="stat-label">Tracked Stocks</div>
            </div>
            <div class="stat-card">
                <div class="stat-number">{transaction_count}</div>
                <div class="stat-label">Transactions</div>
            </div>
            <div class="stat-card">
                <div class="stat-number">{subscription_count}</div>
                <div class="stat-label">Subscriptions</div>
            </div>
        </div>
        
        <div class="section">
            <h3>📊 Quick Actions</h3>
            <a href="/admin/users" class="button">👥 Manage Users</a>
            <a href="/admin/transactions" class="button">💰 View Transactions</a>
            <a href="/admin/debug-auth" class="button">🔍 Debug Auth</a>
        </div>
        
        <div class="section">
            <h3>👥 Recent Users</h3>
            <div class="user-list">
                {% for user in recent_users %}
                <div class="user-item">
                    <strong>{{ user.username if user.username else 'N/A' }}</strong> - {{ user.email if user.email else 'N/A' }}
                    <small>(ID: {{ user.id if user.id else 'N/A' }})</small>
                </div>
                {% endfor %}
            </div>
        </div>
        
        <div class="nav-buttons">
            <a href="/dashboard" class="button">📈 Back to Dashboard</a>
            <a href="/logout" class="button">🚪 Logout</a>
        </div>
    </div>
</body>
</html>
    """.format(
        current_user=current_user,
        user_count=user_count,
        stock_count=stock_count,
        transaction_count=transaction_count,
        subscription_count=subscription_count,
        recent_users=recent_users
    ))

@app.route('/admin/debug-auth')
@login_required
def debug_admin_auth():
    """Debug endpoint to check admin authentication values"""
    return f"""
    <h1>Admin Authentication Debug</h1>
    <p><strong>Current User Email:</strong> '{current_user.email}'</p>
    <p><strong>Current User Username:</strong> '{current_user.username}'</p>
    <p><strong>ADMIN_EMAIL from env:</strong> '{ADMIN_EMAIL}'</p>
    <p><strong>ADMIN_USERNAME from env:</strong> '{ADMIN_USERNAME}'</p>
    <p><strong>Email Match:</strong> {current_user.email == ADMIN_EMAIL}</p>
    <p><strong>Username Match:</strong> {current_user.username == ADMIN_USERNAME}</p>
    <p><strong>is_admin result:</strong> {current_user.is_admin}</p>
    <p><strong>Email comparison:</strong> '{current_user.email}' == '{ADMIN_EMAIL}'</p>
    <p><strong>Username comparison:</strong> '{current_user.username}' == '{ADMIN_USERNAME}'</p>
    <hr>
    <p><a href="/admin">Try Admin Dashboard</a> | <a href="/dashboard">Back to Dashboard</a></p>
    """

# Admin routes for viewing users and transactions
@app.route('/admin/users')
@admin_required
def admin_users():
    """Admin users list"""
    try:
        # Get real user data from database
        users_query = User.query.all()
        
        # Format user data
        users = []
        for user in users_query:
            # Count stocks and transactions
            stock_count = Stock.query.filter_by(user_id=user.id).count()
            transaction_count = Transaction.query.filter_by(user_id=user.id).count()
            
            # Get subscription price
            subscription = Subscription.query.filter_by(user_id=user.id, status='active').first()
            subscription_price = subscription.price if subscription else 0
            
            users.append({
                'id': user.id,
                'username': user.username,
                'email': user.email,
                'stocks': stock_count,
                'transactions': transaction_count,
                'subscription_price': subscription_price,
                'stripe_customer_id': user.stripe_customer_id or 'N/A'
            })
    except Exception as e:
        app.logger.error(f"Database error in admin_users: {str(e)}")
        # Fallback to mock data if database fails
        users = [
            {'id': 1, 'username': 'witty-raven', 'email': 'fordutilityapps@gmail.com', 'stocks': 3, 'transactions': 5, 'subscription_price': 0, 'stripe_customer_id': 'cus_123'},
            {'id': 2, 'username': 'user1', 'email': 'user1@example.com', 'stocks': 2, 'transactions': 3, 'subscription_price': 4.99, 'stripe_customer_id': 'cus_456'},
            {'id': 3, 'username': 'user2', 'email': 'user2@example.com', 'stocks': 1, 'transactions': 2, 'subscription_price': 9.99, 'stripe_customer_id': 'cus_789'}
        ]
    
    return render_template_string("""
<!DOCTYPE html>
<html>
<head>
    <title>Admin - Users</title>
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
        .search-box {
            margin: 20px 0;
            padding: 15px;
            background: #f9f9f9;
            border-radius: 5px;
        }
        .search-box input[type="text"] {
            padding: 8px;
            width: 300px;
            border: 1px solid #ddd;
            border-radius: 4px;
        }
        .search-box button {
            padding: 8px 15px;
            background: #4CAF50;
            color: white;
            border: none;
            border-radius: 4px;
            cursor: pointer;
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
        
        <h1>User Management</h1>
        
        <div class="search-box">
            <form method="get" action="/admin/users">
                <input type="text" name="search" placeholder="Search by username or email" value="{{ request.args.get('search', '') }}">
                <button type="submit">Search</button>
            </form>
        </div>
        
        <table>
            <tr>
                <th>ID</th>
                <th>Username</th>
                <th>Email</th>
                <th>Stocks</th>
                <th>Transactions</th>
                <th>Subscription</th>
                <th>Actions</th>
            </tr>
            {% for user in users %}
            <tr>
                <td>{{ user.id }}</td>
                <td>{{ user.username }}</td>
                <td>{{ user.email }}</td>
                <td>{{ user.stocks }}</td>
                <td>{{ user.transactions }}</td>
                <td>${{ user.subscription_price }}</td>
                <td>
                    <a href="/admin/users/{{ user.id }}" class="button button-secondary button-small">View</a>
                    <a href="/admin/users/{{ user.id }}/edit" class="button button-warning button-small">Edit</a>
                </td>
            </tr>
            {% endfor %}
        </table>
        
        <a href="/admin" class="button">Back to Dashboard</a>
    </div>
</body>
</html>
    """, users=users)

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
                'symbol': tx.symbol,
                'shares': tx.shares,
                'price': tx.price,
                'transaction_type': tx.transaction_type,
                'date': tx.date.strftime('%Y-%m-%d'),
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
        filtered_transactions = [t for t in filtered_transactions if t['symbol'].lower() == symbol_filter.lower()]
    if type_filter:
        filtered_transactions = [t for t in filtered_transactions if t['transaction_type'].lower() == type_filter.lower()]
    
    # Get unique users and symbols for filters
    unique_users = list(set([(t['user_id'], t['username']) for t in transactions]))
    unique_symbols = list(set([t['symbol'] for t in transactions]))
    
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
                    <option value="">All Symbols</option>
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
                <th>Symbol</th>
                <th>Shares</th>
                <th>Price</th>
                <th>Total</th>
                <th>Type</th>
                <th>Date</th>
                <th>Notes</th>
                <th>Actions</th>
            </tr>
            {% for tx in filtered_transactions %}
            <tr>
                <td>{{ tx.id }}</td>
                <td>{{ tx.username }}</td>
                <td>{{ tx.symbol }}</td>
                <td>{{ tx.shares }}</td>
                <td>${{ '%0.2f'|format(tx.price) }}</td>
                <td>${{ '%0.2f'|format(tx.shares * tx.price) }}</td>
                <td class="{{ tx.transaction_type }}">{{ tx.transaction_type|upper }}</td>
                <td>{{ tx.date }}</td>
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
                'current_price': stock.current_price,
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

@app.route('/admin/users/<int:user_id>')
@admin_required
def admin_user_detail(user_id):
    """Admin route to view user details"""
    try:
        # Get real user data from database
        user = User.query.get(user_id)
        
        if not user:
            flash('User not found', 'danger')
            return redirect(url_for('admin_users'))
        
        # Count stocks and transactions
        stock_count = Stock.query.filter_by(user_id=user.id).count()
        transaction_count = Transaction.query.filter_by(user_id=user.id).count()
        
        # Get subscription
        subscription = Subscription.query.filter_by(user_id=user.id, status='active').first()
        subscription_price = subscription.price if subscription else 0
        
        # Format user data
        user_data = {
            'id': user.id,
            'username': user.username,
            'email': user.email,
            'stocks': stock_count,
            'transactions': transaction_count,
            'subscription_price': subscription_price,
            'stripe_customer_id': user.stripe_customer_id or 'N/A',
            'created_at': user.created_at.strftime('%Y-%m-%d')
        }
        
        # Get user's stocks
        stocks_query = Stock.query.filter_by(user_id=user.id).all()
        stocks = []
        for stock in stocks_query:
            stocks.append({
                'id': stock.id,
                'ticker': stock.ticker,
                'quantity': stock.quantity,
                'purchase_price': stock.purchase_price,
                'current_price': stock.current_price,
                'purchase_date': stock.purchase_date.strftime('%Y-%m-%d')
            })
        
        # Get user's transactions
        transactions_query = Transaction.query.filter_by(user_id=user.id).order_by(Transaction.date.desc()).all()
        transactions = []
        for tx in transactions_query:
            transactions.append({
                'id': tx.id,
                'symbol': tx.symbol,
                'shares': tx.shares,
                'price': tx.price,
                'transaction_type': tx.transaction_type,
                'date': tx.date.strftime('%Y-%m-%d'),
                'notes': tx.notes or ''
            })
    except Exception as e:
        app.logger.error(f"Database error in admin_user_detail: {str(e)}")
        # Fallback to mock data if database fails
        user_data = {
            'id': user_id,
            'username': 'witty-raven' if user_id == 1 else f'user{user_id}',
            'email': 'fordutilityapps@gmail.com' if user_id == 1 else f'user{user_id}@example.com',
            'stocks': 3 if user_id == 1 else 1,
            'transactions': 5 if user_id == 1 else 2,
            'subscription_price': 0 if user_id == 1 else 4.99,
            'stripe_customer_id': f'cus_{123 + user_id * 100}',
            'created_at': '2023-01-01'
        }
        
        # Mock user's stocks
        stocks = [
            {'id': 1, 'ticker': 'AAPL', 'quantity': 5, 'purchase_price': 150.0, 'current_price': 180.0, 'purchase_date': '2023-01-15'},
            {'id': 2, 'ticker': 'MSFT', 'quantity': 5, 'purchase_price': 250.0, 'current_price': 280.0, 'purchase_date': '2023-02-20'}
        ] if user_id == 1 else []
        
        # Mock user's transactions
        transactions = [
            {'id': 1, 'symbol': 'AAPL', 'shares': 10, 'price': 150.0, 'transaction_type': 'buy', 'date': '2023-01-15', 'notes': 'Initial purchase'},
            {'id': 2, 'symbol': 'MSFT', 'shares': 5, 'price': 250.0, 'transaction_type': 'buy', 'date': '2023-02-20', 'notes': 'Portfolio diversification'},
            {'id': 5, 'symbol': 'AAPL', 'shares': 5, 'price': 170.0, 'transaction_type': 'sell', 'date': '2023-05-15', 'notes': 'Profit taking'}
        ] if user_id == 1 else []
    
    return render_template_string("""
<!DOCTYPE html>
<html>
<head>
    <title>User Details</title>
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
        .user-info {
            background: #f5f5f5;
            padding: 20px;
            border-radius: 5px;
            margin-bottom: 20px;
        }
        .user-info h2 {
            margin-top: 0;
        }
        .user-info .detail {
            margin-bottom: 10px;
        }
        .user-info .label {
            font-weight: bold;
            display: inline-block;
            width: 150px;
        }
        .section {
            margin-top: 30px;
        }
        .buy { color: green; }
        .sell { color: red; }
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
        
        <h1>User Details</h1>
        
        <div class="user-info">
            <h2>{{ user.username }}</h2>
            <div class="detail"><span class="label">Email:</span> {{ user.email }}</div>
            <div class="detail"><span class="label">User ID:</span> {{ user.id }}</div>
            <div class="detail"><span class="label">Created:</span> {{ user.created_at }}</div>
            <div class="detail"><span class="label">Subscription:</span> ${{ user.subscription_price }}</div>
            <div class="detail"><span class="label">Stripe Customer:</span> {{ user.stripe_customer_id }}</div>
            <div class="detail"><span class="label">Stocks:</span> {{ user.stocks }}</div>
            <div class="detail"><span class="label">Transactions:</span> {{ user.transactions }}</div>
            
            <a href="/admin/users/{{ user.id }}/edit" class="button button-warning">Edit User</a>
        </div>
        
        <div class="section">
            <h2>User's Stocks</h2>
            {% if stocks %}
            <table>
                <tr>
                    <th>Ticker</th>
                    <th>Quantity</th>
                    <th>Purchase Price</th>
                    <th>Current Price</th>
                    <th>Total Value</th>
                    <th>Purchase Date</th>
                    <th>Actions</th>
                </tr>
                {% for stock in stocks %}
                <tr>
                    <td>{{ stock.ticker }}</td>
                    <td>{{ stock.quantity }}</td>
                    <td>${{ '%0.2f'|format(stock.purchase_price) }}</td>
                    <td>${{ '%0.2f'|format(stock.current_price) }}</td>
                    <td>${{ '%0.2f'|format(stock.quantity * stock.current_price) }}</td>
                    <td>{{ stock.purchase_date }}</td>
                    <td>
                        <a href="/admin/stocks/{{ stock.id }}/edit" class="button button-warning button-small">Edit</a>
                        <a href="/admin/stocks/{{ stock.id }}/delete" class="button button-danger button-small">Delete</a>
                    </td>
                </tr>
                {% endfor %}
            </table>
            <a href="/admin/users/{{ user.id }}/add-stock" class="button button-secondary">Add Stock</a>
            {% else %}
            <p>This user has no stocks.</p>
            <a href="/admin/users/{{ user.id }}/add-stock" class="button button-secondary">Add Stock</a>
            {% endif %}
        </div>
        
        <div class="section">
            <h2>User's Transactions</h2>
            {% if transactions %}
            <table>
                <tr>
                    <th>Symbol</th>
                    <th>Shares</th>
                    <th>Price</th>
                    <th>Total</th>
                    <th>Type</th>
                    <th>Date</th>
                    <th>Notes</th>
                    <th>Actions</th>
                </tr>
                {% for tx in transactions %}
                <tr>
                    <td>{{ tx.symbol }}</td>
                    <td>{{ tx.shares }}</td>
                    <td>${{ '%0.2f'|format(tx.price) }}</td>
                    <td>${{ '%0.2f'|format(tx.shares * tx.price) }}</td>
                    <td class="{{ tx.transaction_type }}">{{ tx.transaction_type|upper }}</td>
                    <td>{{ tx.date }}</td>
                    <td>{{ tx.notes }}</td>
                    <td>
                        <a href="/admin/transactions/{{ tx.id }}/edit" class="button button-warning button-small">Edit</a>
                        <a href="/admin/transactions/{{ tx.id }}/delete" class="button button-danger button-small">Delete</a>
                    </td>
                </tr>
                {% endfor %}
            </table>
            <a href="/admin/users/{{ user.id }}/add-transaction" class="button button-secondary">Add Transaction</a>
            {% else %}
            <p>This user has no transactions.</p>
            <a href="/admin/users/{{ user.id }}/add-transaction" class="button button-secondary">Add Transaction</a>
            {% endif %}
        </div>
        
        <a href="/admin/users" class="button">Back to Users</a>
    </div>
</body>
</html>
    """, user=user, stocks=stocks, transactions=transactions)

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
                <input type="text" id="ticker" name="ticker" value="{{ transaction_data.symbol }}" required>
            </div>
            
            <div class="form-group">
                <label for="quantity">Shares</label>
                <input type="number" id="quantity" name="quantity" value="{{ transaction_data.shares }}" step="0.01" required>
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
                <input type="date" id="date" name="date" value="{{ transaction_data.date }}" required>
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

# Export the Flask app for Vercel serverless function
# This is required for Vercel's Python runtime
app.debug = False
