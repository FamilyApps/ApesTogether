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

---

# Unified Sector-Supply Plan — bots + human creators (Session 42, 2026-08-21)

The leaderboard is the storefront; this section governs what stocks it.
Principle: **supply follows demand, bots follow humans.** Bots are
scaffolding — they make the board look alive and give every human creator
a race to run in; humans are the product. All bot creation goes through
the admin panel batch tools (`generate_bot_batch` honors per-sector
`industry=`); sector vocabulary = `bot_personas.INDUSTRY_WEIGHTS` (9
industries: Tech 20 / Finance 14 / Consumer 14 / Healthcare 12 / Energy 10 /
ETF 10 / Industrial 8 / Real Estate 8 / General 4).

## Current state — ACTUALS recorded 2026-08-21 (USER admin-panel pull)

12 live bots = 10 strategy bots + 2 copytrade bots (CoastHillBear
"Diversified" + marblethehill72 Technology — the "—"-strategy pair the
drift checks skip):

| Sector | Live bots | Phase-1 target | Gap | Who |
|---|---|---|---|---|
| Technology | 4 (3 strategy + 1 copytrade) | 3–4 | ✓ full | fund.finance2024 (social_momentum), zen1889 (sector_rotation), chart1658 (value), marblethehill72 (copytrade) |
| Consumer | **0** | 2–3 | **+2–3 ⚠ priority** | — (meme-adjacent sector EMPTY; r/wsb audience overlap) |
| ETF | **0** | 2 | **+2 ⚠ priority** | — (the "boring benchmark" bots humans love to beat) |
| Finance | 1 | 2 | +1 | moon-cash2021 (earnings) |
| Healthcare | 3 | 2 | ✓ over — no action | candle3873 (balanced), divi51 (insider_follower), panther3765 (news_reactor) |
| Energy | 1 | 1–2 | +1 optional | panther2585 (dividend_growth) |
| Industrial | **0** | 1 | +1 | — |
| Real Estate | 1 | 1 | ✓ | panther59wizard (swing) |
| General | 1 | 0–1 | ✓ | apex1575 (momentum) |
| Diversified (copytrade) | 1 | n/a | — | CoastHillBear |
| **Total** | **12** | **18–20** | **+6–8** | |

**TOP-UP BATCH SPEC (execute Mon 8/24 per the day-by-day):** 3 Consumer +
2 ETF + 1 Finance + 1 Industrial (+1 Energy if going to 20). Vary
strategy archetypes within each sector batch (momentum/value/swing mix —
`generate_bot_batch(count, industry=...)` already diversifies unless
`strategy=` is pinned). No Healthcare, Tech, or General additions.

## Standing rules

1. **Baseline top-up (once, at quiet launch):** bring every major sector
   to the Phase-1 target above (~18–20 total). No further calendar-driven
   bot creation.
2. **Human-arrival trigger:** when a human creator joins a sector with <2
   bots, spin up 2 same-sector bots within a week — every human gets
   peers to beat. The DM hook writes itself ("our AI accounts average +X%
   — think you can beat the machines?" — AGGREGATE only, never "our Energy
   AI": naming a sector's AI pins the account, and identity is the crown
   jewel).
3. **Demand trigger:** if portfolio-view analytics show a sector drawing
   views with no supply, add 1–2 bots there.
4. **Ceiling:** bots ≤ 2× human creators once ≥5 humans exist. A board
   that is mostly house pills reads as a ghost town to exactly the
   audience we court. Pause bot creation, never cull (track records are
   the moat — deleting one destroys real history).
5. **AI-vs-human framing — IDENTITY-SAFE ONLY (corrected Session 43c):**
   bot identity is NEVER externally differentiated — crown jewel, and it's
   ENGINEERED IN: `_founding_trader_house_pill()` gives house accounts a
   rankless gold pill precisely so badge presence can't discriminate bots
   from humans (Session 42's "house pill" note meant THIS — Cascade
   misread it as a bot-disclosure tag; all "disclosed AI" copy purged
   Session 43c). Content may say AIs EXIST on the board and how the
   machines are doing IN AGGREGATE — never map an AI to a username, rank,
   or sector slot.

