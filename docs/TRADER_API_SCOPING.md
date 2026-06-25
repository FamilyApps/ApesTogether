# Public Trader API — Scoping

**Date:** 2026-06-22 (Session 18) · **Status:** Scoping / decision doc (no code yet) · **Owner:** product
**Tracked in:** `LAUNCH_TODO.md §2`

Scopes the "automated inputs from users (especially AI models)" idea. Per the product philosophy ("Algorithms and AI bots welcome"), there are two distinct API products. This doc designs each **separately**, then shows how they **combine**, and ends with a v1 recommendation + open decisions.

- **UC-A — Algo/AI Creator API (inbound WRITE).** Let an external algo/AI **run its own public ApesTogether portfolio over HTTP** — submit buys/sells, set holdings — so humans can subscribe and copy it. A public, hardened version of the **internal bot system we already run**.
- **UC-D — Subscriber Auto-Execution API (outbound READ + events).** Let a **subscriber's own bot/broker** pull the creators they follow and **auto-place the mirrored trades in their real brokerage** account.

They are mirror images: **A produces signal, D consumes it.** Same trade event; opposite ends of the pipe.

---

## Why this is largely "expose what already exists" (UC-A)

We already operate dozens of internal bots that trade virtual portfolios via authenticated endpoints — the mechanics are proven:

- `mobile_api.py:3408` `POST /portfolio/trade` — the user-facing trade path (buy/sell, pending after-hours queueing).
- `mobile_api.py:4255` `POST /admin/bot/execute-trade` — the internal bot trade executor.
- `mobile_api.py:1424` `POST /portfolio/stocks` — add/set holdings.
- `mobile_api.py:6107` `POST /admin/bot/process-pending-trades` — settles queued trades at market open.
- The slot/subscription + payout model (`MobileSubscription`, `XeroPayoutRecord`) already turns "followers of a portfolio" into revenue and creator payouts.

**So UC-A is mostly: per-user API-key auth + scopes + rate-limits + validation wrapped around the trade/holdings logic that the internal bots already use** — not a green-field build. Crucially, trades are **virtual** (real market data, simulated execution), which keeps UC-A's regulatory surface low.

UC-D is the opposite: it touches **real brokerage money**, so it is mostly **new** (broker integrations + a heavy compliance layer).

---

## UC-A — Algo/AI Creator API (inbound WRITE)

### Goal
A developer or AI agent registers as a creator, gets an API key, and drives a public portfolio programmatically. Followers subscribe (existing $9/mo, 85% to the creator). This directly delivers "AI bots welcome" as a **first-class, self-serve** capability instead of an admin-only internal feature.

### Auth
- **Per-user API keys** with scopes (`trade:write`, `portfolio:read`). Show the secret once; store a hash (bcrypt/argon2). Support 2 active keys for rotation.
- Sign requests or send `Authorization: Bearer <key>`; bind every call to the owning `user_id` server-side (reuse the existing `g.user_id` ownership pattern — see `docs/SECURITY_AUDIT.md`, IDOR is already handled this way).
- Optional HMAC body signature (`X-Signature`) for tamper-evidence on POSTs.

