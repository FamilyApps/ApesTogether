# Devin Handover — ApesTogether (Android pre-launch work)

> **Purpose:** continuity doc so a fresh assistant session (e.g. Devin Local/Desktop) can pick up
> exactly where we left off without the user re-explaining the project, file locations, git access,
> testing setup, or current status. Written 2026-06-07 at the end of "Session 11".
>
> **The living source of truth is `LAUNCH_TODO.md`.** Read its top section first — **"▶ RESUME HERE
> — Sunday"** — then **Section C (Pre-launch testing)** and **Section H (Operations / Data)**. This
> handover summarizes the workflow/environment context that is NOT in LAUNCH_TODO.

---

## 0. FIRST THING TO DECIDE: push the 2 local commits?

`git log` shows **2 commits that exist locally but are NOT pushed to `origin/master`**:

- `275fb20` docs: add Sunday resume block to LAUNCH_TODO
- `7a21b67` Android: fix FCM/App-Link deep-link nav (onNewIntent + extras), verified on Pixel 8a; migrate Google IAP to subscriptionsv2 + per-product pricing

They are safe in the local repo at `c:\Users\catal\CascadeProjects\stock-portfolio-app`, but not backed
up to GitHub and not deployed. **Pushing `master` triggers a Vercel production deploy** (see §4).
The IAP backend changes are behavior-neutral until `GOOGLE_PLAY_CREDENTIALS_JSON` is set, so deploying
them early is low-risk — but confirm with the user before pushing. Command:

```powershell
git push origin master
```

---

## 1. Environment & repo

- **OS / shell:** Windows, PowerShell. **Never** use `cd` in commands — set the working directory instead.
- **Repo root:** `c:\Users\catal\CascadeProjects\stock-portfolio-app`
- **Git remote:** `origin` → `https://github.com/FamilyApps/ApesTogether.git`
- **Branch:** `master` (tracks `origin/master`). Work happens directly on `master`.
- **Git access:** yes — staging, committing, fetching, log/status all work from the repo root.
- **Unrelated uncommitted files (NOT ours — leave them alone unless the user asks):**
  `docs/ASO_STRATEGY.md` (modified) and `TOMORROW_GAMEPLAN.md` (untracked). These predate our work.

---

## 2. Git / commit workflow (how the user expects changes handled)

- **Stage specific paths**, not blanket `git add -A`, so unrelated WIP files don't get swept in. Example:
  ```powershell
  git add android/ iap_validation_service.py mobile_api.py tests/test_phase1_mobile.py LAUNCH_TODO.md
  git commit -m "<concise, specific message>"
  ```
