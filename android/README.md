# Apes Together — Android

Native Android client. Mirrors the iOS app at `../ios/ApesTogetherApp/`.

## Stack

| Layer | Tech |
|---|---|
| Language | Kotlin 2.0 |
| UI | Jetpack Compose (Material 3) |
| DI | Hilt |
| Networking | Retrofit + OkHttp + kotlinx.serialization |
| Storage | DataStore + AndroidX EncryptedSharedPreferences (token) |
| Auth | Google Sign-In via Credential Manager + Google Identity Services |
| Charts | Vico (Compose-native) |
| Push | Firebase Cloud Messaging |
| Billing | Google Play Billing 7.x |
| Min SDK | 26 (Android 8.0) |
| Target SDK | 35 (Android 15) |

## Project layout

```
android/
├── settings.gradle.kts
├── build.gradle.kts          # root, plugin declarations only
├── gradle/libs.versions.toml # version catalog (single source of truth)
├── secrets.properties        # gitignored — see secrets.properties.example
└── app/
    ├── build.gradle.kts
    ├── proguard-rules.pro
    ├── google-services.json  # gitignored — download from Firebase console
    └── src/main/
        ├── AndroidManifest.xml
        ├── kotlin/com/apestogether/app/
        │   ├── ApesTogetherApplication.kt   # Hilt entry, FCM channel setup
        │   ├── MainActivity.kt              # Compose host, runtime permissions
        │   ├── data/
        │   │   ├── api/
        │   │   │   ├── ApiService.kt        # Retrofit interface mirroring iOS APIService
        │   │   │   ├── AuthInterceptor.kt
        │   │   │   └── di/ApiModule.kt
        │   │   ├── auth/
        │   │   │   ├── TokenStore.kt        # encrypted-at-rest token storage
        │   │   │   └── AuthRepository.kt    # Google Sign-In + token exchange
        │   │   └── models/Models.kt         # data classes mirroring iOS Models.swift
        │   ├── push/
        │   │   └── ApesFirebaseMessagingService.kt
        │   └── ui/
        │       ├── RootApp.kt
        │       ├── theme/                   # mirrors iOS Theme.swift palette
        │       ├── navigation/              # Screen routes + RootNavGraph
        │       └── screens/
        │           ├── login/               # Real (Google Sign-In)
        │           ├── leaderboard/         # Real (lists + tap-to-detail)
        │           ├── topinfluencers/      # Stub
        │           ├── myportfolio/         # Stub
        │           ├── subscriptions/       # Stub
        │           ├── portfolio/           # Stub (deep-link target)
        │           ├── settings/            # Real (sign-out)
        │           └── common/              # Shared placeholder
        └── res/
            ├── values/{strings,colors,themes}.xml
            ├── drawable/                    # ic_notification + adaptive launcher layers
            ├── mipmap-anydpi-v26/           # adaptive launcher icon manifests
            └── xml/{backup_rules,data_extraction_rules}.xml
```

## First-time setup

You need:
- **Android Studio Hedgehog (2023.1.1) or newer** — Iguana / Koala recommended.
- **JDK 17** (Android Studio bundles it).
- A Firebase project (re-use the iOS project) and a Google Cloud OAuth client.

### 1. Open the project

Open Android Studio → `File → Open` → select the `android/` directory (NOT the repo root). Wait for Gradle sync.

### 2. Generate the Gradle wrapper

