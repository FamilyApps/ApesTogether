# Environment Variables Reference

## Current Status

### ✅ Already Configured
```bash
# Stripe Payment Processing
STRIPE_PUBLIC_KEY=pk_live_...
STRIPE_SECRET_KEY=sk_live_...

# Twilio SMS
TWILIO_ACCOUNT_SID=AC...
TWILIO_AUTH_TOKEN=...
TWILIO_PHONE_NUMBER=+1...

# Alpha Vantage Market Data
ALPHA_VANTAGE_API_KEY=...

# Database
DATABASE_URL=postgresql://...

# Flask
SECRET_KEY=...
```

---

## 🔲 Mobile App Backend (Phase 1)

### Firebase Cloud Messaging (Push Notifications)
```bash
# Option 1: JSON string (recommended for Vercel)
FIREBASE_CREDENTIALS_JSON={"type":"service_account","project_id":"...","private_key":"..."}

# Option 2: File path (for local development)
FIREBASE_CREDENTIALS_PATH=/path/to/firebase-service-account.json
```

**Setup Steps**:
1. Go to https://console.firebase.google.com/
2. Create or select project "apestogether"
3. Project Settings → Service Accounts → Generate new private key
4. Download JSON file
5. For Vercel: Stringify JSON and add as FIREBASE_CREDENTIALS_JSON
6. For local: Set FIREBASE_CREDENTIALS_PATH to file location

### Apple In-App Purchases
```bash
# App Store Connect shared secret
APPLE_SHARED_SECRET=...  # From App Store Connect
APPLE_BUNDLE_ID=com.apestogether.app
```

**Setup Steps**:
1. Go to https://appstoreconnect.apple.com/
2. My Apps → Your App → App Information
3. App-Specific Shared Secret → Generate
4. Copy and add to environment

### Google Play Billing
```bash
# Service account JSON for Google Play Developer API
GOOGLE_PLAY_CREDENTIALS_JSON={"type":"service_account","project_id":"..."}
GOOGLE_PLAY_PACKAGE_NAME=com.apestogether.app
```

**Setup Steps**:
1. Go to https://play.google.com/console/
2. Setup → API access → Create service account
3. Grant "Financial data" permission
4. Download JSON key
5. Stringify and add as GOOGLE_PLAY_CREDENTIALS_JSON

### JWT for Mobile Authentication
```bash
# JWT secret for mobile API tokens (can use existing SECRET_KEY)
JWT_SECRET=...  # Or falls back to SECRET_KEY
```

---

## 🔲 Need to Add (Week 2-3)

### Agent System
```bash
# Controller API Key (generate a secure random key)
CONTROLLER_API_KEY=generate_with_secrets_token_urlsafe_64

# Generate command:
# python -c "import secrets; print(secrets.token_urlsafe(64))"
```

### News Data
```bash
# NewsAPI (sign up at newsapi.org)
NEWSAPI_KEY=...
# Cost: $50/month for 100,000 requests
```

---

## 🔲 Need to Add (Week 3)

### Xero Accounting
```bash
# Xero OAuth Credentials
XERO_CLIENT_ID=...  # From Xero developer portal
XERO_CLIENT_SECRET=...  # From Xero developer portal
XERO_REDIRECT_URI=https://apestogether.ai/xero/callback
XERO_TENANT_ID=...  # After OAuth connection
```

**Setup Steps**:
1. Go to https://developer.xero.com/
2. Create new app
3. Set redirect URI: `https://apestogether.ai/xero/callback`
4. Copy Client ID and Secret
5. Complete OAuth flow to get Tenant ID

---

## Setting Variables in Vercel

### Via CLI
```bash
# Production
vercel env add CONTROLLER_API_KEY production
vercel env add NEWSAPI_KEY production
vercel env add XERO_CLIENT_ID production
vercel env add XERO_CLIENT_SECRET production
```

### Via Dashboard
1. Go to https://vercel.com/dashboard
2. Select project: stock-portfolio-app
3. Settings → Environment Variables
4. Add each variable
5. Select environments: Production
6. Redeploy after adding

---

## Security Best Practices

### ✅ Do
- Use different keys for dev/staging/prod
- Rotate keys quarterly
- Store in password manager
- Never commit to git
- Use `.env` for local development

### ❌ Don't
- Hardcode in source files
- Share keys via email/Slack
- Use same keys across projects
- Expose keys in error messages
- Log sensitive values

---

## Generating Secure Keys

### CONTROLLER_API_KEY
```python
import secrets
print(secrets.token_urlsafe(64))
```

Output example:
```
xJh7_K9mP3nQ2wR8vT1yU4zB5aE6cF7dG8hI9jL0kM1nO2pS3qT4rU5sV6wX7yZ8
```

### JWT_SECRET (if needed)
```python
import secrets
print(secrets.token_hex(32))
```

Output example:
```
a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0u1v2w3x4y5z6a7b8c9d0e1f2
```

---

## Testing Locally

### .env file (local development only)
```bash
# Create .env file (gitignored)
DATABASE_URL=postgresql://localhost/apestogether_dev
FLASK_ENV=development
FLASK_DEBUG=1

# Use same values as production for testing
TWILIO_ACCOUNT_SID=...
TWILIO_AUTH_TOKEN=...
TWILIO_PHONE_NUMBER=...
ALPHA_VANTAGE_API_KEY=...
```

### Load in Flask
```python
from dotenv import load_dotenv
load_dotenv()  # Already in api/index.py
```

---

## Cost Tracking

### By Service

| Service | Variable | Monthly Cost |
|---------|----------|--------------|
| Alpha Vantage | ALPHA_VANTAGE_API_KEY | $100 (existing) |
| Twilio | TWILIO_* | $25-50 (usage) |
| NewsAPI | NEWSAPI_KEY | $50 |
| Xero | XERO_* | $20 (existing) |
| Stripe | STRIPE_* | 2.9% + $0.30/txn |

**Total**: $195-220/month base + usage

---

## Monitoring

### Set Billing Alerts

**Twilio**:
- Alert at $50, $100, $200
- Email: your@email.com

**Vercel**:
- Monitor function invocations
- Set bandwidth alerts

**NewsAPI**:
- Track daily request count
- Alert at 80% of limit

---

## Troubleshooting

### Missing Variable
**Error**: `KeyError: 'CONTROLLER_API_KEY'`
**Fix**: Add variable to Vercel, redeploy

### Wrong Value
**Error**: `Invalid API key`
**Fix**: Verify variable value in Vercel dashboard

### Not Loading
**Error**: `os.environ.get() returns None`
**Fix**: Check variable name spelling, restart server

---

## Quick Reference

### Check Variable in Production
```bash
vercel env pull .env.local
cat .env.local | grep VARIABLE_NAME
```

### Update Variable
```bash
vercel env rm VARIABLE_NAME production
vercel env add VARIABLE_NAME production
```

### List All Variables
```bash
vercel env ls
```

---

## Next Steps

1. **Week 2**: Add `CONTROLLER_API_KEY` and `NEWSAPI_KEY`
2. **Week 3**: Add Xero OAuth credentials
3. **Week 5**: Generate agent JWT secret (if separate from main)
4. **Ongoing**: Rotate keys quarterly

---

**Last Updated**: January 29, 2026
