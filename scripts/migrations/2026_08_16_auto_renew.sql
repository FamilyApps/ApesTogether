-- Store auto-renew display flag on subscriptions.
-- False after the user cancels but before the period ends, so clients can
-- render "Ends <date>" instead of "Renews <date>". Display-only: `status`
-- remains the sole access gate. NULL = unknown (legacy rows / no
-- renewal-status notification yet) -> clients treat as renewing.
-- Written by iap_webhooks (Apple DID_CHANGE_RENEWAL_STATUS; Google RTDN
-- authoritative re-fetch autoRenewEnabled).

ALTER TABLE mobile_subscription ADD COLUMN IF NOT EXISTS auto_renew BOOLEAN;
