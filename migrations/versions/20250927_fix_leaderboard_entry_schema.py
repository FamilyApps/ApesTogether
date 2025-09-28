"""Fix leaderboard_entry table schema

Revision ID: 20250927_fix_leaderboard_entry_schema
Revises: 20250916_fix_leaderboard_cache_period_length
Create Date: 2025-09-27 20:35:00.000000

The leaderboard_entry table has the wrong schema - it has old columns like 'date' and 'portfolio_value'
instead of the expected 'period' and 'performance_percent' columns. This migration fixes the schema.
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '20250927_fix_leaderboard_entry_schema'
down_revision = '20250916_fix_leaderboard_cache_period_length'
branch_labels = None
depends_on = None

def upgrade():
    # Drop the existing leaderboard_entry table with wrong schema
    op.drop_table('leaderboard_entry')
    
    # Recreate leaderboard_entry table with correct schema
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
    # Drop the correct schema table
    op.drop_table('leaderboard_entry')
    
    # Recreate the old schema (for rollback purposes)
    op.create_table('leaderboard_entry',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('date', sa.Date(), nullable=True),
        sa.Column('portfolio_value', sa.Float(), nullable=True),
        sa.Column('daily_return', sa.Float(), nullable=True),
        sa.Column('total_return', sa.Float(), nullable=True),
        sa.Column('rank_position', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['user.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
