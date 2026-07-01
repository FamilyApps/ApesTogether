# Marketing & Launch Budget Plan

_Created 2026-06-30. Reference doc for launch + post-launch growth spend._

## ⚠️ Paid reviews — DO NOT

Buying or incentivizing App Store / Play Store reviews violates **Apple
Guidelines 3.2 & 5.6** and **Google Play** policy. Enforcement = app removal
and **developer-account termination** — an existential risk to the whole
launch. The legitimate way to lift ratings volume is the in-app prompt
(`SKStoreReviewController` on iOS / Play In-App Review on Android) fired at a
"happy moment" (e.g., after a good performance day or a successful trade copy).

## Note: "influencer" in this codebase ≠ marketing outreach

The word *influencer* throughout the repo (`XERO_PAYOUT_INTEGRATION.md`,
`TopInfluencersView`, payout tables) refers to **creators being paid via the
payout pipeline** — it is **not** a marketing/outreach plan. As of this doc,
there was **no documented influencer *marketing* outreach plan**; this doc
starts it (see the playbook below).

## Budget tiers

### $0 — organic baseline (do these regardless of budget)
- Finish ASO (titles/subtitles/keywords/screenshots — see `ASO_STRATEGY.md`).
- Waitlist → launch-day email blast.
- Product Hunt launch (free).
- Reddit (r/investing, r/wallstreetbets — respect self-promo rules).
- Organic FinTok / X / IG (accounts already linked in the site footer).
- In-app ratings prompt at a happy moment.

### $1,000
- **~$700 Apple Search Ads** — highest-intent installs. Bid on brand + competitor
  terms ("Public", "eToro", "social trading", "copy trading").
- **~$300** one micro-influencer post *or* a small TikTok Spark Ads test.

### $4,000
- **~$2,000–2,500 Apple Search Ads** — scale winning keywords + Discovery.
- **~$1,000** — 2–3 finance micro-influencers (authentic demos; performance-based where possible).
- **~$500** — an **App Preview video** (biggest conversion lever after screenshots).

## Micro-influencer outreach playbook (preferred lever)
- **Targets:** finance/investing micro-influencers (10k–100k) on TikTok, YouTube Shorts, X.
- **Comp models:** flat fee · affiliate/referral (tie to the existing in-app referral system) · performance (CPI).
- **Deliverable:** authentic 30–60s demo — leaderboard → copy a trade → real-time alert.
- **Tracking:** UTM links → the app already logs `PageView` / `LinkClick`.
- **Compliance:** require FTC `#ad` / `#sponsored` disclosure.

## Highest-ROI, budget-agnostic
App Preview video · Apple Search Ads · referral loop · in-app ratings prompt.
