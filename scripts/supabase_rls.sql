-- =============================================================================
-- Supabase Row Level Security (RLS) for ApesTogether
-- =============================================================================
-- 
-- Run this in your Supabase SQL Editor (Dashboard > SQL Editor > New Query).
--
-- IMPORTANT: This app uses a SERVICE_ROLE key from the backend (Flask),
-- which bypasses RLS entirely. RLS only restricts the anon/public key
-- and any direct Supabase client calls (e.g., from a future mobile SDK).
--
-- Strategy:
--   - Enable RLS on every table so the anon key has ZERO access by default.
--   - Add SELECT policies only for truly public data (leaderboard, market data).
--   - All writes go through the Flask backend using the service_role key.
-- =============================================================================

-- ---------------------------------------------------------------------------
-- 1. Enable RLS on all tables (blocks anon key by default)
-- ---------------------------------------------------------------------------

ALTER TABLE "user"                     ENABLE ROW LEVEL SECURITY;
ALTER TABLE "stock"                    ENABLE ROW LEVEL SECURITY;
ALTER TABLE "subscription"             ENABLE ROW LEVEL SECURITY;
ALTER TABLE "stock_transaction"        ENABLE ROW LEVEL SECURITY;
ALTER TABLE "portfolio_snapshot"       ENABLE ROW LEVEL SECURITY;
ALTER TABLE "market_data"              ENABLE ROW LEVEL SECURITY;
ALTER TABLE "portfolio_snapshot_intraday" ENABLE ROW LEVEL SECURITY;
ALTER TABLE "sp500_chart_cache"        ENABLE ROW LEVEL SECURITY;
ALTER TABLE "leaderboard_cache"        ENABLE ROW LEVEL SECURITY;
ALTER TABLE "user_portfolio_chart_cache" ENABLE ROW LEVEL SECURITY;
ALTER TABLE "dividend"                 ENABLE ROW LEVEL SECURITY;
ALTER TABLE "alpha_vantage_api_log"    ENABLE ROW LEVEL SECURITY;
ALTER TABLE "user_activity"            ENABLE ROW LEVEL SECURITY;
ALTER TABLE "platform_metrics"         ENABLE ROW LEVEL SECURITY;
ALTER TABLE "subscription_tier"        ENABLE ROW LEVEL SECURITY;
ALTER TABLE "trade_limit"              ENABLE ROW LEVEL SECURITY;
ALTER TABLE "sms_notification"         ENABLE ROW LEVEL SECURITY;
ALTER TABLE "stock_info"               ENABLE ROW LEVEL SECURITY;
ALTER TABLE "leaderboard_entry"        ENABLE ROW LEVEL SECURITY;
ALTER TABLE "user_portfolio_stats"     ENABLE ROW LEVEL SECURITY;
ALTER TABLE "notification_log_old"     ENABLE ROW LEVEL SECURITY;
ALTER TABLE "xero_sync_log"            ENABLE ROW LEVEL SECURITY;
ALTER TABLE "agent_config"             ENABLE ROW LEVEL SECURITY;
ALTER TABLE "admin_subscription"       ENABLE ROW LEVEL SECURITY;
ALTER TABLE "notification_preferences" ENABLE ROW LEVEL SECURITY;
ALTER TABLE "notification_log"         ENABLE ROW LEVEL SECURITY;
ALTER TABLE "device_token"             ENABLE ROW LEVEL SECURITY;
ALTER TABLE "in_app_purchase"          ENABLE ROW LEVEL SECURITY;
ALTER TABLE "push_notification_log"    ENABLE ROW LEVEL SECURITY;
ALTER TABLE "xero_payout_record"       ENABLE ROW LEVEL SECURITY;
ALTER TABLE "pending_trade"            ENABLE ROW LEVEL SECURITY;
ALTER TABLE "mobile_subscription"      ENABLE ROW LEVEL SECURITY;
ALTER TABLE "sessions"                 ENABLE ROW LEVEL SECURITY;

-- ---------------------------------------------------------------------------
-- 2. Public READ-ONLY policies (anon key can read these)
-- ---------------------------------------------------------------------------

-- Leaderboard cache is public — powers the landing page
CREATE POLICY "Public read leaderboard_cache"
  ON "leaderboard_cache" FOR SELECT
  USING (true);

-- Market data (S&P 500 history) is public reference data
CREATE POLICY "Public read market_data"
  ON "market_data" FOR SELECT
  USING (true);

-- S&P 500 chart cache is public
CREATE POLICY "Public read sp500_chart_cache"
  ON "sp500_chart_cache" FOR SELECT
  USING (true);

-- Stock info (company names, market cap classification) is public
CREATE POLICY "Public read stock_info"
  ON "stock_info" FOR SELECT
  USING (true);

-- Subscription tier definitions are public (pricing page)
CREATE POLICY "Public read subscription_tier"
  ON "subscription_tier" FOR SELECT
  USING (true);

-- Leaderboard entries are public (shown on leaderboard)
CREATE POLICY "Public read leaderboard_entry"
  ON "leaderboard_entry" FOR SELECT
  USING (true);

-- Limited user fields are public (username, slug for leaderboard display)
-- NOTE: This exposes all columns. If you want column-level control,
-- use a Supabase View instead. The Flask backend controls what it returns.
CREATE POLICY "Public read user profiles"
  ON "user" FOR SELECT
  USING (true);

-- User portfolio stats are shown on public profiles
CREATE POLICY "Public read user_portfolio_stats"
  ON "user_portfolio_stats" FOR SELECT
  USING (true);

-- ---------------------------------------------------------------------------
-- 3. No INSERT/UPDATE/DELETE policies for anon key
-- ---------------------------------------------------------------------------
-- By enabling RLS and only adding SELECT policies above, the anon key
-- cannot write to ANY table. All mutations go through the Flask backend
-- which uses the service_role key (bypasses RLS).
--
-- If you later add Supabase Auth (e.g., for a mobile SDK), add policies like:
--
--   CREATE POLICY "Users can read own stocks"
--     ON "stock" FOR SELECT
--     USING (auth.uid()::int = user_id);
--
--   CREATE POLICY "Users can insert own trades"
--     ON "stock_transaction" FOR INSERT
--     WITH CHECK (auth.uid()::int = user_id);

-- ---------------------------------------------------------------------------
-- 4. Verify RLS is enabled on all tables
-- ---------------------------------------------------------------------------
-- Run this query to confirm:
--
--   SELECT schemaname, tablename, rowsecurity
--   FROM pg_tables
--   WHERE schemaname = 'public'
--   ORDER BY tablename;
--
-- Every row should show rowsecurity = true.
