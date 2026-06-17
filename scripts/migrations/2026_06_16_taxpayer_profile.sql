-- ─────────────────────────────────────────────────────────────────────────
-- W-9 / taxpayer info — in-app collection + payout hold (Layer 1)
-- ─────────────────────────────────────────────────────────────────────────
-- Run this BEFORE deploying the W-9 code so POST /tax/w9 and
-- /admin/bot/generate-payout-records have schema to write/read.
--
-- Idempotent (IF NOT EXISTS) — safe to re-run.
--
-- PII note: the FULL TIN (SSN/EIN) is NEVER stored in this table. It is pushed
-- directly to the creator's Xero contact (TaxNumber), which is the system of
-- record for 1099 reporting. We keep only the last 4 digits + status locally.
--
-- Model: models.py → TaxpayerProfile
--
-- How to run (Supabase SQL Editor):
--   1. Open https://supabase.com/dashboard/project/<project>/sql/new
--   2. Paste this entire file
--   3. Click "Run"
--   4. Verify with:
--        SELECT column_name, data_type, is_nullable
--        FROM information_schema.columns
--        WHERE table_name = 'taxpayer_profile';
-- ─────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS taxpayer_profile (
    id                  SERIAL PRIMARY KEY,
    user_id             INTEGER NOT NULL UNIQUE REFERENCES "user"(id),

    -- W-9 identity (non-sensitive parts retained for display/support)
    legal_name          VARCHAR(200),
    business_name       VARCHAR(200),
    tax_classification  VARCHAR(40),
    tin_type            VARCHAR(10),     -- 'ssn' | 'ein'
    tin_last4           VARCHAR(4),      -- last 4 only — full TIN lives in Xero

    -- Mailing address (also pushed to the Xero contact)
    address_line1       VARCHAR(200),
    address_line2       VARCHAR(200),
    city                VARCHAR(100),
    state               VARCHAR(50),
    postal_code         VARCHAR(20),
    country             VARCHAR(2) DEFAULT 'US',

    -- Submission status
    status              VARCHAR(20) NOT NULL DEFAULT 'not_submitted',
    certified           BOOLEAN DEFAULT FALSE,
    certified_at        TIMESTAMP,
    submitted_at        TIMESTAMP,

    -- Xero push status
    xero_contact_id     VARCHAR(100),
    xero_pushed_at      TIMESTAMP,
    xero_push_status    VARCHAR(20) DEFAULT 'pending',
    xero_error          VARCHAR(500),

    created_at          TIMESTAMP DEFAULT (NOW() AT TIME ZONE 'utc'),
    updated_at          TIMESTAMP DEFAULT (NOW() AT TIME ZONE 'utc')
);

-- Fast lookup by user (hold/release checks during payout generation).
CREATE INDEX IF NOT EXISTS ix_taxpayer_profile_user_id
    ON taxpayer_profile (user_id);
