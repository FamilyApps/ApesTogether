# Apes Together

A copy-trading social platform: people follow real traders' and bot-driven portfolios,
get push notifications on every trade, and subscribe to unlock full portfolios. Native
**iOS** (Swift/SwiftUI) and **Android** (Kotlin/Compose) apps on a shared **Python/Flask**
backend deployed serverless on **Vercel**.

> **History:** this started as a Flask web app with Stripe + Twilio SMS. In Jan 2026 it
> pivoted to native mobile apps with in-app purchases and push notifications. Web-era
> planning/setup docs are archived under `_legacy/docs_web_era/`.

---

## 📚 Documentation map (read in this order)

| If you want… | Read |
|---|---|
| **What's left before launch / current status** | `LAUNCH_TODO.md` (the single task tracker) |
| **Onboarding / environment / how to build & deploy** | `DEVIN_HANDOVER.md` |
| **Current system design** | `CURRENT_ARCHITECTURE.md` (+ `ARCHITECTURE_CHANGELOG.md` for history) |
| **Performance %, snapshots, cash tracking** | `docs/PERFORMANCE_AND_SNAPSHOTS.md` |
| **Money: IAP → Xero → influencer payouts → 1099/W-9** | `XERO_PAYOUT_INTEGRATION.md` (+ `docs/XERO_W9_DEPLOY_CHECKLIST.md`) |
| **Per-creator subscription slots** | `docs/PER_CREATOR_SUBSCRIPTION_SLOTS.md` |
| **Store webhooks (Apple ASSN V2 / Google RTDN)** | `docs/IAP_WEBHOOK_SETUP.md` |
| **Environment variables** | `ENV_VARIABLES.md` |
| **When to upgrade infrastructure** | `SCALING_TRIGGERS.md` |
| **Feature specs** | `PENDING_TRADES_DESIGN.md`, `POLL_ADMIN_GUIDE.md` |
| **Store listing / launch copy** | `docs/` (`ASO_STRATEGY.md`, `PLAY_STORE_LISTING_GUIDE.md`, `LAUNCH_PLAYBOOK.md`) |

---

## 🏗 Architecture at a glance

```
iOS (Swift)   Android (Kotlin)
      \             /
       \           /
     Flask API (Vercel serverless, /api/mobile/*)
      |        |          |             |
  Supabase   Upstash    Firebase      Xero
 (Postgres)  (Redis)     (FCM)     (accounting)
```

- **Auth:** Sign in with Apple (iOS) + Google Sign-In via Credential Manager (Android),
  exchanged for a backend JWT at `/api/mobile/auth/token`.
- **Payments:** Apple StoreKit 2 + Google Play Billing (in-app purchases). No Stripe.
- **Notifications:** Firebase Cloud Messaging (FCM). No SMS.
- **Market data:** Alpha Vantage.
- **Domain:** `https://apestogether.ai` · API base `https://apestogether.ai/api/mobile/`.

## 💵 Pricing & revenue split

**Flat $9.00/month** per creator subscription. Under Apple/Google's Small Business
Program rate the split per sub is:

| Recipient | Amount |
|---|---|
| Apple / Google store fee (15%) | $1.35 |
| Influencer / creator payout | $6.50 |
| Platform | $1.15 |

Payouts are **transaction-driven** (booked per verified purchase/renewal), net of
refund clawbacks, and synced to Xero monthly as bills; creators over the $600/yr
threshold need a W-9 on file (payout held until then). See `XERO_PAYOUT_INTEGRATION.md`.

---

## 📁 Repo layout

| Path | What |
|---|---|
| `api/` | Vercel entrypoint (`api/vercel.py` → `api/index.py`) + cron routes |
| `mobile_api.py` | All `/api/mobile/*` endpoints |
| `models.py` | SQLAlchemy models |
| `iap_validation_service.py`, `iap_webhooks.py` | IAP validation + Apple ASSN / Google RTDN webhooks |
| `xero_service.py` | Xero OAuth + bills/credit notes |
| `push_notification_service.py` | FCM |
| `performance_calculator.py`, `cash_tracking.py`, `leaderboard_utils.py` | Snapshots / performance |
| `ios/` | SwiftUI app (built on a Mac; see `ios/README.md`) |
| `android/` | Kotlin/Compose app (built on Windows; see `android/README.md`) |
| `scripts/migrations/` | SQL migrations (run in Supabase) |
| `_legacy/` | Archived web-era code + docs |

## 🚀 Deploy

- **Backend/web:** `git push origin master` → Vercel production deploy. Env vars live in
  the Vercel dashboard (see `ENV_VARIABLES.md`), not in the repo.
- **iOS:** Xcode Archive → App Store Connect → TestFlight / review.
- **Android:** signed AAB → Google Play Console → track promotion (Play App Signing).

Backend, iOS, and Android ship through **three independent pipelines** — see
`DEVIN_HANDOVER.md` §4 for the full breakdown and build gotchas.
