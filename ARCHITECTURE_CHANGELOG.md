# Architecture Changelog

## May 9, 2026 (evening) — Phantom Chart-Drop Bug: Snapshot Timing Inconsistency

### Symptom
Bot accounts (panther2585, fund.finance2024, apex1575, panther3765, marblethehill72, etc.) showed phantom drops on the daily portfolio chart on days where bot trades happened near or after market close (~16:00–16:09 ET), followed by a recovery the next day. Visible as 7%–12% one-day swings followed by inverse moves.

### Root cause
Two pieces of the snapshot pipeline disagreed on **which day's EOD snapshot an after-close trade should belong to**:

1. **EOD market-close cron** (`api/index.py:5277` → `cash_tracking.calculate_portfolio_value_with_cash`): for `today_et`, computes `stock_value` from **live `Stock` table** (post-trade state) and `cash_proceeds` via `func.date(Transaction.timestamp) <= today_et` (no time-of-day cutoff). Both reflect "all trades of date D applied" = **Option B**.

2. **`/admin/cash-tracking/full-rebuild`** (`admin_cash_tracking.py:_snapshot_effective_date`): used a 16:00 ET cutoff — trades at or after 16:00 ET on date D rolled into D+1's snapshot. **Option A.**

Whenever full-rebuild ran (we run it routinely to fix earlier corruption / drift), it overwrote `cash_proceeds` on every daily snapshot with Option A semantics while leaving `stock_value` (Option B, written by the EOD cron) untouched. The result: snapshots whose `cash_proceeds` and `stock_value` reflected different points in time, producing a $X drop on the trade day and a $X recovery the next day on the chart.

### Diagnostic added
- `GET /admin/audit-snapshot-cash-drift` — walks every PortfolioSnapshot for every user and compares `cash_proceeds` to a chronological transaction replay (Option B). Flags drift; supports `?fix=true` to repair in place.
- `GET /admin/audit-snapshot-max-cash-drift` — same idea for `max_cash_deployed`.

⚠️ **Audit caveat**: the audit's Option B replay can't distinguish (a) real bugs (stock rebuilt with after-close trades, cash not refreshed) from (b) snapshots that correctly reflect pre-after-close state on **both** sides (after-close BUY trades with both cash and stock excluded, smoothly picked up the next day). For (b), drift is reported but the snapshot is internally consistent and should NOT be "fixed". Triage manually by checking the next day's snapshot for smooth pickup.

### Fix
`admin_cash_tracking.py:_snapshot_effective_date` now uses **20:05 UTC** as the cutoff — matching the actual EOD market-close cron schedule (`5 20 * * 1-5` in `vercel.json`). Trades < 20:05 UTC apply to that day's snapshot (the cron at 20:05 UTC saw them); trades >= 20:05 UTC roll to the next day's snapshot. UTC anchoring handles DST automatically.

This produces snapshots that **match what the EOD cron actually wrote** — both stock_value (from live `Stock` holdings at 20:05 UTC) and cash_proceeds reflect the same point in time, so the chart is smooth on both after-close-sell days (panther2585 pattern) and after-close-buy days (fund.finance2024 pattern).

The previous 16:00 ET cutoff was 5 minutes too early. It misclassified trades at 16:00-16:04 ET (which the 16:05 ET cron DID see) as next-day trades, causing the cash/stock mismatch.

Intraday snapshot logic (timestamp-granular replay via `txn_timeline`) is unchanged — that's correct as-is.

### Lessons
1. **Pick one snapshot-timing semantic and stick with it across every writer.** When two code paths write the same column with different rules, they corrupt each other every time both run.
2. **Anchor cutoffs to the actual cron schedule (in UTC), not to a market-time approximation.** The EOD cron fires at 20:05 UTC. Using 16:00 ET (which equals 20:00 UTC in EDT or 21:00 UTC in EST) introduces a 5–60 minute discrepancy depending on DST.
3. **A drift detector that only checks `User.cash_proceeds` is insufficient.** It missed all of these snapshots because the User-level state was correct — it was only historical PortfolioSnapshot rows that were stale. The new audit endpoints close that gap.
4. **Naive Option-B replays (no time-of-day cutoff) misclassify after-close trades in the OTHER direction.** Option B says "all trades on date D apply to D" — but the EOD cron at 16:05 ET physically can't have seen a trade at 16:09 ET. So Option B replay would put a trade in D's snapshot that the cron never saw, breaking consistency on after-close-buy days.

---

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
