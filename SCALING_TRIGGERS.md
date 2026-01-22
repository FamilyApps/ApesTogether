# 📊 Scaling Triggers & Refactoring Guide
## When to Upgrade Infrastructure for Apes Together Mobile

**Document Version**: 1.0  
**Created**: January 21, 2026  

---

## Quick Reference: Scaling Decision Matrix

| Metric | Current Limit | Warning Threshold | Action Trigger | Upgrade Path |
|--------|---------------|-------------------|----------------|--------------|
| **Concurrent Users** | 1,000 | 750 | 900 | See Tier 2 |
| **Database Connections** | 20 | 15 | 18 | Upgrade Postgres plan |
| **API Latency (P95)** | 500ms | 750ms | 1,000ms | Add caching/CDN |
| **Push Notifs/min** | 500 | 400 | 475 | Batch notifications |
| **AlphaVantage calls/min** | 150 | 120 | 140 | Add secondary key |
| **Monthly Cost** | Budget | 80% | 90% | Review architecture |

---

## Tier 1: Startup Phase (0 - 10,000 Users)

### Infrastructure Stack
```
Vercel Pro ($20/mo)
├── Flask API (serverless)
├── Cron jobs (market close, intraday)
└── Static assets

Vercel Postgres ($50/mo)
├── 20 connections
├── 256MB storage
└── Daily backups

Upstash Redis (Free → $10/mo)
├── 10K commands/day free
└── Price caching

Firebase Spark (Free)
├── 1M notifications/month
└── 10GB storage
```

### Monitoring Metrics (Set Up Immediately)

```python
# Add to api/index.py - Simple metrics endpoint

@app.route('/admin/metrics/health')
@login_required
def health_metrics():
    """Real-time health metrics for scaling decisions"""
    from sqlalchemy import text
    
    # Database connection count
    result = db.session.execute(text(
        "SELECT count(*) FROM pg_stat_activity WHERE datname = current_database()"
    ))
    db_connections = result.scalar()
    
    # Active users (last 5 minutes)
    five_min_ago = datetime.utcnow() - timedelta(minutes=5)
    active_users = UserActivity.query.filter(
        UserActivity.timestamp > five_min_ago
    ).distinct(UserActivity.user_id).count()
    
    # Push notifications sent today
    today = date.today()
    notifications_today = PushNotificationLog.query.filter(
        func.date(PushNotificationLog.sent_at) == today
    ).count()
    
    # AlphaVantage API calls today
    api_calls_today = AlphaVantageAPILog.query.filter(
        func.date(AlphaVantageAPILog.timestamp) == today
    ).count()
    
    return jsonify({
        'db_connections': db_connections,
        'db_connection_limit': 20,
        'db_connection_percent': (db_connections / 20) * 100,
        'active_users_5min': active_users,
        'notifications_today': notifications_today,
        'api_calls_today': api_calls_today,
        'api_calls_limit': 150 * 60 * 8,  # 150/min × 60min × 8 market hours
        'warnings': get_scaling_warnings(db_connections, active_users, api_calls_today)
    })

def get_scaling_warnings(db_conn, active_users, api_calls):
    warnings = []
    if db_conn >= 15:
        warnings.append('⚠️ Database connections at 75% - consider upgrading')
    if active_users >= 750:
        warnings.append('⚠️ Concurrent users approaching limit - prepare Tier 2')
    if api_calls >= 50000:
        warnings.append('⚠️ API calls high - add secondary AlphaVantage key')
    return warnings
```

### Upgrade Triggers for Tier 1 → Tier 2

| Trigger | Threshold | Immediate Action |
|---------|-----------|------------------|
| Database connections consistently >15 | 3 days | Upgrade Postgres plan |
| API latency P95 >800ms | 1 day | Add Redis caching |
| Push notification failures >5% | Immediate | Check FCM quota |
| User complaints about speed | 3+ reports | Full architecture review |
| Monthly revenue >$5,000 | Consistent | Begin Tier 2 planning |

---

## Tier 2: Growth Phase (10,000 - 50,000 Users)

### When to Upgrade

**Hard Triggers** (Must upgrade immediately):
- [ ] Database connection errors in logs
- [ ] API timeout errors >1% of requests
- [ ] Push notification delivery delays >30 seconds
- [ ] User-facing errors on trade execution

**Soft Triggers** (Plan upgrade within 2 weeks):
- [ ] P95 latency consistently >500ms
- [ ] Database CPU >70% during market hours
- [ ] Redis cache hit rate <80%
- [ ] Monthly costs approaching $500

