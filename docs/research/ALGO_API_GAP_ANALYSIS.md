# Algo-Trader API Ecosystem — Research & Gap Analysis vs. Our API Plan

**Date:** 2026-09-01 · **Status:** Research track B deliverable (owner-requested) · **Plan under review:** `docs/TRADER_API_SCOPING.md` (UC-A Creator API)
**Question:** what do algo traders actually use, and does our planned API meet them where they are?

---

## 1. The ecosystem in 2026 — who our target developers already are

### 1a. Alpaca — the de facto retail algo standard (our primary compatibility target)
Every 2026 comparison ranks Alpaca the "unambiguous first choice" for retail algo devs. Its conventions ARE the retail algo dialect:
- **Auth:** static API key + secret headers (no OAuth dance, no local gateway process)
- **Orders:** `POST /v2/orders` with `{symbol, qty | notional, side, type, time_in_force, client_order_id}` — fractional `qty` AND dollar-`notional` supported
- **Idempotency/tracking:** `client_order_id` (caller-supplied), queryable by it
- **Paper mode:** free, first-class (`paper=True` in SDK) — the norm devs expect everywhere
- **SDK:** `alpaca-py` (Python is the lingua franca; JS second)
- **Streaming:** WebSocket `trade_updates` for order-state changes
- **MCP:** official `alpaca-mcp-server` (65 tools, uvx-installable; Claude/ChatGPT/Cursor) — but **self-host only; Alpaca offers NO hosted remote MCP** (their docs: "remote hosting not yet available")

### 1b. Interactive Brokers — pro-grade, high-friction
Socket-based TWS API requiring a running local gateway; most powerful, worst DX. Its users want multi-asset REAL execution — mostly not our persona. **No compatibility action needed.**

### 1c. Tradier / TradeStation / Schwab / Robinhood
Tradier = options-centric REST with OAuth2 (the OAuth is cited as friction for server-side bots — validates our API-key decision, D-2). Others retail-oriented, less algo-native. **No compatibility action needed** beyond noting options are a future asset class.

### 1d. TradingView — the LARGEST population of retail "algo" traders
- ~269M monthly visits (Mar 2026), 100k+ published Pine Scripts; strategy alerts fire **webhook JSON POSTs**
- An entire bridge industry exists ONLY to convert these alerts into broker orders (TradersPost, WunderTrading, 3Commas, Alertatron, SignalForge…) — users pay monthly + run VPSs just for the plumbing
- Community payload convention: `{"action":"buy","symbol":"{{ticker}}","qty":{{strategy.order.contracts}}}` + a secret token + bar-timestamp dedupe key; guidance is always "once per bar close"
- **Key insight: most "algo traders" never touch a broker API.** They write Pine, and the alert webhook IS their bot.

### 1e. AI agents / MCP (the newest cohort — and OUR brand)
"AI trader" increasingly literally means an LLM with MCP tools. Alpaca ships an official MCP server as a headline feature. Clients: Claude Desktop/Web/Mobile, ChatGPT, Cursor, Gemini CLI. Their gap: **no hosted option** (self-host burden). Because OUR trades are virtual, we can safely offer what a real-money broker hesitates to: a **hosted remote MCP connector**.

### 1f. Explicitly out of scope for us (fine to say no)
- **HFT / streaming data strategies** — our delayed pricing makes this impossible by design; positioning: "minutes matter, microseconds don't" (a track-record venue, not an execution venue)
- **FIX protocol, QuantConnect LEAN plugin, futures/FX** — institutional/other-asset ecosystems; revisit only on demand
- **Crypto (ccxt) / MT5 crowd** — different venues; the roadmap's prediction-markets item is the eventual answer

---

## 2. Gap analysis — TRADER_API_SCOPING.md UC-A vs. the ecosystem

### Already aligned (no change)
| Plan item | Ecosystem verdict |
|---|---|
| API keys over OAuth (D-2) | ✔ Correct — matches Alpaca; Tradier's OAuth is documented friction |
| REST `/api/v1/orders` + GET/DELETE, portfolio/positions/fills | ✔ Matches the standard surface |
| No `price` param, server-side pricing | ✔ Universal model; also our hard invariant |
| Idempotency requirement | ✔ Right idea — but see G-1 for the dialect |
| Rate limits + quota headers | ✔ Standard practice |
| Paper trading | ✔ We ARE the paper environment — a selling point, not a caveat |

### Gaps (priority order)

**G-1 — Speak the Alpaca dialect (cheap now, expensive to retrofit).**
Adopt Alpaca-compatible names/enums verbatim in v1: `symbol`, `qty`, `notional`, `side: buy|sell`, `type: market`, `time_in_force: day`, `client_order_id`; order lifecycle `accepted → filled | canceled` (+ our `queued` for after-hours). Accept `client_order_id` AS the idempotency key (keep the `Idempotency-Key` header as an alias). Result: porting an existing alpaca-py bot ≈ change base URL + keys.

