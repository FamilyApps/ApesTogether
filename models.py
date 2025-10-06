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
    
    # Tiered subscriptions
    stripe_price_id = db.Column(db.String(255), nullable=True)
    subscription_price = db.Column(db.Float, nullable=True)
    stripe_customer_id = db.Column(db.String(255), nullable=True)
    
    # Cash tracking (NEW)
    max_cash_deployed = db.Column(db.Float, default=0.0, nullable=False)  # Cumulative capital deployed
    cash_proceeds = db.Column(db.Float, default=0.0, nullable=False)  # Uninvested cash from sales

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
    
    def __repr__(self):
        return f"<Transaction {self.transaction_type} {self.quantity} {self.ticker} @ ${self.price}>"

class PortfolioSnapshot(db.Model):
    """Daily portfolio value snapshot"""
    __tablename__ = 'portfolio_snapshot'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    total_value = db.Column(db.Float, nullable=False)  # stock_value + cash_proceeds
    
    # cash tracking components (NEW - for Modified Dietz calculations)
    stock_value = db.Column(db.Float, default=0.0)  # Value of stock holding only
    cash_proceeds = db.Column(db.Float, default=0.0)  # Uninvested cash from sales
    max_cash_deployed = db.Column(db.Float, default=0.0)  # Cumulative capital deployed
    
    # Legacy field (kept for backward compatibility)
    cash_flow = db.Column(db.Float, default=0.0)  # Net cash flow for the day (deposits - withdrawals)
    
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

class PortfolioSnapshotIntraday(db.Model):
    """Intraday portfolio value snapshots for detailed performance tracking"""
    __tablename__ = 'portfolio_snapshot_intraday'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    timestamp = db.Column(db.DateTime, nullable=False)
    total_value = db.Column(db.Float, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationship with User
    user = db.relationship('User', backref=db.backref('intraday_snapshots', lazy='dynamic'))
    
    # Ensure one snapshot per user per timestamp
    __table_args__ = (db.UniqueConstraint('user_id', 'timestamp', name='unique_user_timestamp_intraday'),)
    
    def __repr__(self):
        return f"<PortfolioSnapshotIntraday {self.user_id} {self.timestamp} ${self.total_value}>"

class SP500ChartCache(db.Model):
    """Pre-generated S&P 500 chart data cache"""
    __tablename__ = 'sp500_chart_cache'
    
    id = db.Column(db.Integer, primary_key=True)
    period = db.Column(db.String(10), nullable=False)  # '1D', '5D', '1M', etc.
    chart_data = db.Column(db.Text, nullable=False)  # JSON string of chart data
    generated_at = db.Column(db.DateTime, nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)
    
    # Ensure one cache entry per period
    __table_args__ = (db.UniqueConstraint('period', name='unique_period_chart'),)
    
    def __repr__(self):
        return f"<SP500ChartCache {self.period} generated at {self.generated_at}>"

class LeaderboardCache(db.Model):
    """Pre-generated leaderboard data cache updated at market close"""
    __tablename__ = 'leaderboard_cache'
    
    id = db.Column(db.Integer, primary_key=True)
    period = db.Column(db.String(20), nullable=False)  # '1D_all', '1D_small_cap', '1D_large_cap', etc.
    leaderboard_data = db.Column(db.Text, nullable=False)  # JSON string of leaderboard data
    rendered_html = db.Column(db.Text, nullable=True)  # Pre-rendered HTML for maximum performance
    generated_at = db.Column(db.DateTime, nullable=False)
    
    # Ensure one cache entry per period
    __table_args__ = (db.UniqueConstraint('period', name='unique_period_leaderboard'),)
    
    def __repr__(self):
        return f"<LeaderboardCache {self.period} generated at {self.generated_at}>"

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

class AlphaVantageAPILog(db.Model):
    """Track Alpha Vantage API calls for monitoring and rate limiting"""
    __tablename__ = 'alpha_vantage_api_log'
    
    id = db.Column(db.Integer, primary_key=True)
    endpoint = db.Column(db.String(100), nullable=False)  # API endpoint called
    symbol = db.Column(db.String(10), nullable=True)  # Stock symbol if applicable
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    response_status = db.Column(db.String(20), nullable=False)  # 'success', 'error', 'rate_limited'
    response_time_ms = db.Column(db.Integer, nullable=True)  # Response time in milliseconds
    
    def __repr__(self):
        return f"<AlphaVantageAPILog {self.endpoint} {self.symbol} at {self.timestamp}>"

class UserActivity(db.Model):
    """Track actual user activity for accurate metrics"""
    __tablename__ = 'user_activity'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    activity_type = db.Column(db.String(50), nullable=False)  # 'login', 'add_stock', 'view_dashboard', etc.
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    ip_address = db.Column(db.String(45), nullable=True)  # For session tracking
    user_agent = db.Column(db.String(255), nullable=True)  # For device tracking
    
    def __repr__(self):
        return f"<UserActivity user_id={self.user_id} {self.activity_type} at {self.timestamp}>"

class PlatformMetrics(db.Model):
    """Daily platform metrics for admin dashboard"""
    __tablename__ = 'platform_metrics'
    
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False, unique=True)
    unique_stocks_count = db.Column(db.Integer, nullable=False, default=0)
    active_users_1d = db.Column(db.Integer, nullable=False, default=0)
    active_users_7d = db.Column(db.Integer, nullable=False, default=0)
    active_users_30d = db.Column(db.Integer, nullable=False, default=0)
    active_users_90d = db.Column(db.Integer, nullable=False, default=0)
    api_calls_total = db.Column(db.Integer, nullable=False, default=0)
    api_calls_avg_per_minute = db.Column(db.Float, nullable=False, default=0.0)
    api_calls_peak_per_minute = db.Column(db.Integer, nullable=False, default=0)
    api_calls_peak_time = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    
    def __repr__(self):
        return f"<PlatformMetrics {self.date} - {self.unique_stocks_count} stocks, {self.active_users_1d} active users>"

