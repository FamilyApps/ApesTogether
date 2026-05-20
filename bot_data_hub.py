"""
Shared Data Hub for Bot Agent Orchestrator
============================================
Fetches market data once for all tracked tickers, computes technical
indicators, and aggregates news/social sentiment. All bots consume
this shared cache — data cost is O(tickers), not O(bots).

Data Sources (May 2026 refactor — AV Premium is now PRIMARY):
    - AlphaVantage Premium ($99.99/mo, 150 calls/min):
        * REALTIME_BULK_QUOTES   — current price for 100 symbols / call (PRIMARY)
        * TIME_SERIES_DAILY      — 100-day OHLCV history per symbol
                                   (used by /api/cron/refresh-daily-bars to
                                    populate the DailyPriceBar cache once
                                    per day post-market)
        * NEWS_SENTIMENT         — topic-based news sentiment
        * TOP_GAINERS_LOSERS     — daily mover screen
    - yfinance (free): bulk OHLCV / quote FALLBACK only — kept for
      resilience against AV outages but Vercel serverless IPs see
      intermittent blocks, so don't rely on it as primary.
    - Finnhub Free (60 calls/min): social sentiment (paid endpoint —
      returns 403 on the free tier), analyst upgrades/downgrades,
      insider transactions.

Architecture:
    During market hours, trade waves read pre-fetched daily bars from the
    `daily_price_bar` table and only call REALTIME_BULK_QUOTES (one batch
    call per 100 tickers) to append the current intraday bar before
    computing indicators. This avoids the 100+ AV calls per wave that
    used to blow Vercel's 60s function timeout.
"""

import os
import time
import json
import logging
import requests
# numpy is required by the technical-indicator + sentiment-aggregation
# functions below, but those only run in the bot-trading pipeline (GitHub
# Actions / a separate worker). On Vercel serverless the 250 MB function
# bundle limit can cause numpy to be stripped from the deployment,
# breaking lightweight admin paths like `probe_finnhub_health` that
# import this module but don't need numpy. Make the import optional so
# those paths keep working — any function that actually uses `np.*` will
# raise NameError at call time, which is exactly the failure mode we
# want for an environment that genuinely needs numpy.
try:
    import numpy as np
except ImportError:
    np = None  # type: ignore[assignment]
from datetime import datetime, timedelta
from collections import defaultdict

logger = logging.getLogger('bot_data_hub')

# ── API Keys ─────────────────────────────────────────────────────────────────

ALPHA_VANTAGE_KEY = os.environ.get('ALPHA_VANTAGE_API_KEY', '')
FINNHUB_KEY = os.environ.get('FINNHUB_API_KEY', '')

# Set FINNHUB_PREMIUM=true (or 1/yes) when the Finnhub key is on a paid plan
# that includes social sentiment + analyst upgrades/downgrades endpoints.
# When unset/false (free tier), those calls are skipped entirely — they would
# otherwise return 403 and only after wasting ~2 min per wave on rate-limit
# pauses + per-ticker request roundtrips. Insider transactions remain enabled
# because Finnhub docs say they're available on the free tier.
FINNHUB_PREMIUM = os.environ.get('FINNHUB_PREMIUM', '').lower() in ('1', 'true', 'yes')

# ── Ticker Universe ──────────────────────────────────────────────────────────
# Master list of all tickers across all industries

UNIVERSE = {
    'Technology': [
        'AAPL', 'MSFT', 'GOOGL', 'NVDA', 'META', 'CRM', 'ADBE', 'INTC',
        'AMD', 'ORCL', 'CSCO', 'SHOP', 'SNOW', 'PLTR', 'NET',
        'TWLO', 'ZS', 'PANW', 'CRWD', 'DDOG', 'MDB', 'TEAM', 'NOW', 'UBER',
    ],
    'Healthcare': [
        'JNJ', 'UNH', 'PFE', 'ABBV', 'LLY', 'MRK', 'TMO', 'ABT',
        'BMY', 'AMGN', 'GILD', 'ISRG', 'VRTX', 'REGN', 'ZTS',
        'MDT', 'SYK', 'EW', 'DXCM', 'IDXX',
    ],
    'Finance': [
        'JPM', 'BAC', 'WFC', 'GS', 'MS', 'BLK', 'SCHW', 'C',
        'AXP', 'V', 'MA', 'COF', 'USB', 'PNC', 'TFC', 'FITB',
    ],
    'Energy': [
        'XOM', 'CVX', 'COP', 'SLB', 'EOG', 'MPC', 'VLO', 'PSX',
        'OKE', 'WMB', 'ENPH', 'FSLR', 'NEE', 'D', 'DUK', 'SO',
    ],
    'Consumer': [
        'AMZN', 'TSLA', 'HD', 'MCD', 'NKE', 'SBUX', 'TGT', 'COST',
        'WMT', 'PG', 'KO', 'PEP', 'DIS', 'LULU', 'NFLX', 'BKNG',
    ],
    'Industrial': [
        'CAT', 'DE', 'HON', 'UPS', 'BA', 'RTX', 'LMT', 'GE',
        'MMM', 'EMR', 'ITW', 'FDX', 'GD', 'NOC', 'WM', 'RSG',
    ],
    'Real Estate': [
        'AMT', 'PLD', 'CCI', 'EQIX', 'PSA', 'SPG', 'O', 'VICI',
        'DLR', 'ARE', 'AVB', 'EQR', 'MAA', 'UDR',
    ],
    'ETF': [
        'SPY', 'QQQ', 'VTI', 'IWM', 'DIA', 'ARKK', 'XLF', 'XLK',
        'XLE', 'XLV', 'GLD', 'TLT', 'VOO', 'SCHD', 'VIG', 'VYM',
    ],
}

def get_all_tickers():
    """Return deduplicated list of all tickers in the universe."""
    seen = set()
    tickers = []
    for sector_tickers in UNIVERSE.values():
        for t in sector_tickers:
            if t not in seen:
                seen.add(t)
                tickers.append(t)
    return tickers

def get_sector_for_ticker(ticker):
    """Return the sector a ticker belongs to."""
    for sector, tickers in UNIVERSE.items():
        if ticker in tickers:
            return sector
    return 'General'


# ── Price Provider (AlphaVantage primary, yfinance fallback) ─────────────────
# Rationale: AV Premium ($99/mo, 150 req/min) provides:
#   - REALTIME_BULK_QUOTES: up to 100 symbols per call for current prices
#   - TIME_SERIES_DAILY: 100-day OHLCV history (per-symbol)
# Trade waves use the cached DailyPriceBar table + REALTIME_BULK_QUOTES for
# the intraday tip; the daily refresh cron uses TIME_SERIES_DAILY concurrently.


# How many seconds between AV calls to stay under 150/min. With a small
# safety margin (140 req/min effective) the inter-call gap is ~0.43s.
_AV_RATE_LIMIT_RPS = 140.0 / 60.0  # ~2.33 req/sec
_AV_MIN_INTERVAL_S = 1.0 / _AV_RATE_LIMIT_RPS


