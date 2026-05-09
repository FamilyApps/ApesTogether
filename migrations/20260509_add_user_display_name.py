"""
Migration: Add display_name column to User
Date: 2026-05-09
Purpose: Allow public-facing names that don't conform to the username regex
         (spaces, apostrophes, emoji, brand names, etc.). The `username`
         column stays as the unique URL-safe handle; `display_name` is what
         we render to other users in leaderboards / portfolio headers.

Idempotent — safe to run multiple times. Uses ADD COLUMN IF NOT EXISTS.

Apply locally:
    python migrations/20260509_add_user_display_name.py

Apply on Vercel (preferred): hit /api/mobile/admin/migrations/add-display-name
once after the deploy. That admin endpoint runs the same SQL plus optionally
sets display_name for the two copy-trading bots (user_id=13, user_id=14) in
the same transaction.
"""
import os
import sys
from sqlalchemy import create_engine, text

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DATABASE_URL = os.environ.get('DATABASE_URL') or os.environ.get('POSTGRES_URL')
if DATABASE_URL and DATABASE_URL.startswith('postgres://'):
    DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql://', 1)


def run_migration():
    if not DATABASE_URL:
        print("Error: DATABASE_URL or POSTGRES_URL is required")
        return False

    engine = create_engine(DATABASE_URL)
    with engine.connect() as conn:
        with conn.begin():
            conn.execute(text("""
                ALTER TABLE "user"
                ADD COLUMN IF NOT EXISTS display_name VARCHAR(80)
            """))
            print('OK Added display_name column to "user" table (or already existed)')
    return True


if __name__ == '__main__':
    success = run_migration()
    sys.exit(0 if success else 1)
