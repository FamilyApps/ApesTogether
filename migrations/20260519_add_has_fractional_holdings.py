"""
Migration: Add has_fractional_holdings column to UserPortfolioStats
Date: 2026-05-19
Purpose: Phase E — power the "Hide portfolios with fractional shares" toggle
         on Discover/Leaderboard. The flag is recomputed daily by
         calculate_user_portfolio_stats: True iff at least one Stock row for
         the user has a non-integer quantity (>= 0.0001 off integer).

         Filter is opt-in per request (?hide_fractional=1). Defaults off so
         existing behavior is unchanged. NULL is treated as "unknown — show",
         so users whose stats haven't been recomputed yet won't be filtered
         out before the cron has populated the column.

Idempotent — safe to run multiple times. Uses ADD COLUMN IF NOT EXISTS.

Run from project root:

    # Option 1: Python script (auto-loads .env)
    python migrations/20260519_add_has_fractional_holdings.py

    # Option 2: pass DATABASE_URL explicitly (no .env needed)
    python migrations/20260519_add_has_fractional_holdings.py "postgresql://user:pw@host/db"

After the column exists, hit POST /api/mobile/admin/portfolio-stats/recompute-fractional
to backfill the flag for existing users (one-shot — going forward the daily
market-close cron keeps it fresh via calculate_user_portfolio_stats).

This bypasses Vercel's pooled connection (which enforces a short
statement_timeout that kills the ALTER under any concurrent load).
We connect directly with a 30s statement_timeout and a short lock_timeout
so the ALTER fails fast on contention instead of being killed mid-wait.
"""
import os
import sys
import time
from sqlalchemy import create_engine, text

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from dotenv import load_dotenv
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for env_file in ('.env', '.env.production'):
        path = os.path.join(project_root, env_file)
        if os.path.exists(path):
            load_dotenv(path, override=False)
            print(f"[*] Loaded environment from {env_file}")
            break
except ImportError:
    print("[!] python-dotenv not available; relying on shell environment")


def get_database_url():
    if len(sys.argv) > 1:
        return sys.argv[1]
    url = os.environ.get('DATABASE_URL') or os.environ.get('POSTGRES_URL')
    if url and url.startswith('postgres://'):
        url = url.replace('postgres://', 'postgresql://', 1)
    return url


def run_migration():
    db_url = get_database_url()
    if not db_url:
        print("ERROR: DATABASE_URL is required.")
        print("       Either set it in .env, or pass as first arg:")
        print('       python migrations/20260519_add_has_fractional_holdings.py "postgresql://..."')
        return False

    engine = create_engine(
        db_url,
        connect_args={
            "options": "-c statement_timeout=30000 -c lock_timeout=2000",
        },
        pool_pre_ping=True,
    )

    last_error = None
    for attempt in range(1, 4):
        try:
            with engine.connect() as conn:
                conn = conn.execution_options(isolation_level="AUTOCOMMIT")
                # NULL default keeps "unknown" distinct from "definitely no
                # fractional positions". The endpoint treats NULL as "show"
                # to avoid filtering out users mid-rollout before the cron
                # has populated the column.
                conn.execute(text(
                    'ALTER TABLE user_portfolio_stats '
                    'ADD COLUMN IF NOT EXISTS has_fractional_holdings BOOLEAN'
                ))
                print('[OK] has_fractional_holdings column ensured on user_portfolio_stats')

                result = conn.execute(text("""
                    SELECT column_name, data_type, is_nullable
                    FROM information_schema.columns
                    WHERE table_name = 'user_portfolio_stats'
                      AND column_name = 'has_fractional_holdings'
                """)).fetchone()
                if result:
                    print(f"[VERIFIED] column={result[0]} type={result[1]} nullable={result[2]}")
                    return True
                else:
                    print("[ERROR] Column not visible after ALTER. Aborting.")
                    return False
        except Exception as e:
            last_error = e
            msg = str(e)
            print(f"[attempt {attempt}/3] ALTER failed: {msg[:300]}")
            if 'lock_timeout' in msg.lower() or 'querycanceled' in msg.lower() or 'canceling statement' in msg.lower():
                if attempt < 3:
                    backoff = 2 * attempt
                    print(f"            Likely lock contention. Retrying in {backoff}s...")
                    time.sleep(backoff)
                    continue
            break

    print(f"\n[FAIL] Could not add has_fractional_holdings column after retries: {last_error}")
    return False


if __name__ == '__main__':
    success = run_migration()
    sys.exit(0 if success else 1)
