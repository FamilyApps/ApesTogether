import os
import pandas as pd
from dotenv import load_dotenv
from dotenv import load_dotenv
load_dotenv()
from alpha_vantage.timeseries import TimeSeries
from flask import Flask, render_template, redirect, url_for, flash, request, session, jsonify
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_migrate import Migrate
from authlib.integrations.flask_client import OAuth
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.middleware.proxy_fix import ProxyFix
import json
import random
import re
import requests
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

@app.route('/admin-direct')
@login_required
def admin_direct():
    """Direct admin access route that bypasses blueprints"""
    # Check if user is admin
    if current_user.email != 'fordutilityapps@gmail.com':
        flash('You must be an admin to access this page.', 'danger')
        return redirect(url_for('index'))
    
    # Get counts for dashboard
    user_count = User.query.count()
    stock_count = Stock.query.count()
    transaction_count = 0  # Placeholder since Transaction model might not exist
    subscription_count = Subscription.query.count()
    
    # Get latest users
    latest_users = User.query.order_by(User.id.desc()).limit(5).all()
    
    # Return admin info as JSON since we might not have the admin template
    admin_data = {
        'user_count': user_count,
        'stock_count': stock_count,
        'transaction_count': transaction_count,
        'subscription_count': subscription_count,
        'latest_users': [{'id': user.id, 'email': user.email, 'username': user.username} for user in latest_users],
        'admin_email': current_user.email,
        'admin_username': current_user.username
    }
    
    return jsonify(admin_data)

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

        # --- Logic to update subscription price based on trade frequency ---
        today_start = datetime.combine(date.today(), datetime.min.time())
        trades_today = Stock.query.filter(
            Stock.user_id == current_user.id,
            Stock.purchase_date >= today_start
        ).count()

        # If this is the 5th trade of the day, and price is not already $8
        if trades_today > 4 and current_user.subscription_price != 8.00:
            current_user.stripe_price_id = 'price_1RbX1FQWUhVa3vgDoTuknCC6'  # $8 Price ID
            current_user.subscription_price = 8.00
            db.session.commit()
            flash('Congratulations on your active trading! Your portfolio subscription price for new subscribers has been updated to $8/month.', 'info')
        # --- End of subscription price logic ---

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
    try:
        api_key = os.environ.get('ALPHA_VANTAGE_API_KEY')
        if not api_key:
            print("Error: ALPHA_VANTAGE_API_KEY not found in environment variables.")
            return None

        ts = TimeSeries(key=api_key, output_format='json')
        # Use get_quote_endpoint for the latest price
        data, meta_data = ts.get_quote_endpoint(symbol=ticker_symbol)
        
        # The key for price in a quote endpoint is '05. price'
        if '05. price' in data:
            return {'price': float(data['05. price'])}
        else:
            # Check for API limit note
            if "Note" in data and "Thank you for using Alpha Vantage!" in data.get("Note", ""):
                 print(f"API call limit likely reached for {ticker_symbol}.")
            else:
                 print(f"Could not find price for {ticker_symbol}. Response: {data}")
            return None

    except Exception as e:
        print(f"Error fetching data for {ticker_symbol} from Alpha Vantage: {e}")
        return None

# Context processor to provide current datetime to all templates
@app.context_processor
def inject_now():
    return {'now': datetime.utcnow()}

@app.route('/stock-comparison')
def stock_comparison():
    api_key = os.environ.get('ALPHA_VANTAGE_API_KEY')
    if not api_key:
        flash("ALPHA_VANTAGE_API_KEY not found. Cannot display stock comparison.", "danger")
        return render_template('stock_comparison.html', dates=[], tsla_prices=[], sp500_prices=[])

    try:
        ts = TimeSeries(key=api_key, output_format='pandas')
        
        # Fetch data for TSLA and SPY (S&P 500 proxy)
        # Using 'compact' for the last 100 data points, which is enough for ~6 months of trading days
        tsla_data, _ = ts.get_daily_adjusted('TSLA', outputsize='compact')
        spy_data, _ = ts.get_daily_adjusted('SPY', outputsize='compact')

        # Combine data on common dates
        # We'll use the adjusted close price '5. adjusted close' for a better comparison
        combined_data = pd.concat([tsla_data['5. adjusted close'], spy_data['5. adjusted close']], axis=1, keys=['tsla', 'spy']).dropna()
        
        # Get last 180 days if more than that is returned
        end_date = datetime.now()
        start_date = end_date - timedelta(days=180)
        combined_data = combined_data[combined_data.index >= start_date]

        # Prepare data for Chart.js
        common_dates = combined_data.index.strftime('%Y-%m-%d').tolist()
        tsla_prices = combined_data['tsla'].tolist()
        sp500_prices = combined_data['spy'].tolist()
        
        # Reverse for chronological order in chart
        common_dates.reverse()
        tsla_prices.reverse()
        sp500_prices.reverse()

    except Exception as e:
        # Check for common API limit error message
        if "Thank you for using Alpha Vantage!" in str(e):
            flash("API call limit reached. Please try again later.", "warning")
        else:
            flash(f"Error fetching comparison data from Alpha Vantage: {e}", "danger")
        return render_template('stock_comparison.html', dates=[], tsla_prices=[], sp500_prices=[])

    return render_template('stock_comparison.html', 
                         dates=common_dates,
                         tsla_prices=tsla_prices,
                         sp500_prices=sp500_prices)





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


if __name__ == '__main__':
    # In development, run with debug mode
    if os.environ.get('FLASK_ENV') == 'development':
        app.run(host='0.0.0.0', port=5003, debug=True)
    else:
        # In production, let the WSGI server handle it
        app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), debug=False)
