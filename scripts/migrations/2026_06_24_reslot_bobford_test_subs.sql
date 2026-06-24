-- 2026_06_24_reslot_bobford_test_subs.sql
-- One-time fix for bobford00's 3 FREE TEST subscriptions.
--
-- Background: bobford00's 3 subs (-> CoastHillBear / candle3873 / divi51) are
-- real-platform rows (apple/google) but were FREE TEST purchases -- no money
-- changed hands and they never went through a real App Store / Play purchase.
-- All three bought the legacy product (com.apestogether.subscription.monthly),
-- so slot_for_product_id() resolved every one to slot=1 -> they all render as
-- "Trader Subscription A". This renumbers the occupying ones to distinct slots
-- (A/B/C) so the in-app per-creator slot mapping + the Subscriptions tab render
-- correctly.
--
-- Why this is safe even though platform != 'admin' (the comped reslot migration,
-- 2026_06_22_reslot_comped_subs.sql, intentionally SKIPS real purchases): these
-- rows have NO real store entitlement behind them, so there is no store "Manage
-- Subscriptions" slot to stay matched to (the usual reason we never renumber a
-- real purchase). Scoped to bobford00 only. Idempotent: re-running is a no-op.
--
-- NOTE: real future multi-creator subscriptions only get distinct slots once the
-- per-creator slot PRODUCTS (com.apestogether.sub.s02..s20 monthly+annual) are
-- live in App Store Connect + Play Console. Until then every real purchase can
-- only buy slot 1's legacy product and will collide here the same way.

BEGIN;

WITH occupying AS (
    -- A subscription "occupies" a slot while it's active, or canceled-but-
    -- still-entitled (paid through the period). Mirrors _subscription_occupies_slot.
    SELECT ms.id, ms.created_at
    FROM mobile_subscription ms
    JOIN "user" u ON u.id = ms.subscriber_id
    WHERE u.username = 'bobford00'
      AND (
            ms.status = 'active'
            OR (ms.status = 'canceled' AND ms.expires_at IS NOT NULL AND ms.expires_at > now())
          )
),
ranked AS (
    SELECT id,
           row_number() OVER (ORDER BY created_at, id) AS rn
    FROM occupying
)
UPDATE mobile_subscription ms
SET slot = ranked.rn
FROM ranked
WHERE ms.id = ranked.id
  AND ms.slot IS DISTINCT FROM ranked.rn;

COMMIT;

-- Verify (expect distinct slots 1,2,3 -> A,B,C):
--   SELECT ms.id, ms.slot, ms.status, u2.username AS creator
--   FROM mobile_subscription ms
--   JOIN "user" u  ON u.id  = ms.subscriber_id
--   JOIN "user" u2 ON u2.id = ms.subscribed_to_id
--   WHERE u.username = 'bobford00'
--   ORDER BY ms.slot;
