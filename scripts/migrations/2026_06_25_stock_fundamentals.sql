-- 2026_06_25_stock_fundamentals.sql
-- Per-ticker fundamentals cache from AlphaVantage OVERVIEW (Bot Layer B).
--
-- Fundamentals change slowly (quarterly earnings, periodic analyst revisions),
-- so this table is refreshed WEEKLY by /api/cron/refresh-fundamentals rather
-- than every trade wave. OVERVIEW costs one AV call PER ticker, which is far too
-- expensive to run per-wave but trivial once a week for the ~130-ticker universe.
--
-- Trade waves read from this table (direct DB inside Flask, or via HTTP from the
-- GitHub Actions bot runner) and feed three signals the bots previously lacked:
--   * valuation  (pe_ratio / peg_ratio)        -> value / GARP archetypes
--   * dividend   (dividend_yield)              -> dividend_growth archetype
--   * analyst    (analyst_target_price upside) -> REVIVES the dead analyst leg
--     that produced nothing on the free Finnhub tier.
--
-- Safe to deploy the code before OR after this migration: the loaders degrade to
-- {} when the table is absent and the new signals simply contribute 0. Idempotent.

CREATE TABLE IF NOT EXISTS stock_fundamentals (
    id                   SERIAL PRIMARY KEY,
    ticker               VARCHAR(20)      NOT NULL UNIQUE,

    -- Valuation
    pe_ratio             DOUBLE PRECISION,
    peg_ratio            DOUBLE PRECISION,
    price_to_book        DOUBLE PRECISION,
    eps                  DOUBLE PRECISION,

    -- Income / risk
    dividend_yield       DOUBLE PRECISION,   -- fraction, e.g. 0.025 = 2.5%
    beta                 DOUBLE PRECISION,

    -- Analyst
    analyst_target_price DOUBLE PRECISION,

    -- Context / descriptive
    market_cap           DOUBLE PRECISION,
    sector               VARCHAR(80),
    name                 VARCHAR(160),

    fetched_at           TIMESTAMP        NOT NULL DEFAULT (now() AT TIME ZONE 'utc')
);

-- Single-ticker lookups + a freshness scan for the weekly janitor / staleness.
CREATE UNIQUE INDEX IF NOT EXISTS ix_stock_fundamentals_ticker
    ON stock_fundamentals (ticker);
CREATE INDEX IF NOT EXISTS ix_stock_fundamentals_fetched_at
    ON stock_fundamentals (fetched_at);