### Infrastructure Upgrades

```
Before (Tier 1)                    After (Tier 2)
─────────────────                  ─────────────────
Vercel Pro ($20)          →        Vercel Enterprise ($200)
Vercel Postgres ($50)     →        Supabase Pro ($500)
Upstash Free ($0-10)      →        Upstash Pro ($100)
Firebase Spark ($0)       →        Firebase Blaze ($50-100)
AlphaVantage ($100)       →        AlphaVantage ×2 ($200)
─────────────────                  ─────────────────
Total: ~$180/mo                    Total: ~$1,050-1,100/mo
```

### Required Code Refactoring

#### 1. Database Connection Pooling

```python
# Update database configuration for connection pooling

# Before (direct connection)
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL')

# After (with PgBouncer or connection pooling)
from sqlalchemy.pool import QueuePool

app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL')
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'poolclass': QueuePool,
    'pool_size': 10,
    'max_overflow': 20,
    'pool_timeout': 30,
    'pool_recycle': 1800,  # Recycle connections every 30 min
}
```

#### 2. Read Replica for Heavy Queries

```python
# Separate read/write database connections

WRITE_DB_URL = os.environ.get('DATABASE_URL')  # Primary
READ_DB_URL = os.environ.get('DATABASE_REPLICA_URL')  # Read replica

# Use read replica for:
# - Leaderboard queries
# - Chart data queries
# - Historical performance calculations

def get_leaderboard_data(period):
    """Use read replica for leaderboard queries"""
    with read_engine.connect() as conn:
        result = conn.execute(text("""
            SELECT * FROM leaderboard_cache 
            WHERE period = :period
        """), {'period': period})
        return result.fetchone()
```

#### 3. Notification Batching

```python
# Batch notifications to avoid FCM rate limits

from collections import defaultdict
import asyncio

notification_queue = defaultdict(list)

async def queue_notification(user_id: int, notification: dict):
    """Queue notifications for batched sending"""
    notification_queue[user_id].append(notification)
    
async def flush_notifications():
    """Send all queued notifications in batches (run every 5 seconds)"""
    for user_id, notifications in notification_queue.items():
        if len(notifications) > 1:
            # Combine multiple notifications
            combined = combine_notifications(notifications)
            await send_push(user_id, combined)
        else:
            await send_push(user_id, notifications[0])
    notification_queue.clear()

def combine_notifications(notifications: list) -> dict:
    """Combine multiple trade alerts into one notification"""
    if all(n['type'] == 'trade_alert' for n in notifications):
        return {
            'title': f"📊 {len(notifications)} new trades",
            'body': f"Your subscriptions made {len(notifications)} trades",
            'type': 'trade_summary',
            'data': {'trades': notifications}
        }
    return notifications[-1]  # Return most recent
```

#### 4. API Rate Limiting

```python
# Add per-user rate limiting

from functools import wraps
import redis

redis_client = redis.from_url(os.environ.get('REDIS_URL'))

def rate_limit(requests_per_minute=60):
    """Rate limit decorator using Redis"""
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            if current_user.is_authenticated:
                key = f"rate_limit:{current_user.id}:{f.__name__}"
            else:
                key = f"rate_limit:{request.remote_addr}:{f.__name__}"
            
            current = redis_client.incr(key)
            if current == 1:
                redis_client.expire(key, 60)  # 1 minute window
            
            if current > requests_per_minute:
                return jsonify({'error': 'Rate limit exceeded'}), 429
            
            return f(*args, **kwargs)
        return wrapper
    return decorator

@app.route('/api/v1/portfolio/realtime')
@login_required
@rate_limit(requests_per_minute=30)  # Max 30 requests/min per user
def realtime_portfolio():
    # ... existing code
```

---

## Tier 3: Scale Phase (50,000 - 100,000+ Users)

### When to Upgrade

**Critical Triggers** (Upgrade within 1 week):
- [ ] Database read replica falling behind >5 seconds
- [ ] Redis memory >80% capacity
- [ ] Serverless cold starts causing user complaints
- [ ] Monthly costs exceeding $2,500

**Strategic Triggers** (Plan within 1 month):
- [ ] Preparing for major marketing push
- [ ] Enterprise customer requests
- [ ] International expansion planned
- [ ] Real-time features (WebSocket) needed

### Infrastructure Upgrades

