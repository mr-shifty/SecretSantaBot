"""add survey field to route1_entries

Revision ID: 0003_add_survey_field
Revises: 0002_add_route_fields
Create Date: 2025-12-04 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0003_add_survey_field'
down_revision = '0002_add_route_fields'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('route1_entries', sa.Column('survey', sa.Text(), nullable=True))


def downgrade():
    op.drop_column('route1_entries', 'survey')

