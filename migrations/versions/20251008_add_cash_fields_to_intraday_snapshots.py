"""Add cash tracking fields to portfolio_snapshot_intraday

Revision ID: 20251008_intraday_cash
Create Date: 2025-10-08 21:07:00

This migration adds stock_value, cash_proceeds, and max_cash_deployed fields
to the portfolio_snapshot_intraday table to properly track intraday trades.

CRITICAL: Without these fields, intraday buy/sell transactions lose tracking
of cash proceeds, making it impossible to accurately track day trader performance.
"""

from alembic import op
import sqlalchemy as sa


def upgrade():
    """Add cash tracking fields to portfolio_snapshot_intraday"""
    
    # Add stock_value column
    op.add_column('portfolio_snapshot_intraday', 
        sa.Column('stock_value', sa.Float(), nullable=True, server_default='0.0')
    )
    
    # Add cash_proceeds column
    op.add_column('portfolio_snapshot_intraday',
        sa.Column('cash_proceeds', sa.Float(), nullable=True, server_default='0.0')
    )
    
    # Add max_cash_deployed column
    op.add_column('portfolio_snapshot_intraday',
        sa.Column('max_cash_deployed', sa.Float(), nullable=True, server_default='0.0')
    )
    
    # For existing rows, set stock_value = total_value (conservative approach)
    # This assumes existing snapshots had no cash proceeds
    op.execute("""
        UPDATE portfolio_snapshot_intraday 
        SET stock_value = total_value,
            cash_proceeds = 0.0,
            max_cash_deployed = 0.0
        WHERE stock_value IS NULL
    """)
    
    # Now make columns non-nullable
    op.alter_column('portfolio_snapshot_intraday', 'stock_value', nullable=False)
    op.alter_column('portfolio_snapshot_intraday', 'cash_proceeds', nullable=False)
    op.alter_column('portfolio_snapshot_intraday', 'max_cash_deployed', nullable=False)


def downgrade():
    """Remove cash tracking fields from portfolio_snapshot_intraday"""
    
    op.drop_column('portfolio_snapshot_intraday', 'max_cash_deployed')
    op.drop_column('portfolio_snapshot_intraday', 'cash_proceeds')
    op.drop_column('portfolio_snapshot_intraday', 'stock_value')
