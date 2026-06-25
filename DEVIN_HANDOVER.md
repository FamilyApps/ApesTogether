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
- **✅ Cascade CAN build the Android app from this Windows PC** (verified 2026-06-08). **Critical gotcha:**
  `java` is **NOT on PATH** and `JAVA_HOME` is **empty**, so a bare `.\gradlew.bat` fails. Set `JAVA_HOME`
  to Android Studio's bundled JDK 21 (JBR) first, then run Gradle from the `android/` dir:
  ```powershell
  $env:JAVA_HOME = 'C:\Program Files\Android\Android Studio\jbr'   # OpenJDK 21
  .\gradlew.bat --no-daemon assembleDebug      # APK only (no device needed)
  .\gradlew.bat --no-daemon :app:installDebug  # build + install (Pixel must be plugged in & authorized)
  ```
  Debug APK output: `android/app/build/outputs/apk/debug/app-debug.apk` (~25 MB, versionName `1.0-debug`).
- **Distribution link:** there is **no** automated App-Distribution/Gradle task in the repo. The "download
  link" the user shares is a **manual upload** of `app-debug.apk` (e.g. Firebase App Distribution console).
  A rebuilt APK = the old link is stale; either `adb install -r` to the Pixel directly or re-upload for a new link.
- **Local install for testing:** `.\gradlew.bat :app:installDebug` (USB to the Pixel 8a) — see §5 (needs `JAVA_HOME`, above).
- **Release:** build a signed **AAB** → upload to **Google Play Console** → promote through tracks
  (internal-testing → closed → production). Play Console handles signing (Play App Signing).
- **IAP:** Play Billing; products/base-plans/trial configured in **Play Console**; backend validates the
  purchase token via `purchases.subscriptionsv2.get` (`iap_validation_service.py`).
- **Push:** Firebase Cloud Messaging directly.
- **App Links verification:** `public/.well-known/assetlinks.json` (served by the backend) must contain the
  real signing-cert SHA-256s.
- Vercel does **not** build or host the Android app.

### 4C. iOS app (requires a Mac + Xcode → App Store Connect)
- **Source-of-truth in THIS repo:** `ios/ApesTogetherApp/` (SwiftUI). Bundle ID `com.apestogether.ApesTogether` (verified 2026-06-22 in `project.pbxproj` Debug+Release + the bundled `GoogleService-Info.plist`; an earlier note here said `com.apestogether.app`, which is WRONG -- that string is the *Android* `applicationId`. See section 8).
  Setup steps in `ios/README.md`.
- **CANNOT be built on this Windows machine.** Per `ios/README.md`, the `ios/` folder must be moved to a
  **Mac**, opened in **Xcode 15+**, and built there. No CI/fastlane is configured — it's a manual Xcode flow.

