# Pre-Launch Security Audit — Backend

**Date:** 2026-06-22 (Session 18) · **Auditor:** Cascade · **Scope:** Flask backend deployed on Vercel (`api/vercel.py` → `api/index.py` + `mobile_api.py`, `iap_webhooks.py`, `xero_service.py`, `admin_cash_tracking.py`, `admin_*_routes.py`). Native clients and store-console config are out of scope here.

This is the first dedicated pass requested in `LAUNCH_TODO.md §1` (the USER flagged it as never having been done). It targets the items they named — **SQL injection**, **authorization/IDOR**, **webhook authenticity**, **secrets**, and **rate-limiting/abuse**.

---

## Verdict

**No critical or high-severity vulnerabilities found.** The two classes the USER worried about most — **SQL injection** and **IDOR/broken authorization** — are **clean**: raw SQL is uniformly parameterized, and per-user resources are scoped to the authenticated `g.user_id`. The real gaps are **operational hardening**, chiefly that the rate-limiter is in-memory (ineffective on Vercel's ephemeral/concurrent instances) and that the login and Google webhook endpoints lack throttling / push-token verification. None of these block launch, but **S-1 and S-2 below should be fixed pre-launch.**

| ID | Area | Severity | Status |
|----|------|----------|--------|
| S-1 | Rate-limiting is in-memory (no-op on serverless) + absent on `/auth/token` | **Medium** | Open |
| S-2 | Google RTDN webhook does not verify the Pub/Sub OIDC push token | **Low–Med** | Open |
| S-3 | Legacy `app.py` runs Flask `debug=True` (NOT the deployed entrypoint) | **Low / Info** | Open |
| S-4 | No dependency-vulnerability scan in CI (`pip-audit`/Dependabot) | **Low / Process** | Open |
| S-5 | No centralized request-body size / input-validation guard | **Low** | Open |

---

## What was verified CLEAN ✅

- **SQL / ORM injection — none.** Every raw query goes through `db.session.execute(text("... :param ..."), {params})` with bind parameters (e.g. `admin_cash_tracking.py`, `admin_phase_*_routes.py`, the `column_exists` helper at `api/index.py:7074-7079`). The scan for `text(f"…")`, `execute(f"…")`, `.format(`/`%`-built SQL, and string concatenation into `execute()`/`text()` found **only** the DDL helper at `api/index.py:7105-7140` (`ALTER TABLE "{table}" ADD COLUMN {col} {col_type}`) — and its `table`/`col`/`col_type` come **exclusively** from the hardcoded `column_migrations` list (the only user input, `step`, is validated to `1–6`/`all`). It is additionally `@admin_2fa_required`. **Not exploitable.**
- **IDOR / authorization — properly scoped.** Sampled every per-user mutation that takes an ID from the URL:
  - `DELETE /unsubscribe/<subscription_id>` → `MobileSubscription.query.filter_by(id=…, subscriber_id=g.user_id)` (`mobile_api.py:879`).
  - `POST|DELETE /subscriptions/<sub_id>/scale` → `filter_by(id=sub_id, subscriber_id=g.user_id, status='active')` (`mobile_api.py:2109`, `:2147`).
  - `DELETE /portfolio/pending-trades/<pending_id>` → `qt.user_id != g.user_id → 404`, and only while `status=='queued'` (`mobile_api.py:3584-3588`).
- **Route auth coverage.** 90 of 97 `mobile_api` routes carry an auth decorator (`@require_admin_2fa` ×45, `@require_auth` ×30, `@require_admin_or_cron` ×8, `@require_cron_secret` ×7). The 7 with no decorator are all intentional: `/health`, `/leaderboard` (public + `@rate_limit`), `/auth/token` (login), the two store webhooks (authenticated by signature — see below), and `/admin/xero/{connect,callback}` (gated by `_is_admin_session()` which requires `admin_email` **and** `admin_2fa_verified`, plus an OAuth `state` CSRF check on the callback — `mobile_api.py:8204`, `:8226`, `:3605-3611`).
- **JWT auth.** `require_auth` verifies HS256 with `JWT_SECRET`, rejects missing/expired/invalid tokens, and reads identity only from the verified payload (`mobile_api.py:185-218`). Tokens are never trusted unsigned.
- **OAuth login.** `STRICT_OAUTH_VERIFICATION=enforce` is live (verified via probe in a prior session) — Google/Apple ID tokens are signature-verified with the correct audience before a JWT is issued.
- **Apple webhook authenticity.** `POST /webhooks/apple/notifications` verifies Apple's `x5c` JWS chain and pins `certs/AppleRootCA-G3.cer`; a bad signature → `400 invalid_signature`, never a state change (`mobile_api.py:903-930`, `iap_webhooks.py`).
- **Admin API.** Admin endpoints require `X-Admin-Key` (`ADMIN_API_KEY`) **and** TOTP (`ADMIN_TOTP_SECRET`) via `@require_admin_2fa`.
- **Secrets.** All secrets read from `os.environ` (`JWT_SECRET`, `APPLE_SHARED_SECRET`, `GOOGLE_PLAY_CREDENTIALS_JSON`, `XERO_*`, `ADMIN_*`). No hardcoded keys/tokens found in the scanned source.
- **CORS.** No wildcard `Access-Control-Allow-Origin` / `CORS(app, origins='*')` (correct — native clients don't need permissive CORS).
- **Prod debug.** Deployed entrypoint is `api/vercel.py` per `vercel.json`; it does not run with the Werkzeug debugger. (See S-3 for the legacy file.)

---

## Findings & remediation

### S-1 — Rate-limiting is in-memory; `/auth/token` is unthrottled · **Medium**
`rate_limit(max_requests, per_seconds)` (`mobile_api.py:~150`) uses a **process-local sliding-window dict**. On Vercel, requests are served by **ephemeral, horizontally-scaled instances**, so each instance keeps its own counter and counters reset on cold start — an attacker spread across instances (or hitting cold lambdas) effectively bypasses it. Additionally, `POST /auth/token` (public login / token-exchange, which performs outbound ID-token verification) has **no** `@rate_limit`.

**Impact:** Limited brute-force protection is largely illusory under load; `/auth/token` and `/leaderboard` are abusable for DoS / cost amplification.

**Fix:**
1. Back the limiter with a **shared store** — Postgres (a small `rate_limit_hit` table or `pg_advisory`), or Upstash/Vercel KV (Redis). Keep the same decorator API; swap the backend.
2. Add throttling to `/auth/token` (e.g. `@rate_limit(10, 60)` keyed by IP) once the shared store is in place.
3. Consider Vercel's platform-level WAF / rate-limit rules as defense-in-depth for the public routes.

### S-2 — Google RTDN webhook lacks Pub/Sub OIDC verification · **Low–Medium**
`POST /webhooks/google/rtdn` (`mobile_api.py:933-952`) is public and does not verify the Cloud Pub/Sub push **OIDC token** (the `Authorization: Bearer <jwt>` Google attaches, issuer `accounts.google.com`, audience = your push-subscription audience). It is *safe against state forgery* because `handle_google_rtdn` re-fetches authoritative state from the Play Developer API before mutating — a forged `purchaseToken` simply fails validation. But the open endpoint can be spammed to trigger outbound Play API calls (amplification / quota burn).

**Fix (pick one, ideally both):**
1. Configure the Pub/Sub push subscription with an **OIDC service-account token** and verify it server-side (`google.oauth2.id_token.verify_oauth2_token`, check `aud`/`iss`/`email`).
2. Add a **shared-secret query token** to the push URL (`…/rtdn?token=<random>`) and reject mismatches — quick stop-gap. *(Apple's webhook already authenticates via JWS, so this gap is Google-only.)*

### S-3 — Legacy `app.py` uses `debug=True` · **Low / Informational**
`app.py:813` calls `app.run(host='0.0.0.0', port=5003, debug=True)`. This is the **legacy local web entrypoint**, not the Vercel deployment (`vercel.json` → `api/vercel.py`), so the Werkzeug interactive debugger (RCE if exposed) is **not** live in prod. Still: guard or remove it to prevent accidental exposure.

**Fix:** Gate behind `debug=os.environ.get('FLASK_DEBUG')=='1'`, or delete the legacy runner if `app.py` is dead.

### S-4 — No dependency-vulnerability scanning · **Low / Process**
No `pip-audit`/Dependabot/CodeQL in CI. Transitive CVEs (e.g. in `pyjwt`, `cryptography`, `requests`, `flask`) would go unnoticed.

**Fix:** Add `pip-audit` to CI and enable Dependabot + CodeQL (already tracked in `LAUNCH_TODO.md §10` CI hardening — links here).

### S-5 — No centralized input-size / validation guard · **Low**
Handlers validate fields ad-hoc (good in the spots checked, e.g. `target_dollars` numeric/positive). There is no global `MAX_CONTENT_LENGTH` or schema validation, so oversized/garbage bodies reach handlers.

**Fix:** Set `app.config['MAX_CONTENT_LENGTH']` (e.g. 256 KB) and validate the few free-text inputs (display name, W-9 fields) for length/charset before persistence (also feeds the UGC-scrub launch item).

---

## Remediation checklist (priority order)
- [ ] **S-1a** Move rate-limiter to a shared store (Postgres/KV).
- [ ] **S-1b** Add `@rate_limit` to `/auth/token` (and confirm `/leaderboard`).
- [ ] **S-2** Verify Pub/Sub OIDC token (or add shared-secret URL token) on `/webhooks/google/rtdn`.
- [ ] **S-5** Set `MAX_CONTENT_LENGTH` + validate free-text fields (display name, W-9).
- [ ] **S-3** Guard/remove `app.py` `debug=True`.
- [ ] **S-4** Add `pip-audit` + Dependabot + CodeQL to CI (see `LAUNCH_TODO.md §10`).

## Out of scope / recommended ongoing
- Penetration test of the live deployment (dynamic) before/at launch.
- Native-client secret hygiene (no API secrets shipped in the app binaries).
- Periodic re-audit when the **inbound trading API** (`LAUNCH_TODO.md §2`) lands — a new authenticated write surface that will need its own injection/authz/rate-limit review.
