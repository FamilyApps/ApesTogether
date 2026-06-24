-- 2026_06_24_stock_price_cache.sql
-- Shared, cross-instance stock-price cache (W9, see docs/PRICE_CACHE_AND_SCALING.md).
--
-- portfolio_performance.py keeps a fast per-instance in-memory cache (L1) in
-- front of THIS shared table (L2). Every serverless instance reads/writes the
-- same rows here, so a ticker is fetched from AlphaVantage at most once per TTL
-- window across the whole fleet instead of once per instance. Until this table
-- exists the helpers transparently fall back to in-memory-only behavior, so it
-- is safe to deploy the code before (or after) running this migration.
--
-- `updated_at` is stored as naive UTC (matching the app's datetime.utcnow()
-- convention, same as stock_transaction.timestamp). Idempotent.

CREATE TABLE IF NOT EXISTS stock_price_cache (
    ticker     VARCHAR(20)      PRIMARY KEY,
    price      DOUBLE PRECISION NOT NULL,
    updated_at TIMESTAMP        NOT NULL DEFAULT (now() AT TIME ZONE 'utc')
);

-- Lets a future janitor prune long-stale rows cheaply (optional).
CREATE INDEX IF NOT EXISTS ix_stock_price_cache_updated_at
    ON stock_price_cache (updated_at);
