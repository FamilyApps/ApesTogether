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
| Target SDK | 34 (Android 14) |

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

`iap_validation_service.py` already implements Google Play receipt validation — for production you'll need to set the `GOOGLE_PLAY_SERVICE_ACCOUNT_JSON` env var in Vercel with a service-account key that has Play Developer API access.

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

## What's NOT done yet (in priority order)

These are tracked in `../LAUNCH_TODO.md` Section C:

1. Port `LeaderboardView` filter pills + sparkline (iOS file is 38KB / 1000+ lines).
2. Port `PortfolioDetailView` (47KB — the largest iOS view).
3. Port `MyPortfolioView` (9KB).
4. Port `TopInfluencersView` (16KB).
5. Port `SubscriptionsView` (18KB).
6. Port `AddStocksView`, `WelcomeCarouselView`, `ReferralPreviewView`, `EarnNudgeView` — full referral onboarding flow.
7. Compose chart equivalent of `PerformanceChartView.swift` using Vico.
8. `LegalText.swift` → assets/legal/* + `SettingsScreen` linkouts.
9. Google Play Billing client integration on `PortfolioDetailScreen` subscribe CTA.
10. End-to-end tested:
    - Google Sign-In → token exchange → `getCurrentUser` round trip.
    - Trade-alert FCM push lands while app backgrounded.
    - App Link from `https://apestogether.ai/p/<slug>` opens `PortfolioDetailScreen`.
    - Subscribe via Play Billing → backend validation → MobileSubscription row appears.
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
