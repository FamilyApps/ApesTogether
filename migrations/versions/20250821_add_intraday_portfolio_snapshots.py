"""Add intraday portfolio snapshots table

Revision ID: 20250821_add_intraday_portfolio_snapshots
Revises: 20250820_add_intraday_support
Create Date: 2025-08-21 15:35:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import sqlite

# revision identifiers, used by Alembic.
revision = '20250821_add_intraday_portfolio_snapshots'
down_revision = '20250820_add_intraday_support'
branch_labels = None
depends_on = None


def upgrade():
    # Create intraday portfolio snapshots table
    op.create_table('portfolio_snapshot_intraday',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('timestamp', sa.DateTime(), nullable=False),
        sa.Column('total_value', sa.Float(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['user.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'timestamp', name='unique_user_timestamp_intraday')
    )
    
    # Create index for efficient queries
    op.create_index('idx_intraday_user_timestamp', 'portfolio_snapshot_intraday', ['user_id', 'timestamp'])
    
    # Create table for pre-generated S&P 500 chart data
    op.create_table('sp500_chart_cache',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('period', sa.String(10), nullable=False),
        sa.Column('chart_data', sa.Text(), nullable=False),  # JSON string
        sa.Column('generated_at', sa.DateTime(), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('period', name='unique_period_chart')
    )


def downgrade():
    op.drop_index('idx_intraday_user_timestamp', table_name='portfolio_snapshot_intraday')
    op.drop_table('sp500_chart_cache')
    op.drop_table('portfolio_snapshot_intraday')
