"""create settings table and add attempts to notification_logs

Revision ID: 0003_add_settings
Revises: 0002_add_route_fields
Create Date: 2025-12-09 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0003_add_settings'
down_revision = '0002_add_route_fields'
branch_labels = None
depends_on = None


def upgrade():
    # Create settings table (key -> value JSON)
    op.create_table(
        'settings',
        sa.Column('key', sa.String(), primary_key=True, nullable=False),
        sa.Column('value', sa.JSON(), nullable=True),
    )

    # Add attempts column to notification_logs (default 0)
    op.add_column('notification_logs', sa.Column('attempts', sa.Integer(), nullable=False, server_default='0'))


def downgrade():
    # Remove attempts column
    op.drop_column('notification_logs', 'attempts')

    # Drop settings table
    op.drop_table('settings')
