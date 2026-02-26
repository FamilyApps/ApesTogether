"""
Database models for the stock portfolio application.
"""
from flask_login import UserMixin
from datetime import datetime
from flask_sqlalchemy import SQLAlchemy

# Initialize SQLAlchemy without binding to app yet
db = SQLAlchemy()

class User(UserMixin, db.Model):
    __tablename__ = 'user'  # Explicitly set - will be quoted in PostgreSQL as "user"
    
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
    
    # Cash tracking
    max_cash_deployed = db.Column(db.Float, default=0.0, nullable=False)  # Cumulative capital deployed
    cash_proceeds = db.Column(db.Float, default=0.0, nullable=False)  # Uninvested cash from sales
    
    # Portfolio sharing & GDPR
    portfolio_slug = db.Column(db.String(20), unique=True, nullable=True)  # Unique URL slug for public sharing
    deleted_at = db.Column(db.DateTime, nullable=True)  # GDPR soft-delete timestamp
    
    # User type and creation tracking (NEW - for agent system)
    role = db.Column(db.String(20), default='user')  # 'user', 'agent', 'admin'
    created_by = db.Column(db.String(20), default='human')  # 'human', 'system'
    created_at = db.Column(db.DateTime, default=datetime.utcnow)  # Account creation timestamp
    
    # SMS/Email trading and notifications (NEW - for Week 2)
    phone_number = db.Column(db.String(20), nullable=True)  # E.164 format: +12125551234
    default_notification_method = db.Column(db.String(10), default='email')  # 'email' or 'sms'
    
    # Future-proofing for leaderboard filtering and admin controls
    leaderboard_eligible = db.Column(db.Boolean, default=True)  # Admin can exclude from leaderboards
    extra_data = db.Column('metadata', db.JSON, default=dict)  # Flexible storage for future fields

class Stock(db.Model):
    __tablename__ = 'stock'
    
    id = db.Column(db.Integer, primary_key=True)
    ticker = db.Column(db.String(10))
    quantity = db.Column(db.Float)
    purchase_price = db.Column(db.Float)
    purchase_date = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))

class Subscription(db.Model):
    __tablename__ = 'subscription'
    
    id = db.Column(db.Integer, primary_key=True)
    subscriber_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    subscribed_to_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    stripe_subscription_id = db.Column(db.String(255), unique=True, nullable=False)
    status = db.Column(db.String(50), nullable=False, default='active')  # e.g., 'active', 'canceled'
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    start_date = db.Column(db.DateTime, default=datetime.utcnow)
    end_date = db.Column(db.DateTime, nullable=True)

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
    total_value = db.Column(db.Float, nullable=False)  # stock_value + cash_proceeds
    
    # Cash tracking components (ADDED - matches PortfolioSnapshot)
    stock_value = db.Column(db.Float, default=0.0)  # Value of stock holdings only
    cash_proceeds = db.Column(db.Float, default=0.0)  # Uninvested cash from sales
    max_cash_deployed = db.Column(db.Float, default=0.0)  # Cumulative capital deployed
    
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
    symbol = db.Column(db.String(50), nullable=True)  # Stock symbol or batch identifier (e.g., BATCH_23_TICKERS)
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

class UserPortfolioStats(db.Model):
    """
    Cache table for portfolio statistics
    Updated daily during market close cron
    """
    __tablename__ = 'user_portfolio_stats'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, unique=True)
    
    # Trading activity
    avg_trades_per_week = db.Column(db.Float, default=0.0)
    total_trades = db.Column(db.Integer, default=0)
    
    # Portfolio composition
    unique_stocks_count = db.Column(db.Integer, default=0)
    large_cap_percent = db.Column(db.Float, default=0.0)
    small_cap_percent = db.Column(db.Float, default=0.0)
    
    # Industry mix (JSON: {'Technology': 45.2, 'Healthcare': 30.5, ...})
    industry_mix = db.Column(db.JSON)
    
    # Social metrics
    subscriber_count = db.Column(db.Integer, default=0)
    
    # Metadata
    last_updated = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationship
    user = db.relationship('User', backref=db.backref('portfolio_stats', uselist=False))
    
    def __repr__(self):
        return f"<UserPortfolioStats user_id={self.user_id} stocks={self.unique_stocks_count}>"

class OldNotificationLog(db.Model):
    """DEPRECATED - Old notification log (keeping for migration compatibility)"""
    __tablename__ = 'notification_log_old'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    portfolio_owner_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    notification_type = db.Column(db.String(20), nullable=True)  # 'sms', 'email'
    transaction_id = db.Column(db.Integer, db.ForeignKey('stock_transaction.id'), nullable=True)
    sent_at = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(20), nullable=True)  # 'sent', 'failed', 'pending'
    twilio_sid = db.Column(db.String(100), nullable=True)
    error_message = db.Column(db.Text, nullable=True)
    
    # Relationships
    user = db.relationship('User', foreign_keys=[user_id])
    portfolio_owner = db.relationship('User', foreign_keys=[portfolio_owner_id])
    transaction = db.relationship('Transaction')
    
    def __repr__(self):
        return f"<NotificationLog {self.notification_type} to user_id={self.user_id} status={self.status}>"