## Launch-window timing rules (Session 43b research — early access vs the Nov launch)

USER asked whether we add "many more bots after the real launch than during
early access." Research verdict: **the count may end up higher post-launch,
but the CALENDAR logic is the reverse of the intuition, because track-record
age cannot be manufactured retroactively.** A bot created in November has a
3-day chart on launch day; a bot created in August has a 10-week one. The
launch story leans on months of humans-vs-machines data — aggregate fleet
age is the asset that can't be bought later. Hence:

6. **NO FLEET-WIDE WIPE at publish/soft-launch — with ONE exception.**
   The fleet keeps its Mar–Aug history: aggregate age is what makes the
   spike-week claim "humans and machines have been competing for months"
   true, and pre-publish account age has a natural true cover (internal
   beta/testing period — every app has one). EXCEPTION (Session 43c, USER
   + attorney): **Wolff's Flagship Fund + The Grok Portfolio get an
   in-place fresh-start reset at Publish** (LAUNCH_TODO #16 spec) so their
   charts begin day-0 of early access. Junk test accounts stay off
   marketing surfaces — flag any account to exclude and we'll hide it.
7. **Early access (now–Oct 14):** Mon 8/24 baseline top-up to 18–20, then
   TRIGGER-DRIVEN ONLY (rules 2–3). Human-arrival adds during Sep–Oct
   organically produce bots that are weeks old by launch.
8. **BOT FREEZE Oct 15 → end of spike week (~Nov 21):** no new house bots.
   Any bot on the board Nov 10 has ≥4 weeks of chart. Zero creations during
   the spike itself.
9. **Post-launch (Dec+):** demand triggers fire far more often at
   spike-scale traffic, so total additions will likely exceed the EA period
   — the USER's intuition, validated — but they stay demand-PULLED (rules
   2–3), never calendar mass-adds, and the ≤2×-humans ceiling (rule 4)
   holds. The real post-launch bot-scaling channel is the **Trader API
   (UC-A, Dec build)**: third-party bots grow the AI side without growing
   the house fleet. House bots trend toward a curated benchmark layer, not
   a growth lever.
