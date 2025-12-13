"""fix boolean defaults for Postgres

Revision ID: 0008_fix_boolean_defaults
Revises: 0007_merge_0006_heads
Create Date: 2025-12-13 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0008_fix_boolean_defaults'
down_revision = '0007_merge_0006_heads'
branch_labels = None
depends_on = None


def upgrade():
    # Ensure PostgreSQL uses TRUE/FALSE literals for boolean defaults.
    conn = op.get_bind()
    if conn.dialect.name == 'postgresql':
        op.execute("ALTER TABLE users ALTER COLUMN is_active SET DEFAULT true")


def downgrade():
    conn = op.get_bind()
    if conn.dialect.name == 'postgresql':
        op.execute("ALTER TABLE users ALTER COLUMN is_active SET DEFAULT 1")
