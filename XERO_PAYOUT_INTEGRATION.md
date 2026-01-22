# 💰 Xero Integration for Influencer Payouts
## Apple/Google IAP → Xero Accounting → Influencer Checks

**Document Version**: 1.0  
**Created**: January 21, 2026  

---

## Revenue Flow Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         PAYMENT FLOW                                     │
│                                                                          │
│  User Subscribes ($9/mo)                                                │
│         │                                                                │
│         ▼                                                                │
│  ┌─────────────────┐                                                    │
│  │ Apple App Store │ ──or── │ Google Play │                            │
│  │   (30% = $2.70) │        │ (30% = $2.70)│                           │
│  └────────┬────────┘        └──────┬───────┘                           │
│           │                        │                                    │
│           └────────────┬───────────┘                                    │
│                        ▼                                                │
│           ┌────────────────────────┐                                    │
│           │  Apes Together Backend  │                                   │
│           │  (Receives $6.30/sub)   │                                   │
│           │                         │                                   │
│           │  Split:                 │                                   │
│           │  - Influencer: $5.40    │                                   │
│           │  - Platform:   $0.90    │                                   │
│           └────────────┬────────────┘                                   │
│                        │                                                │
│                        ▼                                                │
│           ┌────────────────────────┐                                    │
│           │     Xero Accounting     │                                   │
│           │                         │                                   │
│           │  - Track per influencer │                                   │
│           │  - Monthly aggregation  │                                   │
│           │  - Generate invoices    │                                   │
│           │  - Issue payments       │                                   │
│           └────────────┬────────────┘                                   │
│                        │                                                │
│                        ▼                                                │
│           ┌────────────────────────┐                                    │
│           │   Influencer Receives   │                                   │
│           │   Monthly Check/ACH     │                                   │
│           │                         │                                   │
│           │   Real subs × $5.40     │                                   │
│           │ + Bonus subs × $5.40    │                                   │
│           └─────────────────────────┘                                   │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Data Model Updates

### Updated AdminSubscription Model (Bonus Subscribers)

```python
# models.py - Update AdminSubscription for new pricing

class AdminSubscription(db.Model):
    """
    Bonus/Ghost subscribers - admin pays full influencer payout ($5.40/sub)
    These appear in subscriber counts but don't go through Apple/Google
    """
    __tablename__ = 'admin_subscription'
    
    id = db.Column(db.Integer, primary_key=True)
    portfolio_user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    bonus_subscriber_count = db.Column(db.Integer, default=0, nullable=False)
    monthly_payout = db.Column(db.Float, nullable=False)  # count × $5.40
    reason = db.Column(db.String(500), nullable=True)  # Admin notes
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationship
    portfolio_user = db.relationship('User', foreign_keys=[portfolio_user_id], backref='bonus_subscriptions')
    
    # Fixed payout per subscriber (60% of $9)
    PAYOUT_PER_SUBSCRIBER = 5.40
    
    @property
    def calculated_payout(self):
        """Total monthly payout for bonus subscribers"""
        return self.bonus_subscriber_count * self.PAYOUT_PER_SUBSCRIBER
    
    def __repr__(self):
        return f"<AdminSubscription user={self.portfolio_user_id} bonus={self.bonus_subscriber_count} payout=${self.monthly_payout}>"
```

### XeroPayoutRecord Model

```python
# models.py - Add XeroPayoutRecord

class XeroPayoutRecord(db.Model):
    """
    Track payouts synced to Xero for influencer payments
    """
    __tablename__ = 'xero_payout_record'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    
    # Period
    payout_month = db.Column(db.Integer, nullable=False)  # 1-12
    payout_year = db.Column(db.Integer, nullable=False)
    
    # Subscriber counts
    real_subscriber_count = db.Column(db.Integer, default=0)
    bonus_subscriber_count = db.Column(db.Integer, default=0)
    total_subscriber_count = db.Column(db.Integer, default=0)
    
    # Amounts
    real_payout = db.Column(db.Float, default=0.0)      # From Apple/Google revenue
    bonus_payout = db.Column(db.Float, default=0.0)     # From admin pocket
    total_payout = db.Column(db.Float, default=0.0)
    
    # Xero sync
    xero_contact_id = db.Column(db.String(100), nullable=True)
    xero_invoice_id = db.Column(db.String(100), nullable=True)
    xero_payment_id = db.Column(db.String(100), nullable=True)
    
    # Status
    status = db.Column(db.String(20), default='pending')  # pending, invoiced, paid
    synced_to_xero = db.Column(db.Boolean, default=False)
    synced_at = db.Column(db.DateTime, nullable=True)
    paid_at = db.Column(db.DateTime, nullable=True)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    user = db.relationship('User', backref='payout_records')
    
    __table_args__ = (
        db.UniqueConstraint('user_id', 'payout_month', 'payout_year', name='unique_user_month_payout'),
    )
```

