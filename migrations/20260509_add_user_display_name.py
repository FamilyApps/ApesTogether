"""
Migration: Add display_name column to User
Date: 2026-05-09
Purpose: Allow public-facing names that don't conform to the username regex
         (spaces, apostrophes, emoji, brand names, etc.). The `username`
         column stays as the unique URL-safe handle; `display_name` is what
         we render to other users in leaderboards / portfolio headers.

Idempotent — safe to run multiple times. Uses ADD COLUMN IF NOT EXISTS.

Run from project root:

    # Option 1: Python script (auto-loads .env)
    python migrations/20260509_add_user_display_name.py

    # Option 2: pass DATABASE_URL explicitly (no .env needed)
    python migrations/20260509_add_user_display_name.py "postgresql://user:pw@host/db"

This bypasses Vercel's pooled connection (which enforces a short
statement_timeout that kills the ALTER under any concurrent load).
We connect directly with a 30s statement_timeout and a short lock_timeout
so the ALTER fails fast on contention instead of being killed mid-wait.

After the column exists, hit the admin endpoint
    POST /api/mobile/admin/users/set-display-name
to populate display_name for the two copy-trading bots (user_id=13, 14).
"""
import os
import sys
import time
from sqlalchemy import create_engine, text

# Allow imports from project root for sibling modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Auto-load .env so we don't need to set env vars manually
try:
    from dotenv import load_dotenv
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    # Try .env first (local dev), then .env.production
    for env_file in ('.env', '.env.production'):
        path = os.path.join(project_root, env_file)
        if os.path.exists(path):
            load_dotenv(path, override=False)
            print(f"[*] Loaded environment from {env_file}")
            break
except ImportError:
    print("[!] python-dotenv not available; relying on shell environment")


def get_database_url():
    """Read DATABASE_URL from CLI arg, env, or fail with a clear message."""
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
        print('       python migrations/20260509_add_user_display_name.py "postgresql://..."')
        return False

    # Direct (unpooled) connection so we're not subject to Vercel pool's
    # short statement_timeout. Use server-side options to be safe anyway.
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
                # Run in autocommit so the ALTER is its own transaction
                # and we don't hold any locks longer than needed.
                conn = conn.execution_options(isolation_level="AUTOCOMMIT")
                conn.execute(text(
                    'ALTER TABLE "user" ADD COLUMN IF NOT EXISTS display_name VARCHAR(80)'
                ))
                print('[OK] display_name column ensured on "user" table')

                # Verify it stuck
                result = conn.execute(text("""
                    SELECT column_name, data_type, character_maximum_length
                    FROM information_schema.columns
                    WHERE table_name = 'user' AND column_name = 'display_name'
                """)).fetchone()
                if result:
                    print(f"[VERIFIED] column={result[0]} type={result[1]} max_length={result[2]}")
                    return True
                else:
                    print("[ERROR] Column not visible after ALTER. Aborting.")
                    return False
        except Exception as e:
            last_error = e
            msg = str(e)
            print(f"[attempt {attempt}/3] ALTER failed: {msg[:300]}")
            # If the column already exists or there's no concurrent issue,
            # don't bother retrying. Otherwise retry after backoff.
            if 'lock_timeout' in msg.lower() or 'querycanceled' in msg.lower() or 'canceling statement' in msg.lower():
                if attempt < 3:
                    backoff = 2 * attempt
                    print(f"            Likely lock contention. Retrying in {backoff}s...")
                    time.sleep(backoff)
                    continue
            # Non-retryable error
            break

    print(f"\n[FAIL] Could not add display_name column after retries: {last_error}")
    return False


if __name__ == '__main__':
    success = run_migration()
    sys.exit(0 if success else 1)
