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

- [ ] If Xero isn't connected yet: visit **`/admin/xero/connect`** and authorize.
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

## F. Known gaps (NOT yet built — proposed next work)

- [ ] **Refund/chargeback handling** — Apple ASSN V2 `REFUND` webhook + Google
      RTDN / Voided Purchases sweep → reverse 4010/6100 via credit notes and claw
      back the payout. (Highest priority — real money leaks without it.)
- [ ] **Transaction-driven payouts** — pay annual subs once (sum of period
      `InAppPurchase.influencer_payout`) instead of `active_count × $9`.
- [ ] **Idempotency guard on payout sync** keyed on `(user, period)`.
- [ ] **$600 / missing-TIN dashboard** + W-9 push-retry job for failed Xero syncs.