---

## Subscriber Count Calculation

### Display Subscriber Count (Real + Bonus)

```python
# api/index.py - Add to User model or utility function

def get_display_subscriber_count(user_id: int) -> int:
    """
    Get total subscriber count for display (real + bonus)
    Used for: leaderboard, portfolio pages, public profiles
    """
    # Real subscribers (active Apple/Google subscriptions)
    real_count = Subscription.query.filter(
        Subscription.subscribed_to_id == user_id,
        Subscription.status == 'active'
    ).count()
    
    # Bonus subscribers (admin-added)
    bonus_record = AdminSubscription.query.filter_by(
        portfolio_user_id=user_id
    ).first()
    bonus_count = bonus_record.bonus_subscriber_count if bonus_record else 0
    
    return real_count + bonus_count


def get_subscriber_breakdown(user_id: int) -> dict:
    """
    Get detailed subscriber breakdown (admin-only view)
    """
    real_count = Subscription.query.filter(
        Subscription.subscribed_to_id == user_id,
        Subscription.status == 'active'
    ).count()
    
    bonus_record = AdminSubscription.query.filter_by(
        portfolio_user_id=user_id
    ).first()
    bonus_count = bonus_record.bonus_subscriber_count if bonus_record else 0
    
    return {
        'real_subscribers': real_count,
        'bonus_subscribers': bonus_count,
        'total_display': real_count + bonus_count,
        'real_monthly_payout': real_count * 5.40,
        'bonus_monthly_payout': bonus_count * 5.40,
        'total_monthly_payout': (real_count + bonus_count) * 5.40
    }
```

### Update Leaderboard Query

```python
# leaderboard_utils.py - Update to include bonus subscribers

def get_leaderboard_with_subscribers():
    """
    Get leaderboard data with combined subscriber counts
    """
    # Subquery for real subscriber counts
    real_sub_counts = db.session.query(
        Subscription.subscribed_to_id,
        func.count(Subscription.id).label('real_count')
    ).filter(
        Subscription.status == 'active'
    ).group_by(Subscription.subscribed_to_id).subquery()
    
    # Subquery for bonus subscriber counts
    bonus_counts = db.session.query(
        AdminSubscription.portfolio_user_id,
        AdminSubscription.bonus_subscriber_count.label('bonus_count')
    ).subquery()
    
    # Main query combining both
    users = db.session.query(
        User,
        func.coalesce(real_sub_counts.c.real_count, 0).label('real_subscribers'),
        func.coalesce(bonus_counts.c.bonus_count, 0).label('bonus_subscribers'),
        (func.coalesce(real_sub_counts.c.real_count, 0) + 
         func.coalesce(bonus_counts.c.bonus_count, 0)).label('total_subscribers')
    ).outerjoin(
        real_sub_counts, User.id == real_sub_counts.c.subscribed_to_id
    ).outerjoin(
        bonus_counts, User.id == bonus_counts.c.portfolio_user_id
    ).filter(
        User.is_public == True
    ).order_by(
        desc('total_subscribers')
    ).all()
    
    return users
```

---

## Xero API Integration

### Environment Variables

```
# .env additions
XERO_CLIENT_ID=your_xero_client_id
XERO_CLIENT_SECRET=your_xero_client_secret
XERO_TENANT_ID=your_xero_tenant_id
XERO_REDIRECT_URI=https://apestogether.ai/admin/xero/callback
```

### Xero Service

