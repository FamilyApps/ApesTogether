# Per-Creator Subscription Slots

**Status:** building (Session 15). **Decision:** N=20 concurrent subs/user, **one free trial per user (lifetime)**, uniform pricing.

---

## ✅ What YOU need to do (everything below this section is code reference)

The code is built + committed. These are the only **manual, operator-only** steps, in order:

1. **[✅ DONE] Run the DB migration** `scripts/migrations/2026_06_14_subscription_slot.sql` in the Supabase SQL Editor. ("Success. No rows returned" is the expected result.)
2. **Confirm the backend deployed.** The slot code is already pushed to `master`; Vercel auto-deploys. Just verify the deploy went green.
3. **Create the slot products in BOTH stores** (the big one): Slots 2–20, **same price** as Slot 1, **no free trial**. Click-by-click in the **"Store console setup"** section further down. *(Until you do this, a user's FIRST subscription still works — it uses Slot 1's existing products — but a SECOND concurrent subscription will fail with "product not available.")*
4. **Ship the apps:** archive a new **iOS** build to TestFlight (picks up the client changes); the **Android** build is already on your Pixel — also push it to the Play internal track.
5. **Test on-device:** subscribe to **two** creators → confirm two independent entries on the store Manage page, the in-app "Subscription A / B" chips match, and canceling one leaves the other active.

*Local testing (optional):* Slots 2–20 are also in `ios/ApesTogetherApp/Configuration.storekit` (regenerate with `python scripts/gen_storekit_slots.py`), so you can exercise the monthly/annual toggle + multi-sub flow in Xcode's local StoreKit environment before creating the real store products.

---

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
| 2 | B | `com.apestogether.sub.s02.monthly` | `com.apestogether.sub.s02.annual` | No |
| … | … | … | … | No |
| 20 | T | `com.apestogether.sub.s20.monthly` | `com.apestogether.sub.s20.annual` | No |

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
`com.apestogether.sub.s02.monthly` / `.s02.annual` … through `s20`.

> **Why `sub`, not `subscription`?** Google Play caps product IDs at **40 chars**.
> `com.apestogether.subscription.s02.monthly` is 41 (rejected); the abbreviated
> `com.apestogether.sub.s02.monthly` is 32. Slot 1 keeps its existing (longer) legacy
> IDs — those already exist in both stores and are under 40 (`…subscription.monthly`
> = 37).

### Exact products to create (Slots 2–20)

Create every row below. Notes on the columns:
- **Subscription Group** — in App Store Connect, use this string for **both** the
  group's *Reference Name* and its (user-facing) *Display Name*. Google Play has no
  groups; ignore this column there.
- **Reference Name** — App Store Connect only: the per-subscription *Reference Name*
  (internal, never shown to users). **Google Play has no equivalent** — for Play, set
  each product's user-facing **Name** to the *Subscription Group* value
  (`Trader Subscription B`) instead, so it matches the in-app cancel hint.
- **Product ID** — identical on both stores and **must match exactly** (lowercase,
  zero-padded `sNN`). This is the only field the app depends on. Enter the **bare
  ID with no surrounding quotes or backticks** — type
  `com.apestogether.sub.s02.monthly`, not the quoted version you may see
  in this doc or in `subscription_slots.py` (those quotes/backticks are only
  formatting / Python string delimiters).

**Slot 1 (A) already exists** — shown only for reference:
- **Never recreate it or change its Product IDs** (`com.apestogether.subscription.monthly`
  / `.annual`). Both stores forbid editing a product ID after creation, and the
  backend keys Slot 1 off those exact legacy IDs (`subscription_slots.py`).
