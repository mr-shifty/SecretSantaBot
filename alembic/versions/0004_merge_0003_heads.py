"""merge 0003 heads

Revision ID: 0004_merge_0003_heads
Revises: 0003_add_settings, 0003_add_survey_field
Create Date: 2025-12-09 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0004_merge_0003_heads'
down_revision = ('0003_add_settings', '0003_add_survey_field')
branch_labels = None
depends_on = None


def upgrade():
    # This is a merge migration to resolve multiple heads.
    # It intentionally does not alter the database schema.
    pass


def downgrade():
    pass
