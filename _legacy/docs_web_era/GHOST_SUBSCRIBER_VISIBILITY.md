# Ghost Subscriber Visibility Requirements

## ✅ Confirmed: Ghost Subscribers ARE Visible

### Where They Show Up:

#### 1. User's Dashboard
```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 john_trader's Portfolio
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Subscribers: 10  <-- 2 real + 8 ghosts
Monthly Earnings: $105.00

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

**Implementation**:
```python
def get_total_subscribers(user_id):
    # Real subscribers
    real = Subscription.query.filter_by(
        subscribed_to_id=user_id,
        status='active'
    ).count()
    
    # Ghost subscribers
    ghosts = db.session.query(
        db.func.sum(AdminSubscription.ghost_subscriber_count)
    ).filter_by(
        portfolio_user_id=user_id
    ).scalar() or 0
    
    return real + ghosts
    # Example: 2 + 8 = 10 total
```

---

#### 2. Leaderboard
```
┌──────────────────────────────────────────────────────┐
│ Top Portfolios                                       │
├────────┬───────────────┬────────────┬────────────────┤
│ Rank   │ User          │ Return %   │ Subscribers    │
├────────┼───────────────┼────────────┼────────────────┤
│ 1      │ john_trader   │ +15.2%     │ 10 📈          │
│ 2      │ jane_investor │ +12.1%     │ 5              │
│ 3      │ mike_stocks   │ +8.5%      │ 3              │
└────────┴───────────────┴────────────┴────────────────┘
                                         ^
                                         |
                              Includes 8 ghosts
```

**Implementation**:
```python
def get_leaderboard():
    users = User.query.all()
    
    leaderboard = []
    for user in users:
        # Get total subscribers (real + ghost)
        total_subs = get_total_subscribers(user.id)
        
        leaderboard.append({
            'username': user.username,
            'return_pct': calculate_return(user.id),
            'subscribers': total_subs  # Shows 10, not 2
        })
    
    return sorted(leaderboard, key=lambda x: x['return_pct'], reverse=True)
```

---

#### 3. Xero Accounting
```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Monthly Payout Report - October 2025
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

john_trader
  Real Subscribers:     2 × $15 = $30
  Ghost Subscribers:    8 × $15 = $120
  Total Revenue:        $150
  Your 70% Payout:      $105.00 ✅
  
Check to Write:
  Payee: john_trader
  Amount: $105.00
  Memo: "Oct 2025 subscriber earnings"

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

**Xero Integration**:
```python
def generate_monthly_payout_report():
    """For check writing at month end"""
    
    users = User.query.filter(
        # Users with real OR ghost subscribers
        or_(
            User.subscriptions_as_owner.any(),
            User.ghost_subscriptions.any()
        )
    ).all()
    
    report = []
    for user in users:
        # Real subscriber revenue
        real_subs = Subscription.query.filter_by(
            subscribed_to_id=user.id,
            status='active'
        ).all()
        real_revenue = sum(sub.tier_price for sub in real_subs)
        
        # Ghost subscriber revenue
        ghost_subs = AdminSubscription.query.filter_by(
            portfolio_user_id=user.id
        ).all()
        ghost_revenue = sum(gs.monthly_revenue for gs in ghost_subs)
        
        # Total payout (70% of combined)
        total_revenue = real_revenue + ghost_revenue
        payout = total_revenue * 0.70
        
        report.append({
            'user': user.username,
            'real_count': len(real_subs),
            'ghost_count': sum(gs.ghost_subscriber_count for gs in ghost_subs),
            'total_count': len(real_subs) + sum(gs.ghost_subscriber_count for gs in ghost_subs),
            'real_revenue': real_revenue,
            'ghost_revenue': ghost_revenue,
            'total_revenue': total_revenue,
            'payout_70_pct': payout
        })
    
    return report
```

**Xero Export** (CSV for importing):
```csv
Payee,Real Subs,Ghost Subs,Total Subs,Revenue,Payout,Account
john_trader,2,8,10,$150.00,$105.00,User Payments
jane_investor,5,0,5,$75.00,$52.50,User Payments
mike_stocks,3,2,5,$75.00,$52.50,User Payments
```

---

## What DOESN'T Happen

### ❌ Ghost Subscribers Do NOT:
1. **Receive notifications**
   - No SMS when trades happen
   - No emails
   - They're not real users, just a number

2. **Create Stripe charges**
   - No subscription records in Stripe
   - No monthly billing
   - No fees

