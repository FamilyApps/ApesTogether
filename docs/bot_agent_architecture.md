# Bot Agent Orchestrator — Architecture & Implementation Plan

## Platform Philosophy
AI bots are **openly encouraged** on Apes Together. The platform is a competition for
who — professional, student, AI bot, anyone — can pick the best stocks. FAQ and marketing
will explicitly cover this. No special disclosure or labeling of bots is needed.

## Goal
Build an autonomous trading agent system where each bot has a personalized strategy, does real market research (price action, technicals, news sentiment, social media buzz), and makes informed buy/sell decisions daily to maximize gains. Start with 1 bot, scale up as needed via CLI controls. Architecture supports up to 10,000 bots at low marginal cost.

---

## 1. Data Layer — "Shared Research Hub"

**Core insight**: Decouple data fetching from bot decision-making. One centralized process fetches market data for the entire universe of tracked tickers, then all 10,000 bots consume that shared data. This means data cost is **O(tickers)**, not **O(bots)**.

### Data Sources (all already available or free)

| Source | What We Get | Cost | Rate Limit |
|--------|------------|------|------------|
| **AlphaVantage Premium** (existing) | NEWS_SENTIMENT (per-ticker sentiment scores from news), TOP_GAINERS_LOSERS (daily movers), server-side RSI/MACD/SMA/EMA/BBANDS, bulk quotes (100 tickers/call), earnings transcripts | ~$50/mo | 150 calls/min |
| **yfinance** (free, no key) | Bulk historical OHLCV (500 tickers in 1 call), real-time quotes, dividends, fundamentals (P/E, market cap, revenue) | $0 | ~2000/hr |
| **Finnhub Free** (free key) | Social sentiment from Reddit + Twitter (mention count, positive/negative scores, buzz score), company news headlines, earnings calendar, analyst upgrades/downgrades, congressional trading, insider transactions | $0 | 60 calls/min |

### Daily Data Pipeline (runs once, ~8 minutes total)

```
Phase 1: Bulk Price Data (yfinance)                          ~30 sec
  - Download 500 tickers in one yf.download() call
  - Get 100-day history for technical indicator computation

Phase 2: Technical Indicators (computed locally in pandas)    ~5 sec
  - RSI(14), MACD(12,26,9), SMA(20,50,200), EMA(12,26)
  - Bollinger Bands, ATR(14), Volume SMA(20)
  - Stochastic RSI, ADX (trend strength)
  - All computed from Phase 1 data — zero API calls

Phase 3: News Sentiment (AlphaVantage)                       ~3 min
  - NEWS_SENTIMENT for each industry topic (8 calls)
  - Returns per-ticker sentiment labels + scores
  - Each call covers 50+ articles mentioning dozens of tickers

Phase 4: Social Buzz (Finnhub)                               ~3 min
  - Social sentiment for top 100 tickers (Reddit + Twitter)
  - Mention count, positive/negative ratio, buzz score
  - At 60 calls/min, covers 100 tickers in ~2 min

Phase 5: Market Movers (AlphaVantage)                        ~1 sec
  - TOP_GAINERS_LOSERS — 1 API call, returns top 20 each
  - Identifies momentum opportunities

Phase 6: Analyst Activity (Finnhub)                          ~1 min
  - Recent upgrades/downgrades for tracked tickers
  - Earnings calendar for upcoming week
  - Insider transactions (are insiders buying or selling?)

Total: ~500 tickers covered, ~250 API calls, well within limits
```

### Data Cache Structure

All fetched data is written to a shared in-memory dictionary (or Redis/JSON file for persistence between runs):

```python
market_data = {
    "AAPL": {
        "price": 189.50,
        "change_pct": 1.2,
        "volume": 58000000,
        "volume_avg_20": 52000000,     # above-average volume = confirmation
        "rsi_14": 62.3,
        "macd_signal": "bullish_cross",  # MACD crossed above signal line
        "sma_20": 185.0,
        "sma_50": 180.0,
        "sma_200": 172.0,
        "price_vs_sma20": "above",      # price > SMA20 = short-term bullish
        "bollinger_position": 0.72,      # 0=lower band, 1=upper band
        "atr_14": 3.2,
        "adx": 28.5,                     # >25 = trending
        "news_sentiment": 0.35,          # -1 to 1 from AlphaVantage
        "news_buzz": "high",             # many articles = attention
        "social_mentions": 142,          # Reddit + Twitter mentions
        "social_sentiment": 0.61,        # positive ratio
        "analyst_action": "upgrade",     # recent analyst action
        "insider_net": "buying",         # net insider activity
        "earnings_days_away": 15,        # days until next earnings
        "sector": "Technology",
        "market_cap": 2900000000000,
    },
    ...
}
```

---

## 2. Strategy Layer — "Bot Personas"

Each bot has a **strategy profile** stored in `User.extra_data`. Strategies are parameterized — no LLM needed, just different weights on the same shared indicators.

### Strategy Types

