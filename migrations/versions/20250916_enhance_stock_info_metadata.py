"""Enhance StockInfo with comprehensive metadata fields

Revision ID: 20250916_enhance_stock_info_metadata
Revises: 20250916_fix_leaderboard_cache_period_length
Create Date: 2025-09-16 15:03:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '20250916_enhance_stock_info_metadata'
down_revision = '20250916_fix_leaderboard_cache_period_length'
branch_labels = None
depends_on = None

def upgrade():
    # Add new columns to stock_info table
    op.add_column('stock_info', sa.Column('sector', sa.String(100), nullable=True))
    op.add_column('stock_info', sa.Column('industry', sa.String(100), nullable=True))
    op.add_column('stock_info', sa.Column('naics_code', sa.String(10), nullable=True))
    op.add_column('stock_info', sa.Column('exchange', sa.String(10), nullable=True))
    op.add_column('stock_info', sa.Column('country', sa.String(5), nullable=True, default='US'))
    op.add_column('stock_info', sa.Column('is_active', sa.Boolean(), nullable=True, default=True))
    
    # Update cap_classification to support more categories
    op.alter_column('stock_info', 'cap_classification',
                    existing_type=sa.String(20),
                    type_=sa.String(20),
                    comment='small, mid, large, mega, unknown')

def downgrade():
    # Remove the new columns
    op.drop_column('stock_info', 'sector')
    op.drop_column('stock_info', 'industry')
    op.drop_column('stock_info', 'naics_code')
    op.drop_column('stock_info', 'exchange')
    op.drop_column('stock_info', 'country')
    op.drop_column('stock_info', 'is_active')
