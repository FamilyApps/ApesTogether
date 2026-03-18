"""
Bot Strategy Engine
====================
Defines 10 strategy archetypes with parameterized scoring functions.
Each bot gets a unique strategy profile generated via Dirichlet sampling
around its archetype template — producing thousands of distinct behaviors
from just 10 base types.

Strategy Archetypes:
    1. momentum     - Rides trends: RSI 50-70, MACD bullish, above SMA20
    2. value        - Contrarian dip buyer: RSI < 35, below SMA50, positive news
    3. news_reactor - Catalyst-driven: high news sentiment + social buzz
    4. swing        - Bollinger Band bounces, ATR-based sizing, 3-10 day holds
    5. earnings     - Pre-earnings plays with sentiment + analyst support
    6. sector_rotation - Rotates into strongest sectors monthly
    7. insider_follower - Follows net insider buying + supporting technicals
    8. dividend_growth  - Targets dividend stocks near support levels
    9. social_momentum  - Reddit/Twitter buzz + volume surge
   10. balanced     - Equal-weight blend of all signals
"""

import random
import math
import numpy as np
import logging

logger = logging.getLogger('bot_strategies')

# ── Strategy Archetype Templates ─────────────────────────────────────────────
# Each defines the "center" of the Dirichlet distribution for indicator weights
# and default thresholds. Individual bots sample AROUND these values.

