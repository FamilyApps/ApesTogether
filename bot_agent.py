"""
Bot Agent Orchestrator v2 for Apes Together
=============================================
Intelligent autonomous trading agents that do real market research,
apply parameterized strategies, and make informed buy/sell decisions.

Usage:
    python bot_agent.py seed --count 1                     # Create 1 bot (default)
    python bot_agent.py seed --count 5 --industry Tech     # Create 5 tech bots
    python bot_agent.py seed --count 3 --strategy momentum # 3 momentum bots
    python bot_agent.py trade                              # Run one trading session
    python bot_agent.py trade --wave 1                     # Trade wave 1 only
    python bot_agent.py trade --dry-run                    # Preview decisions only
    python bot_agent.py remove --user-id 42                # Deactivate bot #42
    python bot_agent.py remove --last 3                    # Deactivate last 3 created
    python bot_agent.py gift --user-id 42 --count 5        # Gift 5 subscribers
    python bot_agent.py status                             # Dashboard overview
    python bot_agent.py refresh                            # Refresh market data only

Environment:
    CRON_SECRET             - Required
    API_BASE_URL           - Optional, defaults to https://apestogether.ai/api/mobile
    ALPHA_VANTAGE_API_KEY  - Required for news sentiment
    FINNHUB_API_KEY        - Optional, enables social sentiment
"""

import os
import sys
import io
import json
import time
import random
import argparse
import logging
from datetime import datetime

# Load .env file before anything else reads environment variables
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv not installed; rely on shell-exported env vars

# Fix Windows console encoding for emoji/unicode output
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# ── Logging ──────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(name)s] %(levelname)s: %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger('bot_agent')

# Quiet down noisy libraries
logging.getLogger('urllib3').setLevel(logging.WARNING)
logging.getLogger('yfinance').setLevel(logging.WARNING)


# ── Imports (local modules) ──────────────────────────────────────────────────

from bot_data_hub import MarketDataHub
from bot_strategies import generate_trade_decisions, generate_strategy_profile, STRATEGY_TEMPLATES
from bot_behaviors import (
    should_trade_today, get_trade_wave, apply_human_biases,
    apply_fomo_trades, is_market_hours, add_trade_delay
)
from bot_executor import (
    get_active_bots, execute_bot_decisions, create_bot_account,
    seed_initial_portfolio, gift_subscribers, get_dashboard_stats, api_call
)
from bot_personas import generate_bot_persona, generate_bot_batch


# ── Seed Command ─────────────────────────────────────────────────────────────

# Archetype → preferred industry mapping.
# Some archetypes are best suited to a specific sector;
# the rest get a random mixed portfolio.
ARCHETYPE_INDUSTRY_MAP = {
    'momentum':         None,            # mixed
    'value':            None,            # mixed
    'news_reactor':     None,            # mixed — reacts to any sector news
    'swing':            None,            # mixed
    'earnings':         'Finance',       # earnings plays suit finance sector
    'sector_rotation':  None,            # mixed by definition
    'insider_follower': 'Healthcare',    # insider activity most meaningful here
    'dividend_growth':  'Energy',        # energy/utilities heavy on dividends
    'social_momentum':  'Technology',    # Reddit/Twitter buzz = mostly tech
    'balanced':         None,            # mixed
}


