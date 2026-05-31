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

def compute_signal_components(stock_data, profile):
    """
    Compute the per-category weighted contributions to the composite signal score.

    Returns a dict mapping {component_name: weighted_contribution}, where each
    contribution is `weight × signal_value` (the same term that gets summed by
    `compute_signal_score`). Use this to attribute a trade decision to its
    dominant data source (e.g., RSI, news, insider) for UX surfaces like the
    admin Recent Trades 'Source' column.

    Component names: 'rsi', 'macd', 'news', 'social', 'volume', 'insider',
    'analyst', 'trend', 'mover'. Missing/unavailable signals contribute 0.
    """
    weights = dict(profile['indicator_weights'])  # copy so we can adjust
    strategy = profile['strategy']
    components = {
        'rsi': 0.0, 'macd': 0.0, 'news': 0.0, 'social': 0.0,
        'volume': 0.0, 'insider': 0.0, 'analyst': 0.0, 'trend': 0.0, 'mover': 0.0,
    }

    # ── Redistribute weight from data legs that have NO data for this ticker ──
    # On the free Finnhub tier the social / analyst / insider endpoints return
    # nothing (premium-gated or HTTP 403), and any given ticker may simply have
    # no AlphaVantage news coverage. Leaving that weight in place permanently
    # caps the composite score below the bot's buy_threshold — e.g. bot 11
    # carries 57% of its weight on social_buzz, so with social dead it could
    # never clear a 0.52 buy threshold. That starves BUY decisions while
    # price-based SELLs (stop-loss / take-profit) keep firing, which is the
    # cash-accumulation bug. Reallocating each dead leg's weight to the live
    # signals restores a meaningful [-1, 1] score range so thresholds stay
    # reachable, and keeps source attribution honest (a leg with no data can't
    # be flagged as the 'dominant' driver).
    #
    # Per-ticker detection (more accurate than a global data_quality flag):
    #   - social_buzz   dead when social_mentions == 0
    #   - news_sentiment dead when article_count == 0 (distinct from neutral news)
    #   - insider       dead when neither insider nor analyst data is present
    #                   (get_stock_data omits insider_buys / sets analyst_action
    #                    = 'none' when Finnhub returned nothing). This single
    #                    'insider' weight backs BOTH the insider and analyst
    #                    components below, so zeroing it kills both correctly.
    dead_keys = []
    if stock_data.get('social_mentions', 0) == 0:
        dead_keys.append('social_buzz')
    if stock_data.get('article_count', 0) == 0:
        dead_keys.append('news_sentiment')
    if 'insider_buys' not in stock_data and stock_data.get('analyst_action', 'none') == 'none':
        dead_keys.append('insider')

    orphan = sum(weights.get(k, 0.0) for k in dead_keys)
    if orphan > 0:
        live = {k: w for k, w in weights.items() if k not in dead_keys and w > 0}
        live_total = sum(live.values())
        if live_total > 0:
            for k in live:
                weights[k] += orphan * (weights[k] / live_total)
        for k in dead_keys:
            weights[k] = 0.0  # keep key but zeroed so attribution skips it

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
        components['rsi'] = weights.get('rsi', 0) * rsi_signal

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
    components['macd'] = weights.get('macd', 0) * macd_signal

    # ── News Sentiment Signal ──
    news_sent = stock_data.get('news_sentiment', 0)
    news_buzz = stock_data.get('news_buzz', 'low')
    # Amplify if high buzz
    buzz_multiplier = 1.5 if news_buzz == 'high' else 1.0 if news_buzz == 'medium' else 0.6
    news_signal = min(1.0, max(-1.0, news_sent * 2.5 * buzz_multiplier))
    components['news'] = weights.get('news_sentiment', 0) * news_signal

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
    components['social'] = weights.get('social_buzz', 0) * min(1.0, max(-1.0, social_signal))

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
    components['volume'] = weights.get('volume', 0) * volume_signal

    # ── Insider Signal ──
    # Insider transactions (Finnhub) and analyst recommendations (Finnhub) are
    # reported as SEPARATE components so source attribution is honest — the
    # admin panel shows "Finnhub Insider informed N trades" vs "Finnhub Analyst
    # informed M trades" independently. They share the single 'insider'
    # indicator weight, and because the old combined signal's clamp never bound
    # (max 0.7+0.3=1.0, min -0.5-0.3=-0.8), splitting the sum into two weighted
    # terms leaves the composite score identical — this is attribution-only.
    insider_net = stock_data.get('insider_net', 'neutral')
    if insider_net == 'buying':
        insider_signal = 0.7
    elif insider_net == 'selling':
        insider_signal = -0.5
    else:
        insider_signal = 0.0
    components['insider'] = weights.get('insider', 0) * insider_signal

    # ── Analyst Recommendation Signal (shares the insider weight) ──
    analyst_action = stock_data.get('analyst_action', 'none')
    if analyst_action in ('up', 'upgrade'):
        analyst_signal = 0.3
    elif analyst_action in ('down', 'downgrade'):
        analyst_signal = -0.3
    else:
        analyst_signal = 0.0
    components['analyst'] = weights.get('insider', 0) * analyst_signal

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

    components['trend'] = weights.get('price_trend', 0) * min(1.0, max(-1.0, trend_signal))

    # ── Top Mover Bonus (unweighted flat addend) ──
    mover = stock_data.get('mover_status', 'normal')
    if mover == 'top_gainer' and strategy in ('momentum', 'social_momentum', 'news_reactor'):
        components['mover'] = 0.08  # Small bonus for momentum chasers
    elif mover == 'top_loser' and strategy == 'value':
        components['mover'] = 0.05  # Small bonus for contrarians

    return components


