"""
Bot Persona Generator
======================
Generates realistic bot identities with names, industries, and strategy
profiles. Each bot gets a unique combination of strategy archetype,
Dirichlet-sampled indicator weights, personality quirks, life stage,
and attention universe.
"""

import random
import re
import logging

logger = logging.getLogger('bot_personas')


# ── Name Generation ──────────────────────────────────────────────────────────
# Modeled after real usernames on Polymarket, Kalshi, StockTwits, etc.
# Patterns: CamelCase compounds, lowercase+num, short punchy, real-name-ish
# NO underscores, hyphens, or corporate suffixes like "_capital" or "_trader"

# CamelCase compound words (Polymarket style: HorizonSplendidView, CemeterySun)
CAMEL_FIRST = [
    'Autumn', 'Azure', 'Bright', 'Canyon', 'Cedar', 'Cobalt', 'Coast',
    'Copper', 'Coral', 'Crimson', 'Crystal', 'Dawn', 'Desert', 'Ember',
    'Falcon', 'Forest', 'Frost', 'Golden', 'Harbor', 'Horizon', 'Iron',
    'Ivory', 'Jade', 'Jasper', 'Lunar', 'Maple', 'Meadow', 'Mesa',
    'Midnight', 'Moss', 'Mountain', 'North', 'Nova', 'Ocean', 'Onyx',
    'Orion', 'Pacific', 'Peak', 'Phoenix', 'Pine', 'Polar', 'Prairie',
    'Raven', 'Ridge', 'River', 'Sage', 'Shadow', 'Sierra', 'Silver',
    'Solar', 'South', 'Steel', 'Stone', 'Storm', 'Summit', 'Tidal',
    'Timber', 'Valley', 'Velvet', 'Vintage', 'Violet', 'Wild', 'Winter',
]

CAMEL_SECOND = [
    'Arc', 'Bay', 'Bear', 'Bell', 'Bird', 'Blaze', 'Bloom', 'Bolt',
    'Brook', 'Cliff', 'Cloud', 'Crest', 'Dale', 'Drift', 'Dusk',
    'Edge', 'Elk', 'Fall', 'Field', 'Fire', 'Flare', 'Flow', 'Fox',
    'Glen', 'Grove', 'Gust', 'Hawk', 'Haven', 'Hill', 'Isle', 'Jay',
    'Lake', 'Lane', 'Lark', 'Leaf', 'Light', 'Lynx', 'Moon', 'Oak',
    'Path', 'Point', 'Rain', 'Reed', 'Rock', 'Rose', 'Run', 'Rush',
    'Sand', 'Sky', 'Spark', 'Spring', 'Star', 'Sun', 'Swift', 'Tide',
    'Trail', 'Vale', 'View', 'Wave', 'West', 'Wind', 'Wolf', 'Wren',
]

# Lowercase fused words (Polymarket style: reachingthesky, beachboy4, swisstony)
LOWERCASE_WORDS = [
    'reaching', 'morning', 'evening', 'coastal', 'northern', 'southern',
    'western', 'eastern', 'rising', 'falling', 'running', 'rolling',
    'sleeping', 'waking', 'chasing', 'quiet', 'golden', 'silver',
    'copper', 'marble', 'velvet', 'autumn', 'winter', 'summer',
    'spring', 'frozen', 'broken', 'hidden', 'steady', 'lucky',
    'dusty', 'rusty', 'misty', 'cloudy', 'sunny', 'rainy', 'snowy',
    'blue', 'green', 'red', 'grey', 'dark', 'bright', 'deep',
    'tall', 'old', 'new', 'swift', 'slow', 'loud', 'calm',
]

LOWERCASE_NOUNS = [
    'thesky', 'thehill', 'thewind', 'moon', 'sun', 'stars', 'rain',
    'creek', 'river', 'lake', 'ocean', 'beach', 'mountain', 'valley',
    'forest', 'meadow', 'canyon', 'desert', 'island', 'harbor',
    'fox', 'wolf', 'hawk', 'bear', 'elk', 'owl', 'crow', 'jay',
    'oak', 'pine', 'birch', 'cedar', 'maple', 'sage', 'fern',
    'stone', 'sand', 'clay', 'iron', 'frost', 'ember', 'spark',
    'boy', 'kid', 'dude', 'tony', 'mike', 'dave', 'sam', 'joe',
]

# Short punchy handles (Kalshi/StockTwits style: gatorr, cobybets1)
SHORT_HANDLES = [
    'gatorr', 'bucky', 'jojo', 'momo', 'nemo', 'zazu', 'kiko',
    'remy', 'bobo', 'lulu', 'coco', 'milo', 'otto', 'tito',
    'ziggy', 'bongo', 'fizzy', 'jazzy', 'peppy', 'dizzy',
    'sparky', 'rocky', 'lucky', 'stormy', 'dusty', 'rusty',
    'frosty', 'smoky', 'misty', 'buddy', 'scout', 'bandit',
    'rebel', 'maverick', 'blaze', 'flash', 'dash', 'ace',
]

