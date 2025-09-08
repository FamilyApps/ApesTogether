import os
# Removed pandas import to reduce deployment size
# import pandas as pd
from dotenv import load_dotenv
load_dotenv()

# Admin credentials from environment variables
ADMIN_EMAIL = os.environ.get('ADMIN_EMAIL', 'admin@apestogether.ai')
ADMIN_USERNAME = os.environ.get('ADMIN_USERNAME', 'admin')

# Removed alpha_vantage import to reduce deployment size
# from alpha_vantage.timeseries import TimeSeries
from flask import Flask, render_template, redirect, url_for, flash, request, session, jsonify
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.middleware.proxy_fix import ProxyFix
import json
import random
import re
# Removed imports to reduce deployment size
# from flask_migrate import Migrate
# from authlib.integrations.flask_client import OAuth
# import requests
import stripe
from datetime import datetime, date, timedelta

# App configuration
app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-key-for-testing')
# Use DATABASE_URL from environment if available, otherwise fall back to SQLite
database_url = os.environ.get('DATABASE_URL')
if database_url:
    # Vercel/Neon uses postgres://, but SQLAlchemy needs postgresql://
    database_url = database_url.replace('postgres://', 'postgresql://')
app.config['SQLALCHEMY_DATABASE_URI'] = database_url or 'sqlite:///portfolio.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Stripe configuration
app.config['STRIPE_PUBLIC_KEY'] = os.environ.get('STRIPE_PUBLIC_KEY')
app.config['STRIPE_SECRET_KEY'] = os.environ.get('STRIPE_SECRET_KEY')

app.config['STRIPE_WEBHOOK_SECRET'] = os.environ.get('STRIPE_WEBHOOK_SECRET')

stripe.api_key = app.config['STRIPE_SECRET_KEY']


# Initialize extensions
db = SQLAlchemy(app)
migrate = Migrate(app, db)
login_manager = LoginManager(app)
login_manager.login_view ='login'





oauth = OAuth(app)

# Configure OAuth providers
# Note: In production, you would need to register your app with Google and Apple
# and use real client IDs and secrets from environment variables
google = oauth.register(
    name='google',
    client_id=os.environ.get('GOOGLE_CLIENT_ID', 'google-client-id'),
    client_secret=os.environ.get('GOOGLE_CLIENT_SECRET', 'google-client-secret'),
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={
        'scope': 'openid email profile'
        # Don't hardcode redirect_uri - will use url_for in the route
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

# Database models
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(150), unique=True, nullable=False)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=True)
    oauth_provider = db.Column(db.String(20))
    oauth_id = db.Column(db.String(100))
    stocks = db.relationship('Stock', backref='owner', lazy='dynamic')
    # Add fields for tiered subscriptions
    stripe_price_id = db.Column(db.String(255), nullable=True)
    subscription_price = db.Column(db.Float, nullable=True)
    stripe_customer_id = db.Column(db.String(255), nullable=True)

class Stock(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    ticker = db.Column(db.String(10))
    quantity = db.Column(db.Float)
    purchase_price = db.Column(db.Float)
    purchase_date = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))


