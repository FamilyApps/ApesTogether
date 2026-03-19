"""
Seed two copy-trading bots for Public.com portfolio email notifications:
  1. Grok Portfolio bot
  2. Wolff's Flagship Fund bot

These bots will have their trades populated by the Google Apps Script
email parser (public_email_parser.gs) which watches for Public.com
trade notification emails and calls the /admin/bot/email-trade endpoint.

Usage:
    python scripts/seed_copytrade_bots.py

Requires: ADMIN_API_KEY in .env or environment
"""
import os
import sys
import json
import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from bot_personas import generate_username

API_BASE = os.environ.get('API_BASE_URL', 'https://apestogether.ai/api/mobile')
ADMIN_KEY = os.environ.get('ADMIN_API_KEY')

if not ADMIN_KEY:
    print("ERROR: ADMIN_API_KEY not set")
    sys.exit(1)

HEADERS = {
    'Content-Type': 'application/json',
    'X-Admin-Key': ADMIN_KEY
}

BOTS = [
    {
        'label': 'Grok Portfolio',
        'source': 'grok_portfolio',
        'industry': 'Technology',
        'strategy': 'AI/Tech-focused growth portfolio managed by xAI Grok',
    },
    {
        'label': "Wolff's Flagship Fund",
        'source': 'wolffs_flagship',
        'industry': 'Diversified',
        'strategy': "Diversified growth fund managed by Wolff Research",
    },
]


def create_bot(label, industry, strategy_desc):
    """Create a bot account via the admin API."""
    username = generate_username()
    email = f"{username.lower()}@bot.apestogether.ai"
    
    print(f"\n{'='*50}")
    print(f"Creating bot for: {label}")
    print(f"  Username: {username}")
    print(f"  Email: {email}")
    print(f"  Industry: {industry}")
    
    # Create user via admin API
    resp = requests.post(f"{API_BASE}/admin/bot/create-user", headers=HEADERS, json={
        'username': username,
        'email': email,
        'industry': industry,
        'trading_style': 'copytrade',
        'notes': f'Copy-trading bot for {label}. {strategy_desc}'
    })
    
    if resp.status_code == 200:
        data = resp.json()
        user_id = data.get('user', {}).get('id') or data.get('user_id')
        print(f"  [OK] Created! user_id={user_id}")
        
        # Gift some subscribers for visibility
        sub_resp = requests.post(f"{API_BASE}/admin/bot/gift-subscribers", headers=HEADERS, json={
            'user_id': user_id,
            'count': 3
        })
        if sub_resp.status_code == 200:
            print(f"  [+] Gifted 3 subscribers")
        
        return {'user_id': user_id, 'username': username, 'label': label}
    else:
        print(f"  [FAIL] {resp.status_code} {resp.text}")
        return None


def main():
    print("[*] Seeding Copy-Trading Bots for Apes Together")
    print(f"   API: {API_BASE}")
    
    created = []
    for bot_config in BOTS:
        result = create_bot(bot_config['label'], bot_config['industry'], bot_config['strategy'])
        if result:
            result['source'] = bot_config['source']
            created.append(result)
    
    print(f"\n{'='*50}")
    print(f"[OK] Created {len(created)}/{len(BOTS)} bots\n")
    
    print("Google Apps Script Configuration:")
    print("   Set these as Script Properties in your Google Apps Script project:\n")
    
    for bot in created:
        prop_name = f"{'GROK' if 'grok' in bot['source'] else 'WOLFF'}_BOT_USERNAME"
        print(f"   {prop_name} = {bot['username']}")
    
    print(f"   ADMIN_API_KEY = (your admin key)")
    print(f"   API_BASE_URL = {API_BASE}")
    
    print(f"\nBot Summary:")
    for bot in created:
        print(f"   {bot['label']}: username={bot['username']}, user_id={bot['user_id']}")


if __name__ == '__main__':
    main()
