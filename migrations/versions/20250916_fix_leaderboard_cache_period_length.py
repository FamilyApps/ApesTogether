"""Fix leaderboard cache period field length

Revision ID: 20250916_fix_leaderboard_cache_period_length
Revises: 20250820_add_intraday_support
Create Date: 2025-09-16 14:37:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '20250916_fix_leaderboard_cache_period_length'
down_revision = '20250820_add_intraday_support'
branch_labels = None
depends_on = None

def upgrade():
    # Increase the period field length from 10 to 20 characters
    op.alter_column('leaderboard_cache', 'period',
                    existing_type=sa.String(10),
                    type_=sa.String(20),
                    existing_nullable=False)

def downgrade():
    # Revert the period field length back to 10 characters
    op.alter_column('leaderboard_cache', 'period',
                    existing_type=sa.String(20),
                    type_=sa.String(10),
                    existing_nullable=False)