class Subscription(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    subscriber_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    subscribed_to_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    stripe_subscription_id = db.Column(db.String(255), unique=True, nullable=False)
    status = db.Column(db.String(50), nullable=False, default='active')  # e.g., 'active', 'canceled'
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Define relationships to get User objects
    # backref creates a 'subscriptions_made' collection on the User model (for the subscriber)
    subscriber = db.relationship('User', foreign_keys=[subscriber_id], backref='subscriptions_made')
    # backref creates a 'subscribers' collection on the User model (for the user being subscribed to)
    subscribed_to = db.relationship('User', foreign_keys=[subscribed_to_id], backref='subscribers')

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Routes
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/register')
def register():
    return render_template('register.html')

@app.route('/terms-of-service')
def terms_of_service():
    return render_template('terms_of_service.html')

@app.route('/privacy-policy')
def privacy_policy():
    return render_template('privacy_policy.html')

@app.route('/admin-direct')
@login_required
def admin_direct():
    """Super simple admin access route"""
    # Check if user is admin
    if current_user.email != ADMIN_EMAIL:
        flash('You must be an admin to access this page.', 'danger')
        return redirect(url_for('index'))
    
    # Return basic admin info as HTML to avoid any potential issues with jsonify
    admin_html = f'''
    <html>
    <head>
        <title>Admin Access</title>
        <style>
            body {{ font-family: Arial, sans-serif; margin: 40px; }}
            .container {{ max-width: 800px; margin: 0 auto; }}
            .success {{ color: green; }}
            .info {{ margin-top: 20px; background: #f5f5f5; padding: 15px; border-radius: 5px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>Admin Access</h1>
            <p class="success">✅ Admin access granted</p>
            
            <div class="info">
                <h2>Admin User Info:</h2>
                <p><strong>Email:</strong> {current_user.email}</p>
                <p><strong>Username:</strong> {current_user.username}</p>
            </div>
            
            <div class="info">
                <h2>What now?</h2>
                <p>This confirms you have admin access. The full admin dashboard is not available in this branch.</p>
                <p>To access full admin functionality, you'll need to:</p>
                <ol>
                    <li>Merge the vercel-deploy branch into master</li>
                    <li>Or configure Vercel to deploy from the vercel-deploy branch</li>
                </ol>
            </div>
        </div>
    </body>
    </html>
    '''
    
    return admin_html

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        user = User.query.filter_by(username=username).first()
        
        if user and user.password_hash and check_password_hash(user.password_hash, password):
            login_user(user)
            # Redirect to onboarding if the user has no stocks, otherwise to dashboard
            if user.stocks.count() == 0:
                return redirect(url_for('onboarding'))
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid username or password.', 'danger')
            return redirect(url_for('login'))
            
    return render_template('login.html')

@app.route('/login/google')
def login_google():
    redirect_uri = url_for('authorize_google', _external=True)
    return google.authorize_redirect(redirect_uri)

@app.route('/login/google/authorize')
def authorize_google():
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
        db.session.add(user)
        db.session.commit()
    
    login_user(user)
    
    # Check if this is the user's first login (no stocks yet)
    if user.stocks.count() == 0:
        return redirect(url_for('onboarding'))
    return redirect(url_for('dashboard'))

@app.route('/login/apple')
def login_apple():
    redirect_uri = url_for('authorize_apple', _external=True)
    return apple.authorize_redirect(redirect_uri)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email = request.form.get('email')
        username = request.form.get('username')
        password = request.form.get('password')

        # Basic validation
        if not email or not username or not password:
            flash('Please fill in all fields.', 'danger')
            return redirect(url_for('register'))

        # Check if user already exists
        if User.query.filter((User.email == email) | (User.username == username)).first():
            flash('Email or username already exists.', 'danger')
            return redirect(url_for('register'))

        # Create new user with hashed password
        new_user = User(
            email=email,
            username=username,
            password_hash=generate_password_hash(password, method='pbkdf2:sha256'),
            oauth_provider='local', # To distinguish from Google/Apple users
            stripe_price_id='price_1RbX0yQWUhVa3vgDB8vGzoFN',  # Default $4 price
            subscription_price=4.00
        )
        db.session.add(new_user)
        db.session.commit()

        login_user(new_user)
        flash('Registration successful! Welcome to the platform.', 'success')
        return redirect(url_for('onboarding'))

    return render_template('register.html')


@app.route('/login/apple/authorize')
def authorize_apple():
    token = apple.authorize_access_token()
    user_info = token.get('userinfo', {})
    
    # Check if user exists
    user = User.query.filter_by(email=user_info.get('email')).first()
    
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
            email=user_info.get('email'),
            username=username,
            oauth_provider='apple',
            oauth_id=user_info.get('sub')
        )
        db.session.add(user)
        db.session.commit()
    
    login_user(user)
    
    # Check if this is the user's first login (no stocks yet)
    if user.stocks.count() == 0:
        return redirect(url_for('onboarding'))
    return redirect(url_for('dashboard'))

