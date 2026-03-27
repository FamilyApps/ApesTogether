"""
Migration: Drop rendered_html column from leaderboard_cache table

HTML pre-rendering has been removed from the codebase. The rendered_html column
is no longer written to or read from. This migration drops it to save DB space.
"""
import os
import sys
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.environ.get('DATABASE_URL') or os.environ.get('POSTGRES_PRISMA_URL')

if DATABASE_URL and DATABASE_URL.startswith('postgres://'):
    DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql://', 1)


def run_migration():
    """Drop rendered_html column from leaderboard_cache table"""
    if not DATABASE_URL:
        print("Error: No database URL found in environment variables")
        sys.exit(1)

    print("Connecting to database...")

    try:
        engine = create_engine(DATABASE_URL)

        with engine.connect() as conn:
            # Check if column exists before attempting to drop
            result = conn.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'leaderboard_cache' 
                AND column_name = 'rendered_html'
            """))

            if not result.fetchone():
                print("rendered_html column does not exist — nothing to do")
                return

            # Drop the column
            conn.execute(text("""
                ALTER TABLE leaderboard_cache DROP COLUMN rendered_html
            """))
            conn.commit()

            print("Successfully dropped rendered_html column from leaderboard_cache")

    except Exception as e:
        print(f"Migration error: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    run_migration()
