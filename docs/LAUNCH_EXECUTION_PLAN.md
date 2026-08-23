# Launch Execution Plan — Phases 0–4, Click-by-Click

_Created Session 33 (2026-07-22). Operationalizes `MARKETING_PLAN.md`
§"Full-Plan Review & Trigger-Based Sequencing". This is the doc you open
every morning. Content to post lives in `LAUNCH_CONTENT.md`; DMs/pitches in
`LAUNCH_OUTREACH.md`; trader pipeline in `TRADER_RECRUITMENT.md`; engineering
state in `LAUNCH_TODO.md`._

**Governing rules (from the adopted verdicts):**
- Store availability ≠ launch moment. The public spike fires ONCE, gated.
- Never: paid reviews, botted engagement, fabricated numbers.
- Founder-voiced > brand-voiced. Sustainable cadence > heroic cadence.

---

# PHASE 0 — Infrastructure (NOW → both store approvals)

## 0.1 Register social handles (USER, ~2h, one sitting)

Do these in one evening. Use `bob@laborofloveapp.com` (or the
apestogether.ai alias) + a password manager entry per account.

1. **X:** x.com → Sign up → handle `@ApesTogetherApp` (fallbacks:
   `@ApesTogetherHQ`, `@apestogether_ai`). Bio:
   `Verified trading strategies. Every trade tracked. 85% to traders. Zero hype. apestogether.ai`
   Link: `https://apestogether.ai?utm_source=x&utm_medium=bio`.
   Upload the 512×512 icon as avatar.
2. **TikTok:** tiktok.com/signup → username `apestogether`. Bio:
   `Follow verified traders. Not TikToks.` Link (needs 1k followers for
   bio link — put it in the profile website field when unlocked; until
   then keep it in video captions): `apestogether.ai?utm_source=tiktok&utm_medium=bio`.
3. **Instagram:** instagram.com → username `apestogether` (fallback
   `apestogether.app`). Bio: `Creator economy meets Wall Street.` +
   UTM link. Set to Business account (Settings → Account type) for
   analytics.
4. **YouTube:** youtube.com → Create channel "ApesTogether" (for Shorts
   cross-posts). Handle `@apestogether`.
5. **LinkedIn:** no new page needed yet — update YOUR headline to
   `Building ApesTogether — verified trading strategies | NYC` (founder-led
   beats brand page).
6. **Reddit:** use your existing aged account (do NOT create a fresh one —
   fresh accounts get filtered). Join: r/wallstreetbets, r/stocks,
   r/investing, r/algotrading, r/smallstreetbets, r/startups,
   r/SideProject. **No app mentions for 2+ weeks** — comment genuinely so
   the account has recent non-promo history.
7. Record every handle + password in the password manager; add the
   handles to the site footer if any differ from what's linked there.

## 0.2 Engineering boxes (already in flight — tracked in LAUNCH_TODO)

