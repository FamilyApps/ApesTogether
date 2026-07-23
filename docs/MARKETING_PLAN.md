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

## Founding Trader badge — RULES (defined Session 27; IMPLEMENTED Session 28)

**Status: BUILT (Session 28).** Award sweep + payload fields + gold badge
chips shipped across backend, Android, and iOS (iOS ships with the next Mac
build). Award runs automatically after a user's first trade (live +
after-hours-queued paths) and manually via
`POST /api/mobile/admin/founding-trader/award` (admin 2FA) for
backfill/verification. Web UI chip still pending (post-launch). Rules, so
every doc and outreach message means the same thing by "founding trader":

1. **Who:** the first **100 human traders** to place at least one trade,
   ranked by first-trade timestamp. Beta trades count (closed-test and
   TestFlight users took the early risk; they get the reward).
2. **Bots NEVER qualify.** House/disclosed-AI accounts, admin accounts,
   and internal test accounts are excluded. The badge is a human status
   marker — house accounts occupying scarce slots would be exactly the
   manufactured scarcity we swore off. (Wolff and the AI funds already
   have their own AI identity; they don't need this one.)
3. **Permanent + irrevocable.** Survives pausing subscriptions, going
   inactive, or turning off "Allow New Subscribers." Not transferable.
4. **What it confers:** a badge on the leaderboard row + public portfolio
   profile. Status only — no fee break, no placement boost (a paid-for or
   perk-loaded badge would corrupt the leaderboard's neutrality).
5. **Public counter is allowed** ("73/100 founding slots claimed") once
   meaningfully underway (~20+) — honest because mechanically enforced.

**As built (Session 28):** `User.extra_data['founding_trader']` =
`{rank, first_trade_at, awarded_at}`, awarded by an idempotent sweep
(`mobile_api._award_founding_trader_badges`) that ranks eligible humans by
`MIN(buy/sell Transaction.timestamp)` and freezes at 100. Exclusions
enforced in code: `role != 'user'` (bots + admin), `is_company_owned`
(founder + reviewer accounts), copytrade bots, soft-deleted users.
Triggers: first live trade (`execute_trade`), market-open queued-trade
settle (`process_queued_trades`), and admin backfill endpoint. Surfaced as
`founding_trader` on the leaderboard `user` object and portfolio `owner`
object; gold FOUNDER chip on leaderboard rows + "Founding Trader" pill in
the profile badge row on Android and iOS. Web UI chip: post-launch.

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

---

# Full-Plan Review & Trigger-Based Sequencing (Session 33, 2026-07-22)

_USER directive: **no launch rush — do it right.** Full review of PLAYBOOK /
CONTENT / OUTREACH / this doc + fresh channel research. This section
supersedes the playbook's calendar dates; the playbook's CONTENT and
SEQUENCE remain valid, re-anchored to triggers below._

## Core finding: the plan is date-broken, not content-broken

The 49-day playbook assumed 7 weeks of audience-building BEFORE store
launch (Apr 14 → Jun 1). None of it ran (social handles still unregistered
at Day 49+), yet store approval is now days away. The fix is NOT to cram —
it's the already-adopted quiet-launch verdict taken seriously: **store
availability ≠ launch moment.** Store-live day is infrastructure. The
marketing launch is a separate, later, gated event we fire exactly once.
This also converts our biggest weakness (no audience yet) into the moat:
**every quiet week adds verified track-record history that competitors'
marketing can't fabricate** — the product's core asset compounds during
the delay. "No rush" is strategically correct, not a concession.

## Phases (trigger-based — no calendar dates)

- **Phase 0 — NOW → Play/Apple approval (infrastructure):** register the 6
  social handles (squatting risk — overdue since Session 13); press-kit
  skeleton; "vs Dub vs eToro" GEO comparison page; first waitlist nurture
  email ("build log #1"); Android in-app review prompt (gap #9).
- **Phase 1 — approval → QUIET availability (supply hunt):** promote to
  production silently; waitlist email only ("you're early — the Founding
  Trader clock is running"). 80% of effort = **1:1 recruitment of the
  first 25 human traders** (operator-DM playbook — see gap #2). Founder
  build-in-public cadence starts at a SUSTAINABLE rate (3 X posts + 1
  TikTok/wk, founder-voiced, not the playbook's daily grind). Harden app;
  collect testimonials; review prompts firing.
- **Phase 2 — proof accumulation (4–10 wks):** exit gates for Phase 3:
  crash-free ≥ 99.5% over 2 wks · ≥ 20 human traders with ≥ 5 trades ·
  ≥ 10 traders with 30 d+ verified history · D7 retention ≥ 30% · 5–10
  testimonials in hand · press kit + App Preview video DONE · Founding
  Trader counter meaningfully underway. Build ASA keyword list; dry-run
  attribution.
- **Phase 3 — the one-shot public launch:** date picked 2–3 wks out ONLY
  when every gate passes. Order: WSJ exclusive (existing relationship)
  → embargo week: Tier 2/3 press + Reddit posts + influencer wave +
  waitlist blast + $2-bill stunt + Apple Search Ads on. Product Hunt at
  most a side-beat (see verdict below). Hook: "disclosed AI bots vs.
  verified humans on one leaderboard" — the anti-slop angle is strongest
  while the backlash is current.
- **Phase 4 — post-spike engine:** ASA scale-up on winning keywords ·
  micro-influencer affiliate program riding the in-app referral system ·
  monthly "humans vs AI — Q results" content beat (leaderboard IS the
  content) · GEO/SEO expansion · ratings flywheel · store-featuring
  pitches to Apple/Google editorial (free long shot).

## Product Hunt — DEPRIORITIZED (2026-07-22 research)

2026 reality: 500+ launches/day (mostly AI tools), audience drifted from
buyers to browsers, B2C consumer apps convert poorly, and guidance is
explicit — skip if consumer-facing, pre-testimonials, or self-hunting.
Expected yield even at top-5: low-hundreds of signups. **Verdict: never
the launch moment; optional Phase 3/4 side-beat only if a credentialed
hunter materializes. Ignore the fake-upvote vendors that will DM on
launch.** (Playbook §PH copy stays — it's fine as-is if used.)

## Gap register (from the full review)

1. **Launch-moment ambiguity** — playbook Phase 7 still treats store-live
   day as blast day; contradicts the quiet-launch verdict. FIXED by the
   phases above.
2. **No trader-supply pipeline (BIGGEST GAP).** "Supply first" is the
   playbook's own #1 principle, yet journalists are name-listed and
   traders aren't. Need: a named list of 25 target humans (finance-Discord
   mods, r/algotrading posters with public track records, FinTwit paper-
   trading accounts, NYU/Columbia/Baruch club officers), a personal DM (not
   template blast), white-glove onboarding, Founding Trader slot as the
   honest hook. Owner: founder; Cascade drafts the target list + DM.
3. **Cold-start content** — partially covered by disclosed AI bots (built);
   human seeding still required (#2).
4. **Waitlist rot** — signups have heard nothing for months; only
   countdown emails exist. Add a monthly founder "build log" nurture email
   (first one in Phase 0) or the launch-day blast lands on a dead list.
5. **Unsustainable posting cadence** — 49 days × 3+ platforms daily is
   fantasy for a solo founder mid-bugfix. Adopted: 3+1/wk founder-voiced
   floor; playbook content library becomes a menu, not a schedule.
6. **Referral loop unwired to marketing** — in-app referral exists but no
   onboarding surface pushes it at happy moments, and influencer comp
   isn't tied to it. Phase 4 affiliate program should ride it.
7. **Install attribution hole** — UTMs cover web only; store installs are
   blind. Cheap fix: "How did you hear about us?" one-tap survey in
   onboarding (build during Phase 1); ASA/Play attribution later.
8. **Press kit + App Preview video unstarted** — both are Phase 2 exit
   gates; the video is the top store-conversion lever after screenshots.
9. **Android in-app review prompt MISSING** — iOS has it
   (`TradeSheetView.swift` post-trade); Android has no Play In-App Review
   call. Add to v7 (small, no policy risk when unconditional-frequency
   rules respected). The ratings flywheel is our only legit ratings lever.
10. **GEO page unbuilt** — "ApesTogether vs Dub vs eToro" comparison page
    + crawlable FAQ; AI-search referrals compound with zero spend.
11. **Store featuring never planned** — App Store featuring nomination
    form + Play editorial pitch, post-spike.
12. **KPI tracker has no owner/cadence** — re-point the playbook KPI table
    at the phase gates above; review weekly during Phases 1–2.

## What stays exactly as-is

Compliance guardrails (playbook §11) · messaging rules (§2) · no-paid-
reviews / no-fabrication bright lines · open-access verdict · Founding
Trader rules · content library + outreach templates (re-dated) · WSJ-
exclusive-first press strategy · $2-bill stunt (parked for Phase 3 week).
