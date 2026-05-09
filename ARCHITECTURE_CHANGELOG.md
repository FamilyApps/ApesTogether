# Architecture Changelog

## May 9, 2026 — Display Name Field + Schema-Migration Lessons

### Summary
Added `display_name VARCHAR(80)` column to `user` to support public-facing names containing spaces, apostrophes, uppercase, and other characters that the `username` validation regex blocks. The `username` column remains the unique URL-safe handle; `display_name` is what we render to other users in leaderboards / portfolio headers / share cards.

### Schema change
- `user.display_name VARCHAR(80) NULL` — nullable, falls back to `username` via `User.public_name` property
- iOS Codable models gained optional `displayName: String?` + `publicName` computed helper
- 8 backend serializers + 6 Swift views updated to render `public_name` / `publicName` instead of raw username for display

### Lessons learned about Supabase + Vercel migrations

1. **Migrate the schema BEFORE deploying the model change.** Today's outage: deployed a SQLAlchemy model declaring `display_name` while the DB column didn't yet exist. SQLAlchemy ORM SELECTs all mapped columns by default, so every `User.query.first()` started 500'ing with `psycopg2.errors.UndefinedColumn` until the column was added. **Always run the ALTER first, verify it stuck, then push the code that references it.**

2. **Never run schema mutations from a Vercel pooled endpoint.** Vercel's pooled connection to Supabase enforces a short `statement_timeout` (~5–15s). `ALTER TABLE ... ADD COLUMN` requires `ACCESS EXCLUSIVE`, which waits behind any in-flight shared lock. Under live traffic, it consistently gets killed by `QueryCanceled`. Use one of:
   - **Supabase SQL Editor** (web UI; direct connection, no pooler-imposed timeout)
   - **`psql` against the direct port (5432)** — not the pooler port (6543)
   - **`migrations/20260509_add_user_display_name.py`** style runner: direct unpooled `create_engine` with `connect_args={"options": "-c statement_timeout=30000 -c lock_timeout=2000"}`, AUTOCOMMIT isolation, retry 3× on lock contention

3. **`ALTER TABLE ... ADD COLUMN IF NOT EXISTS` is not free.** It still acquires `ACCESS EXCLUSIVE` even when the column exists and the operation is a no-op. If a serverless endpoint needs to be schema-migration-aware, gate the ALTER on an `information_schema.columns` pre-check (shared-lock SELECT, fast under load) and skip the ALTER when the column already exists. See `mobile_api.py admin_set_display_name` for the pattern.

### New endpoint
`POST /api/mobile/admin/users/set-display-name` (admin 2FA) — idempotent batch update of display_name for any number of users. Pre-checks column existence via `information_schema`; only ALTERs if missing; UPDATEs by id.

---

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