- [ ] Play Billing E2E on the Pixel (money test #4) — steps in
  LAUNCH_TODO §Next Session.
- [ ] v7 on-device verify (founder pill + dynamic CTA + NEW: review prompt).
- [ ] iOS Build 47: ASC checks → submit for review (§0.3).
- [ ] Play verdict → promote v6 (§1.1).
- [ ] `notifications@apestogether.ai` Gmail-spam bug (open since May 27) —
  matters before ANY waitlist email goes out; test + fix SPF/DKIM/DMARC
  alignment first (send test to a personal Gmail; check "show original"
  headers for `dkim=pass` `spf=pass` `dmarc=pass`).
- [ ] Android v8 compliance build (targetSdk 36, Billing 8, NDK symbols)
  — HARD deadline Aug 31.

## 0.3 iOS Build 47 → App Store review (USER on Mac + web)

1. **Reviewer demo account first** (Apple rejects without it): in the
   PROD app or web, create `reviewer@apestogether.ai` (Google sign-in on
   a Workspace alias, or Apple sign-in), make 2–3 sample trades, follow/
   subscribe to at least one trader (gift it via admin if needed so the
   reviewer sees the subscriber experience).
2. appstoreconnect.apple.com → My Apps → ApesTogether → **check the
   Slot-A subscription group** (Monetization → Subscriptions): the
   original group's monthly + annual must each show the 7-day
   introductory offer, state "Approved"/"Ready to Submit". Slot B+
   groups: NO intro offers (by design).
3. App page → the 1.0 version → select **Build 47** → App Review
   Information: reviewer credentials + note:
   `Sign in with the provided Google account. All trading is virtual/paper — no real money. Subscriptions use sandbox.`
4. Verify the resizer bullet renders un-wrapped: run Build 47 on the Mac
   simulator (iPhone SE = narrowest) → any locked portfolio → check
   "Adjust the portfolio size instantly" fits on one line; if it wraps,
   accept or ping Cascade to shorten.
5. **Submit for Review.** In-app purchases: attach the Slot-A monthly +
   annual (+ any slot products ASC requires) to the submission when
   prompted.

## 0.4 Cascade deliverables (this session unless noted)

- [x] Android Play In-App Review prompt (post-3rd-trade, mirrors iOS) — DONE, rides v7.
- [x] Trader-recruitment pipeline doc → `TRADER_RECRUITMENT.md`.
- [x] Waitlist nurture email #1 → `LAUNCH_CONTENT.md` #E-BUILDLOG-01.
- [x] GEO comparison page — DONE 7/22, live at `/compare` (+ footer link).
- [x] Press-kit skeleton — DONE 7/23: public `/press` page (boilerplate,
  angles, fact-check FAQ, brand colors) + `docs/PRESS_KIT.md` assembly guide
  (one-pager draft, screenshot shot-list, Gemini prompts). USER assembly
  items in PRESS_KIT.md §1–§5.
- [x] Acquisition survey (gap #7) — DONE 7/22: backend + Android (rides v7) +
  iOS (rides Build 48).

**PHASE 0 EXIT:** handles registered · Build 47 submitted · billing E2E
passed · email deliverability verified.

---

# PHASE 1 — Quiet availability + supply hunt (approval → ~4 weeks)

## 1.1 Promote v6 to Production (USER, the day the Play verdict lands)

1. play.google.com/console → ApesTogether → Test and release → **Closed
   testing** → your track → the approved v6 release → **Promote release
   → Production**.
2. Review the release notes (keep the existing ones) → **Start rollout to
   Production** → confirm. Choose **staged rollout 20%** → bump to 100%
   after 48h crash-free (Play Console → Quality → Android vitals).
3. Do NOT post anywhere. The only announcement is §1.2.
4. Same week: build + upload **v7** (Internal → smoke → Production) per
   LAUNCH_TODO §PENDING BUILDS.

## 1.2 Waitlist email #1 (USER, after both stores are live)

1. Fix/verify the deliverability bug first (§0.2).
2. Export the waitlist: the `BetaWaitlist` table (ask Cascade for a CSV
   dump script) → send #E-BUILDLOG-01 (`LAUNCH_CONTENT.md`) via Gmail
   mail-merge (Workspace: Gmail → compose → "multi-send" mode) from
   `bob@apestogether.ai`. BCC yourself. Under ~500 recipients/day keeps
   Workspace limits happy.
3. Trader-segment signups get the #E-BUILDLOG-01-TRADER variant (same
   doc) — it leads with the Founding Trader clock.

## 1.3 Trader recruitment — THE Phase 1 job (USER 30–45 min/day)

Full playbook: `TRADER_RECRUITMENT.md`. Rhythm: **3 personal DMs/day,
every weekday.** Track every contact in the doc's table. Target: 25
committed traders by end of Phase 1. White-glove each yes: personal
onboarding, first-trade walk-through, founding-badge confirmation.

## 1.4 Founder posting cadence (USER, ~3h/week total)

- **X: 3 posts/week** (Mon/Wed/Fri, ~9am ET). Source from
  `LAUNCH_CONTENT.md` X library — treat it as a menu, adapt freely;
  the build-in-public + anti-finfluencer angles age best.
- **TikTok: 1/week** (+ cross-post to IG Reels/YT Shorts — same file,
  captions in the TT scripts).
- **Reddit: comments only** — genuinely useful replies in the joined
  subs; zero app mentions until Phase 3 (the account must not look like
  it exists to promote).
- Reply to every reply. Skip a day rather than post filler.

## 1.5 In-app metrics watch (weekly, Fridays)

Play Console → Android vitals (crash-free) · ASC → Analytics · backend
admin: signups, traders with ≥1 trade, D7 retention, review-prompt
ratings appearing. Log a one-line status in LAUNCH_TODO each Friday.

**PHASE 1 EXIT:** both stores live + v7 shipped · ≥10 committed traders
actively trading · first testimonials requested · cadence holding 3 weeks
straight.

---

# PHASE 2 — Proof accumulation (~4–10 weeks after quiet launch)

## 2.1 Exit gates (ALL must pass before Phase 3 gets a date)

| Gate | Where to check |
|---|---|
| Crash-free ≥ 99.5% over 14 days, both platforms | Play vitals / Xcode Organizer |
| ≥ 20 human traders with ≥ 5 trades | admin dashboard |
| ≥ 10 traders with ≥ 30-day history | leaderboard 1M view |
| D7 retention ≥ 20% (finance-category top quartile; benchmarks: category avg ≈17–18%, cross-app median ≈11–13% — 30% was nearly 2× category norm; keep 30% as stretch, not gate) | store analytics |
| 5–10 usable testimonials | #E-TESTIMONIAL replies |
| Press kit complete | §2.3 |
| App Preview video live on both listings | §2.4 |
| Founding counter ≥ ~20 claimed | admin |
| v8 compliance build shipped (if past Aug) | LAUNCH_TODO |

## 2.2 Testimonials

Send #E-TESTIMONIAL (`LAUNCH_CONTENT.md`) to every active user at ~day
14 of their usage. Ask permission to quote with first name/handle. Park
quotes in the press kit.

## 2.3 Press kit (Cascade drafted 7/23 — USER assembles)

**Done:** `/press` page live · one-pager text drafted · shot-list + Gemini
prompts ready — all in `docs/PRESS_KIT.md`. **USER (per PRESS_KIT.md):**
Drive folder · 6 real screenshots (capture during on-device sessions) ·
banner via Gemini · founder bio + real headshot · `press@apestogether.ai`
alias · metrics fill at Phase-2 exit · swap Drive link into `/press`.
The WSJ angle sheet comes from `LAUNCH_OUTREACH.md` §Story Angles.

## 2.4 App Preview video (~$500 budget or DIY)

30s screen-capture: leaderboard scroll → tap trader → subscribe →
real-time alert arrives → portfolio resize. iOS: record on-device sim
per Apple spec (1080×1920); Android: same cut works. Captions burned in
(most viewers on mute). Upload: ASC → App Previews; Play Console →
Store listing → video (YouTube link).

## 2.5 Paid-ads dry run (small, optional, $100–200)

Apple Search Ads BASIC → $5/day cap → keywords: `copy trading`, `social
trading`, `follow traders`, `dub`, `etoro alternative` — collect CPI
data only, then pause; informs Phase 3/4 budgets.

**PHASE 2 EXIT = every 2.1 gate green.** Then, and only then, pick the
Phase 3 date 2–3 weeks out (avoid earnings-season Fridays; Tue–Thu best).

---

# PHASE 3 — The one-shot public launch (1 week, date-locked)

_Research note (7/23): tier-1 exclusives need 2–3 weeks lead — treat the
campaign as starting T-21, not T-14 (WSJ ask goes out at T-21 with a
"claim by [date] or we go wide" window). OPTIONAL, needs USER call: Apple
featuring nominations can be filed as "App Launch" type 6–8 weeks pre-date
(3-week documented floor) — the approved gap plan #11 keeps featuring
post-spike, but filing at T-45 costs nothing and could align featuring with
launch week. Decide when the date is picked._

## 3.0 T-minus-21 to T-minus-14 days
- WSJ exclusive offer (your prior-coverage reporter first) —
  `LAUNCH_OUTREACH.md` WSJ pitch + press kit + embargo date. If no reply
  in 5 business days → follow-up; if dead by T-7 → release the exclusive
  to Tier-2 (Axios/Fast Company/TechCrunch consumer) as "first look".
- Confirm $2-bill stunt logistics (bills ordered, QR stickers printed,
  Midtown route from `LAUNCH_CONTENT.md` §Stunt).
- Queue launch-week content (all #-LAUNCH pieces, dates filled).

## 3.1 T-minus-7
- Tier 2/3 journalist emails with embargo (`LAUNCH_OUTREACH.md`).
- Influencer wave: every warm contact from Phase 1/2 gets the beta-
  invitation message + press kit; offer affiliate/referral comp.
- Waitlist email: "One week." (adapt #E-PRELAUNCH).

## 3.2 Launch day (Tue–Thu)
- 7:00am ET: X launch thread (pin) · TikTok · LinkedIn · IG · waitlist
  blast #E-LAUNCH.
- 8:00am: Reddit — r/wallstreetbets #R-LAUNCH (positions-or-ban energy,
  receipts angle), r/stocks #R-LAUNCH-2; 9:00am r/startups #R-LAUNCH-3.
  Reply to EVERY comment all day; never defensive.
- Stunt day = launch day or day-2, 11:30–1:30 Midtown; film everything.
- Apple Search Ads ON at the committed budget tier (MARKETING_PLAN
  §Budget tiers).
- Product Hunt: ONLY if a credentialed hunter volunteered — otherwise skip
  (deprioritized verdict).
- Monitor Vercel + Sentry/vitals; hotfix > marketing if anything breaks.

## 3.3 Launch week days 2–7
- Press follow-ups with day-1 numbers · influencer reposts · daily X
  updates ("Day 2: N traders, the AI is beating N% of humans…") ·
  in-app review prompts doing their work · respond to every store review.

---

# PHASE 4 — Post-spike engine (ongoing)

- **Weekly:** leaderboard content beat — every Friday, founder X post +
  monthly TikTok: "Humans vs AI, week N standings." The leaderboard IS
  the content machine.
- **ASA scale:** raise budget on keywords with CPI under target; add
  Play App Campaigns if CPI validates.
- **Affiliate program:** micro-influencers get referral links tied to
  the in-app referral system; performance comp only. FTC #ad required.
- **Store featuring:** ASC → "Promote Your App" featuring nomination
  (developer.apple.com/app-store/featuring-nominations) once
  post-launch metrics look good; Play editorial via Console banner when
  offered.
- **GEO/SEO:** comparison page iterations; answer "app to follow
  verified traders"-shaped questions on Reddit/Quora (honestly, as
  founder).
- **Quarterly:** "Q(N) results: AI vs humans" — the recurring press hook
  nobody else can run.
- **KPI review:** monthly against the playbook §9 table, owner: USER,
  first Friday of the month.

---

# DAY-BY-DAY — from publish day (rewritten 2026-08-21; supersedes the 7/23 calendar)

_State at rewrite: Android v13 APPROVED, awaiting USER's Publish click
(managed publishing). iOS Build 50 resubmitted 8/21 after the 2.1a
server-side fix. `/get-app` CTA redirect deployed. ENG = LAUNCH_TODO;
MKT = this plan; SECTOR = MARKETING_PLAN §Unified Sector-Supply Plan._

| Day | Items |
|---|---|
| **Sat 8/22** _(weekday labels corrected Session 43b — 8/22 is a SATURDAY; tasks keep their day-of-week anchors)_ | ENG: verify SIWA on TestFlight (post-`db_retry`-deploy sanity) · **click "Publish 2 changes" in Play Console — quiet availability begins** · install from the real listing on the Pixel → sign-in + `adb shell pm get-app-links com.apestogether.app` (App Links autoVerify, ENG §0.6) · **day-1 real-card money test**: self-subscribe to a HUMAN creator, verify payout accrual row · pull bot sector distribution from admin dashboard → fill the SECTOR table. |
| **Sun 8/23** | MKT §0.1: register ALL social handles (one sitting, ~2h) → tell Cascade to restore the footer "Follow Us" links · **buy X Premium ($8/mo) on @BrooklynDad85** (the founder account — Session 43 decision; refresh bio + banner while you're in there) · optional: browse Cascade's sourcing queries and start filling `TRADER_RECRUITMENT.md` tracker · **ENG (Session 43c — USER: "why not today?" — correct: Sunday IS the cleanest window; market closed, intraday/close crons idle, zero AV contention): drift-heuristic patch deployed → run the full #11 repair sequence TODAY, URLs handed one at a time by Cascade.** Still needs a market day: founder's first trades, top-up bots' first trades, and confirming the stale-close-cron fix at Monday's 4pm close. |
| **Mon 8/24** | ENG (Cascade+USER): **market-data repair sequence (if not already run Sun 8/23) — PRE-MARKET, 8:00–9:15am ET** (fallback: after ~4:45pm once the market-close cron finishes; write steps — reconciles/snapshot rewrites/cache clears — must not race intraday crons, and AV backfills shouldn't share the per-minute budget with live collection). Order: Cascade deploys the drift-heuristic patch FIRST (LAUNCH_TODO #11 Round 3), then #11 list: coverage audit → dailybars backfill → AV fetch for XLE/NEE/JPM/HD… → re-run stock-value audit → root-cause stale-close cron → reconcile apex1575 + bobford00 → re-run drift audit → cache invalidations (chart1658 incl. — held from Sunday) · Cascade builds `/admin/reset-house-account` + public-payload numeric user-ID audit + join-date display & Founding-pill rank-render checks (#16) · bot top-up batch per the SECTOR table gaps + verify sector-rule binding for value archetype · **founder starts trading his own portfolio (creator #1) — the ride-along track-record clock starts today** · MKT: fill tracker to 25 named trader candidates (~90 min) · iOS verdict watch (daily from here). |
| **Tue 8/25** | MKT: founder cadence starts on @BrooklynDad85 — pin #X-01 (now carries the API line) + post #RIDE-TRADE-01 + first 3 trader DMs (daily rhythm) · Reddit warm-up begins (comments only, target subs per LAUNCH_CONTENT §REDDIT) · ENG: `notifications@` deliverability diagnosis (blocks waitlist email #1). |
| **Wed 8/26** | MKT: 3 DMs · ENG (Cascade): OG previews Tier 1+2 (`/og/<slug>.png`) — the share-link preview IS the ad. |
| **Thu 8/27** | MKT: TikTok #1 (+ IG/YT cross-post) + 3 DMs · ENG: if iOS approved → release Build 50, set `IOS_APP_STORE_ID` on Vercel (flips `/get-app` iOS routing), add Smart App Banner meta · **once both stores live: landing flip** (hero → "Early access is open" + store badges; waitlist demoted to secondary — LAUNCH_TODO #12). |
| **Fri 8/28** | MKT: X post #2 + 3 DMs + first weekly metrics note in LAUNCH_TODO (installs/signups/subs/traders + bots-vs-humans ratio) · ENG: waitlist email #1 (§1.2) once BOTH stores live + deliverability verified. |
| **Sat–Sun 8/29–30** | Light: reply to everything; plan week's 3 posts. NOTE: v13 already satisfied the Aug-31 targetSdk-36/Billing-8 deadline — nothing due. |
| **Week of 9/1** | Phase 1 rhythm (3 X + 1 TikTok + 5×3 DMs + Friday metrics; X rhythm = #RIDE-TRADE + #RIDE-BUILD + leaderboard beat) · first Reddit self-post: #R-03 r/SideProject (after ≥1 wk of comment warm-up) · ENG: remaining money E2E (Xero bill gen, W-9 hold/release, Android cancel-path) · Build 51 scope: terms footnote parity + referral surfaces + share-email spruce-up · Cascade: brand-spelling sweep + UGC scrub + disclaimers audit + landing refresh (screenshot/OG test/waitlist counter) · nudge attorney on ToS §5.2(a) (+ if the founder-written alt review is still wanted post-launch, raise 16 CFR Part 465 in the same conversation — LAUNCH_TODO #17) · **Wolff+Grok fresh-start reset: run `/admin/reset-house-account` for both (~1wk post-Publish so they read as early users — LAUNCH_TODO #16; execute AFTER hours)** · verify AV `no_calls` post-top-up + drift cron + cold-start ping · DMARC aggregate-report monitoring ON (`rua=` tag; the `p=reject` flip stays Dec — it needs weeks of reports). |
| **Week of 9/8** | Phase 1 rhythm · first #E-TESTIMONIAL sends (day-14 users) · #R-04 r/EntrepreneurRideAlong month-1 numbers post · human-arrival bot triggers per SECTOR rules as traders commit · USER 15-min security pass: Vercel log review + `CRON_SECRET` rotation · Firebase cleanup (audit who deleted the fingerprints, delete stray iOS Firebase app, resolve SHA-1 dup warning) · **Trader API UC-A build STARTS (pulled forward from Dec — Session 43c: #RIDE-BUILD/#RIDE-API need real shipped work, and it captures the algo waitlist pre-launch; invite-only keys until Dec hardening; D-1..D-6 per `TRADER_API_SCOPING.md`)** · CI quick wins (S-4 pip-audit + Dependabot — an afternoon). |
| **Mid-Sep (Phase 2 start)** | ENG: load-test `/api/mobile/feed` @100 concurrent (pre-spike gate) · Settings v1.1 screens (Payment History / Tax Info / FAQ — Build 52 + v14) · recapture 6 Play screenshots on the real Pixel · Cascade research write-up: external AI stock-picking model APIs (LAUNCH_TODO §2#3) · MKT: press kit assembly + App Preview video (optional) + In-App Events draft · reward-badge SCHEMA design (build stays Dec; doubles as a "vote on seasons" content beat) · UC-A build continues — first #RIDE-API post with real status. |
| **~Fri 10/3 (first monthly close)** | Verify Xero revenue post + payout sync · ghost/bonus-subscriber tracking vs month-end payouts · first real payout check-run email review. |
| **Mid-Oct (T-21)** | Press pitches out (LAUNCH_OUTREACH) · Apple featuring nomination (T-45 was late Sep — submit if metrics green) · consider X Premium+ upgrade for the spike window · KPI tracker stood up · **Oct 15: BOT FREEZE begins (→ ~Nov 21) — no new house bots; every launch-day bot needs ≥4 wks of chart (MARKETING_PLAN §Launch-window timing rule 8)**. |
| **Nov 10–19** | SPIKE (playbook launch week; $2-bill stunt; manual iOS release timed here if held). |
| **Dec (post-spike)** | Phase 4 engine · **UC-A public hardening + open key issuance** (build started wk 9/8; invite-only until here) → outbound trade-event feed UC-B after · UC-D stays compliance-gated (start legal review when UC-A opens) · **reward-badge BUILD + launch ("Market Beater" / Ape of the Month / seasons — schema designed mid-Sep; launch waits for a real user population, which now exists)** · CI hardening remainder (branch protection, SHA-pin Actions — pip-audit/Dependabot done wk 9/8) · SQLAlchemy consolidation + legacy OAuth shim removal + orphan-row delete (the two pure-risk refactors stay post-launch deliberately: no user-visible value, real regression surface) · DMARC → `p=reject` (monitoring since wk 9/1) · web FOUNDER chip + N/100 counter (at ~20+ claimed). |
| **Jan 2027** | 1099-NEC filing via Track1099 from Xero (decision logged Session 21; W-9s + 6010 bills already feed it). |

Then: Phase 1 rhythm until its exit criteria (≥10 committed traders),
Phase 2 gates review every Friday, and the Phase 3 date gets picked only
when §2.1 is all green. Phase-duration targets below still govern — the
Nov 10–19 ideal launch window holds if Phase 1 exits by ~early October.

_Dropped/moot (so they stop resurfacing): Play pre-registration + Apple
pre-order (moot — we publish 8/22 instead of pre-launching); Waitlist 2.0
+ invite gate (rejected, Session 26)._

---

# PHASE DURATION TARGETS — research-grounded (Session 34, 2026-07-23)

_Sources: YC pitch guide + founder-PR playbooks (tier-1 exclusive = 2–3 wks
lead, follow-up at +2–3 days, ~6 wks full PR cycle) · Apple featuring docs
(3-wk floor, 6–8 wks realistic for App Launch nominations) · 2025–26
retention benchmarks (finance D7 ≈17–18% category avg). Durations are
targets, not deadlines — gates still govern._

| Phase | Ideal duration | Calendar (if nothing slips) | What actually bounds it |
|---|---|---|---|
| **0 — Infrastructure** | 1–2 weeks | now → ~Aug 1 | Play verdict (out of our hands) + Build 47 submission + billing E2E + deliverability fix. USER effort: ~1 evening (handles) + 2 short console/Mac sessions. |
| **1 — Quiet + supply** | 4–6 weeks | ~Aug 1 → early/mid Sep | The ≥10-committed-traders gate: 15 DMs/wk × 10–20% yes-rate = 50–100 DMs ≈ 4–7 wks. Cadence-holding gate has a hard 3-wk floor. |
| **2 — Proof** | 6–10 weeks (plan on 8) | mid-Sep → early Nov | Hard clocks that can't compress: 30-day track records only start once traders are active; 14-day crash-free window; testimonials at day-14 of usage. App Preview video + kit assembly + optional featuring nomination (T-45) live inside this window. |
| **3 — Spike** | 4 weeks (T-21 → launch+7) | pitch ~mid-Oct → launch mid-Nov | Tier-1 exclusive lead time (2–3 wks) + launch week execution. |
| **4 — Engine** | ongoing; first 90 days structured | mid-Nov → | Weekly leaderboard beat, monthly KPI vs playbook §9, quarterly "AI vs humans" report (the recurring hook). |

**Ideal launch window: Tue–Thu, Nov 10–19, 2026** (post-Q3-earnings lull,
before Thanksgiving week 11/23–27). **Fallback: Dec 1–3.** Slips past that →
jump to mid-January; never launch Dec 10–Jan 5 (press dead zone). Total
runway from today: ~16–19 weeks — the calendar month of quiet operation
before the spike is a feature (track-record moat compounds), not a delay.