class XeroSyncLog(db.Model):
    """Log of Xero accounting sync operations"""
    __tablename__ = 'xero_sync_log'
    
    id = db.Column(db.Integer, primary_key=True)
    sync_type = db.Column(db.String(50), nullable=True)  # 'subscription_revenue', 'user_payout', 'stripe_fee'
    entity_id = db.Column(db.Integer, nullable=True)  # ID of the related entity (subscription_id, user_id, etc.)
    entity_type = db.Column(db.String(50), nullable=True)  # 'subscription', 'payout', 'fee'
    xero_invoice_id = db.Column(db.String(100), nullable=True)
    xero_contact_id = db.Column(db.String(100), nullable=True)
    amount = db.Column(db.Float, nullable=True)
    synced_at = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(20), nullable=True)  # 'success', 'failed', 'pending'
    error_message = db.Column(db.Text, nullable=True)
    
    def __repr__(self):
        return f"<XeroSyncLog {self.sync_type} ${self.amount} status={self.status}>"

class AgentConfig(db.Model):
    """Configuration and state for automated trading agents"""
    __tablename__ = 'agent_config'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, unique=True)
    personality = db.Column(db.JSON, nullable=False)  # Risk tolerance, trading style, preferences
    strategy_params = db.Column(db.JSON, nullable=False)  # Strategy-specific parameters
    status = db.Column(db.String(20), default='active')  # 'active', 'paused', 'disabled'
    last_trade_at = db.Column(db.DateTime, nullable=True)
    total_trades = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationship
    user = db.relationship('User', backref=db.backref('agent_config', uselist=False))
    
    def __repr__(self):
        return f"<AgentConfig user_id={self.user_id} status={self.status} trades={self.total_trades}>"

class AdminSubscription(db.Model):
    """Bonus subscribers - admin pays 60% payout from platform pocket, no actual app store transactions"""
    __tablename__ = 'admin_subscription'
    
    id = db.Column(db.Integer, primary_key=True)
    portfolio_user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)  # Who gets the bonus subs
    bonus_subscriber_count = db.Column(db.Integer, default=0, nullable=False)  # Bonus count (e.g., 8)
    reason = db.Column(db.String(500), nullable=True)  # Admin notes (e.g., "Marketing boost", "Early adopter reward")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Legacy fields (kept for backward compatibility with existing data)
    ghost_subscriber_count = db.Column(db.Integer, default=0, nullable=True)  # Deprecated: use bonus_subscriber_count
    tier = db.Column(db.String(20), nullable=True)  # Deprecated: no longer used (flat pricing)
    monthly_payout = db.Column(db.Float, nullable=True)  # Deprecated: calculated dynamically
    
    # Relationship
    portfolio_user = db.relationship('User', foreign_keys=[portfolio_user_id], backref='bonus_subscriptions')
    
    # Flat pricing (mobile app model - January 2026)
    SUBSCRIPTION_PRICE = 9.00
    INFLUENCER_PAYOUT_PERCENT = 0.60  # 60% to influencer
    PLATFORM_PERCENT = 0.10  # 10% to platform
    STORE_FEE_PERCENT = 0.30  # 30% to Apple/Google
    
    @property
    def monthly_revenue(self):
        """Notional monthly revenue from bonus subscribers (for display purposes)"""
        return self.bonus_subscriber_count * self.SUBSCRIPTION_PRICE
    
    @property
    def payout_amount(self):
        """Calculate 60% payout for bonus subscribers (paid from platform pocket)"""
        return self.bonus_subscriber_count * self.SUBSCRIPTION_PRICE * self.INFLUENCER_PAYOUT_PERCENT
    
    def calculate_payout(self):
        """Calculate 60% payout - matches new mobile pricing model"""
        return self.payout_amount
    
    def __repr__(self):
        return f"<AdminSubscription user={self.portfolio_user_id} bonus={self.bonus_subscriber_count} payout=${self.payout_amount:.2f}>"

class NotificationPreferences(db.Model):
    """User preferences for notifications per subscription"""
    __tablename__ = 'notification_preferences'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    subscription_id = db.Column(db.Integer, db.ForeignKey('subscription.id'), nullable=False)
    notification_type = db.Column(db.String(10), default='email')  # 'email' or 'sms'
    enabled = db.Column(db.Boolean, default=True)  # Can disable notifications per subscription
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    user = db.relationship('User', backref='notification_preferences')
    subscription = db.relationship('Subscription', backref='notification_preferences')
    
    def __repr__(self):
        return f"<NotificationPreferences user={self.user_id} sub={self.subscription_id} type={self.notification_type} enabled={self.enabled}>"