def fetch_realtime_bulk_quotes(tickers, chunk_size=100):
    """
    Fetch current price for `tickers` using AlphaVantage REALTIME_BULK_QUOTES.

    Up to 100 symbols per call. Returns {ticker: {price, change_pct, volume,
    timestamp, source}}. Missing tickers are silently dropped — caller can
    detect by checking the returned dict size vs input.

    This is the PRIMARY realtime-quote path for trade waves. Yields the
    actual intraday price (not yesterday's close) so indicators reflect
    current conditions.
    """
    if not ALPHA_VANTAGE_KEY:
        logger.error("No ALPHA_VANTAGE_API_KEY set — cannot fetch bulk quotes")
        return {}

    quotes = {}
    chunks = [tickers[i:i + chunk_size] for i in range(0, len(tickers), chunk_size)]
    logger.info(f"REALTIME_BULK_QUOTES: {len(tickers)} tickers in {len(chunks)} chunk(s)")

    for chunk_idx, chunk in enumerate(chunks):
        symbols_str = ','.join(chunk)
        url = (f"https://www.alphavantage.co/query?function=REALTIME_BULK_QUOTES"
               f"&symbol={symbols_str}&entitlement=realtime&apikey={ALPHA_VANTAGE_KEY}")
        t0 = time.time()
        try:
            resp = requests.get(url, timeout=15)
            elapsed_ms = int((time.time() - t0) * 1000)
            data = resp.json() if resp.status_code == 200 else {}
            entries = data.get('data') or []
            status_label = 'success' if entries else (
                'rate_limited' if 'Note' in data or 'Information' in data else 'error'
            )
            _log_av_api_call('REALTIME_BULK_QUOTES',
                             f'BULK({len(chunk)})', status_label, elapsed_ms)

            if not entries:
                # Stash the AV response message for diagnostics, but don't
                # raise — partial wave failure is recoverable.
                msg = data.get('Note') or data.get('Information') or data.get('Error Message')
                if msg:
                    logger.warning(f"REALTIME_BULK_QUOTES returned no data: {msg}")
                continue

            for q in entries:
                t = (q.get('symbol') or '').upper()
                if not t:
                    continue
                try:
                    price_raw = q.get('close') or q.get('price') or '0'
                    price = float(price_raw)
                    if price <= 0:
                        continue
                    vol_raw = q.get('volume') or '0'
                    volume = int(float(vol_raw)) if vol_raw else 0
                    quotes[t] = {
                        'price': round(price, 2),
                        'volume': volume,
                        'timestamp': q.get('timestamp'),
                        'source': 'av_bulk',
                    }
                except (ValueError, TypeError):
                    continue

        except Exception as e:
            elapsed_ms = int((time.time() - t0) * 1000)
            _log_av_api_call('REALTIME_BULK_QUOTES',
                             f'BULK({len(chunk)})', 'error', elapsed_ms)
            logger.warning(f"REALTIME_BULK_QUOTES chunk {chunk_idx+1} failed: {e}")

        # Pause between chunks to stay well under 150/min (one bulk call per
        # second is more than safe even at 100 chunks/minute).
        if chunk_idx < len(chunks) - 1:
            time.sleep(_AV_MIN_INTERVAL_S)

    logger.info(f"REALTIME_BULK_QUOTES returned {len(quotes)}/{len(tickers)} tickers")
    return quotes


def _fetch_av_daily_bars_single(ticker):
    """Fetch 100-day OHLCV from AlphaVantage TIME_SERIES_DAILY for one ticker.

    Returns (ticker, DataFrame) on success or (ticker, None) on failure.
    Caller is responsible for rate limiting between calls.
    """
    if np is None:
        # pandas is also a heavy dep; this function should never be called
        # outside the numpy-enabled context (refresh-daily-bars cron).
        raise RuntimeError("pandas/numpy unavailable — daily-bars fetch requires the full bundle")
    import pandas as pd

    t0 = time.time()
    try:
        url = (f"https://www.alphavantage.co/query?function=TIME_SERIES_DAILY"
               f"&symbol={ticker}&outputsize=compact&apikey={ALPHA_VANTAGE_KEY}")
        resp = requests.get(url, timeout=15)
        elapsed_ms = int((time.time() - t0) * 1000)
        data = resp.json() if resp.status_code == 200 else {}
        ts = data.get('Time Series (Daily)') or {}

        if not ts:
            note = data.get('Note') or data.get('Information') or data.get('Error Message')
            status = 'rate_limited' if (note and 'limit' in str(note).lower()) else 'error'
            _log_av_api_call('TIME_SERIES_DAILY', ticker, status, elapsed_ms)
            if note:
                logger.warning(f"TIME_SERIES_DAILY {ticker}: {note}")
            return (ticker, None)

        _log_av_api_call('TIME_SERIES_DAILY', ticker, 'success', elapsed_ms)
        rows = []
        for date_str, vals in ts.items():
            rows.append({
                'Date': pd.Timestamp(date_str),
                'Open': float(vals.get('1. open', 0)),
                'High': float(vals.get('2. high', 0)),
                'Low': float(vals.get('3. low', 0)),
                'Close': float(vals.get('4. close', 0)),
                'Volume': float(vals.get('5. volume', 0)),
            })
        df = pd.DataFrame(rows).set_index('Date').sort_index()
        if len(df) < 20:
            return (ticker, None)
        return (ticker, df)
    except Exception as e:
        elapsed_ms = int((time.time() - t0) * 1000)
        _log_av_api_call('TIME_SERIES_DAILY', ticker, 'error', elapsed_ms)
        logger.warning(f"TIME_SERIES_DAILY {ticker} failed: {e}")
        return (ticker, None)


def fetch_av_daily_bars_concurrent(tickers, max_workers=4):
    """
    Fetch 100-day OHLCV history for `tickers` from AlphaVantage TIME_SERIES_DAILY
    with bounded concurrency. Used by /api/cron/refresh-daily-bars to populate
    the DailyPriceBar cache once per day post-market.

    Returns dict of {ticker: DataFrame[Open,High,Low,Close,Volume]}.

    Rate-limit math (premium 150/min):
        With max_workers=4 and 0.43s gap per worker = ~9.3 calls/sec total.
        That's WAY over the 2.5/sec sustained limit, BUT AV throttles in
        sliding 60s windows so short bursts are fine as long as the total
        per minute stays <= 150. We pace each call to avg ~2.3 req/sec.
    """
    if not ALPHA_VANTAGE_KEY:
        logger.error("No ALPHA_VANTAGE_API_KEY set — cannot fetch daily bars")
        return {}

    from concurrent.futures import ThreadPoolExecutor, as_completed

    result = {}
    n = len(tickers)
    logger.info(f"TIME_SERIES_DAILY concurrent fetch: {n} tickers, workers={max_workers}")
    start = time.time()

    # Token-bucket-ish pacing: stagger submissions so total throughput
    # stays near 2.3 req/sec (140/min effective, well under 150/min limit).
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = []
        for i, ticker in enumerate(tickers):
            futures.append(executor.submit(_fetch_av_daily_bars_single, ticker))
            # Sleep between submissions — this single-threadedly enforces
            # the global rate. With max_workers=4 the workers run in parallel
            # but submissions are paced so the steady-state is ~2.3 req/sec.
            time.sleep(_AV_MIN_INTERVAL_S)

        for fut in as_completed(futures):
            try:
                ticker, df = fut.result()
                if df is not None:
                    result[ticker] = df
            except Exception as e:
                logger.warning(f"Daily-bars worker exception: {e}")

    elapsed = time.time() - start
    logger.info(f"TIME_SERIES_DAILY concurrent fetch: {len(result)}/{n} ok in {elapsed:.1f}s")
    return result


