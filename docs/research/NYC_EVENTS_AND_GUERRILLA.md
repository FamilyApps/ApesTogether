# NYC In-Person Channel — Events Research + Guerrilla Plan

**Date:** 2026-09-01 · **Status:** Research track C deliverable · **Integrates into:** `docs/MARKETING_PLAN.md` (IRL channel section) · playbook slots that said "research NYC fintech meetups" (`docs/LAUNCH_PLAYBOOK.md` days 3/11)
**Rule of the channel:** every physical touchpoint carries its own QR/short-link (see §4) or we learn nothing.

---

## 1. Event inventory (verified via web, 2026-09-01)

### Tier 1 — plan around these

| Event | When | Audience | Fit / action |
|---|---|---|---|
| **Stocktoberfest NYC (Stocktwits)** — stocktoberfest.stocktwits.com | **Oct 5–7, 2026** | Top traders, financial content creators, RIAs/retail analysts, fintech, public-co execs | **The one that matters — 5 weeks before Nov launch.** Exactly our supply side: traders with audiences who need monetization + receipts. Go with founder ride-along story, early-access invites, Founding Trader pitch. Cheaper 1-day Wednesday pass exists (City Winery programming). **VERIFY ticket price before buying** — Stocktwits events historically run $500+. |
| **QWAFAxNEW** — qwafaxnew.org | **Sep 5, 2026** ("The Science of Alpha: Quant Investing, AI & Market Insight"), Oct TBD (Petter Kolm, RL for trading, NYU) | NYC's premier quant society; MFE-program alliances (Columbia, NYU Courant/Tandon, CMU, Fordham, Stevens) | Professional quants + MFE students = UC-A creator API persona. RSVPs cap fast, members get preference — join as member (cheap). **Sep 5 is THIS FRIDAY** — decide today/tomorrow. |
| **NYC Algorithmic Trading (Meetup)** — meetup.com/nyc-algorithmic-trading | Monthly talks (recent ones online, Fri 7pm) | 5,229 members, practical algo focus ("automate purchase and sale using stats/ML") | The exact #X-03/#X-16 persona in one room. Attend 1–2, THEN pitch organizers a talk: "I built a paper-trading venue where algos earn subscription revenue — here's the architecture" (builder talk, not an ad). |
| **Day Traders of New York (Meetup)** | Friday nights, in person ("Live In Person Trading… Pizza served"), 134 W 29th St | Retail day traders, all levels | Demand side + creator supply. Low-stakes recurring room to test the pitch and wear the shirt (§3). |

### Tier 2 — opportunistic / recurring generic

| Event | When | Notes |
|---|---|---|
| NYC Finance, Investment & Wealth Mgmt Networking Night (Meetup) | Sep 9, 2026, 6pm; recurs ~monthly | Generic finance networking; RIAs + fintech operators. Cheap reps for the 30-second pitch. |
| NY Trading, Finance & Banking Networking Affair (Eventbrite-gated) | Recurring | Wall Street professional crowd; lower fit, near-zero cost. |
| AI in Finance & Algo Trading (Meetup) | Stale — last event 2022 | Skip; listed so we don't re-research it. |

### Tier 3 — missed this cycle, calendar for 2027

| Event | 2026 date (passed) | Why it hurts / 2027 action |
|---|---|---|
| **WOLF Summit NYC** — summit.wolf.financial | Aug 3, 2026 | ~200 traders/fintech builders/finance creators, **co-hosted by Public.com** (our copy-trading source broker — awkward-adjacent but also warm). Watch for their off-cycle events; book 2027 early. |
| Modern Investor Summit NYC (Finimize) | May 19, 2026 | 200–250 engaged retail investors; had an entire "How Retail Investors Are Using AI" session — our thesis on a stage. Book 2027; pitch a speaker slot once we have traction numbers. |
| NY Fintech Week / Empire Fintech | April (annual) | Industry/VC-heavy; useful when we want partnerships or press, not users. 2027. |

### University channel (no dates — always on)
QWAFAxNEW's partner MFE programs + NYU/Columbia undergrad quant/fintech clubs. The #X-16 "CS student with a strategy" persona lives here, and clubs are starved for real speakers. One email per club offering a "how to get paid for a track record without AUM" talk. Best window: September (club fair season) — i.e., now.

---

## 2. What to actually do at events (the founder script)