```python
# services/xero_integration.py

import os
import requests
from datetime import datetime, timedelta
from models import db, User, Subscription, AdminSubscription, XeroPayoutRecord, XeroSyncLog

class XeroPayoutService:
    """
    Handle Xero integration for influencer payouts
    """
    
    PAYOUT_PER_SUBSCRIBER = 5.40  # 60% of $9
    
    def __init__(self):
        self.client_id = os.environ.get('XERO_CLIENT_ID')
        self.client_secret = os.environ.get('XERO_CLIENT_SECRET')
        self.tenant_id = os.environ.get('XERO_TENANT_ID')
        self.access_token = None
        self.token_expiry = None
    
    def refresh_token(self):
        """Refresh Xero OAuth token"""
        # Implementation depends on Xero OAuth2 flow
        pass
    
    def calculate_monthly_payouts(self, year: int, month: int) -> list:
        """
        Calculate all influencer payouts for a given month
        Returns list of payout records ready for Xero
        """
        payouts = []
        
        # Get all users with subscribers (real or bonus)
        influencers = User.query.filter(
            User.is_public == True
        ).all()
        
        for user in influencers:
            # Count real subscribers for this month
            real_count = Subscription.query.filter(
                Subscription.subscribed_to_id == user.id,
                Subscription.status == 'active',
                # Only count subscriptions active during this month
                Subscription.created_at <= datetime(year, month + 1, 1) if month < 12 else datetime(year + 1, 1, 1)
            ).count()
            
            # Get bonus subscribers
            bonus_record = AdminSubscription.query.filter_by(
                portfolio_user_id=user.id
            ).first()
            bonus_count = bonus_record.bonus_subscriber_count if bonus_record else 0
            
            if real_count > 0 or bonus_count > 0:
                payout = XeroPayoutRecord(
                    user_id=user.id,
                    payout_month=month,
                    payout_year=year,
                    real_subscriber_count=real_count,
                    bonus_subscriber_count=bonus_count,
                    total_subscriber_count=real_count + bonus_count,
                    real_payout=real_count * self.PAYOUT_PER_SUBSCRIBER,
                    bonus_payout=bonus_count * self.PAYOUT_PER_SUBSCRIBER,
                    total_payout=(real_count + bonus_count) * self.PAYOUT_PER_SUBSCRIBER,
                    status='pending'
                )
                payouts.append(payout)
        
        return payouts
    
    def create_xero_contact(self, user: User) -> str:
        """
        Create or get Xero contact for influencer
        Returns Xero contact ID
        """
        headers = {
            'Authorization': f'Bearer {self.access_token}',
            'Xero-tenant-id': self.tenant_id,
            'Content-Type': 'application/json'
        }
        
        # Check if contact exists
        response = requests.get(
            f'https://api.xero.com/api.xro/2.0/Contacts?where=EmailAddress=="{user.email}"',
            headers=headers
        )
        
        if response.status_code == 200:
            contacts = response.json().get('Contacts', [])
            if contacts:
                return contacts[0]['ContactID']
        
        # Create new contact
        contact_data = {
            'Contacts': [{
                'Name': user.username,
                'EmailAddress': user.email,
                'ContactStatus': 'ACTIVE',
                'IsSupplier': True,  # Influencers are suppliers (we pay them)
                'DefaultCurrency': 'USD'
            }]
        }
        
        response = requests.post(
            'https://api.xero.com/api.xro/2.0/Contacts',
            headers=headers,
            json=contact_data
        )
        
        if response.status_code == 200:
            return response.json()['Contacts'][0]['ContactID']
        
        raise Exception(f"Failed to create Xero contact: {response.text}")
    
    def create_bill_for_payout(self, payout: XeroPayoutRecord, user: User) -> str:
        """
        Create a bill (accounts payable) in Xero for influencer payout
        Returns Xero invoice ID
        """
        headers = {
            'Authorization': f'Bearer {self.access_token}',
            'Xero-tenant-id': self.tenant_id,
            'Content-Type': 'application/json'
        }
        
        # Ensure contact exists
        if not payout.xero_contact_id:
            payout.xero_contact_id = self.create_xero_contact(user)
        
        # Create bill
        due_date = datetime(payout.payout_year, payout.payout_month, 1) + timedelta(days=45)
        
        bill_data = {
            'Invoices': [{
                'Type': 'ACCPAY',  # Accounts Payable (bill)
                'Contact': {'ContactID': payout.xero_contact_id},
                'Date': datetime.now().strftime('%Y-%m-%d'),
                'DueDate': due_date.strftime('%Y-%m-%d'),
                'Reference': f'Payout-{user.username}-{payout.payout_year}-{payout.payout_month:02d}',
                'Status': 'AUTHORISED',
                'LineItems': [
                    {
                        'Description': f'Subscriber payout - {payout.real_subscriber_count} real subscribers @ $5.40',
                        'Quantity': payout.real_subscriber_count,
                        'UnitAmount': self.PAYOUT_PER_SUBSCRIBER,
                        'AccountCode': '6000'  # Cost of Goods Sold or appropriate account
                    }
                ]
            }]
        }
        
        # Add bonus subscribers as separate line item if any
        if payout.bonus_subscriber_count > 0:
            bill_data['Invoices'][0]['LineItems'].append({
                'Description': f'Bonus subscriber payout - {payout.bonus_subscriber_count} bonus subscribers @ $5.40',
                'Quantity': payout.bonus_subscriber_count,
                'UnitAmount': self.PAYOUT_PER_SUBSCRIBER,
                'AccountCode': '6100'  # Marketing/Promotion expense account
            })
        
        response = requests.post(
            'https://api.xero.com/api.xro/2.0/Invoices',
            headers=headers,
            json=bill_data
        )
        
        if response.status_code == 200:
            invoice_id = response.json()['Invoices'][0]['InvoiceID']
            payout.xero_invoice_id = invoice_id
            payout.status = 'invoiced'
            payout.synced_to_xero = True
            payout.synced_at = datetime.utcnow()
            return invoice_id
        
        raise Exception(f"Failed to create Xero bill: {response.text}")
    
    def sync_monthly_payouts_to_xero(self, year: int, month: int):
        """
        Main function: Calculate and sync all payouts for a month to Xero
        """
        # Calculate payouts
        payouts = self.calculate_monthly_payouts(year, month)
        
        results = {
            'success': [],
            'failed': [],
            'total_payout': 0,
            'total_real': 0,
            'total_bonus': 0
        }
        
        for payout in payouts:
            try:
                user = User.query.get(payout.user_id)
                
                # Save payout record first
                db.session.add(payout)
                db.session.flush()
                
                # Create bill in Xero
                self.create_bill_for_payout(payout, user)
                
                results['success'].append({
                    'user': user.username,
                    'total_payout': payout.total_payout,
                    'xero_invoice_id': payout.xero_invoice_id
                })
                results['total_payout'] += payout.total_payout
                results['total_real'] += payout.real_payout
                results['total_bonus'] += payout.bonus_payout
                
            except Exception as e:
                results['failed'].append({
                    'user_id': payout.user_id,
                    'error': str(e)
                })
        
        db.session.commit()
        
        # Log sync
        log = XeroSyncLog(
            sync_type='monthly_payouts',
            records_synced=len(results['success']),
            records_failed=len(results['failed']),
            total_amount=results['total_payout'],
            status='completed' if not results['failed'] else 'partial',
            details=str(results)
        )
        db.session.add(log)
        db.session.commit()
        
        return results
```