```
Before (Tier 2)                    After (Tier 3)
─────────────────                  ─────────────────
Vercel Enterprise ($200)  →        AWS ECS/EKS ($1,500)
Supabase Pro ($500)       →        Aurora PostgreSQL ($800)
Upstash Pro ($100)        →        ElastiCache ($300)
Firebase Blaze ($100)     →        Firebase + SNS ($300)
AlphaVantage ×2 ($200)    →        AlphaVantage ×5 ($500)
                          +        TimescaleDB ($200)
                          +        Cloudflare Enterprise ($200)
                          +        Datadog ($100)
─────────────────                  ─────────────────
Total: ~$1,100/mo                  Total: ~$3,900/mo
```

### Required Architecture Changes

#### 1. Microservices Split

```
Current Monolith                   Microservices
─────────────────                  ─────────────────
api/index.py (all routes)  →       auth-service/
                                   portfolio-service/
                                   notification-service/
                                   leaderboard-service/
                                   agent-service/
```

**Service Boundaries**:
```yaml
# docker-compose.yml (development) / ECS task definitions (production)

services:
  auth-service:
    image: apestogether/auth:latest
    environment:
      - DATABASE_URL=${DATABASE_URL}
      - JWT_SECRET=${JWT_SECRET}
    ports:
      - "8001:8000"
    
  portfolio-service:
    image: apestogether/portfolio:latest
    environment:
      - DATABASE_URL=${DATABASE_URL}
      - ALPHA_VANTAGE_API_KEY=${ALPHA_VANTAGE_API_KEY}
    ports:
      - "8002:8000"
    
  notification-service:
    image: apestogether/notifications:latest
    environment:
      - FIREBASE_CREDENTIALS=${FIREBASE_CREDENTIALS}
      - REDIS_URL=${REDIS_URL}
    ports:
      - "8003:8000"
```

#### 2. Event-Driven Architecture

```python
# Replace direct function calls with event publishing

# Before (synchronous)
def execute_trade(user_id, ticker, quantity, action, price):
    transaction = create_transaction(...)
    send_trade_notification(...)  # Blocks execution
    update_leaderboard(...)       # Blocks execution
    return transaction

# After (event-driven)
import boto3

sqs = boto3.client('sqs')
TRADE_QUEUE_URL = os.environ.get('TRADE_EVENT_QUEUE_URL')

def execute_trade(user_id, ticker, quantity, action, price):
    transaction = create_transaction(...)
    
    # Publish event - non-blocking
    sqs.send_message(
        QueueUrl=TRADE_QUEUE_URL,
        MessageBody=json.dumps({
            'event': 'trade_executed',
            'data': {
                'user_id': user_id,
                'transaction_id': transaction.id,
                'ticker': ticker,
                'quantity': quantity,
                'action': action,
                'price': price,
                'timestamp': datetime.utcnow().isoformat()
            }
        })
    )
    
    return transaction  # Return immediately

# Separate workers consume events
# notification-worker: Sends push notifications
# leaderboard-worker: Updates rankings
# analytics-worker: Records metrics
```

#### 3. Database Sharding Strategy

```python
# User-based sharding for 100K+ users

def get_shard_for_user(user_id: int) -> str:
    """Determine which database shard holds user data"""
    shard_count = 4
    shard_id = user_id % shard_count
    return os.environ.get(f'DATABASE_SHARD_{shard_id}_URL')

# Shard assignment:
# Shard 0: user_id % 4 == 0 (users 4, 8, 12, ...)
# Shard 1: user_id % 4 == 1 (users 1, 5, 9, ...)
# Shard 2: user_id % 4 == 2 (users 2, 6, 10, ...)
# Shard 3: user_id % 4 == 3 (users 3, 7, 11, ...)

# Global tables (replicated across all shards):
# - stock_info
# - subscription_tier
# - market_data
# - leaderboard_cache (computed aggregates)

# Sharded tables (user-specific data):
# - user
# - stock
# - transaction
# - portfolio_snapshot
# - subscription (both subscriber and subscribed_to must be on same shard - use subscriber's shard)
```

---

## AlphaVantage Scaling Strategy

### Current: 150 requests/minute ($100/month)

**Optimization Strategies Before Adding Keys**:

1. **Batch API calls** (already implemented):
   - REALTIME_BULK_QUOTES: 100 symbols per call
   - Current efficiency: ~95% reduction in API calls

2. **Aggressive caching**:
   - During market hours: 90-second cache
   - After hours: Cache until next market open
   - Weekend: Cache all weekend

3. **Smart refresh**:
   - Only refresh stocks in active portfolios
   - Prioritize stocks with price alerts set

### Scaling Tiers

