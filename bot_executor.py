"""
Bot Trade Executor
===================
Executes trade decisions via the admin API. Handles position sizing,
API communication, error handling, and trade logging.
"""

import os
import sys
import time
import random
import logging
import requests
from datetime import datetime

logger = logging.getLogger('bot_executor')

API_BASE = os.environ.get('API_BASE_URL', 'https://apestogether.ai/api/mobile')
ADMIN_KEY = os.environ.get('ADMIN_API_KEY', '')


# ── API Communication ────────────────────────────────────────────────────────

def api_call(endpoint, method='GET', data=None, timeout=30):
    """Make an authenticated admin API call."""
    headers = {
        'X-Admin-Key': ADMIN_KEY,
        'Content-Type': 'application/json'
    }
    url = f"{API_BASE}{endpoint}"

    try:
        if method == 'GET':
            resp = requests.get(url, headers=headers, timeout=timeout)
        else:
            resp = requests.post(url, headers=headers, json=data, timeout=timeout)

        result = resp.json()
        if resp.status_code == 403:
            logger.error("AUTH ERROR: Invalid admin key")
            return {'error': 'invalid_admin_key'}, 403
        return result, resp.status_code
    except requests.exceptions.Timeout:
        logger.warning(f"API timeout: {endpoint}")
        return {'error': 'timeout'}, 504
    except Exception as e:
        logger.warning(f"API error: {endpoint} → {e}")
        return {'error': str(e)}, 500


# ── Bot Discovery ────────────────────────────────────────────────────────────

def get_active_bots():
    """Fetch all active bot accounts from the API."""
    result, status = api_call('/admin/bot/list-users?role=agent')
    if status != 200:
        logger.error(f"Failed to fetch bots: {status}")
        return []

    bots = result.get('users', [])
    active = [b for b in bots if b.get('bot_active') is not False]
    logger.info(f"Found {len(active)} active bots (of {len(bots)} total)")
    return active


def get_bot_holdings(user_id):
    """
    Get a bot's current stock holdings via admin API.
    Returns list of {ticker, quantity, purchase_price}
    """
    result, status = api_call(f'/admin/bot/holdings?user_id={user_id}')
    if status == 200:
        return result.get('holdings', [])
    return []


# ── Trade Execution ──────────────────────────────────────────────────────────

def execute_trade(user_id, ticker, quantity, price, trade_type, reason=''):
    """
    Execute a single trade via the admin API.

    Args:
        user_id: bot's user ID
        ticker: stock ticker symbol
        quantity: number of shares
        price: execution price
        trade_type: 'buy' or 'sell'
        reason: human-readable reason for the trade

    Returns:
        (success: bool, result: dict)
    """
    if quantity <= 0 or price <= 0:
        logger.warning(f"Invalid trade params: qty={quantity}, price={price}")
        return False, {'error': 'invalid_params'}

    data = {
        'user_id': user_id,
        'ticker': ticker,
        'quantity': quantity,
        'price': price,
        'type': trade_type,
    }

    result, status = api_call('/admin/bot/execute-trade', 'POST', data)

    if result.get('success'):
        logger.info(f"  {trade_type.upper()} {quantity} {ticker} @ ${price:.2f} "
                     f"(user_id={user_id}) — {reason}")
        return True, result
    else:
        error = result.get('error', 'unknown')
        if error == 'insufficient_shares' and trade_type == 'sell':
            logger.debug(f"  Insufficient shares for SELL {ticker} (user_id={user_id})")
        else:
            logger.warning(f"  Trade failed: {trade_type} {ticker} — {error}")
        return False, result


