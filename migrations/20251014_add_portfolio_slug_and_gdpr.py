"""
Migration: Add portfolio_slug and deleted_at to User model
Date: 2025-10-14
Purpose: Enable unique shareable URLs and GDPR-compliant account deletion
"""

from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import text
import secrets
import string

def generate_slug():
    """Generate a URL-safe unique slug (11 chars, like nanoid)"""
    alphabet = string.ascii_letters + string.digits  # a-z, A-Z, 0-9
    return ''.join(secrets.choice(alphabet) for _ in range(11))

def upgrade(db: SQLAlchemy):
    """Add portfolio_slug and deleted_at columns, generate slugs for existing users"""
    with db.engine.connect() as conn:
        with conn.begin():
            # Add portfolio_slug column
            conn.execute(text("""
                ALTER TABLE user 
                ADD COLUMN portfolio_slug VARCHAR(20) UNIQUE
            """))
            
            # Add deleted_at column
            conn.execute(text("""
                ALTER TABLE user 
                ADD COLUMN deleted_at DATETIME
            """))
            
            print("✓ Added portfolio_slug and deleted_at columns to user table")
            
            # Generate slugs for existing users
            users = conn.execute(text("SELECT id FROM user WHERE portfolio_slug IS NULL")).fetchall()
            
            for user in users:
                user_id = user[0]
                # Generate unique slug
                while True:
                    slug = generate_slug()
                    # Check if slug already exists
                    existing = conn.execute(text(
                        "SELECT id FROM user WHERE portfolio_slug = :slug"
                    ), {'slug': slug}).fetchone()
                    
                    if not existing:
                        break
                
                # Update user with slug
                conn.execute(text(
                    "UPDATE user SET portfolio_slug = :slug WHERE id = :user_id"
                ), {'slug': slug, 'user_id': user_id})
                
                print(f"✓ Generated slug for user {user_id}: {slug}")
            
            print(f"✓ Migration complete: {len(users)} users updated with portfolio slugs")

def downgrade(db: SQLAlchemy):
    """Remove portfolio_slug and deleted_at columns"""
    with db.engine.connect() as conn:
        with conn.begin():
            conn.execute(text("ALTER TABLE user DROP COLUMN portfolio_slug"))
            conn.execute(text("ALTER TABLE user DROP COLUMN deleted_at"))
            print("✓ Removed portfolio_slug and deleted_at columns from user table")