- **Keep its existing 7-day trial** — that's the one-trial-per-user mechanism.
- **Rename its subscription-group Display Name** from `Apes Together Premium` to
  `Trader Subscription A` so it matches the in-app cancel hint ("cancel the entry
  labeled *Trader Subscription A*"). Group Display Names are editable anytime and
  safe to change (unlike Product IDs). The internal *Reference Names* don't matter —
  align them if you like, but that's optional.

| Slot | Subscription Group | Reference Name | Product ID | Billing | Price |
|------|--------------------|----------------|------------|---------|-------|
| A (1) | Trader Subscription A | _(exists)_ Monthly A | `com.apestogether.subscription.monthly` | 1 month | $9 |
| A (1) | Trader Subscription A | _(exists)_ Annual A | `com.apestogether.subscription.annual` | 1 year | $69 |
| B (2) | Trader Subscription B | Slot B Monthly | `com.apestogether.sub.s02.monthly` | 1 month | $9 |
| B (2) | Trader Subscription B | Slot B Annual | `com.apestogether.sub.s02.annual` | 1 year | $69 |
| C (3) | Trader Subscription C | Slot C Monthly | `com.apestogether.sub.s03.monthly` | 1 month | $9 |
| C (3) | Trader Subscription C | Slot C Annual | `com.apestogether.sub.s03.annual` | 1 year | $69 |
| D (4) | Trader Subscription D | Slot D Monthly | `com.apestogether.sub.s04.monthly` | 1 month | $9 |
| D (4) | Trader Subscription D | Slot D Annual | `com.apestogether.sub.s04.annual` | 1 year | $69 |
| E (5) | Trader Subscription E | Slot E Monthly | `com.apestogether.sub.s05.monthly` | 1 month | $9 |
| E (5) | Trader Subscription E | Slot E Annual | `com.apestogether.sub.s05.annual` | 1 year | $69 |
| F (6) | Trader Subscription F | Slot F Monthly | `com.apestogether.sub.s06.monthly` | 1 month | $9 |
| F (6) | Trader Subscription F | Slot F Annual | `com.apestogether.sub.s06.annual` | 1 year | $69 |
| G (7) | Trader Subscription G | Slot G Monthly | `com.apestogether.sub.s07.monthly` | 1 month | $9 |
| G (7) | Trader Subscription G | Slot G Annual | `com.apestogether.sub.s07.annual` | 1 year | $69 |
| H (8) | Trader Subscription H | Slot H Monthly | `com.apestogether.sub.s08.monthly` | 1 month | $9 |
| H (8) | Trader Subscription H | Slot H Annual | `com.apestogether.sub.s08.annual` | 1 year | $69 |
| I (9) | Trader Subscription I | Slot I Monthly | `com.apestogether.sub.s09.monthly` | 1 month | $9 |
| I (9) | Trader Subscription I | Slot I Annual | `com.apestogether.sub.s09.annual` | 1 year | $69 |
| J (10) | Trader Subscription J | Slot J Monthly | `com.apestogether.sub.s10.monthly` | 1 month | $9 |
| J (10) | Trader Subscription J | Slot J Annual | `com.apestogether.sub.s10.annual` | 1 year | $69 |
| K (11) | Trader Subscription K | Slot K Monthly | `com.apestogether.sub.s11.monthly` | 1 month | $9 |
| K (11) | Trader Subscription K | Slot K Annual | `com.apestogether.sub.s11.annual` | 1 year | $69 |
| L (12) | Trader Subscription L | Slot L Monthly | `com.apestogether.sub.s12.monthly` | 1 month | $9 |
| L (12) | Trader Subscription L | Slot L Annual | `com.apestogether.sub.s12.annual` | 1 year | $69 |
| M (13) | Trader Subscription M | Slot M Monthly | `com.apestogether.sub.s13.monthly` | 1 month | $9 |
| M (13) | Trader Subscription M | Slot M Annual | `com.apestogether.sub.s13.annual` | 1 year | $69 |
| N (14) | Trader Subscription N | Slot N Monthly | `com.apestogether.sub.s14.monthly` | 1 month | $9 |
| N (14) | Trader Subscription N | Slot N Annual | `com.apestogether.sub.s14.annual` | 1 year | $69 |
| O (15) | Trader Subscription O | Slot O Monthly | `com.apestogether.sub.s15.monthly` | 1 month | $9 |
| O (15) | Trader Subscription O | Slot O Annual | `com.apestogether.sub.s15.annual` | 1 year | $69 |
| P (16) | Trader Subscription P | Slot P Monthly | `com.apestogether.sub.s16.monthly` | 1 month | $9 |
| P (16) | Trader Subscription P | Slot P Annual | `com.apestogether.sub.s16.annual` | 1 year | $69 |
| Q (17) | Trader Subscription Q | Slot Q Monthly | `com.apestogether.sub.s17.monthly` | 1 month | $9 |
| Q (17) | Trader Subscription Q | Slot Q Annual | `com.apestogether.sub.s17.annual` | 1 year | $69 |
| R (18) | Trader Subscription R | Slot R Monthly | `com.apestogether.sub.s18.monthly` | 1 month | $9 |
| R (18) | Trader Subscription R | Slot R Annual | `com.apestogether.sub.s18.annual` | 1 year | $69 |
| S (19) | Trader Subscription S | Slot S Monthly | `com.apestogether.sub.s19.monthly` | 1 month | $9 |
| S (19) | Trader Subscription S | Slot S Annual | `com.apestogether.sub.s19.annual` | 1 year | $69 |
| T (20) | Trader Subscription T | Slot T Monthly | `com.apestogether.sub.s20.monthly` | 1 month | $9 |
| T (20) | Trader Subscription T | Slot T Annual | `com.apestogether.sub.s20.annual` | 1 year | $69 |

### App Store Connect (iOS) — 19 new subscription groups

> **⚠️ Already created the iOS slots with the long `…subscription.sNN.*` IDs?**
> App Store Connect product IDs are **permanent** — you can't edit or delete them.
> Don't recreate the *groups* (keep `Trader Subscription B`..`T` and Slot 1). For each
> Slot **B–T**, inside its existing group:
> 1. **Create a new subscription** using the short ID from the table
>    (`com.apestogether.sub.sNN.monthly` / `.annual`), $9 / $69, no intro offer.
> 2. **Remove the old long-ID product from sale** (clear its price / "Remove from
>    Sale") so it can never be purchased. It will linger as an unused draft — harmless.
> The short ID is the only one the backend hands the app, so only it can ever sell.

> **What users see on the Manage Subscriptions screen:** iOS lists each active
> subscription by its **subscription *group* Display Name**, with the per-subscription
> Display Name shown beneath as the selected plan. A user subscribed to three creators
> sees:
>
> ```
> Trader Subscription A
>    Monthly Subscription · $9/mo · Renews …
> Trader Subscription B
>    Annual Subscription · $69/yr · Renews …
> Trader Subscription C
>    Monthly Subscription · $9/mo · Renews …
> ```
>
> So the **group Display Name** (unique per slot, A..T) is the differentiator; the
> "Monthly/Annual Subscription" per-subscription name is intentionally **identical**
> across slots and only tells the user which plan they're on. That's why the group
> Display Name must match the in-app cancel hint exactly. (Source: subscription
> groups' localized data drive the Manage-screen appearance.)

Each slot must be its **own subscription group** (Apple allows only one active sub
per group → separate groups = independently cancelable). For each slot `s02`..`s20`:

1. App Store Connect → your app → **Monetization ▸ Subscriptions**.
2. **Subscription Groups → Create** → set both its Reference Name and its
   user-facing **Display Name** to `Trader Subscription B` (B for s02, C for s03, …).
   The Display Name is what users see on the Manage page and **must match the in-app
   cancel hint exactly** ("cancel the entry labeled *Trader Subscription B*"). Do NOT
   put a creator name — the slot→creator mapping is per-user and lives in-app.
3. Inside the group, **Create** two subscriptions, using the exact **Reference
   Name** + **Product ID** from the *"Exact products to create"* table above
   (monthly = duration **1 month**, **$9**; annual = duration **1 year**, **$69**).
4. Add the localized **Display Name** + **Description** — **identical for every
   slot**, matching your existing Slot 1 products:
   - Monthly → Display Name `Monthly Subscription` · Description `Follow a trader's moves in real-time`
   - Annual → Display Name `Annual Subscription` · Description `Follow a trader's moves in real-time — best value`
   *(The per-subscription Reference Name from step 3 is internal-only; this Display
   Name + Description are what users see. They're the same across all slots — the
   slot letter is carried by the GROUP display name, see step 2.)*
5. **Do NOT add an Introductory Offer** (no free trial) on any slot ≥ 2.
6. Submit for review (can be bundled with the next app version or submitted alone).

> Tip: these 19 groups are **already** in `ios/ApesTogetherApp/Configuration.storekit`
> (run `python scripts/gen_storekit_slots.py` to regenerate) so you can test slots in
> the local StoreKit environment now. Sandbox / production use App Store Connect, not
> the .storekit file — so you still need to create them there per the table above.

### Google Play — 38 new products

Play has no "group" concept; distinct products are independently cancelable. The
product's **Name** is what users see on the Play Manage-subscriptions page, so set it
to the slot's *Subscription Group* value (`Trader Subscription B`) so it matches the
in-app cancel hint. Both the monthly and annual product of a slot share that same
Name (a user only ever has one of them active at a time).

Play Console → **Monetize ▸ Products ▸ Subscriptions** → for each `s02`..`s20`:

1. **Create subscription** with the **Product ID** from the table (start with
   `…sNN.monthly`); set its **Name** to the slot's *Subscription Group* value
   (e.g. `Trader Subscription B`).
2. Add a **base plan**: auto-renewing, **1 month**, **$9**, no offer. Base plan IDs
   allow only lowercase letters, numbers, and hyphens (no periods/underscores) — use
   `monthly` (and `annual` below). If Play rejects a duplicate, prefix the slot:
   `s02-monthly`. The code uses the *Product ID*, not the base plan ID, so any valid
   value works.
3. Repeat for `…sNN.annual`: same **Name** (`Trader Subscription B`), auto-renewing,
   **1 year**, **$69**, **no** free-trial offer.
4. **Activate** each.

> **Slot 1:** rename your existing `…subscription.monthly` / `.annual` products'
> **Name** to `Trader Subscription A` too (Product IDs stay unchanged). Only Slot 1's
> products keep their existing 7-day free-trial offer.

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