def execute_bot_decisions(user_id, username, decisions, bot_profile, market_hub):
    """
    Execute all trade decisions for a single bot.

    Args:
        user_id: bot's user ID
        username: bot's display name (for logging)
        decisions: list of {action, ticker, score, reason, price, ...}
        bot_profile: bot's strategy profile
        market_hub: MarketDataHub for current prices

    Returns:
        list of executed trades
    """
    from bot_behaviors import calculate_position_size, add_trade_delay

    executed = []
    portfolio_value = _estimate_portfolio_value(user_id)

    # Shuffle decisions slightly (humans don't execute in perfect order)
    random.shuffle(decisions)

    for decision in decisions:
        action = decision['action']
        ticker = decision['ticker']
        reason = decision.get('reason', '')

        # Get current price from market hub (most recent)
        stock_data = market_hub.get_stock_data(ticker)
        if stock_data:
            price = stock_data.get('price', decision.get('price', 0))
        else:
            price = decision.get('price', 0)

        if price <= 0:
            logger.warning(f"  Skipping {ticker}: no price data")
            continue

        # Add tiny price noise (simulates market spread / slight delay)
        spread_pct = random.uniform(-0.001, 0.001)
        price = round(price * (1 + spread_pct), 2)

        # Calculate position size
        quantity = calculate_position_size(decision, bot_profile, portfolio_value)

        # Execute
        success, result = execute_trade(user_id, ticker, quantity, price, action, reason)

        if success:
            executed.append({
                'action': action,
                'ticker': ticker,
                'quantity': quantity,
                'price': price,
                'reason': reason,
                'score': decision.get('score', 0),
                'is_fomo': decision.get('is_fomo', False),
                'timestamp': datetime.utcnow().isoformat(),
            })
        elif action == 'sell' and result.get('error') == 'insufficient_shares':
            # Try selling fewer shares
            reduced_qty = max(1, quantity // 2)
            if reduced_qty != quantity:
                success2, result2 = execute_trade(
                    user_id, ticker, reduced_qty, price, action,
                    reason + ' (reduced qty)')
                if success2:
                    executed.append({
                        'action': action,
                        'ticker': ticker,
                        'quantity': reduced_qty,
                        'price': price,
                        'reason': reason + ' (partial)',
                        'score': decision.get('score', 0),
                        'timestamp': datetime.utcnow().isoformat(),
                    })

        # Human-like delay between trades
        delay = add_trade_delay()
        time.sleep(delay)

    if executed:
        buys = sum(1 for t in executed if t['action'] == 'buy')
        sells = sum(1 for t in executed if t['action'] == 'sell')
        logger.info(f"  {username}: executed {buys} buys, {sells} sells")

    return executed


# ── Portfolio Helpers ─────────────────────────────────────────────────────────

def _estimate_portfolio_value(user_id):
    """
    Rough estimate of a bot's portfolio value.
    For position sizing — doesn't need to be exact.
    Default to $100K simulated portfolio if we can't fetch.
    """
    # In a real implementation, this would query the DB
    # For now, use a reasonable default
    return 100_000


# ── Bot Account Management ───────────────────────────────────────────────────

def create_bot_account(username, email, industry, strategy_profile):
    """
    Create a new bot account and configure it with a strategy profile.

    Returns:
        (user_id, success: bool)
    """
    # Create user
    result, status = api_call('/admin/bot/create-user', 'POST', {
        'username': username,
        'email': email,
        'industry': industry,
    })

    if status == 409:
        # Username taken — append random suffix
        username = username + str(random.randint(100, 999))
        email = f"{username.replace('-', '.').replace('_', '.')}@apestogether.ai"
        result, status = api_call('/admin/bot/create-user', 'POST', {
            'username': username,
            'email': email,
            'industry': industry,
        })

    if not result.get('success'):
        logger.error(f"Failed to create bot {username}: {result.get('error')}")
        return None, False

    user_id = result['user']['id']

    # Store strategy profile in bot config
    config_data = {
        'user_id': user_id,
        'industry': industry,
        'trading_style': strategy_profile.get('strategy', 'balanced'),
        'trade_frequency': strategy_profile.get('trade_frequency', 'daily'),
        'max_stocks': strategy_profile.get('max_positions', 8),
        'notes': f"Strategy: {strategy_profile.get('strategy')} | "
                 f"Life stage: {strategy_profile.get('life_stage', 'unknown')} | "
                 f"Risk: {strategy_profile.get('risk_tolerance', 0.5):.2f}",
    }
    api_call('/admin/bot/update-config', 'POST', config_data)

    return user_id, True


def _generate_portfolio_size():
    """
    Generate a realistic random portfolio size based on American stock holdings.
    Uses a log-normal distribution:
      - Median ~$40K (typical retail investor)
      - Range roughly $5K–$500K
      - Right-skewed: most portfolios are smaller, few are very large
    """
    import math
    # Log-normal: mu=10.6, sigma=0.9 gives median ~$40K, mean ~$60K
    raw = random.lognormvariate(10.6, 0.9)
    # Clamp to $5K–$500K
    return max(5_000, min(500_000, raw))


def seed_initial_portfolio(user_id, strategy_profile, market_hub):
    """
    Give a new bot an initial portfolio of stocks based on its strategy.
    Uses real market prices from the data hub.
    """
    attention = strategy_profile.get('attention_universe', [])
    if not attention:
        logger.warning(f"Bot {user_id} has empty attention universe")
        return 0

    # Pick 4-10 stocks to start with
    num_stocks = random.randint(4, min(10, len(attention)))
    selected = random.sample(attention, num_stocks)

    # Realistic random portfolio size (not a fixed $100K)
    portfolio_size = _generate_portfolio_size()
    logger.info(f"  Portfolio size for user_id={user_id}: ${portfolio_size:,.0f}")

    stocks = []
    for ticker in selected:
        stock_data = market_hub.get_stock_data(ticker)
        if not stock_data:
            continue

        price = stock_data.get('price', 0)
        if price <= 0:
            continue

        # Calculate initial quantity based on randomized portfolio size
        allocation = portfolio_size / num_stocks
        qty = max(1, int(allocation / price))

        # Human noise on quantity
        qty = max(1, int(qty * random.uniform(0.7, 1.3)))

        # Round to human-like numbers
        if qty > 20:
            qty = round(qty / 5) * 5
        elif qty > 10:
            qty = round(qty / 2) * 2

        # Slightly vary purchase price (simulates buying over past days)
        price_noise = random.uniform(-0.02, 0.02)
        purchase_price = round(price * (1 + price_noise), 2)

        stocks.append({
            'ticker': ticker,
            'quantity': qty,
            'purchase_price': purchase_price,
        })

    if not stocks:
        return 0

    result, _ = api_call('/admin/bot/add-stocks', 'POST', {
        'user_id': user_id,
        'stocks': stocks,
    })

    if result.get('success'):
        logger.info(f"  Seeded {len(stocks)} stocks for user_id={user_id}")
        return len(stocks)
    else:
        logger.warning(f"  Failed to seed stocks for user_id={user_id}")
        return 0


def gift_subscribers(user_id, count):
    """Gift fake subscribers to a bot account."""
    result, _ = api_call('/admin/bot/gift-subscribers', 'POST', {
        'user_id': user_id,
        'count': count,
    })
    return result.get('success', False)


# ── Dashboard / Status ───────────────────────────────────────────────────────

def get_dashboard_stats():
    """Fetch bot dashboard summary stats."""
    result, _ = api_call('/admin/bot/dashboard')
    return result
