"""
Bot Human Behavior Simulation
===============================
Applies realistic human-like noise and biases to bot trading decisions.
Simulates FOMO, loss aversion, overconfidence, recency bias, timing
variation, skip days, and partial fills.

Each bot's personality quirks (from its strategy profile) control how
strongly each bias affects their behavior.
"""

import random
import math
import logging
from datetime import datetime, timedelta

logger = logging.getLogger('bot_behaviors')


# ── Trading Wave Scheduling ──────────────────────────────────────────────────

TRADING_WAVES = {
    1: {'name': 'open', 'center_hour': 9, 'center_min': 45, 'jitter_min': 30},
    2: {'name': 'mid_morning', 'center_hour': 10, 'center_min': 45, 'jitter_min': 35},
    3: {'name': 'afternoon', 'center_hour': 13, 'center_min': 15, 'jitter_min': 40},
    4: {'name': 'close', 'center_hour': 15, 'center_min': 30, 'jitter_min': 25},
}


def should_trade_today(bot_profile):
    """
    Decide if a bot trades today based on trade_frequency and personality.
    Returns True/False.
    """
    frequency = bot_profile.get('trade_frequency', 'daily')
    patience = bot_profile.get('personality', {}).get('patience', 0.5)

    if frequency == 'daily':
        # Daily traders still skip ~10-20% of days (human laziness/distraction)
        skip_chance = 0.10 + patience * 0.10
        return random.random() > skip_chance

    elif frequency == 'twice_weekly':
        # Trade ~2-3 days per week
        day_of_week = datetime.utcnow().weekday()
        # More likely on Mon/Wed/Fri
        trade_days = {0: 0.7, 1: 0.3, 2: 0.6, 3: 0.3, 4: 0.5}
        chance = trade_days.get(day_of_week, 0.3)
        return random.random() < chance

    elif frequency == 'weekly':
        # Trade ~1 day per week, usually Mon or Fri
        day_of_week = datetime.utcnow().weekday()
        trade_days = {0: 0.5, 1: 0.1, 2: 0.1, 3: 0.1, 4: 0.4}
        chance = trade_days.get(day_of_week, 0.1)
        return random.random() < chance

    return random.random() > 0.15  # Default: 85% chance


def get_trade_wave(bot_profile):
    """
    Determine which trading wave a bot belongs to today.
    Returns wave number (1-4) based on preferred_waves and personality.
    """
    preferred = bot_profile.get('preferred_waves', [1, 2, 3, 4])
    if not preferred:
        preferred = [1, 2, 3, 4]

    # Usually trade in preferred wave, but occasionally drift
    if random.random() < 0.85:
        return random.choice(preferred)
    else:
        return random.randint(1, 4)


def get_wave_delay_seconds(wave_number):
    """
    Get the delay in seconds for executing within a wave.
    Adds human-like jitter around the wave center time.
    """
    wave = TRADING_WAVES.get(wave_number, TRADING_WAVES[1])
    jitter_seconds = random.gauss(0, wave['jitter_min'] * 30)  # Gaussian jitter
    return max(0, int(jitter_seconds))


# ── Decision Modification (Human Biases) ─────────────────────────────────────

def apply_human_biases(decisions, bot_profile, recent_trades=None):
    """
    Apply human psychological biases to raw trade decisions.

    Args:
        decisions: list of {action, ticker, score, reason, price, ...}
        bot_profile: bot's strategy profile with personality quirks
        recent_trades: list of recent trades [{type, ticker, pnl, ...}]

    Returns:
        Modified decisions list (some may be removed, added, or modified)
    """
    recent_trades = recent_trades or []
    personality = bot_profile.get('personality', {})
    modified = []

    # Count recent win/loss streak
    win_streak = _count_streak(recent_trades, 'win')
    loss_streak = _count_streak(recent_trades, 'loss')

    for decision in decisions:
        action = decision['action']
        ticker = decision['ticker']
        score = decision['score']

        # ── Skip chance (human distraction/laziness) ──
        skip_base = 0.08  # 8% base chance of not following through
        if personality.get('patience', 0.5) < 0.3:
            skip_base += 0.10  # Impatient bots skip more
        if random.random() < skip_base:
            logger.debug(f"Bot skipped {action} {ticker} (distraction)")
            continue

        # ── FOMO: Chase hot stocks even if not in plan ──
        # (This is applied at the orchestrator level for stocks not in decisions)

        # ── Overconfidence after winning streak ──
        if win_streak >= 3 and personality.get('overconfidence', 0.3) > 0.4:
            if action == 'buy':
                # Increase conviction — may result in larger position size later
                decision['confidence_boost'] = 1.0 + personality['overconfidence'] * 0.5
                decision['reason'] += f" | Overconfident (win streak: {win_streak})"

        # ── Loss aversion: panic sell faster after losses ──
        if loss_streak >= 2 and personality.get('loss_aversion', 0.5) > 0.4:
            if action == 'sell':
                # More likely to follow through on sells
                decision['urgency'] = 'high'
                decision['reason'] += f" | Loss aversion (loss streak: {loss_streak})"
            elif action == 'buy':
                # Less likely to buy after losses
                if random.random() < personality['loss_aversion'] * 0.4:
                    logger.debug(f"Bot skipped buy {ticker} (loss-averse after losses)")
                    continue

        # ── Recency bias: weight recent performance ──
        recency = personality.get('recency_bias', 0.4)
        if recent_trades and recency > 0.5:
            last_trade = recent_trades[-1]
            if last_trade.get('pnl', 0) > 0 and action == 'buy':
                # Recent win → more bullish
                decision['score'] = score * (1 + recency * 0.15)
            elif last_trade.get('pnl', 0) < 0 and action == 'buy':
                # Recent loss → more cautious
                if random.random() < recency * 0.3:
                    logger.debug(f"Bot skipped buy {ticker} (recency bias after loss)")
                    continue

        modified.append(decision)

    return modified