class SubscriptionTier(db.Model):
    """Subscription tier definitions with pricing and trade limits"""
    __tablename__ = 'subscription_tier'
    
    id = db.Column(db.Integer, primary_key=True)
    tier_name = db.Column(db.String(50), nullable=False, unique=True)  # 'Light', 'Standard', etc.
    price = db.Column(db.Float, nullable=False)
    max_trades_per_day = db.Column(db.Integer, nullable=False)
    stripe_price_id = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f"<SubscriptionTier {self.tier_name} ${self.price} {self.max_trades_per_day} trades/day>"

class TradeLimit(db.Model):
    """Daily trade count tracking per user"""
    __tablename__ = 'trade_limit'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    trade_count = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationship with User
    user = db.relationship('User', backref=db.backref('trade_limits', lazy='dynamic'))
    
    # Ensure one record per user per day
    __table_args__ = (db.UniqueConstraint('user_id', 'date', name='unique_user_date_trade_limit'),)
    
    def __repr__(self):
        return f"<TradeLimit {self.user_id} {self.date} {self.trade_count} trades>"

class SMSNotification(db.Model):
    """SMS notification settings and phone verification"""
    __tablename__ = 'sms_notification'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    phone_number = db.Column(db.String(20), nullable=True)
    is_verified = db.Column(db.Boolean, default=False)
    sms_enabled = db.Column(db.Boolean, default=True)
    verification_code = db.Column(db.String(6), nullable=True)
    verification_expires = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationship with User
    user = db.relationship('User', backref=db.backref('sms_notification', uselist=False))
    
    def __repr__(self):
        return f"<SMSNotification {self.user_id} {self.phone_number} verified={self.is_verified}>"

class StockInfo(db.Model):
    """Stock information including market cap, industry classification, and metadata"""
    __tablename__ = 'stock_info'
    
    id = db.Column(db.Integer, primary_key=True)
    ticker = db.Column(db.String(10), unique=True, nullable=False)
    company_name = db.Column(db.String(200), nullable=True)
    market_cap = db.Column(db.BigInteger, nullable=True)  # In dollars
    cap_classification = db.Column(db.String(20), nullable=True)  # 'small', 'mid', 'large', 'mega'
    sector = db.Column(db.String(100), nullable=True)  # Technology, Healthcare, etc.
    industry = db.Column(db.String(100), nullable=True)  # Software, Biotechnology, etc.
    naics_code = db.Column(db.String(10), nullable=True)  # 6-digit NAICS industry code
    exchange = db.Column(db.String(10), nullable=True)  # NYSE, NASDAQ, etc.
    country = db.Column(db.String(5), nullable=True, default='US')  # ISO country code
    is_active = db.Column(db.Boolean, default=True)  # For delisted stocks
    last_updated = db.Column(db.DateTime, default=datetime.utcnow)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def get_market_cap_category(self):
        """Return market cap category based on current market cap"""
        if not self.market_cap:
            return 'unknown'
        
        if self.market_cap >= 200_000_000_000:  # $200B+
            return 'mega'
        elif self.market_cap >= 10_000_000_000:  # $10B+
            return 'large'
        elif self.market_cap >= 2_000_000_000:   # $2B+
            return 'mid'
        else:
            return 'small'
    
    def __repr__(self):
        return f"<StockInfo {self.ticker} {self.company_name} {self.cap_classification} cap>"

class LeaderboardEntry(db.Model):
    """Leaderboard performance metrics and cap percentages"""
    __tablename__ = 'leaderboard_entry'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    period = db.Column(db.String(10), nullable=False)  # '1D', '5D', '3M', 'YTD', '1Y', '5Y', 'MAX'
    performance_percent = db.Column(db.Float, nullable=False)
    small_cap_percent = db.Column(db.Float, default=0.0)
    large_cap_percent = db.Column(db.Float, default=0.0)
    avg_trades_per_week = db.Column(db.Float, default=0.0)
    portfolio_value = db.Column(db.Float, default=0.0)
    calculated_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationship with User
    user = db.relationship('User', backref=db.backref('leaderboard_entries', lazy='dynamic'))
    
    # Ensure one entry per user per period
    __table_args__ = (db.UniqueConstraint('user_id', 'period', name='unique_user_period_leaderboard'),)
    
    def __repr__(self):
        return f"<LeaderboardEntry {self.user_id} {self.period} {self.performance_percent}%>"
