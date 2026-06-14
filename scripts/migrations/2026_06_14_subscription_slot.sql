-- ─────────────────────────────────────────────────────────────────────────
-- Per-creator subscription slots — add `slot` to mobile_subscription
-- ─────────────────────────────────────────────────────────────────────────
-- Run this BEFORE deploying the slot code so GET /subscriptions and
-- /purchase/validate have schema to write/read.
--
-- Idempotent (IF NOT EXISTS) — safe to re-run.
--
-- Column:
--   slot — Integer 1..MAX_SUBSCRIPTION_SLOTS (see subscription_slots.py).
--          Which generic store "slot" product backs this subscription. The
--          (slot, subscribed_to_id) pair maps a store slot to a creator,
--          per user. NULL for legacy rows created before this feature
--          (treated as "unknown slot" — UI falls back to no label).
--
-- Design doc: docs/PER_CREATOR_SUBSCRIPTION_SLOTS.md
--
-- How to run (Supabase SQL Editor):
--   1. Open https://supabase.com/dashboard/project/<project>/sql/new
--   2. Paste this entire file
--   3. Click "Run"
--   4. Verify with:
--        SELECT column_name, data_type, is_nullable
--        FROM information_schema.columns
--        WHERE table_name = 'mobile_subscription' AND column_name = 'slot';
--      Expect 1 row, integer, is_nullable = YES.
-- ─────────────────────────────────────────────────────────────────────────

ALTER TABLE mobile_subscription
    ADD COLUMN IF NOT EXISTS slot INTEGER NULL;

-- Backfill: existing single-product subscriptions were all effectively Slot 1
-- (the legacy com.apestogether.subscription.{monthly,annual} products). Only
-- touch active rows so we don't relabel historical/expired ones.
UPDATE mobile_subscription
   SET slot = 1
 WHERE slot IS NULL
   AND status = 'active';

-- Index the common "which slots does this user occupy?" lookup the slot
-- allocator issues on every Subscribe tap.
CREATE INDEX IF NOT EXISTS ix_mobile_subscription_subscriber_slot
    ON mobile_subscription (subscriber_id, slot);
