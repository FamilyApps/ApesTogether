# Performance & Portfolio Snapshots — Canonical Design

**Status:** current. **Last consolidated:** 2026-06-22 (Session 18).

> This document is the single canonical reference for how portfolio **snapshots**,
> **cash tracking**, and **performance %** work. It merges and supersedes three older
> docs, now archived under `_legacy/docs_web_era/`:
> `DESIGN_DECISIONS_EXPLAINED.md`, `PERFORMANCE_CALCULATION_AUDIT.md`,
> `PORTFOLIO_CLEANUP_PLAN.md`. Those were written in the web-era (Chart.js /
> `dashboard.html`) and described work that is now **done**; read them only for
> historical incident detail. Day-to-day bug/incident history lives in
> `ARCHITECTURE_CHANGELOG.md`; open tasks live in `LAUNCH_TODO.md`.

---

## 1. Portfolio snapshots are End-of-Day (EOD)

- A `PortfolioSnapshot` row per user per day = **EOD holdings × close prices + cash**.
- Written by the **market-close cron** (`vercel.json`: `5 20 * * 1-5` → 20:05 UTC) via
  `cash_tracking.calculate_portfolio_value_with_cash`.
- **Intraday trades are not snapshotted** at EOD: if a position is bought and sold the
  same day it isn't in the EOD holdings; the realized gain shows up as **cash**
  (`cash_proceeds`). This matches how Fidelity/Schwab/E-Trade report daily value.
- **1D intraday charts** are the exception — a separate 15-min collector
  (`/api/cron/collect-intraday-data`, market hours only) produces intraday points.

What we capture vs. not:

| Captured | Not captured |
|---|---|
| EOD value (holdings × close + cash) | Intraday high/low watermarks |
| All trades in the `Transaction` table | Multiple EOD points per day |
| Realized gains (as `cash_proceeds`) | Mid-day portfolio value (except the 1D chart) |

---

## 2. Cash-tracking model — `max_cash_deployed` + `cash_proceeds`

Two `User` fields (also stored per `PortfolioSnapshot`) make performance correct
without ever asking the user for a "starting capital":

- **`max_cash_deployed`** — cumulative capital ever deployed (only ever increases when
  *new* outside money is needed for a buy).
- **`cash_proceeds`** — uninvested cash currently on hand (from sells / dividends).

```
portfolio_value = stock_value + cash_proceeds
performance     = (portfolio_value - max_cash_deployed) / max_cash_deployed
```

**Cash-on-hand is spent before new capital** (`cash_tracking.process_transaction`
spends `cash_proceeds` before increasing `max_cash_deployed`). Worked example:

```
Day 1  Buy 10 TSLA @ $5     deployed=$50  cash=$0   value=$50   perf=0%
Day 2  Buy 5 AAPL @ $2,     deployed=$60  cash=$0   value=$65   perf=+8.33%
       TSLA -> $5.50
Day 3  Sell AAPL @ $1       deployed=$60  cash=$5   value=$60   perf=0%
Day 4  Buy 10 SPY @ $1      deployed=$65  cash=$0   value=$65   perf=0%
       (uses $5 cash + $5 new capital)
```

A **seed/`initial`** holding (declaring an existing position) counts as a buy and
sets `max_cash_deployed` at creation. (Known latent item: the onboarding
"declare existing holdings" path historically recorded `price=0` / no transaction —
tracked in `LAUNCH_TODO.md` Section A.)

---

## 3. Performance % — Modified Dietz, one source of truth

The intended formula (from `migrations/versions/20251005_add_snapshot_cash_fields.py`):

```
Return = (V_end - V_start - CF) / (V_start + W * CF)
  V_start = stock_value_start + cash_proceeds_start
  V_end   = stock_value_end   + cash_proceeds_end
  CF      = max_cash_deployed_end - max_cash_deployed_start   (net new capital)
  W       = time-weight of CF over the period
```

**History:** an audit once found *three* divergent implementations (a simple-% chart
formula, a wrong Modified-Dietz that used `total_value` baselines, and an unused
`cash_tracking.calculate_performance`). They were consolidated into a **single**
calculator — `performance_calculator.py` — which is now the source of truth for the
dashboard, leaderboard, chart cache, and admin tools. Do **not** reintroduce
per-caller performance math.

---

## 4. Chart behavior

- Charts start at the user's **first real holdings date** — no flat 0% line before the
  user owned anything (`actual_start = max(requested_start, first_holdings_date)`).
- Empty/again-missing data degrades gracefully (returns `None` / "no data" message,
  never a crash) on both backend and client.
- Deleting/rebuilding snapshots **invalidates the chart cache**
  (`user_portfolio_chart_cache`) so the next request regenerates correctly.

---

## 5. Snapshot-timing consistency (the drift lessons)

These are the rules that keep the daily chart smooth. Breaking them reintroduces
"phantom drop then recover" artifacts.

1. **One snapshot-timing semantic across every writer.** The EOD cron and any
   rebuild must agree on which day an after-close trade belongs to. The rebuild's
   `_snapshot_effective_date` uses a **20:05 UTC** cutoff to match the cron schedule
   (UTC-anchored so DST is automatic). Trades `< 20:05 UTC` apply to that day; `>=`
   roll to the next day. **Do not** change this to a naive UTC-date cutoff — it would
   include post-close trades the cron's `stock_value` didn't see → inconsistent
   `total_value`.
2. **Read-skew race (intraday writer).** `calculate_portfolio_value_with_cash` reads
   cash and holdings in two queries; a trade landing between them once produced
   spike/dip-and-revert rows. Fixed by re-reading cash and recomputing if it moved
   mid-read. Only the **1D intraday** chart + ~15-min 1D leaderboard were ever
   affected; daily snapshots replay cash from transactions and were always clean.
3. **Drift detectors** (`/admin/audit-snapshot-cash-drift`,
   `/admin/audit-snapshot-max-cash-drift`, `/admin/audit-bot-portfolio-integrity`,
   `/admin/audit-intraday-anomalies`) bucket trades by **UTC calendar date** and
   tolerate the full post-close window (`>= 20:00 UTC`), so the EOD bot-trade wave
   isn't a false positive. **Never run `?fix=true` on bots/agents** — their
   synthetically backfilled history makes the transaction-replay oracle produce
   false `-100%` drift.

See `ARCHITECTURE_CHANGELOG.md` (May 9, 2026 entries) for the full incident write-ups.

---

## 6. MarketData coverage (supporting data)

`market_data` (used to value/validate snapshots) is populated on-demand and was
historically sparse. The bot universe's `daily_price_bar` table is refreshed daily and
holds most missing closes, so two admin tools backfill cheaply:
`/admin/audit-marketdata-coverage` (read-only) and
`/admin/backfill-marketdata-from-dailybars` (+ `/admin/backfill-marketdata-av-fetch`
for held tickers outside the universe). Backfilling improves audit fidelity and any
*future* recompute; it does **not** retroactively rewrite already-stored snapshots.

---

## Pointers

- **Tasks / status:** `LAUNCH_TODO.md`
- **Incident history:** `ARCHITECTURE_CHANGELOG.md`
- **Current system design:** `CURRENT_ARCHITECTURE.md`
- **Archived originals:** `_legacy/docs_web_era/{DESIGN_DECISIONS_EXPLAINED,PERFORMANCE_CALCULATION_AUDIT,PORTFOLIO_CLEANUP_PLAN}.md`
