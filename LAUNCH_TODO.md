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
- [ ] **🚨 SECURITY (pre-launch blocker): Verify Google/Apple ID tokens properly.** `mobile_api.py:/auth/token` (line ~1576) currently decodes ID tokens with `verify_signature=False` — comment says `"development only!"`. Any actor with any valid Google ID token can authenticate as any user by forging a `sub` claim. Fix: use `google.oauth2.id_token.verify_oauth2_token` against a whitelist of accepted `aud` values (iOS Client ID from `GoogleService-Info.plist`, Android Web Client ID from `secrets.properties`, and the legacy web `GOOGLE_CLIENT_ID` if web sign-in is still in use). Same fix needed for Apple — verify against Apple's JWKS. MUST be fixed before public launch.
- [ ] Ping cron `*/4 * * * *` → `/api/health` to prevent Vercel cold starts (from `IMPLEMENTATION_CHECKLIST.md:69-73`) — status unclear, verify if deployed
- [ ] Verify weekly drift-detection cron fires on schedule (first scheduled run confirms; check `/admin/cash-tracking/last-drift-check` after)
- [ ] Confirm `.env.production` has `ADMIN_TOTP_SECRET` and `ADMIN_API_KEY` set on Vercel
- [ ] Load-test `/api/mobile/feed` at 100 concurrent users
- [ ] Cash-Tracking-Drift card on `/admin-panel` System Health: shows "never been run" even after a successful manual run. Likely the timestamp display reads from a stored `last_drift_check` record that isn't updated on the synchronous "Run now" path. Low priority polish — functionality is correct (clean result is being computed), only the timestamp text is stale.
- [x] Audit-cron email: fall back to `ADMIN_EMAIL` if `ADMIN_NOTIFY_EMAIL` is unset (commit pending May 10) — eliminates need for a duplicate Vercel env var; alerts will go to `fordutilityapps@gmail.com`.

## B. iOS App

- [ ] Confirm TestFlight Build 30 includes `PerformanceChartView.swift` sparse-label change
- [ ] Visual verify CoastHillBear + your portfolio charts on every period (1D / 5D / 1M / 3M / YTD / 1Y)
- [ ] App Store Connect listing: title, subtitle, keywords, description (copy in `docs/ASO_STRATEGY.md` already drafted)
- [ ] **Replace AI-generated mockup screenshots** with real app screenshots
- [ ] App Store Connect: Privacy nutrition labels
- [ ] App Store Connect: Export Compliance answers
- [ ] Submit for App Store review (per playbook: Tue May 20)

## C. Android App — large unfinished workstream

**DECISION (May 10, 2026): Native Android in Kotlin / Jetpack Compose.** Wait for Android before public launch. No launch date set until Android is "fairly bug-free." Target: 1–2 weeks of focused Android work, then beta + parity verification, then begin marketing outreach in earnest.

### Foundation (completed May 10, session 3 — see commit + `android/README.md`)