@app.route('/update-username', methods=['POST'])
@login_required
def update_username():
    new_username = request.form.get('username')

    # Validation
    if not new_username:
        flash('Username cannot be empty.', 'danger')
        return redirect(url_for('dashboard'))

    if len(new_username) < 3 or len(new_username) > 20:
        flash('Username must be between 3 and 20 characters.', 'danger')
        return redirect(url_for('dashboard'))

    if not re.match(r'^[a-zA-Z0-9_-]+$', new_username):
        flash('Username can only contain letters, numbers, dashes, and underscores.', 'danger')
        return redirect(url_for('dashboard'))

    existing_user = User.query.filter(User.username == new_username).first()
    if existing_user and existing_user.id != current_user.id:
        flash('That username is already taken. Please choose another.', 'danger')
        return redirect(url_for('dashboard'))

    # Update username
    current_user.username = new_username
    db.session.commit()
    flash('Username updated successfully!', 'success')
    return redirect(url_for('dashboard'))


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/dashboard')
@login_required
def dashboard():
    stocks = current_user.stocks.all()
    portfolio_data = []
    total_portfolio_value = 0

    for stock in stocks:
        stock_data = get_stock_data(stock.ticker)
        if stock_data and stock_data.get('price') is not None:
            current_price = stock_data['price']
            stock_info = {
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
                'ticker': stock.ticker,
                'quantity': stock.quantity,
                'purchase_price': stock.purchase_price,
                'current_price': 'N/A',
                'total_value': 'N/A'
            }
            portfolio_data.append(stock_info)

    return render_template('dashboard.html', stocks=portfolio_data, total_portfolio_value=total_portfolio_value)

@app.route('/onboarding')
@login_required
def onboarding():
    return render_template('onboarding.html')

@app.route('/save_onboarding', methods=['POST'])
@login_required
def save_onboarding():
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
                    user_id=current_user.id
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

@app.route('/add_stock', methods=['POST'])
@login_required
def add_stock():
    ticker = request.form.get('ticker')
    quantity_str = request.form.get('quantity')
    
    if not ticker or not quantity_str:
        flash('Please provide both a ticker and a quantity.', 'danger')
        return redirect(url_for('dashboard'))

    try:
        quantity = float(quantity_str)
        if quantity <= 0:
            flash('Quantity must be a positive number.', 'danger')
            return redirect(url_for('dashboard'))
    except ValueError:
        flash('Invalid quantity. Please enter a number.', 'danger')
        return redirect(url_for('dashboard'))

    ticker = ticker.upper()
    stock_data = get_stock_data(ticker)
    if stock_data and stock_data.get('price') is not None:
        stock = Stock(
            ticker=ticker,
            quantity=quantity,
            purchase_price=stock_data['price'],
            user_id=current_user.id
        )
        db.session.add(stock)
        db.session.commit()

        # --- Enhanced dynamic pricing logic for 5-tier system ---
        # Update trade count tracking
        trades_today = update_trade_limit_count(current_user.id)
        
        # Check if trade limit exceeded
        exceeded, current_count, limit, tier_name = check_trade_limit_exceeded(current_user.id)
        if exceeded:
            flash(f'Trade limit reached! You have made {current_count} trades today. Your {tier_name} tier allows {limit} trades per day. Upgrade your activity to increase your subscription price and attract more subscribers!', 'warning')
        
        # Update subscription price based on 7-day trading average
        price_updated = update_user_subscription_price(current_user.id)
        if price_updated:
            flash(f'Your subscription price has been updated to ${current_user.subscription_price}/month based on your recent trading activity!', 'info')
        
        # Send SMS notifications
        from sms_utils import send_trade_confirmation_sms, send_subscriber_notification_sms
        
        # Send trade confirmation to user if SMS enabled
        send_trade_confirmation_sms(current_user.id, ticker, quantity, "bought")
        
        # Send notifications to subscribers
        subscriptions = Subscription.query.filter_by(subscribed_to_id=current_user.id, status='active').all()
        for subscription in subscriptions:
            send_subscriber_notification_sms(subscription.subscriber_id, current_user.username, ticker, quantity, "bought")
        
        # --- End of enhanced subscription price logic ---

        flash(f'Successfully added {quantity} shares of {ticker} to your portfolio.', 'success')
    
    else:
        flash(f"Could not find ticker '{ticker}'. Please check the ticker symbol and try again.", 'danger')
    
    return redirect(url_for('dashboard'))

