# Press Kit — Assembly Guide

_Created Session 34 (2026-07-23). The public page is live at `apestogether.ai/press`
(`templates/press.html`). This doc is the USER's assembly checklist for the
shareable Drive folder + one-pager PDF. Phase 2 exit gate = "press kit complete"
means: every checkbox below done and the Drive link swapped into `/press`._

---

## 1. The Drive folder (what journalists actually get)

Create one public "anyone with link can VIEW" Google Drive folder named
**"ApesTogether Press Kit"** containing:

- [ ] `ApesTogether-OnePager.pdf` — text drafted below (§3); paste into Google
      Docs, style minimally, export PDF.
- [ ] `screenshots/` — 6 real captures (shot list §2). PNG, straight off the
      device, no frames/effects (journalists add their own).
- [ ] `logo/` — app icon 512×512 + 1024×1024 PNG (have: `static/images/logo.png`;
      export the 1024 master from the design source).
- [ ] `banner/` — press banner (Gemini prompt §4.1).
- [ ] `founder/` — real headshot (photo, not AI) + `bio.txt` (3 sentences, §5).
- [ ] `facts.txt` — copy the Quick Facts + Fact-check FAQ from `/press`.
- [ ] **Then:** swap the `mailto:` asset link on `/press` for the Drive link
      (marked with `TODO(USER)` comment in `templates/press.html`).

## 2. Screenshot shot list (capture on the Pixel 8a during today's on-device pass)

Take these while doing the billing E2E / v7 sideload — the device is already
in hand. `adb exec-out screencap -p > name.png` or power+voldown.

1. **Leaderboard** — 1W view with AI bots + humans interleaved (the money shot;
   this is the "humans vs machines" visual every story needs).
2. **Trader portfolio (public view)** — hero card with performance chart + founder pill.
3. **Real-time alert notification** — system tray showing a trade alert
   (trigger via admin test push or a bot trade).
4. **Trade logging screen** — the trade sheet mid-entry (shows "priced at market" mechanic).
5. **Subscribe sheet** — plan pills w/ trial copy (shows the $9 business model).
6. **Earnings/payout screen** — a creator's payout summary (shows the 85% story).

iOS versions of 1–3 too if the Mac session happens (Apple likes platform-native
shots; also needed for ASC "App Preview" stills later).

## 3. One-pager PDF — draft text (paste into Docs)

> **ApesTogether**
> **Every trade verified. 85% to traders. AI bots keep the humans honest.**
>
> **The problem** — Most young investors get stock ideas from social media.
> None of it is verifiable: anyone can claim any track record, sell any course,
> delete any losing call.
>
> **The product** — ApesTogether is the verification layer. Traders log trades
> in the app, timestamped and priced at the live market price. No imported
> history, no self-reported wins — the public leaderboard is built only from
> what happened after you joined. Subscribers pay $9/month for a trader's
> real-time trade alerts, then decide for themselves in their own brokerage.
> Traders keep 85% of net proceeds. It's the creator economy where the content
> is a track record.
>
> **The hook** — AI-managed portfolios trade on the same leaderboard, same
> rules. The standings are a live public experiment: can retail traders beat
> the machines? [UPDATE BEFORE SENDING: current standings one-liner, e.g.
> "After N weeks: the top AI bot ranks #X of Y."]
>
> **Traction** — [UPDATE BEFORE SENDING: traders on platform · trades logged ·
> founding-trader count · waitlist size · retention if strong]
>
> **The company** — Built solo by a NYC developer; bootstrapped, zero VC.
> Operated by Family Apps LLC. Not a broker — all platform trading is virtual;
> no funds held, no trades executed.
>
> **Contact** — press@apestogether.ai · apestogether.ai/press
> [FOUNDER NAME] · [X handle] · iOS + Android (U.S.)

## 4. Gemini asset prompts (USER runs these, delivered in chat too)

Rules: decorative/brand art ONLY from AI — never fake app screenshots, never
an AI founder "photo" (both are press-credibility killers). Keep text out of
the images; text gets added in Docs/Canva where it can't be misspelled.

### 4.1 Press banner (Drive folder cover + one-pager header)
See chat for the full prompt (banner, 16:9).

### 4.2 One-pager header strip
See chat (wide thin strip variant of the same system).

### 4.3 X/social launch-era card background
See chat (1200×675 quote-card background).

## 5. Remaining USER inputs (can't be done by Cascade)

- [ ] Create the `press@apestogether.ai` alias (Workspace Admin → account →
      Add alternate email) → it's already referenced on `/press`.
- [ ] Founder bio (3 sentences: name, one-line background incl. prior WSJ
      coverage if you want it referenced, why you built this) + real headshot.
- [ ] Decide: real name public? (WSJ pitch references prior coverage — probably
      yes.) Update the `/press` Founder section via Cascade when decided.
- [ ] Metrics block in the one-pager: fill at Phase-2 exit when numbers exist.

## 6. Distribution notes (from LAUNCH_OUTREACH.md — don't re-invent)

- WSJ exclusive first (T-21 to T-14), then embargo wave to Tier 2/3 (T-10 to
  T-7), then wide. Angle sheet: `LAUNCH_OUTREACH.md` §Story Angles.
- Attach the one-pager PDF; link the Drive folder + `/press`; never attach
  more than the PDF (spam filters).
- Same-day response SLA on press@ during launch week.
