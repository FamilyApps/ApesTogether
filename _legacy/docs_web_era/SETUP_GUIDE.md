# Stock Portfolio App - Complete Setup Guide

This guide will walk you through setting up all the new subscription tiers, SMS notifications, and leaderboard features.

## Phase 1: Database Setup and Migration

### Step 1: Run Database Migration
```bash
# Navigate to your project directory
cd c:\Users\catal\CascadeProjects\stock-portfolio-app

# Install new dependencies
pip install -r requirements.txt

# Run the app to trigger migration
python app.py
```

### Step 2: Create Database Tables
Visit: `http://localhost:5003/admin/run-migration`
- This will create all the new tables (subscription_tier, trade_limit, sms_notification, stock_info, leaderboard_entry)

### Step 3: Populate Subscription Tiers
```bash
python populate_subscription_tiers.py
```
**IMPORTANT**: Before running this, you need to create Stripe products first (see Phase 2).

## Phase 2: Stripe Setup

### Step 1: Create Stripe Products
Log into your Stripe Dashboard and create these 5 products:

1. **Light Tier - $8/month**
   - Product Name: "Light Portfolio Subscription"
   - Price: $8.00 USD/month
   - Copy the Price ID (starts with `price_`)

2. **Standard Tier - $12/month**
   - Product Name: "Standard Portfolio Subscription" 
   - Price: $12.00 USD/month
   - Copy the Price ID

3. **Active Tier - $20/month**
   - Product Name: "Active Portfolio Subscription"
   - Price: $20.00 USD/month
   - Copy the Price ID

4. **Pro Tier - $30/month**
   - Product Name: "Pro Portfolio Subscription"
   - Price: $30.00 USD/month
   - Copy the Price ID

5. **Elite Tier - $50/month**
   - Product Name: "Elite Portfolio Subscription"
   - Price: $50.00 USD/month
   - Copy the Price ID

### Step 2: Update Subscription Tiers Script
Edit `populate_subscription_tiers.py` and replace the placeholder Stripe price IDs:
```python
'stripe_price_id': 'price_YOUR_ACTUAL_STRIPE_PRICE_ID_HERE'
```

### Step 3: Run Subscription Tiers Population
```bash
python populate_subscription_tiers.py
```

## Phase 3: Twilio SMS Setup (Optional)

### Step 1: Create Twilio Account
1. Sign up at https://www.twilio.com/
2. Get a phone number for SMS
3. Note your Account SID, Auth Token, and Phone Number

### Step 2: Add Twilio Credentials to Environment
Add to your `.env` file:
```
TWILIO_ACCOUNT_SID=your_account_sid_here
TWILIO_AUTH_TOKEN=your_auth_token_here
TWILIO_PHONE_NUMBER=+1234567890
```

### Step 3: Install Twilio SDK
```bash
pip install twilio==8.10.0
```

### Step 4: Update SMS Utils
Edit `sms_utils.py` and uncomment the real Twilio implementation:
```python
# Uncomment these lines in send_sms() function:
from twilio.rest import Client
client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
message = client.messages.create(
    body=message,
    from_=TWILIO_PHONE_NUMBER,
    to=phone_number
)
return True, message.sid, None
```

## Phase 4: Testing and Debugging

### Step 1: Access Debug Dashboard
Visit: `http://localhost:5003/debug/`

This provides access to all debugging routes:
- `/debug/subscription-tiers` - View tier data
- `/debug/user-tier-info` - Check your tier status
- `/debug/simulate-trades` - Test tier changes
- `/debug/sms-settings` - Test SMS functionality
- `/debug/leaderboard-data` - View leaderboard calculations

### Step 2: Test Dynamic Pricing
1. Go to `/debug/simulate-trades`
2. Create 5+ trades to test tier upgrades
3. Check `/debug/user-tier-info` to see tier changes

### Step 3: Test SMS Features
1. Go to `/sms/settings`
2. Add your phone number
3. Verify with SMS code
4. Make a trade to test notifications

### Step 4: Test Leaderboard
1. Go to `/leaderboard/`
2. View performance rankings
3. Test "Subscribe for $X" buttons
4. Use `/debug/calculate-performance` to populate test data

## Phase 5: Production Deployment

### Step 1: Environment Variables
Ensure these are set in production:
```
STRIPE_PUBLIC_KEY=pk_live_...
STRIPE_SECRET_KEY=sk_live_...
STRIPE_WEBHOOK_SECRET=whsec_...
TWILIO_ACCOUNT_SID=AC...
TWILIO_AUTH_TOKEN=...
TWILIO_PHONE_NUMBER=+1...
ALPHA_VANTAGE_API_KEY=... (optional, for real market cap data)
```

### Step 2: Database Migration in Production
Run the migration endpoint once in production:
`https://yourdomain.com/admin/run-migration`

### Step 3: Populate Subscription Tiers in Production
Upload and run `populate_subscription_tiers.py` with production Stripe price IDs.

## Troubleshooting

### Common Issues

1. **Import Errors**
   - Make sure all new files are uploaded
   - Check that blueprints are registered in `app.py`

2. **Database Errors**
   - Run the migration endpoint
   - Check that all new models are imported in `app.py`

3. **Stripe Errors**
   - Verify price IDs are correct
   - Check that products exist in your Stripe account

4. **SMS Not Working**
   - SMS will work in mock mode without Twilio credentials
   - Check Twilio credentials are correct
   - Verify phone number format (+1234567890)

### Debug Routes for Troubleshooting

- `/debug/database-status` - Check table counts
- `/debug/user-tier-info` - Check pricing logic
- `/debug/subscription-tiers` - Verify tier data
- `/debug/reset-user-data` - Reset test data

## Key Features Implemented

### ✅ Dynamic Subscription Pricing
- 5-tier system based on trading activity
- Automatic price updates based on 7-day average
- Trade limits per tier

### ✅ SMS Notifications
- Phone verification flow
- Trade confirmations
- Subscriber notifications
- Mock mode for testing

### ✅ Enhanced Leaderboard
- Performance metrics by time period
- Market cap classifications
- "Subscribe for $X" buttons with dynamic pricing
- Small cap vs large cap portfolio breakdowns

### ✅ Comprehensive Debugging
- Debug dashboard with all test routes
- Trade simulation
- SMS testing
- Database status checks

## Next Steps

1. **Create Stripe Products** - This is the critical first step
2. **Run Database Migration** - Set up new tables
3. **Populate Subscription Tiers** - With real Stripe price IDs
4. **Test Dynamic Pricing** - Use debug routes
5. **Set up Twilio** - For real SMS (optional)
6. **Deploy to Production** - With proper environment variables

The system is designed to work in stages - you can test dynamic pricing and leaderboards immediately, then add SMS functionality later when ready.
