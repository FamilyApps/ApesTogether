# Per-Creator Subscription Slots

**Status:** building (Session 15). **Decision:** N=20 concurrent subs/user, **one free trial per user (lifetime)**, uniform pricing.

## Problem

A user can subscribe to many creators, each independently billed and independently
cancelable. The App Store / Play Store only allow **one active subscription per
subscription group (iOS) / per product (Android)** per account, and auto-renewable
products must be **pre-approved** (you can't mint a product per UGC creator at
runtime). So we can't use one shared product for everyone (the old design — it
blocked the 2nd creator with `ITEM_ALREADY_OWNED` and had no way to show *which*
creator on the store Manage page).

## Model: numbered slots + server-side creator attribution

A bounded pool of **N=20 generic, identical-price "slots."** Each slot is its own
iOS **subscription group** (required so the slots are independently cancelable) and
its own pair of products (monthly + annual). The store only ever knows about 20
slots ("Subscription A".."Subscription T"); **which creator a slot maps to is held
entirely on our backend, per-user.** This is the same pattern Twitch uses for
mobile channel subs (a small fixed set of products, target attributed server-side)
— but we keep **auto-renewal** (Twitch's iOS "Sub Tokens" are consumables and lose
auto-renew).

- bobford00's Slot A might be → Wolff; candle3873's Slot A might be → zen1889.
- Store Manage page shows "Subscription A / B / …"; the in-app Subscriptions tab
  shows **"Wolff's Flagship Fund — Subscription A"** + "To cancel, open Manage and
  cancel *Subscription A*." so the user knows which to pick.

### Product-ID scheme

| Slot | Label | Monthly product ID | Annual product ID | Trial? |
|------|-------|--------------------|-------------------|--------|
| 1 | A | `com.apestogether.subscription.monthly` *(existing)* | `com.apestogether.subscription.annual` *(existing)* | **Yes** |
| 2 | B | `com.apestogether.subscription.s02.monthly` | `com.apestogether.subscription.s02.annual` | No |
| … | … | … | … | No |
| 20 | T | `com.apestogether.subscription.s20.monthly` | `com.apestogether.subscription.s20.annual` | No |

Slot 1 **reuses the existing products** (no client/store churn; they already carry
the 7-day trial). Source of truth: `subscription_slots.py`.

### One free trial per user — store-enforced, zero app logic

The 7-day intro offer is configured **only on Slot 1 (A)** products. Because:
1. A user's **first** subscription always lands in Slot A (Slot A is only occupied
   if they already have an active sub there ⇒ they already subscribed once).
2. Intro-offer eligibility is **once per subscription group / product, per account**
   — so even after a user cancels their Slot A sub and a *new* creator later reuses
   Slot A, the store will **not** grant the trial again.

⇒ Exactly **one free trial in a user's lifetime**, enforced natively by both stores.
Slots B–T have no intro offer, so concurrent 2nd/3rd subs bill immediately.

## Backend

### Slot allocation (no reservation table needed)

The store itself prevents double-booking a slot (you can't own Slot A's product
twice), so we just compute the slot **on demand** and bind it at validate time.

A slot is **occupied** for a user if they have a `MobileSubscription` in that slot
that is `active`, or `canceled` but `expires_at` is still in the future (grace —
the store entitlement still exists until period end). Otherwise it's free.

`GET /api/mobile/subscriptions/slot-for-creator?subscribed_to_id=<id>`:
1. Already have an active/grace sub to this creator → `409 {error:"already_subscribed", slot, slot_label}`.
2. Else lowest free slot 1..20. None free → `409 {error:"max_reached", max_slots:20}`.
3. Else `200 {slot, slot_label, monthly_product_id, annual_product_id, max_slots}`.

### Binding

`POST /purchase/validate` is unchanged in shape; it derives the slot from the
**authoritative** purchased `product_id` (`slot_for_product_id`) and stores it on
the `MobileSubscription`. The creator binding lives on the **purchase token /
originalTransactionId** (already how `iap_webhooks._apply_update` matches), so slot
reuse over time is safe — webhooks update the right row regardless of slot number.

`GET /subscriptions` returns `slot` + `slot_label` per made-subscription for the UI.