@app.route('/delete_stock/<int:stock_id>', methods=['POST'])
@login_required
def delete_stock(stock_id):
    stock = Stock.query.get_or_404(stock_id)
    
    # Check if the stock belongs to the current user
    if stock.user_id != current_user.id:
        flash('You do not have permission to delete this stock', 'danger')
        return redirect(url_for('dashboard'))
    
    db.session.delete(stock)
    db.session.commit()
    
    flash(f'Removed {stock.ticker} from your portfolio', 'success')
    return redirect(url_for('dashboard'))

@app.route('/api/portfolio_value')
@login_required
def portfolio_value():
    stocks = current_user.stocks.all()
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

def get_stock_data(ticker_symbol):
    """Fetches real-time stock data from Alpha Vantage."""
    api_key = os.environ.get('ALPHA_VANTAGE_API_KEY')
    
    if not api_key:
        print(f"ERROR: No ALPHA_VANTAGE_API_KEY found in environment variables")
        print(f"Please add ALPHA_VANTAGE_API_KEY to your .env file")
        return None
    
    try:
        import requests
        
        # Use Alpha Vantage Global Quote endpoint for real-time data
        url = 'https://www.alphavantage.co/query'
        params = {
            'function': 'GLOBAL_QUOTE',
            'symbol': ticker_symbol,
            'apikey': api_key
        }
        
        response = requests.get(url, params=params, timeout=10)
        data = response.json()
        
        # Check for API errors
        if 'Error Message' in data:
            print(f"Alpha Vantage Error: {data['Error Message']}")
            return None
            
        if 'Note' in data:
            print(f"Alpha Vantage Rate Limit: {data['Note']}")
            return None
        
        # Extract price from Global Quote response
        quote = data.get('Global Quote', {})
        price_str = quote.get('05. price')
        
        if price_str:
            price = float(price_str)
            print(f"Retrieved real price for {ticker_symbol}: ${price}")
            return {'price': price}
        else:
            print(f"No price data found for {ticker_symbol}")
            return None
            
    except Exception as e:
        print(f"Error fetching real data for {ticker_symbol}: {e}")
        return None

# Context processor to provide current datetime to all templates
@app.context_processor
def inject_now():
    return {'now': datetime.utcnow()}

@app.route('/stock-comparison')
def stock_comparison():
    # Simplified implementation that returns mock data
    # This avoids the need for the heavy pandas and alpha_vantage dependencies
    
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

# This is the end of the stock_comparison function





# ====================================================================
# == Subscription and Payment Routes
# ====================================================================

@app.route('/explore')
@login_required
def explore():
    """Display a list of all other users to subscribe to."""
    users = User.query.filter(User.id != current_user.id).order_by(User.username).all()
    return render_template('explore.html', users=users)


@app.route('/profile/<username>')
@login_required
def profile(username):
    """Display a user's profile page."""
    # Redirect to own dashboard if viewing self
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


@app.route('/create-payment-intent', methods=['POST'])
@login_required
def create_payment_intent():
    """Creates a subscription and a Payment Intent for Stripe Elements."""
    data = request.get_json()
    user_id = data.get('user_id')
    user_to_subscribe_to = User.query.get_or_404(user_id)

    try:
        # Get or create a Stripe customer for the current user
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

        return jsonify({
            'clientSecret': subscription.latest_invoice.payment_intent.client_secret,
            'subscriptionId': subscription.id
        })
    except Exception as e:
        return jsonify(error={'message': str(e)}), 400


