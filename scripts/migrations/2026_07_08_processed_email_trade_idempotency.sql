-- ============================================================================
-- 2026-07-08 — processed_email_trade: server-side idempotency for email copy trades
-- ============================================================================
-- Root-cause fix for the unpause-replay incident (4 stale sells mirrored into
-- Wolff's Flagship Fund). bot_email_trade now dedupes on the stable Gmail
-- message_id and, while paused, records each inbound message as
-- 'skipped_paused' so resuming ingestion can never re-execute pause-window
-- emails. This table is that ledger. Matches models.py::ProcessedEmailTrade.
--
-- Order of operations: run this migration BEFORE (or with) the deploy. The code
-- degrades gracefully if the table is missing (lookup rolls back + warns, no
-- dedupe), but idempotency is only active once this table exists.
--
-- SAFE / IDEMPOTENT: CREATE TABLE IF NOT EXISTS — re-running is a no-op.
-- HOW TO RUN (Supabase SQL Editor): paste + Run the whole file.
-- ============================================================================

CREATE TABLE IF NOT EXISTS processed_email_trade (
    id            SERIAL PRIMARY KEY,
    message_id    VARCHAR(255) NOT NULL,
    status        VARCHAR(30)  NOT NULL,   -- executed | deferred | mixed | executed_manual | skipped_paused
    email_subject VARCHAR(500),
    received_at   TIMESTAMP,               -- email_received_at from GAS
    processed_at  TIMESTAMP    NOT NULL DEFAULT (now() AT TIME ZONE 'utc'),
    trades_count  INTEGER      NOT NULL DEFAULT 0,
    detail        TEXT
);

-- Single unique index — matches SQLAlchemy Column(unique=True, index=True) and
-- backs both dedupe lookups and the ON CONFLICT / IntegrityError race guard.
CREATE UNIQUE INDEX IF NOT EXISTS ix_processed_email_trade_message_id
    ON processed_email_trade (message_id);

-- Verify:
SELECT column_name, data_type, is_nullable
  FROM information_schema.columns
 WHERE table_name = 'processed_email_trade'
 ORDER BY ordinal_position;
