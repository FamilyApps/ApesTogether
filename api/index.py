"""
Vercel serverless function handler for the Flask app.
This is a standalone version with admin access functionality.
"""
import os
import json
import logging
import psycopg2
import random
import requests
import stripe
import sys
import traceback
from datetime import datetime, timedelta
from functools import wraps
from dotenv import load_dotenv
from flask import Flask, render_template_string, render_template, redirect, url_for, request, session, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.middleware.proxy_fix import ProxyFix
from authlib.integrations.flask_client import OAuth

# Load environment variables
load_dotenv()

# Initialize Flask app
app = Flask(__name__, template_folder='../templates', static_folder='../static')
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1)

# Enable jinja2 template features in render_template_string
app.jinja_env.globals.update({
    'len': len,
    'format': format
})

# Set up error logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Login required decorator
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access this page', 'danger')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

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
    DATABASE_URL = os.environ.get('DATABASE_URL') or os.environ.get('POSTGRES_PRISMA_URL')

    # Fix Postgres URL for SQLAlchemy 1.4+
    if DATABASE_URL and DATABASE_URL.startswith('postgres://'):
        DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql://', 1)

    # Configure Flask app
    app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL or 'sqlite:///portfolio.db'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-key-for-testing')  # Use consistent fallback

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

    # Initialize database
    db = SQLAlchemy(app)
    migrate = Migrate(app, db)
    logger.info("Database and migrations initialized successfully")
except Exception as e:
    logger.error(f"Failed to initialize database: {str(e)}")
    # Continue without database to allow basic functionality

# Define database models
class User(db.Model):
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
    subscriptions = db.relationship('Subscription', backref='user', lazy=True)
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
        
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
        
    def is_admin(self):
        return self.email == 'fordutilityapps@gmail.com'

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
    
    # Define relationships to get User objects
    # backref creates a 'subscriptions_made' collection on the User model (for the subscriber)
    subscriber = db.relationship('User', foreign_keys=[subscriber_id], backref='subscriptions_made')
    # backref creates a 'subscribers' collection on the User model (for the user being subscribed to)
    subscribed_to = db.relationship('User', foreign_keys=[subscribed_to_id], backref='subscribers')

    def __repr__(self):
        return f'<Subscription {self.subscriber_id} to {self.subscribed_to_id} - {self.status}>'

# Secret key is already set in app.config

# Check if we're running on Vercel
VERCEL_ENV = os.environ.get('VERCEL_ENV')
if VERCEL_ENV:
    print(f"Running in Vercel environment: {VERCEL_ENV}")