def cmd_seed(args):
    """Create new bot accounts with strategy profiles and initial portfolios."""
    one_each = args.one_per_archetype
    count = args.count
    industry = args.industry
    strategy = args.strategy

    # Build the persona list
    if one_each:
        # One bot per archetype — ignore --count and --strategy
        archetype_names = list(STRATEGY_TEMPLATES.keys())
        total = len(archetype_names)
        print(f"\n🦍 Seeding 1 bot per archetype ({total} total)...")
    else:
        total = count
        print(f"\n🦍 Seeding {total} bot(s)...")
        if industry:
            print(f"   Industry: {industry}")
        if strategy:
            print(f"   Strategy: {strategy}")

    # First, refresh market data so we can seed with real prices
    print(f"\n📊 Refreshing market data for initial portfolios...")
    hub = MarketDataHub()
    hub.refresh(include_extras=False)  # Core data only for seeding

    if not hub.is_core_available():
        print("⚠️  Warning: Market data unavailable. Seeding without initial portfolio.")
        hub = None

    # Generate personas
    if one_each:
        personas = []
        for arch in archetype_names:
            # Use mapped industry or override with --industry flag
            ind = industry or ARCHETYPE_INDUSTRY_MAP.get(arch)
            personas.append(generate_bot_persona(strategy_name=arch, industry=ind))
    else:
        personas = generate_bot_batch(count, industry=industry, strategy=strategy)

    created = []
    for i, persona in enumerate(personas):
        username = persona['username']
        email = persona['email']
        ind = persona['industry']
        strat = persona['strategy_name']
        profile = persona['strategy_profile']

        print(f"\n  [{i+1}/{total}] Creating: {username}")
        print(f"    Industry: {ind} | Strategy: {strat}")
        print(f"    Life stage: {profile.get('life_stage')} | Risk: {profile.get('risk_tolerance'):.2f}")
        print(f"    Attention universe: {len(profile.get('attention_universe', []))} tickers")

        # Create account
        user_id, success = create_bot_account(username, email, ind, profile)
        if not success:
            print(f"    ❌ Failed to create account")
            continue

        print(f"    ✅ Created (ID={user_id})")

        # Seed initial portfolio with real prices
        if hub and hub.is_core_available():
            stock_count = seed_initial_portfolio(user_id, profile, hub)
            print(f"    📊 Seeded {stock_count} stocks")
        else:
            print(f"    ⚠️  Skipped portfolio seeding (no market data)")

        # Gift initial subscribers
        sub_count = persona['subscriber_count']
        if gift_subscribers(user_id, sub_count):
            print(f"    👥 Gifted {sub_count} subscribers")

        # Store full strategy profile as JSON for future reference
        _save_bot_profile(user_id, profile)

        created.append({
            'user_id': user_id,
            'username': username,
            'industry': ind,
            'strategy': strat,
        })

        time.sleep(random.uniform(0.3, 0.8))

    print(f"\n✅ Created {len(created)}/{total} bots")
    for c in created:
        print(f"   ID={c['user_id']} | {c['username']} | {c['industry']} | {c['strategy']}")


# ── Trade Command ────────────────────────────────────────────────────────────