@app.route('/stripe-webhook', methods=['POST'])
def stripe_webhook():
    """Handle incoming webhooks from Stripe."""
    payload = request.data
    sig_header = request.headers.get('Stripe-Signature')
    webhook_secret = app.config['STRIPE_WEBHOOK_SECRET']
    event = None

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, webhook_secret)
    except (ValueError, stripe.error.SignatureVerificationError) as e:
        return 'Invalid request', 400

    # Handle successful payment for the new subscription flow
    if event['type'] == 'invoice.payment_succeeded':
        invoice = event['data']['object']
        stripe_subscription_id = invoice.get('subscription')
        # We need to retrieve the subscription to get the metadata we set
        subscription_details = stripe.Subscription.retrieve(stripe_subscription_id)
        metadata = subscription_details.get('metadata')

        if metadata and stripe_subscription_id:
            # Check if we've already processed this subscription to handle webhook retries
            existing_sub = Subscription.query.filter_by(stripe_subscription_id=stripe_subscription_id).first()
            if not existing_sub:
                subscriber_id = metadata.get('subscriber_id')
                subscribed_to_id = metadata.get('subscribed_to_id')
                
                new_subscription = Subscription(
                    subscriber_id=subscriber_id,
                    subscribed_to_id=subscribed_to_id,
                    stripe_subscription_id=stripe_subscription_id,
                    status='active'
                )
                db.session.add(new_subscription)
                db.session.commit()

    # Handle canceled subscription
    if event['type'] == 'customer.subscription.deleted':
        subscription_object = event['data']['object']
        stripe_subscription_id = subscription_object['id']
        subscription = Subscription.query.filter_by(stripe_subscription_id=stripe_subscription_id).first()
        if subscription:
            subscription.status = 'canceled'
            db.session.commit()

    return 'Success', 200


# Register the admin blueprint
try:
    from admin_interface import admin_bp
    app.register_blueprint(admin_bp)
    print("Admin blueprint registered successfully")
except ImportError as e:
    print(f"Could not register admin blueprint: {e}")

# Register the admin debug blueprint
try:
    from admin_route_debug import debug_bp
    app.register_blueprint(debug_bp)
    print("Admin debug blueprint registered successfully")
except ImportError as e:
    print(f"Could not register admin debug blueprint: {e}")

# Register the main debug blueprint
try:
    from debug_routes import debug_bp as main_debug_bp
    app.register_blueprint(main_debug_bp)
    print("Main debug blueprint registered successfully")
except ImportError as e:
    print(f"Could not register main debug blueprint: {e}")

# Register the SMS blueprint
try:
    from sms_routes import sms_bp
    app.register_blueprint(sms_bp)
    print("SMS blueprint registered successfully")
except ImportError as e:
    print(f"Could not register SMS blueprint: {e}")

# Register the leaderboard blueprint
try:
    app.register_blueprint(leaderboard_bp)
    print("Leaderboard blueprint registered successfully")
except ImportError as e:
    print(f"Could not register leaderboard blueprint: {e}")


# Portfolio performance API endpoints
@app.route('/api/portfolio/performance/<period>')
@login_required
def get_portfolio_performance(period):
    """Get portfolio performance data for a specific time period"""
    try:
        from portfolio_performance import performance_calculator
        performance_data = performance_calculator.get_performance_data(current_user.id, period.upper())
        return jsonify(performance_data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/portfolio/snapshot')
@login_required
def create_portfolio_snapshot():
    """Create a portfolio snapshot for today"""
    try:
        from portfolio_performance import performance_calculator
        performance_calculator.create_daily_snapshot(current_user.id)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/admin/run-migration')
def run_migration():
    """One-time migration endpoint - remove after use"""
    try:
        # Check if user is admin
        if not (current_user.is_authenticated and 
                (current_user.email == ADMIN_EMAIL or current_user.username == ADMIN_USERNAME)):
            return jsonify({'error': 'Admin access required'}), 403
        
        # Create the new tables
        from models import db, User, Stock, Subscription, Transaction, PortfolioSnapshot, MarketData, SP500ChartCache, SubscriptionTier, TradeLimit, SMSNotification, StockInfo, LeaderboardEntry
        from subscription_utils import update_user_subscription_price, update_trade_limit_count, check_trade_limit_exceeded, get_subscription_tier_info
        db.create_all()
        
        return jsonify({
            'success': True, 
            'message': 'Migration completed successfully. New tables created.'
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    # In development, run with debug mode
    if os.environ.get('FLASK_ENV') == 'development':
        app.run(host='0.0.0.0', port=5003, debug=True)
    else:
        # In production, let the WSGI server handle it
        app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), debug=False)
