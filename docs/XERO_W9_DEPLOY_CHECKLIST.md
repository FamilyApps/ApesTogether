# Xero + W-9 + Revenue Accounting — Remaining Actions Checklist

Living log of everything left to do for the W-9 collection + Xero gross/principal
accounting work. Check items off as you go.

---

## A. Pre-deploy (do BEFORE pushing to prod)

- [ ] **Run the migration** `scripts/migrations/2026_06_16_taxpayer_profile.sql` in
      Supabase (creates the `taxpayer_profile` table). Must run before the new
      code deploys, or `/tax/w9*` endpoints will 500.

## B. Deploy

- [ ] **Push to `master`** → Vercel auto-deploys the backend.
- [ ] **Hard-refresh `/admin-panel`** once after deploy (the Babel CDN URL is now
      pinned to `@7`, so the browser must re-fetch it). Confirm the panel loads
      with no "Cannot use import statement" JS error.

## C. Post-deploy verification (Xero chart of accounts)

- [ ] If Xero isn't connected yet: visit **`https://apestogether.ai/api/mobile/admin/xero/connect`** and authorize (note the `/api/mobile` prefix — the bare `/admin/xero/connect` 404s).
- [ ] **`GET /admin/xero/accounts`** and confirm all three show `true`:
      - `4010_subscription_revenue` (REVENUE — gross subscription income)
      - `6100_store_fees` (EXPENSE — Apple/Google commission)
      - `6010_user_payments` (EXPENSE — creator payouts / contract labor)
- [ ] If any are missing/false, create them in Xero with those exact codes, then
      re-check. (Codes are referenced by `xero_service.REVENUE_ACCOUNT_CODE`,
      `STORE_FEE_ACCOUNT_CODE`, and the payout bill code `6010`.)

## D. Ship the mobile apps

- [ ] **iOS**: build + submit. New in-app W-9 form lives at Settings → "Tax Info (W-9)".
- [ ] **Android**: build + submit. Same entry point in Settings.
- [ ] Sanity check on each: a creator with a subscriber sees the W-9 form; a user
      with no subscribers sees "No tax info needed yet".

---

## E. Monthly accounting run (operational, recurring)

Order matters:

1. [ ] **`POST /admin/xero/post-revenue`** `{ "period_year": Y, "period_month": M }`
       → books gross revenue (4010) + store fees (6100) per platform. Idempotent.
2. [ ] **`POST /admin/bot/generate-payout-records`** → creates payout records.
       Company bots + owner accounts are skipped. Real creators without a W-9 on
       file are created as `held`.
3. [ ] Creators submit their **W-9** in-app → held payouts auto-release to `pending`.
4. [ ] **`POST /admin/xero/sync-payouts`** → posts creator payout bills (6010).
       Held (no-W-9) records are skipped until released.

---

## How company-owned revenue is treated (FYI — already wired)

Subscriptions to **your own accounts** (`bobford00@gmail.com`,
`fordutilityapps@gmail.com`) and **your bots** (`role == 'agent'`):

- Subscriber pays; **store takes its cut** (booked to 6100).
- **No creator payout** is generated (no 6010 bill) — payout generation and W-9
  requirement both skip these via `User.is_company_owned`.
- At purchase time the influencer share is rolled into `platform_revenue`, so the
  **post-store remainder is Family Apps LLC profit** (4010 − 6100, with 6010 = 0).
- Single source of truth: `User.is_company_owned` in `models.py` (+ `OWNER_EMAILS`).
  To add/remove an owner account, edit `OWNER_EMAILS` there.

---

## F. Known gaps — ALL BUILT in Session 16 (see `LAUNCH_TODO.md` for live status)

These were the proposed next-work items; they are now implemented (code complete,
tested via `tests/test_payout_integrity.py`). Tasks are tracked only in
`LAUNCH_TODO.md` going forward.

- [x] **Refund/chargeback handling** — `xero_service.reverse_refunded_purchase[s]`
      issues idempotent revenue (4010) + store-fee (6100) credit notes; best-effort
      hook in the webhooks + authoritative sweep `POST /admin/xero/reconcile-refunds`.
- [x] **Transaction-driven payouts** — `bot_generate_payout_records` now sums the
      period's non-refunded `InAppPurchase` rows (annual paid once), and
      `create_bill_for_payout` bills the actual amount (not `active_count × $`).
- [x] **Idempotency guard on payout sync** — unique index `uq_payout_user_period`
      on `(portfolio_user_id, period_start, period_end)`.
- [x] **$600 / missing-TIN dashboard** — `GET /admin/tax/1099-readiness` — plus the
      W-9 push-retry/reconcile job `POST /admin/tax/w9/retry-sync`.

> **Migration:** run `scripts/migrations/2026_06_17_payout_integrity.sql` (adds
> `in_app_purchase.payout_reversed_at` + the unique index) before deploying this work.