# Real-ish first names (no suffixes, just the name + optional number)
REAL_FIRST_NAMES = [
    'alex', 'jordan', 'riley', 'casey', 'morgan', 'avery',
    'blake', 'cameron', 'drew', 'emery', 'finley', 'harper',
    'jamie', 'kai', 'logan', 'mason', 'nolan', 'parker',
    'quinn', 'reese', 'sawyer', 'taylor', 'wren', 'skyler',
    'rowan', 'sage', 'river', 'phoenix', 'kendall', 'devon',
    'hayden', 'peyton', 'rory', 'shay', 'tatum', 'lennox',
    'marley', 'oakley', 'harley', 'dallas', 'jules', 'nico',
]


def _generate_username_with_parts():
    """Generate a candidate username plus the lowercase word components it was
    built from. Components feed the similarity guard: two bots must never
    share a visible name word (SteelFire + RainFire both read as bots).
    """
    pattern = random.choices(
        ['camel', 'lowercase_fused', 'short_handle', 'real_name', 'real_num'],
        weights=[30, 25, 15, 15, 15],
        k=1
    )[0]

    if pattern == 'camel':
        # CamelCase: SilverFox, MidnightStar, CoastalBreezeView
        first = random.choice(CAMEL_FIRST)
        second = random.choice(CAMEL_SECOND)
        parts = [first.lower(), second.lower()]
        # Sometimes add a third word or number
        extra = random.choices(
            ['', random.choice(CAMEL_SECOND), str(random.randint(1, 99))],
            weights=[50, 30, 20], k=1
        )[0]
        if extra and not extra.isdigit():
            parts.append(extra.lower())
        return f"{first}{second}{extra}", parts

    elif pattern == 'lowercase_fused':
        # Fused lowercase: reachingthesky, goldenoak7, quietstorm
        word = random.choice(LOWERCASE_WORDS)
        noun = random.choice(LOWERCASE_NOUNS)
        num = random.choice(['', str(random.randint(1, 99))])
        return f"{word}{noun}{num}", [word, noun]

    elif pattern == 'short_handle':
        # Short punchy: gatorr, sparky22, ace
        handle = random.choice(SHORT_HANDLES)
        num = random.choices(
            ['', str(random.randint(1, 9)), str(random.randint(10, 99))],
            weights=[40, 30, 30], k=1
        )[0]
        return f"{handle}{num}", [handle]

    elif pattern == 'real_name':
        # Just a name, maybe with a short number: alex, jordan7, reese42
        name = random.choice(REAL_FIRST_NAMES)
        num = random.choices(
            ['', str(random.randint(1, 9)), str(random.randint(10, 99)),
             str(random.randint(100, 999))],
            weights=[30, 25, 30, 15], k=1
        )[0]
        return f"{name}{num}", [name]

    else:  # real_num — just initials/letters + numbers
        # kch123 style
        letters = ''.join(random.choices('abcdefghijklmnopqrstuvwxyz', k=random.randint(2, 4)))
        num = str(random.randint(1, 999))
        return f"{letters}{num}", [letters]


def generate_username():
    """
    Generate a modern, trendy username matching Polymarket/Kalshi/StockTwits style.
    No underscores, hyphens, or corporate suffixes.
    """
    return _generate_username_with_parts()[0]


def _components_of_existing(username):
    """Best-effort decomposition of an EXISTING username into comparable
    lowercase components. CamelCase splits cleanly; fused lowercase names
    can't be split, so their digit-stripped blob is included whole (exact
    word matches against it still catch e.g. 'golden' vs 'golden7').
    """
    if not username:
        return set()
    comps = {w.lower() for w in re.findall(r'[A-Z][a-z]+', username)}
    blob = re.sub(r'[^a-z]', '', username.lower())
    if blob:
        comps.add(blob)
    return comps


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


def generate_bot_batch(count, industry=None, strategy=None, existing_usernames=None):
    """
    Generate a batch of bot personas.
    Ensures diverse strategies and industries across the batch.

    existing_usernames: iterable of usernames already in the DB. Candidates
    sharing a visible word component with ANY of them are rejected, so the
    fleet never accumulates near-twins across creation batches.
    """
    from bot_strategies import STRATEGY_TEMPLATES, pick_random_strategy

    personas = []
    used_usernames = set()
    # Similarity guard: track every WORD used in any name (this batch + the
    # existing fleet) and reject candidates that reuse one. Prevents
    # dead-giveaway near-twins like SteelFire/RainFire (shared 'Fire') both
    # within a batch and against bots created in earlier batches.
    used_components = set()
    for existing in (existing_usernames or []):
        used_usernames.add(existing.lower())
        used_components |= _components_of_existing(existing)

    for i in range(count):
        persona = generate_bot_persona(
            strategy_name=strategy,
            industry=industry,
        )

        # Regenerate until the name is exact-unique AND shares no word
        # component with any existing/batch name. Word lists are large
        # enough (~4k camel combos alone) that 60 attempts practically
        # always succeeds; the fallback keeps at least exact uniqueness.
        candidate, parts = _generate_username_with_parts()
        attempts = 0
        while attempts < 60 and (
            candidate.lower() in used_usernames
            or any(p in used_components for p in parts)
        ):
            candidate, parts = _generate_username_with_parts()
            attempts += 1
        if attempts >= 60:
            logger.warning(
                f"Username similarity guard exhausted after {attempts} attempts; "
                f"accepting '{candidate}' with possible shared component"
            )
            while candidate.lower() in used_usernames:
                candidate = f"{candidate}{random.randint(1, 99)}"

        persona['username'] = candidate
        persona['email'] = generate_email(candidate)
        used_usernames.add(candidate.lower())
        used_components.update(parts)
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
