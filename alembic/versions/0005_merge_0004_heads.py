"""merge 0004 heads

Revision ID: 0005_merge_0004_heads
Revises: 0004_merge_0003_heads, 0004_convert_survey_to_json
Create Date: 2025-12-09 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0005_merge_0004_heads'
down_revision = ('0004_merge_0003_heads', '0004_convert_survey_to_json')
branch_labels = None
depends_on = None


def upgrade():
    # Merge migration to resolve multiple 0004 heads; no schema changes.
    pass


def downgrade():
    pass
