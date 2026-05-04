# Apes Together — Competitive Pricing & Cost Analysis

*Prepared May 3, 2026*

---

## Executive Summary

**Recommendation: Keep $9/month per trader subscription. Lower the free trial from 1 month to 7 days. Add an annual plan at $79/year (27% discount).**

Your current pricing is correctly positioned. Here's why, and the detailed evidence.

---

## 1. Competitive Landscape Deep Dive

### Dub (Closest Competitor)

**What they offer:** Real-money copy trading with automated execution via their own SEC-registered broker-dealer. Users' money is held in Dub's brokerage, and trades are auto-mirrored.

**Current pricing model (as of April 2026 — they recently restructured):**
- **dub Free tier:** Browse portfolios, view performance/holdings. One-time manual copy (not auto-synced).
- **dub Plus:** Auto-copy for "Core Creator" portfolios. Quarterly or annual billing (exact price not publicly listed but historically $9.99/month or $89.99/year for the old "Founder's Access" plan).
- **Premium Creator subscriptions:** Individual per-creator subscriptions set by each creator. Separate from dub Plus. Requires separate payment per Premium Creator you want to follow.
- **$3/month maintenance fee** on brokerage accounts.
- **$100 minimum deposit** to open an account.
- **$30 ACH return fee.**
- **SEC regulatory fees** passed through on sales.

**Creator compensation (Dub):** Opaque. CNBC reports "royalties" negotiated individually between Dub and each creator. No transparent rev-share formula. Must be "accepted" into the creator program.

**User complaints (from Reddit, App Store, Trustpilot 3.6★):**
- Subscription cost devastating on small accounts ($90/year is a 9% drag on a $1,000 account)
- 13F filing data is weeks to months old — "copying yesterday's trades"
- Delayed execution during volatility causes slippage
- Limited assets (no crypto, options, international stocks)
- New per-creator subscription model confuses users
- $3/month maintenance fee on top of subscription

**Key insight:** Dub now charges BOTH a platform subscription (dub Plus) AND per-creator fees for premium creators. Total cost to follow one premium creator: ~$10/month (Plus) + creator fee = potentially $20-30+/month.

---

### eToro (Established global player, recently IPO'd on Nasdaq)

**What they offer:** Full copy trading with real money via their platform. Publicly traded (ETOR) since May 2025.

**Pricing:**
- **$0 additional fee for copy trading** — no subscription, no performance fee, no management fee
- Revenue comes from spreads and currency conversion fees (hidden costs)
- **$200 minimum** to copy a single investor
- **$500+ recommended** for accurate replication
- Withdrawal fee: $5
- Currency conversion fee: 1.5% (for non-USD deposits)
- Inactivity fee: $10/month after 12 months
- **Waitlisted access** — copy trading feature is currently behind a waitlist in the US, creating an additional barrier to entry beyond the $200 minimum

**Creator compensation (eToro Popular Investor Program) — 4 tiers:**
- **Cadet tier (Level 1):** No payment. Need 1 verified copier, $1K AUC, risk score ≤6, must stay 2+ months
- **Champion tier (Level 2):** Monthly payment from eToro (fixed amount, not %). Need to stay 4+ months
- **Elite tier (Level 3):** 1.5% of AUC annually, paid monthly. Must stay 2+ months before advancing
- **Elite Pro (Level 4):** Up to 2-2.5% of AUC annually, paid monthly
- Example: $150K AUC × 1.5% = $2,250/year ($187/month)
- Example: $5M AUC × 2% = $100,000/year ($8,333/month)

**User experience:** Generally positive. Main complaints: positions can't be transferred to another broker, small copy amounts miss some trades. Copy trading behind a waitlist frustrates US users who signed up expecting immediate access.

**Key insight:** eToro's "free" model is funded by spreads/FX fees, which are invisible to most users. Their Popular Investor payments are based on AUC, not subscriptions — structurally different from your model. The waitlist + $200 minimum + requirement that real money is at risk are all significant friction points that Apes Together avoids entirely.

---

### Autopilot

**What they offer:** Automated portfolio mirroring through connected brokerage accounts (Robinhood, Fidelity, Schwab, E*TRADE, etc.)

