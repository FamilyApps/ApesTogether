# Launch TODO — Living Checklist

**Launch day: June 1, 2026** (see `docs/LAUNCH_PLAYBOOK.md` for the full day-by-day calendar)

This document is the single source of truth for what's still open before launch. Update it every session. Items are grouped by category, not by order. Within each category, items are roughly high → low priority.

**Legend:** `[ ]` open · `[~]` in progress · `[x]` done · `[!]` blocked on external dependency

---

## A. Technical / Backend

- [x] Fix CoastHillBear chart spike bug (capital-deployment-aware replay)
- [x] Add `@require_admin_2fa` to `rebuild_leaderboard_cache_single`
- [x] `FOR UPDATE NOWAIT` on leaderboard_cache SELECT — fail-fast instead of 120s hang
- [x] Drift-detection System Health card in `/admin-panel`
- [x] AlphaVantage API logging from GitHub Actions — batch endpoint + HTTP fallback in `_log_av_api_call`
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

**2026-05-09 — session ended with:**
- Chart spike fix deployed
- Leaderboard rebuild auth + lock-fast deployed (commit `8d448ab`)
- Drift indicator + AlphaVantage logging fix added (uncommitted — see `git status`)
- This LAUNCH_TODO.md created
