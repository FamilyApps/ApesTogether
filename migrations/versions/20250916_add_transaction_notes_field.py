"""Add notes field to Transaction model

Revision ID: 20250916_add_transaction_notes_field
Revises: 20250916_enhance_stock_info_metadata
Create Date: 2025-09-16 15:45:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '20250916_add_transaction_notes_field'
down_revision = '20250916_enhance_stock_info_metadata'
branch_labels = None
depends_on = None

def upgrade():
    # Add notes column to stock_transaction table
    op.add_column('stock_transaction', sa.Column('notes', sa.Text(), nullable=True))

def downgrade():
    # Remove the notes column
    op.drop_column('stock_transaction', 'notes')
