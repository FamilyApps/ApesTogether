# Production Migration Guide

## Direct Production Deployment (Skip Local Testing)

If you want to deploy directly to production, here's the step-by-step process:

### Prerequisites
1. **Alpha Vantage API Key** added to production environment variables
2. **5 Stripe Products** created with price IDs
3. **Updated `populate_subscription_tiers.py`** with real Stripe price IDs

### Production Deployment Steps

#### Step 1: Deploy New Code to Production
Upload all the new files to your production server:
- `models.py` (updated with new models)
- `subscription_utils.py`
- `sms_utils.py` 
- `sms_routes.py`
- `debug_routes.py`
- `leaderboard_utils.py`
- `leaderboard_routes.py`
- `populate_subscription_tiers.py` (with real Stripe price IDs)
- `requirements.txt` (updated)
- All new template files

#### Step 2: Install New Dependencies on Production
```bash
pip install -r requirements.txt
```

#### Step 3: Set Production Environment Variables
Add these to your production environment:
```
ALPHA_VANTAGE_API_KEY=your_real_api_key
TWILIO_ACCOUNT_SID=your_twilio_sid (optional)
TWILIO_AUTH_TOKEN=your_twilio_token (optional)  
TWILIO_PHONE_NUMBER=your_twilio_number (optional)
```

#### Step 4: Run Production Migration
Visit your production migration endpoint:
```
https://yourdomain.com/admin/run-migration
```

This will create the new database tables:
- `subscription_tier`
- `trade_limit` 
- `sms_notification`
- `stock_info`
- `leaderboard_entry`

#### Step 5: Populate Subscription Tiers on Production
Upload and run the subscription tiers script on your production server:
```bash
python populate_subscription_tiers.py
```

#### Step 6: Test Production Features
- Visit `https://yourdomain.com/leaderboard/`
- Test dynamic pricing by making trades
- Check `https://yourdomain.com/debug/` for debugging

### Production Migration Safety Notes

1. **Database Backup**: Always backup your production database before migration
2. **Downtime**: The migration should be quick (seconds), but plan for brief downtime
3. **Rollback Plan**: Keep the old code version ready in case rollback is needed
4. **User Impact**: Existing users won't be affected - new features are additive

### What Happens to Existing Users

- **Existing subscriptions**: Continue working normally
- **User accounts**: Unchanged
- **Portfolio data**: Unchanged  
- **New features**: Available immediately after migration

### Monitoring After Deployment

Check these endpoints post-deployment:
- `/debug/database-status` - Verify new tables exist
- `/debug/subscription-tiers` - Verify tier data loaded
- `/leaderboard/` - Test leaderboard functionality
- Make a test trade to verify dynamic pricing

### If Something Goes Wrong

1. **Check logs** for error messages
2. **Visit `/debug/database-status`** to see what tables exist
3. **Rollback** to previous code version if needed
4. **Contact support** if database issues occur

The migration is designed to be safe and additive - it only adds new tables and features without modifying existing data.
