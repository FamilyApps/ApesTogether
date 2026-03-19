"""
Obfuscate bot portfolio values so they don't match the real Public.com account.
Calls /admin/bot/scale-holdings to multiply all quantities and cash by a factor.

Usage:
    python scripts/obfuscate_bot_holdings.py
"""
import os
import sys
import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

API_BASE = os.environ.get('API_BASE_URL', 'https://apestogether.ai/api/mobile')
ADMIN_KEY = os.environ.get('ADMIN_API_KEY')

if not ADMIN_KEY:
    print("ERROR: ADMIN_API_KEY not set")
    sys.exit(1)

HEADERS = {
    'Content-Type': 'application/json',
    'X-Admin-Key': ADMIN_KEY
}

# Different multipliers per bot for extra obfuscation
# Grok: 1.37x  (~$13,892 -> ~$19,032)
# Wolff: 1.52x (~$9,953 -> ~$15,129)
BOTS = [
    {'user_id': 13, 'label': 'Grok Portfolio', 'multiplier': 1.37},
    {'user_id': 14, 'label': "Wolff's Flagship Fund", 'multiplier': 1.52},
]


def main():
    print("[*] Obfuscating Bot Portfolio Values")
    print(f"    API: {API_BASE}")

    for bot in BOTS:
        user_id = bot['user_id']
        label = bot['label']
        multiplier = bot['multiplier']

        print(f"\n{'='*60}")
        print(f"Scaling: {label} (user_id={user_id}, multiplier={multiplier}x)")

        resp = requests.post(f"{API_BASE}/admin/bot/scale-holdings", headers=HEADERS, json={
            'user_id': user_id,
            'multiplier': multiplier
        })

        if resp.status_code == 200:
            data = resp.json()
            print(f"  [OK] Scaled {data.get('stocks_scaled', 0)} stocks")
            cash = data.get('cash_proceeds', {})
            deployed = data.get('max_cash_deployed', {})
            print(f"  Cash: ${cash.get('old', 0):.2f} -> ${cash.get('new', 0):.2f}")
            print(f"  Max deployed: ${deployed.get('old', 0):.2f} -> ${deployed.get('new', 0):.2f}")
            for s in data.get('stocks', []):
                print(f"    {s['ticker']}: {s['old_quantity']:.6f} -> {s['new_quantity']:.6f}")
        else:
            print(f"  [FAIL] {resp.status_code} {resp.text}")

    print(f"\n{'='*60}")
    print("[OK] Obfuscation complete!")


if __name__ == '__main__':
    main()
