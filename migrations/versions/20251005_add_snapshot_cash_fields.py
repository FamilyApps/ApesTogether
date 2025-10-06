"""Add cash tracking fields to PortfolioSnapshot

Revision ID: 20251005_add_snapshot_cash_fields
Revises: 20251005_add_cash_tracking
Create Date: 2025-10-05

CRITICAL: PortfolioSnapshot needs cash tracking fields for Modified Dietz calculations

New Fields:
- stock_value: Value of stock holdings only
- cash_proceeds: Uninvested cash from sales
- max_cash_deployed: Cumulative capital deployed at this point in time

Why Needed:
For period performance calculations (e.g., 1M, 3M), we need historical values of:
- Beginning stock_value, cash_proceeds, max_cash_deployed
- Ending stock_value, cash_proceeds, max_cash_deployed

Modified Dietz Formula:
Return = (V_end - V_start - CF) / (V_start + W * CF)

Where:
- V_start = stock_value_start + cash_proceeds_start
- V_end = stock_value_end + cash_proceeds_end
- CF = max_cash_deployed_end - max_cash_deployed_start (net deposits)
- W = time-weighted factor

Example:
Aug 1: stock=$10, cash=$5, deployed=$10 → Portfolio=$15
Sep 1: stock=$15, cash=$10, deployed=$15 → Portfolio=$25
CF = $5 (new capital deployed)
Return = ($25 - $15 - $5) / ($15 + 0.5*$5) = 28.6% (NOT 66.7%!)
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '20251005_add_snapshot_cash_fields'
down_revision = '20251005_add_cash_tracking'
branch_labels = None
depends_on = None

def upgrade():
    # Add cash tracking columns to portfolio_snapshot table
    op.add_column('portfolio_snapshot', sa.Column('stock_value', sa.Float(), nullable=True, server_default='0.0'))
    op.add_column('portfolio_snapshot', sa.Column('cash_proceeds', sa.Float(), nullable=True, server_default='0.0'))
    op.add_column('portfolio_snapshot', sa.Column('max_cash_deployed', sa.Float(), nullable=True, server_default='0.0'))

def downgrade():
    op.drop_column('portfolio_snapshot', 'max_cash_deployed')
    op.drop_column('portfolio_snapshot', 'cash_proceeds')
    op.drop_column('portfolio_snapshot', 'stock_value')