- **⚠️ Mac-side workspace layout (USER-REPORTED 2026-06-07 — CONFIRM ON THE MAC, may be outdated).**
  This setup keeps getting lost between sessions, so it's recorded here. On the user's MacBook the paths
  are roughly:
  - `~/Documents/ApesTogether/` — the iOS/Xcode working area (NOT the same place as the backend clone).
  - `~/Documents/ApesTogether/ios/ApesTogether/` — the **Xcode project** (`.xcodeproj`/workspace) lives here.
  - `~/Documents/ApesTogether/ios/ApesTogetherApp/` — the **Swift source + assets**.
  - `~/CascadeProjects/stock-portfolio-app/` — a clone of the **backend** files (user says "may be outdated").

  **Implication / risk:** the Mac's Xcode project under `~/Documents/ApesTogether/ios/` is a SEPARATE copy
  from this git repo's `ios/` folder, so the two can drift. Before doing iOS work, **confirm which copy is
  authoritative** and reconcile (ideally make the Mac build directly from a fresh clone of this repo's
  `ios/`, or sync changes back into git so `ios/` here stays the source of truth). **Do not assume these
  paths are current** — verify with `ls` on the Mac first. (TODO: nail this down and update this section
  with confirmed paths + which copy is canonical.)

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
  **production** backend. Install via Android Studio **Run**, or (set `JAVA_HOME` first — see §4B, `java` is not on PATH):
  ```powershell
  # from c:\Users\catal\CascadeProjects\stock-portfolio-app\android
  $env:JAVA_HOME = 'C:\Program Files\Android\Android Studio\jbr'
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
| 1 | Google Sign-In round trip | **DONE — verified on physical Pixel 8a (2026-06-09).** Root cause of prior failure was an unregistered signing SHA-1 (`google-services.json` had `oauth_client count: 0`); fixed by registering the Play App Signing SHA-1 `8F:A7:83…` as the Android OAuth client. Logcat: `GetGoogleIdOperation succeeded` → `CREDENTIALS_RECEIVED`. |
| 2 | Trade-alert FCM (background display + tap-to-navigate) | **Verified on device.** Test push delivered+displayed; all deep-link nav paths confirmed. |
| 3 | App Link `apestogether.ai/p/<slug>` → PortfolioDetail | **Handling verified on device** (cold+warm). **Server side now FIXED + verified live (2026-06-24):** `https://apestogether.ai/.well-known/assetlinks.json` was shipping an EMPTY `sha256_cert_fingerprints` list (Vercel `includeFiles` didn't bundle the static file → route fell back to an unset env var), which silently blocked `autoVerify`. Now serves both fingerprints via an embedded code constant (commit `3a0b14d`), confirmed live. **Remaining:** on-device `autoVerify` check (`adb shell pm get-app-links com.apestogether.app`) after installing a build signed with the matching Play key. |
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

---

## 8. Google Cloud / Firebase / Google Sign-In / SHA keys -- definitive map (Session 18, 2026-06-22)

> Written so nobody re-runs the "two Google accounts / duplicate apps / which SHA goes where" rabbit
> hole again. **Everything below was verified from source files + a live production probe.** Bottom line:
> the setup is INTENTIONAL and WORKING -- there is no harmful duplication to "fix".

### 8A. Three separate Google projects, three different jobs

| Project (console name) | id / number | Owner login | Job | Google Sign-In? |
|---|---|---|---|---|
| **Firebase** | `apestogether-2c749` / `#1096138595577` | (Firebase console acct) | FCM push + the bundled config files (`google-services.json`, `GoogleService-Info.plist`) | **No** (not Firebase Auth) |
| **"Apes Together"** | `#654567882865` | `bobford00@gmail.com` | **Google Sign-In project of record** -- owns the Web + Android OAuth clients | **Yes** |
| **"Apes Together Play API"** | `apestogether-play-api` | `fordutilityapps@gmail.com` | Play Developer API service account (`GOOGLE_PLAY_CREDENTIALS_JSON`) + RTDN Pub/Sub topic `play-rtdn` | No ("Google Auth Platform not configured" here is CORRECT) |

The "two accounts" (`bobford00` vs `fordutilityapps`) split is an ownership-hygiene quirk, **not a bug** --
Sign-In is verified by our own backend (8B), so it works across projects/accounts. Consolidating ownership
someday is nice-to-have, NOT a launch blocker.

### 8B. How Google Sign-In actually flows (why cross-project is fine)

Android **Credential Manager** (`serverClientId = GOOGLE_WEB_CLIENT_ID`) -> Google returns an ID token whose
`aud` = that Web client id -> app POSTs it to **`/api/mobile/auth/token`** -> backend
`mobile_api._verify_google_id_token` verifies signature + `aud` against Vercel **`GOOGLE_ANDROID_CLIENT_ID`**
(set to that same Web client id). **This is custom backend verification, NOT Firebase Auth** -- which is why
`google-services.json` has `oauth_client: 0` and that's fine. iOS uses **Apple Sign-In only** (no Google), so
`GoogleService-Info.plist` having no `CLIENT_ID` / `REVERSED_CLIENT_ID` is CORRECT, not broken.

### 8C. Apps registered in Firebase project `apestogether-2c749`

