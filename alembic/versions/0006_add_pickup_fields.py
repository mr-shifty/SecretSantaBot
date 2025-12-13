"""Add pickup_index, pickup_point_id and pickup_delivery_mode

Revision ID: 0006_add_pickup_fields
Revises: 0005_merge_0004_heads
Create Date: 2025-12-13 12:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0006_add_pickup_fields'
down_revision = '0005_merge_0004_heads'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('route1_entries', sa.Column('pickup_index', sa.String(), nullable=True))
    op.add_column('route1_entries', sa.Column('pickup_point_id', sa.String(), nullable=True))
    op.add_column('route1_entries', sa.Column('pickup_delivery_mode', sa.String(), nullable=True))


def downgrade():
    op.drop_column('route1_entries', 'pickup_delivery_mode')
    op.drop_column('route1_entries', 'pickup_point_id')
    op.drop_column('route1_entries', 'pickup_index')
