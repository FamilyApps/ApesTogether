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
- [ ] GEO comparison page ("ApesTogether vs Dub vs eToro") — awaiting USER
  approval (gap plan list).
- [ ] Press-kit skeleton — awaiting approval.

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
| D7 retention ≥ 30% | store analytics |
| 5–10 usable testimonials | #E-TESTIMONIAL replies |
| Press kit complete | §2.3 |
| App Preview video live on both listings | §2.4 |
| Founding counter ≥ ~20 claimed | admin |
| v8 compliance build shipped (if past Aug) | LAUNCH_TODO |

## 2.2 Testimonials

Send #E-TESTIMONIAL (`LAUNCH_CONTENT.md`) to every active user at ~day
14 of their usage. Ask permission to quote with first name/handle. Park
quotes in the press kit.

## 2.3 Press kit (Cascade drafts, USER assembles, ~1 week)

One shared folder (Drive) + one page on the site (`/press`): 6 store
screenshots (have) · app icon + logo SVG (have) · founder bio + photo ·
one-pager PDF (Cascade drafts: what/why/traction/AI-vs-human hook) ·
3–5 data points (traders, trades logged, AI-vs-human standings) ·
testimonial quotes · FAQ. The WSJ angle sheet comes from
`LAUNCH_OUTREACH.md` §Story Angles.

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

## 3.0 T-minus-14 days
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

# DAY-BY-DAY — next two weeks (start 2026-07-23)

_Assumes Play verdict lands within ~a week; slide the dependent rows if
it doesn't. ENG = engineering box from LAUNCH_TODO; MKT = this plan._

| Day | Items |
|---|---|
| **Wed 7/23** | ENG: Play Billing E2E on Pixel (LAUNCH_TODO steps 1–2: monthly-with-trial, annual-slot-B-no-trial, backend rows, cancel) · ENG: sideload debug build — verify founder pill, CTA flip, NEW review prompt on 3rd trade · MKT: review Cascade's 7 gap plans (chat) + approve/reject. |
| **Thu 7/24** | MKT §0.1: register ALL social handles (one sitting, ~2h) · ENG: create `reviewer@apestogether.ai` demo account (§0.3.1). |
| **Fri 7/25** | ENG §0.3: ASC checks (Slot-A intro offer, resizer on SE sim) → **submit Build 47 for App Store review** · ENG: test `notifications@` deliverability (headers check). |
| **Sat 7/26** | MKT: fill `TRADER_RECRUITMENT.md` tracker — 25 named candidates (USER browses with Cascade's sourcing queries; ~90 min). |
| **Sun 7/27** | Rest. Optional: first founder X post (intro thread #X-01, revised version). |
| **Mon 7/28** | MKT: founder cadence starts — X post #1 · ENG: Play verdict watch (daily from here). Attorney answered? → send §5.2(a) before/after. |
| **Tue 7/29** | MKT: 3 trader DMs (start of daily rhythm) · ENG: if verdict in → §1.1 promote v6 (staged 20%). |
| **Wed 7/30** | MKT: X post #2 + 3 DMs · ENG: v7 AAB build → Internal smoke (needs v6 promoted first). |
| **Thu 7/31** | MKT: TikTok #1 (+ IG/YT cross-post) + 3 DMs · ENG: v6 rollout 20%→100% if vitals clean; v7 → Production. |
| **Fri 8/1** | MKT: X post #3 + 3 DMs + weekly metrics note in LAUNCH_TODO · ENG: waitlist email #1 send (§1.2) once both stores live. |
| **Sat–Sun 8/2–3** | Light: reply to everything; plan week's 3 posts. |
| **Week of 8/4** | Phase 1 rhythm (3 posts + 5×3 DMs + Friday metrics) · ENG: **v8 compliance build session** (targetSdk 36 + Billing 8 — book a full day; deadline 8/31) · Apple verdict watch → iOS live quietly. |
| **Week of 8/11** | Phase 1 rhythm · first #E-TESTIMONIAL sends (day-14 users) · v8 to Internal → Production. |

Then: Phase 1 rhythm until its exit criteria, Phase 2 gates review every
Friday, and the Phase 3 date gets picked only when §2.1 is all green.