STRATEGY_TEMPLATES = {
    'momentum': {
        'description': 'Rides trends using momentum indicators',
        'indicator_weights': {
            'rsi': 0.22, 'macd': 0.25, 'news_sentiment': 0.12,
            'social_buzz': 0.10, 'volume': 0.18, 'insider': 0.05,
            'price_trend': 0.08,
        },
        'buy_threshold': 0.45,
        'sell_threshold': -0.25,
        'hold_period_days': (3, 15),
        'max_positions': (6, 12),
        'risk_tolerance': (0.5, 0.8),
        'trade_frequency': 'daily',
        'preferred_cap': 'any',
    },
    'value': {
        'description': 'Buys undervalued dips with contrarian logic',
        'indicator_weights': {
            'rsi': 0.28, 'macd': 0.10, 'news_sentiment': 0.20,
            'social_buzz': 0.05, 'volume': 0.12, 'insider': 0.15,
            'price_trend': 0.10,
        },
        'buy_threshold': 0.40,
        'sell_threshold': -0.15,
        'hold_period_days': (10, 60),
        'max_positions': (5, 10),
        'risk_tolerance': (0.3, 0.6),
        'trade_frequency': 'twice_weekly',
        'preferred_cap': 'large',
    },
    'news_reactor': {
        'description': 'Trades on news catalysts and sentiment shifts',
        'indicator_weights': {
            'rsi': 0.08, 'macd': 0.08, 'news_sentiment': 0.35,
            'social_buzz': 0.22, 'volume': 0.15, 'insider': 0.05,
            'price_trend': 0.07,
        },
        'buy_threshold': 0.50,
        'sell_threshold': -0.30,
        'hold_period_days': (1, 7),
        'max_positions': (4, 8),
        'risk_tolerance': (0.6, 0.9),
        'trade_frequency': 'daily',
        'preferred_cap': 'any',
    },
    'swing': {
        'description': 'Bollinger Band bounces with ATR-based sizing',
        'indicator_weights': {
            'rsi': 0.20, 'macd': 0.15, 'news_sentiment': 0.08,
            'social_buzz': 0.05, 'volume': 0.20, 'insider': 0.07,
            'price_trend': 0.25,
        },
        'buy_threshold': 0.42,
        'sell_threshold': -0.20,
        'hold_period_days': (3, 10),
        'max_positions': (5, 10),
        'risk_tolerance': (0.4, 0.7),
        'trade_frequency': 'daily',
        'preferred_cap': 'any',
    },
    'earnings': {
        'description': 'Pre-earnings plays with analyst + sentiment support',
        'indicator_weights': {
            'rsi': 0.12, 'macd': 0.10, 'news_sentiment': 0.25,
            'social_buzz': 0.15, 'volume': 0.13, 'insider': 0.15,
            'price_trend': 0.10,
        },
        'buy_threshold': 0.48,
        'sell_threshold': -0.20,
        'hold_period_days': (5, 20),
        'max_positions': (4, 8),
        'risk_tolerance': (0.4, 0.7),
        'trade_frequency': 'twice_weekly',
        'preferred_cap': 'large',
    },
    'sector_rotation': {
        'description': 'Rotates into strongest sectors, out of weakest',
        'indicator_weights': {
            'rsi': 0.15, 'macd': 0.15, 'news_sentiment': 0.15,
            'social_buzz': 0.08, 'volume': 0.15, 'insider': 0.10,
            'price_trend': 0.22,
        },
        'buy_threshold': 0.38,
        'sell_threshold': -0.18,
        'hold_period_days': (15, 45),
        'max_positions': (6, 15),
        'risk_tolerance': (0.3, 0.6),
        'trade_frequency': 'weekly',
        'preferred_cap': 'any',
    },
    'insider_follower': {
        'description': 'Follows insider buying activity with technical confirmation',
        'indicator_weights': {
            'rsi': 0.15, 'macd': 0.12, 'news_sentiment': 0.10,
            'social_buzz': 0.05, 'volume': 0.13, 'insider': 0.35,
            'price_trend': 0.10,
        },
        'buy_threshold': 0.45,
        'sell_threshold': -0.22,
        'hold_period_days': (10, 40),
        'max_positions': (5, 10),
        'risk_tolerance': (0.3, 0.6),
        'trade_frequency': 'twice_weekly',
        'preferred_cap': 'large',
    },
    'dividend_growth': {
        'description': 'Targets dividend stocks near support for income + growth',
        'indicator_weights': {
            'rsi': 0.18, 'macd': 0.08, 'news_sentiment': 0.10,
            'social_buzz': 0.03, 'volume': 0.12, 'insider': 0.14,
            'price_trend': 0.35,
        },
        'buy_threshold': 0.35,
        'sell_threshold': -0.12,
        'hold_period_days': (30, 120),
        'max_positions': (8, 15),
        'risk_tolerance': (0.2, 0.4),
        'trade_frequency': 'weekly',
        'preferred_cap': 'large',
    },
    'social_momentum': {
        'description': 'Trades Reddit/Twitter buzz + volume surge',
        'indicator_weights': {
            'rsi': 0.10, 'macd': 0.10, 'news_sentiment': 0.12,
            'social_buzz': 0.35, 'volume': 0.20, 'insider': 0.03,
            'price_trend': 0.10,
        },
        'buy_threshold': 0.52,
        'sell_threshold': -0.35,
        'hold_period_days': (1, 5),
        'max_positions': (3, 8),
        'risk_tolerance': (0.7, 0.95),
        'trade_frequency': 'daily',
        'preferred_cap': 'any',
    },
    'balanced': {
        'description': 'Equal-weight blend of all signals, conservative sizing',
        'indicator_weights': {
            'rsi': 0.15, 'macd': 0.15, 'news_sentiment': 0.15,
            'social_buzz': 0.12, 'volume': 0.15, 'insider': 0.13,
            'price_trend': 0.15,
        },
        'buy_threshold': 0.40,
        'sell_threshold': -0.20,
        'hold_period_days': (5, 30),
        'max_positions': (6, 12),
        'risk_tolerance': (0.3, 0.6),
        'trade_frequency': 'daily',
        'preferred_cap': 'any',
    },
}


# ── Dirichlet Parameter Sampling ─────────────────────────────────────────────

