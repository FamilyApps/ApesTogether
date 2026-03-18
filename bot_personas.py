"""
Bot Persona Generator
======================
Generates realistic bot identities with names, industries, and strategy
profiles. Each bot gets a unique combination of strategy archetype,
Dirichlet-sampled indicator weights, personality quirks, life stage,
and attention universe.
"""

import random
import logging

logger = logging.getLogger('bot_personas')


# ── Name Generation ──────────────────────────────────────────────────────────
# Mix of realistic-sounding usernames across different styles

FIRST_PARTS = [
    # Animal-themed
    'bull', 'bear', 'hawk', 'wolf', 'fox', 'eagle', 'lion', 'shark',
    'falcon', 'raven', 'orca', 'phoenix', 'lynx', 'cobra', 'panther',
    'raptor', 'condor', 'viper', 'puma', 'tiger',
    # Trait-themed
    'swift', 'bold', 'clever', 'calm', 'sharp', 'bright', 'keen',
    'steady', 'wise', 'quick', 'prime', 'deep', 'iron', 'core',
    'alpha', 'apex', 'zen', 'max', 'true', 'pure',
    # Finance-themed
    'profit', 'yield', 'gains', 'divi', 'chart', 'candle', 'green',
    'stack', 'fund', 'trade', 'cash', 'hedge', 'margin', 'equity',
    # Tech-bro themed
    'cyber', 'neo', 'data', 'pixel', 'quantum', 'node', 'byte',
    'crypto', 'algo', 'sigma', 'delta', 'gamma',
]

SECOND_PARTS = [
    'trader', 'investor', 'capital', 'wealth', 'plays', 'picks',
    'street', 'market', 'returns', 'portfolio', 'finance', 'stocks',
    'runner', 'hunter', 'seeker', 'master', 'king', 'pro',
    'genius', 'wizard', 'monk', 'sage', 'guru', 'chief',
    'whale', 'ape', 'diamond', 'rocket', 'moon', 'titan',
]

# Some realistic "real name" style usernames
REAL_NAMES = [
    'mike_trades', 'sarah_invests', 'jt_capital', 'alex_markets',
    'chris_gains', 'sam_stocks', 'jordan_plays', 'taylor_picks',
    'casey_wealth', 'riley_returns', 'morgan_port', 'drew_finance',
    'pat_trader', 'jamie_bull', 'quinn_alpha', 'avery_hedge',
    'logan_yield', 'reese_gains', 'blake_capital', 'skyler_trades',
    'parker_invest', 'cameron_stocks', 'dakota_gains', 'emery_wealth',
    'finley_trades', 'harley_picks', 'kendall_port', 'lennox_alpha',
    'marley_bull', 'oakley_cap', 'peyton_trade', 'rowan_invest',
    'sage_returns', 'tatum_plays', 'val_stocks', 'wren_capital',
]


def generate_username():
    """
    Generate a unique, human-looking username.
    Mixes several patterns to avoid uniformity.
    """
    pattern = random.choices(
        ['compound', 'real_name', 'simple_num', 'initials'],
        weights=[40, 25, 25, 10],
        k=1
    )[0]

    if pattern == 'compound':
        first = random.choice(FIRST_PARTS)
        second = random.choice(SECOND_PARTS)
        sep = random.choice(['-', '_', '', '.'])
        num = random.choice(['', str(random.randint(1, 99)),
                             str(random.randint(2020, 2026))])
        variants = [
            f"{first}{sep}{second}{num}",
            f"{second}{sep}{first}{num}",
            f"{first}{num}{sep}{second}",
        ]
        return random.choice(variants)

    elif pattern == 'real_name':
        base = random.choice(REAL_NAMES)
        suffix = random.choice(['', str(random.randint(1, 99)),
                                str(random.randint(100, 999))])
        return f"{base}{suffix}"

    elif pattern == 'simple_num':
        first = random.choice(FIRST_PARTS)
        num = random.randint(1, 9999)
        return f"{first}{num}"

    else:  # initials
        letters = ''.join(random.choices('abcdefghijklmnopqrstuvwxyz', k=2))
        suffix = random.choice(['_trades', '_capital', '_invest', '_stocks',
                                '_picks', '_wealth', '_port'])
        num = random.choice(['', str(random.randint(1, 99))])
        return f"{letters}{suffix}{num}"