| Strategy | How It Decides | Human Archetype |
|----------|---------------|-----------------|
| **Momentum Chaser** | Buys stocks with RSI 50-70 + positive MACD cross + above SMA20. Sells when RSI > 75 or MACD bearish cross. | "The trend is your friend" trader |
| **Value Hunter** | Looks for RSI < 35 + price below SMA50 + positive news sentiment. Contrarian entries on dips. | Warren Buffett style |
| **News Reactor** | Prioritizes high news_sentiment + high social_buzz. Buys on positive catalysts, sells on negative shifts. | Reddit/Twitter-driven trader |
| **Swing Trader** | Enters at Bollinger Band lower, exits at upper. Uses ATR for position sizing. 3-10 day holds. | Technical chart reader |
| **Earnings Player** | Buys stocks 5-15 days before earnings if sentiment positive + analyst upgrades. Sells 1-2 days before earnings (risk management). | Earnings season specialist |
| **Sector Rotator** | Tracks relative strength of sectors. Rotates into strongest sectors, out of weakest. Monthly rebalance. | Macro strategist |
| **Insider Follower** | Prioritizes stocks where insiders are net buying + positive technicals. | "Follow the smart money" |
| **Dividend Growth** | Targets stocks with rising dividends + price near support levels. Long-term holds. | Income investor |
| **Social Momentum** | Highest social mentions + positive sentiment + volume surge. Quick entries/exits. | WallStreetBets FOMO trader |
| **Balanced/General** | Equal-weight blend of technicals + sentiment + fundamentals. Conservative position sizing. | Diversified index-aware trader |

### Strategy Profile Structure (stored in User.extra_data)

```python
{
    "industry": "Technology",
    "strategy": "momentum",
    "risk_tolerance": 0.7,          # 0-1, affects position sizes
    "max_positions": 10,            # max concurrent holdings
    "trade_frequency": "daily",     # daily, twice_weekly, weekly
    "hold_period_days": [3, 15],    # typical hold range
    "indicator_weights": {
        "rsi": 0.25,
        "macd": 0.20,
        "news_sentiment": 0.20,
        "social_buzz": 0.15,
        "volume": 0.10,
        "insider": 0.10
    },
    "buy_threshold": 0.6,           # weighted score > this → buy signal
    "sell_threshold": -0.3,         # weighted score < this → sell signal
    "personality_quirks": {
        "fomo_factor": 0.3,         # tendency to chase hot stocks
        "loss_aversion": 0.6,       # how quickly to cut losses
        "overconfidence": 0.4,      # tendency to oversize winners
    }
}
```

---

## 3. Decision Engine — "The Brain"

For each bot, each trading session:

```
1. SCAN: Filter the shared market_data to bot's industry/universe
2. SCORE: Apply bot's indicator_weights to each stock's signals
3. RANK: Sort by composite score
4. DECIDE:
   - BUY: Top-scoring stocks above buy_threshold that bot doesn't own
   - SELL: Owned stocks below sell_threshold
   - HOLD: Everything else
5. SIZE: Determine quantity based on risk_tolerance + ATR
6. EXECUTE: Call admin API to place trades
```

### Scoring Function

```python
def compute_signal_score(stock_data, bot_profile):
    weights = bot_profile['indicator_weights']
    score = 0.0

    # RSI signal: oversold=bullish, overbought=bearish
    rsi = stock_data['rsi_14']
    if rsi < 30: rsi_signal = 1.0       # strongly oversold
    elif rsi < 45: rsi_signal = 0.5     # mildly oversold
    elif rsi < 55: rsi_signal = 0.0     # neutral
    elif rsi < 70: rsi_signal = 0.3     # momentum (good for momentum bots)
    else: rsi_signal = -0.5             # overbought

    # For momentum bots, flip the RSI interpretation
    if bot_profile['strategy'] == 'momentum':
        if 50 < rsi < 70: rsi_signal = 0.7  # riding the trend

    # MACD signal
    macd_signal = 1.0 if stock_data['macd_signal'] == 'bullish_cross' else
                  -1.0 if stock_data['macd_signal'] == 'bearish_cross' else 0.0

    # News + Social sentiment (-1 to 1)
    news_signal = stock_data['news_sentiment']
    social_signal = (stock_data['social_sentiment'] - 0.5) * 2  # normalize to -1,1

    # Volume confirmation
    vol_ratio = stock_data['volume'] / max(stock_data['volume_avg_20'], 1)
    volume_signal = min(1.0, (vol_ratio - 1.0))  # positive if above average

    # Insider signal
    insider_signal = 0.5 if stock_data['insider_net'] == 'buying' else
                    -0.5 if stock_data['insider_net'] == 'selling' else 0.0

    score = (weights['rsi'] * rsi_signal +
             weights['macd'] * macd_signal +
             weights['news_sentiment'] * news_signal +
             weights['social_buzz'] * social_signal +
             weights['volume'] * volume_signal +
             weights['insider'] * insider_signal)

    # Apply personality quirks
    if stock_data.get('social_mentions', 0) > 100:
        score += bot_profile['personality_quirks']['fomo_factor'] * 0.2

    return score
```

