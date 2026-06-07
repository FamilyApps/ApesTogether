# Production Deployment Checklist for apestogether.ai

## Files to Upload to Production Server

### New Python Files:
- `subscription_utils.py`
- `sms_utils.py`
- `sms_routes.py`
- `debug_routes.py`
- `leaderboard_utils.py`
- `leaderboard_routes.py`
- `populate_subscription_tiers.py` (with your Stripe price IDs)

### Updated Files:
- `models.py` (updated with new database models)
- `app.py` (updated with new imports and routes)
- `requirements.txt` (updated with twilio and alembic)

### New Template Files:
- `templates/sms_settings.html`
- `templates/leaderboard.html`

### Migration File:
- `migrations/versions/20250907_add_subscription_tiers_and_features.py`

## Step 1: Upload Files
Use your preferred method (FTP, SSH, Git, etc.) to upload all the above files to your apestogether.ai server.

## Step 2: Install Dependencies
SSH into your production server and run:
```bash
cd /path/to/your/app
pip install -r requirements.txt
```

The new dependencies being installed are:
- `twilio==8.10.0`
- `alembic==1.12.1`

## Verification Commands
After uploading, you can verify files are present:
```bash
ls -la subscription_utils.py sms_utils.py debug_routes.py
ls -la templates/leaderboard.html templates/sms_settings.html
```

## Ready for Next Steps
Once files are uploaded and dependencies installed:
1. Visit https://apestogether.ai/admin/run-migration
2. Run `python populate_subscription_tiers.py`
3. Test at https://apestogether.ai/leaderboard/
