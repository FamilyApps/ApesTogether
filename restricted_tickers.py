"""
Restricted-ticker policy
========================
Leveraged and inverse ETFs/ETNs are blocked from user portfolios. They exist
to amplify daily moves (2x/3x, long or short), which turns the leaderboard
into a leverage contest instead of a stock-picking track record, and their
daily-reset decay makes long-window performance math misleading.

Enforced at BOTH user-facing entry points:
  - POST /portfolio/trade      (live + after-hours queued buys)
  - POST /portfolio/stocks     (onboarding 'seed' + 'buy' intents)

Existing positions are grandfathered (sells of a restricted ticker are always
allowed so users can exit; only new BUY exposure is blocked).

The list is curated, not exhaustive — extend it as new products appear.
Pattern rules below catch the standard leveraged-fund families.
"""

# Broad-market / sector 2x-3x bull+bear pairs, commodity/vol/rates leverage,
# and the single-stock leveraged ETF families (Direxion/GraniteShares/Defiance).
LEVERAGED_ETF_TICKERS = frozenset({
    # Nasdaq / S&P / Dow / Russell
    'TQQQ', 'SQQQ', 'QLD', 'QID', 'PSQ', 'SSO', 'SDS', 'SH', 'UPRO', 'SPXU',
    'SPXL', 'SPXS', 'SPUU', 'SPDN', 'UDOW', 'SDOW', 'DDM', 'DXD', 'DOG',
    'TNA', 'TZA', 'URTY', 'SRTY', 'UWM', 'TWM', 'RWM',
    # Sector 3x pairs
    'SOXL', 'SOXS', 'TECL', 'TECS', 'FAS', 'FAZ', 'LABU', 'LABD', 'CURE',
    'DRN', 'DRV', 'NAIL', 'DPST', 'DFEN', 'DUSL', 'UTSL', 'PILL', 'WANT',
    'RETL', 'HIBL', 'HIBS', 'WEBL', 'WEBS', 'BNKU', 'BNKD',
    # Commodities / metals / energy
    'NUGT', 'DUST', 'JNUG', 'JDST', 'GUSH', 'DRIP', 'ERX', 'ERY', 'BOIL',
    'KOLD', 'UCO', 'SCO', 'AGQ', 'ZSL', 'UGL', 'GLL', 'DGP', 'DZZ',
    # Rates / treasuries
    'TMF', 'TMV', 'TBT', 'UBT', 'TYD', 'TYO', 'TTT',
    # International
    'YINN', 'YANG', 'EDC', 'EDZ', 'EURL', 'EUO', 'YCS', 'YCL', 'CWEB',
    'CHAU', 'CHAD', 'KORU', 'INDL', 'MEXX', 'BRZU', 'EWV', 'EZJ',
    # FANG+ / thematic leveraged ETNs
    'FNGU', 'FNGD', 'FNGO', 'BULZ', 'BERZ', 'OILU', 'OILD',
    # Leveraged / inverse volatility ETPs (daily-reset decay vehicles)
    'UVXY', 'UVIX', 'SVIX', 'SVXY',
    # Single-stock leveraged ETFs
    'NVDL', 'NVDD', 'NVDU', 'NVDQ', 'NVD', 'NVDX', 'NVDS',
    'TSLL', 'TSLQ', 'TSLS', 'TSLZ', 'TSLT', 'TSLR',
    'AAPU', 'AAPD', 'AAPB', 'MSFU', 'MSFD', 'MSFL',
    'AMZU', 'AMZD', 'AMZZ', 'GGLL', 'GGLS',
    'METU', 'METD', 'FBL', 'CONL', 'CONI',
    'MSTX', 'MSTZ', 'MSTU', 'MSTR2',  # MicroStrategy leveraged family
    'SMCX', 'SMCZ', 'SMCL', 'PLTU', 'PLTD', 'AMDL', 'AMDS',
    'COIW', 'COIG', 'BITX', 'BITI', 'ETHU', 'ETHD',
})


def is_restricted_ticker(ticker):
    """Return a human-readable reason string if the ticker is restricted,
    else None. Input is normalized (strip/upper) defensively."""
    t = (ticker or '').strip().upper()
    if not t:
        return None
    if t in LEVERAGED_ETF_TICKERS:
        return 'leveraged_or_inverse_etf'
    return None


RESTRICTED_TICKER_MESSAGE = (
    'Leveraged and inverse ETFs are not supported. ApesTogether tracks '
    'stock-picking performance; daily-reset leveraged products distort '
    'leaderboard math.'
)