### Endpoints (v1)
| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/api/v1/orders` | Submit a buy/sell (ticker, side, qty or notional, optional limit). Returns order id + queued/filled status. |
| `GET`  | `/api/v1/orders/{id}` | Order status (queued → filled/cancelled). |
| `DELETE` | `/api/v1/orders/{id}` | Cancel a still-queued (after-hours) order. |
| `GET`  | `/api/v1/portfolio` | Current cash + positions (mirrors the app's own view). |
| `GET`  | `/api/v1/positions` | Positions only, with avg cost + market value. |
| `GET`  | `/api/v1/fills` | Trade history (paginated). |

### Validation & risk controls
- Reuse existing trade validation (valid ticker, sufficient cash/shares, market-hours → pending queue).
- **Abuse caps:** max orders/min, max tickers, min order size; block obvious wash/ping-pong patterns that game the leaderboard. The shared-store rate-limiter this depends on is **now shipped** (audit **S-1 RESOLVED**, Session 19 W1) — see the design below.
- **Idempotency-Key** header so a retrying bot can't double-submit.
- **Market-data redistribution:** returning live prices/positions to third parties may exceed AlphaVantage/Finnhub license terms — confirm before exposing price fields, or restrict to the creator's own portfolio data (which they generated). **(Legal check required.)**

### Rate-limiting & quotas (UC-A) — concrete design
The foundation already exists and is live: `rate_limit(max_requests, per_seconds)` + the Postgres fixed-window counter `_rate_limit_db_hit` (table `mobile_rate_limit`, keyed `client_key + window_start`) in `mobile_api.py`, correct across serverless instances with an in-memory fallback. UC-A needs five deltas on top of it:

1. **Key by owning `user_id`, not by API key or IP.** On auth, resolve the key → set `g.user_id` to the owner (reuse the existing pattern). Meter on `user:{user_id}` so a creator **cannot multiply their quota by minting extra keys**. (The decorator already prefers `g.user_id` when set, so this mostly falls out for free.)
2. **Separate read vs. write buckets, stacked per-minute + per-day.** Reads are cheap, order-writes are not. Stack two decorators using the existing arbitrary-window support (the daily window prunes automatically — `_rate_limit_db_hit` already deletes windows >1 day):
   - Reads (`GET /portfolio|positions|fills|orders/{id}`): per-minute burst only.
   - Writes (`POST/DELETE /orders`): a per-minute burst **and** a per-day quota, sharing one bucket name across all order routes (pass an explicit `bucket='orders'` rather than the default per-function key so a bot can't fan out across endpoints to dodge the cap).
3. **Tiered limits resolved at request time (resolves D-6).** Today's limits are static at decoration time; tiers need the cap to come from the key's plan. Add a thin `rate_limit_tiered(bucket, limits_by_tier)` variant that reads `g.api_key_tier` (set during auth) and picks the row. Proposed v1 defaults (final numbers = D-6):
     | Tier | Reads/min | Order-writes/min | Orders/day |
     |------|-----------|------------------|------------|
     | Free | 60 | 20 | 1,000 |
     | Paid/developer | 300 | 120 | 50,000 |
   Keep a hard global safety ceiling above the paid tier regardless of plan.
4. **Emit standard quota headers on every response** (not just 429): `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset`. The current decorator only sets `Retry-After` on the 429 path; well-behaved bots self-throttle when given remaining/reset, which cuts 429 volume. (`_rate_limit_db_hit` already returns the hit count, so remaining = limit − hits is cheap to surface.)
5. **Dedupe before metering.** Resolve the `Idempotency-Key` first; a replayed request that maps to an existing order returns the prior result and **must not** consume quota again. Order matters: idempotency check → rate meter → trade validation.

**Known limitation to document for devs:** fixed-window allows up to ~2× burst across a window boundary. Acceptable for v1; if order-write abuse appears, upgrade just the `orders` bucket to a token-bucket/GCRA without touching the read paths.

### Effort: **~Medium.** Reuses internal trade logic; net-new = API-key model, scopes, docs, the tiered-limit wrapper + quota headers on top of the now-shipped S-1 limiter, and a developer settings screen.

---

## UC-D — Subscriber Auto-Execution API (outbound READ + events)

### Goal
A subscriber connects their **real brokerage**; their bot (or ours) detects when a creator they follow trades and **places the scaled equivalent in their real account** — "copy-trading with real money."

### Shape
- **Read API:** `GET /api/v1/following` (creators I sub to), `GET /api/v1/following/{creator}/fills?since=…` (new trades), `GET /api/v1/following/{creator}/positions` (target weights). The **scale math already exists** (`set_subscription_scale`, `scale_factor`, `target_dollars` — `mobile_api.py:2068`), so we can hand a follower exact share counts for their account size.
- **Events:** webhook/push on each new creator trade (we already fire push notifications on trades — reuse `push_notification_service.py`), so a follower's bot reacts in near-real-time.
- **Brokerage execution:** we do **not** build broker connectivity ourselves. Integrate an aggregator — **SnapTrade** or **Alpaca** (broker) — or let advanced users bring their own broker API key. The follower (or their bot) places the order; we provide the signal + sizing.

### The hard part: compliance & liability ⚠️
Routing **real-money** trades based on someone else's picks is materially different from virtual copy-trading:
- It can constitute **investment advice / discretionary management** → potential **RIA / broker-dealer** registration exposure, suitability obligations, and recordkeeping.
- Mitigations to evaluate **with counsel**: keep execution **user-initiated and self-directed** (we provide data + optional automation the user configures, not advice); prominent "not financial advice / you control execution" disclaimers; no discretionary authority held by us; rely on the aggregator/broker as the regulated executor.
- Real-money failures (slippage, partial fills, outages, a creator's bad trade) create **direct user financial loss** → support, dispute, and insurance considerations the virtual product doesn't have.

### Effort: **~Large.** New broker-aggregator integration, real-time event delivery, reconciliation, **and** a legal/compliance workstream that is the actual gating item.

---

## Together — one API platform

If both ship, they share one spine and reinforce each other:

- **Shared infrastructure:** one API-key + scope system, one **shared-store rate-limiter** (the S-1 fix serves both), one OpenAPI spec + developer docs site, one `/api/v1/*` namespace and developer settings screen.
- **The data pipeline is symmetric:** a UC-A creator's `POST /orders` writes a fill → the platform records it → UC-D streams that fill to followers' bots. **Build the canonical "trade event" once** and both products read/write it. Designing UC-A's order/fill model now with UC-D in mind avoids a rewrite later.
- **Flywheel:** UC-A brings in algo/AI *creators* (more strategies to follow); UC-D makes following them *actionable with real money* (more subscriber value → more willingness to pay). A feeds D's supply; D increases A's monetization.
- **Scope boundary:** UC-A is internal-virtual (low risk) and can launch standalone. UC-D layers real-money execution + compliance on top of the same signal — so the sane sequence is **A first, D as a compliance-gated fast-follow.**

---

## Recommendation

1. **UC-A = v1 (near-launch or immediate fast-follow).** Low regulatory risk (virtual), high philosophy fit ("AI bots welcome" becomes self-serve), mostly a hardened wrapper over proven internal logic. **Its hard dependency — the audit S-1 shared-store rate-limiter — is now SHIPPED (Session 19 W1)**, so the remaining rate-limit work is just the UC-A wrapper in "Rate-limiting & quotas" above.
2. **UC-D = post-launch, compliance-gated.** Start the **legal review now** (it's the long pole), pick an aggregator (**SnapTrade vs. Alpaca**), and design UC-A's trade-event model to be UC-D-ready so D is additive, not a rewrite.
3. **Do not block the store launch on either.** Both are additive platform features; ship the apps first.

---

## Open decisions (need your call)
- **D-1:** UC-A scope — orders only, or also direct holdings-set (`PUT /positions`)? (AI agents often prefer "set target weights.")
- **D-2:** Auth — API keys (recommended, simplest for devs/AI) vs. full OAuth2 client-credentials?
- **D-3:** Does UC-A expose **live prices** (market-data license question) or only the creator's own portfolio state?
- **D-4:** UC-D execution model — aggregator (SnapTrade/Alpaca) vs. bring-your-own-broker-key vs. ApesTogether-hosted bot?
- **D-5:** Are paid API creators subject to the same store-IAP subscription economics, or a separate developer tier?
- **D-6:** Rate-limit/quota tiers (free vs. paid API access)? *(Concrete v1 proposal now in "Rate-limiting & quotas (UC-A)" above — Free 60r/20w/min + 1k orders/day, Paid 300r/120w/min + 50k/day; confirm the numbers + the free/paid split.)*

*Next step on approval: I can turn UC-A into an implementation plan (data model, the `/api/v1` blueprint, API-key issuance + the S-1 shared rate-limiter, OpenAPI spec) and/or open the UC-D legal/aggregator checklist.*

---

## Design clarifications (Session 19, from USER Q&A)

### 1. What does the interface actually look like? (no GUI)
Correct — **there is no GUI for the bot.** The "interface" is:
1. A set of **documented HTTPS REST endpoints** (e.g. `POST /api/v1/orders`) + an **OpenAPI spec**.
2. A **per-user API key** the developer generates inside the app.
3. The developer's own code/bot calls our endpoints over HTTPS with `Authorization: Bearer <api_key>` and a JSON body.

We publish docs + issue the key; the customer writes the client. No dashboard is required for v1 (a simple "API Keys" screen in Settings to create/revoke keys is the only UI we add).

### 2. Preserving the Apple/Google sign-in friction (anti-low-quality / anti-Sybil)
This is preserved **by construction**, and it's the key design rule:

- **API access requires an existing in-app account.** To get a key you must (a) install the app, (b) **sign in with Apple or Google** (the friction that limits multi-accounting), then (c) generate an API key in Settings.
- **No separate web/API signup.** There is no API-only registration path, so the API introduces **no new account-creation surface** and therefore **no new Sybil hole** — every API key is bound to exactly one Apple/Google-verified account and its single portfolio.
- **Keys are scoped to that one account.** A key can only act on its owner's portfolio (`g.user_id` ownership, same as the app — see `docs/SECURITY_AUDIT.md`). It cannot read or trade on anyone else's behalf.
- Net effect: an algo/AI trader has exactly the same one-identity-per-person ceiling as a human app user.

### 3. Price integrity — "no one but our backend can ever set a price" ✅ guaranteed
Already enforced and the API inherits it for free:

- The trade path (`execute_trade`) now **fetches the authoritative price server-side** and **ignores any client-supplied `price`** (Session 19 W3 fix).
- The inbound API will route through this **same** path and accept **only** `{ticker, side, quantity}` (or a target weight) — **there is no `price` parameter**. A caller physically cannot submit, set, or alter a price.
- Prices come exclusively from our market-data layer (`PortfolioPerformanceCalculator.get_stock_data` → AlphaVantage), served from the shared cache (see `docs/PRICE_CACHE_AND_SCALING.md`). This is a **hard invariant** of the API contract.

### 4. Outbound API (UC-D) output format — same event as email, machine-readable, not personalized
You're right: the outbound payload is the creator's **trade-notification stream**, just structured for machines instead of humans.

- **Same underlying event** as today's trade email/push (a creator bought/sold X shares of TICKER at time T).
- **Not personalized.** It's the creator's raw trade feed; the *consumer's* bot decides what to do with it (e.g. scale to its own account). We can optionally include the creator's resulting **position weight** so a follower can mirror proportionally — but the feed itself isn't tailored per subscriber.
- **Format:** JSON by default (one object per trade), with an optional **CSV export** of history. Example row:
  `{"creator":"wolff","ticker":"NVDA","side":"buy","quantity":2.5,"weight_pct":4.1,"ts":"2026-06-22T14:03:11Z"}`
- **Delivery:** pollable (`GET /api/v1/creators/{id}/trades?since=<cursor>`) and/or push (a **webhook** we POST to the subscriber's URL on each new trade — reuses the existing trade fan-out that already sends email/push).
- **How it differs from the email notification:**
  | | Trade email (today) | Outbound API feed |
  |---|---|---|
  | Audience | human, in their inbox | the subscriber's bot/program |
  | Format | prose / HTML | JSON (or CSV export) |
  | Delivery | email | poll endpoint + optional webhook |
  | Parseable | no (free text) | yes (stable schema + cursor) |
  | Personalized | no | no (raw creator stream; optional weight to enable mirroring) |
- **Access control:** identical to who gets the email/push today — **only active subscribers** of that creator can read its feed (entitlement check on the API key's account).

*(These answers resolve parts of D-1/D-2/D-3 above: keys not OAuth for v1; no price param ever; UC-D is a non-personalized structured trade feed, not a brokerage executor — real-money execution stays the consumer's responsibility, which also keeps our compliance surface smaller.)*
