# 🚀 COPY THIS MESSAGE TO START IMPLEMENTATION

---

**Hey Cascade! I'm ready to start implementing the enhanced features we planned yesterday. Let's begin with Week 2.**

## What to Build (Week 2 - SMS/Email Trading)

### 1. Inbound Trading
- Users can text "BUY 10 TSLA" to Twilio number → trade executes
- Users can email trades@apestogether.ai → trade executes  
- Use existing `get_stock_prices()` from `portfolio_performance.py` for pricing
- Send confirmation SMS/email to user

### 2. Enhanced Notifications
- Update notifications to include position percentage
- Format: "🔔 john_trader sold 5 TSLA (50% of position) @ $245.67"
- Only send to REAL subscribers (not ghost subscribers)
- Support both SMS and email per user preference

### 3. Notification Preferences
- Add signup flow to choose default method (email/SMS)
- Add settings page for per-subscription toggles
- Update User model with `phone_number` and `default_notification_method`

### 4. Latency Optimizations (Grok Confirmed)
- Add ping cron (every 4 minutes) to keep functions warm
- Use ThreadPoolExecutor for parallel notification sending (max_workers=20)
- Target: 5-8 seconds from user SMS → subscriber notification ✅

## Implementation Details

**New Endpoints**:
- `POST /api/twilio/inbound` - Handle incoming SMS trades
- `POST /api/email/inbound` - Handle incoming email trades
- `GET /api/health` - Ping endpoint (keep function warm)

**New Files to Create**:
- `services/trading_sms.py`
- `services/trading_email.py`  
- `templates/complete_profile.html` (notification prefs at signup)
- `templates/notification_settings.html` (per-subscription toggles)

**Files to Update**:
- `api/index.py` (add endpoints)
- `services/notification_utils.py` (add position percentage logic)
- `models.py` (add User.phone_number, User.default_notification_method)
- `vercel.json` (add ping cron)

## Success Criteria

- ✅ User texts "BUY 10 TSLA" → trade executes, confirmation sent
- ✅ Subscribers notified within 5-10 seconds
- ✅ Notifications show "50% of position" for sells
- ✅ Users can choose email/SMS at signup
- ✅ Users can toggle per-subscription in settings
- ✅ No Vercel cold starts (ping cron working)

## Reference Documentation

All implementation details are in:
- `ENHANCED_FEATURES.md` (lines 142-300)
- `LATENCY_ANALYSIS.md` (optimization guide)
- `GHOST_SUBSCRIBER_VISIBILITY.md` (ghost subscriber implementation)

## Let's Go!

Start with the inbound SMS endpoint first, then add the latency optimizations. I'll test with my phone number as we go.

🚀 Ready when you are!

---
