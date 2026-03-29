"""
Seed copy-trading bot portfolios with current holdings.
Converts dollar amounts to share quantities using current market prices.

Usage:
    python scripts/seed_bot_holdings.py
"""
import os
import sys
import json
import requests
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

API_BASE = os.environ.get('API_BASE_URL', 'https://apestogether.ai/api/mobile')
CRON_SECRET = os.environ.get('CRON_SECRET')
AV_KEY = os.environ.get('ALPHA_VANTAGE_API_KEY')

if not CRON_SECRET:
    print("ERROR: CRON_SECRET not set")
    sys.exit(1)

HEADERS = {
    'Content-Type': 'application/json',
    'X-Cron-Secret': CRON_SECRET
}

# Wolff's Flagship Fund — user_id=14, username=CoastHillBear
WOLFF_HOLDINGS = {
    'user_id': 14,
    'cash': 21.39,
    'stocks': {
        'SGOV': 1986.53, 'GLTR': 931.81, 'IREN': 857.51, 'CIFR': 570.14,
        'META': 498.21, 'AMD': 369.10, 'AMZN': 361.44, 'NVDA': 357.99,
        'MCO': 354.95, 'AVGO': 350.81, 'MSFT': 350.36, 'REGN': 343.57,
        'BN': 342.17, 'MELI': 337.64, 'GRAB': 337.25, 'STZ': 333.36,
        'LLY': 327.65, 'PANW': 312.19, 'WULF': 306.30, 'NOW': 302.66,
    }
}

# Grok Portfolio — user_id=13, username=marblethehill72
GROK_HOLDINGS = {
    'user_id': 13,
    'cash': 103.58,
    'stocks': {
        'VST': 1150.78, 'TLN': 1076.78, 'DRS': 1002.58, 'BAH': 994.42,
        'GD': 952.34, 'LMT': 932.08, 'OXY': 906.95, 'DVN': 902.15,
        'TMO': 897.93, 'MTDR': 895.60, 'PEG': 839.24, 'SO': 836.04,
        'CACI': 820.35, 'NEM': 812.93, 'HALO': 767.78,
    }
}


def fetch_price_av(ticker):
    """Fetch current price from AlphaVantage GLOBAL_QUOTE."""
    if not AV_KEY:
        return None
    url = f"https://www.alphavantage.co/query?function=GLOBAL_QUOTE&symbol={ticker}&apikey={AV_KEY}"
    try:
        resp = requests.get(url, timeout=10)
        data = resp.json()
        quote = data.get('Global Quote', {})
        price = float(quote.get('05. price', 0))
        return price if price > 0 else None
    except Exception as e:
        print(f"  AV error for {ticker}: {e}")
        return None


def fetch_prices_batch(tickers):
    """Fetch prices for all tickers. Uses AlphaVantage with rate limiting."""
    prices = {}
    print(f"Fetching prices for {len(tickers)} tickers...")
    
    for i, ticker in enumerate(sorted(tickers)):
        price = fetch_price_av(ticker)
        if price:
            prices[ticker] = price
            print(f"  {ticker}: ${price:.2f}")
        else:
            print(f"  {ticker}: FAILED - will skip")
        
        # AV rate limit: ~75 req/min on premium, be safe
        if (i + 1) % 5 == 0:
            time.sleep(1)
    
    return prices


def seed_portfolio(holdings, label, prices):
    """Seed a bot's portfolio via the admin API."""
    user_id = holdings['user_id']
    cash = holdings['cash']
    
    print(f"\n{'='*60}")
    print(f"Seeding: {label} (user_id={user_id})")
    print(f"Cash: ${cash:.2f}")
    
    stocks_payload = []
    total_stock_value = 0
    
    for ticker, dollar_value in holdings['stocks'].items():
        if ticker not in prices:
            print(f"  SKIP {ticker} - no price available")
            continue
        
        price = prices[ticker]
        # Convert dollar amount to fractional shares (round to 6 decimal places)
        quantity = round(dollar_value / price, 6)
        
        stocks_payload.append({
            'ticker': ticker,
            'quantity': quantity,
            'purchase_price': price
        })
        total_stock_value += dollar_value
        print(f"  {ticker}: ${dollar_value:.2f} / ${price:.2f} = {quantity:.6f} shares")
    
    print(f"\n  Total stock value: ${total_stock_value:.2f}")
    print(f"  Cash: ${cash:.2f}")
    print(f"  Total portfolio: ${total_stock_value + cash:.2f}")
    print(f"  Stocks to add: {len(stocks_payload)}")
    
    # Step 1: Add stocks
    if stocks_payload:
        resp = requests.post(f"{API_BASE}/admin/bot/add-stocks", headers=HEADERS, json={
            'user_id': user_id,
            'stocks': stocks_payload
        })
        if resp.status_code == 200:
            print(f"  [OK] Added {resp.json().get('added_count', 0)} stocks")
        else:
            print(f"  [FAIL] Add stocks: {resp.status_code} {resp.text}")
            return False
    
    # Step 2: Set cash tracking (max_cash_deployed = total portfolio value, cash_proceeds = cash)
    total_value = total_stock_value + cash
    resp = requests.post(f"{API_BASE}/admin/bot/set-cash", headers=HEADERS, json={
        'user_id': user_id,
        'max_cash_deployed': total_value,
        'cash_proceeds': cash
    })
    if resp.status_code == 200:
        print(f"  [OK] Set max_cash_deployed=${total_value:.2f}, cash_proceeds=${cash:.2f}")
    else:
        print(f"  [WARN] Set cash: {resp.status_code} {resp.text}")
        print(f"         (May need manual update if endpoint doesn't exist)")
    
    return True


def main():
    # Collect all unique tickers
    all_tickers = set()
    all_tickers.update(WOLFF_HOLDINGS['stocks'].keys())
    all_tickers.update(GROK_HOLDINGS['stocks'].keys())
    
    print(f"[*] Seeding Bot Portfolio Holdings")
    print(f"    API: {API_BASE}")
    print(f"    Total unique tickers: {len(all_tickers)}\n")
    
    # Fetch all prices
    prices = fetch_prices_batch(all_tickers)
    
    if not prices:
        print("\nERROR: Could not fetch any prices. Check ALPHA_VANTAGE_API_KEY.")
        sys.exit(1)
    
    print(f"\nFetched {len(prices)}/{len(all_tickers)} prices")
    
    # Seed each portfolio
    seed_portfolio(GROK_HOLDINGS, "Grok Portfolio (marblethehill72)", prices)
    seed_portfolio(WOLFF_HOLDINGS, "Wolff's Flagship Fund (CoastHillBear)", prices)
    
    print(f"\n{'='*60}")
    print("[OK] Portfolio seeding complete!")


if __name__ == '__main__':
    main()