- **The pitch is the product's weirdness:** "It's a leaderboard where the receipts are real and followers pay you — bots welcome. My AI bots are currently beating me." Lead with the bot-vs-human angle; it starts arguments, arguments start signups.
- **Never sell from the audience mic.** Q&A self-promotion is the fastest way to get blacklisted by meetup organizers. Talk to people at the pizza table; give the organizer a straight offer to present a real technical talk later.
- **Carry:** phone with the app installed (demo = leaderboard scroll, 10 seconds), business cards with the event-specific QR (§4), shirt on body (§3).
- **Collect, don't broadcast:** the win condition per event is 5 real conversations + 2 X/phone contacts, not 50 flyers.
- **Claim discipline applies in person** (same as `LAUNCH_CONTENT.md` owner notes): API/options/prediction markets are "on the roadmap," bots are "company accounts, clearly labeled," never present paper returns as real-money returns.

---

## 3. Guerrilla layer — shirts + Money Bike

### Shirts
- **Design directive:** the receipt motif. Front: small logo. Back: an actual-format trade receipt ("SELL 2.52605 SGOV @ $100.40 — verified 15:39:00") with headline **"SHOW ME YOUR RECEIPTS"** + QR. A conversation object, not a billboard.
- **Second design (bot angle):** "MY AI IS BEATING ME — apestogether.ai" — pairs with the founder ride-along story.
- **Cost:** Printful/Custom Ink ~$15–25/shirt small-batch. Order ≤10 first run (founder + gifts to first NYC creators met at events). Gift shirts ONLY to people who've signed up — a shirt on a real trader at the next meetup is the whole play.
- **Timing:** in hand before Stocktoberfest (order by ~Sep 20).

### Money Bike
- **Concept:** the themed bike as a rolling billboard through Manhattan. Add a rear/frame sign: logo + "The leaderboard where receipts are real" + giant QR (short-link `/bike`, §4). QR must be legible at a stoplight: ≥8" square, high contrast.
- **Routes/times:** Financial District (Bowling Green/Charging Bull tourist+finance mix), Union Square, NYU/Columbia campuses in September, outside Stocktoberfest venues Oct 5–7 (public street — free counter-programming). Weekday lunch + weekend afternoons.
- **Legal sanity:** riding a decorated personal bike with a sign = fine; don't obstruct sidewalks, don't lean-and-leave it as unattended signage (that can be treated as posting/obstruction), no handing out flyers into traffic. It's your bike with a sign, not a permitted ad structure — keep it that way.
- **Expectations:** this is a story generator more than a funnel — film it for #TT/#X content ("I marketed my fintech app from a bicycle"). The content about the bike will out-reach the bike.

---

## 4. Measurement — one short-link per physical surface

| Surface | Link (set up as redirects w/ UTM) |
|---|---|
| Shirt QR | `apestogether.ai/shirt` |
| Bike QR | `apestogether.ai/bike` |
| Business cards (events) | `apestogether.ai/nyc` |
| Talk slides (when we present) | `apestogether.ai/talk` |

Zero-infra version: Vercel redirects in `vercel.json` → store pages/site with `?utm_source=` params. If a surface produces nothing in 60 days, kill or redesign it.

---

## 5. Budget (fits inside the existing $1k tier of `MARKETING_PLAN.md`)

| Item | Est. |
|---|---|
| Meetup/QWAFAxNEW memberships + event RSVPs | ~$100 |
| Stocktoberfest 1-day pass (VERIFY price) | $300–800? |
| Shirts ×10 | ~$200 |
| Bike signage (coroplast + mount + QR print) | ~$60 |
| Business cards ×250 | ~$40 |

---

## 6. Sequenced into the trigger-based phases

- **Now → launch trigger (Phase pre-launch):** QWAFAxNEW Sep 5 if ticket available → NYC Algo Trading + Day Traders meetups as recurring reps → order shirts → university club emails (September window) → decide Stocktoberfest by mid-Sep.
- **Stocktoberfest (Oct 5–7):** peak effort — early-access invites + Founding Trader pitch in person; bike outside venue; every contact into the outreach tracker.
- **Launch window (Nov):** invite every warm NYC contact personally on launch day; return to the two recurring meetups wearing the leaderboard ("I launched — here's what happened") — that's also the moment to give the organizer-pitched technical talk.
- **Post-launch:** talks graduate from "what I'm building" to "what the data shows" (bot-vs-human results = QWAFAxNEW-grade material).