---

## 4. Human Behavior Simulation

Real traders don't act like algorithms. Each bot simulates human tendencies:

### Behavioral Traits

- **FOMO (Fear of Missing Out)**: High-FOMO bots chase stocks that are already up 5%+ with high social buzz. They enter late but ride momentum.
- **Loss Aversion**: High-loss-aversion bots cut losses quickly (sell at -3%). Low-loss-aversion bots hold through dips hoping for recovery.
- **Overconfidence**: After a winning streak (3+ consecutive profitable trades), overconfident bots increase position sizes by 20-50%.
- **Recency Bias**: Bots weight recent price action more heavily than longer-term trends.
- **Herd Behavior**: Some bots check what other top-performing bots on the leaderboard are holding and factor that into decisions.
- **Trading Time Variance**: Bots don't all trade at 9:30 AM. They trade at varied times: some at open, some at lunch, some near close.
- **Skip Days**: Not every bot trades every day. Some trade 3x/week, some daily, some only when strong signals appear.
- **Partial Fills**: Bots sometimes buy/sell partial positions instead of all-or-nothing.

### Implementation

```python
def apply_human_noise(bot, decision):
    # Sometimes skip trading even with signals (human laziness/distraction)
    if random.random() < 0.15:  # 15% chance of doing nothing
        return None

    # Vary quantity by ±15% (humans don't buy exact round lots)
    noise = random.uniform(0.85, 1.15)
    decision['quantity'] = max(1, int(decision['quantity'] * noise))

    # After 3+ winning trades, increase size (overconfidence)
    if bot.recent_win_streak >= 3 and bot.personality['overconfidence'] > 0.5:
        decision['quantity'] = int(decision['quantity'] * 1.3)

    # Loss aversion: sell faster after recent losses
    if decision['type'] == 'hold' and bot.unrealized_pnl < -0.03:
        if random.random() < bot.personality['loss_aversion']:
            decision['type'] = 'sell'  # panic sell

    return decision
```

---

## 5. Execution Architecture

### Scheduling (Cron-based)

```
8:00 AM ET  — Phase 1-6: Shared Research Hub fetches all data
9:35 AM ET  — Wave 1: 30% of bots trade (early birds)
10:30 AM ET — Wave 2: 30% of bots trade (mid-morning)
1:00 PM ET  — Wave 3: 20% of bots trade (lunch traders)
3:30 PM ET  — Wave 4: 20% of bots trade (end-of-day)
4:30 PM ET  — End-of-day portfolio snapshot + P&L logging
```

Each wave introduces ±30 minute jitter per bot for realism.

### API Call Budget Per Day

```
Data fetching:    ~250 calls (AlphaVantage + Finnhub)
Trade execution:  ~5,000 calls (avg 0.5 trades per bot × 10,000 bots)
Total:            ~5,250 API calls to our own backend per day
                  ~250 external API calls (well within limits)
```

### Scaling Math

- **AlphaVantage**: 150 calls/min × 60 min = 9,000 calls/hr. We use ~250/day. Massive headroom.
- **yfinance**: 1 bulk call for 500 tickers. Trivial.
- **Finnhub**: 60 calls/min × 60 min = 3,600 calls/hr. We use ~100/day. Massive headroom.
- **Our backend API**: Trade execution calls are just POST requests to our own server. Rate limit is whatever our server can handle.
- **Compute**: All 10,000 bot decisions are pure Python math on shared data. Takes <10 seconds total on a single CPU.
- **Marginal cost per bot**: $0.00/day (data is shared, compute is trivial).

---

## 6. Implementation Files

```
bot_agent.py          — CLI entrypoint, orchestrator, scheduling
bot_data_hub.py       — Shared data fetching (AlphaVantage, yfinance, Finnhub)
bot_strategies.py     — Strategy definitions and scoring functions
bot_behaviors.py      — Human behavior simulation (FOMO, loss aversion, etc.)
bot_executor.py       — Trade execution via admin API
bot_personas.py       — Bot persona generation (names, industries, strategy params)
```

---

## 7. Cost Summary

| Item | Daily Cost | Monthly Cost |
|------|-----------|--------------|
| AlphaVantage Premium | (existing) | ~$50 |
| Finnhub Free | $0 | $0 |
| yfinance | $0 | $0 |
| Compute (runs on any VPS) | ~$0.10 | ~$3 |
| **Total marginal cost for 10K bots** | **~$0.10** | **~$53** |

---

## 8. Key Risks & Mitigations

| Risk | Mitigation |
|------|-----------|
| yfinance rate limiting | Cache aggressively, batch requests, use AlphaVantage as fallback |
| All bots making identical trades | Strategy diversity + personality quirks + FOMO variance ensure different decisions |
| Unrealistic trade patterns | Human noise layer, skip days, time jitter, partial fills |
| API downtime | Graceful degradation — if data fetch fails, bots hold existing positions |
| Leaderboard manipulation concerns | Bots are flagged `role='agent'` in DB; can be excluded from real leaderboards if needed |
