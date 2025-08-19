"""Add portfolio performance tracking models

Revision ID: 20250819_add_portfolio_performance_models
Revises: 20250715_add_created_at_to_user
Create Date: 2025-08-19 19:16:32.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20250819_add_portfolio_performance_models'
down_revision = '20250715_add_created_at_to_user'
branch_labels = None
depends_on = None


def upgrade():
    # Create portfolio_snapshot table
    op.create_table('portfolio_snapshot',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('total_value', sa.Float(), nullable=False),
        sa.Column('cash_flow', sa.Float(), nullable=True, default=0.0),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['user.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'date', name='unique_user_date_snapshot')
    )
    
    # Create market_data table
    op.create_table('market_data',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('symbol', sa.String(length=10), nullable=False),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('close_price', sa.Float(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('symbol', 'date', name='unique_symbol_date')
    )


def downgrade():
    # Drop tables in reverse order
    op.drop_table('market_data')
    op.drop_table('portfolio_snapshot')
