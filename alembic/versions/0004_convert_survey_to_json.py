"""convert survey column to JSON

Revision ID: 0004_convert_survey_to_json
Revises: 0003_add_survey_field
Create Date: 2025-12-04 00:30:00.000000
"""
from alembic import op
import sqlalchemy as sa
import json

# revision identifiers, used by Alembic.
revision = '0004_convert_survey_to_json'
down_revision = '0003_add_survey_field'
branch_labels = None
depends_on = None


def upgrade():
    # Only apply for PostgreSQL — other DBs (SQLite) will ignore JSON operations
    conn = op.get_bind()
    if conn.dialect.name != 'postgresql':
        return

    # If column is already json/jsonb, skip
    col_type = conn.execute(sa.text("SELECT data_type FROM information_schema.columns WHERE table_name='route1_entries' AND column_name='survey';")).scalar()
    if col_type in ('json', 'jsonb'):
        return

    # Find rows with invalid JSON and set them to NULL to avoid conversion errors
    rows = conn.execute(sa.text("SELECT id, survey FROM route1_entries WHERE survey IS NOT NULL;"))
    for r in rows:
        survey_text = r[1]
        try:
            json.loads(survey_text)
        except Exception:
            conn.execute(sa.text("UPDATE route1_entries SET survey = NULL WHERE id = :id"), {'id': r[0]})

    # Alter survey column type to JSON using cast
    op.execute("ALTER TABLE route1_entries ALTER COLUMN survey TYPE json USING survey::json;")


def downgrade():
    try:
        op.alter_column('route1_entries', 'survey', type_=sa.Text(), existing_type=sa.JSON(), nullable=True)
    except Exception:
        pass