**G-2 — Notional + fractional orders.**
Fractional already works internally (house bots trade 2.5-share lots). Add `notional` ("buy $500 of NVDA") — compute qty server-side at fill price. Agents and TradingView payloads both prefer it.

**G-3 — TradingView webhook receiver (biggest funnel, small build).**
`POST /api/v1/webhooks/tradingview?token=<per-user-webhook-token>` accepting the community payload (`action`/`side`, `symbol`/`ticker`, `qty`/`notional`, optional `k` dedupe key). It's a translation shim in front of the same order path. **We uniquely need no bridge**: the "broker" is us and the money is virtual — a Pine user pastes ONE URL into their alert dialog and their strategy is live on the leaderboard. Publish copy-paste alert templates with TradingView placeholders. Security: webhook token ≠ API key (scoped to order-submit only), dedupe on `k`/bar-timestamp, document once-per-bar-close.

**G-4 — MCP server, and host it (brand-defining differentiator).**
`apestogether-mcp` (pip/uvx) exposing v1 as tools: `submit_order`, `get_portfolio`, `get_positions`, `get_fills`, `get_performance`, `get_leaderboard`. Then go where Alpaca can't: a **hosted remote MCP connector** (Claude/ChatGPT web+mobile take a URL + key — zero install). Real-money brokers fear hosting this; our virtual-money model makes the blast radius acceptable. "AI bots welcome" becomes: *add our connector, tell Claude to trade.* Feeds X-03/X-16/#X-ROADMAP content directly.

**G-5 — Python SDK.**
Thin `apestogether` pip package mirroring alpaca-py ergonomics (`TradingClient(api_key).submit_order(...)`). Generate from the planned OpenAPI spec; JS via codegen later.

**G-6 — Outbound order-status webhook (creator-side).**
Our after-hours queue means fills often happen at next open, when the bot isn't watching. Alpaca solves with WebSocket streams; serverless-cheap equivalent: caller registers a webhook URL, we POST on fill/cancel. WebSocket only if demand proves it.

**G-7 — Sandbox that protects the public track record (design decision needed).**
Industry norm: test in paper before live. Our twist: the portfolio IS the user's public track record — integration bugs would pollute it, but one-account-one-portfolio is the anti-Sybil rule. Proposal: per-account **scratch sandbox portfolio** — API-only, never public, never leaderboard-eligible, resettable on demand (`/api/v1/sandbox/reset`), selected by key type (sandbox key vs live key, Alpaca-style). Preserves the Sybil ceiling (still one account) while matching the test-first workflow every dev expects.

**G-8 — Market clock/calendar endpoints.**
`GET /api/v1/clock` (is_open, next_open, next_close) + `GET /api/v1/calendar`. Trivial (expose existing market-hours logic) and universally expected; doubly important for us so bots understand the after-hours queue semantics.

**G-9 — Market data stance (resolves D-3).**
Serve only (a) the creator's own portfolio state and (b) — license permitting — the delayed quotes we already cache, clearly labeled `delayed`. Document "bring your own data" (yfinance/Alpaca-data/Polygon) as the intended pattern. We are a track-record venue; data vending invites license risk (AlphaVantage redistribution) for zero differentiation.

### Open-decision updates this research resolves
- **D-1:** v1 = orders only, Alpaca-dialect. Add declarative `PUT /api/v1/positions/targets` (set target weights) in v1.1 — AI agents like it, but TradingView + ported bots think in orders first.
- **D-2:** CONFIRMED API keys. OAuth is documented ecosystem friction.
- **D-3:** Resolved per G-9.
- **NEW D-7:** approve the sandbox-portfolio design (G-7)?
- **NEW D-8:** hosted MCP (G-4) — ship self-host first, hosted fast-follow? Hosting cost is one thin service; payoff is category-of-one marketing.

---

## 3. Recommended build order (v1 → v1.2)
1. **v1 core (per existing plan + G-1/G-2/G-8):** Alpaca-dialect orders/portfolio/positions/fills + clock, API keys, tiered rate limits, quota headers, OpenAPI spec
2. **v1 launch companions (G-3, G-5):** TradingView webhook receiver + copy-paste Pine templates; `apestogether` pip package
3. **v1.1 (G-4, G-6, G-7):** MCP server (self-host, then hosted), outbound fill webhooks, sandbox keys
4. **v1.2 (D-1 part 2):** target-weights endpoint for rebalance-style agents

**The pitch that falls out of this research:** *"If your bot speaks Alpaca, it already speaks ApesTogether. If your strategy lives in TradingView, one webhook URL puts it on the leaderboard. If your trader is Claude, add our connector."* — three sentences covering ~everyone in 1a/1d/1e.
