# Architecture Changelog

## January 21, 2026 - Mobile App Pivot

### Summary
Complete pivot from web app + SMS to native iOS/Android apps with push notifications.

### What Changed

| Component | Before (Web Era) | After (Mobile Era) |
|-----------|------------------|-------------------|
| **Client** | Web app (Flask templates) | Native iOS (Swift) + Android (Kotlin) |
| **Notifications** | Twilio SMS ($0.0079/msg) | Firebase Cloud Messaging (free) |
| **Payments** | Stripe | Apple StoreKit 2 + Google Play Billing |
| **Auth** | Google OAuth (web) | Sign in with Apple + Google Sign-In |
| **API** | Session-based | JWT tokens |

### New Files (Phase 1 - Backend)

| File | Purpose |
|------|---------|
| `push_notification_service.py` | Firebase FCM integration for iOS/Android |
| `iap_validation_service.py` | Apple/Google receipt verification |
| `api/mobile_api.py` | REST endpoints for mobile apps |
| `tests/test_phase1_mobile.py` | Unit tests for mobile backend |

### Updated Models

| Model | Changes |
|-------|---------|
| `DeviceToken` | NEW - Stores FCM/APNs tokens per device |
| `InAppPurchase` | NEW - Tracks Apple/Google purchases |
| `PushNotificationLog` | NEW - Audit trail for notifications |
| `XeroPayoutRecord` | NEW - Monthly influencer payout tracking |
| `MobileSubscription` | NEW - Links subscribers to portfolios |
| `AdminSubscription` | UPDATED - Flat $9 pricing, 60% influencer payout |

### Archived Files

Moved to `_legacy/` folder:
- `sms_routes.py`, `sms_utils.py`, `trading_sms.py` → `_legacy/sms_twilio/`
- 50+ debug/analysis docs → `_legacy/docs_debug_history/`
- 30+ one-time scripts → `_legacy/scripts_one_time/`

### Pricing Model

**Flat $9/month** for all subscriptions:
- 30% ($2.70) → Apple/Google
- 60% ($5.40) → Influencer
- 10% ($0.90) → Platform

### Environment Variables Required

```bash
# Mobile Auth
JWT_SECRET=your-jwt-secret-key

# Firebase (for push notifications)
FIREBASE_CREDENTIALS_JSON={"type":"service_account",...}

# Apple IAP (Phase 2)
APPLE_SHARED_SECRET=your-app-store-shared-secret
APPLE_BUNDLE_ID=com.apestogether.app

# Google Play (Phase 3)
GOOGLE_PLAY_CREDENTIALS_JSON={"type":"service_account",...}
GOOGLE_PLAY_PACKAGE_NAME=com.apestogether.app
```

### Database Migration

Run after deployment:
```
GET /admin/create-mobile-tables
```

Creates: `device_token`, `in_app_purchase`, `push_notification_log`, `xero_payout_record`, `mobile_subscription`

---

## Previous Architecture (Sept 2025 - Jan 2026)

### Web App Era
- Flask web application with server-side rendering
- Google OAuth for authentication
- Twilio for SMS trade alerts
- Stripe for subscription payments
- Session-based authentication

### Key Learnings Carried Forward
1. Modified Dietz performance calculation (validated by Grok)
2. Leaderboard caching strategy
3. Chart data generation with timezone handling
4. Alpha Vantage rate limiting (150 req/min on Premium)
5. Supabase connection pooling requirements

---

## Roadmap

| Phase | Timeline | Status |
|-------|----------|--------|
| Phase 1: Backend Prep | Week 1-2 | ✅ Complete |
| Phase 2: iOS App | Week 3-6 | 🔜 Next |
| Phase 3: Android App | Week 7-10 | Pending |
| Phase 4: Integration | Week 11-12 | Pending |
| Phase 5: Launch | Week 13-14 | Pending |

See `IMPLEMENTATION_PHASES.md` for detailed timeline.
