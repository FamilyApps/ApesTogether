# Bot Research Data Adequacy — Per-Sector Assessment (owed write-up #2)

**Status:** Produced 2026-06-24 (Session 19). This is the analysis promised in `LAUNCH_TODO.md` §2 ("#2 Per-sector data adequacy incl. real estate & healthcare"), which had never been written.

**Question being answered:** Do the current bot data sources — AlphaVantage `NEWS_SENTIMENT` (topic-based) + `TOP_GAINERS_LOSERS` + Finnhub social/analyst/insider — give the bots **enough signal in thin sectors** (the USER specifically called out **real estate** and **healthcare**)? Where there are gaps, what extra data services close them?

**TL;DR:**
1. The stack is **adequate for what the product actually is** — a generator of *realistic, varied, plausible* virtual trading behavior, not an alpha engine. Every sector has full technical coverage, and the existing per-ticker **dead-leg reweighting** keeps trade decisions sensible when alt-data is missing.
2. It is **structurally thin in exactly the two sectors the USER flagged**, because those sectors' true drivers are not in the data set: **Real Estate** trades on *interest rates / FFO / cap rates*; **biotech (within Healthcare)** trades on *FDA decisions / clinical-trial readouts*. None of these are inputs today.
3. On the **current free Finnhub tier two of the four alt-data legs are dead** (social + analyst return 403 and are skipped). So in practice today's non-price signals are just **AV news sentiment + insider transactions + top movers**.
4. **Highest ROI fix is nearly free:** four AlphaVantage endpoints already included in the $99.99/mo Premium plan (`EARNINGS_CALENDAR`, `DIVIDENDS`, `OVERVIEW`, `TREASURY_YIELD`/`FEDERAL_FUNDS_RATE`) would (a) give the `earnings` archetype the earnings-date input it currently lacks, (b) feed `dividend_growth`/REIT scoring, and (c) hand Real-Estate bots a rates signal — at **zero incremental cost**.

---

## 1. What the bots actually consume today

Grounded in `bot_data_hub.py` and `bot_strategies.py`.

### Data sources
| Provider | Endpoint | Used for | Status |
|---|---|---|---|
| AlphaVantage Premium ($99.99/mo, 150/min) | `REALTIME_BULK_QUOTES` | current price, 100 symbols/call | **Primary**, healthy |
| " | `TIME_SERIES_DAILY` | 100-day OHLCV → `DailyPriceBar` cache | healthy (daily cron) |
| " | `NEWS_SENTIMENT` | topic-based news sentiment | healthy (8 topics) |
| " | `TOP_GAINERS_LOSERS` | daily market-wide mover screen | healthy |
| yfinance (free) | bulk OHLCV | fallback only | unreliable on Vercel IPs |
| Finnhub (free, 60/min) | `stock/social-sentiment` | Reddit/Twitter buzz | **DEAD — 403 on free tier, skipped** |
| " | `stock/upgrade-downgrade` | analyst actions | **DEAD — 403 on free tier, skipped** |
| " | `stock/insider-transactions` | insider buy/sell net | **works on free tier** |

`FINNHUB_PREMIUM` (env flag) gates the two dead legs off entirely so they don't waste ~2 min/wave on rate-limit pauses (`bot_data_hub.py:60-66`).

### Signals merged per ticker (`MarketDataHub.get_stock_data`, `bot_data_hub.py:1449`)
- **Technical (local compute from bars + spliced intraday quote):** `rsi`, `macd`, `volume`, `price_trend`.
- **News:** `news_sentiment`, `news_buzz`, `article_count` (AV).
- **Social:** `social_mentions`, `social_sentiment`, `social_ratio` (Finnhub — **0 on free tier**).
- **Analyst:** `analyst_action` (Finnhub — **'none' on free tier**).
- **Insider:** `insider_net` (Finnhub — works).
- **Mover:** `mover_status` from `TOP_GAINERS_LOSERS`.

### How signals become trades
`STRATEGY_TEMPLATES` (10 archetypes, `bot_strategies.py:33`) weight `{rsi, macd, news_sentiment, social_buzz, volume, insider, price_trend}` (the `analyst` component shares the `insider` weight). A Dirichlet sample around each archetype yields thousands of distinct bot profiles.

**Critical mitigation already in place** — `compute_signal_components` (`bot_strategies.py:338-375`) detects *per-ticker* dead legs (`social_mentions==0`, `article_count==0`, no insider/analyst) and **redistributes that weight to the live signals**, so a bot that nominally weights social 35% doesn't get permanently stuck below its buy threshold when social is dead. This is why missing alt-data degrades gracefully into "technical + whatever's live" rather than breaking the bot.

### Universe (`UNIVERSE`, `bot_data_hub.py:71`)
Technology 24 · Healthcare 20 · Finance 16 · Energy 16 · Consumer 16 · Industrial 16 · **Real Estate 14** · ETF 16. All names are large-cap, liquid → clean technicals everywhere.

### News topic → sector coverage (`ALPHA_NEWS_TOPICS`, `bot_data_hub.py:771`)
`technology, finance, life_sciences (≈Healthcare), energy_transportation, manufacturing (≈Industrial), real_estate, retail_wholesale (≈Consumer), economy_macro`. **Every UNIVERSE sector has a matching topic** — so news coverage is *present* for all sectors; the issue is *depth/volume*, not absence.

---

## 2. Per-sector adequacy

Legend: ✅ strong · ⚠️ thin-but-usable · ❌ missing/structural gap.

