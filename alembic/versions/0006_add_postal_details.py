"""add postal recipient details and branch/index

Revision ID: 0006_add_postal_details
Revises: 0005_merge_0004_heads
Create Date: 2025-12-12 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0006_add_postal_details'
down_revision = '0005_merge_0004_heads'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('route1_entries', sa.Column('postal_index', sa.String(), nullable=True))
    op.add_column('route1_entries', sa.Column('postal_branch_number', sa.String(), nullable=True))
    op.add_column('route1_entries', sa.Column('postal_recipient_last_name', sa.String(), nullable=True))
    op.add_column('route1_entries', sa.Column('postal_recipient_first_name', sa.String(), nullable=True))
    op.add_column('route1_entries', sa.Column('postal_recipient_patronymic', sa.String(), nullable=True))


def downgrade():
    op.drop_column('route1_entries', 'postal_recipient_patronymic')
    op.drop_column('route1_entries', 'postal_recipient_first_name')
    op.drop_column('route1_entries', 'postal_recipient_last_name')
    op.drop_column('route1_entries', 'postal_branch_number')
    op.drop_column('route1_entries', 'postal_index')