class NotificationLog(db.Model):
    """Log of all notifications sent"""
    __tablename__ = 'notification_log'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    portfolio_owner_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    subscription_id = db.Column(db.Integer, db.ForeignKey('subscription.id'), nullable=True)
    notification_type = db.Column(db.String(10), nullable=False)  # 'sms' or 'email'
    status = db.Column(db.String(20), nullable=False)  # 'sent', 'failed'
    twilio_sid = db.Column(db.String(100), nullable=True)  # Twilio message SID (for SMS)
    sendgrid_message_id = db.Column(db.String(100), nullable=True)  # SendGrid message ID (for email)
    error_message = db.Column(db.String(500), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    user = db.relationship('User', foreign_keys=[user_id], backref='notifications_received')
    portfolio_owner = db.relationship('User', foreign_keys=[portfolio_owner_id], backref='notifications_sent')
    
    def __repr__(self):
        return f"<NotificationLog user={self.user_id} type={self.notification_type} status={self.status}>"


# =============================================================================
# MOBILE APP MODELS (Phase 1 - January 2026)
# =============================================================================

class DeviceToken(db.Model):
    """Push notification tokens for iOS/Android devices"""
    __tablename__ = 'device_token'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    token = db.Column(db.String(500), nullable=False)  # FCM/APNs token
    platform = db.Column(db.String(10), nullable=False)  # 'ios' or 'android'
    device_id = db.Column(db.String(100), nullable=True)  # Unique device identifier
    app_version = db.Column(db.String(20), nullable=True)  # e.g., "1.0.0"
    os_version = db.Column(db.String(20), nullable=True)  # e.g., "iOS 17.2" or "Android 14"
    is_active = db.Column(db.Boolean, default=True)  # False if token is invalid/expired
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_used_at = db.Column(db.DateTime, nullable=True)  # Last successful push
    
    # Relationship
    user = db.relationship('User', backref='device_tokens')
    
    # Unique constraint: one token per device per user
    __table_args__ = (
        db.UniqueConstraint('user_id', 'device_id', name='unique_user_device'),
    )
    
    def __repr__(self):
        return f"<DeviceToken user={self.user_id} platform={self.platform} active={self.is_active}>"


class InAppPurchase(db.Model):
    """Apple/Google In-App Purchase records"""
    __tablename__ = 'in_app_purchase'
    
    id = db.Column(db.Integer, primary_key=True)
    subscriber_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    subscribed_to_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    
    # Platform details
    platform = db.Column(db.String(10), nullable=False)  # 'apple' or 'google'
    product_id = db.Column(db.String(100), nullable=False)  # e.g., 'com.apestogether.subscription.monthly'
    
    # Transaction identifiers
    transaction_id = db.Column(db.String(200), unique=True, nullable=False)  # Apple/Google transaction ID
    original_transaction_id = db.Column(db.String(200), nullable=True)  # For renewals
    
    # Receipt data
    receipt_data = db.Column(db.Text, nullable=True)  # Encrypted receipt (for re-validation)
    
    # Subscription details
    status = db.Column(db.String(20), nullable=False, default='active')  # 'active', 'expired', 'canceled', 'refunded'
    purchase_date = db.Column(db.DateTime, nullable=False)
    expires_date = db.Column(db.DateTime, nullable=True)  # For subscriptions
    
    # Pricing (for accounting)
    price = db.Column(db.Float, default=9.00)  # Flat $9
    currency = db.Column(db.String(3), default='USD')
    
    # Payout tracking
    influencer_payout = db.Column(db.Float, default=5.40)  # 60% of $9
    platform_revenue = db.Column(db.Float, default=0.90)  # 10% of $9
    store_fee = db.Column(db.Float, default=2.70)  # 30% Apple/Google
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    subscriber = db.relationship('User', foreign_keys=[subscriber_id], backref='iap_subscriptions_made')
    subscribed_to = db.relationship('User', foreign_keys=[subscribed_to_id], backref='iap_subscribers')
    
    def __repr__(self):
        return f"<InAppPurchase {self.platform} sub={self.subscriber_id}->owner={self.subscribed_to_id} status={self.status}>"


class PushNotificationLog(db.Model):
    """Log of push notifications sent via Firebase/APNs"""
    __tablename__ = 'push_notification_log'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)  # Recipient
    portfolio_owner_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)  # Trader
    device_token_id = db.Column(db.Integer, db.ForeignKey('device_token.id'), nullable=True)
    
    # Notification content
    title = db.Column(db.String(200), nullable=False)
    body = db.Column(db.String(500), nullable=False)
    data_payload = db.Column(db.JSON, nullable=True)  # Custom data (ticker, action, price, etc.)
    
    # Delivery status
    status = db.Column(db.String(20), nullable=False)  # 'sent', 'delivered', 'failed', 'invalid_token'
    fcm_message_id = db.Column(db.String(200), nullable=True)  # Firebase message ID
    error_message = db.Column(db.String(500), nullable=True)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    delivered_at = db.Column(db.DateTime, nullable=True)
    
    # Relationships
    user = db.relationship('User', foreign_keys=[user_id], backref='push_notifications_received')
    portfolio_owner = db.relationship('User', foreign_keys=[portfolio_owner_id], backref='push_notifications_triggered')
    device_token = db.relationship('DeviceToken', backref='notifications')
    
    def __repr__(self):
        return f"<PushNotificationLog user={self.user_id} status={self.status}>"


