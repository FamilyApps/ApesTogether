# Prompt for Architecture Review (Perplexity / Grok)

Copy everything below the line and paste into Perplexity or Grok:

---

I'm building an autonomous bot trading agent system for a social investing platform (think a simulated WallStreetBets meets Robinhood). The platform lets real users track portfolios and subscribe to follow other users' trades. I need to populate the platform with bot "influencer" accounts that behave like real human traders — each with their own strategy, research process, and personality.

**Please review this architecture for technical soundness, cost-effectiveness, scalability, and realism of the trading behavior. Identify any flaws, missing considerations, or better approaches I should consider.**

## Context & Constraints
- Scale target: **10,000 bot accounts**, each making 0-2 trades per day
- Cost target: **<$100/month** total for all bots combined (excluding existing API subscriptions)
- Bots trade on a simulated portfolio (no real money), but use **real market data** to make decisions
- Already have: **AlphaVantage Premium** (150 API calls/min), our own Flask backend with admin APIs for creating users, adding stocks, and executing trades
- Willing to add: **Finnhub Free** (60 calls/min, free tier), **yfinance** (free, no API key)
- Bots should look and feel like real human traders to other users on the platform — varied strategies, varied timing, imperfect decisions, human-like behavioral biases
- No LLM calls per bot (too expensive at scale) — pure rules-based strategies with parameterized configs

## Proposed Architecture

### Layer 1: Shared Data Hub (runs once daily, ~8 min)
One centralized process fetches market data for ~500 tracked tickers. All 10K bots consume this shared data. Data cost is O(tickers), not O(bots).

**Data sources:**
1. **yfinance** — Bulk download 500 tickers' 100-day OHLCV history in one call (~30 sec). Free, no API key.
2. **Local pandas computation** — RSI(14), MACD(12,26,9), SMA(20/50/200), EMA(12/26), Bollinger Bands, ATR(14), ADX, Stochastic RSI, Volume SMA(20). Zero API calls.
3. **AlphaVantage NEWS_SENTIMENT** — Query by topic (technology, finance, healthcare, etc.) — ~8 API calls cover all industries, returns per-ticker sentiment scores from news articles.
4. **AlphaVantage TOP_GAINERS_LOSERS** — 1 call, identifies daily momentum plays.
5. **Finnhub Social Sentiment** — Reddit + Twitter mention counts and positive/negative sentiment scores for top ~100 tickers (~100 API calls at 60/min = ~2 min).
6. **Finnhub Analyst Upgrades/Downgrades + Insider Transactions** — for ~50 key tickers (~50 calls).

**Total external API calls/day: ~250** (well within all rate limits).

### Layer 2: Strategy Engine (10 strategy archetypes)
Each bot has a parameterized strategy profile stored in the database:

1. **Momentum Chaser** — RSI 50-70, positive MACD cross, above SMA20, rides trends
2. **Value Hunter** — RSI < 35, below SMA50, positive news sentiment, contrarian dip buying
3. **News Reactor** — Prioritizes high news sentiment + social buzz, catalyst-driven
4. **Swing Trader** — Bollinger Band bounces, ATR-based sizing, 3-10 day holds
5. **Earnings Player** — Buys 5-15 days pre-earnings if sentiment positive, sells before event
6. **Sector Rotator** — Tracks relative sector strength, rotates monthly
7. **Insider Follower** — Prioritizes stocks with net insider buying + supporting technicals
8. **Dividend Growth** — Targets rising dividends + price near support
9. **Social Momentum** — Highest social mentions + positive sentiment + volume surge
10. **Balanced/General** — Equal-weight blend of all signals

Each strategy has different **indicator weights** (e.g., momentum bot weights RSI 0.25, MACD 0.20, news 0.20, social 0.15, volume 0.10, insider 0.10). A composite score above a buy_threshold triggers a buy signal; below sell_threshold triggers a sell.

### Layer 3: Human Behavior Simulation
Bots simulate real human psychology:
- **FOMO**: Some bots chase stocks that are already up 5%+ with high social buzz
- **Loss Aversion**: Configurable — some cut losses at -3%, others hold through -15% dips
- **Overconfidence**: After 3+ winning trades, some bots increase position sizes 20-50%
- **Recency Bias**: Weight recent price action more than longer-term trends
- **Skip Days**: 15% chance of not trading even with signals (simulates human distraction)
- **Time Jitter**: Bots trade in 4 waves across the day (9:35am, 10:30am, 1pm, 3:30pm ET) with ±30 min random offset
- **Partial Fills**: Vary quantities ±15% from calculated ideal
- **Herd Behavior**: Some bots check what top leaderboard performers are holding

### Layer 4: Execution
- Trades executed via internal admin REST API (POST /admin/bot/execute-trade)
- Run as cron job (could be Vercel cron, GitHub Actions, or standalone VPS)
- Each bot's decision is pure Python math on shared data — <10 sec total for all 10K bots on single CPU

### Cost Estimate
| Item | Monthly |
|------|---------|
| AlphaVantage Premium (existing) | ~$50 |
| Finnhub Free | $0 |
| yfinance | $0 |
| Compute (VPS/cron) | ~$3 |
| **Total** | **~$53/month for 10K bots** |

## My Specific Questions

1. **Strategy Diversity**: Will 10 strategy archetypes with parameterized weights produce enough trade diversity across 10K bots, or will they still feel homogeneous? How should I ensure realistic variance?

2. **Data Freshness**: Running the data hub once at 8am ET means bots trade on potentially stale data. Should I add a midday refresh? Or is daily data sufficient for the realism goal since these are simulated portfolios?

3. **yfinance Reliability**: yfinance scrapes Yahoo Finance and has no SLA. At 500 tickers, am I likely to hit rate limits or get blocked? Should I have a fallback to AlphaVantage's TIME_SERIES_DAILY (which would cost 500 API calls = ~3.5 min at 150/min)?

4. **Social Sentiment Value**: Finnhub's free-tier social sentiment covers Reddit/Twitter. Is this data actually useful for identifying trending stocks, or is it too noisy/delayed to matter? Are there better free alternatives?

5. **Missing Data Sources**: Am I missing any free/cheap data source that would significantly improve bot decision quality? (Congressional trading data? Options flow? Short interest?)

6. **Behavioral Realism**: What human trading behaviors am I missing that would make the bots more convincing? Should I add any of: anchoring bias, disposition effect (selling winners too early), calendar effects (Monday pessimism, Friday optimism), portfolio rebalancing triggers?

7. **Risk of Pattern Detection**: If a savvy user looked at bot trading patterns, what would give them away as bots? How do I make them harder to distinguish from real users?

8. **Alternative Architecture**: Is there a fundamentally better approach I'm not considering? For example, should I use a lightweight ML model trained on historical profitable trades instead of rules-based strategies? Would that be feasible at this scale/cost?

9. **Execution Scheduling**: I proposed 4 trading waves per day. Is this realistic for human behavior? Should some bots be "day traders" (multiple trades in one session) vs "swing traders" (trade once every few days)?

10. **Ethical/Legal Considerations**: The bots will appear as real users on the platform. What disclosures or safeguards should I implement? Should bots be subtly flagged? Should the platform's TOS address AI-generated portfolio content?
