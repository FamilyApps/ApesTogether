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

## D2. Before public launch — REMOVE test overrides (CRITICAL)

- [ ] **Delete the `W9_TEST_EMAILS` env var on Vercel** (then redeploy). It was set
      during testing so an owner/admin account (e.g. `bobford00`) — normally never
      payout-eligible — could open and submit the in-app W-9 form. Left set in
      production it makes those accounts appear payout-eligible for the W-9 gate.
      Read at `mobile_api.py` `_user_is_payout_eligible` / `W9_TEST_EMAILS`.
      **Status 2026-07-01: still SET on purpose — keep until the W-9→Xero flow is
      fully confirmed with `bobford00`, then remove before launch.**
- [ ] (Optional) Clean up the test W-9 data the override created: delete the
      `taxpayer_profile` row for the test account and clear/blank its Xero contact
      `TaxNumber`, so no bogus TIN lingers in Xero.

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

---

## G. Address validation — USPS intentionally NOT used

**Decision (2026-07-03): we are NOT wiring up USPS address validation.** The USPS
Address API goes paid on **July 12, 2026** (requires a signed license agreement +
tier-based fees, transitioning to the "Enhanced Addresses API"). For our very low
mailing volume it isn't worth a license/fee, so we rely on lighter safeguards.

**What actually guards address quality (no external service, no cost):**

- **Client-side:** the in-app W-9 form enforces a valid US state (dropdown) and a
  ZIP matching `^\d{5}(-\d{4})?$`, plus required street/city.
- **Server-side:** the same format + valid-US-state + ZIP checks are enforced in
  `tax_w9_submit`.
- **Human review:** the month-end check-run email (section H) lists every payee's
  mailing address and flags missing ones, so bad addresses are caught before a
  check is mailed.

**Dormant code left in place (harmless, no action needed):**

- `services/address_validation.py` and the USPS call in `tax_w9_submit` are
  **fail-open**: with `USPS_CLIENT_ID` / `USPS_CLIENT_SECRET` **unset** the USPS
  lookup is a no-op and submission proceeds on the format checks above. Leave the
  vars unset.
- The mobile "Submit anyway" override (`skip_address_check`) only appears if the
  server returns `address_not_deliverable`, which can't happen while USPS is
  unconfigured — so it stays dormant.
- If USPS (or an alternative) is ever adopted later, just set the two env vars and
  it activates; no code change required.

## H. Month-end check-run report email

The monthly payout cron now emails a "check run" (payee name + mailing address +
amount + real/gift sub counts) to **bobford00@gmail.com** so mailing checks never
depends on remembering to run a report. Uses the existing SendGrid sender.

- [ ] **Test delivery/format now:** `GET /api/mobile/admin/tax/payout-check-run?sample=1`
      (admin 2FA) emails a fabricated SAMPLE report (3 payees incl. a business and
      a missing-address warning row). Confirm it lands at bobford00@gmail.com.
- [ ] **Real current data:** `?email=1` instead of `?sample=1`. NOTE: this is
      currently EMPTY — the only subscribed creator is a company bot, which is
      `is_company_owned` and generates no payout, so it's excluded by design.
- Automatic send fires at the end of `run_monthly_payout_pipeline` (the 3rd-of-month
  cron), best-effort so it never blocks the payout run.
