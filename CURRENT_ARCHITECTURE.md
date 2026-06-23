# Apes Together - Current Architecture

**Last Updated:** June 22, 2026 (Session 18)  
**Status:** Pre-launch — iOS + Android feature-complete; money/store config in progress. See `LAUNCH_TODO.md` for live status.

---

## Quick Reference

| Question | Answer |
|----------|--------|
| What platform? | Native iOS + Android apps |
| How do users get notified? | Push notifications (Firebase FCM) |
| How do users pay? | Apple/Google In-App Purchase |
| What's the price? | $9/month flat, per creator |
| Who gets paid? (per $9 sub) | Influencer $6.50 · platform $1.15 · store $1.35 (15%, Small Business rate) |

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

**Single Price: $9/month**, charged **per creator** (each follow is its own subscription
via the slot model — see `docs/PER_CREATOR_SUBSCRIPTION_SLOTS.md`).

Revenue split per sub, under Apple/Google's **Small Business Program** rate:

| Recipient | Amount | Percent |
|-----------|--------|---------|
| Apple/Google store fee | $1.35 | 15% |
| Influencer / creator | $6.50 | — |
| Platform | $1.15 | — |

(Above $1M annual revenue the store fee rises to 30%; the split recomputes from the
constants in `models.py::AdminSubscription`.) Payouts are **transaction-driven** (per
verified purchase/renewal), net of refund clawbacks, synced to Xero monthly as bills;
creators past $600/yr require a W-9 on file. See `XERO_PAYOUT_INTEGRATION.md`.

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
APPLE_BUNDLE_ID=com.apestogether.ApesTogether  # iOS bundle ID (NOT com.apestogether.app — that's the Android package)
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

| Phase | Status |
|-------|--------|
| 1. Backend Prep | ✅ Complete |
| 2. iOS App | ✅ Feature-complete (TestFlight) |
| 3. Android App | ✅ Feature-complete (Play internal testing) |
| 4. Money/store config + E2E tests | 🔄 In progress |
| 5. Launch | ⏳ Pending — see `LAUNCH_TODO.md` |

---

## Related Documents

- `LAUNCH_TODO.md` — single task tracker / current status
- `DEVIN_HANDOVER.md` — onboarding, environment, build & deploy
- `docs/PERFORMANCE_AND_SNAPSHOTS.md` — performance %, snapshots, cash tracking
- `XERO_PAYOUT_INTEGRATION.md` — IAP → Xero payouts → 1099/W-9
- `docs/PER_CREATOR_SUBSCRIPTION_SLOTS.md` — per-creator subscription slots
- `SCALING_TRIGGERS.md` — when to upgrade infrastructure
- `ARCHITECTURE_CHANGELOG.md` — history of architecture changes
- *(archived)* `_legacy/docs_web_era/MOBILE_ARCHITECTURE_PLAN.md` — original Jan-2026 pivot plan
