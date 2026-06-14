# IAP Server-to-Server Webhook Setup

Two **public** endpoints receive subscription-lifecycle events directly from Apple and
Google, so the backend learns about renew / cancel / expire / refund **without** waiting
for the client to next call `/purchase/validate`.

| Store | Endpoint |
|-------|----------|
| Apple App Store Server Notifications V2 | `POST https://apestogether.ai/api/mobile/webhooks/apple/notifications` |
| Google Play Real-time Developer Notifications (RTDN) | `POST https://apestogether.ai/api/mobile/webhooks/google/rtdn` |

**Code:** `iap_webhooks.py` (handlers) + the two routes in `mobile_api.py`. Handlers only
**UPDATE** existing `InAppPurchase` / `MobileSubscription` rows (they never create rows —
new subscriptions still only come from an authenticated `/purchase/validate`). Refund/revoke
maps the `MobileSubscription` to `expired`.

**Security model:**
- **Apple** requests are JWS signature-verified (the `x5c` certificate chain; pinned to
  Apple Root CA - G3 when the cert is available).
- **Google** push requests are *not* trusted directly — the handler **re-fetches the
  authoritative subscription state from the Play Developer API** (using our service account),
  so a forged push can only trigger a harmless re-validation, never inject false state.

---

## Part 1 — Apple App Store Server Notifications V2

### A. Set the notification URLs
1. **App Store Connect** → **Apps** → **ApesTogether** → left sidebar **General → App Information**.
2. Scroll to **App Store Server Notifications**.
3. Set **Version** to **Version 2**.
4. **Production Server URL:** `https://apestogether.ai/api/mobile/webhooks/apple/notifications`
5. **Sandbox Server URL:** the same URL (the handler reads the environment from the signed payload).
6. **Save.**

### B. Pin Apple's root certificate (recommended)
Without this, the handler still verifies the `x5c` chain structure + the leaf signature, but it
logs a warning and does **not** pin to Apple's root. To fully pin:
- Download **Apple Root CA - G3**: https://www.apple.com/certificateauthority/AppleRootCA-G3.cer
- **Option 1 (file):** commit it to `certs/AppleRootCA-G3.cer` in the repo (DER, exactly as downloaded).
- **Option 2 (env):** convert to PEM and set the Vercel env var `APPLE_ROOT_CA_G3_PEM` to the PEM text:
  ```
  openssl x509 -inform der -in AppleRootCA-G3.cer -out AppleRootCA-G3.pem
  ```
- Confirm the Vercel env var `APPLE_BUNDLE_ID = com.apestogether.ApesTogether` (this is the default;
  notifications for any other bundle ID are ignored).

### C. Test
1. Request a test notification — App Store Connect's **Request a Test Notification** control, or the
   App Store Server API `POST /inApps/v1/notifications/test`.
2. In **Vercel logs**, confirm a `200` on `/api/mobile/webhooks/apple/notifications`. A `TEST`
   notification carries no transaction, so the handler returns `{"no_transaction": true}` — that's expected.

---

## Part 2 — Google Play Real-time Developer Notifications (RTDN)

These steps use the **same Google Cloud project** whose service-account JSON is already set in the
Vercel env var `GOOGLE_PLAY_CREDENTIALS_JSON` (the one used for purchase validation).

### A. Create a Pub/Sub topic
1. **Google Cloud Console** → **Pub/Sub → Topics → Create Topic**. ID e.g. `play-rtdn`.
   The full resource name will be `projects/PROJECT_ID/topics/play-rtdn`.

### B. Let Google Play publish to the topic
2. Open the topic → **Permissions / Add Principal**.
3. **Principal:** `google-play-developer-notifications@system.gserviceaccount.com`
4. **Role:** `Pub/Sub Publisher` → **Save**. *(Required — Play Console rejects the topic without it.)*

### C. Add a push subscription to our endpoint
5. On the topic → **Create Subscription**.
6. **Delivery type:** Push.
7. **Endpoint URL:** `https://apestogether.ai/api/mobile/webhooks/google/rtdn`
8. Leave **Enable authentication OFF** (the handler does not verify a push OIDC token; safety comes
   from re-fetching state from the Play API). The default acknowledgement deadline is fine.

### D. Register the topic in Play Console
9. **Play Console** → your app → **Monetize → Monetization setup**.
10. **Real-time developer notifications** → **Topic name:** `projects/PROJECT_ID/topics/play-rtdn` → **Save**.
11. Click **Send test notification**.

### E. Test
- In **Vercel logs**, confirm a `200` on `/api/mobile/webhooks/google/rtdn` and the line
  `[RTDN] test notification received` (the handler returns `{"test": true}`).

---

## After setup — verify end-to-end (no real money)
1. Make a sandbox / license-tester purchase, then trigger a **cancel** or **refund** from the store
   (iOS: Xcode StoreKit *Manage Transactions* / Sandbox; Android: Play license-tester subscription).
2. Watch Vercel logs for the webhook `200` and the resulting status flip.
3. Confirm the `InAppPurchase` / `MobileSubscription` row changed status **without** the client
   calling `/purchase/validate` — e.g. re-run `POST /api/mobile/admin/bot/simulate-subscription-lifecycle`
   (the `live_dry_run` block) or inspect the row directly.

---

## Quick reference
- **Apple endpoint:** `/api/mobile/webhooks/apple/notifications`
- **Google endpoint:** `/api/mobile/webhooks/google/rtdn`
- **Env vars:** `APPLE_ROOT_CA_G3_PEM` (optional), `APPLE_BUNDLE_ID` (default `com.apestogether.ApesTogether`), `GOOGLE_PLAY_CREDENTIALS_JSON` (already set for validation).
- **Cert file (optional):** `certs/AppleRootCA-G3.cer`
- **Google publisher SA:** `google-play-developer-notifications@system.gserviceaccount.com` (needs `Pub/Sub Publisher`).
