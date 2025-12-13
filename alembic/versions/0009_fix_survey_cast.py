"""fix survey column values and cast to json

Revision ID: 0009_fix_survey_cast
Revises: 0008_fix_boolean_defaults
Create Date: 2025-12-13 00:45:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0009_fix_survey_cast'
down_revision = '0008_fix_boolean_defaults'
branch_labels = None
depends_on = None


def upgrade():
    # Only apply for PostgreSQL — other DBs (SQLite) will ignore JSON operations
    conn = op.get_bind()
    if conn.dialect.name != 'postgresql':
        return

    # 1) Wrap non-JSON textual values into JSON string values, e.g. "foo" => '"foo"'
    op.execute(
        """
        UPDATE route1_entries
        SET survey = to_json(survey::text)
        WHERE survey IS NOT NULL AND survey !~ '^\\s*[\\{\\[]';
        """
    )

    # 2) For any remaining invalid JSON strings, set them to NULL.
    #    We'll iterate rows and attempt to cast individually inside PL/pgSQL to avoid aborting whole transaction.
    op.execute(
        """
        DO $$
        DECLARE r RECORD;
        BEGIN
            FOR r IN SELECT id, survey FROM route1_entries WHERE survey IS NOT NULL LOOP
                BEGIN
                    PERFORM r.survey::json;
                EXCEPTION WHEN OTHERS THEN
                    UPDATE route1_entries SET survey = NULL WHERE id = r.id;
                END;
            END LOOP;
        END;
        $$;
        """
    )

    # 3) Alter column type to JSON using cast
    op.execute("ALTER TABLE route1_entries ALTER COLUMN survey TYPE json USING survey::json;")


def downgrade():
    conn = op.get_bind()
    if conn.dialect.name != 'postgresql':
        return
    # revert: cast back to text
    op.execute("ALTER TABLE route1_entries ALTER COLUMN survey TYPE text USING survey::text;")
