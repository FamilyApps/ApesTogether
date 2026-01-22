"""
Migration: Add Mobile App Tables
Created: January 21, 2026
Phase: 1 - Backend Preparation

New tables:
- device_token: Push notification tokens for iOS/Android
- in_app_purchase: Apple/Google IAP records
- push_notification_log: Push notification delivery log
- xero_payout_record: Influencer payout tracking for Xero
- mobile_subscription: Mobile app subscription linking

Updates:
- admin_subscription: Add bonus_subscriber_count, updated_at columns
"""

import os
import sys
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def run_migration(db_url=None):
    """Run the migration to add mobile app tables"""
    from sqlalchemy import create_engine, text
    
    # Use provided URL or get from environment
    if not db_url:
        db_url = os.environ.get('DATABASE_URL')
        if not db_url:
            raise ValueError("DATABASE_URL environment variable not set")
    
    # Handle Heroku-style postgres:// URLs
    if db_url.startswith('postgres://'):
        db_url = db_url.replace('postgres://', 'postgresql://', 1)
    
    engine = create_engine(db_url)
    
    with engine.connect() as conn:
        # Start transaction
        trans = conn.begin()
        
        try:
            # 1. Create device_token table
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS device_token (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES "user"(id),
                    token VARCHAR(500) NOT NULL,
                    platform VARCHAR(10) NOT NULL,
                    device_id VARCHAR(100),
                    app_version VARCHAR(20),
                    os_version VARCHAR(20),
                    is_active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_used_at TIMESTAMP,
                    CONSTRAINT unique_user_device UNIQUE (user_id, device_id)
                )
            """))
            print("✓ Created device_token table")
            
            # 2. Create in_app_purchase table
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS in_app_purchase (
                    id SERIAL PRIMARY KEY,
                    subscriber_id INTEGER NOT NULL REFERENCES "user"(id),
                    subscribed_to_id INTEGER NOT NULL REFERENCES "user"(id),
                    platform VARCHAR(10) NOT NULL,
                    product_id VARCHAR(100) NOT NULL,
                    transaction_id VARCHAR(200) UNIQUE NOT NULL,
                    original_transaction_id VARCHAR(200),
                    receipt_data TEXT,
                    status VARCHAR(20) NOT NULL DEFAULT 'active',
                    purchase_date TIMESTAMP NOT NULL,
                    expires_date TIMESTAMP,
                    price FLOAT DEFAULT 9.00,
                    currency VARCHAR(3) DEFAULT 'USD',
                    influencer_payout FLOAT DEFAULT 5.40,
                    platform_revenue FLOAT DEFAULT 0.90,
                    store_fee FLOAT DEFAULT 2.70,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))
            print("✓ Created in_app_purchase table")
            
            # 3. Create push_notification_log table
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS push_notification_log (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES "user"(id),
                    portfolio_owner_id INTEGER NOT NULL REFERENCES "user"(id),
                    device_token_id INTEGER REFERENCES device_token(id),
                    title VARCHAR(200) NOT NULL,
                    body VARCHAR(500) NOT NULL,
                    data_payload JSONB,
                    status VARCHAR(20) NOT NULL,
                    fcm_message_id VARCHAR(200),
                    error_message VARCHAR(500),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    delivered_at TIMESTAMP
                )
            """))
            print("✓ Created push_notification_log table")
            
            # 4. Create xero_payout_record table
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS xero_payout_record (
                    id SERIAL PRIMARY KEY,
                    portfolio_user_id INTEGER NOT NULL REFERENCES "user"(id),
                    period_start DATE NOT NULL,
                    period_end DATE NOT NULL,
                    real_subscriber_count INTEGER DEFAULT 0,
                    bonus_subscriber_count INTEGER DEFAULT 0,
                    total_subscriber_count INTEGER DEFAULT 0,
                    gross_revenue FLOAT DEFAULT 0.0,
                    store_fees FLOAT DEFAULT 0.0,
                    platform_revenue FLOAT DEFAULT 0.0,
                    influencer_payout FLOAT DEFAULT 0.0,
                    bonus_payout FLOAT DEFAULT 0.0,
                    xero_invoice_id VARCHAR(100),
                    xero_contact_id VARCHAR(100),
                    xero_synced_at TIMESTAMP,
                    xero_sync_status VARCHAR(20) DEFAULT 'pending',
                    xero_error VARCHAR(500),
                    payment_status VARCHAR(20) DEFAULT 'pending',
                    paid_at TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))
            print("✓ Created xero_payout_record table")
            
            # 5. Create mobile_subscription table
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS mobile_subscription (
                    id SERIAL PRIMARY KEY,
                    subscriber_id INTEGER NOT NULL REFERENCES "user"(id),
                    subscribed_to_id INTEGER NOT NULL REFERENCES "user"(id),
                    in_app_purchase_id INTEGER NOT NULL REFERENCES in_app_purchase(id),
                    status VARCHAR(20) NOT NULL DEFAULT 'active',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    expires_at TIMESTAMP,
                    push_notifications_enabled BOOLEAN DEFAULT TRUE
                )
            """))
            print("✓ Created mobile_subscription table")
            
            # 6. Update admin_subscription table with new columns
            # Check if columns exist first
            result = conn.execute(text("""
                SELECT column_name FROM information_schema.columns 
                WHERE table_name = 'admin_subscription' AND column_name = 'bonus_subscriber_count'
            """))
            if not result.fetchone():
                conn.execute(text("""
                    ALTER TABLE admin_subscription 
                    ADD COLUMN IF NOT EXISTS bonus_subscriber_count INTEGER DEFAULT 0,
                    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                """))
                # Migrate data from ghost_subscriber_count to bonus_subscriber_count
                conn.execute(text("""
                    UPDATE admin_subscription 
                    SET bonus_subscriber_count = COALESCE(ghost_subscriber_count, 0)
                    WHERE bonus_subscriber_count = 0 OR bonus_subscriber_count IS NULL
                """))
                print("✓ Updated admin_subscription table with new columns")
            else:
                print("✓ admin_subscription already has new columns")
            
            # 7. Create indexes for performance
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_device_token_user_id ON device_token(user_id);
                CREATE INDEX IF NOT EXISTS idx_device_token_platform ON device_token(platform);
                CREATE INDEX IF NOT EXISTS idx_in_app_purchase_subscriber ON in_app_purchase(subscriber_id);
                CREATE INDEX IF NOT EXISTS idx_in_app_purchase_subscribed_to ON in_app_purchase(subscribed_to_id);
                CREATE INDEX IF NOT EXISTS idx_in_app_purchase_status ON in_app_purchase(status);
                CREATE INDEX IF NOT EXISTS idx_push_log_user ON push_notification_log(user_id);
                CREATE INDEX IF NOT EXISTS idx_push_log_status ON push_notification_log(status);
                CREATE INDEX IF NOT EXISTS idx_xero_payout_user ON xero_payout_record(portfolio_user_id);
                CREATE INDEX IF NOT EXISTS idx_mobile_sub_subscriber ON mobile_subscription(subscriber_id);
                CREATE INDEX IF NOT EXISTS idx_mobile_sub_subscribed_to ON mobile_subscription(subscribed_to_id);
            """))
            print("✓ Created indexes")
            
            # Commit transaction
            trans.commit()
            print("\n✅ Migration completed successfully!")
            return True
            
        except Exception as e:
            trans.rollback()
            print(f"\n❌ Migration failed: {e}")
            raise


