# Legacy Code Archive

**Archived: January 21, 2026**

This folder contains code and documentation from the **web app + SMS era** that is no longer active following the mobile app pivot.

## Folder Structure

### `sms_twilio/`
SMS notification system using Twilio - **DEPRECATED**
- `sms_routes.py` - Flask routes for SMS settings
- `sms_utils.py` - Twilio SMS sending utilities
- `trading_sms.py` - Trade alert SMS service
- `sms_settings.html` - Template for SMS preferences

**Replaced by:** `push_notification_service.py` (Firebase Cloud Messaging)

### `docs_web_era/`
Documentation from web app development phases (Sept 2025 - Jan 2026)
- Implementation plans for web-only features
- Week-by-week development logs
- Feature specifications that no longer apply

### `docs_debug_history/`
Historical debugging sessions and Grok consultation records
- Chart issue investigations
- Performance debugging
- Timezone fixes
- One-time analysis documents

### `scripts_one_time/`
One-time migration and debugging scripts
- Database backfill scripts
- Data validation scripts
- Debugging utilities
- SQL migration files

## Why Archived?

On January 21, 2026, the project pivoted from:
- **Web app + SMS notifications + Stripe payments**

To:
- **Native iOS/Android apps + Push notifications + Apple/Google IAP**

The SMS/Twilio infrastructure is no longer needed because:
1. Push notifications replace SMS (free, richer, no per-message cost)
2. Native apps provide better UX than mobile web
3. In-app purchases replace Stripe (simpler for users, platform handles payments)

## Can This Code Be Deleted?

**Not yet.** Keep this archive for:
1. Reference when building mobile features with similar logic
2. Potential rollback if mobile pivot is reversed
3. Historical documentation of design decisions

**Safe to delete after:** Mobile apps reach production and SMS is confirmed unnecessary (estimate: Q2 2026)

## Current Architecture

See `/MOBILE_ARCHITECTURE_PLAN.md` and `/IMPLEMENTATION_PHASES.md` for the current mobile-first architecture.
