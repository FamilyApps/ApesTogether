# Apes Together iOS App

SwiftUI-based iOS app for following top traders and receiving real-time trade alerts.

## Requirements

- Xcode 15.0+
- iOS 17.0+
- macOS for development

## Setup Instructions

### 1. Open in Xcode

Since you're on Windows, you'll need a Mac to build this app. Transfer the `ios/` folder to your Mac.

```bash
# On Mac, open terminal in the ios folder and create Xcode project
cd ios
```

### 2. Create Xcode Project

Open Xcode and create a new project:
1. File → New → Project
2. Choose "App" under iOS
3. Product Name: **ApesTogetherApp**
4. Bundle Identifier: **com.apestogether.app**
5. Interface: **SwiftUI**
6. Language: **Swift**
7. Save to the `ios/` folder

Then drag the existing Swift files into the project.

### 3. Add Firebase SDK

Using Swift Package Manager:
1. File → Add Package Dependencies
2. Add: `https://github.com/firebase/firebase-ios-sdk`
3. Select products: **FirebaseMessaging**

### 4. Add GoogleService-Info.plist

1. Download from Firebase Console (you already did this during setup)
2. Drag into the Xcode project root
3. Ensure "Copy items if needed" is checked

### 5. Configure Capabilities

In Xcode, select your target → Signing & Capabilities:
1. **+ Capability** → Push Notifications
2. **+ Capability** → Sign in with Apple
3. **+ Capability** → In-App Purchase
4. **+ Capability** → Background Modes → Remote notifications

### 6. Configure Signing

1. Select your Apple Developer Team
2. Bundle Identifier must match: `com.apestogether.app`

### 7. Create App in App Store Connect

1. Go to https://appstoreconnect.apple.com
2. My Apps → + → New App
3. Platform: iOS
4. Name: Apes Together
5. Bundle ID: com.apestogether.app
6. SKU: apestogether-ios

### 8. Configure In-App Purchases

In App Store Connect:
1. Your App → Monetization → Subscriptions
2. Create Subscription Group: "Portfolio Access"
3. Create Subscription:
   - Reference Name: Monthly Subscription
   - Product ID: `com.apestogether.subscription.monthly`
   - Price: $9.00/month

### 9. Build & Run

1. Select a simulator or connected device
2. Press ⌘R to build and run

## Project Structure

```
ApesTogetherApp/
├── ApesTogetherApp.swift     # App entry point + Firebase config
├── ContentView.swift         # Root view with auth check
├── Info.plist               # App configuration
├── Models/
│   └── Models.swift         # Data models
├── Views/
│   ├── LoginView.swift      # Sign in with Apple
│   ├── LeaderboardView.swift # Top traders list
│   ├── PortfolioDetailView.swift # Individual portfolio
│   ├── MyPortfolioView.swift # User's own portfolio
│   ├── SubscriptionsView.swift # Following list
│   └── SettingsView.swift   # Settings & sign out
├── Services/
│   ├── APIService.swift     # Backend API client
│   ├── AuthenticationManager.swift # Auth state
│   ├── KeychainService.swift # Secure token storage
│   └── SubscriptionManager.swift # StoreKit 2
└── ViewModels/
    └── (ViewModels embedded in Views for simplicity)
```

## Features

- ✅ Sign in with Apple
- ✅ Leaderboard with period filters (1D, 5D, 7D, 1M, etc.)
- ✅ Portfolio detail views
- ✅ Push notifications for trade alerts
- ✅ StoreKit 2 subscriptions
- ✅ Notification preferences per subscription

## Testing

### TestFlight

1. Archive: Product → Archive
2. Distribute App → TestFlight & App Store
3. Upload to App Store Connect
4. Add testers in TestFlight section

### Push Notifications

Test push notifications using Firebase Console:
1. Firebase Console → Cloud Messaging
2. Send test message to FCM token (logged in console)

## Environment

The app connects to: `https://apestogether.ai/api/mobile`

API endpoints used:
- `POST /auth/token` - Authentication
- `GET /leaderboard` - Leaderboard data
- `GET /portfolio/{slug}` - Portfolio details
- `GET /subscriptions` - User's subscriptions
- `POST /device/register` - FCM token registration
- `POST /purchase/validate` - IAP validation
