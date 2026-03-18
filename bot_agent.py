"""
Bot Agent Orchestrator for Apes Together
=========================================
Creates realistic bot portfolios across industries and executes trades
with human-like timing variations.

Usage:
    python bot_agent.py --action seed --count 5 --industry Technology
    python bot_agent.py --action trade --rounds 3
    python bot_agent.py --action seed-all --bots-per-industry 3
    python bot_agent.py --action gift --user-id 42 --count 5
    python bot_agent.py --action status

Environment:
    ADMIN_API_KEY  - Required, must match the server's admin key
    API_BASE_URL   - Optional, defaults to https://apestogether.ai/api/mobile
"""

import os
import sys
import json
import time
import random
import string
import argparse
import requests
from datetime import datetime, timedelta

# ── Config ──────────────────────────────────────────────────────────────────

API_BASE = os.environ.get('API_BASE_URL', 'https://apestogether.ai/api/mobile')
ADMIN_KEY = os.environ.get('ADMIN_API_KEY', '')

# ── Industry Stock Pools ────────────────────────────────────────────────────
# Realistic stock picks per industry with typical price ranges

INDUSTRY_STOCKS = {
    'Technology': [
        ('AAPL', 170, 195), ('MSFT', 380, 430), ('GOOGL', 150, 175),
        ('NVDA', 800, 950), ('META', 480, 550), ('CRM', 270, 310),
        ('ADBE', 520, 580), ('INTC', 30, 45), ('AMD', 140, 175),
        ('ORCL', 120, 145), ('CSCO', 48, 56), ('SHOP', 70, 90),
        ('SNOW', 150, 180), ('PLTR', 22, 32), ('NET', 80, 100),
        ('SQ', 70, 85), ('TWLO', 60, 80), ('ZS', 200, 240),
    ],
    'Healthcare': [
        ('JNJ', 155, 170), ('UNH', 500, 560), ('PFE', 26, 32),
        ('ABBV', 170, 195), ('LLY', 700, 800), ('MRK', 120, 135),
        ('TMO', 540, 600), ('ABT', 105, 120), ('BMY', 50, 58),
        ('AMGN', 280, 310), ('GILD', 75, 88), ('ISRG', 380, 420),
        ('VRTX', 400, 450), ('REGN', 900, 1000), ('ZTS', 175, 195),
    ],
    'Finance': [
        ('JPM', 190, 215), ('BAC', 35, 42), ('WFC', 55, 65),
        ('GS', 420, 480), ('MS', 90, 105), ('BLK', 780, 860),
        ('SCHW', 70, 82), ('C', 58, 68), ('AXP', 210, 240),
        ('V', 270, 295), ('MA', 440, 480), ('COF', 140, 160),
        ('USB', 42, 50), ('PNC', 155, 175),
    ],
    'Energy': [
        ('XOM', 105, 120), ('CVX', 150, 170), ('COP', 110, 130),
        ('SLB', 48, 58), ('EOG', 120, 140), ('PXD', 230, 260),
        ('MPC', 160, 180), ('VLO', 140, 160), ('PSX', 130, 150),
        ('OKE', 70, 82), ('WMB', 35, 42), ('ENPH', 100, 130),
        ('FSLR', 170, 210), ('NEE', 65, 78),
    ],
    'Consumer': [
        ('AMZN', 175, 195), ('TSLA', 230, 280), ('HD', 360, 400),
        ('MCD', 280, 310), ('NKE', 95, 115), ('SBUX', 95, 110),
        ('TGT', 140, 165), ('COST', 700, 780), ('WMT', 165, 185),
        ('PG', 160, 175), ('KO', 58, 65), ('PEP', 170, 185),
        ('DIS', 100, 120), ('LULU', 380, 430),
    ],
    'Industrial': [
        ('CAT', 310, 360), ('DE', 380, 430), ('HON', 200, 225),
        ('UPS', 145, 165), ('BA', 200, 240), ('RTX', 95, 110),
        ('LMT', 440, 490), ('GE', 155, 175), ('MMM', 100, 120),
        ('EMR', 105, 120), ('ITW', 250, 275), ('FDX', 260, 290),
    ],
    'Real Estate': [
        ('AMT', 195, 220), ('PLD', 125, 145), ('CCI', 105, 120),
        ('EQIX', 780, 860), ('PSA', 280, 310), ('SPG', 145, 165),
        ('O', 55, 62), ('VICI', 30, 35), ('DLR', 135, 155),
        ('ARE', 120, 140), ('AVB', 190, 215),
    ],
    'ETF': [
        ('SPY', 490, 530), ('QQQ', 430, 480), ('VTI', 250, 275),
        ('IWM', 200, 225), ('DIA', 390, 420), ('ARKK', 45, 60),
        ('XLF', 40, 46), ('XLK', 200, 225), ('XLE', 85, 98),
        ('XLV', 140, 155), ('GLD', 210, 230), ('TLT', 90, 102),
        ('VOO', 470, 510), ('SCHD', 78, 86),
    ],
    'General': [
        ('AAPL', 170, 195), ('MSFT', 380, 430), ('AMZN', 175, 195),
        ('GOOGL', 150, 175), ('JPM', 190, 215), ('JNJ', 155, 170),
        ('XOM', 105, 120), ('SPY', 490, 530), ('TSLA', 230, 280),
        ('V', 270, 295), ('HD', 360, 400), ('PG', 160, 175),
    ],
}