def _load_cached_daily_bars_via_http(tickers, min_bars=20, max_bars=100):
    """Fetch DailyPriceBar cache via HTTP from the Vercel-hosted app.

    Used when running inside GitHub Actions (no DB credentials in CI). The
    app server reads the cache out of Postgres and returns a JSON payload
    we reconstruct into the same `{ticker: DataFrame}` shape the caller
    expects from the direct-DB path.

    Auth: requires CRON_SECRET in env (already set in the GH Actions
    workflow `env:` block). Without it we silently fall through to the
    live-AV path.

    Failure modes (cache unreachable, HTTP timeout, JSON parse error,
    empty response): all degrade gracefully \u2014 we return `{}` and the
    caller's existing fallback to live AV fetch kicks in.
    """
    try:
        import pandas as pd
    except ImportError:
        return {}

    cron_secret = os.environ.get('CRON_SECRET', '')
    if not cron_secret:
        logger.info("No CRON_SECRET in env \u2014 skipping HTTP cache fetch")
        return {}

    base_url = os.environ.get('APP_BASE_URL', 'https://apestogether.ai').rstrip('/')
    url = f"{base_url}/api/cron/get-cached-daily-bars"
    params = {
        'tickers': ','.join(tickers),
        'min_bars': str(min_bars),
        'max_bars': str(max_bars),
    }
    headers = {'X-Cron-Secret': cron_secret}

    t0 = time.time()
    try:
        resp = requests.get(url, params=params, headers=headers, timeout=20)
    except Exception as e:
        logger.warning(f"DailyPriceBar HTTP fetch failed: {e}")
        return {}

    elapsed_ms = int((time.time() - t0) * 1000)

    if resp.status_code != 200:
        logger.warning(
            f"DailyPriceBar HTTP fetch returned HTTP {resp.status_code} "
            f"({elapsed_ms} ms) \u2014 falling back to live AV"
        )
        return {}

    try:
        data = resp.json()
    except Exception as e:
        logger.warning(f"DailyPriceBar HTTP response not JSON: {e}")
        return {}

    if not data.get('success'):
        logger.warning(f"DailyPriceBar HTTP fetch reported failure: "
                       f"{data.get('error') or data.get('message')}")
        return {}

    bars_by_ticker = data.get('bars') or {}
    result = {}
    for ticker, rows in bars_by_ticker.items():
        if not rows or len(rows) < min_bars:
            continue
        recs = []
        for row in rows:
            # row = [date_iso, open, high, low, close, volume]
            try:
                recs.append({
                    'Date': pd.Timestamp(row[0]),
                    'Open': float(row[1]),
                    'High': float(row[2]),
                    'Low': float(row[3]),
                    'Close': float(row[4]),
                    'Volume': float(row[5]),
                })
            except (IndexError, ValueError, TypeError):
                continue
        if len(recs) < min_bars:
            continue
        result[ticker] = pd.DataFrame(recs).set_index('Date').sort_index()

    logger.info(
        f"DailyPriceBar cache hit (via HTTP): {len(result)}/{len(tickers)} tickers "
        f"in {elapsed_ms} ms"
    )
    return result


def _load_cached_daily_bars(tickers, min_bars=20):
    """Load OHLCV bars from the DailyPriceBar cache table.

    Returns {ticker: DataFrame} for tickers with at least `min_bars` rows.
    Tickers with no/insufficient cache rows are omitted.

    Two access paths depending on execution context:
      1. Direct DB query \u2014 used inside Flask app (Vercel serverless).
      2. HTTP fetch from /api/cron/get-cached-daily-bars \u2014 used when
         running inside GitHub Actions (no DB session available in CI).

    The HTTP path is taken whenever we detect a CI environment OR the
    direct-DB query raises (e.g. no Flask app context bound). Both paths
    return identical shapes so the rest of the pipeline is agnostic.
    """
    try:
        import pandas as pd  # noqa: F401  (used downstream)
    except ImportError:
        return {}

    # Detect GitHub Actions context — skip the direct-DB path entirely.
    if os.environ.get('GITHUB_ACTIONS') == 'true':
        return _load_cached_daily_bars_via_http(tickers, min_bars=min_bars)

    try:
        from models import db, DailyPriceBar
        import pandas as pd
    except ImportError:
        # No models module reachable — try HTTP as a last resort.
        return _load_cached_daily_bars_via_http(tickers, min_bars=min_bars)

    try:
        rows = (
            DailyPriceBar.query
            .filter(DailyPriceBar.ticker.in_(tickers))
            .order_by(DailyPriceBar.ticker.asc(), DailyPriceBar.date.asc())
            .all()
        )
    except Exception as e:
        # No Flask app context, no DATABASE_URL, etc. Fall back to HTTP.
        logger.info(f"DailyPriceBar direct-DB query unavailable ({e}); trying HTTP fallback")
        return _load_cached_daily_bars_via_http(tickers, min_bars=min_bars)

    by_ticker = defaultdict(list)
    for r in rows:
        by_ticker[r.ticker].append({
            'Date': pd.Timestamp(r.date),
            'Open': float(r.open) if r.open is not None else float(r.close),
            'High': float(r.high) if r.high is not None else float(r.close),
            'Low': float(r.low) if r.low is not None else float(r.close),
            'Close': float(r.close),
            'Volume': float(r.volume) if r.volume is not None else 0.0,
        })

    result = {}
    for ticker, recs in by_ticker.items():
        if len(recs) < min_bars:
            continue
        df = pd.DataFrame(recs).set_index('Date').sort_index()
        result[ticker] = df
    return result