---

## Admin Interface for Bonus Subscribers

### Admin Route

```python
# api/index.py - Add admin routes for bonus subscribers

@app.route('/admin/bonus-subscribers', methods=['GET'])
@login_required
@admin_required
def admin_bonus_subscribers():
    """View and manage bonus subscribers"""
    users_with_subs = db.session.query(
        User,
        AdminSubscription
    ).outerjoin(
        AdminSubscription, User.id == AdminSubscription.portfolio_user_id
    ).filter(
        User.is_public == True
    ).all()
    
    return render_template('admin/bonus_subscribers.html', users=users_with_subs)


@app.route('/admin/bonus-subscribers/<int:user_id>', methods=['POST'])
@login_required
@admin_required
def update_bonus_subscribers(user_id):
    """Update bonus subscriber count for a user"""
    user = User.query.get_or_404(user_id)
    
    new_count = request.form.get('bonus_count', type=int, default=0)
    reason = request.form.get('reason', '')
    
    # Get or create AdminSubscription record
    admin_sub = AdminSubscription.query.filter_by(portfolio_user_id=user_id).first()
    
    if admin_sub:
        admin_sub.bonus_subscriber_count = new_count
        admin_sub.monthly_payout = new_count * 5.40
        admin_sub.reason = reason
        admin_sub.updated_at = datetime.utcnow()
    else:
        admin_sub = AdminSubscription(
            portfolio_user_id=user_id,
            bonus_subscriber_count=new_count,
            monthly_payout=new_count * 5.40,
            reason=reason
        )
        db.session.add(admin_sub)
    
    db.session.commit()
    
    flash(f'Updated {user.username} to {new_count} bonus subscribers (${new_count * 5.40:.2f}/mo payout)')
    return redirect(url_for('admin_bonus_subscribers'))


@app.route('/admin/payouts/preview/<int:year>/<int:month>')
@login_required
@admin_required
def preview_monthly_payouts(year, month):
    """Preview monthly payouts before syncing to Xero"""
    xero_service = XeroPayoutService()
    payouts = xero_service.calculate_monthly_payouts(year, month)
    
    total_real = sum(p.real_payout for p in payouts)
    total_bonus = sum(p.bonus_payout for p in payouts)
    total_all = sum(p.total_payout for p in payouts)
    
    return render_template('admin/payout_preview.html',
        payouts=payouts,
        year=year,
        month=month,
        total_real=total_real,
        total_bonus=total_bonus,
        total_all=total_all
    )


@app.route('/admin/payouts/sync/<int:year>/<int:month>', methods=['POST'])
@login_required
@admin_required
def sync_payouts_to_xero(year, month):
    """Sync monthly payouts to Xero"""
    xero_service = XeroPayoutService()
    results = xero_service.sync_monthly_payouts_to_xero(year, month)
    
    flash(f'Synced {len(results["success"])} payouts to Xero. Total: ${results["total_payout"]:.2f}')
    
    if results['failed']:
        flash(f'Failed to sync {len(results["failed"])} payouts. Check logs.', 'error')
    
    return redirect(url_for('preview_monthly_payouts', year=year, month=month))
```