def rollback_migration(db_url=None):
    """Rollback the migration (drop tables)"""
    from sqlalchemy import create_engine, text
    
    if not db_url:
        db_url = os.environ.get('DATABASE_URL')
        if not db_url:
            raise ValueError("DATABASE_URL environment variable not set")
    
    if db_url.startswith('postgres://'):
        db_url = db_url.replace('postgres://', 'postgresql://', 1)
    
    engine = create_engine(db_url)
    
    with engine.connect() as conn:
        trans = conn.begin()
        try:
            # Drop in reverse order of dependencies
            conn.execute(text("DROP TABLE IF EXISTS mobile_subscription CASCADE"))
            conn.execute(text("DROP TABLE IF EXISTS push_notification_log CASCADE"))
            conn.execute(text("DROP TABLE IF EXISTS xero_payout_record CASCADE"))
            conn.execute(text("DROP TABLE IF EXISTS in_app_purchase CASCADE"))
            conn.execute(text("DROP TABLE IF EXISTS device_token CASCADE"))
            
            trans.commit()
            print("✅ Rollback completed - tables dropped")
            return True
        except Exception as e:
            trans.rollback()
            print(f"❌ Rollback failed: {e}")
            raise


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Mobile App Tables Migration')
    parser.add_argument('--rollback', action='store_true', help='Rollback migration')
    args = parser.parse_args()
    
    if args.rollback:
        rollback_migration()
    else:
        run_migration()
