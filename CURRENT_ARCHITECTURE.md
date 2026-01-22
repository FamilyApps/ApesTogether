# Apes Together - Current Architecture

**Last Updated:** January 21, 2026  
**Status:** Mobile App Phase 1 Complete

---

## Quick Reference

| Question | Answer |
|----------|--------|
| What platform? | Native iOS + Android apps |
| How do users get notified? | Push notifications (Firebase FCM) |
| How do users pay? | Apple/Google In-App Purchase |
| What's the price? | $9/month flat |
| Who gets paid? | 60% influencer, 10% platform, 30% store |

---

## System Overview

```
┌─────────────────┐    ┌─────────────────┐
│   iOS App       │    │  Android App    │
│   (Swift)       │    │  (Kotlin)       │
└────────┬────────┘    └────────┬────────┘
         │                      │
         └──────────┬───────────┘
                    │
                    ▼
         ┌──────────────────────┐
         │   Flask API          │
         │   (Vercel Serverless)│
         └──────────┬───────────┘
                    │
    ┌───────────────┼───────────────┐
    │               │               │
    ▼               ▼               ▼
┌────────┐   ┌──────────┐   ┌──────────┐
│Supabase│   │  Redis   │   │ Firebase │
│ (Postgres)│ │ (Upstash)│   │  (FCM)   │
└────────┘   └──────────┘   └──────────┘
```

---

## Key Files (Mobile Backend)

| File | Purpose |
|------|---------|
| `api/mobile_api.py` | REST endpoints for mobile apps |
| `push_notification_service.py` | Firebase push notifications |
| `iap_validation_service.py` | Apple/Google receipt validation |
| `models.py` | Database models (including new mobile tables) |

---

## Mobile API Endpoints

### Authentication
- `POST /api/mobile/auth/token` - Exchange OAuth for JWT
- `POST /api/mobile/auth/refresh` - Refresh JWT

### Device Management
- `POST /api/mobile/device/register` - Register FCM token
- `DELETE /api/mobile/device/unregister` - Remove token

### Subscriptions
- `POST /api/mobile/purchase/validate` - Validate IAP receipt
- `GET /api/mobile/subscriptions` - Get user's subscriptions
- `DELETE /api/mobile/unsubscribe/<id>` - Cancel subscription

### Portfolio Data
- `GET /api/mobile/portfolio/<slug>` - Get portfolio (full if subscribed)
- `GET /api/mobile/leaderboard` - Public leaderboard

### Settings
- `PUT /api/mobile/notifications/settings` - Toggle push notifications

---

## Database Models (New)

```
DeviceToken          - FCM/APNs tokens per user device
InAppPurchase        - Apple/Google purchase records
MobileSubscription   - Subscriber ↔ Portfolio owner links
PushNotificationLog  - Notification audit trail
XeroPayoutRecord     - Monthly influencer payouts
```

---

## Pricing Structure

**Single Price: $9/month**

| Recipient | Amount | Percent |
|-----------|--------|---------|
| Apple/Google | $2.70 | 30% |
| Influencer | $5.40 | 60% |
| Platform | $0.90 | 10% |

---

## Infrastructure

| Service | Plan | Cost/Month |
|---------|------|------------|
| Vercel | Pro | $20 |
| Supabase | Pro | $25 |
| Upstash Redis | Pro | $10 |
| Alpha Vantage | Premium | $99.99 |
| Firebase FCM | Free | $0 |
| **Total** | | **~$155** |

---

## Environment Variables

### Required Now
```bash
DATABASE_URL=postgresql://...
REDIS_URL=redis://...
JWT_SECRET=your-secret
ALPHAVANTAGE_API_KEY=your-key
```

### Required for Phase 2 (iOS)
```bash
FIREBASE_CREDENTIALS_JSON={"type":"service_account",...}
APPLE_SHARED_SECRET=from-app-store-connect
APPLE_BUNDLE_ID=com.apestogether.app
```

### Required for Phase 3 (Android)
```bash
GOOGLE_PLAY_CREDENTIALS_JSON={"type":"service_account",...}
GOOGLE_PLAY_PACKAGE_NAME=com.apestogether.app
```

---

## What's NOT Current

The following are **DEPRECATED** and moved to `_legacy/`:

- ❌ SMS notifications (Twilio)
- ❌ Web-only subscription flow
- ❌ Stripe payments
- ❌ Session-based auth for mobile

See `_legacy/README.md` for details.

---

## Development Phases

| Phase | Weeks | Status |
|-------|-------|--------|
| 1. Backend Prep | 1-2 | ✅ Complete |
| 2. iOS App | 3-6 | 🔜 Up Next |
| 3. Android App | 7-10 | Pending |
| 4. Integration | 11-12 | Pending |
| 5. Launch | 13-14 | Pending |

---

## Related Documents

- `IMPLEMENTATION_PHASES.md` - Detailed 14-week plan
- `MOBILE_ARCHITECTURE_PLAN.md` - Full technical architecture
- `SCALING_TRIGGERS.md` - When to upgrade infrastructure
- `XERO_PAYOUT_INTEGRATION.md` - Influencer payout tracking
- `ARCHITECTURE_CHANGELOG.md` - History of architecture changes