# ── Username Generation ─────────────────────────────────────────────────────

ADJECTIVES = [
    'swift', 'bold', 'clever', 'calm', 'sharp', 'bright', 'keen',
    'steady', 'wise', 'quick', 'prime', 'deep', 'iron', 'core',
    'alpha', 'apex', 'chill', 'true', 'pure', 'wild', 'lunar',
    'solar', 'sonic', 'cyber', 'neo', 'zen', 'max', 'top',
]

NOUNS = [
    'trader', 'hawk', 'bull', 'wolf', 'fox', 'eagle', 'lion',
    'shark', 'bear', 'titan', 'atlas', 'viper', 'falcon', 'raven',
    'orca', 'phoenix', 'lynx', 'cobra', 'panther', 'mustang',
    'rhino', 'jaguar', 'puma', 'raptor', 'condor', 'heron',
]

def generate_username():
    """Generate a human-looking username like 'swift-hawk-42'"""
    adj = random.choice(ADJECTIVES)
    noun = random.choice(NOUNS)
    num = random.randint(1, 99)
    sep = random.choice(['-', '_', ''])
    
    patterns = [
        f"{adj}{sep}{noun}",
        f"{adj}{sep}{noun}{num}",
        f"{noun}{sep}{adj}",
        f"{noun}{num}",
        f"{adj}{num}{sep}{noun}",
    ]
    return random.choice(patterns)


def generate_email(username):
    """Generate a plausible email for a bot"""
    domains = ['apestogether.ai']
    return f"{username.replace('-', '.').replace('_', '.')}@{random.choice(domains)}"


# ── API Helpers ─────────────────────────────────────────────────────────────

def api_call(endpoint, method='GET', data=None):
    """Make an authenticated admin API call"""
    headers = {
        'X-Admin-Key': ADMIN_KEY,
        'Content-Type': 'application/json'
    }
    url = f"{API_BASE}{endpoint}"
    
    try:
        if method == 'GET':
            resp = requests.get(url, headers=headers, timeout=30)
        else:
            resp = requests.post(url, headers=headers, json=data, timeout=30)
        
        result = resp.json()
        if resp.status_code == 403:
            print(f"  ❌ AUTH ERROR: Invalid admin key")
            sys.exit(1)
        return result, resp.status_code
    except Exception as e:
        print(f"  ❌ REQUEST ERROR: {e}")
        return {'error': str(e)}, 500


# ── Bot Seeding ─────────────────────────────────────────────────────────────

