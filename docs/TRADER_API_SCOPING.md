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
- **Abuse caps:** max orders/min (ties to audit **S-1** — needs the shared-store rate-limiter, not the current in-memory one), max tickers, min order size; block obvious wash/ping-pong patterns that game the leaderboard.
- **Idempotency-Key** header so a retrying bot can't double-submit.
- **Market-data redistribution:** returning live prices/positions to third parties may exceed AlphaVantage/Finnhub license terms — confirm before exposing price fields, or restrict to the creator's own portfolio data (which they generated). **(Legal check required.)**

### Effort: **~Medium.** Reuses internal trade logic; net-new = API-key model, scopes, docs, the shared rate-limiter (S-1), and a developer settings screen.

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

1. **UC-A = v1 (near-launch or immediate fast-follow).** Low regulatory risk (virtual), high philosophy fit ("AI bots welcome" becomes self-serve), mostly a hardened wrapper over proven internal logic. **Hard dependency: the audit S-1 shared-store rate-limiter must land first** — a public write API without real rate-limiting is a liability.
2. **UC-D = post-launch, compliance-gated.** Start the **legal review now** (it's the long pole), pick an aggregator (**SnapTrade vs. Alpaca**), and design UC-A's trade-event model to be UC-D-ready so D is additive, not a rewrite.
3. **Do not block the store launch on either.** Both are additive platform features; ship the apps first.

---

## Open decisions (need your call)
- **D-1:** UC-A scope — orders only, or also direct holdings-set (`PUT /positions`)? (AI agents often prefer "set target weights.")
- **D-2:** Auth — API keys (recommended, simplest for devs/AI) vs. full OAuth2 client-credentials?
- **D-3:** Does UC-A expose **live prices** (market-data license question) or only the creator's own portfolio state?
- **D-4:** UC-D execution model — aggregator (SnapTrade/Alpaca) vs. bring-your-own-broker-key vs. ApesTogether-hosted bot?
- **D-5:** Are paid API creators subject to the same store-IAP subscription economics, or a separate developer tier?
- **D-6:** Rate-limit/quota tiers (free vs. paid API access)?

*Next step on approval: I can turn UC-A into an implementation plan (data model, the `/api/v1` blueprint, API-key issuance + the S-1 shared rate-limiter, OpenAPI spec) and/or open the UC-D legal/aggregator checklist.*
