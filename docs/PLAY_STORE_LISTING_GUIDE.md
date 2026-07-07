# Google Play Store — Listing Creation Guide

**Audience:** First-time Play Console publisher creating the ApesTogether listing.
**Status snapshot (May 24, 2026):** Developer account paid ($25, Family Apps LLC, May 11). Firebase Android app and Google Cloud OAuth clients already exist. **The app listing itself has not been created yet** — that's what this guide walks through.

---

## How this guide is organized

| Part | What you'll do | Time |
|---|---|---|
| Part 0 | Gather assets before you start | 30 min |
| Part 1 | Create the app + main store listing | 60 min |
| Part 2 | Compliance forms (content rating, data safety, financial features, etc.) | 90 min |
| Part 3 | Set up subscription products | 30 min |
| Part 4 | Internal Testing → Closed Testing 14-day gate | 14 days elapsed (you're not blocked the whole time) |
| Part 5 | Submit for Production review | 30 min + Google's review (~3 days) |
| Part 6 | Common rejections — read this BEFORE submitting | 10 min |

This is *only* the listing flow. Technical setup (signing keystore, billing service account, AAB upload, FCM, App Links) is in `android/README.md`.

> **Note on cross-references:** When this guide says "see `android/README.md` Step N", the technical setup is there. This guide only repeats the listing-relevant pieces.

---

# PART 0 — Gather assets before you start

Don't open Play Console until everything below is in a folder you can drag-and-drop from. Play Console is finicky and timing out mid-form is frustrating.

## 0.1 Listing copy (already written for you)

All copy lives in `docs/ASO_STRATEGY.md` v3. Specifically you'll need:

| Field | Value | Char count |
|---|---|---|
| **Title** | `ApesTogether: AI Stock Trader` | 29/30 |
| **Short description** | `Verified stock strategies. Every pick tracked. Traders keep 85%.` | 64/80 |
| **Full description** | See `ASO_STRATEGY.md` "Description" section | ~2,400/4,000 |
| **App category** | Finance | — |

> **Brand-spelling reminder:** Use `ApesTogether` (fused, no space) everywhere. The decision rationale is in `ASO_STRATEGY.md` "Branding decision" section.

## 0.2 Visual assets

| Asset | Size / format | Where it comes from | Status |
|---|---|---|---|
| **App icon** | 512×512 PNG (32-bit, with alpha) | Generate from Gemini Prompt 8 in `ASO_STRATEGY.md` | ⬜ Not yet generated |
| **Feature graphic** | 1024×500 PNG/JPG | Generate from Gemini Prompt 7 in `ASO_STRATEGY.md` | ⬜ Not yet generated |
| **Phone screenshots** (×8) | 1080×1920 (or higher portrait, 16:9 ratio); min 320 px on shortest side | Generate from Gemini Prompts 1–6 + the 2 Android-specific (Prompts 7–8 in screenshot list) | ⬜ Not yet generated |
| **7-inch tablet screenshots** | Optional. 1200×1920 portrait. | Same prompts, larger frame | Optional |
| **10-inch tablet screenshots** | Optional. 1800×2560 portrait. | Same prompts | Optional |

**Phone screenshot count:** 2 minimum, 8 maximum. We're targeting 8.

**Recommended workflow:** Use Gemini → generate at 1290×2796 (matches our iOS target), then resize to 1080×1920 for Play. The aspect ratio is close enough that the resize is clean.

## 0.3 Compliance assets

| Asset | What it is | Where to get it | Status |
|---|---|---|---|
| **Privacy policy URL** | Public URL to your privacy policy | `https://apestogether.ai/privacy-policy` | ⬜ Verify the URL returns 200 and is up to date |
| **Tester credentials** | Username + password for a real working account, for Google's reviewer to sign in | Create a fresh account specifically for review (`reviewer@apestogether.ai` or similar). Add a few followed traders so the reviewer sees value | ⬜ Create before submission |
| **Demo video URL** (optional) | YouTube unlisted, ≤ 30 sec | Generate after screenshots are done | Optional |
| **Family Apps LLC documents** | Business registration / EIN | Already submitted to Google for the account verification | ✅ |

## 0.4 Subscription product IDs (must match code)

Per `android/README.md` Step 3 — these are hardcoded in `BillingService.kt` and the iOS StoreKit setup. Don't change them.

| Product ID | Name | Price |
|---|---|---|
| `com.apestogether.subscription.monthly` | Monthly Subscription | $9.00 USD |
| `com.apestogether.subscription.annual` | Annual Subscription | $69.00 USD |

Both should have a 7-day free trial offer for new customers.

---

# PART 1 — Create the app + main store listing

## 1.1 Open Play Console and create the app

1. Go to https://play.google.com/console
2. Sign in with the Google account that owns the Family Apps LLC developer profile.
3. **Click `Create app`** (top right of the All apps page).
4. Fill the modal:

| Field | Value |
|---|---|
| App name | `ApesTogether` *(no colon, no descriptor — just the brand. The full title with descriptor goes in the listing later.)* |
| Default language | English (United States) – en-US |
| App or game | App |
| Free or paid | **Free** *(yes — even though we charge subscriptions. "Paid" means upfront purchase, which we're not.)* |
| Declarations: My app conforms to Play policies | ✓ |
| Declarations: My app conforms to US export laws | ✓ |

5. **Click `Create app`.**

You'll land on the app's Dashboard. The right side has "Set up your app" with 8 collapsible cards. We're going to fill them in order.

> **About the App name field:** Play allows 30 chars in the *display* name shown in the store. Many apps put the full title there (`ApesTogether: AI Stock Trader`). But the field at app-creation time is the internal name. The customer-facing title comes from the **Main store listing → App name** further down. **You'll set both to `ApesTogether: AI Stock Trader` (29 char) eventually** — but for the create-app modal, just use `ApesTogether` to avoid the colon-character validation Play sometimes gripes about. We'll set the public title in step 1.4.

## 1.2 Set the package name (one-time, irreversible)

1. **Dashboard → App content → App bundles** *(or)* **Setup → App integrity** — locations vary slightly by Play Console version.
2. Set **Package name** to `com.apestogether.app`.
3. **Save.** This match must be exact — `com.apestogether.app` is hardcoded in:
   - `android/app/build.gradle.kts` (`applicationId`)
   - `android/app/src/main/AndroidManifest.xml`
   - `BillingService.kt`
   - Backend `GOOGLE_PLAY_PACKAGE_NAME` env var

> ⚠️ **Once set and once you upload your first build, the package name CANNOT be changed.** If you typo it, you have to delete the app and start over. Verify before saving.

## 1.3 Store settings

**Setup → Store settings.**

| Field | Value |
|---|---|
| App category — Type | App |
| App category — Category | **Finance** |
| Tags | Add: `Investing`, `Personal finance`, `Stocks`. *(Avoid: "Trading", "Brokerage" — these tags map to regulated services and may trigger extra review.)* |
| Store listing contact details — Email | A monitored address — `support@apestogether.ai` |
| Store listing contact details — Phone | Optional but recommended for support credibility |
| Store listing contact details — Website | `https://apestogether.ai` |
| External marketing | "I do not target ads to children" — toggle off (we're 17+) |

Save.

## 1.4 Main store listing (the big one)

**Grow → Store listing → Main store listing.**

This is the public-facing listing users see in the store. Fill every field exactly:

### App name (30 char max)
```
ApesTogether: AI Stock Trader
```

### Short description (80 char max)
```
Verified stock strategies. Every pick tracked. Traders keep 85%.
```

### Full description (4,000 char max)

Paste the full description from `docs/ASO_STRATEGY.md` "Description" section, with these **2 modifications** for Play (also documented in the ASO doc Play section):

1. In `PRIVACY & SAFETY`, change `Apple ID / Google Play subscriptions` → `Google Play subscriptions`.
2. Replace the closing Apple disclaimer paragraph with the **Play closing paragraph** from `ASO_STRATEGY.md` "Google Play listing → Full description" section. That paragraph weaves in the longtails Play indexes for keyword search.

### App icon (512×512 PNG, 32-bit with alpha)

Drop in the icon you generated from Gemini Prompt 8.

> ⚠️ **No text in the icon.** Play rejects icons that contain readable text — and Apple does too. Just the gorilla silhouette + the chart line.

### Feature graphic (1024×500)

Drop in the graphic from Gemini Prompt 7.

> The wordmark in the feature graphic is `ApesTogether` (fused, single token). Verify this when reviewing Gemini's output before uploading.

### Phone screenshots (2 min, 8 max — we're using 8)

Drag and drop the 8 screenshots in this order (matches `ASO_STRATEGY.md` screenshot table):

1. `01-leaderboard.png` — "AI traders. Verified picks."
2. `02-trade-alert.png` — "Real-time alerts. Every move."
3. `03-sp500-comparison.png` — "Tracked vs. S&P 500."
4. `04-filters.png` — "Filter by sector or cap."
5. `05-scale-modal.png` — "Scale any portfolio."
6. `06-creator-share.png` — "Traders keep 85%."
7. `07-android-darkmode.png` — "Dark mode by default."
8. `08-android-pushalert.png` — "Push alerts on every device."

> Order matters. The first 3 carry 80% of conversion impact per the screenshot research in `ASO_STRATEGY.md`.

### Tablet screenshots (optional)

Skip for v1. Add post-launch if installs from tablets show meaningful traction.

### Video (optional)

Skip for v1. Plan to add a 30-sec preview after launch (storyboard in `ASO_STRATEGY.md` "App-preview video" section).

**Save** at the top of the page after every major field. Play auto-saves but flakily.

---

# PART 2 — Compliance forms (the policy gauntlet)

These are the cards on **Dashboard → Set up your app**. Most are short questionnaires; one (Data safety) is long. Do them in this order.

## 2.1 App access

**Dashboard → App access.**

Question: "Is all or part of your app restricted based on login credentials, membership, location, or other forms of authentication?"

**Answer: All or some functionality is restricted.**

Then add **Login instructions** for Google's reviewer:

> Username: `reviewer@apestogether.ai`
> Password: `[set this — use a password manager, NEVER hardcode]`
>
> Notes for reviewer:
> 1. Open the app, tap "Continue with Google" on the login screen, sign in with the credentials above.
> 2. The Leaderboard tab loads with verified traders ranked by 1-week performance.
> 3. Tap any trader to see their portfolio, S&P 500 comparison, and trade history.
> 4. The "Subscribe" button on a portfolio launches Google Play Billing for $9/mo. (Test cards work in your reviewer environment.)
> 5. All trades shown are virtual (paper-traded) using real market data, per our store description.

**Save.**

## 2.2 Ads

**Dashboard → Ads.**

Question: "Does your app contain ads?"

**Answer: No, my app does not contain ads.**

> If you ever add ads (we don't plan to), you must come back and update this.

**Save.**

## 2.3 Content rating

**Dashboard → Content rating.**

1. Click **Start questionnaire**.
2. Email address: same support email.
3. Category: **Reference, News, or Educational** *(this is the closest fit. NOT "Casino/Gambling" — even though the questionnaire might tempt you toward it because of "trading", trading-without-real-money does NOT qualify as gambling per Google's policy.)*

### Questionnaire answers (financial-app-specific)

| Question | Answer | Why |
|---|---|---|
| Violence | No | — |
| Sexuality | No | — |
| Profanity | No | We don't allow it in display names / shared content |
| Drugs / alcohol / tobacco | No | — |
| Real-money gambling, betting, lotteries | **No** | Critical: this is paper trading, no real-money wagering on outcomes |
| Simulated gambling / casino-style gameplay | **No** | We don't have casino mechanics |
| User-generated content | **Yes** | Display names, shared portfolio links, trade comments are user-generated |
| Users can interact / share content | **Yes** | Subscribers see traders' content; share-sheet exists |
| Shares user location | No | We don't collect location |
| Digital purchases | **Yes** | Google Play Billing subscriptions |

The result will be **PEGI 3 / IARC: Everyone** with a "Users Interact" flag — that's normal for finance apps.

**Submit.**

## 2.4 Target audience and content

**Dashboard → Target audience and content.**

1. **Target age groups:** Select **18+ only**. Uncheck everything below 18.

   > Critical for finance apps. If you accidentally include any age <18, Play applies the Designed for Families program rules + COPPA scrutiny + ad restrictions, and may reject the listing.

2. **Appeals to children?** No.

3. **Children & families program?** No.

4. **Store presence:** "My app is not targeted to children" — confirm.

**Save.**

## 2.5 News app

**Dashboard → News app.**

Question: "Is your app a news app?"

**Answer: No.** *(We're a finance / social app, not a news publisher, even though we surface trade activity in real time.)*

**Save.**

## 2.6 COVID-19 contact tracing and status apps

**Dashboard → COVID-19 contact tracing and status apps.**

**Answer: Not a public health authority app.** **Save.**

## 2.7 Data safety (the long one)

**Dashboard → Data safety.**

This is a multi-page form. Be **accurate** — your answers must match your privacy policy and your code's actual behavior. Lying here is a fast path to suspension.

### Data collection and security overview

| Question | Answer |
|---|---|
| Does your app collect or share any user data types? | **Yes** |
| Is all user data collected by your app encrypted in transit? | **Yes** (HTTPS-only via Vercel + APNs/FCM-encrypted push) |
| Do you provide a way for users to request data deletion? | **Yes** (Settings → Delete Account, per `LegalText.swift:438`) |

### Data types collected (you'll be asked for each one)

For each data type listed below, indicate: **collected = yes**, **shared = no** (unless noted), **optional vs required**, **purposes**.

| Data type | Collected? | Purpose | Optional? |
|---|---|---|---|
| **Name** | Yes (display name from Google Sign-In) | App functionality, Account management | Required |
| **Email address** | Yes (Google Sign-In) | App functionality, Account management | Required |
| **User IDs** | Yes (`User.id`, Google sub) | App functionality, Account management | Required |
| **Address** (state/country only — for tax 1099) | Yes (W-9 path only, only if user opts to be a creator and earns ≥ $600) | Tax compliance | Optional (only if becoming a creator) |
| **Tax ID (TIN/SSN)** | Yes (W-9 collected via Xero, NOT stored in our DB) | Tax compliance | Optional (only creators earning ≥ $600/yr) |
| **Phone number** | Yes (only if user opts into SMS notifications) | App functionality | Optional |
| **Purchase history** | Yes (Play Billing receipts) | App functionality | Required (for subscribers) |
| **Photos** | **No** | — | — |
| **Videos** | **No** | — | — |
| **Audio files** | **No** | — | — |
| **Files and docs** | **No** | — | — |
| **Calendar events** | **No** | — | — |
| **Contacts** | **No** | — | — |
| **App activity (in-app actions)** | Yes | Analytics, App functionality | Required |
| **App info and performance** (crash logs, diagnostics) | Yes (Firebase Crashlytics if enabled) | Analytics | Required |
| **Device or other IDs** (FCM token) | Yes | App functionality (push notifications) | Required |
| **Financial info: payment info** | **No** | (Play handles this — we never see card details) | — |
| **Financial info: purchase history** | (covered above) | | |
| **Health and fitness** | **No** | — | — |
| **Messages** | **No** | — | — |
| **Photos / videos / audio** | **No** | — | — |
| **Location** | **No** | — | — |
| **Web browsing** | **No** | — | — |

### Data sharing (with third parties)

| Recipient | What you share | Why |
|---|---|---|
| **Google** (Play Billing, FCM, Firebase) | Purchase tokens, FCM tokens, crash logs | Required for billing, push, diagnostics |
| **Xero** (creators only) | Name, email, TIN, address — for the creator only when they're being paid | Tax compliance (W-9, 1099-NEC) |
| **AlphaVantage / FMP** (market data providers) | NO user data — we send ticker symbols only, not user-identifiable info | Market data |

### Data deletion

State exactly: "Users can delete their account from Settings → Delete Account. Account deletion removes all personal data within 30 days, except records required for tax compliance (Family Apps LLC retains creator earnings + W-9 records per IRS retention rules)."

**Save and submit.** This form takes 30-60 minutes to fill out carefully. Don't rush.

## 2.8 Government apps

**Dashboard → Government apps.**

**Answer: Not a government app.** **Save.**

## 2.9 Financial features (CRITICAL for ApesTogether)

**App content → Financial features.**

> This is the form Play uses to enforce the [Financial Services policy](https://support.google.com/googleplay/android-developer/answer/9876821). Get it right or you get stuck in re-review hell. See also Google's [declaration help page](https://support.google.com/googleplay/android-developer/answer/13849271).

> **UI NOTE (updated Jul 2026):** Google reworked this form. The old option **"Personal investment research and management"** no longer exists, and there is no standalone "portfolio management (non-brokerage)" bucket. The current list is grouped as *Banking and loans / Payments and transfers / Purchase agreements / Trading and funds / Support services / Other*. Under **Trading and funds** the only stock option is the combined **"Stock trading and portfolio management."**

### What to select

**Select the bottom "Other" checkbox** (the general catch-all under the *Other* heading) and describe the feature yourself. We deliberately avoid the **"Stock trading and portfolio management"** label because it reads as a brokerage; ApesTogether is **paper trading only** — no real securities, no real money invested, no custody, no advice.

Do **NOT** select:
- ☐ Anything under Banking and loans, Payments and transfers, Purchase agreements — N/A
- ☐ Cryptocurrency wallet / exchange / NFT — N/A
- ☐ Crowdfunding and chit funds / Prediction markets — N/A
- ☐ **Stock trading and portfolio management** — implies a brokerage/managed portfolios; we're simulated + informational only
- ☐ **Financial advice** — we explicitly do not give individualized advice
- ☐ "My app doesn't provide any financial features" — risky *under*-declaration given the investing-themed listing + real market data

### "Other" description (exact copy submitted)

Short label:
```
Simulated (paper) stock-portfolio tracking & social sharing
```

Description:
```
A social, educational stock-portfolio app. Users create and track simulated "paper" portfolios using real market prices — no real securities are ever bought or sold and no real money is invested. The app does not execute trades, act as a broker, dealer, or exchange, hold or transfer user funds or securities, or provide personalized or professional financial advice. All portfolio content is informational and educational only; members can view and learn from other users' voluntarily shared paper portfolios.
```

### Fees / disclosures

- Fees: **Yes — content-access subscription fees** (paying to view a creator's shared paper portfolio; not an investment product or managed account).
- Business name: **Family Apps LLC**
- Business registration number: *(your LLC EIN — same one used in Play account verification)*
- Country/region: **United States**
- States supported: **United States only** (subscribers and creators are limited to US tax residents per `LegalText.swift:438` FAQ "Who can use this app?")

**Save.**

### Outcome (recorded Jul 7, 2026)

After submitting the **"Other"** declaration with the copy above, Play responded:

> "At the moment, you're not required to submit any additional documentation for the financial features your app provides. If this changes, we'll let you know."

Per Google's declaration help page, mandatory license-document uploads are triggered by **personal-loan** features and by **specific countries/regions** — *not* by this declaration. No license upload was requested.

> **Consistency reminders (so this holds up on review):**
> - Keep the same framing everywhere (this form, Step 2, listing, screenshots): *informational/educational only; all trades virtual/paper on real market data; no real brokerage, custody, or advice.*
> - Avoid marketing words like "invest your money," "brokerage," "advice," or "returns on real capital."
> - Scope any "no real money" claim to the **portfolio/trading feature**, not the whole app (subscriptions are real charges — see the Data Safety "Purchase history" declaration).
> - This is a regulatory framing call; confirm with counsel before relying on it. Backing position, per `LAUNCH_PLAYBOOK.md:235-244`: "ApesTogether is an informational platform. All content is educational. We do not provide individualized investment advice. The platform shows public, on-platform paper-trading performance of users who voluntarily share their portfolios."

## 2.10 Health apps

**Dashboard → Health apps.**

**Answer: My app is not a health app.** **Save.**

## 2.11 Privacy policy

**Grow → Store listing → Main store listing → Privacy policy.**

URL: `https://apestogether.ai/privacy-policy`

Verify before saving:
- The URL returns HTTP 200 (try in incognito).
- The privacy policy is publicly accessible (no login wall).
- The policy mentions the data types you declared in 2.7.
- The policy explains how to request deletion.

**Save.**

---

# PART 3 — Set up monetization

This section is **also covered in `android/README.md` Step 3** with more code-level detail. Here, only the listing-flow steps:

## 3.1 Create the two subscription products

**Monetize → Products → Subscriptions → Create subscription.**

### Subscription 1 — Monthly

- **Product ID:** `com.apestogether.subscription.monthly` (must match exactly)
- **Name:** `Monthly Subscription`
- **Description:** `Follow a trader's moves in real-time`
- **Base plan:**
  - Plan ID: `monthly`
  - Renewal type: Auto-renewing
  - Billing period: Monthly
  - Price: $9.00 USD (set per country if you localize later)
- **Offers (free trial):**
  - Eligibility: New customers acquiring this subscription for the first time
  - Phase 1: 7 days free
  - Phase 2: standard auto-renewing price

### Subscription 2 — Annual

- **Product ID:** `com.apestogether.subscription.annual`
- **Name:** `Annual Subscription`
- **Description:** `Follow a trader's moves in real-time — best value`
- **Base plan:**
  - Plan ID: `annual`
  - Renewal type: Auto-renewing
  - Billing period: Yearly
  - Price: $69.00 USD (saves 36% vs monthly)
- **Offers (free trial):** same 7-day free trial as monthly

**Activate** both subscriptions when the form lets you (you may need to fully complete the store listing first — Play sometimes blocks subscription activation until everything else is green).

## 3.2 Tax & financial information

**Setup → Payments profile.** *(Or Tools → Payments setup, depending on Play Console version.)*

- Verify Family Apps LLC business profile.
- Add bank account for receiving subscription revenue.
- Submit W-9 / business tax forms as Play requests.

## 3.3 Pricing & distribution / Small Business Program

**Monetize → Subscriptions Small Business Program.**

Apply for the **15% rev-share tier** (instead of standard 30%). Eligibility: < $1M annual revenue. **Apply on day one** — there's no penalty for applying, and once you exceed the threshold, you graduate automatically.

This is what makes the **"Traders keep 85%" claim** financially possible: subscriber pays $9, Play keeps 15% = $1.35 fee, you receive $7.65 net, of which 85% ($6.50) goes to the creator and 15% ($1.15) goes to Family Apps LLC.

> Without the Small Business Program, Play's standard 30% cut would leave you with $6.30 — not enough to support the 85% creator share at the same headline price.

---

# PART 4 — Internal Testing → Closed Testing

## 4.1 Backend prerequisites (do these before uploading the first build)

Per `android/README.md` Step 4:

1. Create the Google Cloud service account `apes-play-billing-validator`.
2. Generate JSON key, paste contents into Vercel env var `GOOGLE_PLAY_CREDENTIALS_JSON`.
3. Set `GOOGLE_PLAY_PACKAGE_NAME=com.apestogether.app` in Vercel.
4. Grant the service account **API access** in Play Console: **Setup → API access → Grant access**.
5. Redeploy Vercel.

Without these, the backend can't validate Play purchase tokens, and the Subscribe button will fail at the validation step.

## 4.2 Build a signed Android App Bundle (AAB)

Follow `android/README.md` Step 5.1:

1. Create a release keystore (one-time). Store it + passwords in a safe place.
2. **Android Studio → Build → Generate Signed Bundle / APK → Android App Bundle (.aab).**
3. Sign with your release keystore.

> ⚠️ **Lose this keystore = lose the ability to push updates.** Back it up to encrypted cloud storage (1Password, Bitwarden vault, etc.) AND a physical USB drive in a safe.

## 4.3 Upload to Internal Testing

**Testing → Internal testing → Create new release.**

1. **App Signing**: let Play manage the upload key (Play App Signing). This re-signs your upload AAB with Play's managed key. Recommended for ApesTogether — Play's key is much harder to lose than yours.
2. **Upload your .aab.** Play will scan it for issues (deobfuscation files, native library compatibility, target API level) and surface warnings.
3. **Release name:** Use the version code (e.g., `1 (1.0.0)`).
4. **Release notes:** First version — `Initial Internal Testing release.`

### Add internal testers

**Testing → Internal testing → Testers tab.**

1. **Create email list** → Name it `ApesTogether Internal Testers`. Add your own email and any teammates (≤ 100 emails for internal track).
2. Save the **opt-in URL** that appears (e.g., `https://play.google.com/apps/internaltest/4699...`).
3. On your test device:
   - Open the opt-in URL while signed in with the same Google account.
   - Tap "Become a tester".
   - Install from the Play Store link on that page.

## 4.4 Test the full happy path on a real device

Per `android/README.md` Step 5:

- ☐ Open the app, sign in with Google.
- ☐ Leaderboard loads.
- ☐ Tap a trader → portfolio detail loads, S&P chart renders.
- ☐ Tap "Subscribe" → real Google Play sheet appears (tester card auto-presented).
- ☐ Confirm purchase → backend validates → green "Subscribed" banner.
- ☐ Phone receives a trade-alert push notification.
- ☐ Open `https://apestogether.ai/p/<some-portfolio-slug>` in Chrome → app opens to Portfolio Detail (App Links verified).

**Fix any issues, push a new release to Internal Testing, repeat.**

## 4.5 Promote to Closed Testing — START THE 14-DAY GATE

> ⚠️ **Google Play 2024 policy: new personal accounts and new "Organization" accounts publishing their first app must run a Closed Testing track with at least 12 testers for at least 14 continuous days before being eligible for Production.**
>
> **This is a hard gate.** It doesn't matter if your app works perfectly — Play will refuse Production approval until 14 days have elapsed AND 12+ testers have actually opted in.
>
> **Start this clock as early as possible.** Per `LAUNCH_TODO.md:111` and `LAUNCH_PLAYBOOK.md` Day 22, this is what gates the public launch date.

### Steps:

**Testing → Closed testing → Create new track.**

1. Track name: `Closed Testing` (or `Beta`).
2. Add testers — recruit at least 12 people who will actually open the app. Suggested sources:
   - Family Apps LLC team
   - Existing waitlist signups who said they want to test
   - Personal network — friends who hold investment accounts
3. Send them the opt-in URL. Email template:

   > Subject: ApesTogether beta — your access link
   >
   > Hi [name],
   >
   > Thanks for being part of the ApesTogether closed beta. Click the link below on your Android device while signed in to Google with this email address:
   >
   > [opt-in URL]
   >
   > Tap "Become a tester" → "Install on Google Play". Your feedback in the next 14 days is what unlocks our public launch.
   >
   > — [Your name]

4. Promote your latest Internal Testing release to Closed Testing (right-click the release → Promote to track).
5. **Mark the 14-day countdown on your calendar.** During this window:
   - Keep pushing fixes via Internal → Closed promotions.
   - Talk to testers, collect feedback, iterate.
   - **Don't** restart the 14-day clock by changing tracks.

---

# PART 5 — Submit for Production

## 5.1 Pre-submission checks

Before you click submit, verify in Play Console:

- ☐ All "Set up your app" cards in Dashboard are green.
- ☐ Store listing is complete and previewed.
- ☐ Pricing & distribution: countries selected (recommend **United States only** for v1, expand later).
- ☐ Both subscription products are **Active**.
- ☐ 14 days have elapsed since Closed Testing started.
- ☐ At least 12 testers have opted in (Play will show a count).
- ☐ Backend env vars set: `GOOGLE_PLAY_CREDENTIALS_JSON`, `GOOGLE_PLAY_PACKAGE_NAME`.
- ☐ `assetlinks.json` placeholders replaced with real release-signing-cert SHA-256s. Verify with `adb shell pm verify-app-links --re-verify com.apestogether.app`.
- ☐ Privacy policy URL returns 200, content matches Data safety declarations.
- ☐ Reviewer credentials set in App access and the account works.

## 5.2 Promote to Production

**Production → Create new release.**

1. Promote the latest Closed Testing release.
2. Release notes (this becomes the "What's new" line in store):

   ```
   ApesTogether v1.0 — initial public launch.

   • Follow verified stock strategies from real traders
   • Real-time push alerts on every trade
   • Performance benchmarked vs. the S&P 500
   • Filter by sector and market cap
   • Adjust portfolio size to match your scale

   For educational purposes only. All trades on the platform are virtual using real market data.
   ```

3. **Rollout percentage:** start at **20%** for the first 48 hours. Watch crash rate, ANR rate, install-uninstall ratio. If clean, ramp to 50%, then 100% over the next week.
4. **Submit for review.**

## 5.3 What happens during review

- Google reviews typically take 3–7 days for new apps. Finance category reviews often take longer (5–10 days) because of policy scrutiny.
- You'll get email notifications at major status changes.
- If approved → app goes live at the rollout percentage you set.
- If rejected → see Part 6.

---

# PART 6 — Common rejections (read BEFORE submitting)

These are the rejections most likely to hit a finance app like ApesTogether. Avoid them by reading the policy linked, fixing in advance, and double-checking the listing before you click submit.

## 6.1 Financial Services policy violations

**Most common:** the listing implies real-money trading or brokerage services.

| Symptom | Fix |
|---|---|
| Description uses "real trades" / "real money execution" | Replace with "verified strategies, paper-traded on real market data" |
| Title contains "Trading" or "Broker" | Use "Stock Trader" or "AI Trading" — Trading as a noun describing the action of users trading is fine; "Broker" is not |
| Screenshots show realistic balances / earnings | Use modest sample numbers (+2.4%, not +47%) and the educational disclaimer |
| Financial Features form: "Stock or commodities trading" checked | Uncheck. Use only "Personal investment research and management" |

## 6.2 User-generated content (UGC) policy violations

If reviewers find a trader display name with profanity or a portfolio comment that violates policies, the WHOLE app gets rejected.

**Mitigation:**
- Pre-launch: review every existing trader's display name + portfolio for offensive content.
- In-app: ensure the moderation/reporting system in `mobile_api.py` is functional.
- Listing-level: in Data safety, confirm "User can interact with each other" is checked.

## 6.3 Privacy / Data safety mismatches

Play cross-references your Data safety form against:
1. Your privacy policy
2. Static analysis of the AAB (does the manifest declare permissions matching the data you said you collect?)
3. Network traffic patterns from the Closed Testing builds (do you actually send to those endpoints?)

**Mitigation:** the answers in Section 2.7 above should match `legal/privacy-policy.md` exactly. If they don't, fix the privacy policy *first*, then re-fill Data safety.

## 6.4 Missing 14-day Closed Testing

Submitting to Production before 14 days of Closed Testing have elapsed = automatic rejection with the message "Your app must complete a closed test of at least 14 days." Just wait it out.

## 6.5 Subscription cancellation flow

Play requires **clear, accessible cancellation instructions** in your store listing. Our description already includes:

> Cancel anytime through your Apple ID / Google Play subscriptions

(Replace "Apple ID / " in the Play version per `ASO_STRATEGY.md`.) That single line satisfies the requirement. Don't remove it.

## 6.6 IAP-only payment policy

Play requires that **all in-app digital purchases must use Google Play Billing**. Our subscription flow does — see `BillingService.kt`. Do NOT add a "Pay with Stripe" button as an alternative — that's an instant rejection.

> Exception: there's a 2024 EU regulation allowing alternative billing in the European Economic Area, but you have to opt in explicitly and we're US-only at launch, so this doesn't apply.

## 6.7 Target API level

Per Play's 2026 policy, your AAB must target **Android 14 (API 34)** at minimum. Our `app/build.gradle.kts` already targets API 35 — you're fine. Just don't downgrade.

## 6.8 If you do get rejected

1. Read the rejection email carefully — Google now provides specific policy citations.
2. Fix the issue (don't argue — Play's enforcement is mostly automated).
3. **Use the Appeal process only when you genuinely believe the rejection is incorrect.** Frivolous appeals get the developer account flagged. For ApesTogether, a finance-related rejection is more likely a real policy issue than a false positive.
4. Resubmit. There's no penalty for fixing and resubmitting.

---

# Quick reference — fields and their values

If you just want to copy-paste, here's everything in one place:

| Play Console field | Value |
|---|---|
| App name (creation modal) | `ApesTogether` |
| Default language | English (United States) |
| App category | Finance |
| Tags | Investing, Personal finance, Stocks |
| Title (Main store listing) | `ApesTogether: AI Stock Trader` |
| Short description | `Verified stock strategies. Every pick tracked. Traders keep 85%.` |
| Full description | See `docs/ASO_STRATEGY.md` "Description" section + Play closing paragraph |
| Privacy policy URL | `https://apestogether.ai/privacy-policy` |
| Contact email | `support@apestogether.ai` |
| Contact website | `https://apestogether.ai` |
| Package name | `com.apestogether.app` |
| Target audience | 18+ |
| Content rating category | Reference, News, or Educational |
| Ads | No |
| Financial features | Personal investment research and management |
| Data safety encryption | Yes (HTTPS in transit) |
| Data safety deletion | Yes (Settings → Delete Account) |
| Subscription monthly product ID | `com.apestogether.subscription.monthly` ($9 USD, 7-day trial) |
| Subscription annual product ID | `com.apestogether.subscription.annual` ($69 USD, 7-day trial) |
| Small Business Program | Apply for 15% rev share |
| Internal Testing minimum testers | 1 (yourself) |
| Closed Testing minimum testers | 12 |
| Closed Testing minimum days | 14 |
| Production rollout (initial) | 20%, ramp to 100% over 7 days |

---

**Cross-references:**
- `docs/ASO_STRATEGY.md` — all listing copy, screenshot prompts, keyword sets
- `android/README.md` — technical setup (signing keystore, billing service account, AAB upload, FCM, App Links)
- `docs/LAUNCH_PLAYBOOK.md` §11 — compliance guardrails that constrain listing copy
- `LAUNCH_TODO.md` Section C — Android workstream status (what's done vs pending)
