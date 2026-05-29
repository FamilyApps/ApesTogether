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
CRON_SECRET = os.environ.get('CRON_SECRET', '')


# ── API Communication ────────────────────────────────────────────────────────

def api_call(endpoint, method='GET', data=None, timeout=30):
    """Make an authenticated admin API call."""
    headers = {
        'X-Cron-Secret': CRON_SECRET,
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
            logger.error("AUTH ERROR: Invalid cron secret")
            return {'error': 'invalid_cron_secret'}, 403
        return result, resp.status_code
    except requests.exceptions.Timeout:
        logger.warning(f"API timeout: {endpoint}")
        return {'error': 'timeout'}, 504
    except Exception as e:
        logger.warning(f"API error: {endpoint} → {e}")
        return {'error': str(e)}, 500


# ── Bot Discovery ────────────────────────────────────────────────────────────

def get_active_bots():
    """Fetch all active bot accounts from the API.

    Filters out:
      - bots with bot_active explicitly set to False (admin-disabled)
      - copytrade bots (those trade only via the Public.com email
        pipeline; running them through the wave would cause double
        trades / wrong signals). Source of truth for copytrade_bot
        is _is_copytrade_bot() in mobile_api.py; the flag is
        included in the /admin/bot/list-users response.
    """
    result, status = api_call('/admin/bot/list-users?role=agent')
    if status != 200:
        logger.error(f"Failed to fetch bots: {status}")
        return []

    bots = result.get('users', [])
    active = [b for b in bots if b.get('bot_active') is not False]
    copytrade_excluded = [b for b in active if b.get('copytrade_bot')]
    autonomous = [b for b in active if not b.get('copytrade_bot')]
    logger.info(
        f"Found {len(autonomous)} active autonomous bots "
        f"(of {len(bots)} total, {len(copytrade_excluded)} copytrade excluded)"
    )
    return autonomous


def get_bot_holdings(user_id):
    """
    Get a bot's current stock holdings via admin API.
    Returns list of {ticker, quantity, purchase_price}
    """
    result, status = api_call(f'/admin/bot/holdings?user_id={user_id}')
    if status == 200:
        return result.get('holdings', [])
    return []


def get_bot_account(user_id):
    """
    Get a bot's holdings AND uninvested cash in a single admin API call.
    Returns (holdings: list, cash: float). Used by the trade runner so BUY
    sizing reflects total buying power (stock + cash) and idle-cash
    redeployment can run — see _estimate_portfolio_value / generate_trade_decisions.
    Falls back to ([], 0.0) on error.
    """
    result, status = api_call(f'/admin/bot/holdings?user_id={user_id}')
    if status == 200:
        holdings = result.get('holdings', [])
        cash = float(result.get('cash', result.get('cash_proceeds', 0)) or 0)
        return holdings, cash
    return [], 0.0


# ── Trade Execution ──────────────────────────────────────────────────────────

def execute_trade(user_id, ticker, quantity, price, trade_type, reason='', price_source=None):
    """
    Execute a single trade via the admin API.

    Args:
        user_id: bot's user ID
        ticker: stock ticker symbol
        quantity: number of shares
        price: execution price
        trade_type: 'buy' or 'sell'
        reason: human-readable reason for the trade (logged locally only)
        price_source: optional compact label persisted to Transaction.price_source
            and surfaced in the admin Recent Trades 'Source' column. Examples:
            'bot_rsi', 'bot_news', 'bot_insider', 'bot_stoploss', 'bot_takeprofit',
            'bot_fomo'. Defaults to 'bot_research' on the API side if omitted.

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
    if price_source:
        data['price_source'] = price_source

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

    # Fetch holdings ONCE per bot (one HTTP call). Used for two things:
    #   1. Computing real portfolio_value for BUY position sizing.
    #   2. Clamping SELL quantities to actual held shares so we don't
    #      hit /admin/bot/execute-trade's insufficient_shares gate.
    #
    # Before this change, _estimate_portfolio_value() returned a hardcoded
    # $100K and SELLs were sized off that allocation, producing qty=35 for
    # a bot that only owned 5 shares — every SELL failed silently. See
    # wave 2 on 2026-05-20 where 7+ valid sell decisions executed 0 trades.
    holdings, cash = get_bot_account(user_id)
    held_by_ticker = {h['ticker']: h['quantity'] for h in holdings}
    # Include cash so BUY sizing reflects total buying power. This is what lets
    # a cash-heavy bot actually deploy its idle cash instead of sizing new buys
    # off a tiny remaining stock value (the cash-accumulation bug).
    portfolio_value = _estimate_portfolio_value(
        user_id, holdings=holdings, market_hub=market_hub, cash=cash)

    # Shuffle decisions slightly (humans don't execute in perfect order)
    random.shuffle(decisions)

    for decision in decisions:
        action = decision['action']
        ticker = decision['ticker']
        reason = decision.get('reason', '')

        # Map the strategy's signal_tag to a Transaction.price_source value
        # so the admin Recent Trades card can show what drove this trade.
        # `signal_tag` examples from bot_strategies / bot_behaviors:
        #   'rsi', 'macd', 'news', 'social', 'volume', 'insider', 'trend',
        #   'mover', 'mixed', 'stoploss', 'takeprofit', 'fomo'
        signal_tag = decision.get('signal_tag') or 'mixed'
        price_source = f"bot_{signal_tag}"

        # SELL guard: if the bot doesn't hold this ticker, the trade
        # cannot succeed — skip immediately with a clear info log
        # (visible at default INFO level, unlike the old debug-only
        # "Insufficient shares" line that hid the wave-2 bug).
        held_qty = held_by_ticker.get(ticker, 0)
        if action == 'sell' and held_qty <= 0:
            logger.info(f"  Skipping SELL {ticker}: bot holds 0 shares")
            continue

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

        # Calculate position size. For sells, held_qty caps the result.
        quantity = calculate_position_size(
            decision, bot_profile, portfolio_value,
            held_qty=held_qty if action == 'sell' else None,
        )
        if quantity <= 0:
            # SELL path returned 0 — caller should skip (defensive; the
            # held_qty <= 0 guard above should have caught this already).
            continue

        # Execute
        success, result = execute_trade(user_id, ticker, quantity, price, action, reason, price_source=price_source)

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
            # Update local holdings tally so a same-wave second decision
            # on the same ticker (rare, but possible) sees the new qty.
            if action == 'sell':
                held_by_ticker[ticker] = max(0, held_qty - quantity)
            else:
                held_by_ticker[ticker] = held_qty + quantity
        elif action == 'sell' and result.get('error') == 'insufficient_shares':
            # Belt-and-suspenders: clamp+retry once. This should be rare
            # now that held_qty drives sizing, but races (e.g. a manual
            # sell between get_bot_holdings and execute_trade) can still
            # happen. Retry at half the held qty.
            reduced_qty = max(1, min(quantity, held_qty) // 2)
            if reduced_qty != quantity and reduced_qty > 0:
                success2, _ = execute_trade(
                    user_id, ticker, reduced_qty, price, action,
                    reason + ' (reduced qty)', price_source=price_source)
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
                    held_by_ticker[ticker] = max(0, held_qty - reduced_qty)

        # Human-like delay between trades
        delay = add_trade_delay()
        time.sleep(delay)

    if executed:
        buys = sum(1 for t in executed if t['action'] == 'buy')
        sells = sum(1 for t in executed if t['action'] == 'sell')
        logger.info(f"  {username}: executed {buys} buys, {sells} sells")

    return executed


# ── Portfolio Helpers ─────────────────────────────────────────────────────────

def _estimate_portfolio_value(user_id, holdings=None, market_hub=None, cash=0.0):
    """
    Estimate a bot's portfolio value (used for BUY position sizing).

    Args:
        user_id: bot's user ID (kept for signature compat; not used when
            holdings + market_hub are passed in)
        holdings: optional list of {ticker, quantity, purchase_price} from
            get_bot_holdings(). When provided alongside market_hub, returns
            the real mark-to-market value.
        market_hub: optional MarketDataHub used to look up current prices.

        cash: the bot's uninvested cash_proceeds. INCLUDED in the returned
            value so BUY position sizing reflects total buying power. This is
            the fix for the cash-accumulation bug: previously cash was excluded,
            so a bot that had liquidated to 90% cash sized new buys off its tiny
            remaining stock value and could never redeploy.

    Returns:
        float: portfolio value (stock mark-to-market + cash) in dollars.
            Falls back to $100K only when market_hub isn't supplied.

    Notes:
        - When market_hub has no price for a held ticker, purchase_price
          is used as a fallback so the estimate stays reasonable.
    """
    if market_hub is None:
        # Legacy / fallback path — kept so older callers / unit tests don't
        # break (without a market_hub we can't mark-to-market). Production
        # callers in execute_bot_decisions always supply it.
        return 100_000.0 + (cash or 0.0)

    total = 0.0
    for h in (holdings or []):
        ticker = h.get('ticker')
        qty = h.get('quantity', 0) or 0
        if qty <= 0:
            continue
        price = 0.0
        try:
            stock_data = market_hub.get_stock_data(ticker)
            if stock_data:
                price = float(stock_data.get('price', 0) or 0)
        except Exception:
            price = 0.0
        if price <= 0:
            # Fallback to purchase_price — better than dropping the position
            price = float(h.get('purchase_price', 0) or 0)
        total += qty * price

    # Floor at $1K so a bot with empty holdings still sizes new BUYs to
    # something meaningful instead of qty=0 for everything. Cash is added so
    # a cash-heavy bot's buying power is fully reflected in position sizing.
    return max(1_000.0, total + (cash or 0.0))


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