def generate_strategy_profile(strategy_name, industry='General'):
    """
    Generate a unique strategy profile for a bot by sampling around the
    archetype template using a Dirichlet distribution for indicator weights
    and uniform jitter for thresholds.

    This means 10 archetypes → thousands of distinct behavior profiles.
    """
    template = STRATEGY_TEMPLATES.get(strategy_name, STRATEGY_TEMPLATES['balanced'])

    # Sample indicator weights via Dirichlet distribution
    # Concentration parameter controls how close to template:
    # Higher = more similar, lower = more varied
    concentration = 15.0  # moderate variance around archetype
    base_weights = list(template['indicator_weights'].values())
    weight_keys = list(template['indicator_weights'].keys())

    # Dirichlet requires positive params — scale by concentration
    alpha = [w * concentration + 0.1 for w in base_weights]
    sampled = np.random.dirichlet(alpha)

    indicator_weights = {}
    for key, val in zip(weight_keys, sampled):
        indicator_weights[key] = round(float(val), 4)

    # Sample thresholds with jitter
    buy_thresh = template['buy_threshold'] + random.uniform(-0.08, 0.08)
    sell_thresh = template['sell_threshold'] + random.uniform(-0.08, 0.08)

    # Sample hold period, max positions, risk tolerance from ranges
    hold_min, hold_max = template['hold_period_days']
    hold_period = (
        max(1, hold_min + random.randint(-2, 3)),
        max(hold_min + 2, hold_max + random.randint(-5, 5))
    )

    pos_min, pos_max = template['max_positions']
    max_positions = random.randint(pos_min, pos_max)

    risk_min, risk_max = template['risk_tolerance']
    risk_tolerance = round(random.uniform(risk_min, risk_max), 3)

    # Generate personality quirks (affects human behavior simulation)
    personality = {
        'fomo_factor': round(random.uniform(0.05, 0.60), 3),
        'loss_aversion': round(random.uniform(0.20, 0.80), 3),
        'overconfidence': round(random.uniform(0.10, 0.60), 3),
        'recency_bias': round(random.uniform(0.20, 0.70), 3),
        'patience': round(random.uniform(0.20, 0.80), 3),
    }

    # Strategy-specific personality adjustments
    if strategy_name == 'social_momentum':
        personality['fomo_factor'] = round(random.uniform(0.40, 0.85), 3)
    elif strategy_name == 'value':
        personality['patience'] = round(random.uniform(0.60, 0.95), 3)
        personality['fomo_factor'] = round(random.uniform(0.02, 0.20), 3)
    elif strategy_name == 'dividend_growth':
        personality['patience'] = round(random.uniform(0.70, 0.98), 3)
        personality['loss_aversion'] = round(random.uniform(0.15, 0.40), 3)

    # Assign a "life stage" tag (affects behavior realism)
    life_stages = [
        'college_trader', 'young_professional', 'busy_parent',
        'experienced_investor', 'retired_investor', 'side_hustle',
        'finance_nerd', 'casual_dabbler',
    ]
    # Weight life stages by strategy
    if strategy_name in ('social_momentum', 'news_reactor'):
        life_stage = random.choice(['college_trader', 'young_professional', 'finance_nerd', 'casual_dabbler'])
    elif strategy_name in ('dividend_growth', 'value'):
        life_stage = random.choice(['experienced_investor', 'retired_investor', 'busy_parent'])
    else:
        life_stage = random.choice(life_stages)

    # Determine trading wave preferences based on life stage
    if life_stage in ('college_trader', 'casual_dabbler'):
        preferred_waves = [2, 3, 4]  # Late morning to close
    elif life_stage in ('retired_investor', 'experienced_investor'):
        preferred_waves = [1, 2]     # Early birds
    elif life_stage == 'busy_parent':
        preferred_waves = [1, 4]     # Before/after work
    else:
        preferred_waves = [1, 2, 3, 4]

    # Build attention universe: subset of tickers the bot "watches"
    # Not all humans look at 500 tickers; bots get 20-80 based on style
    from bot_data_hub import UNIVERSE
    universe_size = random.randint(20, 60)
    if strategy_name == 'sector_rotation':
        universe_size = random.randint(40, 80)
    elif strategy_name == 'social_momentum':
        universe_size = random.randint(15, 40)

    # Build from preferred industry + some cross-industry picks
    attention_tickers = list(UNIVERSE.get(industry, UNIVERSE.get('General', [])))
    # Add some random picks from other sectors
    all_sectors = list(UNIVERSE.keys())
    random.shuffle(all_sectors)
    for sector in all_sectors:
        if len(attention_tickers) >= universe_size:
            break
        pool = [t for t in UNIVERSE[sector] if t not in attention_tickers]
        sample_size = min(len(pool), random.randint(3, 10))
        attention_tickers.extend(random.sample(pool, sample_size))

    attention_tickers = list(set(attention_tickers))[:universe_size]

    return {
        'strategy': strategy_name,
        'strategy_description': template['description'],
        'industry': industry,
        'indicator_weights': indicator_weights,
        'buy_threshold': round(buy_thresh, 4),
        'sell_threshold': round(sell_thresh, 4),
        'hold_period_days': hold_period,
        'max_positions': max_positions,
        'risk_tolerance': risk_tolerance,
        'trade_frequency': template['trade_frequency'],
        'preferred_cap': template['preferred_cap'],
        'personality': personality,
        'life_stage': life_stage,
        'preferred_waves': preferred_waves,
        'attention_universe': attention_tickers,
    }


