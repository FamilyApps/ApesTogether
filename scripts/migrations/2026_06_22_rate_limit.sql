-- 2026_06_22_rate_limit.sql
-- Shared, serverless-safe rate-limit counter (security audit S-1).
--
-- The custom @rate_limit decorator (mobile_api.py) uses this fixed-window table
-- so a limit holds across Vercel's ephemeral/concurrent instances. Until this
-- table exists the decorator transparently falls back to a per-instance
-- in-memory window, so running this migration is what actually "turns on"
-- cross-instance rate limiting (e.g. for POST /auth/token at 10/min/IP).
-- Idempotent.

CREATE TABLE IF NOT EXISTS mobile_rate_limit (
    client_key   VARCHAR(200) NOT NULL,   -- "<user|admin|ip>:<endpoint>"
    window_start BIGINT       NOT NULL,    -- epoch seconds, floored to the window
    hits         INTEGER      NOT NULL DEFAULT 0,
    PRIMARY KEY (client_key, window_start)
);

-- Supports the decorator's opportunistic cleanup of expired windows.
CREATE INDEX IF NOT EXISTS ix_mobile_rate_limit_window
    ON mobile_rate_limit (window_start);