def seed_bots(industry, count=1):
    """Create bot accounts with realistic portfolios for a given industry"""
    stocks_pool = INDUSTRY_STOCKS.get(industry, INDUSTRY_STOCKS['General'])
    created = []
    
    for i in range(count):
        username = generate_username()
        email = generate_email(username)
        
        print(f"\n  Creating bot: {username} ({industry})")
        
        # 1. Create user
        result, status = api_call('/admin/bot/create-user', 'POST', {
            'username': username,
            'email': email,
            'industry': industry
        })
        
        if status == 409:
            # Username taken, retry with suffix
            username = username + str(random.randint(100, 999))
            email = generate_email(username)
            result, status = api_call('/admin/bot/create-user', 'POST', {
                'username': username,
                'email': email,
                'industry': industry
            })
        
        if not result.get('success'):
            print(f"    ⚠️  Failed: {result.get('error', 'unknown')}")
            continue
        
        user_id = result['user']['id']
        print(f"    ✅ Created ID={user_id}")
        
        # 2. Build a realistic portfolio (5-12 stocks)
        num_stocks = random.randint(5, min(12, len(stocks_pool)))
        selected = random.sample(stocks_pool, num_stocks)
        
        stocks = []
        for ticker, low, high in selected:
            price = round(random.uniform(low, high), 2)
            # Realistic quantities: cheaper stocks get more shares
            if price < 50:
                qty = random.randint(20, 200)
            elif price < 150:
                qty = random.randint(10, 80)
            elif price < 400:
                qty = random.randint(5, 40)
            else:
                qty = random.randint(2, 20)
            
            stocks.append({
                'ticker': ticker,
                'quantity': qty,
                'purchase_price': price
            })
        
        result, _ = api_call('/admin/bot/add-stocks', 'POST', {
            'user_id': user_id,
            'stocks': stocks
        })
        
        if result.get('success'):
            print(f"    📊 Added {len(stocks)} stocks")
        
        # 3. Gift some initial subscribers (1-8, weighted toward lower)
        sub_count = random.choices(
            [1, 2, 3, 4, 5, 6, 7, 8],
            weights=[25, 20, 15, 12, 10, 8, 5, 5],
            k=1
        )[0]
        
        result, _ = api_call('/admin/bot/gift-subscribers', 'POST', {
            'user_id': user_id,
            'count': sub_count
        })
        
        if result.get('success'):
            print(f"    👥 Gifted {sub_count} subscribers")
        
        created.append({
            'user_id': user_id,
            'username': username,
            'industry': industry,
            'stocks': len(stocks),
            'subscribers': sub_count
        })
        
        # Small delay between creations to look natural
        time.sleep(random.uniform(0.3, 0.8))
    
    return created


def seed_all_industries(bots_per_industry=3):
    """Seed bots across all industries"""
    industries = list(INDUSTRY_STOCKS.keys())
    all_created = []
    
    for industry in industries:
        print(f"\n{'='*50}")
        print(f"  Industry: {industry} ({bots_per_industry} bots)")
        print(f"{'='*50}")
        
        created = seed_bots(industry, bots_per_industry)
        all_created.extend(created)
        time.sleep(random.uniform(0.5, 1.5))
    
    return all_created


# ── Trading Simulation ──────────────────────────────────────────────────────

def simulate_trades(rounds=1):
    """
    Execute realistic trades for active bots.
    Each round, a random subset of bots will make 0-2 trades.
    """
    # Get all active bots
    result, _ = api_call('/admin/bot/list-users?role=agent')
    bots = [u for u in (result.get('users') or []) if u.get('bot_active') is not False]
    
    if not bots:
        print("  No active bots found.")
        return
    
    print(f"\n  Found {len(bots)} active bots")
    
    for round_num in range(1, rounds + 1):
        print(f"\n  ── Round {round_num}/{rounds} ──")
        
        # Pick ~30-60% of bots to trade this round
        trade_count = max(1, int(len(bots) * random.uniform(0.3, 0.6)))
        traders = random.sample(bots, min(trade_count, len(bots)))
        
        for bot in traders:
            user_id = bot['id']
            username = bot['username']
            industry = bot.get('industry', 'General')
            stocks_pool = INDUSTRY_STOCKS.get(industry, INDUSTRY_STOCKS['General'])
            
            # Decide: buy new stock, or sell existing?
            # 60% buy, 40% sell (if they have stocks)
            if bot['stock_count'] > 0 and random.random() < 0.4:
                # Sell a portion of an existing holding
                trade_type = 'sell'
                # Pick a random stock from their portfolio to sell
                # We don't know exact holdings, so pick from their industry pool
                ticker, low, high = random.choice(stocks_pool)
                price = round(random.uniform(low, high), 2)
                qty = random.randint(1, 5)
                
                result, status = api_call('/admin/bot/execute-trade', 'POST', {
                    'user_id': user_id,
                    'ticker': ticker,
                    'quantity': qty,
                    'price': price,
                    'type': 'sell'
                })
                
                if result.get('success'):
                    print(f"    {username}: SELL {qty} {ticker} @ ${price}")
                elif result.get('error') == 'insufficient_shares':
                    # Try a buy instead
                    trade_type = 'buy'
                    result, _ = api_call('/admin/bot/execute-trade', 'POST', {
                        'user_id': user_id,
                        'ticker': ticker,
                        'quantity': qty,
                        'price': price,
                        'type': 'buy'
                    })
                    if result.get('success'):
                        print(f"    {username}: BUY {qty} {ticker} @ ${price}")
            else:
                # Buy a stock
                ticker, low, high = random.choice(stocks_pool)
                price = round(random.uniform(low, high), 2)
                if price < 50:
                    qty = random.randint(5, 30)
                elif price < 150:
                    qty = random.randint(3, 15)
                elif price < 400:
                    qty = random.randint(1, 8)
                else:
                    qty = random.randint(1, 4)
                
                result, _ = api_call('/admin/bot/execute-trade', 'POST', {
                    'user_id': user_id,
                    'ticker': ticker,
                    'quantity': qty,
                    'price': price,
                    'type': 'buy'
                })
                
                if result.get('success'):
                    print(f"    {username}: BUY {qty} {ticker} @ ${price}")
            
            # Human-like delay between trades
            time.sleep(random.uniform(0.2, 1.0))
        
        # Delay between rounds
        if round_num < rounds:
            delay = random.uniform(1, 3)
            print(f"\n  Waiting {delay:.1f}s before next round...")
            time.sleep(delay)


