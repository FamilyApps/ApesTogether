# Tomorrow's Gameplan — May 20, 2026

Last updated: 2026-05-19 ~23:15 ET

## Status snapshot (where we are tonight)

- Bot wave end-to-end is **WORKING** in dry-run mode.
  - 138/138 tickers fetched, 4 of 12 bots fired sensible trade decisions.
  - Premium AV key now correct in: local `.env`, Vercel envvars, GitHub Actions secrets.
- Phase E backend (hide-fractional flag) is **DONE**: schema migrated, backfill run, leaderboard filter param added.
- `DailyPriceBar` cache is **populated** (13,800 rows from 138 tickers × ~100 days).

## Step 0 — Morning verification (5 min, do this first)

Before any code changes, confirm the live (non-dry-run) wave fires correctly.

1. **9:45 AM ET wave 1 fires automatically** via the scheduled GH Actions cron.
2. After it finishes, in DevTools console at `apestogether.ai/admin-panel`:
   ```javascript
   fetch('/api/mobile/admin/bot/last-wave-status', { credentials: 'include' })
     .then(r => r.json()).then(d => console.log(JSON.stringify(d.waves[0], null, 2)))
   ```
3. Expected: `status: "ok"`, `bots_checked: 12`, `bots_traded` ≥ 1 (today's dry-run showed 4 bots would have traded — at least some should fire for real), `errors: []`.
4. Open the GitHub Actions run log to confirm:
   - `REALTIME_BULK_QUOTES returned 138/138 tickers` ← premium key working
   - At least one `→ BUY|SELL ... [EXECUTED]` line (NOT `[DRY RUN — not executed]`)
5. Optionally, spot-check the affected bot's portfolio in the admin panel — the new transaction should be visible.

If anything fails, STOP and triage before continuing.

## Step 1 — Quick win: gate Finnhub premium endpoints (15 min)

Saves ~2 minutes per wave (4 waves/day = 8 min/day faster).

**Change**: add `FINNHUB_PREMIUM` env var. When unset/false, skip the three Finnhub premium calls.

### Files to edit
- `bot_data_hub.py`:
  - At top of `fetch_social_sentiment()` (~line 1015): if `not os.environ.get('FINNHUB_PREMIUM')`, log "FINNHUB_PREMIUM unset — skipping social sentiment" and `return {}`.
  - Same for `fetch_analyst_data()` (~line 1079).
  - Leave `fetch_insider_data()` alone (free tier nominally works; just rate-limited tonight).
- No env var needs to be added to GH Actions secrets — absence of the flag is correct behavior.
- Document the flag at the top of `bot_data_hub.py` next to the AV key section.

### Verify
- Re-trigger wave manually (workflow_dispatch, dry-run=true). Log should show:
  ```
  INFO: FINNHUB_PREMIUM unset — skipping social sentiment
  INFO: FINNHUB_PREMIUM unset — skipping analyst data
  ```
- Total elapsed should drop from ~5m to ~3m.

## Step 2 — Phase E UI (iOS + Android, ~2-3 hours)

Web is deprecated. Mobile only.

### Backend recap (already done)
- Endpoint: `GET /api/mobile/leaderboard?hide_fractional=true` — filters out users with `user_portfolio_stats.has_fractional_holdings = true`.
- Same param works on `GET /api/mobile/top-influencers`.

### iOS
- File: `apes-together-ios/ApesTogether/Views/LeaderboardView.swift` (or equivalent FilterSheet location — check the existing filter pattern).
- Add a SwiftUI `Toggle("Hide fractional shares", isOn: $hideFractional)` to the FilterSheet.
- Persist via `@AppStorage("leaderboard_hide_fractional")` so it survives app restarts.
- Append `&hide_fractional=true` to the leaderboard fetch URL when toggle is on.
- Test: toggle ON, confirm bots with fractional holdings (any of them today?) disappear.

### Android
- File: `android/app/src/main/kotlin/com/apestogether/app/ui/screens/leaderboard/LeaderboardScreen.kt` (or equivalent FilterSheet).
- Add `Switch` composable with matching label.
- Persist via `DataStore` (preference key `leaderboard_hide_fractional`).
- Same URL param wiring.

### Copy
- iOS/Android toggle label: **"Hide fractional shares"**.
- Optional helper text: "Filter out portfolios containing partial-share holdings."

## Step 3 — Phase D: portfolio resizer (iOS + Android, ~4-6 hours)

Lets a user scale a subscribed portfolio to their own investment size.

### Design decisions needed before coding
- Where does the scale factor live? Per-subscription, or per-user-global?
- Storage: new DB column on `Subscription` table (`scale_factor FLOAT DEFAULT 1.0`)?
- UI placement: subscribed portfolio detail screen — slider or numeric input?
- Default: 1.0 (no scaling). Range: 0.01 to 100.0.

### Files likely affected
- `models.py`: add `scale_factor` column to `Subscription` (or new table).
- Migration: `migrations/20260520_add_subscription_scale_factor.py`.
- `mobile_api.py`: `GET /api/mobile/subscriptions/<id>/portfolio` returns scaled holdings.
- iOS `SubscribedPortfolioView.swift`: add slider/numeric input.
- Android equivalent.

### Open question for the user
- Should the scaled portfolio also show a scaled cash line / total value, or just the holding quantities?
- Should the scale factor be displayed on the leaderboard (e.g., "John scaled this to $50K")?

## Step 4 — Phase F: security audit (preparatory only tomorrow, ~30 min triage)

Don't execute the full audit tomorrow — just inventory and prioritize.

### Inventory pass (do tomorrow)
1. Check repo visibility: `gh repo view FamilyApps/ApesTogether --json visibility`.
2. List all GH Actions secrets and verify expected set:
   - `ADMIN_API_KEY`, `ALPHA_VANTAGE_API_KEY`, `CRON_SECRET`, `FINNHUB_API_KEY`, `INTRADAY_CRON_TOKEN`
   - Confirmed inventory tonight — these are the only 5.
3. Quick `git log --all -p | grep -E "(API_KEY|SECRET|password)"` to surface any historical leaks. Use BFG Repo-Cleaner if found.
4. List all `/admin/*` endpoints and confirm each has `@require_admin_2fa` decorator (already mostly true; spot-check the diagnose-imports and recompute endpoints added recently).

### Defer the actual remediation
Branch protection, SHA-pinned actions, OIDC, Dependabot, CodeQL enablement — do these in a focused Phase F session after Phases D and E ship.

## Step 5 — Wave efficiency: HTTP cache endpoint for GH Actions (~30 min)

**Decision: Option B (HTTP endpoint)** — confirmed by user 2026-05-19 ~23:14 ET. No DB credentials in CI; consistent with the existing AV-call-logs-over-HTTP pattern.

Saves ~60s per wave (138 daily-bar fetches → 1 cache HTTP read).

### Implementation steps

1. **New endpoint** in `api/index.py`:
   - Route: `GET /api/cron/get-cached-daily-bars`
   - Auth: reuse `verify_cron_request()` (accepts `X-Cron-Secret` or `Authorization: Bearer ...`).
   - Query param: `?tickers=AAPL,MSFT,...` (optional — default to `get_all_tickers()` if omitted).
   - Response: `{"success": true, "tickers": {"AAPL": [[date_iso, open, high, low, close, volume], ...], ...}, "fetched_at": <iso>}`.
   - Limit response size: cap bars to last 100 trading days per ticker (matches what `compute_indicators` needs).
   - Estimated payload: 138 tickers × 100 bars × 6 cols × ~10 bytes/cell ≈ 800 KB compressed. Vercel's response is gzipped by default.

2. **Update `bot_data_hub.py:_load_cached_daily_bars()`**:
   - Detect "no DB context": wrap the SQLAlchemy import in try/except. If `db` is None or query fails, fall through to HTTP path.
   - Better: detect explicit CI flag — `if os.environ.get('GITHUB_ACTIONS') == 'true'`, skip DB entirely and HTTP-fetch.
   - HTTP fetch helper: GET `{APP_BASE_URL}/api/cron/get-cached-daily-bars` with `X-Cron-Secret` header (already in env). `APP_BASE_URL` defaults to `https://apestogether.ai` if not set.
   - Parse JSON response back into `{ticker: pd.DataFrame}` matching the existing return format.
   - Cache the response in-process for the lifetime of `MarketDataHub` (don't refetch within a single wave).

3. **Test path**:
   - Locally: `curl -H "X-Cron-Secret: $CRON_SECRET" https://apestogether.ai/api/cron/get-cached-daily-bars?tickers=AAPL,MSFT | jq '.tickers.AAPL | length'`. Expect ~100.
   - In GH Actions: re-run wave, log should show `INFO: DailyPriceBar cache hit (via HTTP): 138/138 tickers` and skip the TIME_SERIES_DAILY concurrent fetch entirely.

### Files to edit
- `api/index.py`: add new endpoint near the existing `/api/cron/refresh-daily-bars` (~line 8770).
- `bot_data_hub.py`: modify `_load_cached_daily_bars()` to add HTTP fallback path. Add a tiny logger.info distinguishing "via DB" vs "via HTTP" so we can confirm which path ran.

### Edge cases to handle
- Endpoint returns 0 tickers (cache empty): log warning, fall through to live AV fetch (existing path).
- HTTP timeout (e.g., 10s): catch, log, fall through to live AV.
- Network error: same — fall through. The wave is degraded but not broken.

## Step 6 — Wire BotWaveLog writes (low priority, ~30 min)

So the admin panel `last-wave-status` shows the actual GH Actions waves (not just Vercel-cron-triggered ones).

- In `bot_agent.py` `cmd_trade()`, POST to a new `/api/admin/bot/log-wave` endpoint at the end of each wave with: `wave`, `bots_checked`, `bots_traded`, `errors[]`, `duration_ms`.
- Use `X-Admin-Key: <ADMIN_API_KEY>` auth (we already have this secret in GH Actions).
- New endpoint inserts into `BotWaveLog` table.

## Pre-1000-bot scaling (not for tomorrow — months out)

- Batch trade execution endpoint (replace 1 POST per trade with 1 POST per wave).
- Widen ticker universe to 300-500 (need to bump AV plan or chunk the daily-bars cron — currently right at Vercel's 60s limit).
- Intra-wave timing offsets to avoid DB lock contention.
- Vectorize per-archetype strategy decide() if it ever exceeds 100ms per bot.

## Open questions / unresolved items from prior sessions

- **Performance chart discrepancy for panther2585** — was mentioned in original objective but never fully resolved. Triage tomorrow: check current chart for this user, compare to expected values.
- **Vercel environment variable warnings** — user mentioned these earlier. Tomorrow: open Vercel dashboard → Project → Settings → Environment Variables, screenshot any warnings, and resolve. (Could be production-only secrets accidentally exposed to preview, or unused vars.)
- **Cron job logs location** — user wanted to know where to find them. Answer: Vercel dashboard → Project → Deployments → click latest → "Logs" tab, filter by `/api/cron/`. GH Actions logs in the Actions tab of the repo. Document this in a CRONLOGS.md if useful.
- **`price_source` column meaning** — user wanted clarification. Grep for it tomorrow and document.
- **REGN trade mis-attribution / ELV trade notification not sent / duplicate push notifications** — these were the originally-reported bugs. Tonight's work fixed the upstream infrastructure (bot wave + AV key + cache). Tomorrow: verify these specific bugs are no longer reproducing on live waves. If they recur, dig into the notification dispatch path.

## What I should do when you message me tomorrow

1. Read this file.
2. Start with **Step 0** (verify live wave).
3. Move sequentially through Steps 1 → 2 → 3 unless you redirect.
4. Step 4 (security audit triage) can fit anywhere — it's a 30-min self-contained task.
5. Steps 5 and 6 only if there's time after the bigger tasks.
