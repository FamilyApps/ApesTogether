"""Add subscription tiers, trade limits, SMS notifications, stock info, and leaderboard models

Revision ID: 20250907_add_subscription_tiers_and_features
Revises: 20250820_add_intraday_support
Create Date: 2025-09-07 18:35:00.000000

"""
from alembic import op
import sqlalchemy as sa
from datetime import datetime

# revision identifiers, used by Alembic.
revision = '20250907_add_subscription_tiers_and_features'
down_revision = '20250820_add_intraday_support'
branch_labels = None
depends_on = None

def upgrade():
    # Create subscription_tier table
    op.create_table('subscription_tier',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tier_name', sa.String(length=50), nullable=False),
        sa.Column('price', sa.Float(), nullable=False),
        sa.Column('max_trades_per_day', sa.Integer(), nullable=False),
        sa.Column('stripe_price_id', sa.String(length=255), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tier_name')
    )
    
    # Create trade_limit table
    op.create_table('trade_limit',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('trade_count', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['user.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'date', name='unique_user_date_trade_limit')
    )
    
    # Create sms_notification table
    op.create_table('sms_notification',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('phone_number', sa.String(length=20), nullable=True),
        sa.Column('is_verified', sa.Boolean(), nullable=True),
        sa.Column('sms_enabled', sa.Boolean(), nullable=True),
        sa.Column('verification_code', sa.String(length=6), nullable=True),
        sa.Column('verification_expires', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['user.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create stock_info table
    op.create_table('stock_info',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('ticker', sa.String(length=10), nullable=False),
        sa.Column('company_name', sa.String(length=200), nullable=True),
        sa.Column('market_cap', sa.BigInteger(), nullable=True),
        sa.Column('cap_classification', sa.String(length=20), nullable=True),
        sa.Column('last_updated', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('ticker')
    )
    
    # Create leaderboard_entry table
    op.create_table('leaderboard_entry',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('period', sa.String(length=10), nullable=False),
        sa.Column('performance_percent', sa.Float(), nullable=False),
        sa.Column('small_cap_percent', sa.Float(), nullable=True),
        sa.Column('large_cap_percent', sa.Float(), nullable=True),
        sa.Column('avg_trades_per_week', sa.Float(), nullable=True),
        sa.Column('portfolio_value', sa.Float(), nullable=True),
        sa.Column('calculated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['user.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'period', name='unique_user_period_leaderboard')
    )

def downgrade():
    op.drop_table('leaderboard_entry')
    op.drop_table('stock_info')
    op.drop_table('sms_notification')
    op.drop_table('trade_limit')
    op.drop_table('subscription_tier')
