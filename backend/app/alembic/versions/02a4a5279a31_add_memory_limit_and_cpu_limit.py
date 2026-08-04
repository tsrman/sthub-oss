"""add memory_limit_mb and cpu_limit

Revision ID: 02a4a5279a31
Revises: aa22054abc64
Create Date: 2026-06-24 07:20:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "02a4a5279a31"
down_revision: Union[str, Sequence[str], None] = "aa22054abc64"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    result = conn.execute(
        sa.text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name='streamlits' AND column_name IN ('memory_limit_mb', 'memory_limit', 'cpu_limit') "
            "ORDER BY column_name"
        )
    )
    existing = {row[0] for row in result}

    # If old column name exists, rename it
    if "memory_limit" in existing and "memory_limit_mb" not in existing:
        op.alter_column("streamlits", "memory_limit", new_column_name="memory_limit_mb")
    elif "memory_limit_mb" not in existing:
        op.add_column(
            "streamlits", sa.Column("memory_limit_mb", sa.Integer(), nullable=True)
        )

    if "cpu_limit" not in existing:
        op.add_column("streamlits", sa.Column("cpu_limit", sa.Float(), nullable=True))


def downgrade() -> None:
    conn = op.get_bind()
    result = conn.execute(
        sa.text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name='streamlits' AND column_name IN ('memory_limit_mb', 'memory_limit', 'cpu_limit') "
            "ORDER BY column_name"
        )
    )
    existing = {row[0] for row in result}

    if "memory_limit_mb" in existing:
        op.drop_column("streamlits", "memory_limit_mb")
    if "cpu_limit" in existing:
        op.drop_column("streamlits", "cpu_limit")
