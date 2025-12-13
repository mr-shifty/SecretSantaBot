"""convert survey column to JSON

Revision ID: 0004_convert_survey_to_json
Revises: 0003_add_survey_field
Create Date: 2025-12-04 00:30:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0004_convert_survey_to_json'
down_revision = '0003_add_survey_field'
branch_labels = None
depends_on = None


def upgrade():
    # Alter survey column type to JSON where supported (Postgres)
    try:
        op.alter_column('route1_entries', 'survey', type_=sa.JSON(), existing_type=sa.Text(), nullable=True)
    except Exception:
        # Fallback: no-op for DBs that don't support native JSON
        pass


def downgrade():
    try:
        op.alter_column('route1_entries', 'survey', type_=sa.Text(), existing_type=sa.JSON(), nullable=True)
    except Exception:
        pass
