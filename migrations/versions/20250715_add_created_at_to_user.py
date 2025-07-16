"""Add created_at column to User table

Revision ID: 20250715_add_created_at
Revises: 
Create Date: 2025-07-15 21:10:00

"""
from alembic import op
import sqlalchemy as sa
from datetime import datetime

# revision identifiers, used by Alembic
revision = '20250715_add_created_at'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    """Add created_at column to User table"""
    op.add_column('user', sa.Column('created_at', sa.DateTime(), nullable=True, server_default=sa.func.now()))


def downgrade():
    """Remove created_at column from User table"""
    op.drop_column('user', 'created_at')
