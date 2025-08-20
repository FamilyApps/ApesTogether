"""
Database models for the stock portfolio application.
"""
from flask_login import UserMixin
from datetime import datetime
from flask_sqlalchemy import SQLAlchemy

# Initialize SQLAlchemy without binding to app yet
db = SQLAlchemy()

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

class Transaction(db.Model):
    __tablename__ = 'stock_transaction'  # Use stock_transaction instead of transaction (SQLite reserved word)
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    ticker = db.Column(db.String(10), nullable=False)
    quantity = db.Column(db.Float, nullable=False)
    price = db.Column(db.Float, nullable=False)
    transaction_type = db.Column(db.String(10), nullable=False)  # 'buy' or 'sell'
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    
    # Relationship with User
    user = db.relationship('User', backref=db.backref('transactions', lazy='dynamic'))
    
    def __repr__(self):
        return f"<Transaction {self.transaction_type} {self.quantity} {self.ticker} @ ${self.price}>"

class PortfolioSnapshot(db.Model):
    """Daily portfolio value snapshots for performance tracking"""
    __tablename__ = 'portfolio_snapshot'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    total_value = db.Column(db.Float, nullable=False)
    cash_flow = db.Column(db.Float, default=0.0)  # Net cash flow for the day (deposits - withdrawals)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationship with User
    user = db.relationship('User', backref=db.backref('portfolio_snapshots', lazy='dynamic'))
    
    # Ensure one snapshot per user per day
    __table_args__ = (db.UniqueConstraint('user_id', 'date', name='unique_user_date_snapshot'),)
    
    def __repr__(self):
        return f"<PortfolioSnapshot {self.user_id} {self.date} ${self.total_value}>"

class MarketData(db.Model):
    """Cache for market data (S&P 500, etc.)"""
    __tablename__ = 'market_data'
    
    id = db.Column(db.Integer, primary_key=True)
    ticker = db.Column(db.String(20), nullable=False)  # 'SPY', '^GSPC', 'SPY_SP500_INTRADAY', etc.
    date = db.Column(db.Date, nullable=False)
    timestamp = db.Column(db.DateTime, nullable=True)  # For intraday data
    close_price = db.Column(db.Float, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Ensure one entry per ticker per date (or timestamp for intraday)
    __table_args__ = (db.UniqueConstraint('ticker', 'date', 'timestamp', name='unique_ticker_date_timestamp'),)
    
    def __repr__(self):
        return f"<MarketData {self.ticker} {self.date} ${self.close_price}>"