- [x] Android project scaffolded under `/android/` (Kotlin 2.0 / Compose / Hilt / Retrofit / kotlinx.serialization / DataStore + EncryptedSharedPreferences / Vico / Firebase / Play Billing). Min SDK 26, Target SDK 34.
- [x] Networking layer (`ApiService.kt`, `AuthInterceptor.kt`, `ApiModule.kt`) — mirrors iOS `APIService.swift` 1:1. All read endpoints + auth + device registration + IAP validate + notification settings + trade execution + add stocks + tax status.
- [x] Models (`data/models/Models.kt`) — full port of iOS `Models.swift` with `display_name` → `displayName` + `publicName` extension property. snake_case fields handled via `@SerialName`.
- [x] Auth layer: `TokenStore` (encrypted) + `AuthRepository` with Google Sign-In via Credential Manager API (modern replacement for deprecated GoogleSignIn lib).
- [x] FCM push: `ApesFirebaseMessagingService` listens for trade-alert payloads, registers FCM tokens via `/device/register?platform=android`. Uses the same backend `push_notification_service.notify_subscribers_of_trade` already serving iOS.
- [x] App Links: AndroidManifest declares `https://apestogether.ai/p/<slug>` intent filter with `autoVerify=true`. `/public/.well-known/assetlinks.json` added with placeholder SHA-256 fingerprints. `vercel.json` updated to serve it as `application/json`.
- [x] Theme/Color/Type: 1:1 port of iOS `Theme.swift` palette (PrimaryAccent #00D9A5, AppBackground #0A0F0D, Gains #22C55E, Losses #EF4444).
- [x] Navigation: Compose Navigation graph with Login → MainTabs (4 tabs) + PortfolioDetail + Settings.
- [x] Stub screens for all 4 tabs + PortfolioDetail + Settings (Login + Leaderboard + Settings have real impls; the rest are placeholders that compile and route correctly).
- [x] Backend `/purchase/validate` already accepts `platform: "google"` + `purchase_token` and `iap_validation_service.py` already validates against Google Play Developer API. **No backend code changes required for Android billing**, only env var setup (see Section H).

### USER ACTIONS — required before the Android app builds locally

- [x] **Google Play Console** account paid (May 11, $25 one-time, Family Apps LLC). App listing creation with package `com.apestogether.app` still pending — needed before a real release SHA-256 fingerprint is available.
- [x] **Firebase project**: Android app `com.apestogether.app` registered (May 10). `google-services.json` downloaded and placed at `android/app/google-services.json` (gitignored). Debug SHA-1 added to Firebase.
- [x] **Google Cloud OAuth Web client** created ("ApesTogether Web Client") + Android client ("ApesTogether Android Client") with package `com.apestogether.app` + debug SHA-1. Web Client ID needs to be pasted into `android/secrets.properties`. Existing `GOOGLE_CLIENT_ID` Vercel env var ("Stock portfolio web client") is for the web app's Authlib redirect flow — leave it alone.
- [x] **Gradle wrapper generated** by Android Studio Panda on first sync (May 10).
- [ ] **Replace assetlinks.json placeholders**: `public/.well-known/assetlinks.json` has `REPLACE_WITH_RELEASE_SIGNING_CERT_SHA256` + `REPLACE_WITH_PLAY_APP_SIGNING_CERT_SHA256`. Get debug SHA-256 from `gradle :app:signingReport` (already done; save it), release SHA-256 comes from Play Console once the app listing is created and a release artifact is uploaded.

### Screens still to port from iOS

- [x] LeaderboardView filter pills + sparklines (commits `ca17442`, `988e93c`)
- [x] TopInfluencersView (commit `d396ad8`)
- [x] MyPortfolioView (commit `58b0be6`)
- [x] SubscriptionsView (commit `58b0be6`, import fix `e6b7cfd`)
- [x] PortfolioDetailView (commit `58b0be6`)
- [x] PerformanceChartView via Vico (included in PortfolioDetail port `58b0be6`)
- [x] Google Play Billing on PortfolioDetailScreen Subscribe CTA (commit `feb85f2`) — BillingClient connect + querySkuDetails + launchBillingFlow + acknowledgePurchase + POST `/purchase/validate` all wired.
- [x] Onboarding flow — WelcomeCarouselView, ReferralPreviewView, EarnNudgeView, AddStocksView (commit `d1e20c3`)
- [x] CompactPlanToggle iOS port (Save 36% pill + price-prominent typography, commit `9b65fd9`)
- [x] App icon + themed-icons monochrome silhouette (commits `ca17442` through `e212107`, May 11). Photopea-flattened silhouette rescaled to align with foreground bbox.
- [ ] LegalText.swift content → assets/legal/ + SettingsScreen linkouts (status unverified, needs check)
- [ ] FeaturePollView, TradeSheetView, W9FormView, PortfolioShareCardView (lower priority, not strictly needed for v1)
- [ ] Settings TODOs deferred to v1.1: Payment History screen, Tax Info / W-9 sheet, FAQ link (iOS also hasn't shipped these; matches parity)

### Pre-launch testing

- [ ] Google Sign-In → token exchange → `/auth/user` round trip on a real device
- [ ] Trade-alert FCM push delivers while app backgrounded
- [ ] App Link from `https://apestogether.ai/p/<slug>` opens PortfolioDetailScreen (verified with `adb shell pm verify-app-links --re-verify com.apestogether.app`)
- [ ] Subscribe via Play Billing → backend validation → MobileSubscription row appears
- [ ] 14-day Google Play closed-testing window for Production track release

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
- [x] **App mockup is a real screenshot** (May 10 confirmation; pricing in screenshot is dated but acceptable for now — refresh closer to launch)
- [ ] Refresh landing screenshot once iOS app is final (current one has old pricing)
- [ ] **Create social media accounts** (X, TikTok, IG, YouTube) — LAUNCH_PLAYBOOK §3. Originally Day 1 (Apr 14), now: do this weekend before Android work begins, just to lock the handles.
- [ ] Test OG image at opengraph.xyz
- [ ] Live waitlist counter ("Join N others on the waitlist")

## F. Testing

- [ ] End-to-end paid subscription flow with test iOS account (IAP → backend receipt validation → Xero sync → 1099 flow)
- [ ] End-to-end W-9 flow via Xero 1099 contractor group with a real paid subscriber
- [ ] Push notification delivery on both iOS + Android once FCM is live
- [ ] Chart rendering on every current bot portfolio, every period — no spikes, no empty periods where bots are old enough
- [ ] Stripe webhook handling on subscription cancellation / refund edge cases

## G. Marketing / Launch Calendar

**The original Apr 14 – Jun 1 calendar in `docs/LAUNCH_PLAYBOOK.md` is now a template, not a deadline.** Sequencing reset on May 10:

1. Finish iOS stability + paid-sub E2E test + App Store assets (1–2 weeks)
2. Build native Android app (Kotlin/Compose) to feature parity (target: 1–2 weeks of focused work, plus 14-day Google Play closed-testing gate)
3. Beta both apps, fix bugs, declare "fairly bug-free"
4. **Then** set a launch date and run the social-media + outreach phases of LAUNCH_PLAYBOOK at full speed

This section only tracks **deferred / dropped items**:

- [ ] LAUNCH_PLAYBOOK Day 38 — **$2 bill stunt deferred**. Don't order bills until launch week is in sight.
- [ ] LAUNCH_PLAYBOOK Phase 1 social accounts: defer daily posting; only goal this weekend is to **register the handles** (X, TikTok, IG, YouTube, LinkedIn for the company) before someone else takes them. No posting yet.
- [ ] LAUNCH_PLAYBOOK Day 22 (Mon May 5): "Upload to TestFlight + Play Console. Invite 12+ Google Play testers (14-day clock starts)." — Google Play side gated on Section C completion.
- [ ] LAUNCH_PLAYBOOK Day 33 (Fri May 16): "Verify Google Play 14-day gate passed" — recompute target date once Section C scaffolding is done.
- [ ] LAUNCH_PLAYBOOK Day 37 (Tue May 20): "Submit App Store + Google Play listings for review" — recompute.

## H. Operations / Data

- [ ] AlphaVantage News/Movers/Prices (fallback) showing `no_calls` in admin panel — fix shipped this session, verify after next bot-trading wave runs
- [ ] Bot trade decisions cross-checked against AV sentiment data (sanity: do momentum bots actually trade differently on news-positive vs news-negative days?)
- [ ] Xero sync — confirm daily subscription revenue and 70% payout sync still running cleanly
- [ ] Xero — ghost subscriber tracking matches expected month-end payouts
- [ ] Vercel env: `GOOGLE_PLAY_SERVICE_ACCOUNT_JSON` for Google Play purchase validation (read by `iap_validation_service.py`). Generate a service account in Google Cloud Console with Play Developer API access, paste the JSON key contents.

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

**2026-05-11 (afternoon) — session 4 ended with:**
- **Android Section C "Screens still to port from iOS" is functionally complete.** All twelve iOS screens / flows / integrations are now on Android with parity: Leaderboard (filter pills + sparklines), TopInfluencers, MyPortfolio, Subscriptions, PortfolioDetail, PerformanceChartView (Vico), Play Billing E2E, full onboarding (Welcome / Referral / EarnNudge / AddStocks), CompactPlanToggle, and the app icon with themed-icons monochrome silhouette.
- **App icon themed-icons** finished today (commits `30266c3` → `e212107`). Hit several gotchas worth recording: (1) Image Asset Studio prepends an AOSP Apache-2.0 license comment **above** the `<?xml ?>` declaration which malforms the XML and breaks `aapt2`; fix is to delete the boilerplate so the `<?xml ?>` is back on line 1. (2) Asset Studio's "Monochrome" tab does **not** auto-flatten gradient input — it writes the source verbatim. A gradient monochrome layer renders as an empty disc under themed icons. The fix is to hand-flatten in Photopea (lock transparency → fill with black) and re-import, then rescale to match the foreground's *monkey bbox* (not the whole foreground PNG, which has a darker plate). Pillow scripts in this session's commits handle the rescale.
- **Google Play Console account paid** ($25, Family Apps LLC). App listing creation pending — required before release SHA-256 is available for `assetlinks.json`.
- **CompactPlanToggle iOS port** shipped (`9b65fd9`) — Android now matches iOS's "Save 36%" pill on the Annual chip and price-prominent typography. Earlier commit `a64ba7b` tightened vertical padding 8dp → 4dp.
- **Carousel skip race fixed** (`c67dcec`) and Image Asset Studio'd malformed XML resources fixed (`726898e`).
- Remaining Android workstream: LegalText port status (needs check), pre-launch testing on a real device (5 items), `assetlinks.json` SHA-256 swap (gated on Play Console app listing), and v1.1-deferred screens.
- **Pre-launch security blocker** (`mobile_api.py /auth/token` decoding ID tokens with `verify_signature=False`) is the next thing I'm tackling. Both iOS and Android currently rely on this code path; fix needs to preserve backward compat for both clients.

**2026-05-10 (afternoon) — session 3 ended with:**
- Audit tolerance buffer shipped (commit `34a01dc`) — Vercel cron jitter ±60s false positives no longer flagged.
- Display name values set in DB for `marblethehill72` and `CoastHillBear`. iOS Build 32 archived, names confirmed rendering.
- Copytrade-bot email-trade endpoint now fans out push + email to subscribers (commit `8ce748c`). Trade notifications switched from raw username to `public_name`.
- Pending: verify push delivery on next real Public.com trade email. Confirmed: bobford00 has 1 active `device_token` (token_id=2, ios, created Feb 27).
- ADMIN_NOTIFY_EMAIL falls back to ADMIN_EMAIL (commit `ad799d8`) — eliminates need for duplicate Vercel env var.
- **Native Android scaffold complete**: full project under `/android/` (Kotlin 2.0 / Compose / Hilt / Retrofit / Vico / Firebase / Play Billing). Auth, networking, FCM, deep-link config, Theme, Navigation graph, and 7 screens (3 real + 4 stubs) all in. iOS-equivalent feature surface enumerated in Section C "Screens still to port from iOS". `assetlinks.json` added; `vercel.json` serves it as application/json.
- Reviewed Section G launch-calendar reality: at Day 27 of 49, Phase 1 social-media foundation is unstarted. June 1 launch is officially deferred; new sequencing is iOS finalize → Android port → beta → set launch date → run playbook content.

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