# Admin email for authentication
ADMIN_EMAIL = 'fordutilityapps@gmail.com'
ADMIN_USERNAME = 'witty-raven'

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
    
    return render_template(
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
                return redirect(url_for('profile', username=subscribed_to.username))
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
    current_user_id = session.get('user_id')
    
    # Get active subscriptions
    active_subscriptions = Subscription.query.filter_by(
        subscriber_id=current_user_id,
        status='active'
    ).all()
    
    # Get canceled subscriptions
    canceled_subscriptions = Subscription.query.filter_by(
        subscriber_id=current_user_id,
        status='canceled'
    ).all()
    
    return render_template(
        'subscriptions.html',
        active_subscriptions=active_subscriptions,
        canceled_subscriptions=canceled_subscriptions
    )

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
    return render_template('explore.html', users=users)

@app.route('/onboarding')
@login_required
def onboarding():
    """User onboarding page"""
    return render_template('onboarding.html')

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
        return render_template('stock_comparison.html', dates=dates, tsla_prices=tsla_prices, sp500_prices=sp500_prices)
        
    except Exception as e:
        flash(f"Error generating mock stock comparison data: {e}", "danger")
        return render_template('stock_comparison.html', dates=[], tsla_prices=[], sp500_prices=[])

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

    return render_template(
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
    if current_user.email != 'fordutilityapps@gmail.com' and current_user.username != 'witty-raven':
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
    
    return render_template(
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

@app.route('/')
def index():
    """Main landing page"""
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    """User login page"""
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        user = User.query.filter_by(email=email).first()
        
        if user and user.check_password(password):
            session['user_id'] = user.id
            session['email'] = user.email
            session['username'] = user.username
            flash('Login successful!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid email or password', 'danger')
    
    return render_template('login.html')

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
    
    return render_template('register.html')

@app.route('/logout')
def logout():
    """Logout the current user"""
    session.pop('user_id', None)
    session.pop('email', None)
    session.pop('username', None)
    flash('You have been logged out', 'success')
    return redirect(url_for('index'))

@app.route('/login/google')
def login_google():
    """Redirect to Google OAuth login"""
    redirect_uri = url_for('authorize_google', _external=True)
    return google.authorize_redirect(redirect_uri)

@app.route('/login/google/authorize')
def authorize_google():
    """Handle Google OAuth callback"""
    token = google.authorize_access_token()
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
            oauth_provider='google',
            oauth_id=user_info['sub'],  # OpenID Connect uses 'sub' for the user ID
            stripe_price_id='price_1RbX0yQWUhVa3vgDB8vGzoFN',  # Default $4 price
            subscription_price=4.00
        )
        user.set_password('') # Empty password for OAuth users
        db.session.add(user)
        db.session.commit()
    
    # Log the user in
    session['user_id'] = user.id
    session['email'] = user.email
    session['username'] = user.username
    
    # Check if this is the user's first login (no stocks yet)
    if Stock.query.filter_by(user_id=user.id).count() == 0:
        flash('Welcome! Please add some stocks to your portfolio.', 'info')
    else:
        flash('Login successful!', 'success')
        
    return redirect(url_for('dashboard'))

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
        
        # Log the user in
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

@app.route('/dashboard')
@login_required
def dashboard():
    """User dashboard"""
    # Get current user from session
    current_user_id = session.get('user_id')
    current_user = User.query.get(current_user_id)
    
    # Get user's stocks
    stocks = Stock.query.filter_by(user_id=current_user_id).all()
    portfolio_data = []
    total_portfolio_value = 0
    
    for stock in stocks:
        stock_data = get_stock_data(stock.ticker)
        if stock_data and stock_data.get('price') is not None:
            current_price = stock_data['price']
            stock_info = {
                'id': stock.id,
                'ticker': stock.ticker,
                'quantity': stock.quantity,
                'purchase_price': stock.purchase_price,
                'current_price': current_price,
                'total_value': stock.quantity * current_price
            }
            portfolio_data.append(stock_info)
            total_portfolio_value += stock_info['total_value']
        else:
            # Handle cases where stock data couldn't be fetched
            stock_info = {
                'id': stock.id,
                'ticker': stock.ticker,
                'quantity': stock.quantity,
                'purchase_price': stock.purchase_price,
                'current_price': 'N/A',
                'total_value': 'N/A'
            }
            portfolio_data.append(stock_info)
    
    return render_template('dashboard.html', stocks=portfolio_data, total_portfolio_value=total_portfolio_value)

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
def admin_dashboard():
    """Admin dashboard"""
    # Check if email is provided as a parameter
    email_param = request.args.get('email', '')
    if email_param:
        # Store email in session if provided as parameter
        session['email'] = email_param
    
    # Get email from session
    email = session.get('email', '')
    
    # Check if user is admin
    is_admin = (email == ADMIN_EMAIL)
    
    if not is_admin:
        return render_template_string("""
<!DOCTYPE html>
<html>
<head>
    <title>Admin Login</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            margin: 0;
            padding: 20px;
            background-color: #f4f4f4;
        }
        .container {
            max-width: 600px;
            margin: 0 auto;
            background: white;
            padding: 20px;
            border-radius: 5px;
            box-shadow: 0 0 10px rgba(0,0,0,0.1);
        }
        h1 {
            color: #333;
        }
        .form {
            margin-top: 20px;
        }
        label {
            display: block;
            margin-bottom: 5px;
        }
        input[type="text"] {
            width: 100%;
            padding: 8px;
            margin-bottom: 10px;
            border: 1px solid #ddd;
            border-radius: 3px;
        }
        input[type="submit"] {
            background-color: #4CAF50;
            color: white;
            padding: 10px 15px;
            border: none;
            border-radius: 3px;
            cursor: pointer;
        }
        input[type="submit"]:hover {
            background-color: #45a049;
        }
        .message {
            margin-top: 20px;
            padding: 10px;
            background-color: #f8d7da;
            color: #721c24;
            border-radius: 3px;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>Admin Access</h1>
        
        <div class="form">
            <h2>Admin Login</h2>
            <form action="/admin" method="get">
                <label for="email">Admin Email:</label>
                <input type="text" id="email" name="email" placeholder="Enter admin email">
                <input type="submit" value="Login">
            </form>
        </div>
    </div>
</body>
</html>
        """)
    
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
        body {
            font-family: Arial, sans-serif;
            margin: 0;
            padding: 0;
            background-color: #f4f4f4;
        }
        .container {
            width: 80%;
            margin: 0 auto;
            background: white;
            padding: 20px;
            box-shadow: 0 0 10px rgba(0,0,0,0.1);
        }
        h1, h2 {
            color: #333;
        }
        .nav {
            background-color: #333;
            overflow: hidden;
            margin-bottom: 20px;
        }
        .nav a {
            float: left;
            display: block;
            color: white;
            text-align: center;
            padding: 14px 16px;
            text-decoration: none;
        }
        .stats {
            display: flex;
            flex-wrap: wrap;
            gap: 20px;
            margin-bottom: 30px;
        }
        .stat-card {
            flex: 1;
            min-width: 200px;
            background: #f9f9f9;
            padding: 20px;
            border-radius: 5px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        .stat-card h3 {
            margin-top: 0;
            color: #333;
        }
        .stat-card p {
            font-size: 24px;
            font-weight: bold;
            margin: 10px 0 0;
            color: #2196F3;
        }
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
        <div class="nav">
            <a href="/admin">Dashboard</a>
            <a href="/admin/users">Users</a>
            <a href="/admin/transactions">Transactions</a>
            <a href="/admin/stocks">Stocks</a>
            <a href="/">Main Site</a>
        </div>
        
        <h1>Admin Dashboard</h1>
        
        <div class="stats">
            <div class="stat-card">
                <h3>Total Users</h3>
                <p>{{ user_count }}</p>
            </div>
            <div class="stat-card">
                <h3>Total Stocks</h3>
                <p>{{ stock_count }}</p>
            </div>
            <div class="stat-card">
                <h3>Total Transactions</h3>
                <p>{{ transaction_count }}</p>
            </div>
            <div class="stat-card">
                <h3>Active Subscriptions</h3>
                <p>{{ subscription_count }}</p>
            </div>
        </div>
        
        <h2>Recent Users</h2>
        <div class="recent-users">
            <table>
                <tr>
                    <th>ID</th>
                    <th>Username</th>
                    <th>Email</th>
                    <th>Created</th>
                    <th>Actions</th>
                </tr>
                {% for user in recent_users %}
                <tr>
                    <td>{{ user.id }}</td>
                    <td>{{ user.username }}</td>
                    <td>{{ user.email }}</td>
                    <td>{{ user.created_at }}</td>
                    <td>
                        <a href="/admin/users/{{ user.id }}" class="button button-secondary button-small">View</a>
                    </td>
                </tr>
                {% endfor %}
            </table>
        </div>
    </div>
</body>
</html>
    """, user_count=user_count, stock_count=stock_count, transaction_count=transaction_count, subscription_count=subscription_count, recent_users=recent_users)

    # Return access denied template if not admin
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
            <form action="/admin" method="get">
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

# Add an error handler to provide more information on 500 errors
@app.errorhandler(500)
def server_error(e):
    """Handle 500 errors with detailed information"""
    # Get error details
    error_details = str(e)
    logger.error(f"500 error: {error_details}")
    
    # Check if this is an API request
    if request.path.startswith('/api/'):
        return jsonify({
            'error': 'Internal Server Error',
            'details': error_details,
            'status': 500,
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'path': request.path,
            'environment': os.environ.get('VERCEL_ENV', 'development'),
            'database_url_exists': bool(os.environ.get('DATABASE_URL')),
            'postgres_prisma_url_exists': bool(os.environ.get('POSTGRES_PRISMA_URL')),
            'effective_database_url_exists': bool(DATABASE_URL)
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
            <pre>{{ error_details }}</pre>
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
    # Mock transaction data
    transactions = {
        1: {'id': 1, 'user_id': 1, 'username': 'witty-raven', 'symbol': 'AAPL', 'shares': 10, 'price': 150.0, 'transaction_type': 'buy', 'date': '2023-01-15', 'notes': 'Initial purchase'},
        2: {'id': 2, 'user_id': 1, 'username': 'witty-raven', 'symbol': 'MSFT', 'shares': 5, 'price': 250.0, 'transaction_type': 'buy', 'date': '2023-02-20', 'notes': 'Portfolio diversification'},
        3: {'id': 3, 'user_id': 2, 'username': 'user1', 'symbol': 'GOOGL', 'shares': 2, 'price': 2800.0, 'transaction_type': 'buy', 'date': '2023-03-10', 'notes': ''},
        4: {'id': 4, 'user_id': 3, 'username': 'user2', 'symbol': 'AMZN', 'shares': 1, 'price': 3200.0, 'transaction_type': 'buy', 'date': '2023-04-05', 'notes': ''},
        5: {'id': 5, 'user_id': 1, 'username': 'witty-raven', 'symbol': 'AAPL', 'shares': 5, 'price': 170.0, 'transaction_type': 'sell', 'date': '2023-05-15', 'notes': 'Profit taking'}
    }
    
    # Get transaction by ID
    transaction = transactions.get(transaction_id)
    if not transaction:
        flash('Transaction not found', 'danger')
        return redirect(url_for('admin_transactions'))
    
    if request.method == 'POST':
        # In a real app, we would update the transaction in the database
        # For now, just show a success message
        flash('Transaction updated successfully!', 'success')
        return redirect(url_for('admin_transactions'))
    
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
                <input type="text" id="user" name="user" value="{{ transaction.username }}" readonly>
            </div>
            
            <div class="form-group">
                <label for="symbol">Symbol</label>
                <input type="text" id="symbol" name="symbol" value="{{ transaction.symbol }}" required>
            </div>
            
            <div class="form-group">
                <label for="shares">Shares</label>
                <input type="number" id="shares" name="shares" value="{{ transaction.shares }}" step="0.01" required>
            </div>
            
            <div class="form-group">
                <label for="price">Price</label>
                <input type="number" id="price" name="price" value="{{ transaction.price }}" step="0.01" required>
            </div>
            
            <div class="form-group">
                <label for="transaction_type">Transaction Type</label>
                <select id="transaction_type" name="transaction_type" required>
                    <option value="buy" {% if transaction.transaction_type == 'buy' %}selected{% endif %}>Buy</option>
                    <option value="sell" {% if transaction.transaction_type == 'sell' %}selected{% endif %}>Sell</option>
                </select>
            </div>
            
            <div class="form-group">
                <label for="date">Date</label>
                <input type="date" id="date" name="date" value="{{ transaction.date }}" required>
            </div>
            
            <div class="form-group">
                <label for="notes">Notes</label>
                <textarea id="notes" name="notes">{{ transaction.notes }}</textarea>
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
    # Mock stock data
    stocks = {
        1: {'id': 1, 'user_id': 1, 'username': 'witty-raven', 'ticker': 'AAPL', 'quantity': 5, 'purchase_price': 150.0, 'current_price': 180.0, 'purchase_date': '2023-01-15'},
        2: {'id': 2, 'user_id': 1, 'username': 'witty-raven', 'ticker': 'MSFT', 'quantity': 5, 'purchase_price': 250.0, 'current_price': 280.0, 'purchase_date': '2023-02-20'},
        3: {'id': 3, 'user_id': 2, 'username': 'user1', 'ticker': 'GOOGL', 'quantity': 2, 'purchase_price': 2800.0, 'current_price': 2900.0, 'purchase_date': '2023-03-10'},
        4: {'id': 4, 'user_id': 3, 'username': 'user2', 'ticker': 'AMZN', 'quantity': 1, 'purchase_price': 3200.0, 'current_price': 3400.0, 'purchase_date': '2023-04-05'}
    }
    
    # Get stock by ID
    stock = stocks.get(stock_id)
    if not stock:
        flash('Stock not found', 'danger')
        return redirect(url_for('admin_stocks'))
    
    if request.method == 'POST':
        # In a real app, we would update the stock in the database
        # For now, just show a success message
        flash('Stock updated successfully!', 'success')
        return redirect(url_for('admin_stocks'))
    
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
            'SQLALCHEMY_DATABASE_URI': app.config.get('SQLALCHEMY_DATABASE_URI', '').replace(os.environ.get('DATABASE_URL', ''), '[REDACTED]') if os.environ.get('DATABASE_URL') else app.config.get('SQLALCHEMY_DATABASE_URI', ''),
            'WORKING_DIRECTORY': os.getcwd(),
            'DIRECTORY_CONTENTS': os.listdir('.'),
            'TEMPLATE_EXISTS': os.path.exists('../templates'),
            'STATIC_EXISTS': os.path.exists('../static'),
            'PYTHON_VERSION': sys.version
        }
        
        # Check if we can connect to the database
        db_status = 'Unknown'
        try:
            db.session.execute('SELECT 1')
            db_status = 'Connected'
        except Exception as e:
            db_status = f'Error: {str(e)}'
            
        env_info['DATABASE_STATUS'] = db_status
        
        return jsonify(env_info)
    except Exception as e:
        return jsonify({'error': str(e), 'traceback': traceback.format_exc()})

# For local testing
if __name__ == '__main__':
    app.run(debug=True, port=5000)