| Users | Unique Stocks | API Calls/min | Keys Needed | Cost |
|-------|---------------|---------------|-------------|------|
| 1-5K | ~200 | 30-50 | 1 | $100 |
| 5-10K | ~500 | 50-80 | 1 | $100 |
| 10-25K | ~1,000 | 80-120 | 2 | $200 |
| 25-50K | ~2,000 | 120-200 | 3 | $300 |
| 50-100K | ~3,000 | 200-400 | 5 | $500 |

### Multi-Key Implementation

```python
# Rotate through multiple API keys

import itertools

ALPHA_VANTAGE_KEYS = [
    os.environ.get('ALPHA_VANTAGE_API_KEY_1'),
    os.environ.get('ALPHA_VANTAGE_API_KEY_2'),
    os.environ.get('ALPHA_VANTAGE_API_KEY_3'),
]

key_cycle = itertools.cycle([k for k in ALPHA_VANTAGE_KEYS if k])

def get_next_api_key():
    """Round-robin through available API keys"""
    return next(key_cycle)

def get_batch_stock_data_scaled(tickers: list) -> dict:
    """Batch fetch with key rotation"""
    api_key = get_next_api_key()
    
    url = f'https://www.alphavantage.co/query?function=REALTIME_BULK_QUOTES&symbol={",".join(tickers)}&apikey={api_key}'
    # ... rest of implementation
```

---

## Firebase/FCM Scaling

### Free Tier Limits (Spark Plan)
- 1 million notifications/month
- 10GB storage
- 100 simultaneous connections

### When to Upgrade to Blaze

| Trigger | Threshold | Action |
|---------|-----------|--------|
| Monthly notifications | 800K | Upgrade to Blaze |
| Storage usage | 8GB | Upgrade to Blaze |
| Failed notifications | >2% | Check token management |

### Cost Estimation (Blaze Plan)

```
Notifications: $0.01 per 1,000 after first 1M
Storage: $0.026 per GB after 10GB

Example: 50K users, 10 notifications/user/month
= 500K notifications/month
= FREE (under 1M limit)

Example: 100K users, 10 notifications/user/month
= 1M notifications/month
= FREE first 1M, then $0.01/1K
```

---

## Cost Optimization Strategies

### Immediate Savings (Any Scale)

1. **Vercel Edge Caching**:
   - Cache leaderboard HTML for 60 seconds
   - Cache static chart images for 5 minutes
   - Saves ~30% of function invocations

2. **Database Query Optimization**:
   - Add composite indexes (already done)
   - Use materialized views for leaderboards
   - Implement query result caching

3. **Notification Deduplication**:
   - Don't send duplicate notifications
   - Batch multiple trades into single notification
   - Implement quiet hours (no notifications 10PM-8AM)

### Revenue vs. Cost Balance

| Monthly Revenue | Target Max Infra Cost | Ratio |
|-----------------|----------------------|-------|
| $1,000 | $200 | 20% |
| $5,000 | $750 | 15% |
| $25,000 | $2,500 | 10% |
| $100,000 | $8,000 | 8% |

**Rule of Thumb**: Infrastructure costs should be <20% of revenue at any scale.

---

## Monitoring Dashboard Setup

### Key Metrics to Track

```python
# Create admin dashboard for scaling metrics

SCALING_METRICS = {
    'database': {
        'connections_used': lambda: get_db_connections(),
        'connections_limit': 20,  # Update when upgrading
        'query_latency_p95': lambda: get_query_latency(),
        'storage_used_gb': lambda: get_storage_used(),
    },
    'api': {
        'requests_per_minute': lambda: get_rpm(),
        'latency_p95': lambda: get_api_latency(),
        'error_rate': lambda: get_error_rate(),
    },
    'notifications': {
        'sent_today': lambda: get_notifications_count(),
        'delivery_rate': lambda: get_delivery_rate(),
        'avg_delivery_time': lambda: get_avg_delivery_time(),
    },
    'alpha_vantage': {
        'calls_today': lambda: get_av_calls(),
        'calls_limit': 150 * 60 * 8,  # Per day during market hours
        'cache_hit_rate': lambda: get_cache_hit_rate(),
    },
    'costs': {
        'estimated_monthly': lambda: estimate_monthly_cost(),
        'budget': 500,  # Update as needed
    }
}
```

### Alert Configuration