# ── Signal Scoring ───────────────────────────────────────────────────────────

def compute_signal_score(stock_data, profile):
    """
    Compute a composite buy/sell signal score for a stock given a bot's profile.
    Returns a float from roughly -1.0 (strong sell) to +1.0 (strong buy).
    """
    weights = dict(profile['indicator_weights'])  # copy so we can adjust
    strategy = profile['strategy']
    score = 0.0

    # Redistribute social_buzz weight if social data is missing (Finnhub premium)
    if stock_data.get('social_mentions', 0) == 0 and weights.get('social_buzz', 0) > 0:
        orphan = weights.pop('social_buzz')
        other_total = sum(weights.values())
        if other_total > 0:
            for k in weights:
                weights[k] += orphan * (weights[k] / other_total)
        weights['social_buzz'] = 0.0  # keep key but zeroed

    # ── RSI Signal ──
    rsi = stock_data.get('rsi_14')
    if rsi is not None:
        if strategy == 'momentum':
            # Momentum: RSI 50-70 is good (riding trend), >75 is overheated
            if 50 <= rsi <= 70:
                rsi_signal = 0.7
            elif 40 <= rsi < 50:
                rsi_signal = 0.2
            elif rsi > 75:
                rsi_signal = -0.6
            elif rsi < 30:
                rsi_signal = -0.3  # Momentum avoids falling knives
            else:
                rsi_signal = 0.0
        elif strategy == 'value':
            # Value: low RSI = buying opportunity
            if rsi < 30:
                rsi_signal = 1.0
            elif rsi < 40:
                rsi_signal = 0.6
            elif rsi < 50:
                rsi_signal = 0.1
            elif rsi > 70:
                rsi_signal = -0.7
            else:
                rsi_signal = -0.1
        else:
            # Default RSI interpretation
            if rsi < 30:
                rsi_signal = 0.8
            elif rsi < 45:
                rsi_signal = 0.3
            elif rsi < 55:
                rsi_signal = 0.0
            elif rsi < 70:
                rsi_signal = 0.2
            else:
                rsi_signal = -0.5
        score += weights.get('rsi', 0) * rsi_signal

    # ── MACD Signal ──
    macd_cross = stock_data.get('macd_cross', 'none')
    macd_hist = stock_data.get('macd_histogram', 0) or 0
    if macd_cross == 'bullish':
        macd_signal = 1.0
    elif macd_cross == 'bearish':
        macd_signal = -1.0
    elif macd_hist > 0:
        macd_signal = 0.3
    elif macd_hist < 0:
        macd_signal = -0.3
    else:
        macd_signal = 0.0
    score += weights.get('macd', 0) * macd_signal

    # ── News Sentiment Signal ──
    news_sent = stock_data.get('news_sentiment', 0)
    news_buzz = stock_data.get('news_buzz', 'low')
    # Amplify if high buzz
    buzz_multiplier = 1.5 if news_buzz == 'high' else 1.0 if news_buzz == 'medium' else 0.6
    news_signal = min(1.0, max(-1.0, news_sent * 2.5 * buzz_multiplier))
    score += weights.get('news_sentiment', 0) * news_signal

    # ── Social Buzz Signal ──
    social_mentions = stock_data.get('social_mentions', 0)
    social_ratio = stock_data.get('social_ratio', 0.5)
    if social_mentions > 50:
        social_signal = (social_ratio - 0.5) * 2  # Scale 0-1 → -1 to 1
        if social_mentions > 200:
            social_signal *= 1.3  # Very buzzy = amplified
    elif social_mentions > 10:
        social_signal = (social_ratio - 0.5) * 1.2
    else:
        social_signal = 0.0
    score += weights.get('social_buzz', 0) * min(1.0, max(-1.0, social_signal))

    # ── Volume Signal ──
    vol_ratio = stock_data.get('volume_ratio', 1.0)
    if vol_ratio > 2.0:
        volume_signal = 0.8  # Very unusual volume = something happening
    elif vol_ratio > 1.3:
        volume_signal = 0.4  # Above average
    elif vol_ratio < 0.5:
        volume_signal = -0.3  # Very low volume = no interest
    else:
        volume_signal = 0.0
    score += weights.get('volume', 0) * volume_signal

    # ── Insider Signal ──
    insider_net = stock_data.get('insider_net', 'neutral')
    if insider_net == 'buying':
        insider_signal = 0.7
    elif insider_net == 'selling':
        insider_signal = -0.5
    else:
        insider_signal = 0.0
    # Analyst action bonus
    analyst_action = stock_data.get('analyst_action', 'none')
    if analyst_action in ('up', 'upgrade'):
        insider_signal += 0.3
    elif analyst_action in ('down', 'downgrade'):
        insider_signal -= 0.3
    score += weights.get('insider', 0) * min(1.0, max(-1.0, insider_signal))

    # ── Price Trend Signal ──
    price_vs_sma20 = stock_data.get('price_vs_sma20', 'unknown')
    price_vs_sma50 = stock_data.get('price_vs_sma50', 'unknown')
    bb_pos = stock_data.get('bb_position')
    adx = stock_data.get('adx', 25)

    trend_signal = 0.0
    if strategy in ('momentum', 'social_momentum'):
        # Momentum loves above-SMA + strong trend
        if price_vs_sma20 == 'above':
            trend_signal += 0.3
        if price_vs_sma50 == 'above':
            trend_signal += 0.2
        if adx and adx > 30:
            trend_signal += 0.3  # Strong trend
    elif strategy in ('value', 'swing'):
        # Value/swing likes below-SMA (potential reversal)
        if price_vs_sma20 == 'below':
            trend_signal += 0.2
        if bb_pos is not None and bb_pos < 0.2:
            trend_signal += 0.5  # Near lower Bollinger = potential bounce
        elif bb_pos is not None and bb_pos > 0.9:
            trend_signal -= 0.5  # Near upper = potential pullback
    else:
        if price_vs_sma20 == 'above':
            trend_signal += 0.15
        if price_vs_sma50 == 'above':
            trend_signal += 0.10

    score += weights.get('price_trend', 0) * min(1.0, max(-1.0, trend_signal))

    # ── Top Mover Bonus ──
    mover = stock_data.get('mover_status', 'normal')
    if mover == 'top_gainer' and strategy in ('momentum', 'social_momentum', 'news_reactor'):
        score += 0.08  # Small bonus for momentum chasers
    elif mover == 'top_loser' and strategy == 'value':
        score += 0.05  # Small bonus for contrarians

    return round(score, 4)