### Schema change

`MobileSubscription.slot` (Integer, nullable) — `scripts/migrations/2026_06_14_subscription_slot.sql`.

## Clients

Replace the two hardcoded purchase product IDs with **dynamic resolution**:
1. On Subscribe tap, call `slot-for-creator` → get the assigned slot's product IDs.
2. Purchase the monthly/annual product for that slot (per the plan toggle).
3. Validate as today (sends the real `product_id`).
4. `max_reached` → "You've reached the maximum of 20 subscriptions. Cancel one to
   subscribe to another." `already_subscribed` → route to Manage.

Price **display** still uses Slot A products (all slots are the same price), so the
CTA/price UI is unchanged.

Subscriptions tab: show the slot label per row + the "cancel *Subscription X* in
the store" hint (pairs with the single-action Manage button shipped in Session 14).

## Store console setup (manual, one-time)

You create Slots **2–20** in **both** stores. Slot 1 already exists. Every slot
product is the **same price** as Slot 1 ($9/mo, $69/yr) and has **no** intro offer
(only Slot 1 keeps its 7-day trial → one trial per user, lifetime).

Product IDs follow `subscription_slots.py` exactly:
`com.apestogether.subscription.s02.monthly` / `.s02.annual` … through `s20`.

### App Store Connect (iOS) — 19 new subscription groups

Each slot must be its **own subscription group** (Apple allows only one active sub
per group → separate groups = independently cancelable). For each slot `s02`..`s20`:

1. App Store Connect → your app → **Monetization ▸ Subscriptions**.
2. **Subscription Groups → Create** → name it e.g. `Trader Subscription B` (B for
   s02, C for s03, …). The group **Display Name** is what users see on the Manage
   page, so keep it generic-but-clear (do NOT put a creator name — the mapping is
   per-user and lives in-app).
3. Inside the group, **Create** two subscriptions:
   - `com.apestogether.subscription.sNN.monthly` — duration **1 month**, price **$9**.
   - `com.apestogether.subscription.sNN.annual` — duration **1 year**, price **$69**.
4. Add localized display name ("Monthly Subscription" / "Annual Subscription") +
   description (copy from Slot 1).
5. **Do NOT add an Introductory Offer** (no free trial) on any slot ≥ 2.
6. Submit for review (can be bundled with the next app version or submitted alone).

> Tip: keep `ios/ApesTogetherApp/Configuration.storekit` in sync if you test slots
> in the local StoreKit environment (add the 19 groups there too). Production uses
> App Store Connect, not the .storekit file.

### Google Play — 38 new products

Play has no "group" concept; distinct products are independently cancelable.
Play Console → **Monetize ▸ Products ▸ Subscriptions** → for each `s02`..`s20`:

1. **Create subscription**, product ID `com.apestogether.subscription.sNN.monthly`.
2. Add a **base plan**: auto-renewing, **1 month**, **$9**, no offer.
3. Repeat for `…sNN.annual`: auto-renewing, **1 year**, **$69**, **no** free-trial offer.
4. **Activate** each.

> Only Slot 1's products keep their existing 7-day free-trial offer.

### Don't forget
- Same Small-Business-Program / tax settings as Slot 1 so the payout math
  (`InAppPurchase` defaults) stays correct.
- After publishing, run the on-device test in the checklist below.

### Constraints / decisions baked in
- **Uniform pricing required.** Per-creator pricing would multiply slots × tiers.
- **Max 20 concurrent** subs per user (over-provision is cheap; bump later if needed).
- Generic-but-clear store display names ("Trader Subscription A"); real mapping in-app.

## Checklist
- [ ] `subscription_slots.py` catalog
- [ ] `MobileSubscription.slot` column + migration run in Supabase
- [ ] `/subscriptions/slot-for-creator` endpoint
- [ ] validate binds slot; `/subscriptions` returns slot + label
- [ ] iOS dynamic resolution + max UI + tab labels
- [ ] Android dynamic resolution + max UI + tab labels
- [ ] App Store Connect: 19 new groups (no trial), same price
- [ ] Play Console: 38 new products (no trial), same price
- [ ] On-device: subscribe to 2 creators, confirm 2 independent store entries + correct labels