```yaml
# Example: PagerDuty/Opsgenie alert rules

alerts:
  - name: "Database Connection Critical"
    condition: "db_connections > 18"
    severity: critical
    action: "Page on-call engineer"
    
  - name: "API Latency Warning"
    condition: "api_latency_p95 > 800ms"
    severity: warning
    action: "Slack notification"
    
  - name: "Push Delivery Degraded"
    condition: "push_delivery_rate < 95%"
    severity: warning
    action: "Slack notification"
    
  - name: "Cost Budget Warning"
    condition: "estimated_monthly_cost > budget * 0.8"
    severity: info
    action: "Email admin"
```

---

## 🔍 Grok-Verified Recommendations (January 2026)

*The following recommendations were verified by an independent AI architecture review.*

### 1. Rate Limiting (Implement at Launch)

**Without Redis** (0-1K users) - Use Flask-Limiter with in-memory storage:

```python
# api/index.py - Add rate limiting without Redis dependency

from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"],
    storage_uri="memory://",  # In-memory until Redis available
)

# Protect high-traffic endpoints
@app.route('/api/v1/leaderboard')
@limiter.limit("100 per minute")  # Cap at 100 req/s to prevent DDoS
def get_leaderboard():
    # ... existing code

@app.route('/api/v1/portfolio/realtime')
@limiter.limit("30 per minute")  # Prevent excessive polling
@login_required
def realtime_portfolio():
    # ... existing code
```

**With Redis** (1K+ users) - Switch to distributed rate limiting:
```python
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    storage_uri=os.environ.get('REDIS_URL'),  # Distributed storage
)
```

### 2. Alpha Vantage Failover (yfinance Backup)

**Critical**: Add automatic failover to prevent outages if Alpha Vantage rate-limited:

```python
# services/stock_data.py - Add failover strategy

import yfinance as yf
from datetime import datetime, timedelta

class StockDataService:
    """Stock data with automatic Alpha Vantage → yfinance failover"""
    
    def __init__(self):
        self.av_failure_count = 0
        self.av_last_failure = None
        self.FAILOVER_THRESHOLD = 3  # Switch after 3 failures
        self.FAILOVER_COOLDOWN = 300  # 5 minutes before retrying AV
    
    def get_stock_price(self, ticker: str) -> dict:
        """Get stock price with automatic failover"""
        
        # Check if we should use failover
        if self._should_use_failover():
            return self._get_from_yfinance(ticker)
        
        try:
            result = self._get_from_alphavantage(ticker)
            self.av_failure_count = 0  # Reset on success
            return result
        except Exception as e:
            self.av_failure_count += 1
            self.av_last_failure = datetime.utcnow()
            
            # Log warning at 80% of rate limit
            if 'rate limit' in str(e).lower():
                app.logger.warning(f"⚠️ Alpha Vantage rate limit warning: {e}")
            
            # Failover to yfinance
            return self._get_from_yfinance(ticker)
    
    def _should_use_failover(self) -> bool:
        """Check if we should bypass Alpha Vantage"""
        if self.av_failure_count < self.FAILOVER_THRESHOLD:
            return False
        
        # Check cooldown
        if self.av_last_failure:
            elapsed = (datetime.utcnow() - self.av_last_failure).seconds
            if elapsed < self.FAILOVER_COOLDOWN:
                return True  # Still in cooldown, use failover
        
        return False
    
    def _get_from_yfinance(self, ticker: str) -> dict:
        """Fallback to yfinance (free, unlimited)"""
        stock = yf.Ticker(ticker)
        info = stock.info
        return {
            'ticker': ticker,
            'price': info.get('currentPrice') or info.get('regularMarketPrice'),
            'source': 'yfinance',
            'timestamp': datetime.utcnow().isoformat()
        }
    
    def _get_from_alphavantage(self, ticker: str) -> dict:
        """Primary source: Alpha Vantage"""
        # ... existing Alpha Vantage implementation
        pass
```

### 3. Delay Redis to 1,000 Users

**Cost Optimization**: Don't pay for Redis until you need it.

| Users | Caching Strategy | Monthly Cost |
|-------|------------------|--------------|
| 0-500 | In-memory (Flask cache) | $0 |
| 500-1K | In-memory + aggressive DB caching | $0 |
| 1K+ | Upstash Redis | $10/mo |

```python
# Conditional Redis usage

import os

if os.environ.get('REDIS_URL'):
    from redis import Redis
    cache = Redis.from_url(os.environ.get('REDIS_URL'))
else:
    # Simple in-memory cache for <1K users
    from cachetools import TTLCache
    cache = TTLCache(maxsize=1000, ttl=90)  # 90 second TTL
```

