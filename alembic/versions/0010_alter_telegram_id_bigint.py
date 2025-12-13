"""alter users.telegram_id to BIGINT

Revision ID: 0010_alter_telegram_id_bigint
Revises: 0009_fix_survey_cast
Create Date: 2025-12-13 01:30:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0010_alter_telegram_id_bigint'
down_revision = '0009_fix_survey_cast'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    if conn.dialect.name != 'postgresql':
        return

    # ALTER COLUMN to BIGINT using cast — this requires values to fit into bigint
    op.execute("ALTER TABLE users ALTER COLUMN telegram_id TYPE bigint USING telegram_id::bigint;")


def downgrade():
    conn = op.get_bind()
    if conn.dialect.name != 'postgresql':
        return

    # If any values are outside 32-bit signed integer range, set them to NULL before casting
    op.execute("UPDATE users SET telegram_id = NULL WHERE telegram_id::bigint > 2147483647 OR telegram_id::bigint < -2147483648;")
    op.execute("ALTER TABLE users ALTER COLUMN telegram_id TYPE integer USING telegram_id::integer;")