3. **Have user accounts**
   - No login credentials
   - No dashboard
   - No profile

4. **Show in subscriber lists**
   - User can't see "who" their subscribers are
   - Ghost count is just added to total
   - Example: Dashboard shows "10 subscribers" (doesn't list names)

---

## Implementation Summary

### Database Queries

**Total Subscriber Count** (Dashboard):
```python
# Combine real + ghost
total = (
    Subscription.query.filter_by(subscribed_to_id=user_id).count() +
    db.session.query(db.func.sum(AdminSubscription.ghost_subscriber_count))
        .filter_by(portfolio_user_id=user_id).scalar() or 0
)
```

**Notification Recipients** (Only Real):
```python
# Send ONLY to real subscribers
subscribers = Subscription.query.filter_by(
    subscribed_to_id=user_id,
    status='active'
).all()

for sub in subscribers:
    send_notification(sub.subscriber, trade_data)

# Ghost subscribers are NOT notified
```

**Monthly Payout** (Real + Ghost):
```python
# Calculate from both
real_revenue = sum(s.tier_price for s in real_subscriptions)
ghost_revenue = sum(gs.monthly_revenue for gs in ghost_subscriptions)
total_payout = (real_revenue + ghost_revenue) * 0.70
```

---

## Admin UI Requirements

### Ghost Subscriber Management Page

```html
<div class="admin-ghost-subscribers">
  <h2>Ghost Subscriber Management</h2>
  
  <!-- Add Ghosts -->
  <div class="add-form">
    <input type="text" placeholder="Search user..." id="user-search">
    <input type="number" placeholder="Ghost count" id="ghost-count">
    <select id="tier">
      <option value="light">Light - $10/mo</option>
      <option value="standard">Standard - $15/mo</option>
      <option value="active">Active - $25/mo</option>
      <option value="pro">Pro - $35/mo</option>
      <option value="elite">Elite - $55/mo</option>
    </select>
    <textarea placeholder="Reason (private note)"></textarea>
    
    <div class="calculation">
      <strong>Monthly Payout:</strong> <span id="payout">$0.00</span>
      <small>(Ghost count × tier price × 70%)</small>
    </div>
    
    <button onclick="addGhostSubscribers()">Add Ghost Subscribers</button>
  </div>
  
  <!-- Current Ghosts -->
  <table>
    <thead>
      <tr>
        <th>User</th>
        <th>Real Subs</th>
        <th>Ghost Subs</th>
        <th>Total</th>
        <th>Tier</th>
        <th>Monthly Payout</th>
        <th>Reason</th>
        <th>Actions</th>
      </tr>
    </thead>
    <tbody>
      <tr>
        <td>john_trader</td>
        <td>2</td>
        <td>8</td>
        <td>10</td>
        <td>Standard</td>
        <td>$105.00</td>
        <td>Marketing boost</td>
        <td><button onclick="removeGhosts(1)">Remove</button></td>
      </tr>
    </tbody>
  </table>
  
  <!-- Monthly Summary -->
  <div class="summary">
    <h3>Monthly Ghost Subscriber Costs</h3>
    <p>Total Ghost Count: <strong>35</strong></p>
    <p>Total Monthly Payout: <strong>$450.00</strong></p>
    <p>Source: Your Citi Business checking account</p>
  </div>
</div>
```

---

## User Perception

**What john_trader Sees**:
- Dashboard: "You have 10 subscribers"
- Leaderboard: Shows as having 10 subscribers
- Monthly earnings: $105 (70% of 10 × $15)
- Receives check for $105

**What john_trader Doesn't Know**:
- 8 are ghost subscribers
- You're paying the $84 portion
- No real users behind those 8

**Result**: 
- Motivation boost ("I have 10 subscribers!")
- Word-of-mouth marketing ("This platform is great, I'm making money!")
- You can cancel ghosts anytime if performance doesn't justify it

---

## Summary

✅ **Ghost subscribers DO show up in:**
- User dashboard (subscriber count)
- Leaderboard (subscriber count)
- Xero accounting (payout calculations)

❌ **Ghost subscribers do NOT:**
- Receive notifications
- Create Stripe charges
- Have user accounts
- Show as individual subscriber names

**Implementation**:
- `get_total_subscribers()` → Sums real + ghost
- `notify_subscribers()` → Only sends to real
- `generate_payout_report()` → Includes both for check amounts
