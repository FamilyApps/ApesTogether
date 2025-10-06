"""Add cash tracking fields to User model

Revision ID: 20251005_add_cash_tracking
Revises: 
Create Date: 2025-10-05

DESIGN: max_cash_deployed + cash_proceeds (NOT initial_cash)

max_cash_deployed:
- Cumulative total capital user has ever deployed
- Increases when buying stocks (after using available cash_proceeds)
- Never decreases
- Acts as cost basis for performance calculations

cash_proceeds:
- Uninvested cash from stock sales
- Increases when selling stocks
- Decreases when buying stocks (used before deploying new capital)
- Tracks realized gains sitting as cash

Example:
Day 1: Buy 10 TSLA @ $5 → max_cash_deployed = $50, cash_proceeds = $0
Day 2: Buy 5 AAPL @ $2 → max_cash_deployed = $60, cash_proceeds = $0
Day 3: Sell 5 AAPL @ $1 → max_cash_deployed = $60, cash_proceeds = $5
Day 4: Buy 10 SPY @ $1 → uses $5 cash + $5 new → max_cash_deployed = $65, cash_proceeds = $0

Performance = (portfolio_value - max_cash_deployed) / max_cash_deployed
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '20251005_add_cash_tracking'
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    # Add cash tracking columns to user table
    op.add_column('user', sa.Column('max_cash_deployed', sa.Float(), nullable=False, server_default='0.0'))
    op.add_column('user', sa.Column('cash_proceeds', sa.Float(), nullable=False, server_default='0.0'))

def downgrade():
    op.drop_column('user', 'cash_proceeds')
    op.drop_column('user', 'max_cash_deployed')
