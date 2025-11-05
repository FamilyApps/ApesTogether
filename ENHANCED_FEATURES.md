# Enhanced Features - Additional Requirements

## 🎯 Features to Add to Implementation Plan

### 1. Enhanced Admin Dashboard (Week 4)

#### Admin Subscriber Management (SIMPLIFIED)
**Location**: `/admin/subscribers`

**What It Actually Does**:
- **Increments subscriber counter only** (no real subscription created)
- **No Stripe charges** (you pay directly via check)
- **No SMS notifications** (ghost subscribers don't get notified)
- **Just for accounting**: Xero calculates 70% payout at month end

**Features**:
```python
# Add "ghost" subscriber (counter only)
POST /admin/subscribers/add
{
  "portfolio_user_id": 456,
  "count": 8,  # Add 8 ghost subscribers
  "tier": "standard",  # $15/month
  "reason": "Marketing boost"
}

# Remove ghost subscribers
DELETE /admin/subscribers/{admin_subscription_id}

# View all admin-sponsored subscribers
GET /admin/subscribers/sponsored
Response: {
  "subscriptions": [
    {
      "user": "john_trader",
      "ghost_count": 8,
      "tier": "standard",
      "monthly_revenue": 120.00,  # 8 × $15
      "monthly_payout": 84.00,    # 70% of $120
      "reason": "Marketing boost"
    }
  ],
  "total_monthly_payout": 450.00  # What you'll pay via check
}
```

**UI Components**:
- Search user by username/email
- Input: Number of ghost subscribers (1-50)
- Select tier (Light, Standard, Active, Pro, Elite)
- Add reason/notes
- See monthly payout calculation
- List of all ghost subscriptions
- Month-end payout report for Xero

**Database Storage**:
```python
class AdminSubscription(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    portfolio_user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    ghost_subscriber_count = db.Column(db.Integer, default=0)
    tier = db.Column(db.String(20))  # 'light', 'standard', 'active', 'pro', 'elite'
    monthly_payout = db.Column(db.Float)  # 70% of (count × tier_price)
    reason = db.Column(db.String(500))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
```

**How User Sees It**:
- Dashboard shows: "You have 10 subscribers"
- 2 are real users (actual Subscription records)
- 8 are ghost (AdminSubscription.ghost_subscriber_count)
- At month end, you cut them a check for 70% of all 10

**Cost Tracking**:
- No Stripe fees (no real subscriptions)
- No SMS costs (ghosts don't get notified)
- Just your 70% payout: `ghost_count × tier_price × 0.70`
- Example: 8 ghosts × $15 Standard × 0.70 = $84/month

---

#### Agent Management Dashboard
**Location**: `/admin/agents`

**Features**:
```python
# Create agents manually
POST /admin/agents/create
{
  "count": 10,
  "strategy_type": "rsi",  // optional, random if not specified
  "symbols": ["AAPL", "MSFT"],  // optional
  "initial_capital": 10000
}

# View agent statistics
GET /admin/agents/stats
Response: {
  "total_agents": 87,
  "active": 85,
  "paused": 2,
  "total_trades_today": 12,
  "total_trades_all_time": 1543,
  "avg_trades_per_agent": 17.7,
  "strategies": {
    "rsi": 45,
    "ma_crossover": 42
  }
}

# Pause/Resume agent
POST /admin/agents/{agent_id}/pause
POST /admin/agents/{agent_id}/resume

# Delete agent
DELETE /admin/agents/{agent_id}
```

**UI Components**:
- **Agent Creation Card**:
  - Input: Number of agents to create (1-50)
  - Dropdown: Strategy type (RSI, MA Crossover, Random)
  - Button: "Create Agents"
  - Shows cost estimate: $0/month (all free resources)

- **Agent Statistics Dashboard**:
  - Total agents count (big number)
  - Active vs Paused breakdown
  - Trades today / this week / all time
  - Strategy distribution chart
  - Performance metrics (avg return %)

- **Agent List Table**:
  - Username, Strategy, Symbols, Total Trades, Last Trade, Status
  - Actions: Pause, Resume, Delete
  - Sortable by trades, performance, etc.

**No Cron Tweaking Required**:
- Manual creation bypasses cron entirely
- Cron still runs for automated creation (can be disabled if desired)
- Admin has full control via UI

---

### 2. Inbound SMS/Email Trading (Week 2-3)

#### Twilio SMS Trading
**Phone Number**: Get from Twilio (e.g., +1-555-BUY-STOK)

**Inbound Message Handler**:
```python
@app.route('/api/twilio/inbound', methods=['POST'])
def twilio_inbound():
    """Handle inbound SMS trades"""
    from_number = request.form.get('From')
    message = request.form.get('Body').strip().upper()
    
    # Find user by phone number
    user = User.query.join(NotificationPreferences).filter(
        NotificationPreferences.phone_number == from_number
    ).first()
    
    if not user:
        send_sms(from_number, "❌ Phone not registered. Add phone in settings.")
        return '', 200
    
    # Parse trade command
    # Formats: "BUY 10 TSLA", "SELL 5 AAPL", "BUY MSFT 150"
    trade = parse_trade_command(message)
    
    if not trade:
        send_sms(from_number, "❌ Invalid format. Use: BUY 10 TSLA or SELL 5 AAPL")
        return '', 200
    
    # Get price using EXISTING 90-second cache (already implemented)
    from portfolio_performance import get_stock_prices
    prices = get_stock_prices([trade['ticker']])
    price = prices.get(trade['ticker'])
    
    if not price:
        send_sms(from_number, f"❌ Unable to get price for {trade['ticker']}")
        return '', 200
    
    # Execute trade
    try:
        # Get current position for percentage calculation
        current_position = Stock.query.filter_by(
            user_id=user.id,
            ticker=trade['ticker']
        ).first()
        
        transaction = execute_trade(
            user_id=user.id,
            ticker=trade['ticker'],
            quantity=trade['quantity'],
            price=price,
            transaction_type=trade['action'],
            source='sms'
        )
        
        # Calculate position percentage
        if current_position and trade['action'] == 'sell':
            position_pct = (trade['quantity'] / current_position.quantity) * 100
        else:
            position_pct = None
        
        # Send confirmation
        total = trade['quantity'] * price
        send_sms(
            from_number,
            f"✅ {trade['action']} {trade['quantity']} {trade['ticker']} @ ${price:.2f} = ${total:.2f}"
        )
        
        # Notify subscribers (with position percentage)
        notify_subscribers(user.id, 'trade', {
            'username': user.username,
            'action': trade['action'].lower(),
            'quantity': trade['quantity'],
            'ticker': trade['ticker'],
            'price': price,
            'position_pct': position_pct  # NEW: for "50% of position"
        })
        
    except Exception as e:
        send_sms(from_number, f"❌ Trade failed: {str(e)}")
    
    return '', 200

def parse_trade_command(message):
    """Parse BUY/SELL commands"""
    import re
    
    # Pattern: BUY 10 TSLA or SELL 5 AAPL
    pattern = r'(BUY|SELL)\s+(\d+)\s+([A-Z]{1,5})'
    match = re.match(pattern, message)
    
    if match:
        return {
            'action': match.group(1).lower(),
            'quantity': int(match.group(2)),
            'ticker': match.group(3)
        }
    
    # Alternative pattern: BUY TSLA 10
    pattern2 = r'(BUY|SELL)\s+([A-Z]{1,5})\s+(\d+)'
    match = re.match(pattern2, message)
    
    if match:
        return {
            'action': match.group(1).lower(),
            'ticker': match.group(2),
            'quantity': int(match.group(3))
        }
    
    return None

def get_cached_or_live_price(ticker):
    """Get price from cache (<90s) or live API"""
    from datetime import datetime, timedelta
    import redis
    
    # Check if market is open
    now = datetime.now(pytz.timezone('America/New_York'))
    if now.weekday() >= 5:  # Weekend
        # Use last closing price
        return get_last_closing_price(ticker)
    
    if now.hour < 9 or (now.hour == 9 and now.minute < 30):
        # Before market open
        return get_last_closing_price(ticker)
    
    if now.hour >= 16:
        # After market close
        return get_last_closing_price(ticker)
    
    # Market is open - check cache
    cache_key = f"price:{ticker}"
    cached = redis_client.get(cache_key)
    
    if cached:
        cache_data = json.loads(cached)
        cache_time = datetime.fromisoformat(cache_data['timestamp'])
        
        # Cache valid for 90 seconds
        if (now - cache_time).total_seconds() < 90:
            return cache_data['price']
    
    # Fetch live price
    price = fetch_live_price_alpha_vantage(ticker)
    
    # Cache for 90 seconds
    redis_client.setex(
        cache_key,
        90,
        json.dumps({'price': price, 'timestamp': now.isoformat()})
    )
    
    return price
```

**Twilio Setup**:
- Purchase phone number: $1/month
- Configure webhook URL: `https://apestogether.ai/api/twilio/inbound`
- Enable SMS for the number

---

#### Email Trading
**Email Address**: trades@apestogether.ai

**Email Handler** (via SendGrid Inbound Parse or similar):
```python
@app.route('/api/email/inbound', methods=['POST'])
def email_inbound():
    """Handle inbound email trades"""
    from_email = request.form.get('from')
    subject = request.form.get('subject', '').strip().upper()
    body = request.form.get('text', '').strip().upper()
    
    # Find user by email
    user = User.query.filter_by(email=from_email).first()
    
    if not user:
        send_email(from_email, "Trade Failed", "Email not registered.")
        return '', 200
    
    # Parse from subject or body
    trade = parse_trade_command(subject) or parse_trade_command(body)
    
    if not trade:
        send_email(
            from_email,
            "Trade Failed",
            "Invalid format. Use: BUY 10 TSLA or SELL 5 AAPL"
        )
        return '', 200
    
    # Same logic as SMS handler
    price = get_cached_or_live_price(trade['ticker'])
    transaction = execute_trade(...)
    
    # Send confirmation email
    send_email(
        from_email,
        f"Trade Confirmed: {trade['action']} {trade['ticker']}",
        f"Executed {trade['quantity']} shares at ${price:.2f}"
    )
    
    # Notify subscribers
    notify_subscribers(...)
    
    return '', 200
```

**Email Service Setup**:
- SendGrid Inbound Parse or Mailgun Routes
- Forward trades@apestogether.ai → webhook
- Cost: Included in email service

---

### 3. Enhanced Notification System (Week 2)

#### Notification Preferences at Signup
**During Account Creation**:
```python
@app.route('/auth/complete-profile', methods=['POST'])
def complete_profile():
    """After OAuth, collect notification preferences"""
    
    # Show modal/page with:
    # - Phone number (optional)
    # - Default notification method: [ ] Email  [ ] SMS
    # - "You can change per-subscription in settings"
    
    user.default_notification_method = request.form.get('method', 'email')
    
    if phone := request.form.get('phone'):
        user.phone_number = phone
```

**Template** (templates/complete_profile.html):
```html
<form>
  <h3>Notification Preferences</h3>
  
  <div class="form-group">
    <label>Phone Number (Optional)</label>
    <input type="tel" name="phone" placeholder="+1-555-123-4567">
    <small>Required for SMS trade execution and notifications</small>
  </div>
  
  <div class="form-group">
    <label>Default Notification Method</label>
    <select name="method">
      <option value="email" selected>Email (Free)</option>
      <option value="sms">SMS ($0.01 per message)</option>
    </select>
    <small>This will be your default for new subscriptions</small>
  </div>
  
  <button type="submit">Complete Setup</button>
</form>
```

---

#### Per-Subscription Notification Settings
**Settings Page**: `/settings/notifications`

**UI**:
```html
<h3>Your Subscriptions</h3>

<table>
  <thead>
    <tr>
      <th>Portfolio Owner</th>
      <th>Notification Method</th>
      <th>Enabled</th>
    </tr>
  </thead>
  <tbody>
    {% for sub in user.subscriptions %}
    <tr>
      <td>{{ sub.subscribed_to.username }}</td>
      <td>
        <select data-subscription-id="{{ sub.id }}">
          <option value="email" {{ 'selected' if sub.notification_preference.notification_type == 'email' }}>
            Email
          </option>
          <option value="sms" {{ 'selected' if sub.notification_preference.notification_type == 'sms' }}>
            SMS (+$0.01/trade)
          </option>
        </select>
      </td>
      <td>
        <input type="checkbox" 
               data-subscription-id="{{ sub.id }}"
               {{ 'checked' if sub.notification_preference.enabled }}>
      </td>
    </tr>
    {% endfor %}
  </tbody>
</table>
```

**API Endpoint**:
```python
@app.route('/api/notifications/preferences/<int:subscription_id>', methods=['PUT'])
@login_required
def update_notification_preference(subscription_id):
    """Update notification settings for a subscription"""
    
    pref = NotificationPreferences.query.filter_by(
        user_id=current_user.id,
        subscription_id=subscription_id
    ).first()
    
    if not pref:
        pref = NotificationPreferences(
            user_id=current_user.id,
            subscription_id=subscription_id
        )
        db.session.add(pref)
    
    pref.notification_type = request.json.get('type', 'email')  # email or sms
    pref.enabled = request.json.get('enabled', True)
    
    db.session.commit()
    
    return jsonify({'success': True})
```

---

#### Updated notify_subscribers() Function
```python
def notify_subscribers(portfolio_owner_id, notification_type, data):
    """Send notifications via email or SMS based on user preferences"""
    from models import Subscription, NotificationPreferences, NotificationLog
    
    # Get all REAL subscribers (not ghost subscribers)
    subscriptions = Subscription.query.filter_by(
        subscribed_to_id=portfolio_owner_id,
        status='active'
    ).all()
    
    for sub in subscriptions:
        # Get preference for this subscription
        pref = NotificationPreferences.query.filter_by(
            user_id=sub.subscriber_id,
            subscription_id=sub.id
        ).first()
        
        # Skip if disabled
        if pref and not pref.enabled:
            continue
        
        # Default to email if no preference set
        method = pref.notification_type if pref else 'email'
        
        # Format message with position percentage
        if notification_type == 'trade':
            if data.get('position_pct'):
                # Include percentage: "sold 10 TSLA (50% of position)"
                message = f"🔔 {data['username']} {data['action']} {data['quantity']} {data['ticker']} ({data['position_pct']:.1f}% of position) @ ${data['price']:.2f}"
            else:
                # Buy or no existing position: just quantity
                message = f"🔔 {data['username']} {data['action']} {data['quantity']} {data['ticker']} @ ${data['price']:.2f}"
        
        # Send notification (ONLY to real subscribers, not ghosts)
        if method == 'sms' and pref and pref.phone_number:
            result = send_sms(pref.phone_number, message)
        else:
            result = send_email(
                sub.subscriber.email,
                f"Trade Alert: {data['username']}",
                message
            )
        
        # Log delivery
        log = NotificationLog(
            user_id=sub.subscriber_id,
            portfolio_owner_id=portfolio_owner_id,
            subscription_id=sub.id,
            notification_type=method,
            status=result['status'],
            twilio_sid=result.get('sid'),
            error_message=result.get('error')
        )
        db.session.add(log)
    
    db.session.commit()
    
    # NOTE: Ghost subscribers (AdminSubscription) do NOT receive notifications
```

---

### 4. Agent NewsAPI Integration (Week 5-6)

#### Free Tier Limits
- 100 API calls/day (free)
- Use sparingly: 20 agents × 5 checks/day = 100 calls

#### Implementation
```python
class TradingAgent:
    def __init__(self, ...):
        self.use_news = random.random() < 0.2  # Only 20% of agents use news
        self.news_check_frequency = 'daily'  # or 'weekly'
    
    def fetch_news_sentiment(self, symbol):
        """Fetch news sentiment (free tier: 100 calls/day)"""
        if not self.use_news:
            return None
        
        import requests
        
        try:
            response = requests.get(
                'https://newsapi.org/v2/everything',
                params={
                    'q': symbol,
                    'apiKey': os.environ['NEWSAPI_KEY'],
                    'pageSize': 10,
                    'sortBy': 'publishedAt'
                },
                timeout=5
            )
            
            articles = response.json().get('articles', [])
            
            # Simple sentiment: count positive/negative words in headlines
            sentiment_score = calculate_sentiment(articles)
            
            return sentiment_score  # -1 to 1
            
        except Exception as e:
            logger.error(f"NewsAPI error: {e}")
            return None
    
    def generate_signals(self):
        """Enhanced with news sentiment"""
        signals = {}
        
        for symbol in self.symbols:
            data = self.fetch_data(symbol)
            current_price = data['Close'].iloc[-1]
            
            # Technical indicators
            rsi = data['rsi'].iloc[-1]
            
            # Base signal from technical
            if rsi < 30:
                base_signal = 'buy'
                confidence = 0.6
            elif rsi > 70:
                base_signal = 'sell'
                confidence = 0.6
            else:
                continue
            
            # Enhance with news (if agent uses news)
            if self.use_news:
                sentiment = self.fetch_news_sentiment(symbol)
                
                if sentiment:
                    # Positive news boosts buy signals, dampens sell
                    if base_signal == 'buy' and sentiment > 0.3:
                        confidence += 0.2
                    elif base_signal == 'sell' and sentiment < -0.3:
                        confidence += 0.2
                    # Cancel contradictory signals
                    elif base_signal == 'buy' and sentiment < -0.5:
                        continue
                    elif base_signal == 'sell' and sentiment > 0.5:
                        continue
            
            # Only trade if confidence > threshold
            if confidence > 0.65:
                signals[symbol] = {
                    'action': base_signal,
                    'price': current_price,
                    'reason': f'RSI {rsi:.1f}' + (f' + news sentiment' if self.use_news else ''),
                    'confidence': confidence
                }
        
        return signals

def calculate_sentiment(articles):
    """Simple sentiment from headlines"""
    positive_words = ['surge', 'up', 'gain', 'beat', 'strong', 'growth', 'record', 'high']
    negative_words = ['fall', 'down', 'loss', 'miss', 'weak', 'drop', 'concern', 'low']
    
    score = 0
    for article in articles:
        title = article.get('title', '').lower()
        
        for word in positive_words:
            if word in title:
                score += 1
        
        for word in negative_words:
            if word in title:
                score -= 1
    
    # Normalize to -1 to 1
    return max(-1, min(1, score / len(articles) if articles else 0))
```

**NewsAPI Usage**:
- Free tier: 100 calls/day
- Only 20% of agents use it (20 agents if you have 100 total)
- Check news once per day per agent
- Total: ~20 calls/day (well under limit)

**Cost**: $0/month (free tier)

---

### 5. Agent Cost Drivers

**What Drives Agent Costs?**

1. **Market Data (yfinance)**: $0 - Unlimited free
2. **Database Storage**: ~$0.10/agent/month (negligible)
3. **Vercel Function Executions**: ~$0.02/agent/month
4. **SMS Notifications**: $0.15-0.30/agent/day IF they have subscribers
5. **NewsAPI**: $0 (free tier, limited usage)

**Cost Per Agent**:
- **Agent WITHOUT subscribers**: ~$0.50/month
- **Agent WITH subscribers**: ~$5-10/month (SMS costs)

**Scaling Economics**:
```
10 agents (no subscribers):   $5/month
50 agents (10 with subs):      $75/month
100 agents (20 with subs):     $150/month
500 agents (100 with subs):    $750/month
```

**Key Insight**: Agent costs scale primarily with **subscriber SMS notifications**, not the agents themselves.

**Cost Control**:
- Start with agents that have NO subscribers (testing)
- Gradually add subscribers as agents prove profitable
- Most agents will never get subscribers (that's fine, they're free)
- Focus subscriber adds on top-performing agents

---

## Implementation Timeline Updates

### Week 2 (Enhanced): SMS/Email Trading + Notifications
**Original**: 3-4 days  
**Enhanced**: 5-6 days

**Tasks**:
- ✅ SMS notifications (original)
- 🆕 SMS inbound trading (BUY/SELL commands)
- 🆕 Email inbound trading
- 🆕 Price caching (90s)
- 🆕 Notification preference UI at signup
- 🆕 Per-subscription notification toggles

---

### Week 4 (Enhanced): Admin Tools
**Original**: 2-3 days  
**Enhanced**: 4-5 days

**Tasks**:
- ✅ Manual subscriber add (original)
- 🆕 Agent creation dashboard
- 🆕 Agent statistics view
- 🆕 Manual agent triggers (individual/batch)
- 🆕 Agent pause/resume/delete
- 🆕 Cost tracking for admin-sponsored subs

---

### Week 5-6 (Enhanced): Agents with News
**Original**: Agent foundation  
**Enhanced**: Agent foundation + NewsAPI

**Tasks**:
- ✅ TradingAgent class (original)
- ✅ Technical indicators (RSI, MA)
- 🆕 NewsAPI integration (20% of agents)
- 🆕 Sentiment analysis
- 🆕 Combined signals (technical + news)

---

## Database Model Updates

### NotificationPreferences (Enhanced)
```python
class NotificationPreferences(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    subscription_id = db.Column(db.Integer, db.ForeignKey('subscription.id'))
    portfolio_owner_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    
    # Enhanced fields
    notification_type = db.Column(db.String(10), default='email')  # 'email' or 'sms'
    enabled = db.Column(db.Boolean, default=True)
    phone_number = db.Column(db.String(20))
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
```

### User (Enhanced)
```python
class User(db.Model):
    # ... existing fields ...
    
    # New fields
    default_notification_method = db.Column(db.String(10), default='email')
    phone_number = db.Column(db.String(20))  # For SMS trading
```

### AgentConfig (Enhanced)
```python
class AgentConfig(db.Model):
    # ... existing fields ...
    
    # New fields
    use_news = db.Column(db.Boolean, default=False)  # 20% of agents
    news_check_frequency = db.Column(db.String(20), default='daily')
    last_news_check = db.Column(db.DateTime)
```

---

## Environment Variables

Add to `.env` and Vercel:
```bash
# NewsAPI (free tier)
NEWSAPI_KEY=your_free_newsapi_key

# Twilio (existing, but need inbound number)
TWILIO_INBOUND_NUMBER=+15551234567

# Redis (for price caching)
REDIS_URL=redis://localhost:6379
```

---

## Cost Summary (Updated)

### Monthly Operating (100 agents, 20 with subscribers)

| Service | Cost | Notes |
|---------|------|-------|
| Alpha Vantage | $100 | Existing |
| Xero | $20 | Existing |
| Vercel | $30-60 | Scales with usage |
| Twilio SMS | $30-100 | 20 agents × $1.50/day |
| Twilio Phone | $1 | Inbound number |
| NewsAPI | $0 | Free tier (100 calls/day) |
| Redis (optional) | $10 | Price caching |
| **Total** | **$191-291/mo** | |

**Cost per agent WITH subscribers**: ~$5-10/month  
**Cost per agent WITHOUT subscribers**: ~$0.50/month

---

## Summary of Additions

✅ **Admin Dashboard**:
- Manual subscriber add/remove with cost tracking
- Agent creation (individual or batch)
- Agent statistics dashboard
- No cron tweaking needed

✅ **Inbound Trading**:
- SMS: Text "BUY 10 TSLA" to trade
- Email: Send to trades@apestogether.ai
- 90-second price caching
- Market hours detection
- Subscriber notifications

✅ **Enhanced Notifications**:
- Select email/SMS at signup
- Per-subscription toggles
- Settings page to manage all subscriptions
- Email AND SMS support (not just SMS)

✅ **Agent News Integration**:
- Free NewsAPI tier (100 calls/day)
- 20% of agents use news
- Sentiment analysis from headlines
- Combined technical + news signals
- Cost: $0/month

✅ **Agent Costs**:
- Free without subscribers (~$0.50/mo)
- $5-10/mo with subscribers (SMS costs)
- Scales with subscriber notifications
