-- 2026_06_22_reslot_comped_subs.sql
-- One-time backfill: give each subscriber's COMPED (admin/bot) subscriptions
-- distinct slots (A/B/C...) instead of all colliding on slot 1.
--
-- Background: comped subs created by /admin/bot/subscribe never set `slot`, so
-- the 2026_06_14 migration backfilled them all to slot=1 -> every one rendered
-- as "Trader Subscription A" (e.g. bobford00's divi51 / candle3873 / Wolff).
-- The code fix (bot_subscribe now assigns the lowest free slot) handles all
-- FUTURE comped subs; this script fixes the existing rows.
--
-- Safety: real store purchases derive their slot from the purchased product, so
-- we only renumber subscribers whose CURRENTLY-OCCUPYING subscriptions are ALL
-- comped (platform='admin'); mixed real+comped subscribers (none expected
-- pre-launch) are skipped so a real store entitlement's slot is never clobbered.
-- Idempotent: re-running yields the same assignment.

BEGIN;

WITH occupying AS (
    SELECT ms.id,
           ms.subscriber_id,
           ms.created_at,
           iap.platform AS iap_platform
    FROM mobile_subscription ms
    JOIN in_app_purchase iap ON iap.id = ms.in_app_purchase_id
    WHERE ms.status = 'active'
       OR (ms.status = 'canceled' AND ms.expires_at IS NOT NULL AND ms.expires_at > now())
),
safe_subscribers AS (
    SELECT subscriber_id
    FROM occupying
    GROUP BY subscriber_id
    HAVING bool_and(iap_platform = 'admin')
),
ranked AS (
    SELECT o.id,
           row_number() OVER (PARTITION BY o.subscriber_id
                              ORDER BY o.created_at, o.id) AS rn
    FROM occupying o
    JOIN safe_subscribers s ON s.subscriber_id = o.subscriber_id
)
UPDATE mobile_subscription ms
SET slot = ranked.rn
FROM ranked
WHERE ms.id = ranked.id
  AND ms.slot IS DISTINCT FROM ranked.rn;

COMMIT;

-- Verify (expect distinct slots 1,2,3 -> A,B,C for bobford00):
--   SELECT ms.subscriber_id, ms.id, ms.slot, ms.status, u2.username AS creator
--   FROM mobile_subscription ms
--   JOIN "user" u  ON u.id  = ms.subscriber_id
--   JOIN "user" u2 ON u2.id = ms.subscribed_to_id
--   WHERE u.username = 'bobford00'
--   ORDER BY ms.slot;
