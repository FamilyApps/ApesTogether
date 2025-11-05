"""Add phone_number and default_notification_method to User

Revision ID: 20251104_user_phone_notification
Revises: 
Create Date: 2025-11-04

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20251104_user_phone_notification'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # Add phone_number column
    op.add_column('user', sa.Column('phone_number', sa.String(length=20), nullable=True))
    
    # Add default_notification_method column with default value 'email'
    op.add_column('user', sa.Column('default_notification_method', sa.String(length=10), nullable=False, server_default='email'))


def downgrade():
    # Remove columns if rolling back
    op.drop_column('user', 'default_notification_method')
    op.drop_column('user', 'phone_number')