def cmd_trade(args):
    """Run a trading session for all active bots."""
    dry_run = args.dry_run
    wave_filter = args.wave
    force = args.force

    print(f"\n🦍 Trading Session {'(DRY RUN)' if dry_run else ''}")
    print(f"   Time: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")

    if not force and not is_market_hours():
        print("   ⚠️  Market is closed. Use --force to trade anyway.")
        return

    # Step 1: Refresh market data
    print(f"\n📊 Refreshing market data...")
    hub = MarketDataHub()
    hub.refresh(include_extras=True)

    if not hub.is_core_available():
        print("❌ Cannot trade: no price/indicator data available")
        return

    summary = hub.summary()
    print(f"   Tickers with data: {summary['tickers_with_indicators']}")
    print(f"   News sentiment: {summary['tickers_with_news']} tickers")
    print(f"   Social sentiment: {summary['tickers_with_social']} tickers")

    # Step 2: Get active bots
    bots = get_active_bots()
    if not bots:
        print("   No active bots found. Run 'seed' first.")
        return

    print(f"\n🤖 Active bots: {len(bots)}")

    # Step 3: Process each bot
    total_trades = 0
    for bot in bots:
        user_id = bot['id']
        username = bot['username']
        industry = bot.get('industry', 'General')

        # Load strategy profile
        profile = _load_bot_profile(user_id)
        if not profile:
            # Generate a default profile if none saved
            from bot_strategies import pick_random_strategy
            strategy_name = bot.get('extra_data', {}).get('trading_style', pick_random_strategy())
            profile = generate_strategy_profile(strategy_name, industry)

        # Check if bot should trade today
        if not force and not should_trade_today(profile):
            logger.debug(f"  {username}: skipping today (frequency/patience)")
            continue

        # Check wave filter
        bot_wave = get_trade_wave(profile)
        if wave_filter and bot_wave != wave_filter:
            logger.debug(f"  {username}: not in wave {wave_filter} (assigned wave {bot_wave})")
            continue

        print(f"\n  🧠 {username} (ID={user_id}, {profile.get('strategy', '?')}, wave {bot_wave})")

        # Get current holdings (from bot data)
        holdings = _get_bot_holdings_from_api(user_id)

        # Generate trade decisions
        decisions = generate_trade_decisions(profile, hub, holdings)

        # Apply human biases
        recent_trades = []  # TODO: fetch from trade history
        decisions = apply_human_biases(decisions, profile, recent_trades)

        # Add FOMO trades
        fomo = apply_fomo_trades(profile, hub, decisions)
        if fomo:
            decisions.extend(fomo)

        if not decisions:
            print(f"    → No trades (signals below threshold)")
            continue

        # Display decisions
        for d in decisions:
            fomo_tag = " 🔥FOMO" if d.get('is_fomo') else ""
            print(f"    → {d['action'].upper()} {d['ticker']} "
                  f"(score={d['score']:.3f}) — {d['reason']}{fomo_tag}")

        if dry_run:
            print(f"    [DRY RUN — not executed]")
            continue

        # Execute trades
        executed = execute_bot_decisions(user_id, username, decisions, profile, hub)
        total_trades += len(executed)

    print(f"\n✅ Trading session complete: {total_trades} trades executed across {len(bots)} bots")


# ── Remove Command ───────────────────────────────────────────────────────────

def cmd_remove(args):
    """Deactivate (soft-delete) bot accounts."""
    if args.user_id:
        user_ids = [args.user_id]
    elif args.last:
        # Deactivate the last N created bots
        bots = get_active_bots()
        bots.sort(key=lambda b: b.get('created_at', ''), reverse=True)
        user_ids = [b['id'] for b in bots[:args.last]]
    else:
        print("❌ Specify --user-id or --last N")
        return

    print(f"\n🦍 Deactivating {len(user_ids)} bot(s)...")

    for uid in user_ids:
        result, status = api_call('/admin/bot/deactivate', 'POST', {'user_id': uid})
        if result.get('success'):
            print(f"  ✅ Deactivated bot ID={uid}")
        else:
            print(f"  ❌ Failed to deactivate ID={uid}: {result.get('error', 'unknown')}")

    print(f"\n✅ Done. Use 'status' to verify.")


# ── Reactivate Command ──────────────────────────────────────────────────────

def cmd_reactivate(args):
    """Reactivate previously deactivated bots."""
    if not args.user_id:
        print("❌ Specify --user-id")
        return

    result, status = api_call('/admin/bot/reactivate', 'POST', {'user_id': args.user_id})
    if result.get('success'):
        print(f"✅ Reactivated bot ID={args.user_id}")
    else:
        print(f"❌ Failed: {result.get('error', 'unknown')}")


# ── Gift Command ─────────────────────────────────────────────────────────────

def cmd_gift(args):
    """Gift subscribers to a bot account."""
    if not args.user_id:
        print("❌ --user-id required")
        return

    if gift_subscribers(args.user_id, args.count):
        print(f"✅ Gifted {args.count} subscribers to bot ID={args.user_id}")
    else:
        print(f"❌ Gift failed")


# ── Status Command ───────────────────────────────────────────────────────────

