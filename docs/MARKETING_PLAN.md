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

---

# Demand & Scarcity Strategy (added Session 26, 2026-07-13)

_Prompted by the Doublespeed/a16z bot-farm article (manufactured scarcity as
launch fuel). Answers: can we gate access, should we, and how._

## ⚠️ VERDICT (same session, after product-fit review — read this first)

USER challenged the invite-gate idea and the challenge holds. **Scarcity
gating is a bad fit for ApesTogether** and Phase B below is **REJECTED**:

1. **AT is a marketplace where every user is also supply.** Anyone who joins
   and trades adds leaderboard content. Gating shrinks the shelf on both
   sides — unlike Clubhouse, where each invitee WAS the product, our product
   improves with open participation.
2. **Our core asset is time.** A track record can't be manufactured or
   accelerated — the leaderboard only gets interesting after months of
   history. Gating early users starves the exact asset launch depends on.
3. **Scarcity generates zero attention; it only amplifies attention you
   already have.** Robinhood's waitlist worked because "$0 commissions" was
   a self-evidently huge, universal benefit that earned press FIRST; the
   queue mechanics compounded it. "Follow verified traders" is not legible
   as a benefit until the leaderboard has history — weak waitlist fuel.
4. **Audience mismatch.** The r/wsb crowd runs on "positions or ban" —
   receipts culture is a PERFECT product fit, but that same crowd is
   allergic to velvet ropes and growth-hack gimmicks. A public leaderboard
   anyone can lurk fits; an invite gate reads as fintech-bro scammy.

**What replaces artificial scarcity: product-native urgency.** Your track
record starts the day you join — "every week you wait is a week missing
from your verified history" is true, unfabricatable, and targets the trader
side we most need. Plus a capped **Founding Trader badge** (cheap, honest
status). That's ALL the scarcity we keep.

**Adopted plan: open access + sequenced simple strategy** (Labor of Love
lesson applied): soft-launch open → harden with a trickle of organic users
(the mandatory Play closed-test period doubles as this QA window) → THEN
fire the one-shot earned-media spike (WSJ playbook) once crash-free, with
micro-influencers + founder-led social as the steady drumbeat. Press hook =
"disclosed AI bots vs. verified humans on one leaderboard," not "new
copy-trading app." Details preserved below for reference; Phase B is dead.

## The bright line: scarcity ✅, fabrication ❌

Our entire product thesis is *verification vs. unverifiable claims*. If we're
ever caught faking demand (botted content, invented waitlist numbers, fake
"sold out" claims), the product thesis dies with the story — for us it's not
a marketing risk, it's an existential one. The Doublespeed lesson we CAN
take: **real, mechanically-enforced scarcity** (caps, invite codes, timed
drops) is honest and works. The lesson we CANNOT take: astroturfed volume.
Related existing rule: no paid reviews (top of this doc). Our AI traders are
*disclosed* AI competing on the leaderboard — a feature, never a sock puppet.

**Honest scarcity rationales we can state publicly (all true):**
- Market-data API rate limits (price checks scale with active traders)
- Solo founder = finite support capacity during beta
- Google *requires* a capped closed test (12+ testers / 14 days) before
  production access — the platform itself imposes scarcity; use it

## Can we gate access to invitees only? (store policy)

**Yes — with conditions.** Both stores require the *listing* to be publicly
downloadable, but gating *account creation / functionality* behind an invite
is allowed (precedents: Clubhouse, Superhuman, Bluesky):

- **Apple** — App Review Guideline 2.1: reviewers must be able to access the
  full app → provide a demo account **and a working invite code** in App
  Review notes. Guideline 2.3 (accurate metadata): the listing should say
  it's invite-gated.
- **Google Play** — the **App access** declaration in Play Console must
  include working credentials/instructions for any restricted parts. The
  minimum-functionality policy means a hard login wall with nothing behind
  it is risky — so ship a **read-only leaderboard preview** pre-invite
  (which is also our best conversion screen).
- **Distribution-level gating alternatives:** TestFlight (10k cap — cap is
  real and Apple-enforced) and Play closed testing, which we're in anyway.

## Current state (what exists today)

- Waitlist: `BetaWaitlist` model, landing form with investor/trader
  segmentation, live public count (`/api/waitlist/count`), welcome email.
- No referral mechanics, no positions, no invite codes. The stale
  "Beta opens June 1 — limited spots" urgency line was replaced Session 26
  with honest invite-wave framing.
- In-app referral system exists (see referral tie-in in the influencer
  playbook above) — waitlist referrals can reuse the pattern.

## Recommended mechanics (phased)

### Phase A — pre-launch *(SCALED BACK per verdict: no queue-jump build;
waitlist stays a simple email collector + trader segmentation. Revisit
referral mechanics only if pre-launch traffic actually materializes.)*
1. **Waitlist 2.0: position + queue-jump referrals.** On signup show
   "You're #N in line" + a unique referral link; each referral jumps the
   queue. Tiered rewards (tiers convert better than a single ask):
   3 referrals = guaranteed launch-day invite · 10 = founding badge +
   3 invite codes to give away · 25 = 3 months of one subscription free.
   (Robinhood's pre-launch waitlist — ~1M signups — is the canonical run
   of this play in our exact category.)
2. **Weekly invite drops, fixed cadence.** Announce a fixed weekly slot
   (e.g., Wednesday 4 PM ET) when the next wave of beta invites goes out.
   Recurring content beat for X/TikTok + honest urgency. Numbers are real:
   "40 invites this week" because that's what support capacity allows.

### Phase B — launch window — ❌ REJECTED (see verdict) — kept for the record
3. **Soft invite gate at signup.** App public on both stores; anyone can
   browse the read-only leaderboard preview; creating an account requires
   an invite code (from a user, a drop, or the waitlist email). **Every new
   user gets 3 invite codes** (Gmail model) — turns each user into a
   recruiter and keeps growth attributable. Auto-expire the gate (~week 4
   or at a user cap) — scarcity that never releases turns into abandonment.
4. **Founding-trader cap.** Exactly 100 "Founding Trader" slots (permanent
   badge). Trader supply is the marketplace constraint anyway; capping it
   is honest, creates status, and gives the waitlist's trader segment a
   reason to move fast.
5. **Store demand mechanics:** Google Play **pre-registration** and Apple
   **pre-orders** (up to 180 days out) — both convert waitlist hype into a
   day-one install spike, which is what chart rank + featuring algorithms
   reward.

### Standing rules (July 2026 dynamics)
- **Founder-led > brand account.** Post-slop-backlash, builder accounts
  outperform brand accounts; the playbook's build-in-public calendar is
  correctly founder-voiced. Our anti-slop positioning ("verified humans
  and *disclosed* AIs, in the most botted content category — fintok") is
  the marketing angle the Doublespeed backlash hands us for free.
- **AI-search discoverability (GEO).** People now ask ChatGPT/Perplexity
  "app to follow verified traders" — citations come from Reddit threads,
  comparison content, and crawlable FAQ/structured pages. Our landing FAQ
  and genuine Reddit participation double as GEO. Add one "ApesTogether
  vs Dub vs eToro" comparison page on the site.
- **Never**: bought reviews, botted engagement, fake counts, "sold out"
  claims that aren't mechanically true. Show the live waitlist counter
  only once it clears ~100 (small real numbers are anti-social-proof).

## Review-submission impact (do not skip)
If the invite gate ships: put a working invite code + demo account in
**App Review notes** (Apple) and complete the **App access** declaration
(Play) or expect rejection. Add to both store submission checklists.
