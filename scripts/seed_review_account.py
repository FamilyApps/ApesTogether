"""
Seed the app-store reviewer / QA test account with a few starter holdings.

This is a ONE-OFF helper for the account whose email is in models.REVIEW_EMAILS
(default: apestogether.review@gmail.com). That account is a NORMAL role='user'
account -- it is NOT a bot, so no automated bot trades are ever wired to it and
a human reviewer can buy/sell/subscribe/follow exactly like a real user.

Why it is "correct" and won't corrupt charts / % gains going forward
--------------------------------------------------------------------
Holdings are seeded through the SAME code path real trades use:
    POST /api/mobile/admin/bot/add-stocks
which (a) creates the Stock rows, (b) writes 'initial' Transaction rows, and
(c) routes through cash_tracking.process_transaction so User.max_cash_deployed
equals the exact cost basis. Because max_cash_deployed is derived from the same
'initial' transactions the snapshot/max-cash-drift audit replays, the account
reconciles cleanly and the daily market-close cron builds correct snapshots and
performance % from the seed point onward.

To keep the starting P/L near 0%, each position's purchase_price is set to a
near-live quote (keyless Stooq CSV). A tiny non-zero start is expected and fine.

What it does (all idempotent)
-----------------------------
1. Provisions the account server-side via /admin/provision-review-account:
   creates the role='user' row (NOT a bot) if it doesn't exist. No interactive
   "Sign in with Google" is required first -- OAuth links automatically by email
   the first time the actual reviewer signs in on their device.
2. Comps a $0 subscription to a creator (default id=14, Wolff's Flagship Fund)
   so the reviewer sees the premium/subscribed experience. $0 platform='admin'
   IAP -> no payment, no payout, stays out of revenue/Xero.
3. Seeds a diversified starter basket via /admin/bot/add-stocks.

Prerequisites
-------------
- CRON_SECRET is set in your environment or .env (same secret the bot/cron
  scripts already use). API_BASE_URL optionally overrides the prod URL.
- The email is listed in models.REVIEW_EMAILS (the provision endpoint refuses
  any other email).

Usage
-----
    python scripts/seed_review_account.py            # dry-run preview
    python scripts/seed_review_account.py --commit   # provision + subscribe + seed
    python scripts/seed_review_account.py --commit --creator-id 13   # subscribe to Grok instead
"""
import os
import sys
import csv
import io
import argparse

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

API_BASE = os.environ.get('API_BASE_URL', 'https://apestogether.ai/api/mobile')
CRON_SECRET = os.environ.get('CRON_SECRET')

DEFAULT_EMAIL = 'apestogether.review@gmail.com'
DEFAULT_CREATOR_ID = 14  # Wolff's Flagship Fund

# A small, diversified, large-cap starter basket. Recognizable names across
# sectors so a reviewer sees a plausible portfolio. Quantities are computed
# from a live-ish quote to hit ~target_per_position dollars each.
BASKET = ['AAPL', 'MSFT', 'NVDA', 'AMZN', 'JPM']

# Conservative fallback prices used ONLY if a live quote can't be fetched, so
# the script still produces a sane cost basis. Update if wildly stale.
FALLBACK_PRICES = {
    'AAPL': 210.00,
    'MSFT': 450.00,
    'NVDA': 130.00,
    'AMZN': 200.00,
    'JPM': 260.00,
}


def _headers():
    return {'Content-Type': 'application/json', 'X-Cron-Secret': CRON_SECRET}


def fetch_price(ticker):
    """Return a near-live price via Stooq's keyless CSV, or a fallback.

    Stooq end-of-day/last close is close enough to seed a neutral starting
    basis; the app values holdings via AlphaVantage so a small delta is normal.
    """
    url = f"https://stooq.com/q/l/?s={ticker.lower()}.us&f=sd2t2ohlcv&h&e=csv"
    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        row = next(csv.DictReader(io.StringIO(resp.text)))
        close = row.get('Close')
        if close and close.upper() not in ('N/D', ''):
            price = round(float(close), 2)
            if price > 0:
                return price, 'stooq'
    except Exception as e:
        print(f"    ! quote fetch failed for {ticker}: {e}")
    return FALLBACK_PRICES.get(ticker, 100.00), 'fallback'


def find_user(email):
    """Resolve the review account via /admin/bot/list-users (CRON_SECRET auth)."""
    resp = requests.get(f"{API_BASE}/admin/bot/list-users", headers=_headers(), timeout=30)
    resp.raise_for_status()
    users = resp.json().get('users', [])
    email_l = email.strip().lower()
    for u in users:
        if (u.get('email') or '').strip().lower() == email_l:
            return u
    return None


