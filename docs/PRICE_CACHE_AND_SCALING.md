# Stock-Price Cache & AlphaVantage Scaling

**Date:** 2026-06-22 (Session 19) · **Tracked in:** `LAUNCH_TODO.md` W9
**Question (USER):** how short can we make the price cache (ideally ~30s for AI traders on the inbound API), how does this scale from today (2 accounts + bots) to 500 and 50,000 users, and when do we bump the AlphaVantage tier?

---

## TL;DR
- The cache cost driver is **distinct tickers priced per refresh × number of serverless instances** — *not* user count. The cache de-dupes by ticker, so 1 user or 50k users viewing AAPL is the same fetch within a window.
- We already batch with **`REALTIME_BULK_QUOTES` (≤100 symbols/call)**, which is the single biggest lever. Good.
- **The real blocker is that the cache is in-memory and PER-INSTANCE** (`portfolio_performance.py` `stock_price_cache = {}`, `cache_duration = 90`). On Vercel, M concurrent instances each fetch every ticker independently, so cost scales with instance count and shortening the TTL multiplies it.
- **Fix that one thing (shared cache) and 30s is easily affordable on the current 150/min tier, even at 50k users.** Without it, you'll hit the limit at a few hundred concurrent users.

---

## Current state (what the code does today)
- **Cache:** `portfolio_performance.py:40-42` — a module-level Python dict `stock_price_cache`, TTL `cache_duration = 90` seconds during market hours; after-hours/weekends it serves the last cached close (doesn't expire until the next close).
- **Fetch:** `get_stock_data` / batch path uses AlphaVantage **`REALTIME_BULK_QUOTES&entitlement=realtime`**, up to **100 symbols per call** (`portfolio_performance.py:137-149`). So pricing **N** distinct tickers costs `ceil(N/100)` API calls per refresh.
- **Tier:** 150 requests/min (premium).
- **Who triggers fetches:** on-demand portfolio views (`/portfolio/<slug>`, `/portfolio/<slug>/chart`), trade execution (now server-side priced — W3), bot trade waves (`bot_data_hub`), and the market-close / intraday snapshot crons.
- **Logging:** every call is recorded in `AlphaVantageAPILog` — we already have the data to build a usage dashboard.

> **Critical caveat:** because `stock_price_cache` is in-process, it is **not shared across Vercel instances** and resets on cold start. Under real concurrency the effective fetch rate is `(per-instance rate) × (active instances)`.

---

## The cost model
```
calls/min ≈ ceil(distinct_tickers / 100) × (60 / TTL_seconds) × instance_fanout
```
- `distinct_tickers` = unique symbols actively being priced (bounded — portfolios overlap heavily on popular names).
- `instance_fanout` = 1 with a **shared** cache; ≈ number of concurrent serverless instances with the **current per-instance** cache.

User growth raises cost only via (a) more distinct tickers (sub-linear — converges toward the liquid US universe) and (b) more concurrent instances fragmenting the per-instance cache.

---

## Scaling table (market-hours steady state, **assuming a shared cache** + bulk quotes)
Distinct-ticker estimates (overlap grows with users, so this is sub-linear):

| Scale | ~Distinct tickers | Calls per refresh `ceil(N/100)` | TTL 90s | TTL 60s | **TTL 30s** |
|-------|------------------:|--------------------------------:|--------:|--------:|------------:|
| Today (2 + bots) | ~80 | 1 | ~0.7/min | ~1/min | ~2/min |
| 500 users | ~300 | 3 | ~2/min | ~3/min | ~6/min |
| 5,000 users | ~800 | 8 | ~5/min | ~8/min | ~16/min |
| 50,000 users | ~2,000 | 20 | ~13/min | ~20/min | **~40/min** |

**Even at 50k users and a 30s TTL, a shared cache + bulk quotes ≈ 40 calls/min — comfortably under the 150/min tier.**

### Without a shared cache (today's per-instance cache)
Multiply the right-hand columns by the concurrent-instance count. At 50k users Vercel may run 20–50 instances at market open → `40 × 30 ≈ 1,200 calls/min`, which blows past 150 (and even the top 1,200 tier). **This is the bottleneck — not the TTL.**

---

## Can we hit ~30s (or lower) for AI traders?
- **30s: yes**, once the cache is shared (see table). No tier bump needed through 50k users.
- **Below ~30s (e.g., 5–10s):** at 50k users that's `20 × (60/10) = 120/min` — near the 150 cap. Two ways to do it safely:
  1. **Tiered TTL.** Keep 90s for general app/leaderboard display; apply a short TTL (e.g., 30s) only to the **hot set** of tickers actively traded/polled by inbound-API AI traders. This bounds the fast-refresh set to what bots actually touch.
  2. **API reads cache only — never a synchronous AV fetch per request.** The inbound API must serve prices from the shared cache (refreshed by a background/served-on-miss path), so a burst of AI polling can't multiply AV calls. 10,000 bots polling AAPL still = one fetch per window.
- **True sub-second / real-time** later isn't a REST-polling job — use a streaming provider (Polygon.io, Finnhub websockets, or Alpaca data) as a fast-follow. 30s REST-via-shared-cache fully covers launch + early-scale AI trading.

---

## When to bump the AlphaVantage tier
- Premium tiers: **75 / 150 / 300 / 600 / 1200** req/min. We're on **150**.
- **Bump when** sustained market-hours usage exceeds ~**60% of tier** (i.e., >~90/min on the 150 tier) for several days, **or** when `AlphaVantageAPILog` shows rate-limit/`Note`/`Information` throttle responses.
- With a shared cache + bulk quotes, projections say you stay well under 150/min through 50k users — so the trigger to upgrade is more likely **offering sub-30s AI pricing** than raw user growth.

---

## Recommendations (priority order)
1. **Move `stock_price_cache` to a shared store** (Postgres table `stock_price_cache(ticker PK, price, updated_at)` or Vercel KV). Same shared-store theme as the rate-limiter (audit S-1). *This is the prerequisite for both shortening the TTL and scaling users.*
2. **Inbound API serves prices from the shared cache only** — never a per-request synchronous AV fetch — so AI polling can't exhaust the quota.
3. **Tiered TTL:** 90s general; 30s hot set for AI traders.
4. **Verify all hot paths use the bulk-quote batch** (not per-ticker `GLOBAL_QUOTE`).
5. **AV usage dashboard + alert** off `AlphaVantageAPILog` (alert at 60% / 80% of tier).
6. **Stay on 150/min** through early scale; revisit when you ship sub-30s AI pricing or cross ~tens of thousands of concurrent market-hours users.

*Effort: shared cache ≈ small (one table + swap the dict accessors in `portfolio_performance.py`). It is the highest-leverage change and also de-risks the inbound API.*