def apply_fomo_trades(bot_profile, market_hub, current_decisions):
    """
    Add FOMO-driven trades: buy stocks that are surging with high social buzz
    even if they weren't in the bot's normal attention universe.
    """
    fomo = bot_profile.get('personality', {}).get('fomo_factor', 0.2)
    if fomo < 0.2 or random.random() > fomo:
        return []  # Low-FOMO bots don't chase

    fomo_candidates = []
    top_movers = market_hub.top_movers.get('gainers', [])

    already_buying = {d['ticker'] for d in current_decisions if d['action'] == 'buy'}

    for mover in top_movers[:10]:
        ticker = mover['ticker']
        if ticker in already_buying:
            continue

        stock_data = market_hub.get_stock_data(ticker)
        if not stock_data:
            continue

        # FOMO trigger: stock is up big + high social/volume
        change_pct = mover.get('change_pct', 0)
        social_mentions = stock_data.get('social_mentions', 0)
        volume_ratio = stock_data.get('volume_ratio', 1.0)

        fomo_score = 0
        if change_pct > 5:
            fomo_score += 0.3
        if change_pct > 10:
            fomo_score += 0.2
        if social_mentions > 50:
            fomo_score += 0.2
        if volume_ratio > 2.0:
            fomo_score += 0.2

        if fomo_score > 0.3 and random.random() < fomo * fomo_score:
            fomo_candidates.append({
                'action': 'buy',
                'ticker': ticker,
                'score': fomo_score,
                'reason': f"FOMO: +{change_pct:.1f}% today, {social_mentions} social mentions",
                'price': stock_data.get('price', mover.get('price', 0)),
                'is_fomo': True,
            })

    # Max 1-2 FOMO trades per day
    return fomo_candidates[:random.randint(0, 2)]


# ── Position Sizing ──────────────────────────────────────────────────────────

def calculate_position_size(decision, bot_profile, portfolio_value=100000):
    """
    Calculate the number of shares to buy/sell with human-like noise.

    Args:
        decision: trade decision dict
        bot_profile: bot's strategy profile
        portfolio_value: estimated total portfolio value

    Returns:
        int: number of shares
    """
    price = decision.get('price', 100)
    if price <= 0:
        return 1

    risk_tolerance = bot_profile.get('risk_tolerance', 0.5)
    max_positions = bot_profile.get('max_positions', 8)

    # Base position: allocate roughly equal weight per position
    base_allocation = portfolio_value / max_positions
    # Risk tolerance adjusts: higher risk = larger individual positions
    allocation = base_allocation * (0.6 + risk_tolerance * 0.8)

    # Confidence boost from overconfidence
    confidence = decision.get('confidence_boost', 1.0)
    allocation *= confidence

    # Calculate ideal quantity
    ideal_qty = max(1, int(allocation / price))

    # ── Human noise: vary quantity ±15% ──
    noise = random.uniform(0.85, 1.15)
    qty = max(1, int(ideal_qty * noise))

    # For sells, don't sell everything (partial sells feel more human)
    if decision.get('action') == 'sell':
        # Sell 30-80% of position
        sell_fraction = random.uniform(0.30, 0.80)
        if decision.get('urgency') == 'high':
            sell_fraction = random.uniform(0.60, 1.00)  # Panic sells are larger
        qty = max(1, int(qty * sell_fraction))

    # Round to "human" numbers: prefer multiples of 5 or 10
    if qty > 20:
        qty = round(qty / 5) * 5
    elif qty > 10:
        qty = round(qty / 2) * 2

    return max(1, qty)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _count_streak(recent_trades, streak_type):
    """Count consecutive wins or losses from most recent."""
    if not recent_trades:
        return 0
    count = 0
    for trade in reversed(recent_trades):
        pnl = trade.get('pnl', 0)
        if streak_type == 'win' and pnl > 0:
            count += 1
        elif streak_type == 'loss' and pnl < 0:
            count += 1
        else:
            break
    return count


def is_market_hours():
    """Check if US market is currently open (rough check)."""
    now = datetime.utcnow()
    # Market hours: 9:30 AM - 4:00 PM ET (14:30 - 21:00 UTC)
    # Rough check — doesn't account for holidays
    hour_utc = now.hour
    weekday = now.weekday()

    if weekday >= 5:  # Weekend
        return False
    if hour_utc < 14 or hour_utc >= 21:  # Before 9:30 AM or after 4 PM ET
        return False
    if hour_utc == 14 and now.minute < 30:  # Before 9:30 AM ET
        return False
    return True


def add_trade_delay():
    """Add a human-like delay between trade executions."""
    delay = random.uniform(0.3, 2.5)
    if random.random() < 0.1:
        # 10% chance of a longer pause (checking phone, getting coffee)
        delay += random.uniform(3, 8)
    return delay
