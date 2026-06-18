-- Migration: payout integrity (transaction-driven payouts + refund clawback)
-- Date: 2026-06-17
--
-- Adds:
--   1. in_app_purchase.payout_reversed_at — marks a refunded transaction whose
--      already-PAID creator payout has been netted against a later month, so the
--      same refund can never be clawed back twice.
--   2. A UNIQUE index on (portfolio_user_id, period_start, period_end) for
--      xero_payout_record — a hard idempotency guard so a creator can never get
--      two payout records (and thus two bills) for the same month.
--
-- Safe to run before deploying the new code. Idempotent (IF NOT EXISTS).

BEGIN;

ALTER TABLE in_app_purchase
    ADD COLUMN IF NOT EXISTS payout_reversed_at TIMESTAMP NULL;

-- Defensive: if any duplicate (user, period) payout records already exist, the
-- unique index creation below will fail. Pre-launch there should be none. If it
-- does fail, dedupe manually before re-running:
--   SELECT portfolio_user_id, period_start, period_end, COUNT(*)
--   FROM xero_payout_record
--   GROUP BY 1,2,3 HAVING COUNT(*) > 1;

CREATE UNIQUE INDEX IF NOT EXISTS uq_payout_user_period
    ON xero_payout_record (portfolio_user_id, period_start, period_end);

COMMIT;