10. **Capacity gate per batch:** after every batch, verify AV `no_calls`
    headroom + cron durations (SCALING_TRIGGERS.md thresholds); the fleet
    also grows snapshot/close-table load — tonight's stale-close incident
    (LAUNCH_TODO #11) is the cautionary tale.

### The whole cadence in one table (Session 43c — USER asked for it plainly)

| Period | How many bots you create | The rule | Why |
|---|---|---|---|
| **Mon 8/24 (one sitting)** | **+6–8 → 18–20 total** | One-time top-up per the SECTOR table spec above: 3 Consumer + 2 ETF + 1 Finance + 1 Industrial (+1 Energy optional). | Every sector shelf looks stocked for the first early-access visitors, and every one of these bots has an ~11-week chart by launch day. This is the ONLY calendar-driven batch, ever. |
| **8/25 → 10/14 (early access)** | **~0–10, only when a trigger fires** | ① *Human-arrival trigger:* a human creator joins a sector with <2 bots → create 2 same-sector bots within the week ("our Energy AI is up X% — beat it" is the DM hook). ② *Demand trigger:* analytics show a sector drawing views with no supply → add 1–2 there. No trigger = no bots. | Bots follow humans, never the calendar. Volume is set by how recruitment goes, and anything created in this window still ages ≥4 weeks before launch. |
| **10/15 → ~11/21 (FREEZE)** | **0 — no exceptions** | Hard freeze through the spike week; triggers queue up but don't execute. | The spike-week story is "months of humans-vs-machines data" — aggregate fleet age is the asset, and late adds dilute it. Ops/capacity stability (AV budget, crons) during the highest-traffic window. And tail-risk hygiene: if the fleet were ever unmasked, a launch-week creation burst reads as fake-user seeding. |
| **11/22+ (post-launch)** | **Trigger-driven; likely MORE total than EA** | Same two triggers, which fire much more often at spike-scale traffic; ceiling: house bots ≤ 2× human creators, always. New-bot thin charts are fine now — they sit next to months-old accounts on an established board. | Post-launch the AI side should grow via the **Trader API (third-party bots — real users, real payouts)**, not house pills. House bots become a curated benchmark layer; mass-adding them would dilute the humans-beat-bots story the content engine runs on. |

## Gifted subscribers (Session 43b — USER: "gift people subscriptions to get them excited")

**Already fully built — no new code needed** for the main case:
`/admin/bot/gift-subscribers` (POST, admin-2FA; works for ANY user despite
the name) + admin-panel gift modal. Increments
`AdminSubscription.bonus_subscriber_count`; creator sees subscriber count
rise and **gets paid the real $6.50/sub, company-funded** (no store fees, no
platform cut; separate `bonus_payout` line in XeroPayoutRecord; panel shows
the company obligation split; triggers W-9 like real income; month-end
tracking already on the ~10/3 calendar row).

- **What it's FOR (creator-side excitement):** show a new Founding Trader
  real earnings potential — e.g. gift 2–3 subs as a welcome. Use sparingly
  and log a `reason` every time; each gifted sub is a real recurring company
  cost ($6.50/mo) and a real 1099 number.
- **DISCLOSURE TO CREATORS: NONE (USER decision, Session 43c).** Recipients
  are never told subs were gifted — from their side every subscriber is
  organic. (Demand-seeding; the money is real, the creator is genuinely
  paid.) This decision creates FOUR standing guardrails:
  ① **Never remove a gift abruptly** — a creator watching subs vanish with
  no cancel-notification will investigate; treat every gift as a
  multi-month commitment and let attrition happen only alongside real
  churn.
  ② **Keep gifts small (1–3/creator)** so no creator's public brag ("5 subs
  in week 1!") is *mostly* company-manufactured — their posts become our
  receipts by proxy.
  ③ **We never cite subscriber/revenue aggregates in press or posts without
  netting out gifted counts internally first.**
  ④ **The admin `reason` field is now the ONLY paper trail — fill it every
  single time.**
- **What it's NOT:** it does not grant any recipient ACCESS to a portfolio
  (it's a counter, not a comp account). Gifting access to would-be
  SUBSCRIBERS = Apple Offer Codes / Google Play promo codes (store-native,
  auto-converts to paid — the better funnel anyway). ⚠ PRE-FLIGHT before
  ever issuing codes: verify our webhook + `is_trial` pipeline handles
  offer-code/promo redemptions ($0-revenue transactions — same bug class as
  the Session-43 trial-payout fix). Parked until wanted; task in LAUNCH_TODO
  #14.
- **Disclosure rule:** gifted counts are commingled in public subscriber
  counts by design (marketing), but NEVER claim revenue/subscriber numbers
  in press or posts that lean on gifted counts — receipts brand.

## Human recruitment waves (sector-sequenced)

- **Wave 1 (Phase 1, weeks 1–4): generalists + Tech/momentum.** Biggest
  finfluencer supply (X/StockTwits swing traders). Source + DM templates:
  `TRADER_RECRUITMENT.md`. Founding Trader badge (100 cap) is the offer.
- **Wave 2 (Phase 2): dividend/value + options-adjacent swing traders.**
  r/dividends and fintwit value crowd — calm counterweight cohort; their
  audiences skew subscriber (demand side), not just creator.
- **Wave 3 (post-spike): sector specialists.** Energy/uranium X niche,
  biotech catalyst traders, REIT/rates accounts — recruited AGAINST the
  same-sector bot's public record (rule 2's race framing).

Cross-refs: recruitment mechanics + tracker `TRADER_RECRUITMENT.md` ·
phase gates §Trigger-Based Sequencing above · bot tooling
`bot_personas.py`/`bot_agent.py` · weekly KPI check includes
bots-vs-humans ratio (rule 4).

---

# Premium social memberships — VERDICT (researched Session 42b, 2026-08-21)

_Question: which paid platform subscriptions are worth it for OUR strategy
(founder-led X cadence + trader DM outreach + TikTok/IG video + press)?
Researched against 2026 pricing/limits + third-party reach data._

## BUY NOW (before cadence starts Tue 8/26)

- **X Premium, $8/mo, on the FOUNDER'S account (the one posting + DMing).**
  This is the one clear buy — X is our primary channel and every leg of
  the strategy runs through it:
  - **DM throughput (the trader hunt):** measured safe send rate is
    ~30 DMs/day verified vs **~7/day unverified** before the spam
    classifier throttles. Our 3-DMs/day plan is safe either way, but
    unverified leaves zero headroom for replies (replies COUNT against
    the cap) and DM-heavy weeks.
  - **Cold-DM credibility:** checkmark = "real business" signal on
    exactly the message type we're sending (stranger outreach with a
    money pitch). Marginal but it's the margin that matters.
  - **Reach:** X's published ranking code gives paid accounts ~4×
    in-network / ~2× out-of-network boosts; Buffer's 18.8M-post analysis
    (71k accounts) measured ~10× median reach vs free — median FREE
    account engagement is now literally 0. Founder cadence without
    Premium is posting into a void.
  - Unverified posting caps (50 posts + 200 replies/day, May 2026
    change) won't bind at our volume — reach + DMs are the reasons.