| App | Bundle / package | Firebase appId | Status |
|---|---|---|---|
| Android | `com.apestogether.app` | `1:1096138595577:android:...` | live (FCM) |
| **iOS (correct, shipping)** | `com.apestogether.ApesTogether` | `1:1096138595577:ios:ef605a913d1d7aa3b75628` | live -- matches `project.pbxproj` (Debug+Release) AND the bundled plist |
| iOS (STRAY -- mistake) | `com.apestogether.app` | `1:1096138595577:ios:7f2b...` | **safe to delete** (see 8G) -- wrong bundle, nothing ships with it |

### 8D. Signing certs / fingerprints -- which goes where (do NOT confuse SHA-1 vs SHA-256)

Two unrelated uses: **Google Sign-In uses SHA-1** registered as Android OAuth clients in project
**`#654567882865`**; **Android App Links `autoVerify` uses SHA-256** in `public/.well-known/assetlinks.json`.

| Cert | SHA-1 (Sign-In, proj `#654567882865`) | SHA-256 (App Links, assetlinks.json) | Source / notes |
|---|---|---|---|
| **Play app-signing key** (production) | `8F:A7:83:2D...` -- **the one that made Sign-In work on the Play build** | `0A:3A:A0:...:1C:CA` (slot 2 in assetlinks) | Play Console -> Protected with Play -> Manage Play app signing |
| **Upload key** | `49:2E...` (only for a sideloaded release APK) | `64:47:B5:...:2B:57` (slot 1 in assetlinks) | same page |
| **Debug keystore** (`~/.android/debug.keystore`) | `29:56:AA:...:CC:1B` | (not needed) | debug builds only |

The Play-distributed build is signed by Play, so the **Play app-signing SHA-1 `8F:A7...`** is what matters
for production Sign-In. It is **already registered** in `#654567882865`; Sign-In VERIFIED on a Pixel 8a
(2026-06-09).

### 8E. Auth-related Vercel env vars (state CONFIRMED Session 18)

| Var | Value / state | How confirmed |
|---|---|---|
| `GOOGLE_ANDROID_CLIENT_ID` | `654567882865-4skl...` (the Web client id) -- marked *Sensitive* | proven correct: on-device Sign-In succeeds (a wrong `aud` would 401) |
| `STRICT_OAUTH_VERIFICATION` | `enforce` -- marked *Sensitive* | **live probe 2026-06-22:** a forged-but-well-formed Google token to `/api/mobile/auth/token` returned `401 invalid_google_token` (strict path), not `400 email_required_for_new_user` (legacy decode path) |
| `APPLE_BUNDLE_ID` | `com.apestogether.ApesTogether` | present in Vercel |
| `GOOGLE_WEB_CLIENT_ID` | same `654567882865-4skl...` | `android/secrets.properties` (gitignored), injected into `BuildConfig` |

If Sign-In ever breaks: first check `STRICT_OAUTH_VERIFICATION` is still a truthy spelling
(`1/true/on/enforce/yes` -- a typo like `enforced` reads as OFF) and that `GOOGLE_ANDROID_CLIENT_ID` still
equals the Web client id.

### 8F. The Firebase "duplicate OAuth client" warning -- EXPECTED; do NOT "fix" by deleting

Firebase flags *"Another project contains an OAuth 2.0 client that uses this same SHA-1 + package"* for
`(debug SHA-1 29:56..., com.apestogether.app)`. That's because project `#654567882865` legitimately owns
that Android client (it's the Sign-In project). **Do NOT delete the client in `#654567882865` -- it IS the
working Sign-In client; deleting it breaks Google Sign-In.** Firebase here is push-only and FCM needs no
SHA-1, so the warning has zero functional impact.

### 8G. Optional cosmetic cleanups (NOT launch blockers)

1. **Delete the stray iOS Firebase app** (`com.apestogether.app`, appId `...7f2b...`) -- keep the correct
   one (`com.apestogether.ApesTogether`, `...ef605...`). Nothing ships with the stray.
2. *(Optional)* **remove the debug SHA-1 (`29:56...`) from the Firebase Android app** to silence the 8F
   warning. FCM doesn't need it and Sign-In is unaffected (it lives in `#654567882865`, not Firebase).
   `google-services.json` has `oauth_client: 0`, so re-downloading it after is optional (no behavior change).
</CodeContent>
<EmptyFile>false</EmptyFile>
</invoke>