- **Commit messages** are single-line, specific, and describe both the *what* and the *why* (e.g.
  "Android: fix FCM/App-Link deep-link nav (onNewIntent + extras), verified on Pixel 8a; migrate
  Google IAP to subscriptionsv2 + per-product pricing").
- **Do NOT push automatically.** Pushing `master` = a production deploy. Always confirm first.
- The repo is on Windows so git prints harmless `LF will be replaced by CRLF` warnings — ignore them.
- **`LAUNCH_TODO.md` is updated every session** and committed alongside the code it describes.

---

## 3. Key files map (for the current Android-launch work)

**Documentation / planning**
- `LAUNCH_TODO.md` — single source of truth. Resume block at very top; Section C = pre-launch testing;
  Section H = ops/data (incl. the API Usage tab bug). Also a "Monday market-open checklist" near top.
- `docs/LAUNCH_PLAYBOOK.md` — original day-by-day launch calendar (now a template, not a deadline).
- `DEVIN_HANDOVER.md` — this file.

**Android client** (`android/app/src/main/kotlin/com/apestogether/app/`)
- `MainActivity.kt` — **deep-link entry point.** `ingestDeepLink()` resolves the portfolio slug from the
  data Uri (App Links) **or** the `portfolio_slug` intent extra (FCM system-tray tap), on `onCreate`
  **and** `onNewIntent`. (This is the session-11 fix.)
- `ui/RootApp.kt` — navigates to PortfolioDetail when authed + a pending slug exists.
- `OnboardingManager` (injected into MainActivity + RootViewModel) — holds the pending slug.
- `ui/screens/portfolio/PortfolioDetailScreen.kt` — subscribe CTA / Play Billing flow; sends `product_id`.
- `data/models/Models.kt` — purchase-validation request model (`productId` field).
- `data/api/di/ApiModule.kt` — Retrofit/OkHttp; **OkHttp logging = HEADERS in debug** (logs request URLs,
  not bodies — this is what makes the slug-in-logcat trick work).
- `data/api/AuthInterceptor.kt` — Bearer token injection.
- `app/build.gradle.kts` — `applicationId = com.apestogether.app` (**no** debug suffix), `API_BASE_URL =
  https://apestogether.ai/api/mobile/` (debug build talks to **production**), `GOOGLE_WEB_CLIENT_ID` from
  `android/secrets.properties` (gitignored).
- `app/src/main/AndroidManifest.xml` — MainActivity `launchMode=singleTask`; App Link intent filter;
  `trade_alerts` declared as the default FCM notification channel.
- `ApesTogetherApplication.kt` — creates the `trade_alerts` notification channel.

**Backend** (Flask app on Vercel; repo root unless noted)
- `iap_validation_service.py` — IAP validation. Google path now uses `purchases.subscriptionsv2.get`
  (`_parse_google_subscription_v2`, `_parse_rfc3339`); per-product pricing via `_get_pricing`. Reads env
  `GOOGLE_PLAY_CREDENTIALS_JSON` (exact name) + optional `GOOGLE_PLAY_PACKAGE_NAME`.
- `mobile_api.py` — all `/api/mobile/*` endpoints (auth, portfolio, subscriptions, purchase validate,
  `/admin/test-push`, etc.). `product_id` is forwarded end-to-end here.
- `push_notification_service.py` — FCM send helpers (`send_trade_notification` includes `portfolio_slug`
  in the data payload; admin test-push sends only `{'type':'test_push'}` with no slug).
- `models.py` — SQLAlchemy models (`User.portfolio_slug` is a random 11-char string; `MobileSubscription`,
  `DeviceToken`, etc.).
- `api/index.py` — main Flask app + web routes + `generate_portfolio_slug()`.
- `public/.well-known/assetlinks.json` — Android App Links verification file (**has placeholder SHA-256s**
  that still need the real debug + Play App Signing certs).
- `tests/test_phase1_mobile.py` — mobile unit tests (incl. `test_google_response_parsing`, rewritten to v2).

**iOS client** (`ios/ApesTogetherApp/`, SwiftUI — parity reference / the other app on the shared backend)
- Built on a Mac, not this PC (see §4C). `ApesTogetherApp.swift` (Firebase + deep-link `onOpenURL`),
  `Services/SubscriptionManager.swift` (StoreKit 2 IAP), `Services/AuthenticationManager.swift` (Sign in
  with Apple), `Services/APIService.swift` (same `/api/mobile` backend). `ios/README.md` = setup/build steps.
- Note: the iOS deep-link/notification-tap path (`AppDelegate.handleNotification` → `portfolio_slug`) was
  the reference when fixing the Android equivalent — leave iOS untouched unless a change is iOS-specific.

---

## 4. Deployment — THREE separate targets (do not conflate them)

There is **one shared backend** but **two completely independent mobile-app release pipelines**. Pushing
git does NOT deploy either app; it only deploys the backend/web. The two apps ship through different
build machines and different stores.

### 4A. Shared backend + web API (Vercel, git-driven)
- Both the iOS and Android apps talk to the **same** production backend at
  `https://apestogether.ai/api/mobile/` (Python/Flask serverless under `api/`, config in `vercel.json`).
- **Deploy = `git push origin master`** → triggers a **Vercel production deploy**. This is the only thing
  "deploying the backend" means. (Confirm against the Vercel dashboard if in doubt.)
- **Env vars live in the Vercel dashboard**, NOT in the repo. Outstanding for our work:
  **`GOOGLE_PLAY_CREDENTIALS_JSON`** (Android IAP validation; see LAUNCH_TODO Section H). Apple IAP
  validation uses StoreKit 2 JWS and needs no server key.
- `.env` at repo root is local-only.
- This backend is shared, so a server change affects **both** apps at once — test both sides when touching
  shared endpoints (e.g. `/purchase/validate`, `/device/register`, `/auth/token`).

### 4B. Android app (built on THIS Windows machine → Google Play)
- **Source:** `android/` (Kotlin/Compose). Built with Gradle / Android Studio locally on this PC.
- **Local install for testing:** `.\gradlew.bat :app:installDebug` (USB to the Pixel 8a) — see §5.
- **Release:** build a signed **AAB** → upload to **Google Play Console** → promote through tracks
  (internal-testing → closed → production). Play Console handles signing (Play App Signing).
- **IAP:** Play Billing; products/base-plans/trial configured in **Play Console**; backend validates the
  purchase token via `purchases.subscriptionsv2.get` (`iap_validation_service.py`).
- **Push:** Firebase Cloud Messaging directly.
- **App Links verification:** `public/.well-known/assetlinks.json` (served by the backend) must contain the
  real signing-cert SHA-256s.
- Vercel does **not** build or host the Android app.

### 4C. iOS app (requires a Mac + Xcode → App Store Connect)
- **Source:** `ios/ApesTogetherApp/` (SwiftUI). Bundle ID `com.apestogether.app`. Setup steps in
  `ios/README.md`.
- **CANNOT be built on this Windows machine.** Per `ios/README.md`, the `ios/` folder must be moved to a
  **Mac**, opened in **Xcode 15+**, and built there. No CI/fastlane is configured — it's a manual Xcode flow.
- **Release:** Xcode → **Product → Archive** → **Distribute App → TestFlight & App Store** → upload to
  **App Store Connect** → TestFlight for testers, then submit for App Store review.
- **IAP:** StoreKit 2 (`SubscriptionManager.swift`); products `com.apestogether.subscription.monthly` /
  `.annual` configured in **App Store Connect**; backend validates the **JWS** via `/purchase/validate`
  with `platform="apple"` (no server-side key needed).
- **Push:** APNs via Firebase; capabilities (Push, Sign in with Apple, In-App Purchase, Background Modes)
  enabled in Xcode; `GoogleService-Info.plist` added in Xcode.
- Vercel does **not** build or host the iOS app; `git push` has no effect on iOS distribution.

### 4D. Quick reference
| Target | Source | Build machine | Ships via | "Deploy" trigger |
|--------|--------|---------------|-----------|------------------|
| Backend + web API | `api/`, root `*.py` | Vercel (cloud) | Vercel | `git push origin master` |
| Android app | `android/` | This Windows PC (Gradle/Android Studio) | Google Play Console | manual AAB upload + track promotion |
| iOS app | `ios/` | A **Mac** w/ Xcode (not this PC) | App Store Connect | manual Xcode Archive → upload |

---

## 5. Android on-device testing setup (this machine)

- **Device:** Google Pixel 8a, codename **`akita`**, connected by USB-C. Logged into the app as **`bobford00`**.
- **Build:** debug, package `com.apestogether.app` (same package for debug+release), points at the
  **production** backend. Install via Android Studio **Run**, or:
  ```powershell
  # from c:\Users\catal\CascadeProjects\stock-portfolio-app\android
  .\gradlew.bat :app:installDebug
  ```
- **adb is NOT on PATH.** Full path: `%LOCALAPPDATA%\Android\Sdk\platform-tools\adb.exe`. In PowerShell:
  ```powershell
  $adb = "$env:LOCALAPPDATA\Android\Sdk\platform-tools\adb.exe"
  & $adb devices -l    # should list: 44161JEKB07342 ... model:Pixel_8a
  ```
- **What a "slug" is:** a random 11-char id (e.g. `JFKNZXlGGtb`), NOT the username/display name. It's the
  `/p/<slug>` portion of a share link.
- **How to grab a real slug from the device** (because OkHttp logs request URLs at HEADERS level):
  1. `& $adb logcat -c`  (clear)
  2. In the app, open any portfolio.
  3. `& $adb logcat -d | Select-String "mobile/portfolio/"` → the URL contains the slug. (candle3873's
     slug was `JFKNZXlGGtb`.)
- **Deep-link re-test recipe (verified working in session 11):** always launch the app **plain to the feed
  first** so nothing is cached, THEN fire the deep link; success = a `GET /api/mobile/portfolio/<slug>`
  appears in logcat (only happens on real navigation). Same-slug re-navigation can hit a cache and look
  like a false FAIL — that bit us once.
  ```powershell
  $adb = "$env:LOCALAPPDATA\Android\Sdk\platform-tools\adb.exe"; $slug = "<slug>"; $pkg = "com.apestogether.app"
  & $adb logcat -c; & $adb shell am force-stop $pkg; & $adb shell am start -n "$pkg/.MainActivity"; Start-Sleep 8
  & $adb logcat -c
  # App Link (data Uri) path:
  & $adb shell am start -W -a android.intent.action.VIEW -d "https://apestogether.ai/p/$slug" $pkg
  # FCM system-tray (extra) path:  & $adb shell am start -n "$pkg/.MainActivity" --es portfolio_slug "$slug"
  Start-Sleep 6; & $adb logcat -d | Select-String "mobile/portfolio/$slug"
  ```
- **Python note:** the global Python 3.14 here lacks `pytest`/`httpx`, so `iap_validation_service.py`
  can't be imported directly. To unit-test its parsers, stub httpx first:
  `python -c "import sys,types; sys.modules['httpx']=types.ModuleType('httpx'); from iap_validation_service import ..."`.

---

## 6. Current status — the 5 Android pre-launch tests

| # | Test | Status |
|---|------|--------|
| 1 | Google Sign-In round trip | Effectively done (logged in as bobford00 on device). Real-device formal pass optional. |
| 2 | Trade-alert FCM (background display + tap-to-navigate) | **Verified on device.** Test push delivered+displayed; all deep-link nav paths confirmed. |
| 3 | App Link `apestogether.ai/p/<slug>` → PortfolioDetail | **Handling verified on device** (cold+warm). `autoVerify` still pending the assetlinks SHA-256 swap. |
| 4 | Subscribe via Play Billing → backend validation → MobileSubscription row | **Code fixed; not yet testable.** Gated on Play Console setup + `GOOGLE_PLAY_CREDENTIALS_JSON` + backend redeploy. Cannot run over USB sideload. |
| 5 | 14-day Google Play closed-testing window | Process-only, later. Confirm whether the Family Apps LLC org account is even subject to the rule. |

---

## 7. Next steps (priority order — mirrors LAUNCH_TODO resume block)

1. **Play Billing #4 setup** — the only remaining on-device test. Steps: set Vercel
   `GOOGLE_PLAY_CREDENTIALS_JSON` + redeploy backend; publish both subscription products + base plans +
   the 7-day trial in Play Console; add `bobford00` as a License Tester; upload to an **internal-testing
   track** and install via the opt-in link; then subscribe (monthly + annual) on the Pixel and confirm a
   `MobileSubscription` row + 200 from `/purchase/validate`. The user wants to be walked through this.
2. **App Link `autoVerify`** — replace placeholder SHA-256s in `public/.well-known/assetlinks.json` with
   the real debug + Play App Signing certs.
3. **`/admin-panel` → API Usage tab shows all zeroes** (user-reported bug) — investigate the admin route
   that serves API Usage data + where per-provider call counts are incremented. Logged in LAUNCH_TODO §H.
4. *(Optional)* formal real-device Google Sign-In pass (#1) and a real trade-alert FCM tap (needs a live
   subscription, so it rides along with #4).

There are many other open items (legal, ASO, ops audits) throughout `LAUNCH_TODO.md` — those are not part
of the current Android-launch thread but remain on the list.
</CodeContent>
<EmptyFile>false</EmptyFile>
</invoke>
