"""Merge 0006 head revisions

Revision ID: 0007_merge_0006_heads
Revises: 0006_add_postal_details, 0006_add_pickup_fields
Create Date: 2025-12-13 13:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0007_merge_0006_heads'
down_revision = ('0006_add_postal_details', '0006_add_pickup_fields')
branch_labels = None
depends_on = None


def upgrade():
    # This migration is a merge-only revision and doesn't change the DB schema.
    pass


def downgrade():
    # No-op for downgrading; to reverse, one of the branches must be selected explicitly.
    pass