### 4. Agent System Caps and Monitoring

**Environment Variable Cap**:
```bash
# .env
MAX_AGENTS_PER_DAY=1000  # Prevent runaway agent creation
```

**Implementation**:
```python
# api/index.py - Add agent creation cap

@app.route('/admin/agents/create', methods=['POST'])
@login_required
@admin_required
def create_agent():
    """Create agent with daily cap"""
    max_agents = int(os.environ.get('MAX_AGENTS_PER_DAY', 1000))
    
    # Count agents created today
    today = date.today()
    agents_today = AgentConfig.query.filter(
        func.date(AgentConfig.created_at) == today
    ).count()
    
    if agents_today >= max_agents:
        return jsonify({'error': f'Daily agent limit ({max_agents}) reached'}), 429
    
    # ... create agent
```

**Agent-Specific Metrics**:
```python
# Add to health_metrics endpoint

agent_metrics = {
    'agents_created_today': AgentConfig.query.filter(
        func.date(AgentConfig.created_at) == date.today()
    ).count(),
    'agents_active': AgentConfig.query.filter_by(status='active').count(),
    'agent_trades_today': Transaction.query.join(User).filter(
        User.is_agent == True,
        func.date(Transaction.timestamp) == date.today()
    ).count(),
    'agent_research_avg_latency_ms': get_agent_research_latency(),  # Target <5000ms
}
```

### 5. Load Testing with Locust

**Pre-Launch Requirement**: Simulate 1K concurrent users before scaling.

```python
# tests/load_test.py - Locust load test configuration

from locust import HttpUser, task, between

class ApesTogetherUser(HttpUser):
    """Simulate mobile app user behavior"""
    
    wait_time = between(1, 5)  # 1-5 seconds between requests
    
    def on_start(self):
        """Login on start"""
        self.client.post("/api/v1/auth/login", json={
            "email": "loadtest@example.com",
            "password": "testpass123"
        })
    
    @task(10)
    def view_leaderboard(self):
        """Most common action: view leaderboard"""
        self.client.get("/api/v1/leaderboard?period=7d")
    
    @task(5)
    def view_portfolio(self):
        """View own portfolio"""
        self.client.get("/api/v1/portfolio/realtime")
    
    @task(3)
    def view_public_portfolio(self):
        """View another user's portfolio"""
        self.client.get("/api/v1/portfolio/public/stockguru")
    
    @task(1)
    def execute_trade(self):
        """Execute a trade (less frequent)"""
        self.client.post("/api/v1/trade", json={
            "ticker": "AAPL",
            "quantity": 10,
            "action": "buy"
        })

# Run with: locust -f tests/load_test.py --host=https://staging.apestogether.ai
# Target: 1000 concurrent users with <500ms P95 latency
```

**Load Test Thresholds**:
| Metric | Pass | Warning | Fail |
|--------|------|---------|------|
| P50 Latency | <100ms | <200ms | >300ms |
| P95 Latency | <300ms | <500ms | >800ms |
| Error Rate | <0.1% | <1% | >2% |
| Throughput | >500 RPS | >300 RPS | <200 RPS |

### 6. Monitoring Setup Timeline

| Users | Monitoring Stack | Monthly Cost |
|-------|------------------|--------------|
| 0-500 | Vercel Analytics (free) | $0 |
| 500-1K | + Sentry Error Tracking (free tier) | $0 |
| 1K-5K | + Datadog Starter | $15/mo |
| 5K+ | + PagerDuty/Opsgenie alerts | $25/mo |

---

## Summary: Scaling Roadmap

```
PHASE 1: Launch (0-10K users)
├── Vercel Pro + Postgres ($180/mo)
├── Monitor all metrics daily
├── Prepare Tier 2 infrastructure docs
└── Trigger: Revenue >$5K/mo or connections >15

PHASE 2: Growth (10K-50K users)
├── Upgrade to Supabase Pro ($1,100/mo)
├── Add read replica
├── Implement connection pooling
├── Add second AlphaVantage key
└── Trigger: Latency issues or revenue >$25K/mo

PHASE 3: Scale (50K-100K+ users)
├── Migrate to AWS/GCP ($3,900/mo)
├── Microservices architecture
├── Event-driven notifications
├── Database sharding
└── Trigger: Strategic growth decision

ONGOING: Optimization
├── Weekly metric reviews
├── Monthly cost audits
├── Quarterly architecture reviews
└── Annual infrastructure planning
```

---

*Document maintained by: Development Team*
*Last updated: January 21, 2026*
