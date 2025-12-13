"""initial

Revision ID: 0001_initial
Revises: 
Create Date: 2025-11-28 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0001_initial'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'users',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('telegram_id', sa.Integer(), nullable=False, index=True),
        sa.Column('telegram_username', sa.String(), nullable=True),
        sa.Column('first_name', sa.String(), nullable=True),
        sa.Column('last_name', sa.String(), nullable=True),
        sa.Column('phone', sa.String(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=True, server_default=sa.text('true')),
        sa.Column('created_at', sa.DateTime(), nullable=True),
    )

    op.create_table(
        'route1_entries',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('email', sa.String(), nullable=False),
        sa.Column('full_address', sa.Text(), nullable=False),
        sa.Column('delivery_method', sa.String(), nullable=True),
        sa.Column('wishlist', sa.Text(), nullable=True),
        sa.Column('status', sa.String(), nullable=True),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
    )

    op.create_table(
        'route2_entries',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('email', sa.String(), nullable=False),
        sa.Column('status', sa.String(), nullable=True),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
    )

    op.create_table(
        'assignments',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('giver_user_id', sa.Integer(), nullable=False),
        sa.Column('receiver_user_id', sa.Integer(), nullable=False),
        sa.Column('route_type', sa.Integer(), nullable=True),
        sa.Column('assigned_at', sa.DateTime(), nullable=True),
        sa.Column('sent_status', sa.String(), nullable=True),
    )

    op.create_table(
        'notification_logs',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('channel', sa.String(), nullable=False),
        sa.Column('notif_type', sa.String(), nullable=False),
        sa.Column('payload', sa.Text(), nullable=True),
        sa.Column('status', sa.String(), nullable=True),
        sa.Column('sent_at', sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table('notification_logs')
    op.drop_table('assignments')
    op.drop_table('route2_entries')
    op.drop_table('route1_entries')
    op.drop_table('users')