The wrapper JAR/scripts are not yet committed (they're typically generated locally and committed once). From the `android/` directory:

```bash
gradle wrapper --gradle-version 8.10
```

If you don't have `gradle` on your PATH, Android Studio will offer to generate the wrapper on its first sync — accept that prompt.

### 3. Add the Android app to Firebase

1. Go to https://console.firebase.google.com → existing Apes Together project.
2. Add app → Android. Package name: `com.apestogether.app`.
3. SHA-1: get yours with
   ```bash
   keytool -list -v -keystore ~/.android/debug.keystore -alias androiddebugkey -storepass android
   ```
4. Download `google-services.json`. Place it at `android/app/google-services.json` (gitignored).
5. The `com.google.gms.google-services` plugin in `app/build.gradle.kts` will pick it up.

### 4. Configure Google Sign-In

Copy `secrets.properties.example` to `secrets.properties` and fill in `GOOGLE_WEB_CLIENT_ID`. See the example file for full instructions on creating both the Web and Android OAuth clients in Google Cloud Console.

### 5. Run the debug build

```bash
./gradlew :app:installDebug
```

Or hit the green "Run" arrow in Android Studio.

## Backend integration (already in place)

The backend at `https://apestogether.ai/api/mobile/` already supports Android via these existing endpoints:

| Endpoint | Notes |
|---|---|
| `POST /auth/token` | accepts `provider: "google"` |
| `POST /device/register` | accepts `platform: "android"` |
| `POST /purchase/validate` | accepts `platform: "google"` + `purchase_token` |
| All read endpoints | unchanged from iOS |

`iap_validation_service.py` already implements Google Play receipt validation — for production you'll need to set the `GOOGLE_PLAY_CREDENTIALS_JSON` and `GOOGLE_PLAY_PACKAGE_NAME` env vars in Vercel. Full walkthrough in the **Google Play Billing setup** section below.

## App Links / deep linking

Android `https://apestogether.ai/p/<slug>` deep links are wired:
- Manifest declares the intent filter with `android:autoVerify="true"`.
- `/public/.well-known/assetlinks.json` is served from the website (configured in `vercel.json`). Replace the `REPLACE_WITH_*` SHA-256 fingerprints with:
  - **Debug certificate fingerprint:**
    ```bash
    keytool -list -v -keystore ~/.android/debug.keystore -alias androiddebugkey -storepass android | grep SHA256
    ```
  - **Release / Play app-signing fingerprint:** Google Play Console → app → Setup → App signing → "App signing key certificate" SHA-256.
- Verify with:
  ```bash
  adb shell pm verify-app-links --re-verify com.apestogether.app
  adb shell pm get-app-links com.apestogether.app
  ```

## Push notifications (FCM)

`ApesFirebaseMessagingService` handles incoming messages and calls `/device/register` with the FCM token on rotation. The backend's `push_notification_service.py` already targets FCM, so **the same trade-alert payloads sent to iOS are also sent to Android with no backend changes** — provided the Firebase project is configured for both platforms (it is, after step 3 above).

## Google Play Billing setup (required before Subscribe button works)

The Android Subscribe CTA on `PortfolioDetailScreen` is fully wired (`data/billing/BillingService.kt` + `PortfolioDetailViewModel.subscribe()`), but actually charging a user requires three things outside the codebase. Follow them in order — Step 1 takes 1–3 days for Google to verify, so start it ASAP.

### Step 1 — Register a Google Play Developer account

One-time **$25 USD** fee (vs Apple's $99/yr).

1. Go to https://play.google.com/console/u/0/signup
2. Sign in with the Google account you want to own the developer profile.
3. Choose **Organization** account type (not Personal) → enter **Family Apps LLC** as the organization name.
4. Pay $25, upload a government ID + business document, wait 1–3 days for verification.

### Step 2 — Create the app in Play Console

Once verified, in https://play.google.com/console:

1. **All apps → Create app.**
2. App name: `Apes Together`. Default language: English (US). App or game: App. Free or paid: Free (we charge via subscriptions, not upfront).
3. Accept developer program policies.
4. After creation, complete the **Dashboard → Set up your app** checklist:
   - App access (no login required for reviewers — provide test creds anyway)
   - Ads, Content rating, Target audience, News app
   - Data safety (mirror what iOS submitted)
   - Privacy policy URL: `https://apestogether.ai/privacy`
   - Store listing (icon, screenshots, short / full description — reuse iOS App Store copy)
5. Set **package name** to `com.apestogether.app` (must match `applicationId` in `app/build.gradle.kts`).

### Step 3 — Create the subscription products

In **Monetize → Products → Subscriptions** click **Create subscription** twice and use these EXACT product IDs (must match iOS StoreKit and `BillingService.kt`):

| Product ID | Name | Description | Base plan |
|---|---|---|---|
| `com.apestogether.subscription.monthly` | Monthly Subscription | Follow a trader's moves in real-time | Monthly, auto-renewing, $9.00 USD |
| `com.apestogether.subscription.annual` | Annual Subscription | Follow a trader's moves in real-time — best value | Yearly, auto-renewing, $69.00 USD |

For each subscription, add a **free trial offer**:
- Eligibility: New customers acquiring this subscription for the first time
- Phase 1: 7 days free
- Phase 2: standard price (auto)

Activate both subscriptions when the form lets you (you may need a fully completed store listing first).

### Step 4 — Create a Google Cloud service account for the backend

The backend (`iap_validation_service.py`) verifies purchase tokens by calling the Play Developer API. It needs a service account JSON:

1. Go to https://console.cloud.google.com → select the Firebase / Play project.
2. **IAM & Admin → Service Accounts → Create service account.**
   - Name: `apes-play-billing-validator`
   - Role: skip (we grant Play access separately)
3. Open the new service account → **Keys → Add key → Create new key → JSON**. Save the file (it will look like `apes-...-abc123.json`).
4. **Google Play Console → Setup → API access** (left sidebar).
5. Find the service account in the list (it auto-imports from the linked Cloud project). Click **Grant access**.
   - Permissions: **View financial data, orders, and cancellation survey responses** + **Manage orders and subscriptions**.
   - App permissions: select Apes Together.
   - Save.
6. Open the downloaded JSON file → copy the entire contents (a multi-line JSON object).
7. **Vercel → Project → Settings → Environment Variables → Add**:
   - Name: `GOOGLE_PLAY_CREDENTIALS_JSON`
   - Value: paste the entire JSON content.
   - Environments: Production (and Preview if you want sandbox testing on previews).
8. Also add: `GOOGLE_PLAY_PACKAGE_NAME` = `com.apestogether.app`
9. Redeploy Vercel so the new env vars take effect.

### Step 5 — Test on Internal Testing track

Play Billing **only works on apps installed from the Play Store**, not sideloaded debug APKs. So:

1. **Android Studio → Build → Generate Signed Bundle / APK → Android App Bundle (`.aab`)**
   - Create a release keystore (or reuse one). Store the keystore file + passwords somewhere safe — re-uploading the app under a new key requires a new package name.
   - Note: Google Play **App Signing** will re-sign the upload key with their managed key.
2. **Play Console → Testing → Internal testing → Create new release** → upload the `.aab`.
3. Add your Google account to the internal testers list. Save the **opt-in URL**.
4. On your test device, open the opt-in URL while signed in with the same Google account. Tap **Become a tester**, then install from the Play Store link on that page.
5. Open the app, navigate to a non-owned portfolio → tap Subscribe. The real Google Play sheet should appear.
6. Use a **test card** (Google provides them automatically when you're listed as an internal tester — purchases are not charged) or a real card — Play will show your test card option in the payment sheet for testers.

The full happy path: tap Subscribe → Play sheet → confirm → backend validates token → `MobileSubscription` row created → `subscribeState = Success` → green banner appears.

### Troubleshooting

| Symptom | Cause |
|---|---|
| `"Play Billing unavailable on this device"` | Running on emulator without Play Store, or sideloaded APK. Use a Play-installed build on a real device. |
| `"Subscription product not available"` | Product IDs in Play Console don't exactly match `com.apestogether.subscription.{monthly,annual}`, or the products aren't yet **Active**. |
| `"You already subscribed to this trader"` | `ITEM_ALREADY_OWNED` — Play sees an existing subscription for the same SKU. iOS uses subscription groups so users replace one with the other; Android handles this via the Play UI "change subscription" sheet. |
| Server says `"server_config_error"` | `GOOGLE_PLAY_CREDENTIALS_JSON` not set in Vercel, or the service account lacks Play Developer API access. |
| Server says `"invalid_purchase_token"` | The token was already consumed (acknowledged + recorded once already), or Play's API hasn't propagated the new purchase yet (retry after ~30s). |

## What's NOT done yet (in priority order)

These are tracked in `../LAUNCH_TODO.md` Section C:

1. ~~Port `LeaderboardView` filter pills + sparkline~~ ✅
2. ~~Port `PortfolioDetailView`~~ ✅
3. ~~Port `MyPortfolioView`~~ ✅
4. ~~Port `TopInfluencersView`~~ ✅
5. ~~Port `SubscriptionsView`~~ ✅
6. Port `AddStocksView`, `WelcomeCarouselView`, `ReferralPreviewView`, `EarnNudgeView` — full referral onboarding flow.
7. ~~Compose chart equivalent of `PerformanceChartView.swift` using Vico~~ ✅ (PerformanceChartCard).
8. ~~`LegalText.swift` → assets/legal/\* + `SettingsScreen` linkouts~~ ✅ (SettingsScreen opens marketing site URLs).
9. ~~Google Play Billing client integration on `PortfolioDetailScreen` subscribe CTA~~ ✅ (this commit). **Requires Play Console setup (see above) before live charges work.**
10. End-to-end tested:
    - Google Sign-In → token exchange → `getCurrentUser` round trip.
    - Trade-alert FCM push lands while app backgrounded.
    - App Link from `https://apestogether.ai/p/<slug>` opens `PortfolioDetailScreen`.
    - Subscribe via Play Billing → backend validation → `MobileSubscription` row appears.
    - 14-day Google Play closed-testing window for Production track release.

## How to extend

When porting a screen, the pattern is:

1. Create a `screens/<feature>/<Feature>Screen.kt` with a Composable + `@HiltViewModel`.
2. Inject `ApiService` (and any other repositories) into the ViewModel.
3. Expose `StateFlow<UiState>` from the ViewModel; observe via `collectAsState()` in the Composable.
4. The reference iOS file lives at `../ios/ApesTogetherApp/Views/<Feature>View.swift`. Map SwiftUI views to Compose:
   - `VStack/HStack` → `Column/Row`
   - `ScrollView { LazyVStack }` → `LazyColumn`
   - `Button { }` → `Button(onClick = { }) { }`
   - `@StateObject` / `@ObservedObject` → `hiltViewModel<...>()`
   - `Color.primaryAccent` → `PrimaryAccent` (in `ui/theme/Color.kt`)

If anything in iOS uses an API call we haven't added to `ApiService.kt`, add the matching Retrofit method there first.
