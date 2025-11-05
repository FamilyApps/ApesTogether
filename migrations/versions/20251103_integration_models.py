"""Add integration models for notifications, Xero, and agents

Revision ID: 20251103_integration_models
Create Date: 2025-11-03

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = '20251103_integration_models'
down_revision = None  # Update this to your latest migration
branch_labels = None
depends_on = None


def upgrade():
    # Notification Preferences table
    op.create_table('notification_preferences',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('portfolio_owner_id', sa.Integer(), nullable=False),
        sa.Column('email_enabled', sa.Boolean(), server_default='true'),
        sa.Column('sms_enabled', sa.Boolean(), server_default='false'),
        sa.Column('phone_number', sa.String(length=20), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['user_id'], ['user.id'], ),
        sa.ForeignKeyConstraint(['portfolio_owner_id'], ['user.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'portfolio_owner_id', name='unique_user_portfolio_notification')
    )

    # Notification Log table
    op.create_table('notification_log',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('portfolio_owner_id', sa.Integer(), nullable=False),
        sa.Column('notification_type', sa.String(length=20), nullable=True),
        sa.Column('transaction_id', sa.Integer(), nullable=True),
        sa.Column('sent_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('status', sa.String(length=20), nullable=True),
        sa.Column('twilio_sid', sa.String(length=100), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['user.id'], ),
        sa.ForeignKeyConstraint(['portfolio_owner_id'], ['user.id'], ),
        sa.ForeignKeyConstraint(['transaction_id'], ['stock_transaction.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    # Xero Sync Log table
    op.create_table('xero_sync_log',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('sync_type', sa.String(length=50), nullable=True),
        sa.Column('entity_id', sa.Integer(), nullable=True),
        sa.Column('entity_type', sa.String(length=50), nullable=True),
        sa.Column('xero_invoice_id', sa.String(length=100), nullable=True),
        sa.Column('xero_contact_id', sa.String(length=100), nullable=True),
        sa.Column('amount', sa.Float(), nullable=True),
        sa.Column('synced_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('status', sa.String(length=20), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )

    # Agent Config table
    op.create_table('agent_config',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('personality', postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column('strategy_params', postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column('status', sa.String(length=20), server_default='active'),
        sa.Column('last_trade_at', sa.DateTime(), nullable=True),
        sa.Column('total_trades', sa.Integer(), server_default='0'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['user_id'], ['user.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', name='unique_agent_user')
    )

    # Admin Subscription table (for admin-sponsored subscribers)
    op.create_table('admin_subscription',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('subscriber_id', sa.Integer(), nullable=False),
        sa.Column('subscribed_to_id', sa.Integer(), nullable=False),
        sa.Column('admin_sponsored', sa.Boolean(), server_default='true'),
        sa.Column('monthly_cost', sa.Float(), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['subscriber_id'], ['user.id'], ),
        sa.ForeignKeyConstraint(['subscribed_to_id'], ['user.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('subscriber_id', 'subscribed_to_id', name='unique_admin_subscription')
    )

    # Add role column to User table (for agent vs human distinction)
    op.add_column('user', sa.Column('role', sa.String(length=20), server_default='user'))
    op.add_column('user', sa.Column('created_by', sa.String(length=20), server_default='human'))

    # Create indexes for performance
    op.create_index('idx_notification_log_user_id', 'notification_log', ['user_id'])
    op.create_index('idx_notification_log_sent_at', 'notification_log', ['sent_at'])
    op.create_index('idx_xero_sync_log_entity', 'xero_sync_log', ['entity_type', 'entity_id'])
    op.create_index('idx_agent_config_status', 'agent_config', ['status'])


def downgrade():
    # Drop indexes
    op.drop_index('idx_agent_config_status')
    op.drop_index('idx_xero_sync_log_entity')
    op.drop_index('idx_notification_log_sent_at')
    op.drop_index('idx_notification_log_user_id')

    # Drop columns
    op.drop_column('user', 'created_by')
    op.drop_column('user', 'role')

    # Drop tables
    op.drop_table('admin_subscription')
    op.drop_table('agent_config')
    op.drop_table('xero_sync_log')
    op.drop_table('notification_log')
    op.drop_table('notification_preferences')