def generate_trade_decisions(bot_profile, market_hub, current_holdings=None):
    """
    Generate buy/sell decisions for a bot given its profile and market data.

    Args:
        bot_profile: dict with strategy, indicator_weights, thresholds, etc.
        market_hub: MarketDataHub instance with current data
        current_holdings: list of dicts [{ticker, quantity, purchase_price}, ...]

    Returns:
        list of {action: 'buy'|'sell', ticker, score, reason}
    """
    current_holdings = current_holdings or []
    held_tickers = {h['ticker'] for h in current_holdings}
    decisions = []

    attention_universe = bot_profile.get('attention_universe', [])
    buy_threshold = bot_profile['buy_threshold']
    sell_threshold = bot_profile['sell_threshold']
    max_positions = bot_profile['max_positions']
    current_position_count = len(held_tickers)

    # Score all stocks in attention universe
    scored_stocks = []
    for ticker in attention_universe:
        stock_data = market_hub.get_stock_data(ticker)
        if not stock_data:
            continue

        signal = compute_signal_score(stock_data, bot_profile)
        scored_stocks.append({
            'ticker': ticker,
            'score': signal,
            'price': stock_data.get('price', 0),
            'data': stock_data,
        })

    # ── SELL decisions: held stocks below sell threshold ──
    for holding in current_holdings:
        ticker = holding['ticker']
        stock_data = market_hub.get_stock_data(ticker)
        if not stock_data:
            continue

        signal = compute_signal_score(stock_data, bot_profile)
        price = stock_data.get('price', 0)
        purchase_price = holding.get('purchase_price', price)

        # Calculate unrealized P&L
        if purchase_price > 0:
            pnl_pct = (price - purchase_price) / purchase_price
        else:
            pnl_pct = 0

        should_sell = False
        reason = ''

        # Signal-based sell
        if signal < sell_threshold:
            should_sell = True
            reason = f"Signal {signal:.3f} below threshold {sell_threshold:.3f}"

        # Stop-loss (based on risk tolerance — lower risk = tighter stop)
        stop_loss = -0.03 - (1 - bot_profile['risk_tolerance']) * 0.12
        if pnl_pct < stop_loss:
            should_sell = True
            reason = f"Stop-loss triggered: {pnl_pct:.1%} < {stop_loss:.1%}"

        # Take-profit for short-term strategies
        if bot_profile['strategy'] in ('swing', 'social_momentum', 'news_reactor'):
            take_profit = 0.05 + bot_profile['risk_tolerance'] * 0.10
            if pnl_pct > take_profit:
                should_sell = True
                reason = f"Take-profit: {pnl_pct:.1%} > {take_profit:.1%}"

        if should_sell:
            decisions.append({
                'action': 'sell',
                'ticker': ticker,
                'score': signal,
                'reason': reason,
                'price': price,
                'pnl_pct': pnl_pct,
            })

    # ── BUY decisions: top-scored stocks above buy threshold ──
    open_slots = max_positions - current_position_count + len([d for d in decisions if d['action'] == 'sell'])

    # Sort by score descending
    buy_candidates = [s for s in scored_stocks
                      if s['score'] > buy_threshold
                      and s['ticker'] not in held_tickers
                      and s['price'] > 0]
    buy_candidates.sort(key=lambda x: x['score'], reverse=True)

    # Pick top candidates up to open slots
    for candidate in buy_candidates[:max(0, open_slots)]:
        decisions.append({
            'action': 'buy',
            'ticker': candidate['ticker'],
            'score': candidate['score'],
            'reason': f"Signal {candidate['score']:.3f} above threshold {buy_threshold:.3f}",
            'price': candidate['price'],
        })

    return decisions


def pick_random_strategy():
    """Pick a random strategy weighted by intended distribution."""
    strategies = list(STRATEGY_TEMPLATES.keys())
    # Distribution: more balanced/momentum, fewer niche
    weights = [15, 12, 10, 12, 8, 8, 7, 8, 10, 10]
    return random.choices(strategies, weights=weights, k=1)[0]