def cmd_status(args):
    """Display bot dashboard status."""
    stats = get_dashboard_stats()

    print(f"\n  {'='*45}")
    print(f"  🦍 Apes Together — Bot Agent Dashboard")
    print(f"  {'='*45}")
    print(f"  Total Users:       {stats.get('total_users', '?')}")
    print(f"  Human Users:       {stats.get('human_users', '?')}")
    print(f"  Bot Users:         {stats.get('bot_users', '?')}")
    print(f"  Active Bots:       {stats.get('active_bots', '?')}")
    print(f"  Inactive Bots:     {stats.get('inactive_bots', '?')}")
    print(f"  Total Stocks:      {stats.get('total_stocks', '?')}")
    print(f"  Total Trades:      {stats.get('total_trades', '?')}")
    print(f"  Subscriptions:     {stats.get('total_subscriptions', '?')}")
    print(f"  Gifted Subs:       {stats.get('gifted_subscriptions', '?')}")

    breakdown = stats.get('industry_breakdown', {})
    if breakdown:
        print(f"\n  Industry Breakdown:")
        for ind, count in sorted(breakdown.items(), key=lambda x: -x[1]):
            print(f"    {ind:20s} {count} bots")

    # Show active bots with strategy info
    bots = get_active_bots()
    if bots:
        print(f"\n  Active Bot Details:")
        print(f"  {'ID':>5} {'Username':<25} {'Industry':<15} {'Stocks':>6} {'Trades':>6}")
        print(f"  {'-'*5} {'-'*25} {'-'*15} {'-'*6} {'-'*6}")
        for b in bots[:30]:  # Show first 30
            print(f"  {b['id']:>5} {b['username']:<25} "
                  f"{b.get('industry', 'General'):<15} "
                  f"{b.get('stock_count', 0):>6} "
                  f"{b.get('trade_count', 0):>6}")
        if len(bots) > 30:
            print(f"  ... and {len(bots) - 30} more")

    print()


# ── Refresh Command ──────────────────────────────────────────────────────────

def cmd_refresh(args):
    """Refresh market data without trading (for testing/inspection)."""
    print(f"\n📊 Refreshing market data...")

    hub = MarketDataHub()
    hub.refresh(include_extras=not args.core_only)

    summary = hub.summary()
    print(f"\n  Data Hub Summary:")
    print(f"  Tickers with indicators: {summary['tickers_with_indicators']}")
    print(f"  Tickers with news:       {summary['tickers_with_news']}")
    print(f"  Tickers with social:     {summary['tickers_with_social']}")
    print(f"  Tickers with analyst:    {summary['tickers_with_analyst']}")
    print(f"  Tickers with insider:    {summary['tickers_with_insider']}")
    print(f"  Top gainers:             {summary['top_gainers']}")
    print(f"  Data quality:            {summary['data_quality']}")

    if args.ticker:
        ticker = args.ticker.upper()
        data = hub.get_stock_data(ticker)
        if data:
            print(f"\n  {ticker} Detail:")
            for k, v in sorted(data.items()):
                if k != 'ticker':
                    print(f"    {k:25s} {v}")
        else:
            print(f"\n  No data for {ticker}")


# ── Profile Storage ──────────────────────────────────────────────────────────
# Store/load strategy profiles as JSON files for persistence between runs

PROFILE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.bot_profiles')

def _save_bot_profile(user_id, profile):
    """Save a bot's strategy profile to disk."""
    os.makedirs(PROFILE_DIR, exist_ok=True)
    path = os.path.join(PROFILE_DIR, f'{user_id}.json')
    # Convert any non-serializable types
    clean = json.loads(json.dumps(profile, default=str))
    with open(path, 'w') as f:
        json.dump(clean, f, indent=2)

def _load_bot_profile(user_id):
    """Load a bot's strategy profile from disk."""
    path = os.path.join(PROFILE_DIR, f'{user_id}.json')
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return None

def _get_bot_holdings_from_api(user_id):
    """Get a bot's current holdings from the admin API."""
    from bot_executor import get_bot_holdings
    return get_bot_holdings(user_id)