# ── Status ──────────────────────────────────────────────────────────────────

def show_status():
    """Display current dashboard status"""
    result, _ = api_call('/admin/bot/dashboard')
    
    print(f"\n  {'='*40}")
    print(f"  Apes Together — Bot Dashboard Status")
    print(f"  {'='*40}")
    print(f"  Total Users:       {result.get('total_users', '?')}")
    print(f"  Human Users:       {result.get('human_users', '?')}")
    print(f"  Bot Users:         {result.get('bot_users', '?')}")
    print(f"  Active Bots:       {result.get('active_bots', '?')}")
    print(f"  Inactive Bots:     {result.get('inactive_bots', '?')}")
    print(f"  Total Stocks:      {result.get('total_stocks', '?')}")
    print(f"  Total Trades:      {result.get('total_trades', '?')}")
    print(f"  Subscriptions:     {result.get('total_subscriptions', '?')}")
    print(f"  Gifted Subs:       {result.get('gifted_subscriptions', '?')}")
    
    breakdown = result.get('industry_breakdown', {})
    if breakdown:
        print(f"\n  Industry Breakdown:")
        for ind, count in sorted(breakdown.items(), key=lambda x: -x[1]):
            print(f"    {ind:20s} {count} bots")
    
    print()


# ── CLI ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description='Apes Together Bot Agent')
    parser.add_argument('--action', required=True,
                        choices=['seed', 'seed-all', 'trade', 'gift', 'status'],
                        help='Action to perform')
    parser.add_argument('--count', type=int, default=3,
                        help='Number of bots to create (seed) or subscribers to gift')
    parser.add_argument('--industry', type=str, default='Technology',
                        help='Industry for seeding bots')
    parser.add_argument('--bots-per-industry', type=int, default=3,
                        help='Bots per industry for seed-all')
    parser.add_argument('--rounds', type=int, default=1,
                        help='Number of trading rounds')
    parser.add_argument('--user-id', type=int,
                        help='User ID for gift action')
    parser.add_argument('--base-url', type=str,
                        help='Override API base URL')
    
    args = parser.parse_args()
    
    global API_BASE, ADMIN_KEY
    if args.base_url:
        API_BASE = args.base_url
    
    if not ADMIN_KEY:
        print("❌ ADMIN_API_KEY environment variable not set")
        print("   Set it with: export ADMIN_API_KEY=your_key_here")
        sys.exit(1)
    
    print(f"\n🦍 Apes Together Bot Agent")
    print(f"   API: {API_BASE}")
    print(f"   Action: {args.action}")
    
    if args.action == 'seed':
        created = seed_bots(args.industry, args.count)
        print(f"\n✅ Created {len(created)} bots in {args.industry}")
        
    elif args.action == 'seed-all':
        created = seed_all_industries(args.bots_per_industry)
        print(f"\n✅ Created {len(created)} bots across all industries")
        
    elif args.action == 'trade':
        simulate_trades(args.rounds)
        print(f"\n✅ Trading simulation complete")
        
    elif args.action == 'gift':
        if not args.user_id:
            print("❌ --user-id required for gift action")
            sys.exit(1)
        result, _ = api_call('/admin/bot/gift-subscribers', 'POST', {
            'user_id': args.user_id,
            'count': args.count
        })
        if result.get('success'):
            print(f"\n✅ Gifted {args.count} subscribers to user {args.user_id}")
            print(f"   New total: {result.get('new_subscriber_count')}")
        else:
            print(f"\n❌ Gift failed: {result.get('error')}")
        
    elif args.action == 'status':
        show_status()


if __name__ == '__main__':
    main()