**Pricing:**
- **$100/year per portfolio** OR $29/quarter
- Works with existing brokerages (doesn't require their own)
- No minimum investment

**Key difference from you:** Executes real trades in user's actual brokerage. Higher friction (connecting accounts), but real execution.

---

### Public.com

**What they offer:** Social investing features (discontinued explicit copy trading in June 2025, pivoted to AI). Still offers community posts and portfolio visibility.

**Pricing:** Commission-free. Premium tiers for advanced features. No copy trading subscription.

---

### StockHero (Trading bot marketplace)

**Pricing:**
- Lite: $29.99/month
- Basic: $49.99/month
- Pro: $99.99/month

---

## 2. Your Positioning vs. Competition

| Factor | Dub | eToro | Autopilot | **Apes Together** |
|--------|-----|-------|-----------|-------------------|
| Real money execution | ✅ Auto | ✅ Auto | ✅ Auto | ❌ Paper only |
| Subscriber cost/mo | ~$10 + creator fees | $0 (hidden in spreads) | ~$8.33/portfolio | **$9/trader** |
| Minimum investment | $100 | $200 | $0 | **$0** |
| User owns brokerage | ❌ (Dub holds) | ❌ (eToro holds) | ✅ | **N/A (paper)** |
| Performance verification | Partial (13F delay) | Full (live) | Full (live) | **Full (real-time)** |
| Creator revenue share | Opaque/negotiated | 1.5-2% of AUC | Unknown | **85% of proceeds** |
| Barrier to entry (creators) | Acceptance required | Strict qualification | N/A | **None (just perform)** |
| Notifications on trade | ❌ (auto-executes) | ❌ (auto-executes) | ❌ (auto-executes) | **✅ Instant push** |

---

## 3. The Friction Factor — Manual Execution

This is Apes Together's most significant structural disadvantage vs. auto-copy platforms. Users must **manually execute every trade** in their own brokerage after receiving a notification. The friction chain:

1. Receive push notification ("TraderX bought 50 NVDA @ $142.30")
2. Open brokerage app (Robinhood, Schwab, Fidelity, etc.)
3. Search for the ticker
4. Calculate position size (trader bought 50 shares with a $100K portfolio; user has $5K — how many shares?)
5. Execute the order at the **current** price (likely $143+ by now)
6. Repeat for every trade notification

**Concrete costs of friction:**
- **Slippage:** Price moves between notification and execution. On volatile stocks, 0.5-2% per trade is common. Over dozens of trades/month, this is real money.
- **Missed trades:** Notifications during meetings, driving, or after hours are missed entirely. Auto-copy platforms don't have this problem.
- **Scaling decisions:** Every trade requires the user to do portfolio-size math. No guidance is provided.
- **Decision fatigue:** Each notification is a micro-decision ("should I follow this one?"). Automation removes this burden.
- **Sell timing:** A delayed sell execution could mean catching a falling knife.

**This friction means Apes Together is NOT a copy-trading platform.** It's a **real-time trade signal service** with verified performance. The correct comparison set is financial newsletters and signal services:

| Service | Price | What you get |
|---|---|---|
| Motley Fool Stock Advisor | $13/mo | 2 text picks/month (weeks-old analysis) |
| Seeking Alpha Premium | $20/mo | Ratings + analysis articles |
| TipRanks Premium | $30/mo | Analyst consensus + smart portfolios |
| Trade Ideas (scanner) | $84/mo | AI-driven alert streams |
| **Apes Together** | **$9/mo** | **Real-time verified trade alerts** |

Against this comp set, $9/month is a bargain — and the product is superior because it shows verified real performance, not opinions or model scores.

---

## 4. Pricing Arguments

### Arguments for LOWER pricing (vs. $9):
- **Manual execution friction:** Users do all the work — this isn't hands-free copy trading.
- **No capital at risk on your platform:** You don't hold money, so there's less perceived "service."
- **Target demographic skews young/lower income:** Gen Z median total investment ~$4,000 (CFA Institute research). $9/month = $108/year = 2.7% drag on a $4,000 portfolio.
- **Paper trading is free everywhere:** Webull, thinkorswim, Investopedia simulator all offer free paper trading.

### Arguments for KEEPING $9/month:
- **Unique value:** Real-time trade alerts from verified performers. No newsletter offers this.
- **Cheaper than every comparable signal service:** Motley Fool ($13), Seeking Alpha ($20), TipRanks ($30).
- **Lower total cost than copy-trading platforms:** Dub costs $10+/month PLUS per-creator fees PLUS $3/month maintenance. eToro hides costs in spreads.
- **No minimums, no account lock-in:** Users don't move their money to a new brokerage. Zero switching cost.
- **Risk-free discovery:** Paper trading removes the "what if they lose my money" fear — the #1 barrier for new investors.
- **Creator economics are best-in-class:** 85% rev share vs. Dub's opaque negotiation vs. eToro's 1.5% of AUC. This attracts better talent to your platform.
- **$9 is below impulse threshold:** App Store data shows $9.99/month is the sweet spot for "try it" decisions in consumer subscriptions.
- **The friction is the feature:** Users retain full control of their brokerage, choose which trades to follow, and can learn by observing without risking anything. This is a different value prop than "set it and forget it" copy trading.

---

## 5. Portfolio Size & Fee Drag Analysis

### Apes Together fee drag: Monthly vs. Annual options

| Portfolio Size | $9/mo ($108/yr) | $69/yr | $59/yr |
|---|---|---|---|
| $1,000 | 10.8% | **6.9%** | 5.9% |
| $2,500 | 4.3% | **2.8%** | 2.4% |
| $5,000 | 2.2% | **1.4%** | 1.2% |
| $10,000 | 1.1% | **0.7%** | 0.6% |

### Cross-platform comparison (using best available plan)

| Portfolio Size | AT Monthly ($108/yr) | AT Annual ($69/yr) | Dub (~$156/yr) | Autopilot ($100/yr) |
|---|---|---|---|---|
| $1,000 | 10.8% | **6.9%** | 15.6% | 10.0% |
| $2,500 | 4.3% | **2.8%** | 6.2% | 4.0% |
| $5,000 | 2.2% | **1.4%** | 3.1% | 2.0% |
| $10,000 | 1.1% | **0.7%** | 1.6% | 1.0% |

**Key insights:**
- At $69/year, your fee drag **beats Autopilot at every portfolio size** despite Autopilot offering real execution.
- $69/year on a $2,500 portfolio is only 2.8% — comparable to a typical actively managed ETF expense ratio.
- $59/year would be even more competitive but at the cost of creator payouts (see Section 6).
- For accounts under $1,000, the percentage drag is high for ANY subscription service. This is an industry-wide issue, not specific to you.

---

## 6. Creator Compensation Analysis

### Why 85% rev share is correct:

**Monthly plan ($9/month):**
- Subscriber pays: $9/month via App Store IAP
- Apple takes: 15% (Small Business Program) = $1.35
- Net to you: $7.65
- Creator gets 85% of net: $6.50/month
- You retain: $1.15/month (15% of net)

**Annual plan ($69/year):**
- Subscriber pays: $69/year via App Store IAP
- Apple takes: 15% = $10.35
- Net to you: $58.65
- Creator gets 85% of net: $49.85/year ($4.15/month equivalent)
- You retain: $8.80/year ($0.73/month)

**Comparison:**
| Platform | Creator earning per subscriber equivalent |
|---|---|
| **Apes Together (monthly)** | **$6.50/sub/month** (transparent, guaranteed) |
| **Apes Together (annual)** | **$4.15/sub/month** (guaranteed 12 months) |
| Dub | Negotiated "royalties" — reportedly low, opaque |
| eToro | $0 until Champion tier ($50K+ AUC). At $150K AUC: ~$187/mo total |
| Substack | 90% of subscription after Stripe fees (~$4.50 on a $5 sub) |
| YouTube | ~$3-5 per 1000 views (requires constant content creation) |

**Your 85% share is the highest transparent rev-share in copy/social trading.** Even at $69/year, the creator earns $4.15/month per subscriber — competitive with Substack and vastly better than YouTube. The annual plan trades lower per-month payout for guaranteed 12-month retention.

**Example earnings at scale (50/50 monthly/annual split):**
| Subscribers | Monthly revenue | Annual revenue | Creator monthly income |
|---|---|---|---|
| 25 | 13 × $6.50 + 12 × $4.15 | — | **$134/mo** |
| 50 | 25 × $6.50 + 25 × $4.15 | — | **$266/mo** |
| 100 | 50 × $6.50 + 50 × $4.15 | — | **$533/mo** |
| 250 | 125 × $6.50 + 125 × $4.15 | — | **$1,331/mo** |

### The "upload effort" concern:
You mentioned traders need "reasonable compensation for their time uploading trades." Consider:
- Uploading a trade takes <30 seconds in your app
- A trader with 50 subscribers earns ~$266/month for reporting maybe 5-15 trades
- That's $18-53 per trade reported — excellent $/effort ratio
- The leaderboard visibility + potential subscriber growth provides additional non-monetary incentive

---

## 7. Free Trial Length

### Current: 1 month free

**Problem:** A full month free is generous but creates issues:
1. **Delayed revenue:** Your first revenue comes in Month 2 at earliest
2. **Low commitment signal:** Users who sign up "just to try" but never engage don't convert
3. **Competitive comparison:** Dub offers 7 days. Autopilot offers no free trial.
4. **App Store precedent:** Most subscription apps use 3-7 day trials

### Recommendation: 7-day free trial

**Why 7 days is better:**
- Enough time to see 3-5 trading days of alerts (your core value prop)
- Creates urgency to engage quickly
- Matches industry standard (Dub also uses 7 days)
- Converts to revenue 3 weeks sooner
- Users who are serious will convert; tourists won't regardless of trial length
- Still risk-free for the subscriber

**Alternative considered (14 days):** Reasonable but less standard. Would cover 10 trading days. Use this if you feel 7 is too aggressive for beta.

---

## 8. Annual Plan Recommendation

**Add: $69/year option (36% savings vs monthly)**

Rationale:
- Dub charges $89.99/year (25% savings). Your $69 undercuts them by $21/year.
- Your monthly ($9) is already below their monthly ($10+)
- 36% annual discount is aggressive — compensates for the manual execution friction disadvantage vs auto-copy platforms
- $69/year ÷ 12 = $5.75/month perceived cost — makes the fee drag very competitive (see Section 5)
- Annual plans reduce churn significantly (users forget to cancel, feel committed)
- Creator payout on annual: $49.85/year per subscriber ($4.15/month) — still competitive with Substack
- $69 is under the $70 psychological threshold

---

## 9. Final Pricing Recommendation

| Element | Current | Recommended | Rationale |
|---------|---------|-------------|----------|
| Monthly price | $9/month | **$9/month (keep)** | Cheaper than every signal service; below impulse threshold |
| Annual price | None | **$69/year (add)** | 36% discount, undercuts Dub ($90), compensates for manual execution friction |
| Free trial | 1 month | **7 days** | Industry standard, faster revenue, same conversion |
| Creator rev share | 85% | **85% (keep)** | Best in class, key recruiting advantage |
| Minimum deposit | $0 | **$0 (keep)** | Major differentiator vs Dub ($100) and eToro ($200) |

### Price Sensitivity Summary

Your target subscriber with a $4,000 portfolio:
- **Monthly ($9/mo):** 2.7% annual fee drag. Comparable to a typical actively managed ETF.
- **Annual ($69/yr):** 1.7% annual fee drag. **Beats Autopilot** (2.5%) despite Autopilot offering real execution.
- **Dub comparison:** ~3.9% drag on $4K. Your annual plan is less than half the drag.
- **eToro comparison:** "Free" but requires $200 min, locks your money in their platform, hides fees in spreads.

The value proposition justification: If a trader you follow beats the S&P 500 by even 3-5%, your $69/year subscription pays for itself many times over on a $4K portfolio. The paper trading layer means subscribers can validate this BEFORE risking real money — a unique advantage nobody else offers.

**The friction factor is addressed by pricing, not eliminated:** The 36% annual discount acknowledges that subscribers do extra work (manual trade execution). This positions the annual plan as the "serious follower" tier — users who commit to learning from a trader's strategy, not just passively mirroring.

---

## 10. Competitive Vulnerabilities to Monitor

1. **Dub's per-creator model** may train users to expect variable pricing. Your flat $9/trader is simpler and more predictable.
2. **eToro entering the US market aggressively** with "free" copy trading. Counter: your paper trading is truly risk-free; eToro requires real money.
3. **If you add real-money execution later,** you could justify a price increase. Paper → real is a natural upgrade path.
4. **Volume discounts:** Consider a future "follow 3 traders for $19/month" bundle once you have enough quality traders. Not needed at launch.

---

## 11. Key Takeaway

Your $9/month is NOT too high — it's cheaper than every comparable signal service. The main risk isn't price — it's **perceived value given the manual execution friction**. Your messaging must constantly reinforce:

> "See exactly what trades top performers make, the moment they make them. Test their strategies risk-free before committing real money."

That positions the subscription as a **research and discovery tool** (worth $9/month easily) rather than a "copy-trading service" (where users expect automated execution for their money).

**The $69/year annual plan is the key to long-term retention.** It addresses the friction concern through pricing (36% discount = "we know you're doing the work") while locking in revenue and reducing churn. Push the annual plan prominently in the UI — it should be the default selection.