def fetch_bulk_prices(tickers, period='100d'):
    """
    Fetch OHLCV history for all tickers.

    Priority order (new May 2026 architecture):
      1. DailyPriceBar cache (populated by /api/cron/refresh-daily-bars
         post-market every weekday). Read is fast — single indexed query.
      2. AlphaVantage TIME_SERIES_DAILY concurrent fetch (slow, ~45s for
         100 tickers). Used ONLY as a self-healing fallback when the cache
         is empty/stale.
      3. yfinance bulk download (fallback of last resort — flaky on Vercel
         serverless IPs).

    Returns {ticker: DataFrame[Open,High,Low,Close,Volume]} where each
    DataFrame is sorted by Date ascending.
    """
    # ── Path 1: cache ──
    cached = _load_cached_daily_bars(tickers)
    if cached and len(cached) >= max(1, len(tickers) // 2):
        logger.info(f"DailyPriceBar cache hit: {len(cached)}/{len(tickers)} tickers")
        return cached
    if cached:
        logger.info(f"DailyPriceBar cache PARTIAL: {len(cached)}/{len(tickers)} — augmenting from AV")

    # ── Path 2: AlphaVantage concurrent live fetch ──
    missing = [t for t in tickers if t not in cached] if cached else list(tickers)
    av_result = fetch_av_daily_bars_concurrent(missing) if ALPHA_VANTAGE_KEY else {}
    if av_result:
        merged = {**cached, **av_result}
        return merged

    # ── Path 3: yfinance fallback (last resort, often blocked on Vercel) ──
    logger.warning("AlphaVantage daily fetch returned nothing — trying yfinance fallback")
    try:
        import yfinance as yf
        logger.info(f"yfinance fallback: fetching {len(missing)} tickers (period={period})...")
        data = yf.download(missing, period=period, group_by='ticker',
                           auto_adjust=True, threads=True, progress=False)
        yf_result = {}
        if len(missing) == 1:
            t = missing[0]
            if not data.empty:
                yf_result[t] = data[['Open', 'High', 'Low', 'Close', 'Volume']].dropna()
        else:
            for t in missing:
                try:
                    df = data[t][['Open', 'High', 'Low', 'Close', 'Volume']].dropna()
                    if len(df) >= 20:
                        yf_result[t] = df
                except (KeyError, TypeError):
                    pass
        logger.info(f"yfinance fallback returned {len(yf_result)}/{len(missing)} tickers")
        return {**cached, **yf_result}
    except Exception as e:
        logger.error(f"yfinance fallback failed: {e}")
        return cached  # may be empty


def fetch_realtime_quotes(tickers):
    """
    Fetch latest quote (price, volume) for all tickers.

    PRIMARY: AlphaVantage REALTIME_BULK_QUOTES (premium endpoint — up to 100
    symbols per call, ~1s for the full universe).
    FALLBACK: yfinance (less reliable on Vercel serverless).

    Returns {ticker: {price, volume, source, ...}}.
    """
    # ── Primary: AV bulk quotes ──
    quotes = fetch_realtime_bulk_quotes(tickers) if ALPHA_VANTAGE_KEY else {}
    if len(quotes) >= max(1, len(tickers) // 2):
        return quotes

    # ── Fallback: yfinance for anything missing ──
    missing = [t for t in tickers if t not in quotes]
    if not missing:
        return quotes

    logger.warning(f"AV bulk quotes covered {len(quotes)}/{len(tickers)} — falling back to yfinance for {len(missing)}")
    try:
        import yfinance as yf
        import math
        batch_str = ' '.join(missing)
        data = yf.download(batch_str, period='1d', group_by='ticker',
                           auto_adjust=True, threads=True, progress=False)
        for t in missing:
            try:
                if len(missing) == 1:
                    row = data.iloc[-1]
                else:
                    row = data[t].iloc[-1]
                close_val = float(row['Close'])
                vol_val = float(row['Volume'])
                if math.isnan(close_val) or math.isnan(vol_val):
                    continue
                quotes[t] = {
                    'price': round(close_val, 2),
                    'volume': int(vol_val),
                    'source': 'yfinance',
                }
            except (KeyError, IndexError, TypeError, ValueError):
                pass
    except Exception as e:
        logger.warning(f"yfinance quote fallback failed: {e}")

    return quotes


# ── Technical Indicators (computed locally from OHLCV) ────────────────────────

def compute_indicators(price_data):
    """
    Compute technical indicators from OHLCV DataFrames.
    Input: dict of {ticker: DataFrame}
    Output: dict of {ticker: {indicator_name: value, ...}}
    """
    indicators = {}

    for ticker, df in price_data.items():
        try:
            close = df['Close'].values.astype(float)
            high = df['High'].values.astype(float)
            low = df['Low'].values.astype(float)
            volume = df['Volume'].values.astype(float)

            if len(close) < 26:
                continue

            ind = {}

            # Current price & change
            ind['price'] = round(float(close[-1]), 2)
            ind['prev_close'] = round(float(close[-2]), 2) if len(close) >= 2 else ind['price']
            ind['change_pct'] = round((ind['price'] - ind['prev_close']) / ind['prev_close'] * 100, 2)
            ind['volume'] = int(volume[-1])

            # SMAs
            ind['sma_20'] = round(float(np.mean(close[-20:])), 2) if len(close) >= 20 else None
            ind['sma_50'] = round(float(np.mean(close[-50:])), 2) if len(close) >= 50 else None
            ind['sma_200'] = round(float(np.mean(close[-200:])), 2) if len(close) >= 200 else None

            # EMAs
            ind['ema_12'] = round(float(_ema(close, 12)), 2) if len(close) >= 12 else None
            ind['ema_26'] = round(float(_ema(close, 26)), 2) if len(close) >= 26 else None

            # MACD
            if ind['ema_12'] is not None and ind['ema_26'] is not None:
                macd_line = _ema_series(close, 12) - _ema_series(close, 26)
                signal_line = _ema(macd_line[-26:], 9) if len(macd_line) >= 9 else 0
                ind['macd'] = round(float(macd_line[-1]), 4)
                ind['macd_signal'] = round(float(signal_line), 4)
                ind['macd_histogram'] = round(float(macd_line[-1] - signal_line), 4)
                # Detect crossovers
                if len(macd_line) >= 2:
                    prev_macd = float(macd_line[-2])
                    prev_signal = float(_ema(macd_line[-27:-1], 9)) if len(macd_line) >= 10 else signal_line
                    if prev_macd <= prev_signal and macd_line[-1] > signal_line:
                        ind['macd_cross'] = 'bullish'
                    elif prev_macd >= prev_signal and macd_line[-1] < signal_line:
                        ind['macd_cross'] = 'bearish'
                    else:
                        ind['macd_cross'] = 'none'
                else:
                    ind['macd_cross'] = 'none'
            else:
                ind['macd'] = None
                ind['macd_signal'] = None
                ind['macd_histogram'] = None
                ind['macd_cross'] = 'none'

            # RSI (14-period)
            ind['rsi_14'] = round(float(_rsi(close, 14)), 2) if len(close) >= 15 else None

            # Bollinger Bands (20-period, 2 std)
            if len(close) >= 20:
                sma20 = np.mean(close[-20:])
                std20 = np.std(close[-20:])
                upper = sma20 + 2 * std20
                lower = sma20 - 2 * std20
                ind['bb_upper'] = round(float(upper), 2)
                ind['bb_lower'] = round(float(lower), 2)
                ind['bb_position'] = round(float((close[-1] - lower) / (upper - lower)), 3) if upper != lower else 0.5
            else:
                ind['bb_upper'] = ind['bb_lower'] = ind['bb_position'] = None

            # ATR (14-period)
            if len(close) >= 15:
                tr = np.maximum(high[-14:] - low[-14:],
                                np.maximum(np.abs(high[-14:] - close[-15:-1]),
                                           np.abs(low[-14:] - close[-15:-1])))
                ind['atr_14'] = round(float(np.mean(tr)), 2)
            else:
                ind['atr_14'] = None

            # ADX (14-period trend strength)
            ind['adx'] = round(float(_adx(high, low, close, 14)), 2) if len(close) >= 28 else None

            # Volume analysis
            vol_avg_20 = float(np.mean(volume[-20:])) if len(volume) >= 20 else float(volume[-1])
            ind['volume_avg_20'] = int(vol_avg_20)
            ind['volume_ratio'] = round(float(volume[-1]) / max(vol_avg_20, 1), 2)

            # Price vs SMAs
            if ind['sma_20']:
                ind['price_vs_sma20'] = 'above' if ind['price'] > ind['sma_20'] else 'below'
            else:
                ind['price_vs_sma20'] = 'unknown'

            if ind['sma_50']:
                ind['price_vs_sma50'] = 'above' if ind['price'] > ind['sma_50'] else 'below'
            else:
                ind['price_vs_sma50'] = 'unknown'

            # Sector
            ind['sector'] = get_sector_for_ticker(ticker)

            indicators[ticker] = ind

        except Exception as e:
            logger.warning(f"Failed computing indicators for {ticker}: {e}")

    logger.info(f"Computed indicators for {len(indicators)} tickers")
    return indicators


# ── Math helpers ──────────────────────────────────────────────────────────────

def _ema(data, period):
    """Compute the final EMA value for a data array."""
    if len(data) < period:
        return float(np.mean(data))
    multiplier = 2 / (period + 1)
    ema = float(np.mean(data[:period]))
    for val in data[period:]:
        ema = (float(val) - ema) * multiplier + ema
    return ema

def _ema_series(data, period):
    """Compute full EMA series."""
    result = np.zeros(len(data))
    if len(data) < period:
        result[:] = np.mean(data)
        return result
    multiplier = 2 / (period + 1)
    result[period - 1] = np.mean(data[:period])
    for i in range(period, len(data)):
        result[i] = (data[i] - result[i - 1]) * multiplier + result[i - 1]
    result[:period - 1] = result[period - 1]
    return result

def _rsi(close, period=14):
    """Compute RSI."""
    deltas = np.diff(close)
    gains = np.where(deltas > 0, deltas, 0)
    losses = np.where(deltas < 0, -deltas, 0)

    avg_gain = np.mean(gains[-period:])
    avg_loss = np.mean(losses[-period:])

    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def _adx(high, low, close, period=14):
    """Compute ADX (Average Directional Index)."""
    try:
        plus_dm = np.maximum(np.diff(high), 0)
        minus_dm = np.maximum(-np.diff(low), 0)
        # Zero out where other is larger
        mask = plus_dm > minus_dm
        minus_dm[mask & (plus_dm > minus_dm)] = 0
        plus_dm[~mask] = 0

        tr = np.maximum(high[1:] - low[1:],
                        np.maximum(np.abs(high[1:] - close[:-1]),
                                   np.abs(low[1:] - close[:-1])))

        atr = np.convolve(tr, np.ones(period) / period, mode='valid')
        plus_di = np.convolve(plus_dm, np.ones(period) / period, mode='valid')
        minus_di = np.convolve(minus_dm, np.ones(period) / period, mode='valid')

        # Avoid division by zero
        atr = np.where(atr == 0, 1e-10, atr)
        plus_di = (plus_di / atr) * 100
        minus_di = (minus_di / atr) * 100

        dx = np.abs(plus_di - minus_di) / np.maximum(plus_di + minus_di, 1e-10) * 100
        adx = np.mean(dx[-period:]) if len(dx) >= period else np.mean(dx)
        return float(adx)
    except Exception:
        return 25.0  # neutral default


# ── AlphaVantage News Sentiment ──────────────────────────────────────────────

ALPHA_NEWS_TOPICS = [
    'technology', 'finance', 'life_sciences', 'energy_transportation',
    'manufacturing', 'real_estate', 'retail_wholesale', 'economy_macro',
]

# ── AlphaVantage API call logging ───────────────────────────────────────────
# We buffer log entries in-memory and flush them in one batch at the end of
# `MarketDataHub.refresh()`. This works in two execution contexts:
#   1. Inside a Flask app (e.g. manual refresh via admin endpoint): direct DB
#      write, fast, no HTTP roundtrip.
#   2. Inside GitHub Actions (cmd_trade() in bot_agent.py): no Flask app context
#      and no DATABASE_URL, so direct DB fails. Falls back to HTTP POST to
#      /api/mobile/admin/bot/log-av-calls with the CRON_SECRET.
#
# Historically the direct-DB path silently failed from GitHub Actions, so the
# admin panel's "Market Research Data Sources" card always showed 0 calls.

_av_log_buffer = []  # module-level buffer of {endpoint, symbol, status, response_time_ms, timestamp}


def _log_av_api_call(endpoint, symbol='N/A', status='success', response_time_ms=None):
    """Buffer an AlphaVantage API call. Use `flush_av_logs()` to persist."""
    _av_log_buffer.append({
        'endpoint': endpoint,
        'symbol': symbol,
        'response_status': status,
        'response_time_ms': response_time_ms,
        'timestamp': datetime.utcnow().isoformat() + 'Z',
    })


def flush_av_logs():
    """Persist buffered AV call logs. Tries direct DB first, HTTP POST as fallback.

    Safe to call with an empty buffer. Clears the buffer on success of either path.
    Never raises — logging is best-effort and must not break bot trading.
    """
    global _av_log_buffer
    if not _av_log_buffer:
        return

    # Snapshot + clear immediately so concurrent flushes don't double-write.
    # (bot_agent.py is single-threaded, but being defensive is cheap.)
    pending = _av_log_buffer
    _av_log_buffer = []

    # Path 1: Direct DB write (works inside Flask app context, e.g. admin panel).
    try:
        from models import AlphaVantageAPILog, db as _db
        for entry in pending:
            try:
                _db.session.add(AlphaVantageAPILog(
                    endpoint=entry['endpoint'],
                    symbol=entry['symbol'],
                    response_status=entry['response_status'],
                    response_time_ms=entry.get('response_time_ms'),
                ))
            except Exception:
                continue
        _db.session.commit()
        logger.info(f"Flushed {len(pending)} AV call logs directly to DB")
        return
    except Exception as e:
        # Typical failure from GitHub Actions: "Working outside of application context"
        logger.debug(f"Direct-DB AV log write failed ({e.__class__.__name__}); trying HTTP fallback")

    # Path 2: HTTP POST to our backend (works from GitHub Actions, CLI tools).
    try:
        api_base = os.environ.get('API_BASE_URL', 'https://apestogether.ai/api/mobile')
        cron_secret = os.environ.get('CRON_SECRET', '')
        if not cron_secret:
            logger.debug("No CRON_SECRET — skipping HTTP AV log flush")
            return
        resp = requests.post(
            f'{api_base}/admin/bot/log-av-calls',
            json={'logs': pending},
            headers={
                'X-Cron-Secret': cron_secret,
                'Content-Type': 'application/json',
            },
            timeout=10,
        )
        if resp.status_code == 200:
            logger.info(f"Flushed {len(pending)} AV call logs via HTTP")
        else:
            logger.warning(f"HTTP AV log flush failed: {resp.status_code} {resp.text[:200]}")
    except Exception as e:
        logger.warning(f"HTTP AV log flush exception: {e}")


def fetch_news_sentiment():
    """
    Fetch news sentiment from AlphaVantage NEWS_SENTIMENT endpoint.
    Queries by topic to cover all industries efficiently.
    Returns dict of {ticker: {sentiment_score, sentiment_label, article_count, buzz}}
    """
    if not ALPHA_VANTAGE_KEY:
        logger.warning("No ALPHA_VANTAGE_API_KEY — skipping news sentiment")
        return {}

    sentiment = {}
    for topic in ALPHA_NEWS_TOPICS:
        try:
            url = (f"https://www.alphavantage.co/query?function=NEWS_SENTIMENT"
                   f"&topics={topic}&limit=50&sort=RELEVANCE"
                   f"&apikey={ALPHA_VANTAGE_KEY}")
            t0 = time.time()
            resp = requests.get(url, timeout=20)
            elapsed_ms = int((time.time() - t0) * 1000)
            data = resp.json()

            has_feed = bool(data.get('feed'))
            _log_av_api_call('NEWS_SENTIMENT', f'topic:{topic}',
                             'success' if has_feed else 'error', elapsed_ms)

            articles = data.get('feed', [])
            for article in articles:
                for ts in article.get('ticker_sentiment', []):
                    ticker = ts.get('ticker', '')
                    if not ticker or ':' in ticker:  # Skip crypto/forex
                        continue
                    score = float(ts.get('ticker_sentiment_score', 0))
                    label = ts.get('ticker_sentiment_label', 'Neutral')

                    if ticker not in sentiment:
                        sentiment[ticker] = {
                            'scores': [],
                            'labels': [],
                            'article_count': 0,
                        }
                    sentiment[ticker]['scores'].append(score)
                    sentiment[ticker]['labels'].append(label)
                    sentiment[ticker]['article_count'] += 1

            time.sleep(0.5)  # Stay well within 150/min

        except Exception as e:
            logger.warning(f"News sentiment fetch failed for topic '{topic}': {e}")

    # Aggregate per ticker
    result = {}
    for ticker, data in sentiment.items():
        scores = data['scores']
        result[ticker] = {
            'news_sentiment': round(float(np.mean(scores)), 4) if scores else 0.0,
            'news_label': _majority_label(data['labels']),
            'article_count': data['article_count'],
            'news_buzz': 'high' if data['article_count'] >= 5 else 'medium' if data['article_count'] >= 2 else 'low',
        }

    logger.info(f"News sentiment: {len(result)} tickers with sentiment data")
    return result

def _majority_label(labels):
    """Return the most common label."""
    if not labels:
        return 'Neutral'
    from collections import Counter
    return Counter(labels).most_common(1)[0][0]


# ── AlphaVantage Top Gainers/Losers ──────────────────────────────────────────

def fetch_top_movers():
    """
    Fetch top gainers, losers, and most active from AlphaVantage.
    Returns dict with keys: gainers, losers, most_active (each a list of dicts).
    """
    if not ALPHA_VANTAGE_KEY:
        return {'gainers': [], 'losers': [], 'most_active': []}

    try:
        url = (f"https://www.alphavantage.co/query?function=TOP_GAINERS_LOSERS"
               f"&apikey={ALPHA_VANTAGE_KEY}")
        t0 = time.time()
        resp = requests.get(url, timeout=15)
        elapsed_ms = int((time.time() - t0) * 1000)
        data = resp.json()
        _log_av_api_call('TOP_GAINERS_LOSERS', 'MARKET',
                         'success' if data.get('top_gainers') else 'error', elapsed_ms)

        def parse_movers(key):
            items = data.get(key, [])
            return [{
                'ticker': item.get('ticker', ''),
                'price': float(item.get('price', 0)),
                'change_pct': float(item.get('change_percentage', '0').replace('%', '')),
                'volume': int(item.get('volume', 0)),
            } for item in items[:20]]

        result = {
            'gainers': parse_movers('top_gainers'),
            'losers': parse_movers('top_losers'),
            'most_active': parse_movers('most_actively_traded'),
        }
        logger.info(f"Top movers: {len(result['gainers'])} gainers, {len(result['losers'])} losers")
        return result

    except Exception as e:
        logger.warning(f"Top movers fetch failed: {e}")
        return {'gainers': [], 'losers': [], 'most_active': []}


# ── Finnhub Health Probe (for admin dashboard) ──────────────────────────────
#
# The admin "Market Research Data Sources" card needs to know whether each
# Finnhub endpoint actually works. The free tier responds 200 to insider
# transactions and 403 to social-sentiment + recommendation. Rather than
# guess from the env-var presence, we ping each endpoint with a known ticker
# (AAPL) and cache the result for 6h to avoid hammering the API.
#
# Cache is module-level so it survives within a Vercel warm process. Cold
# starts will re-probe, which is fine — we expect at most a handful of
# probe-cycles per day.

_FINNHUB_HEALTH_CACHE = {'data': None, 'expires_at': 0}
_FINNHUB_HEALTH_TTL_SECONDS = 60 * 60 * 6  # 6h


def probe_finnhub_health(force=False):
    """Ping each Finnhub endpoint with AAPL and return per-endpoint status.

    Returns a dict like:
        {
            'last_probe_at': <unix ts>,
            'cache_ttl_seconds': 21600,
            'endpoints': {
                'insider':  {status, http_status, latency_ms, note},
                'social':   {...},
                'analyst':  {...},
            },
        }

    Status values:
        'active'      — HTTP 200 and got data back (free-tier compatible)
        'empty'       — HTTP 200 but empty response (endpoint works, no data for AAPL)
        'forbidden'   — HTTP 403 (premium endpoint, free tier blocked)
        'rate_limited' — HTTP 429
        'error'       — Other HTTP error or network failure
        'missing_key' — FINNHUB_API_KEY env var not set
    """
    from datetime import date as _date, timedelta as _td
    now = time.time()

    if (not force
            and _FINNHUB_HEALTH_CACHE['data']
            and _FINNHUB_HEALTH_CACHE['expires_at'] > now):
        return _FINNHUB_HEALTH_CACHE['data']

    if not FINNHUB_KEY:
        result = {
            'last_probe_at': now,
            'cache_ttl_seconds': _FINNHUB_HEALTH_TTL_SECONDS,
            'endpoints': {
                'insider': {'status': 'missing_key', 'note': 'FINNHUB_API_KEY not set in env'},
                'social': {'status': 'missing_key', 'note': 'FINNHUB_API_KEY not set in env'},
                'analyst': {'status': 'missing_key', 'note': 'FINNHUB_API_KEY not set in env'},
            },
        }
        _FINNHUB_HEALTH_CACHE['data'] = result
        _FINNHUB_HEALTH_CACHE['expires_at'] = now + _FINNHUB_HEALTH_TTL_SECONDS
        return result

    today = _date.today().isoformat()
    last_year = (_date.today() - _td(days=365)).isoformat()
    last_quarter = (_date.today() - _td(days=90)).isoformat()

    endpoints = {
        # Insider transactions — works on free tier (this is what the bot fleet
        # actually uses).
        'insider': (
            f"https://finnhub.io/api/v1/stock/insider-transactions"
            f"?symbol=AAPL&from={last_quarter}&to={today}&token={FINNHUB_KEY}"
        ),
        # Social sentiment — Reddit/Twitter buzz. Premium endpoint; free tier
        # returns HTTP 403 with a clear message in the response body.
        'social': (
            f"https://finnhub.io/api/v1/stock/social-sentiment"
            f"?symbol=AAPL&from={last_year}&to={today}&token={FINNHUB_KEY}"
        ),
        # Analyst upgrades/downgrades. Also premium-only.
        'analyst': (
            f"https://finnhub.io/api/v1/stock/recommendation"
            f"?symbol=AAPL&token={FINNHUB_KEY}"
        ),
    }

    endpoint_results = {}
    for name, url in endpoints.items():
        t0 = time.time()
        try:
            resp = requests.get(url, timeout=5)
            latency_ms = round((time.time() - t0) * 1000)
            if resp.status_code == 200:
                try:
                    data = resp.json()
                except ValueError:
                    data = None
                # Finnhub returns either a list or a dict depending on endpoint.
                # Treat any non-empty response as "active". Empty list/dict means
                # the endpoint is reachable but has no data for AAPL right now.
                if isinstance(data, list):
                    has_data = len(data) > 0
                elif isinstance(data, dict):
                    # 'data' key is the payload for some endpoints, otherwise
                    # any non-empty body counts.
                    has_data = bool(data) and (
                        bool(data.get('data')) if 'data' in data else True
                    )
                else:
                    has_data = False
                endpoint_results[name] = {
                    'status': 'active' if has_data else 'empty',
                    'http_status': 200,
                    'latency_ms': latency_ms,
                    'note': 'Reachable, returns data on free tier' if has_data
                            else 'Reachable but empty response for AAPL',
                }
            elif resp.status_code == 403:
                endpoint_results[name] = {
                    'status': 'forbidden',
                    'http_status': 403,
                    'latency_ms': latency_ms,
                    'note': "Premium endpoint — Finnhub free tier returns 403",
                }
            elif resp.status_code == 429:
                endpoint_results[name] = {
                    'status': 'rate_limited',
                    'http_status': 429,
                    'latency_ms': latency_ms,
                    'note': 'Rate limited — too many calls in the last minute',
                }
            else:
                endpoint_results[name] = {
                    'status': 'error',
                    'http_status': resp.status_code,
                    'latency_ms': latency_ms,
                    'note': f"HTTP {resp.status_code}",
                }
        except requests.exceptions.Timeout:
            endpoint_results[name] = {
                'status': 'error',
                'latency_ms': round((time.time() - t0) * 1000),
                'note': 'Timeout (>5s)',
            }
        except Exception as e:
            endpoint_results[name] = {
                'status': 'error',
                'latency_ms': round((time.time() - t0) * 1000),
                'note': str(e)[:120],
            }

    result = {
        'last_probe_at': now,
        'cache_ttl_seconds': _FINNHUB_HEALTH_TTL_SECONDS,
        'endpoints': endpoint_results,
    }
    _FINNHUB_HEALTH_CACHE['data'] = result
    _FINNHUB_HEALTH_CACHE['expires_at'] = now + _FINNHUB_HEALTH_TTL_SECONDS
    return result


# ── Finnhub Social Sentiment ────────────────────────────────────────────────

def fetch_social_sentiment(tickers, max_tickers=80):
    """
    Fetch Reddit + Twitter social sentiment from Finnhub.
    Returns dict of {ticker: {social_mentions, social_sentiment, social_positive, social_negative}}
    NOTE: This is a Finnhub PREMIUM endpoint. Free tier returns 403.
    """
    if not FINNHUB_KEY:
        logger.warning("No FINNHUB_API_KEY — skipping social sentiment")
        return {}

    if not FINNHUB_PREMIUM:
        logger.info("FINNHUB_PREMIUM unset — skipping social sentiment (premium-only endpoint)")
        return {}

    result = {}
    batch = tickers[:max_tickers]

    for i, ticker in enumerate(batch):
        try:
            today = datetime.utcnow().strftime('%Y-%m-%d')
            week_ago = (datetime.utcnow() - timedelta(days=7)).strftime('%Y-%m-%d')

            url = (f"https://finnhub.io/api/v1/stock/social-sentiment"
                   f"?symbol={ticker}&from={week_ago}&to={today}"
                   f"&token={FINNHUB_KEY}")
            resp = requests.get(url, timeout=10)
            if resp.status_code == 403:
                logger.info("Social sentiment is a premium endpoint — skipping (free tier)")
                return {}
            data = resp.json()

            reddit_data = data.get('reddit', [])
            twitter_data = data.get('twitter', [])
            all_data = reddit_data + twitter_data

            if all_data:
                mentions = sum(d.get('mention', 0) for d in all_data)
                pos_mentions = sum(d.get('positiveMention', 0) for d in all_data)
                neg_mentions = sum(d.get('negativeMention', 0) for d in all_data)
                total_mentions = pos_mentions + neg_mentions

                scores = [d.get('score', 0) for d in all_data if d.get('score', 0) != 0]
                avg_score = float(np.mean(scores)) if scores else 0.0

                result[ticker] = {
                    'social_mentions': mentions,
                    'social_sentiment': round(avg_score, 4),
                    'social_positive': pos_mentions,
                    'social_negative': neg_mentions,
                    'social_ratio': round(pos_mentions / max(total_mentions, 1), 3),
                }

            # Rate limit: 60 calls/min = 1/sec
            if (i + 1) % 55 == 0:
                logger.info("Finnhub rate limit pause (65s)...")
                time.sleep(65)
            else:
                time.sleep(1.1)

        except Exception as e:
            logger.warning(f"Social sentiment failed for {ticker}: {e}")

    logger.info(f"Social sentiment: {len(result)} tickers with data")
    return result


# ── Finnhub Analyst & Insider Data ───────────────────────────────────────────

def fetch_analyst_data(tickers, max_tickers=40):
    """
    Fetch recent analyst upgrades/downgrades from Finnhub.
    Returns dict of {ticker: {analyst_action, analyst_firm, to_grade}}
    NOTE: This is a Finnhub PREMIUM endpoint. Free tier returns 403.
    """
    if not FINNHUB_KEY:
        return {}

    if not FINNHUB_PREMIUM:
        logger.info("FINNHUB_PREMIUM unset — skipping analyst upgrades/downgrades (premium-only endpoint)")
        return {}

    result = {}
    today = datetime.utcnow().strftime('%Y-%m-%d')
    month_ago = (datetime.utcnow() - timedelta(days=30)).strftime('%Y-%m-%d')

    for i, ticker in enumerate(tickers[:max_tickers]):
        try:
            url = (f"https://finnhub.io/api/v1/stock/upgrade-downgrade"
                   f"?symbol={ticker}&from={month_ago}&to={today}"
                   f"&token={FINNHUB_KEY}")
            resp = requests.get(url, timeout=10)
            if resp.status_code == 403:
                logger.info("Analyst upgrades/downgrades is a premium endpoint — skipping (free tier)")
                return {}
            data = resp.json()

            if data and isinstance(data, list) and len(data) > 0:
                latest = data[0]
                result[ticker] = {
                    'analyst_action': latest.get('action', 'none'),
                    'analyst_firm': latest.get('company', ''),
                    'to_grade': latest.get('toGrade', ''),
                    'from_grade': latest.get('fromGrade', ''),
                }

            time.sleep(1.1)

        except Exception as e:
            logger.warning(f"Analyst data failed for {ticker}: {e}")

    logger.info(f"Analyst data: {len(result)} tickers with recent actions")
    return result


def fetch_insider_data(tickers, max_tickers=40):
    """
    Fetch insider transaction summary from Finnhub.
    Returns dict of {ticker: {insider_net: 'buying'|'selling'|'neutral'}}
    """
    if not FINNHUB_KEY:
        return {}

    result = {}
    today = datetime.utcnow().strftime('%Y-%m-%d')
    three_months_ago = (datetime.utcnow() - timedelta(days=90)).strftime('%Y-%m-%d')

    for i, ticker in enumerate(tickers[:max_tickers]):
        try:
            url = (f"https://finnhub.io/api/v1/stock/insider-transactions"
                   f"?symbol={ticker}&from={three_months_ago}&to={today}"
                   f"&token={FINNHUB_KEY}")
            resp = requests.get(url, timeout=10)
            data = resp.json()

            transactions = data.get('data', [])
            if transactions:
                buys = sum(1 for t in transactions
                           if t.get('transactionType', '').startswith('P'))  # Purchase
                sells = sum(1 for t in transactions
                            if t.get('transactionType', '').startswith('S'))  # Sale

                if buys > sells * 1.5:
                    net = 'buying'
                elif sells > buys * 1.5:
                    net = 'selling'
                else:
                    net = 'neutral'

                result[ticker] = {'insider_net': net, 'insider_buys': buys, 'insider_sells': sells}

            time.sleep(1.1)

        except Exception as e:
            logger.warning(f"Insider data failed for {ticker}: {e}")

    logger.info(f"Insider data: {len(result)} tickers")
    return result


# ── Master Data Hub ──────────────────────────────────────────────────────────

class MarketDataHub:
    """
    Central market data cache. Run refresh() once to populate,
    then all bots read from the shared cache.
    """

    def __init__(self):
        self.indicators = {}      # {ticker: {price, rsi_14, macd, ...}}
        self.news = {}            # {ticker: {news_sentiment, article_count, ...}}
        self.social = {}          # {ticker: {social_mentions, social_sentiment, ...}}
        self.analysts = {}        # {ticker: {analyst_action, ...}}
        self.insiders = {}        # {ticker: {insider_net, ...}}
        self.top_movers = {}      # {gainers: [...], losers: [...]}
        self.last_refresh = None
        self.data_quality = {     # Track what succeeded
            'prices': False,      # 100-day OHLCV history (cache or live)
            'quotes': False,      # current intraday quote (AV bulk)
            'indicators': False,  # locally computed RSI/MACD/etc.
            'news': False,
            'social': False,
            'analysts': False,
            'insiders': False,
            'movers': False,
        }

    def refresh(self, include_extras=True):
        """
        Full data refresh. Runs the complete pipeline.
        Set include_extras=False for a lightweight core-only refresh.
        """
        start = time.time()
        tickers = get_all_tickers()
        logger.info(f"=== MarketDataHub refresh: {len(tickers)} tickers ===")

        # Phase 1: Bulk price history (cache → AV → yfinance fallback chain).
        # Returns DataFrames containing daily bars THROUGH the last cache
        # refresh (typically yesterday's close after the 6:30 PM ET cron).
        price_data = fetch_bulk_prices(tickers)
        self.data_quality['prices'] = len(price_data) > 0

        # Phase 2: Realtime quotes via AV REALTIME_BULK_QUOTES (~1s for 100
        # tickers). Done BEFORE indicator computation so we can splice
        # today's intraday close into the price history — this way RSI /
        # MACD / trend signals reflect intraday moves, not just yesterday's
        # close. Without this step, every wave during the trading day would
        # be making decisions based on stale data.
        quotes = fetch_realtime_quotes(tickers)
        self.data_quality['quotes'] = len(quotes) > 0

        # Phase 2b: Splice today's quote as a synthetic bar onto each
        # ticker's history. The OHLC values all collapse to the current
        # price (we don't have the day's true high/low intraday), but
        # since indicators read mostly from `Close`, this is fine for
        # RSI/MACD/trend purposes.
        if price_data and quotes:
            try:
                import pandas as pd
                # "Today" is anchored to NY market date — same as what AV
                # returns for daily bars, so dedupe checks work correctly.
                today_market_date = (
                    pd.Timestamp.now(tz='America/New_York')
                    .normalize().tz_localize(None)
                )
                appended = 0
                for t, df in list(price_data.items()):
                    if t not in quotes or df.empty:
                        continue
                    # If the cache already contains today's bar (e.g., the
                    # daily-bars cron has already run for today after close),
                    # don't double-stamp.
                    if today_market_date in df.index:
                        continue
                    cur_price = float(quotes[t]['price'])
                    cur_volume = float(quotes[t].get('volume') or 0)
                    synthetic = pd.DataFrame(
                        [{
                            'Open': cur_price,
                            'High': cur_price,
                            'Low': cur_price,
                            'Close': cur_price,
                            'Volume': cur_volume,
                        }],
                        index=pd.DatetimeIndex([today_market_date], name=df.index.name),
                    )
                    price_data[t] = pd.concat([df, synthetic])
                    appended += 1
                if appended:
                    logger.info(f"Appended intraday quote bar to {appended} tickers before indicator computation")
            except Exception as e:
                logger.warning(f"Intraday-quote append failed (non-fatal, indicators will use yesterday's close): {e}")

        # Phase 3: Technical indicators (local computation, now incorporates
        # today's intraday close where available).
        if price_data:
            self.indicators = compute_indicators(price_data)
            self.data_quality['indicators'] = len(self.indicators) > 0
        else:
            logger.error("No price data available — indicators will be empty")

        # Phase 3b: Stamp current price/volume onto the indicators dict so
        # downstream consumers see the same value used in the indicator math.
        for t, q in quotes.items():
            if t in self.indicators:
                self.indicators[t]['price'] = q['price']
                self.indicators[t]['volume'] = q.get('volume', self.indicators[t].get('volume', 0))

        if include_extras:
            # Phase 4: News sentiment (AlphaVantage)
            try:
                self.news = fetch_news_sentiment()
                self.data_quality['news'] = len(self.news) > 0
            except Exception as e:
                logger.warning(f"News sentiment phase failed: {e}")

            # Phase 5: Top movers (AlphaVantage)
            try:
                self.top_movers = fetch_top_movers()
                self.data_quality['movers'] = True
            except Exception as e:
                logger.warning(f"Top movers phase failed: {e}")

            # Phase 6: Social sentiment (Finnhub)
            try:
                # Prioritize tickers that have indicators data
                social_tickers = [t for t in tickers if t in self.indicators][:80]
                self.social = fetch_social_sentiment(social_tickers)
                self.data_quality['social'] = len(self.social) > 0
            except Exception as e:
                logger.warning(f"Social sentiment phase failed: {e}")

            # Phase 7: Analyst + insider data (Finnhub)
            try:
                analyst_tickers = [t for t in tickers if t in self.indicators][:40]
                self.analysts = fetch_analyst_data(analyst_tickers)
                self.insiders = fetch_insider_data(analyst_tickers)
                self.data_quality['analysts'] = len(self.analysts) > 0
                self.data_quality['insiders'] = len(self.insiders) > 0
            except Exception as e:
                logger.warning(f"Analyst/insider phase failed: {e}")

        self.last_refresh = datetime.utcnow()
        elapsed = time.time() - start
        logger.info(f"=== Refresh complete in {elapsed:.1f}s — {len(self.indicators)} tickers with indicators ===")
        logger.info(f"Data quality: {self.data_quality}")

        # Persist the buffered AV API-call logs. In Flask-app context this goes
        # direct-to-DB; from GitHub Actions it falls back to HTTP POST. Best-effort
        # — never raises.
        try:
            flush_av_logs()
        except Exception as e:
            logger.warning(f"flush_av_logs failed: {e}")

    def get_stock_data(self, ticker):
        """
        Get the complete data snapshot for a single ticker.
        Merges indicators + news + social + analyst + insider data.
        """
        if ticker not in self.indicators:
            return None

        data = dict(self.indicators[ticker])
        data['ticker'] = ticker

        # Merge news
        if ticker in self.news:
            data.update(self.news[ticker])
        else:
            data['news_sentiment'] = 0.0
            data['news_buzz'] = 'low'
            data['article_count'] = 0

        # Merge social
        if ticker in self.social:
            data.update(self.social[ticker])
        else:
            data['social_mentions'] = 0
            data['social_sentiment'] = 0.0
            data['social_ratio'] = 0.5

        # Merge analyst
        if ticker in self.analysts:
            data.update(self.analysts[ticker])
        else:
            data['analyst_action'] = 'none'

        # Merge insider
        if ticker in self.insiders:
            data.update(self.insiders[ticker])
        else:
            data['insider_net'] = 'neutral'

        # Check if in top movers
        gainer_tickers = [g['ticker'] for g in self.top_movers.get('gainers', [])]
        loser_tickers = [l['ticker'] for l in self.top_movers.get('losers', [])]
        if ticker in gainer_tickers:
            data['mover_status'] = 'top_gainer'
        elif ticker in loser_tickers:
            data['mover_status'] = 'top_loser'
        else:
            data['mover_status'] = 'normal'

        return data

    def get_sector_tickers(self, sector):
        """Get list of tickers in a sector that have data."""
        sector_tickers = UNIVERSE.get(sector, [])
        return [t for t in sector_tickers if t in self.indicators]

    def is_stale(self, max_age_hours=4):
        """Check if data is too old to trade on."""
        if not self.last_refresh:
            return True
        age = (datetime.utcnow() - self.last_refresh).total_seconds() / 3600
        return age > max_age_hours

    def is_core_available(self):
        """Check if at minimum we have price + indicator data."""
        return self.data_quality['prices'] and self.data_quality['indicators']

    def summary(self):
        """Return a summary dict for logging/monitoring."""
        return {
            'tickers_with_indicators': len(self.indicators),
            'tickers_with_news': len(self.news),
            'tickers_with_social': len(self.social),
            'tickers_with_analyst': len(self.analysts),
            'tickers_with_insider': len(self.insiders),
            'top_gainers': len(self.top_movers.get('gainers', [])),
            'last_refresh': self.last_refresh.isoformat() if self.last_refresh else None,
            'data_quality': self.data_quality,
        }
