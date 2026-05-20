-- ─────────────────────────────────────────────────────────────────────────
-- Phase D: portfolio resizer — add scale columns to mobile_subscription
-- ─────────────────────────────────────────────────────────────────────────
-- Run this BEFORE deploying the Phase D code so that the new endpoints
-- and the modified GET /portfolio/<slug> have schema to work against.
--
-- This file is idempotent (uses IF NOT EXISTS) — safe to re-run.
--
-- Columns:
--   scale_factor    — Float. user's chosen dollar size / target portfolio
--                     value, frozen at set time. NULL = no scale set.
--   target_dollars  — Float. The dollar amount the subscriber chose, e.g.
--                     10000.00. Kept alongside scale_factor so the UI can
--                     re-display "You set $10K" without recomputing.
--   scale_set_at    — Timestamp (UTC) when the subscriber configured it.
--
-- All three columns are nullable and have no default — existing rows stay
-- NULL, which the API treats as "no scale" (= legacy behavior).
--
-- How to run (Supabase SQL Editor):
--   1. Open https://supabase.com/dashboard/project/<project>/sql/new
--   2. Paste this entire file
--   3. Click "Run"
--   4. Verify with:
--        SELECT column_name, data_type, is_nullable
--        FROM information_schema.columns
--        WHERE table_name = 'mobile_subscription'
--          AND column_name IN ('scale_factor','target_dollars','scale_set_at');
--      Expect 3 rows, all is_nullable = YES.
-- ─────────────────────────────────────────────────────────────────────────

ALTER TABLE mobile_subscription
    ADD COLUMN IF NOT EXISTS scale_factor   DOUBLE PRECISION NULL,
    ADD COLUMN IF NOT EXISTS target_dollars DOUBLE PRECISION NULL,
    ADD COLUMN IF NOT EXISTS scale_set_at   TIMESTAMP WITHOUT TIME ZONE NULL;

-- Optional: partial index for the common "find my scaled subscriptions"
-- query the iOS/Android settings screens will issue. Indexes only the
-- rows where scale_factor IS NOT NULL (small subset), so storage cost
-- is minimal.
CREATE INDEX IF NOT EXISTS ix_mobile_subscription_scale_set
    ON mobile_subscription (subscriber_id)
    WHERE scale_factor IS NOT NULL;