# ── CLI ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description='🦍 Apes Together — Bot Agent Orchestrator v2',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python bot_agent.py seed --one-per-archetype       # 1 bot per strategy (10 total)
  python bot_agent.py seed --count 5 --industry Technology
  python bot_agent.py seed --count 3 --strategy momentum --industry Finance
  python bot_agent.py trade --dry-run --force        # Preview decisions
  python bot_agent.py trade --force                  # Execute trades
  python bot_agent.py remove --user-id 42            # Deactivate a bot
  python bot_agent.py remove --last 3                # Remove last 3 bots
  python bot_agent.py reactivate --user-id 42        # Bring back a bot
  python bot_agent.py status                         # Dashboard overview
  python bot_agent.py refresh --ticker AAPL           # Check data for a ticker
        """
    )

    subparsers = parser.add_subparsers(dest='command', help='Command to run')

    # seed
    p_seed = subparsers.add_parser('seed', help='Create new bot accounts')
    p_seed.add_argument('--count', type=int, default=1, help='Number of bots (default: 1)')
    p_seed.add_argument('--industry', type=str, default=None,
                        help='Industry focus (Technology, Healthcare, Finance, Energy, Consumer, Industrial, Real Estate, ETF)')
    p_seed.add_argument('--strategy', type=str, default=None,
                        choices=list(STRATEGY_TEMPLATES.keys()),
                        help='Strategy archetype')
    p_seed.add_argument('--one-per-archetype', action='store_true',
                        help='Create 1 bot for each of the 10 strategy archetypes')
    p_seed.set_defaults(func=cmd_seed)

    # trade
    p_trade = subparsers.add_parser('trade', help='Run a trading session')
    p_trade.add_argument('--dry-run', action='store_true', help='Preview only')
    p_trade.add_argument('--wave', type=int, choices=[1,2,3,4], help='Trade specific wave only')
    p_trade.add_argument('--force', action='store_true', help='Trade even if market closed')
    p_trade.set_defaults(func=cmd_trade)

    # remove
    p_remove = subparsers.add_parser('remove', help='Deactivate bot(s)')
    p_remove.add_argument('--user-id', type=int, help='Specific bot ID')
    p_remove.add_argument('--last', type=int, help='Deactivate last N created bots')
    p_remove.set_defaults(func=cmd_remove)

    # reactivate
    p_react = subparsers.add_parser('reactivate', help='Reactivate a deactivated bot')
    p_react.add_argument('--user-id', type=int, required=True, help='Bot ID')
    p_react.set_defaults(func=cmd_reactivate)

    # gift
    p_gift = subparsers.add_parser('gift', help='Gift subscribers to a bot')
    p_gift.add_argument('--user-id', type=int, required=True, help='Bot ID')
    p_gift.add_argument('--count', type=int, default=1, help='Number of subscribers')
    p_gift.set_defaults(func=cmd_gift)

    # status
    p_status = subparsers.add_parser('status', help='Dashboard overview')
    p_status.set_defaults(func=cmd_status)

    # refresh
    p_refresh = subparsers.add_parser('refresh', help='Refresh market data')
    p_refresh.add_argument('--ticker', type=str, help='Show detail for a ticker')
    p_refresh.add_argument('--core-only', action='store_true', help='Skip extras (news/social)')
    p_refresh.set_defaults(func=cmd_refresh)

    # Global options
    parser.add_argument('--base-url', type=str, help='Override API base URL')
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose logging')

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    if args.base_url:
        import bot_executor
        bot_executor.API_BASE = args.base_url

    if not hasattr(args, 'func'):
        parser.print_help()
        sys.exit(0)

    # Validate admin key (not needed for refresh)
    cron_secret = os.environ.get('CRON_SECRET', '')
    if not cron_secret and args.command != 'refresh':
        print("❌ CRON_SECRET environment variable not set")
        print("   Set it: $env:CRON_SECRET='your_key_here'  (PowerShell)")
        sys.exit(1)

    print(f"\n🦍 Apes Together Bot Agent v2")
    print(f"   Command: {args.command}")

    args.func(args)


if __name__ == '__main__':
    main()