def compute_signal_score(stock_data, profile):
    """
    Compute a composite buy/sell signal score for a stock given a bot's profile.
    Returns a float from roughly -1.0 (strong sell) to +1.0 (strong buy).

    Implemented as the sum of `compute_signal_components` so the breakdown
    used for source attribution (admin Recent Trades column) is guaranteed
    to be consistent with the score driving the decision.
    """
    components = compute_signal_components(stock_data, profile)
    return round(sum(components.values()), 4)


def dominant_signal(stock_data, profile):
    """
    Identify which signal category contributed the largest absolute amount
    to the composite score. Used to label trades in the admin Source column
    (e.g., 'rsi', 'news', 'insider').

    Returns the component name with the largest |contribution|, or 'mixed'
    if no component dominates (all contributions essentially zero).
    """
    components = compute_signal_components(stock_data, profile)
    if not components:
        return 'mixed'
    name, value = max(components.items(), key=lambda kv: abs(kv[1]))
    if abs(value) < 0.001:
        return 'mixed'
    return name


def generate_trade_decisions(bot_profile, market_hub, current_holdings=None, cash_available=0.0):
    """
    Generate buy/sell decisions for a bot given its profile and market data.

    Args:
        bot_profile: dict with strategy, indicator_weights, thresholds, etc.
        market_hub: MarketDataHub instance with current data
        current_holdings: list of dicts [{ticker, quantity, purchase_price}, ...]
        cash_available: bot's uninvested cash_proceeds. When a bot has drifted
            to a high cash fraction, an idle-cash redeployment rule deploys the
            excess into its best current ideas (see below) so it stays invested.

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
            'dominant': dominant_signal(stock_data, bot_profile),
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
        # `signal_tag` is a compact, machine-readable label used by the admin
        # Recent Trades 'Source' column to attribute the decision to its
        # actual driver. For signal-driven sells we use the dominant data
        # source; for risk-management sells we use a dedicated tag so the
        # admin can distinguish a stop-loss from a fundamentals-driven exit.
        signal_tag = dominant_signal(stock_data, bot_profile)

        # Signal-based sell
        if signal < sell_threshold:
            should_sell = True
            reason = f"Signal {signal:.3f} below threshold {sell_threshold:.3f}"

        # Stop-loss (based on risk tolerance — lower risk = tighter stop)
        # Stop-loss takes precedence over signal-based sells in `reason` AND `signal_tag`.
        stop_loss = -0.03 - (1 - bot_profile['risk_tolerance']) * 0.12
        if pnl_pct < stop_loss:
            should_sell = True
            reason = f"Stop-loss triggered: {pnl_pct:.1%} < {stop_loss:.1%}"
            signal_tag = 'stoploss'

        # Take-profit for short-term strategies (overrides signal_tag)
        if bot_profile['strategy'] in ('swing', 'social_momentum', 'news_reactor'):
            take_profit = 0.05 + bot_profile['risk_tolerance'] * 0.10
            if pnl_pct > take_profit:
                should_sell = True
                reason = f"Take-profit: {pnl_pct:.1%} > {take_profit:.1%}"
                signal_tag = 'takeprofit'

        if should_sell:
            decisions.append({
                'action': 'sell',
                'ticker': ticker,
                'score': signal,
                'reason': reason,
                'price': price,
                'pnl_pct': pnl_pct,
                'signal_tag': signal_tag,
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
            'signal_tag': candidate.get('dominant', 'mixed'),
        })

    # ── Idle-cash redeployment ────────────────────────────────────────────────
    # The cash-accumulation bug: price-based exits (stop-loss / take-profit)
    # kept selling, but signal-driven BUYs were starved (high thresholds + dead
    # premium data legs), so sale proceeds piled up as cash indefinitely — some
    # bots drifted to 80-95% cash and their charts went flat. This rule is the
    # safety net: when a bot's cash exceeds a ceiling, deploy the excess into its
    # best current ideas (relaxing buy_threshold — "put my idle cash to work")
    # so it stays invested even on waves where nothing clears the threshold.
    #
    # To stay human-like and avoid one giant all-in wave, we deploy at most a
    # few equal-weight positions per wave; the bot converges toward the target
    # cash level over a handful of waves.
    REDEPLOY_TRIGGER_FRAC = 0.15   # begin redeploying once cash exceeds 15% of NAV
    REDEPLOY_TARGET_FRAC = 0.08    # ... deploying down toward ~8% cash
    MAX_REDEPLOY_PER_WAVE = 3

    if cash_available and cash_available > 0:
        # Mark-to-market each held position (hub price, purchase_price fallback)
        # so we know both total stock value (for NAV) and each position's
        # CURRENT size (needed for top-up sizing below).
        held_mv = {}
        for h in current_holdings:
            sd = market_hub.get_stock_data(h['ticker'])
            px = (sd.get('price') if sd else 0) or h.get('purchase_price', 0) or 0
            held_mv[h['ticker']] = held_mv.get(h['ticker'], 0.0) + (h.get('quantity', 0) or 0) * px
        stock_value = sum(held_mv.values())
        nav = stock_value + cash_available
        per_name = nav / max(1, max_positions)  # equal-weight target size

        already_buying = {d['ticker'] for d in decisions if d['action'] == 'buy'}
        selling_now = {d['ticker'] for d in decisions if d['action'] == 'sell'}
        remaining_slots = max(0, open_slots - len(already_buying))

        # Deploy the cash above target, but reserve ~per_name for each
        # signal-driven buy already queued this wave (the executor sizes those
        # off allocation) so the two paths together don't over-deploy into new
        # capital and inflate max_cash_deployed.
        deployable = (cash_available - REDEPLOY_TARGET_FRAC * nav
                      - per_name * len(already_buying))

        # NOTE: no `remaining_slots > 0` gate here. The original rule only
        # opened NEW positions, so a bot sitting AT max_positions with tiny,
        # under-weight holdings (the 'stranded cash' bots — full slot count but
        # only ~40-50% invested, stuck at 50-70% cash) could never redeploy:
        # every slot was taken. Top-ups (below) need no slot, so they keep the
        # bot deploying toward equal-weight even when its book is 'full'.
        if (nav > 0
                and cash_available > REDEPLOY_TRIGGER_FRAC * nav
                and deployable > 0):
            # Two ways to put idle cash to work, both requiring a valid price
            # and a non-negative score (never redeploy into a sell signal):
            #   • OPEN a new position    — consumes a free slot (respects max_positions)
            #   • TOP UP an under-weight existing holding toward per_name — no slot needed
            # The executor's BUY path (/admin/bot/execute-trade) already does a
            # weighted-average cost-basis update when the position exists.
            redeploy_targets = []  # list of (scored_stock, kind, gap_dollars)
            for s in scored_stocks:
                if s['price'] <= 0 or s['score'] < 0 or s['ticker'] in already_buying:
                    continue
                tk = s['ticker']
                if tk in held_tickers:
                    if tk in selling_now:
                        continue  # don't top up a position we're trimming this wave
                    gap = per_name - held_mv.get(tk, 0.0)
                    if gap > 1:  # only top up genuinely under-weight positions
                        redeploy_targets.append((s, 'topup', gap))
                else:
                    redeploy_targets.append((s, 'new', per_name))
            redeploy_targets.sort(key=lambda x: x[0]['score'], reverse=True)

            remaining_cash = deployable
            slots_left = remaining_slots
            buys_made = 0
            for s, kind, gap in redeploy_targets:
                if buys_made >= MAX_REDEPLOY_PER_WAVE or remaining_cash < 1:
                    break
                if kind == 'new':
                    if slots_left <= 0:
                        continue  # out of slots — skip new opens, keep scanning for top-ups
                    slots_left -= 1
                notional = min(per_name, gap, remaining_cash)
                if notional < 1:
                    continue
                verb = 'open' if kind == 'new' else 'add to'
                decisions.append({
                    'action': 'buy',
                    'ticker': s['ticker'],
                    'score': s['score'],
                    'reason': (f"Idle-cash redeploy ({verb}): cash {cash_available / nav:.0%} of NAV "
                               f"> {REDEPLOY_TRIGGER_FRAC:.0%} ceiling; deploying ${notional:,.0f}"),
                    'price': s['price'],
                    'signal_tag': 'redeploy',
                    'target_notional': round(notional, 2),
                })
                remaining_cash -= notional
                buys_made += 1

    return decisions


def pick_random_strategy():
    """Pick a random strategy weighted by intended distribution."""
    strategies = list(STRATEGY_TEMPLATES.keys())
    # Distribution: more balanced/momentum, fewer niche
    weights = [15, 12, 10, 12, 8, 8, 7, 8, 10, 10]
    return random.choices(strategies, weights=weights, k=1)[0]
