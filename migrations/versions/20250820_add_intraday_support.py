"""Add intraday support to MarketData model

Revision ID: 20250820_add_intraday_support
Revises: 20250819_add_portfolio_performance_models
Create Date: 2025-08-20 09:15:04.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import sqlite

# revision identifiers, used by Alembic.
revision = '20250820_add_intraday_support'
down_revision = '20250819_add_portfolio_performance_models'
branch_labels = None
depends_on = None


def upgrade():
    # Add timestamp column for intraday data
    op.add_column('market_data', sa.Column('timestamp', sa.DateTime(), nullable=True))
    
    # Increase symbol column size to accommodate longer names like 'SPY_SP500_INTRADAY'
    op.alter_column('market_data', 'symbol',
                    existing_type=sa.VARCHAR(length=10),
                    type_=sa.VARCHAR(length=20),
                    existing_nullable=False)
    
    # Drop old unique constraint
    op.drop_constraint('unique_symbol_date', 'market_data', type_='unique')
    
    # Add new unique constraint including timestamp
    op.create_unique_constraint('unique_symbol_date_timestamp', 'market_data', ['symbol', 'date', 'timestamp'])


def downgrade():
    # Drop new unique constraint
    op.drop_constraint('unique_symbol_date_timestamp', 'market_data', type_='unique')
    
    # Recreate old unique constraint
    op.create_unique_constraint('unique_symbol_date', 'market_data', ['symbol', 'date'])
    
    # Revert symbol column size
    op.alter_column('market_data', 'symbol',
                    existing_type=sa.VARCHAR(length=20),
                    type_=sa.VARCHAR(length=10),
                    existing_nullable=False)
    
    # Drop timestamp column
    op.drop_column('market_data', 'timestamp')
