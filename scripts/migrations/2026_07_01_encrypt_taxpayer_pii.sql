-- Widen encrypted W-9 PII columns to TEXT so Fernet ciphertext fits.
--
-- App-level encryption is OPT-IN via the TAX_ENCRYPTION_KEY env var
-- (see crypto_utils.py). This migration is safe to run whether or not you
-- enable encryption — it only relaxes column widths. Run it BEFORE setting
-- TAX_ENCRYPTION_KEY in any environment that already has taxpayer_profile rows.
--
-- Existing plaintext rows remain readable after enabling the key (decrypt
-- falls back to raw). Pre-launch there is typically no data to back-fill.

ALTER TABLE taxpayer_profile ALTER COLUMN legal_name    TYPE TEXT;
ALTER TABLE taxpayer_profile ALTER COLUMN business_name TYPE TEXT;
ALTER TABLE taxpayer_profile ALTER COLUMN tin_last4     TYPE TEXT;
ALTER TABLE taxpayer_profile ALTER COLUMN address_line1 TYPE TEXT;
ALTER TABLE taxpayer_profile ALTER COLUMN address_line2 TYPE TEXT;
ALTER TABLE taxpayer_profile ALTER COLUMN city          TYPE TEXT;
ALTER TABLE taxpayer_profile ALTER COLUMN postal_code   TYPE TEXT;
