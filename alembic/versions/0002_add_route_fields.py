"""add detailed route fields and route2 media

Revision ID: 0002_add_route_fields
Revises: 0001_initial
Create Date: 2025-12-03 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0002_add_route_fields'
down_revision = '0001_initial'
branch_labels = None
depends_on = None


def upgrade():
    # Route1 additions
    op.add_column('route1_entries', sa.Column('pickup_type', sa.String(), nullable=True))
    op.add_column('route1_entries', sa.Column('postal_city', sa.String(), nullable=True))
    op.add_column('route1_entries', sa.Column('postal_street', sa.String(), nullable=True))
    op.add_column('route1_entries', sa.Column('postal_building', sa.String(), nullable=True))
    op.add_column('route1_entries', sa.Column('postal_corpus', sa.String(), nullable=True))
    op.add_column('route1_entries', sa.Column('postal_apartment', sa.String(), nullable=True))
    op.add_column('route1_entries', sa.Column('postal_recipient_fullname', sa.String(), nullable=True))
    op.add_column('route1_entries', sa.Column('postal_recipient_phone', sa.String(), nullable=True))
    op.add_column('route1_entries', sa.Column('pickup_company', sa.String(), nullable=True))
    op.add_column('route1_entries', sa.Column('pickup_address', sa.String(), nullable=True))
    op.add_column('route1_entries', sa.Column('pickup_recipient_fullname', sa.String(), nullable=True))
    op.add_column('route1_entries', sa.Column('pickup_recipient_phone', sa.String(), nullable=True))

    # Route2 additions
    op.add_column('route2_entries', sa.Column('image_path', sa.String(), nullable=True))
    op.add_column('route2_entries', sa.Column('notify_date', sa.DateTime(), nullable=True))


def downgrade():
    # Route2 removals
    op.drop_column('route2_entries', 'notify_date')
    op.drop_column('route2_entries', 'image_path')

    # Route1 removals
    op.drop_column('route1_entries', 'pickup_recipient_phone')
    op.drop_column('route1_entries', 'pickup_recipient_fullname')
    op.drop_column('route1_entries', 'pickup_address')
    op.drop_column('route1_entries', 'pickup_company')
    op.drop_column('route1_entries', 'postal_recipient_phone')
    op.drop_column('route1_entries', 'postal_recipient_fullname')
    op.drop_column('route1_entries', 'postal_apartment')
    op.drop_column('route1_entries', 'postal_corpus')
    op.drop_column('route1_entries', 'postal_building')
    op.drop_column('route1_entries', 'postal_street')
    op.drop_column('route1_entries', 'postal_city')
    op.drop_column('route1_entries', 'pickup_type')