def generate_email(username):
    """Generate a plausible email for a bot."""
    clean = username.replace('-', '.').replace('_', '.').replace('..', '.')
    return f"{clean}@apestogether.ai"


# ── Industry Distribution ───────────────────────────────────────────────────

INDUSTRY_WEIGHTS = {
    'Technology': 20,
    'Healthcare': 12,
    'Finance': 14,
    'Energy': 10,
    'Consumer': 14,
    'Industrial': 8,
    'Real Estate': 8,
    'ETF': 10,
    'General': 4,
}

def pick_industry():
    """Pick a random industry weighted by intended distribution."""
    industries = list(INDUSTRY_WEIGHTS.keys())
    weights = list(INDUSTRY_WEIGHTS.values())
    return random.choices(industries, weights=weights, k=1)[0]


# ── Subscriber Count Distribution ───────────────────────────────────────────

def generate_subscriber_count():
    """
    Generate a realistic initial subscriber count.
    Weighted toward low counts with occasional higher numbers.
    """
    return random.choices(
        [1, 2, 3, 4, 5, 6, 7, 8, 10, 12, 15, 20, 25, 30],
        weights=[20, 18, 14, 10, 8, 7, 5, 4, 3, 3, 3, 2, 2, 1],
        k=1
    )[0]


# ── Full Persona Generation ─────────────────────────────────────────────────

def generate_bot_persona(strategy_name=None, industry=None):
    """
    Generate a complete bot persona: identity + strategy profile.

    Args:
        strategy_name: Optional strategy archetype (random if None)
        industry: Optional industry (random if None)

    Returns:
        dict with username, email, industry, strategy_profile, subscriber_count
    """
    from bot_strategies import generate_strategy_profile, pick_random_strategy

    if strategy_name is None:
        strategy_name = pick_random_strategy()
    if industry is None:
        industry = pick_industry()

    username = generate_username()
    email = generate_email(username)
    strategy_profile = generate_strategy_profile(strategy_name, industry)
    subscriber_count = generate_subscriber_count()

    return {
        'username': username,
        'email': email,
        'industry': industry,
        'strategy_name': strategy_name,
        'strategy_profile': strategy_profile,
        'subscriber_count': subscriber_count,
    }


def generate_bot_batch(count, industry=None, strategy=None):
    """
    Generate a batch of bot personas.
    Ensures diverse strategies and industries across the batch.
    """
    from bot_strategies import STRATEGY_TEMPLATES, pick_random_strategy

    personas = []
    used_usernames = set()

    for i in range(count):
        persona = generate_bot_persona(
            strategy_name=strategy,
            industry=industry,
        )

        # Ensure unique username
        attempts = 0
        while persona['username'] in used_usernames and attempts < 10:
            persona['username'] = generate_username()
            persona['email'] = generate_email(persona['username'])
            attempts += 1

        used_usernames.add(persona['username'])
        personas.append(persona)

    # Log distribution
    strategy_dist = {}
    industry_dist = {}
    for p in personas:
        s = p['strategy_name']
        i = p['industry']
        strategy_dist[s] = strategy_dist.get(s, 0) + 1
        industry_dist[i] = industry_dist.get(i, 0) + 1

    logger.info(f"Generated {count} personas:")
    logger.info(f"  Strategies: {dict(sorted(strategy_dist.items()))}")
    logger.info(f"  Industries: {dict(sorted(industry_dist.items()))}")

    return personas
