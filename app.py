import os
from flask import Flask, render_template, redirect, url_for, flash, request, session, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from authlib.integrations.flask_client import OAuth
from werkzeug.security import generate_password_hash, check_password_hash
import json
import requests
from datetime import datetime

# App configuration
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-key-for-testing')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///portfolio.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SERVER_NAME'] = 'localhost:5000'

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
    email = db.Column(db.String(100), unique=True)
    name = db.Column(db.String(100))
    password_hash = db.Column(db.String(200))
    oauth_provider = db.Column(db.String(20))
    oauth_id = db.Column(db.String(100))
    stocks = db.relationship('Stock', backref='owner', lazy='dynamic')

class Stock(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    ticker = db.Column(db.String(10))
    quantity = db.Column(db.Float)
    purchase_price = db.Column(db.Float)
    purchase_date = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Routes
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/login')
def login():
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
        # Create new user
        user = User(
            email=user_info['email'],
            name=user_info.get('name', user_info['email']),
            oauth_provider='google',
            oauth_id=user_info['sub']  # OpenID Connect uses 'sub' for the user ID
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

@app.route('/login/apple/authorize')
def authorize_apple():
    token = apple.authorize_access_token()
    user_info = token.get('userinfo', {})
    
    # Check if user exists
    user = User.query.filter_by(email=user_info.get('email')).first()
    
    if not user:
        # Create new user
        user = User(
            email=user_info.get('email'),
            name=user_info.get('name', user_info.get('email')),
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
    
    # If we have valid stocks, add them all at once
    if stocks_to_add:
        for stock_data in stocks_to_add:
            try:
                # Get price (will use cache if available)
                current_price = get_stock_price(stock_data['ticker'])
                
                # Create new stock
                stock = Stock(
                    ticker=stock_data['ticker'],
                    quantity=stock_data['quantity'],
                    purchase_price=current_price,
                    user_id=current_user.id
                )
                db.session.add(stock)
                
            except Exception as e:
                # Use fallback price on error
                stock = Stock(
                    ticker=stock_data['ticker'],
                    quantity=stock_data['quantity'],
                    purchase_price=100.0,  # Fallback price
                    user_id=current_user.id
                )
                db.session.add(stock)
        
        db.session.commit()
        flash('Your portfolio has been set up with current market prices!', 'success')
    else:
        flash('No valid stocks were entered.', 'warning')
    
    return redirect(url_for('dashboard'))

@app.route('/add_stock', methods=['POST'])
@login_required
def add_stock():
    ticker = request.form.get('ticker')
    quantity = request.form.get('quantity')
    
    if not ticker or not quantity:
        flash('Please fill in all fields', 'danger')
        return redirect(url_for('dashboard'))
    
    try:
        # Fetch current price (will use cache if available)
        ticker = ticker.upper()
        current_price = get_stock_price(ticker)
        
        # Create new stock with fetched price
        stock = Stock(
            ticker=ticker,
            quantity=float(quantity),
            purchase_price=current_price,  # Already a float from get_stock_price
            user_id=current_user.id
        )
        db.session.add(stock)
        db.session.commit()
        flash(f'Added {quantity} shares of {ticker} at ${current_price:.2f}', 'success')
    except Exception as e:
        # Use a fallback price if there's an error
        try:
            stock = Stock(
                ticker=ticker,
                quantity=float(quantity),
                purchase_price=100.0,  # Fallback price
                user_id=current_user.id
            )
            db.session.add(stock)
            db.session.commit()
            flash(f'Added {quantity} shares of {ticker} with placeholder price of $100.', 'warning')
        except Exception as e2:
            flash(f'Error adding stock: {str(e2)}', 'danger')
    
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
    stock_values = []
    
    for stock in stocks:
        # For demo purposes, we'll use the purchase price as the current price
        # In a real app, you would fetch real-time prices from a stock API
        current_price = stock.purchase_price
        value = stock.quantity * current_price
        total_value += value
        stock_values.append({
            'ticker': stock.ticker,
            'quantity': stock.quantity,
            'current_price': current_price,
            'value': value,
            'purchase_price': stock.purchase_price,
            'gain_loss': 0,  # No gain/loss in demo mode
            'id': stock.id
        })
    
    return jsonify({
        'total_value': total_value,
        'stocks': stock_values
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
        cache_expiry[ticker] = current_time + 60  # Cache for 1 minute
    
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

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
