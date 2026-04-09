"""
Shared Data Hub for Bot Agent Orchestrator
============================================
Fetches market data once for all tracked tickers, computes technical
indicators, and aggregates news/social sentiment. All bots consume
this shared cache — data cost is O(tickers), not O(bots).

Data Sources:
    - yfinance (free): Bulk OHLCV history, real-time quotes, fundamentals
    - AlphaVantage Premium ($99.99/mo, 150 calls/min): NEWS_SENTIMENT,
      TOP_GAINERS_LOSERS, realtime quotes (fallback)
    - Finnhub Free (60 calls/min): Social sentiment (Reddit + Twitter),
      analyst upgrades/downgrades, insider transactions
"""

import os
import time
import json
import logging
import requests
import numpy as np
from datetime import datetime, timedelta
from collections import defaultdict

logger = logging.getLogger('bot_data_hub')

# ── API Keys ─────────────────────────────────────────────────────────────────

ALPHA_VANTAGE_KEY = os.environ.get('ALPHA_VANTAGE_API_KEY', '')
FINNHUB_KEY = os.environ.get('FINNHUB_API_KEY', '')

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


# ── Price Provider (yfinance primary, AlphaVantage fallback) ─────────────────

def fetch_bulk_prices(tickers, period='100d'):
    """
    Fetch OHLCV history for all tickers using yfinance.
    Returns dict of {ticker: DataFrame} with columns: Open, High, Low, Close, Volume
    Falls back to AlphaVantage if yfinance fails.
    """
    try:
        import yfinance as yf
        logger.info(f"Fetching {len(tickers)} tickers via yfinance (period={period})...")
        data = yf.download(tickers, period=period, group_by='ticker',
                           auto_adjust=True, threads=True, progress=False)

        result = {}
        if len(tickers) == 1:
            # Single ticker: data is already a flat DataFrame
            t = tickers[0]
            if not data.empty:
                result[t] = data[['Open', 'High', 'Low', 'Close', 'Volume']].dropna()
        else:
            for t in tickers:
                try:
                    df = data[t][['Open', 'High', 'Low', 'Close', 'Volume']].dropna()
                    if len(df) >= 20:
                        result[t] = df
                except (KeyError, TypeError):
                    pass

        logger.info(f"yfinance returned data for {len(result)}/{len(tickers)} tickers")
        return result

    except Exception as e:
        logger.warning(f"yfinance bulk download failed: {e}")
        return _fallback_alphavantage_prices(tickers)


def _fallback_alphavantage_prices(tickers, max_tickers=100):
    """Fallback: fetch daily prices from AlphaVantage (1 call per ticker)."""
    if not ALPHA_VANTAGE_KEY:
        logger.error("No ALPHA_VANTAGE_API_KEY set, cannot use fallback")
        return {}

    import pandas as pd
    result = {}
    batch = tickers[:max_tickers]
    logger.info(f"AlphaVantage fallback: fetching {len(batch)} tickers...")

    for i, ticker in enumerate(batch):
        try:
            url = (f"https://www.alphavantage.co/query?function=TIME_SERIES_DAILY"
                   f"&symbol={ticker}&outputsize=compact&apikey={ALPHA_VANTAGE_KEY}")
            t0 = time.time()
            resp = requests.get(url, timeout=15)
            elapsed_ms = int((time.time() - t0) * 1000)
            data = resp.json()
            ts = data.get('Time Series (Daily)', {})
            _log_av_api_call('TIME_SERIES_DAILY', ticker,
                             'success' if ts else 'error', elapsed_ms)
            if not ts:
                continue

            rows = []
            for date_str, vals in ts.items():
                rows.append({
                    'Date': pd.Timestamp(date_str),
                    'Open': float(vals['1. open']),
                    'High': float(vals['2. high']),
                    'Low': float(vals['3. low']),
                    'Close': float(vals['4. close']),
                    'Volume': float(vals['5. volume']),
                })
            df = pd.DataFrame(rows).set_index('Date').sort_index()
            if len(df) >= 20:
                result[ticker] = df

            # Rate limit: 150 calls/min = 2.5/sec
            if (i + 1) % 140 == 0:
                logger.info("AlphaVantage rate limit pause (60s)...")
                time.sleep(62)
            else:
                time.sleep(0.45)

        except Exception as e:
            logger.warning(f"AlphaVantage failed for {ticker}: {e}")

    logger.info(f"AlphaVantage returned data for {len(result)} tickers")
    return result


def fetch_realtime_quotes(tickers):
    """
    Fetch latest quote (price, change %) for all tickers.
    Uses yfinance for speed, AlphaVantage as fallback.
    Returns dict of {ticker: {price, change_pct, volume}}
    """
    quotes = {}
    try:
        import yfinance as yf
        import math
        # yfinance can fetch multiple quotes at once
        batch_str = ' '.join(tickers)
        data = yf.download(batch_str, period='1d', group_by='ticker',
                           auto_adjust=True, threads=True, progress=False)
        for t in tickers:
            try:
                if len(tickers) == 1:
                    row = data.iloc[-1]
                else:
                    row = data[t].iloc[-1]
                close_val = float(row['Close'])
                vol_val = float(row['Volume'])
                # Skip tickers with NaN data
                if math.isnan(close_val) or math.isnan(vol_val):
                    continue
                quotes[t] = {
                    'price': round(close_val, 2),
                    'volume': int(vol_val),
                }
            except (KeyError, IndexError, TypeError, ValueError):
                pass
    except Exception as e:
        logger.warning(f"yfinance quote fetch failed: {e}")

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

def _log_av_api_call(endpoint, symbol='N/A', status='success', response_time_ms=None):
    """Best-effort log of an AlphaVantage API call to the tracking table."""
    try:
        from models import AlphaVantageAPILog, db as _db
        log = AlphaVantageAPILog(
            endpoint=endpoint,
            symbol=symbol,
            response_status=status,
            response_time_ms=response_time_ms,
        )
        _db.session.add(log)
        _db.session.commit()
    except Exception:
        pass  # Never break bot trading over a log write


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
            'prices': False,
            'indicators': False,
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

        # Phase 1: Bulk price data (yfinance primary, AV fallback)
        price_data = fetch_bulk_prices(tickers)
        self.data_quality['prices'] = len(price_data) > 0

        # Phase 2: Technical indicators (local computation)
        if price_data:
            self.indicators = compute_indicators(price_data)
            self.data_quality['indicators'] = len(self.indicators) > 0
        else:
            logger.error("No price data available — indicators will be empty")

        # Phase 3: Realtime quotes (update current prices)
        quotes = fetch_realtime_quotes(tickers)
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