| Sector | Technicals | News | Top movers | Insider (free) | Social/Analyst (free=dead) | Sector-specific driver coverage | Verdict |
|---|---|---|---|---|---|---|---|
| Technology | ✅ | ✅ rich | ✅ frequent | ⚠️ | ❌ (social would help most here) | earnings ⚠️ | **Good** |
| Finance | ✅ | ✅ | ⚠️ | ⚠️ | ❌ | rates ❌, earnings ⚠️ | **OK** |
| Consumer | ✅ | ✅ | ⚠️ | ⚠️ | ❌ | earnings ⚠️ | **OK** |
| Energy | ✅ | ✅ | ⚠️ | ⚠️ | ❌ | commodity price ❌ | **OK** |
| Industrial | ✅ | ⚠️ medium | ⚠️ | ⚠️ | ❌ | macro/PMI ❌ | **OK** |
| **Healthcare** | ✅ | ✅ big-pharma / ⚠️ biotech | ⚠️ (large-caps rarely move-screen) | ⚠️ | ❌ | **FDA / trial readouts ❌** | **Thin for biotech** |
| **Real Estate** | ✅ | ⚠️ low REIT news volume | ❌ REITs ~never in mover screen | ⚠️ sparse | ❌ (REITs have ~no retail buzz) | **rates / FFO / cap-rate ❌** | **Structurally thin** |

### Real Estate — the clearest gap
- Technicals are fine, so momentum/swing/sector_rotation bots still behave plausibly.
- But REIT prices are dominated by **interest-rate moves, FFO, occupancy and dividend yield** — *none* are inputs. News volume on individual REITs is low, so `article_count` is often 0 → news leg gets reweighted away → these bots are effectively **pure-technical**.
- Social is irrelevant for REITs even if enabled (no Reddit/Twitter buzz on `O` or `PLD`).

### Healthcare — fine for big pharma, thin for biotech
- `JNJ/UNH/PFE/LLY` get solid `life_sciences` news coverage.
- **Biotech (`VRTX`, `REGN`) is driven by binary catalysts** — FDA PDUFA dates, Phase II/III readouts — which can move a stock 30–50% in a day. AV `NEWS_SENTIMENT` catches *some* of this as generic news but there is **no structured FDA/trial calendar**, so bots can't anticipate or properly weight these events.

---

## 3. Recommendations (tiered by cost and effort)

### Tier 0 — Free within the existing AV Premium plan (do first; highest ROI)
These are **already paid for** — only integration work in `bot_data_hub.py` + a weight in `bot_strategies.py`:
1. **`EARNINGS_CALENDAR` / `EARNINGS`** — earnings dates + surprises. The `earnings` archetype (`bot_strategies.py:94`) currently has **no earnings-date input at all**; it proxies via news/analyst. This is the most glaring "we built a strategy without its key signal" gap, and it helps **every** sector.
2. **`TREASURY_YIELD` + `FEDERAL_FUNDS_RATE`** (AV economic indicators) — **directly addresses Real Estate**. Feed the 10Y-yield trend as a sector tailwind/headwind into REIT + `sector_rotation` scoring. Also benefits Finance.
3. **`DIVIDENDS`** — proper input for `dividend_growth` (`bot_strategies.py:139`) and REIT yield scoring.
4. **`OVERVIEW` fundamentals** (already fetched for sector classification in `stock_metadata_utils.py`) — surface P/E, dividend yield, market cap to `value`/`dividend_growth` bots instead of discarding them.

### Tier 1 — Targeted paid add-ons for the two flagged sectors
5. **Healthcare/biotech catalysts:** start with **openFDA** (free) for drug approvals; add **Benzinga FDA/Calendar API** (paid) if biotech becomes a focus. Closes the single biggest *sector-specific* gap.
6. **Revive the dead Finnhub legs** by upgrading Finnhub to a paid tier and setting `FINNHUB_PREMIUM=true`. This turns analyst upgrades/downgrades + social back on — the strategies *already weight them*, so it's pure upside, and analyst coverage especially helps Healthcare. (Validate the specific plan that includes `upgrade-downgrade` + `social-sentiment` before paying.)

### Tier 2 — Only if the bot product becomes a core differentiator / at scale
7. **Financial Modeling Prep (FMP)** (~$22–70/mo) — one API for fundamentals + earnings calendar + analyst estimates + insider across all sectors; could consolidate several AV/Finnhub gaps cheaply.
8. **Polygon.io** ($29–199/mo) — stronger/cheaper real-time + reference + news at scale than AV.
9. **Tiingo** (~$10–50/mo) — cheap news + fundamentals.
10. **Commodity prices** (AV `WTI`/`BRENT`/`NATURAL_GAS`, free in Premium) for Energy if that sector is prioritized.

---

## 4. Bottom line

- **Adequate for launch.** The product needs believable, diverse virtual traders, and the technical + news + insider stack plus dead-leg reweighting delivers that across all sectors.
- **The USER's instinct is correct:** Real Estate and biotech are the thin spots, and the reason is *missing sector-specific drivers* (rates/FFO; FDA/trials), not a general data outage.
- **Before spending anything**, wire in the four Tier-0 AlphaVantage endpoints — they fix the empty `earnings` strategy and the Real-Estate rates gap for free.
- **Next dollar** is best spent reviving Finnhub analyst/social (helps all sectors) and an openFDA→Benzinga biotech catalyst feed (fixes Healthcare's binary-event blind spot).

*Scope note:* This concerns the **internal bot research engine** only. It is distinct from the external **Trader API** (`docs/TRADER_API_SCOPING.md`) and from the separate "#3 external AI stock-picking model" research item, both of which remain open in `LAUNCH_TODO.md` §2.