def provision(email, creator_id):
    """Create the role='user' review account (if missing) and comp a subscription
    to `creator_id` (0 to skip), via /admin/provision-review-account."""
    body = {'email': email, 'subscribe_to': creator_id if creator_id else 0}
    resp = requests.post(f"{API_BASE}/admin/provision-review-account", headers=_headers(),
                         json=body, timeout=45)
    if resp.status_code != 200:
        print(f"ERROR: provision failed {resp.status_code}: {resp.text}")
        sys.exit(1)
    return resp.json()


def _build_basket(target_per_position):
    """Fetch near-live prices and compute whole-share quantities for the basket."""
    stocks = []
    est_total = 0.0
    for ticker in BASKET:
        price, src = fetch_price(ticker)
        qty = max(1, int(target_per_position // price))
        cost = qty * price
        est_total += cost
        print(f"  {ticker:<5} {qty:>4} @ ${price:>8.2f}  = ${cost:>10.2f}  ({src})")
        stocks.append({'ticker': ticker, 'quantity': qty, 'purchase_price': price})
    print(f"\n  Estimated capital deployed: ${est_total:,.2f}")
    return stocks


def main():
    parser = argparse.ArgumentParser(description="Provision + subscribe + seed the reviewer/QA account.")
    parser.add_argument('--email', default=DEFAULT_EMAIL, help='Review account email (default: %(default)s)')
    parser.add_argument('--target-per-position', type=float, default=5000.0,
                        help='Approx USD per position (default: %(default)s)')
    parser.add_argument('--creator-id', type=int, default=DEFAULT_CREATOR_ID,
                        help='Creator user_id to comp a subscription to (default: %(default)s = Wolff). 0 to skip.')
    parser.add_argument('--commit', action='store_true',
                        help='Actually provision/subscribe/seed. Without this flag the script only previews.')
    parser.add_argument('--force', action='store_true',
                        help='Seed the basket even if the account already has holdings (may double positions).')
    args = parser.parse_args()

    if not CRON_SECRET:
        print("ERROR: CRON_SECRET not set (put it in your .env or environment).")
        sys.exit(1)

    # ---- Dry-run: show the plan, mutate nothing ----
    if not args.commit:
        sub_plan = (f"comp a subscription to creator id={args.creator_id}"
                    if args.creator_id else "skip the subscription")
        print(f"[dry-run] Would provision {args.email} (role='user', payout-exempt) and {sub_plan}.")
        existing = find_user(args.email)
        if existing:
            print(f"  Account exists: user_id={existing['id']} role={existing.get('role')} "
                  f"stock_count={existing.get('stock_count')}")
        else:
            print("  Account does not exist yet; provisioning will create it.")
        print("\n  Basket that would be seeded:")
        _build_basket(args.target_per_position)
        print("\nDRY-RUN. Re-run with --commit to provision + subscribe + seed.")
        return

    # ---- 1) Provision account + comp subscription ----
    print(f"Provisioning review account: {args.email}")
    prov = provision(args.email, args.creator_id)
    user = prov.get('user', {})
    user_id = user.get('id')
    print(f"  user_id={user_id} username={user.get('username')} role={user.get('role')} "
          f"created={prov.get('created')}")
    sub = prov.get('subscription')
    if sub:
        print(f"  subscription -> {sub.get('creator_name')} (id={sub.get('creator_id')}): "
              f"subscription_id={sub.get('subscription_id')} created={sub.get('created')}")
    elif args.creator_id:
        print("  WARNING: no subscription info returned.")

    if (user.get('role') or 'user') != 'user':
        print(f"ERROR: provisioned role is '{user.get('role')}', expected 'user'. Aborting seed.")
        sys.exit(1)

    # ---- 2) Guard against double-seeding ----
    current = find_user(args.email)
    stock_count = current.get('stock_count', 0) if current else 0
    if stock_count and not args.force:
        print(f"\nAccount already has {stock_count} holdings; skipping seed (subscription is ensured). "
              f"Use --force to add the basket on top.")
        return

    # ---- 3) Seed holdings ----
    print(f"\nBuilding basket (~${args.target_per_position:,.0f} per position):")
    stocks = _build_basket(args.target_per_position)

    print("\nSeeding via /admin/bot/add-stocks ...")
    resp = requests.post(f"{API_BASE}/admin/bot/add-stocks", headers=_headers(),
                         json={'user_id': user_id, 'stocks': stocks}, timeout=60)
    if resp.status_code != 200:
        print(f"ERROR: add-stocks failed {resp.status_code}: {resp.text}")
        sys.exit(1)

    data = resp.json()
    print(f"  [OK] added_count={data.get('added_count')} "
          f"max_cash_deployed=${data.get('max_cash_deployed'):,.2f} "
          f"cash_proceeds=${data.get('cash_proceeds'):,.2f}")
    print("\nDone. The reviewer can now 'Sign in with Google' with these creds and will see a "
          "seeded portfolio plus an active premium subscription. The next market-close cron "
          "creates the baseline PortfolioSnapshot so performance charts populate going forward.")


if __name__ == '__main__':
    main()