## BUY LATER (trigger-based)

- **X Premium+, $40/mo — upgrade ONLY for the spike window (~Oct 20 →
  launch+2wks).** Data shows Premium+ often ~2× standard-Premium reach
  (highest reply prioritization) — worth $40/mo precisely when reach
  peaks in value (press pitches out, launch week, $2-bill stunt).
  Downgrade after if metrics don't hold. NOT worth it at
  zero-follower stage — the multiplier needs a base to multiply.
- **X Premium on the @ApesTogetherApp brand handle** — only once the
  brand account posts on its own cadence (post-spike). Founder-led
  content outperforms brand accounts at our stage; don't pay twice.
- **Meta Verified (IG), ~$15/mo — trigger: impersonation.** Reach
  benefit was REMOVED from later creator rollouts (Meta's own docs);
  real value = human support + impersonator takedowns. Fintech clone
  scams are a matter of WHEN, not if, post-traction — buy the day the
  first fake "ApesTogether" IG appears, or at Phase 3 if IG becomes a
  real channel. Not before.

## DON'T BUY

- **X Verified Organizations ($1k/mo):** enterprise product; zero
  incremental value over founder Premium at our stage.
- **LinkedIn Premium ($40–70/mo):** LinkedIn confirms NO algorithmic
  reach benefit from Premium; our trader ICP lives on X/StockTwits/Reddit,
  not LinkedIn; journalists get pitched by email. Nothing to buy.
- **LinkedIn Sales Navigator ($99+/mo):** prospecting filters for an ICP
  we don't hunt on LinkedIn. No.
- **Reddit Premium:** ad-free + cosmetics only — no reach, no outreach
  value. Reddit cred comes from account history + honest posts, not paid.
- **StockTwits paid plans:** consumer DATA subscriptions (for reading,
  not reaching). Rooms/follows/DMs need no subscription. No.
- **TikTok:** no relevant paid subscription exists for creators/brands.

**Net: $8/mo now → ~$48/mo for one month around the spike → back to $8–16.**
Rule reminder: none of this changes the content rules — no paid reviews,
no undisclosed paid posts, FTC #ad on anything sponsored.

---

# Prizes & performance bonuses — RESEARCH VERDICT (Session 43, 2026-08-22; ✅ DECIDED — USER concurred same session)

**Question:** cash prizes for beating the S&P? Bonus payments for hitting
subscriber counts?

**Competitor landscape (researched):**
- **Dub:** pays creators ROYALTIES (licensing/rev-share, individually
  negotiated) — no performance prizes. Premium creators are diligence-vetted.
- **eToro:** Popular/Pro Investor program pays **1.5% of assets-under-copy**
  (rev share) with tier gates (min equity, min copiers, risk score <7 —
  note: they CAP allowed risk to qualify, the opposite of prize-chasing).
  Their trading competitions ($2.5k/$1k/$500) are one-off MARKETING EVENTS
  on virtual accounts, never the creator-comp engine.
- **Pattern:** nobody structures core creator pay as performance prizes.
  Prizes appear only as acquisition campaigns.

**Legal (the hard stop):**
- **SEC v. Forcerank:** fantasy-stock app with entry fees + cash payouts
  tied to stock performance = illegal **security-based swaps** (Dodd-Frank).
  $50k fine, shut down. "It's skill-based" was not a defense. ⇒ NEVER
  charge entry + pay on securities performance.
- Free-entry skill contests are generally lawful (no consideration = no
  lottery), but state patchwork applies (AZ/MD/CO/ND restrictions, NY/FL
  bonding >$5k, fixed prizes independent of entrant count, published rules,
  1099s for $600+). A one-off free contest is doable WITH attorney review.
- Sub-count bonuses = ordinary commercial incentive (like TikTok creator
  funds) — legal, no contest law implications.

**Product/messaging analysis:**
- Performance prizes select for VARIANCE, not skill — the known failure
  mode of trading competitions (winner = biggest YOLO, not best strategy).
  That directly degrades what subscribers pay for ("professional-level
  strategies") and what the moat is (credible 30-day+ track records).
- The leaderboard ALREADY pays for beating the S&P: rank → subs → 85% rev
  share. A prize duplicates that loop and converts positive-sum ("every
  ape who beats the market wins") into zero-sum PvP — the exact
  "apes together" damage the USER flagged.
- We ALREADY have a cash supply-side lever: **gifted bonus subscribers**
  (`AdminSubscription.bonus_subscriber_count` pays $6.50/sub from company
  funds) — quieter and steerable, no contest framing.

**DECISION (USER, Session 43):**
1. **NO standing cash prizes for beating the S&P.** (Legal risk + variance
   incentive + undermines rev-share purity.)
2. **NO sub-count cash bonuses at launch** — rev share already pays per
   sub; use gifted bonus subs case-by-case in recruitment offers instead.
3. **YES to STATUS rewards — ON THE POST-LAUNCH TODO** (Dec row of the
   EXECUTION_PLAN day-by-day): research best-in-class reward badges, then
   build — "Market Beater" (beat SPY N consecutive months; Founding
   Trader chip infra is the template), Ape of the Month featured
   placement, leaderboard seasons. Status = competition; money = rev share.
4. **📌 PARKED, NOT ON THE AGENDA — revisit ONLY if growth stalls:**
   one-off free-entry launch competition (small fixed prizes,
   attorney-reviewed rules, eToro pattern). Logged so it isn't forgotten;
   explicitly NOT planned. Trigger to revisit: Phase 1/2 exit criteria
   slipping badly despite cadence + recruitment being executed. Attorney
   sign-off is a precondition, never optional.

---

# Founder ride-along / build-in-public — VERDICT (Session 43; ✅ APPROVED — see DECISIONS at end of section)

**Research says (68-app + 20-founder cohort data, 2026):** build-in-public
works as a TRUST AMPLIFIER, not a traffic channel; every >$1M app pairing
it ran a second channel. It converts when (a) the audience contains your
buyers, (b) there's a conversion funnel, (c) 6–24 months of consistency.
Failure posts outperform wins; specificity beats journey-narration; links
go in the first reply; 2026 audiences discount MRR-screenshot theater.

**Fit for us: STRONG, with one reframe.** Don't "post as though still
building" — we ARE still building (Build 51, referral surfaces, Settings
v1.1, **the Trader API**) and the David-vs-Goliath frame is literally
true (solo founder vs Dub's $30M raise — already in LAUNCH_PLAYBOOK's
competitor table). No pretense needed; pretense is also the thing 2026
audiences have learned to smell.

**The killer variant — TRADE-along, not just build-along:** founder runs
his own portfolio ON the app as creator #1 and posts the verified chart.
"I built an app where anyone can prove they beat Wall Street. Watch me
try in public." That's simultaneously product demo, proof-of-concept,
content engine (every trade = a post), and the aspirational pitch
(anyone can do this) — and it's the content ONLY we can generate.
Disclose founder status on the leaderboard profile; founder account is
company-owned so it takes NO payouts (`is_company_owned` already
handles this) and should be excluded from Founding Trader + any prizes.

**Execution:** this is NOT a new workstream — it's the CONTENT of the
existing 3-posts/wk cadence (X-01 pinned thread already frames it).
Weekly rhythm: 1 build update (what shipped, incl. API progress —
dev-audience catnip), 1 trade/portfolio update (the ride-along), 1
leaderboard/AI-vs-human beat. Losses get posted — that's the credibility
engine and it's also exactly our "verified, warts and all" product value.

**DECISIONS (Session 43):**
- **Timing: starts NOW, not at "launch."** The Nov spike is the launch
  chapter of a story that needs 10 weeks of receipts behind it — warm
  audience research says pre-launch priming is where the value is, and
  the founder's own verified chart needs HISTORY to be content (a 30-day
  chart requires 30 days). Founder trading starts Mon 8/24; #RIDE-TRADE-01
  posts Tue 8/25 with the pinned X-01 thread. (Dates corrected Session 43b —
  8/22 is a Saturday.)
- **X account: @BrooklynDad85** (existing, aged) — age beats a fresh
  handle for DM deliverability + spam-classifier trust, and the everyman
  handle IS the David-vs-Goliath brand. Refresh bio (founder of
  @ApesTogetherApp + "trading my own app in public" + disclosure), pin
  X-01, buy Premium on THIS account (Sat 8/23 item).
- **Reddit added as 4th channel** using the founder's real 8y/5.8k-karma
  account (proof-of-human history). Playbook + templates:
  LAUNCH_CONTENT §REDDIT (account strategy note + R-04 ride-along).
- **TERMINOLOGY (Session 43b, USER question "isn't Publish the launch?"):**
  NO. **Publish = early access opens** (quiet availability; public term:
  "early access" — feeds the Founding-Trader-first-100 scarcity mechanic and
  sets bug expectations; "beta" only in dev-flavored #RIDE-BUILD posts).
  **"Launch" = the Nov 10–19 announcement moment.** The build-in-public
  research's "3–6 months before launch" founders had INSTALLABLE products
  during that window — followers→users→receipts is the conversion chain and
  every link needs availability. X-01/X-03 "live now" → early-access
  language (LAUNCH_CONTENT).
- **CROWN JEWEL — EXTERNAL NON-DIFFERENTIATION (Session 43c, USER +
  attorney consulted):** bot-vs-human is tracked INTERNALLY ONLY
  (accounting / no-payout / `is_company_owned`). Externally NEVER
  differentiated — no tags, no per-account AI claims. Engineered in:
  `_founding_trader_house_pill()` (rankless gold pill so badges can't out
  house accounts). Attorney verdict: paper-trading platform — no legal
  issue with opacity. All prior "disclosed AI / name tags" copy was
  Cascade's error (Session-42 house-pill misread) and is purged: X-01 ¶2,
  X-LAUNCH, RIDE-TRADE, RIDE-API + content-header rule added. Wolff+Grok:
  in-place fresh-start reset at Publish — LAUNCH_TODO #16.
- **All post language Cascade-generated** under LAUNCH_CONTENT §VOICE
  GUARDRAILS (no Claudisms list); weekly trade posts drafted from real
  numbers the USER pastes — results can't be pre-written.
- Founder account: company-owned (no payouts), founder status disclosed,
  excluded from Founding Trader + any future rewards.

---

# Trader API in social language — GAP FOUND (Session 43)

Audit result: the Trader API (UC-A) appears ONLY in eng docs
(`TRADER_API_SCOPING.md`, LAUNCH_TODO §2/§11, EXECUTION_PLAN Dec row).
**ZERO mentions in LAUNCH_CONTENT, LAUNCH_OUTREACH, or the content
calendar.** USER is right — for the AI-trading audience the API promise
is a hook nobody else in copy-trading has: "your algo can compete on a
public leaderboard against humans AND frontier AI models."

**✅ EXECUTED (Session 43, USER approved "make it so"):** ① X-01 pinned
thread now carries the API line (tweet 2) ② #RIDE-API monthly progress
post template added (LAUNCH_CONTENT §RIDE-ALONG) ③ #X-03 re-anchored +
API roadmap line ④ r/algotrading stays the Phase 3 dev-audience play
(R-02). **Standing rules:** promise direction, never dates (UC-A is a
Dec decision); interested replies → waitlist tagged as the API segment;
UC-D (real-brokerage mirroring) is NEVER promised publicly —
compliance-gated.