---

## Monthly Payout Report

### Summary View for Admin

```
┌─────────────────────────────────────────────────────────────────────────┐
│  MONTHLY PAYOUT REPORT - January 2026                                   │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  REVENUE RECEIVED (from Apple/Google)                                   │
│  ─────────────────────────────────────                                  │
│  Total Subscriptions: 1,247                                             │
│  Gross Revenue: $11,223.00 ($9 × 1,247)                                │
│  Platform Fees (30%): -$3,366.90                                        │
│  Net Revenue: $7,856.10                                                 │
│                                                                         │
│  PAYOUTS TO INFLUENCERS                                                 │
│  ─────────────────────────────────────                                  │
│  From Real Subscribers: $6,733.80 (1,247 × $5.40)                      │
│  From Bonus Subscribers: $540.00 (100 × $5.40)                         │
│  Total Influencer Payouts: $7,273.80                                   │
│                                                                         │
│  PLATFORM PROFIT                                                        │
│  ─────────────────────────────────────                                  │
│  Revenue Retained (10%): $1,122.30                                      │
│  Bonus Payouts (admin): -$540.00                                        │
│  Net Platform Profit: $582.30                                           │
│                                                                         │
│  TOP INFLUENCERS BY PAYOUT                                              │
│  ─────────────────────────────────────                                  │
│  1. @stockguru    - 150 real + 20 bonus = $918.00                      │
│  2. @tradequeen   - 120 real + 10 bonus = $702.00                      │
│  3. @bullmarket   - 95 real + 15 bonus = $594.00                       │
│  4. @valueinvestor- 80 real + 5 bonus = $459.00                        │
│  5. @daytraderpro - 75 real + 0 bonus = $405.00                        │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Key Accounting Notes

1. **Real subscriber payouts**: Expense against revenue received from Apple/Google
2. **Bonus subscriber payouts**: Marketing/promotional expense (comes from platform pocket)
3. **Separate line items in Xero**: Keep real and bonus payouts distinct for accounting clarity
4. **Monthly reconciliation**: Match Apple/Google payout reports to Xero records
5. **Tax considerations**: Influencers may need 1099s if US-based and >$600/year

---

*Document maintained by: Development Team*  
*Last updated: January 21, 2026*
