# Launch TODO — Living Checklist

**Launch day: TBD — deferred until Android app is feature-complete and tested.**
Launching iOS-only with a buggy or missing Android app risks long-term reputational damage. The June 1, 2026 date is paused. The original day-by-day calendar lives in `docs/LAUNCH_PLAYBOOK.md`; treat it as a *template* now, not a deadline. Many tasks (legal, social accounts, screenshots, App Store assets) can still be completed in parallel and will compress the post-Android timeline.

This document is the single source of truth for what's still open before launch. Update it every session. Items are grouped by category, not by order. Within each category, items are roughly high → low priority.

**Legend:** `[ ]` open · `[~]` in progress · `[x]` done · `[!]` blocked on external dependency

---

## ⏰ Monday market-open checklist (next trading day)

Things to verify when the market is open and the bot pipeline is running. Hit each URL and report back.

- [ ] **Drift detector still clean.** `/admin-panel` → System Health → Cash-Tracking Drift card. Click *Run now*. After commit `34a01dc` (May 10), the drift report should be free of timing-edge false positives like `marblethehill72` 4/28 PLTR (16:05 ET) and `apex1575` 5/7 ZTS (16:04:27 ET). If those reappear, the tolerance-buffer logic is not firing.
- [ ] **AlphaVantage logging populated.** `/admin-panel` → Bot Management → Market Research Data Sources. After the 9:45 AM ET wave finishes, News (NEWS_SENTIMENT) and Movers (TOP_GAINERS_LOSERS) rows should show non-zero call counts in the last 24h. If still showing `no_calls`, the HTTP fallback isn't firing — check Vercel logs for `/admin/bot/log-av-calls` POSTs.
- [ ] **Bot trades show realistic prices.** `/admin-panel` → System Health → Recent Trades. Verify trades from this morning's wave have plausible prices (not $0.01, not $99999) and the right `Source` (`bot_research` or `bulk_api`).
- [x] **Display names render correctly on iOS.** Confirmed May 10 — app shows "The Grok Portfolio" and "Wolff's Flagship Fund" everywhere after iOS Build 32 was archived.
- [ ] **Push notifications fire for copytrade-bot trades.** After commit `8ce748c` (May 10), when a real Public.com trade-confirmation email lands and the GAS parser POSTs to `/api/mobile/admin/bot/email-trade`, bobford00 should receive a push notification on iPhone within ~30s. The endpoint response now includes a `notifications: {push_sent, email_sent, errors}` block — verify in Vercel logs.
- [ ] **panther2585 1M chart fix verified.** After applying any chart fix from this session, navigate to panther2585's portfolio → 1M period. End of chart should not show ~20% drop unless real market moves justify it.
- [ ] **bobford00 performance audit.** Verify 1D, 1W, 1M return percentages match expected market movement (since no recent trades, your performance should track your held stocks' price changes minus a rough benchmark).

---

## A. Technical / Backend

- [x] Fix CoastHillBear chart spike bug (capital-deployment-aware replay)
- [x] Add `@require_admin_2fa` to `rebuild_leaderboard_cache_single`
- [x] `FOR UPDATE NOWAIT` on leaderboard_cache SELECT — fail-fast instead of 120s hang
- [x] Drift-detection System Health card in `/admin-panel`
- [x] AlphaVantage API logging from GitHub Actions — batch endpoint + HTTP fallback in `_log_av_api_call`
- [x] `display_name` column on User + serializers + iOS Models — public-facing names that bypass the username regex
- [x] **USER ACTION**: display_name values set May 10 via Supabase SQL Editor (`UPDATE "user" SET display_name = ... WHERE username = ...`) for `marblethehill72` ("The Grok Portfolio") and `CoastHillBear` ("Wolff's Flagship Fund"). Verified rendering on iOS.
- [x] Audit-endpoint tolerance buffer for trades within ±60s of cron firing (commit `34a01dc`, May 10) — eliminates Vercel-cron-jitter false positives in `/admin/audit-snapshot-cash-drift`, `/admin/audit-snapshot-max-cash-drift`, and `/api/cron/snapshot-audit`.
- [x] Push + email notification fan-out added to copytrade-bot email-trade endpoint (commit `8ce748c`, May 10). Notifications now use `public_name` so message reads "Wolff's Flagship Fund just bought…" instead of internal username.
- [ ] **VERIFY (no rush)**: bobford00 has at least one active `device_token` row. Run in Supabase SQL Editor: `SELECT u.username, dt.id, dt.platform, dt.is_active, dt.created_at, dt.last_used_at FROM "user" u LEFT JOIN device_token dt ON dt.user_id = u.id WHERE u.username = 'bobford00';`. Zero active rows → iOS app never registered an APNs token (push will silently no-op). If empty, force a fresh app launch + grant permission to trigger registration.
- [ ] Investigate panther2585 ~20% drop at end of 1M chart — see Monday checklist for diagnostic URL
- [ ] Audit bobford00 1D/1W/1M performance — no recent trades so should track held stocks only
- [ ] Audit other `mobile_api.py` admin endpoints for missing auth — I added auth to only one in this session; others may be similarly exposed
- [ ] Ping cron `*/4 * * * *` → `/api/health` to prevent Vercel cold starts (from `IMPLEMENTATION_CHECKLIST.md:69-73`) — status unclear, verify if deployed
- [ ] Verify weekly drift-detection cron fires on schedule (first scheduled run confirms; check `/admin/cash-tracking/last-drift-check` after)
- [ ] Confirm `.env.production` has `ADMIN_TOTP_SECRET` and `ADMIN_API_KEY` set on Vercel
- [ ] Load-test `/api/mobile/feed` at 100 concurrent users

## B. iOS App

- [ ] Confirm TestFlight Build 30 includes `PerformanceChartView.swift` sparse-label change
- [ ] Visual verify CoastHillBear + your portfolio charts on every period (1D / 5D / 1M / 3M / YTD / 1Y)
- [ ] App Store Connect listing: title, subtitle, keywords, description (copy in `docs/ASO_STRATEGY.md` already drafted)
- [ ] **Replace AI-generated mockup screenshots** with real app screenshots
- [ ] App Store Connect: Privacy nutrition labels
- [ ] App Store Connect: Export Compliance answers
- [ ] Submit for App Store review (per playbook: Tue May 20)

## C. Android App — large unfinished workstream

- [ ] Google Play Console account set up
- [ ] Android app scaffolded (Kotlin / Jetpack Compose)
- [ ] Google Play Billing integration (client + backend receipt validation)
- [ ] Firebase Cloud Messaging (FCM) integration (backend + Android client)
- [ ] `/public/.well-known/assetlinks.json` for App Links deep linking (mirror of existing `apple-app-site-association`)
- [ ] 14-day Google Play closed testing window — **must start by Mon May 19 to launch June 1**
- [ ] Google Play store listing (copy already drafted in `docs/ASO_STRATEGY.md`)
- [ ] **DECISION**: if Android isn't realistically shippable by June 1, announce iOS-only launch with "Android coming soon" and scale back Android mentions on landing page

## D. Legal / Compliance

- [!] Privacy policy final version — **blocked on attorney**
- [ ] Terms of Service final review (have `ATTermsOfService03APR2026.docx`, reconcile with `/legal/terms-of-service.md`)
- [ ] Investment disclaimers audit (per LAUNCH_PLAYBOOK §11 — "never claim guaranteed returns", etc.)
- [ ] Per-store disclaimers (App Store + Play listings must say "We do not offer real brokerage services…")

## E. Website / Landing Page

- [x] Hero CTA → "Join the Beta Waitlist"
- [x] Nav CTA → "Join the Beta"
- [x] Waitlist segmentation (follow trader / earn as trader)
- [x] Urgency text, trust bar, slider default, proof card attributions, footer socials, © 2026
- [ ] **Replace app mockup image with real screenshot**
- [ ] **Create social media accounts** (X, TikTok, IG, YouTube) — LAUNCH_PLAYBOOK §3, supposed to be Day 1 (Apr 14)
- [ ] Updated screenshots for the site (depends on iOS Build 30+ being stable)
- [ ] Test OG image at opengraph.xyz
- [ ] Live waitlist counter ("Join N others on the waitlist")

## F. Testing

- [ ] End-to-end paid subscription flow with test iOS account (IAP → backend receipt validation → Xero sync → 1099 flow)
- [ ] End-to-end W-9 flow via Xero 1099 contractor group with a real paid subscriber
- [ ] Push notification delivery on both iOS + Android once FCM is live
- [ ] Chart rendering on every current bot portfolio, every period — no spikes, no empty periods where bots are old enough
- [ ] Stripe webhook handling on subscription cancellation / refund edge cases

## G. Marketing / Launch Calendar

See `docs/LAUNCH_PLAYBOOK.md` for the full 49-day calendar. The status of those items should be tracked separately in a spreadsheet or social-media scheduler, not here. This section only tracks **deviations and misses**.

- [ ] LAUNCH_PLAYBOOK Phase 1 (Apr 14–20): social accounts were supposed to be set up Day 1 — confirm this happened. If not, **everything downstream in the content calendar is compressed**.
- [ ] LAUNCH_PLAYBOOK Day 22 (Mon May 5): "Upload to TestFlight + Play Console. Invite 12+ Google Play testers (14-day clock starts)." — Google Play side likely not done; see section C decision
- [ ] LAUNCH_PLAYBOOK Day 33 (Fri May 16): "Verify Google Play 14-day gate passed" — impossible if testing didn't start May 5
- [ ] LAUNCH_PLAYBOOK Day 37 (Tue May 20): "Submit App Store + Google Play listings for review" — plan for this week

## H. Operations / Data

- [ ] AlphaVantage News/Movers/Prices (fallback) showing `no_calls` in admin panel — fix shipped this session, verify after next bot-trading wave runs
- [ ] Bot trade decisions cross-checked against AV sentiment data (sanity: do momentum bots actually trade differently on news-positive vs news-negative days?)
- [ ] Xero sync — confirm daily subscription revenue and 70% payout sync still running cleanly
- [ ] Xero — ghost subscriber tracking matches expected month-end payouts

---

## Session cadence

At the start of each session, the assistant should:

1. Read this file
2. Ask which open item(s) to work on
3. Update status as items complete

At the end of each session, the assistant should:

1. Check off items finished in the session
2. Add any newly discovered items to the relevant category
3. Commit the updated file alongside any code changes

---

## Last updated

**2026-05-10 (midday) — session 3 ended with:**
- Audit tolerance buffer shipped (commit `34a01dc`) — Vercel cron jitter ±60s false positives no longer flagged.
- Display name values set in DB for `marblethehill72` and `CoastHillBear`. iOS Build 32 archived, names confirmed rendering.
- Copytrade-bot email-trade endpoint now fans out push + email to subscribers (commit `8ce748c`). Trade notifications switched from raw username to `public_name`.
- Pending: verify push delivery on next real Public.com trade email; verify bobford00 has a `device_token` row.
- Reviewed Section G launch-calendar reality: at Day 27 of 49, Phase 1 social-media foundation is unstarted. June 1 launch is officially deferred (LAUNCH_TODO line 4); see launch-playbook walkthrough below for re-sequenced priorities.

**2026-05-09 (afternoon) — session 2 ended with:**
- Drift indicator card live, drift check returned "Clean" (13 users scanned, $1.00 threshold)
- AlphaVantage logging fix shipped (verify Mon at 9:45 AM ET wave)
- iOS Build 31 archived from local Mac
- Discovered `display_name` field never existed; the past "rename usernames" request was effectively a no-op (validation regex blocks spaces/apostrophes/uppercase). Implemented full `display_name` column + iOS Codable + 8 backend serializers + 6 Swift views in this session.
- Launch date deferred from June 1, 2026 to TBD pending Android completion.
- panther2585 ~20% 1M chart drop and bobford00 performance audit pending — diagnostic URLs queued in Monday checklist.

**2026-05-09 (morning) — session 1 ended with:**
- Chart spike fix deployed
- Leaderboard rebuild auth + lock-fast deployed (commit `8d448ab`)
- Drift indicator + AlphaVantage logging fix added
- This LAUNCH_TODO.md created
