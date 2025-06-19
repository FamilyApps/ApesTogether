import os
from flask import Flask, render_template, redirect, url_for, flash, request, session, jsonify
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from authlib.integrations.flask_client import OAuth
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.middleware.proxy_fix import ProxyFix
import json
import random
import re
import requests
import stripe
from datetime import datetime, date

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
login_manager = LoginManager(app)
login_manager.login_view = 'login'
oauth = OAuth(app)

# Configure OAuth providers
# Note: In production, you would need to register your app with Google and Apple
# and use real client IDs and secrets from environment variables
google = oauth.register(
    name='google',
    client_id=os.environ.get('GOOGLE_CLIENT_ID', 'google-client-id'),
    client_secret=os.environ.get('GOOGLE_CLIENT_SECRET', 'google-client-secret'),
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={'scope': 'openid email profile'},
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
    return render_template('dashboard.html', stocks=stocks)

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
            current_price = get_stock_price(stock_data['ticker'])
            
            if current_price is not None:
                stock = Stock(
                    ticker=stock_data['ticker'],
                    quantity=stock_data['quantity'],
                    purchase_price=current_price,
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
    current_price = get_stock_price(ticker)
    
    if current_price is None:
        flash(f"Could not fetch the price for '{ticker}'. Please check the ticker symbol and try again.", 'danger')
        return redirect(url_for('dashboard'))
        
    stock = Stock(
        ticker=ticker,
        quantity=quantity,
        purchase_price=current_price,
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
    total_value = 0
    portfolio_data = []

    for stock in stocks:
        current_price_api = get_stock_price(stock.ticker)
        
        # Ensure purchase_price_db is a float, default to 0.0 if None from DB.
        purchase_price_db = stock.purchase_price if stock.purchase_price is not None else 0.0

        value = 0
        gain_loss = 0
        display_current_price = 0  # Price to show as 'current' on the dashboard

        if current_price_api is not None:
            display_current_price = current_price_api
            value = stock.quantity * current_price_api
            # Only calculate gain/loss if the original purchase_price from DB was not None.
            if stock.purchase_price is not None:
                gain_loss = (current_price_api - purchase_price_db) * stock.quantity
            # If original stock.purchase_price was None, gain_loss remains 0.
        else:
            # API failed to get current price. Use purchase_price_db as current for display.
            # Value is based on purchase_price_db. Gain/loss is 0.
            display_current_price = purchase_price_db
            value = stock.quantity * purchase_price_db
            gain_loss = 0 # Cannot determine gain/loss if current live price is unknown

        total_value += value
        
        portfolio_data.append({
            'id': stock.id,
            'ticker': stock.ticker,
            'quantity': stock.quantity,
            'purchase_price': purchase_price_db,  # Send a valid float (original or 0.0)
            'current_price': display_current_price, # Send a valid float
            'value': value,
            'gain_loss': gain_loss
        })
    
    return jsonify({
        'total_value': total_value,
        'stocks': portfolio_data
    })

# Simple in-memory cache for stock prices to avoid repeated API calls
price_cache = {}
cache_expiry = {}

# Function to get stock price with caching
def get_stock_price(ticker):
    # Check cache first (cache valid for 5 minutes)
    current_time = datetime.now().timestamp()
    if ticker in price_cache and ticker in cache_expiry:
        if current_time < cache_expiry[ticker]:
            return price_cache[ticker]
    
    # If not in cache or expired, fetch new price
    price = fetch_stock_price(ticker)
    
    # Update cache if price is valid
    if price is not None:
        price_cache[ticker] = price
        cache_expiry[ticker] = current_time + 90  # Cache for 90 seconds
    
    return price

# Function to fetch stock price from Alpha Vantage API
def fetch_stock_price(ticker):
    api_key = os.environ.get('ALPHA_VANTAGE_API_KEY')
    if not api_key:
        print("Error: ALPHA_VANTAGE_API_KEY not found in environment variables.")
        return None

    url = f"https://www.alphavantage.co/query?function=GLOBAL_QUOTE&symbol={ticker}&entitlement=realtime&apikey={api_key}"
    
    try:
        response = requests.get(url)
        response.raise_for_status()  # Raise an exception for bad status codes
        data = response.json()
        
        # Check for API limit message
        if "Note" in data and "Thank you for using Alpha Vantage!" in data["Note"]:
            print(f"API call limit reached for {ticker}. Please wait and try again later.")
            return None # Or return a specific value to indicate limit reached

        if "Global Quote" in data and "05. price" in data["Global Quote"]:
            price_str = data["Global Quote"]["05. price"]
            return float(price_str)
        else:
            print(f"Error: Could not fetch price for {ticker}. Response: {data}")
            return None
            
    except requests.exceptions.RequestException as e:
        print(f"Error fetching stock price for {ticker}: {e}")
        return None
    except (KeyError, ValueError) as e:
        print(f"Error parsing stock price for {ticker}: {e}")
        return None

from datetime import datetime, timedelta

# Context processor to provide current datetime to all templates
@app.context_processor
def inject_now():
    return {'now': datetime.utcnow()}

@app.route('/stock-comparison')
def stock_comparison():
    api_key = os.environ.get('ALPHA_VANTAGE_API_KEY')
    if not api_key:
        flash("ALPHA_VANTAGE_API_KEY not found.", "danger")
        return render_template('stock_comparison.html', dates=[], tsla_prices=[], sp500_prices=[])

    # Fetch TSLA data
    tsla_url = f"https://www.alphavantage.co/query?function=TIME_SERIES_DAILY_ADJUSTED&symbol=TSLA&outputsize=full&entitlement=realtime&apikey={api_key}"
    # Fetch S&P 500 data (using SPY as a proxy for S&P 500)
    sp500_url = f"https://www.alphavantage.co/query?function=TIME_SERIES_DAILY_ADJUSTED&symbol=SPY&outputsize=full&entitlement=realtime&apikey={api_key}"

    try:
        tsla_response = requests.get(tsla_url)
        sp500_response = requests.get(sp500_url)
        tsla_response.raise_for_status()
        sp500_response.raise_for_status()

        tsla_data = tsla_response.json().get("Time Series (Daily)", {})
        sp500_data = sp500_response.json().get("Time Series (Daily)", {})

        if not tsla_data or not sp500_data:
            # Handle case where API limit might be reached or data is empty
            note_tsla = tsla_response.json().get("Note", "")
            note_sp500 = sp500_response.json().get("Note", "")
            if "Thank you for using Alpha Vantage!" in note_tsla or "Thank you for using Alpha Vantage!" in note_sp500:
                 flash("API call limit reached. Please try again later.", "warning")
            else:
                flash("Could not retrieve stock data.", "danger")
            return render_template('stock_comparison.html', dates=[], tsla_prices=[], sp500_prices=[])

        # Get dates from the last 6 months
        end_date = datetime.now()
        start_date = end_date - timedelta(days=180)
        
        all_dates = sorted([d for d in tsla_data.keys() if datetime.strptime(d, '%Y-%m-%d') >= start_date], reverse=True)
        
        common_dates = []
        tsla_prices = []
        sp500_prices = []

        for date_str in all_dates:
            if date_str in sp500_data:
                common_dates.append(date_str)
                tsla_prices.append(float(tsla_data[date_str]['4. close']))
                sp500_prices.append(float(sp500_data[date_str]['4. close']))
        
        # Reverse the lists to have dates in ascending order for the chart
        common_dates.reverse()
        tsla_prices.reverse()
        sp500_prices.reverse()

    except requests.exceptions.RequestException as e:
        flash(f"Error fetching data from Alpha Vantage: {e}", "danger")
        return render_template('stock_comparison.html', dates=[], tsla_prices=[], sp500_prices=[])
    except (KeyError, ValueError) as e:
        flash(f"Error parsing data from Alpha Vantage: {e}", "danger")
        return render_template('stock_comparison.html', dates=[], tsla_prices=[], sp500_prices=[])

    return render_template('stock_comparison.html', 
                         dates=common_dates,
                         tsla_prices=tsla_prices,
                         sp500_prices=sp500_prices)


# Create database tables
with app.app_context():
    db.create_all()


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
            price = get_stock_price(stock.ticker)
            if price:
                value = stock.quantity * price
                total_value += value
                stock_details.append({'ticker': stock.ticker, 'quantity': stock.quantity, 'price': price, 'value': value})
        portfolio_data = {
            'stocks': stock_details,
            'total_value': total_value
        }

    return render_template('profile.html', user_to_view=user_to_view, subscription=subscription, portfolio_data=portfolio_data, price=user_to_view.subscription_price)


@app.route('/create-checkout-session/<int:user_id>')
@login_required
def create_checkout_session(user_id):
    """Create a Stripe Checkout session for a subscription."""
    user_to_subscribe_to = User.query.get_or_404(user_id)

    # Prevent users from subscribing to themselves
    if user_to_subscribe_to.id == current_user.id:
        flash('You cannot subscribe to yourself.', 'error')
        return redirect(url_for('profile', username=user_to_subscribe_to.username))

    try:
        checkout_session = stripe.checkout.Session.create(
            payment_method_types=['card', 'paypal'],
            payment_method_options={
                'paypal': {'preferred_network': 'paypal'}
            },
            line_items=[
                {
                    'price': user_to_subscribe_to.stripe_price_id,
                    'quantity': 1,
                },
            ],
            mode='subscription',
            success_url=url_for('profile', username=user_to_subscribe_to.username, _external=True) + '?session_id={CHECKOUT_SESSION_ID}',
            cancel_url=url_for('profile', username=user_to_subscribe_to.username, _external=True),
            metadata={
                'subscriber_id': current_user.id,
                'subscribed_to_id': user_to_subscribe_to.id
            },
            customer_email=current_user.email
        )
        return redirect(checkout_session.url, code=303)
    except Exception as e:
        flash(f'Error connecting to payment provider: {str(e)}', 'error')
        return redirect(url_for('profile', username=user_to_subscribe_to.username))


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

    # Handle successful payment
    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        metadata = session.get('metadata')
        stripe_subscription_id = session.get('subscription')
        if metadata and stripe_subscription_id:
            # Prevent duplicates from webhook retries
            if not Subscription.query.filter_by(stripe_subscription_id=stripe_subscription_id).first():
                new_subscription = Subscription(
                    subscriber_id=metadata['subscriber_id'],
                    subscribed_to_id=metadata['subscribed_to_id'],
                    stripe_subscription_id=stripe_subscription_id,
                    status='active'
                )
                db.session.add(new_subscription)
                db.session.commit()

    # Handle canceled subscription
    if event['type'] == 'customer.subscription.deleted':
        session = event['data']['object']
        stripe_subscription_id = session.get('id')
        subscription = Subscription.query.filter_by(stripe_subscription_id=stripe_subscription_id).first()
        if subscription:
            subscription.status = 'canceled'
            db.session.commit()

    return 'Success', 200


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
