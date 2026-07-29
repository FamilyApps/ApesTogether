-- ─────────────────────────────────────────────────────────────────────────
-- Anonymize feature-poll votes once a poll closes
-- ─────────────────────────────────────────────────────────────────────────
-- Run this BEFORE deploying the poll-anonymization code (the deactivation
-- paths write user_id = NULL, which fails while the column is NOT NULL).
--
-- Idempotent — safe to re-run.
--
-- Why: user_id on feature_poll_vote exists only to enforce one-vote-per-user
-- and show "you voted X" while a poll is OPEN. Once a poll closes, only the
-- anonymous tally matters. Severing the link means closed-poll opinions are
-- no longer personal data (and don't appear in GDPR data exports).
--
-- The unique_poll_user_vote constraint stays: Postgres treats NULLs as
-- distinct, so any number of anonymized rows per poll coexist fine, while
-- active-poll rows (user_id set) remain deduplicated.

-- 1. Allow the anonymized state.
ALTER TABLE feature_poll_vote ALTER COLUMN user_id DROP NOT NULL;

-- 2. One-time backfill: sever the link on votes for already-closed polls.
UPDATE feature_poll_vote
SET user_id = NULL
WHERE user_id IS NOT NULL
  AND poll_id IN (SELECT id FROM feature_poll WHERE active = false);