class XeroPayoutRecord(db.Model):
    """Track influencer payouts synced to Xero"""
    __tablename__ = 'xero_payout_record'
    
    id = db.Column(db.Integer, primary_key=True)
    portfolio_user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    
    # Payout period
    period_start = db.Column(db.Date, nullable=False)
    period_end = db.Column(db.Date, nullable=False)
    
    # Subscriber counts
    real_subscriber_count = db.Column(db.Integer, default=0)  # From InAppPurchase
    bonus_subscriber_count = db.Column(db.Integer, default=0)  # From AdminSubscription
    total_subscriber_count = db.Column(db.Integer, default=0)  # real + bonus
    
    # Revenue breakdown (all at $9/subscriber)
    gross_revenue = db.Column(db.Float, default=0.0)  # total_subs × $9
    store_fees = db.Column(db.Float, default=0.0)  # 30% to Apple/Google
    platform_revenue = db.Column(db.Float, default=0.0)  # 10% ($0.90/sub)
    influencer_payout = db.Column(db.Float, default=0.0)  # 60% ($5.40/sub)
    
    # Bonus payout (paid from platform pocket)
    bonus_payout = db.Column(db.Float, default=0.0)  # bonus_subs × $5.40
    
    # Xero sync status
    xero_invoice_id = db.Column(db.String(100), nullable=True)
    xero_contact_id = db.Column(db.String(100), nullable=True)
    xero_synced_at = db.Column(db.DateTime, nullable=True)
    xero_sync_status = db.Column(db.String(20), default='pending')  # 'pending', 'synced', 'failed'
    xero_error = db.Column(db.String(500), nullable=True)
    
    # Payment status
    payment_status = db.Column(db.String(20), default='pending')  # 'pending', 'paid', 'held'
    paid_at = db.Column(db.DateTime, nullable=True)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationship
    portfolio_user = db.relationship('User', backref='payout_records')
    
    def calculate_totals(self):
        """Recalculate all amounts based on subscriber counts"""
        self.total_subscriber_count = self.real_subscriber_count + self.bonus_subscriber_count
        self.gross_revenue = self.real_subscriber_count * 9.00
        self.store_fees = self.real_subscriber_count * 2.70
        self.platform_revenue = self.real_subscriber_count * 0.90
        self.influencer_payout = self.real_subscriber_count * 5.40
        self.bonus_payout = self.bonus_subscriber_count * 5.40
    
    @property
    def total_payout(self):
        """Total owed to influencer (real + bonus)"""
        return self.influencer_payout + self.bonus_payout
    
    def __repr__(self):
        return f"<XeroPayoutRecord user={self.portfolio_user_id} period={self.period_start}-{self.period_end} payout=${self.total_payout}>"


class MobileSubscription(db.Model):
    """Mobile app subscription linking - replaces Stripe-based Subscription for mobile"""
    __tablename__ = 'mobile_subscription'
    
    id = db.Column(db.Integer, primary_key=True)
    subscriber_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    subscribed_to_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    in_app_purchase_id = db.Column(db.Integer, db.ForeignKey('in_app_purchase.id'), nullable=False)
    
    status = db.Column(db.String(20), nullable=False, default='active')  # 'active', 'expired', 'canceled'
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime, nullable=True)
    
    # Notification preferences
    push_notifications_enabled = db.Column(db.Boolean, default=True)
    
    # Relationships
    subscriber = db.relationship('User', foreign_keys=[subscriber_id], backref='mobile_subscriptions_made')
    subscribed_to = db.relationship('User', foreign_keys=[subscribed_to_id], backref='mobile_subscribers')
    in_app_purchase = db.relationship('InAppPurchase', backref='subscription')
    
    def __repr__(self):
        return f"<MobileSubscription sub={self.subscriber_id}->owner={self.subscribed_to_id} status={self.status}>"
