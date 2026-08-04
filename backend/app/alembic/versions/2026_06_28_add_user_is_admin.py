"""add is_admin flag to users

Revision ID: 8f2a3b4c5d6e
Revises: d268fd7131b3
Create Date: 2026-06-28 10:30:00.000000

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "8f2a3b4c5d6e"
down_revision: Union[str, Sequence[str], None] = "76e136eaa815"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(conn, table_name: str, column_name: str) -> bool:
    row = conn.execute(
        sa.text(
            """
            SELECT 1 FROM information_schema.columns
            WHERE table_name = :table_name
              AND column_name = :column_name
              AND table_schema = current_schema()
            """
        ),
        {"table_name": table_name, "column_name": column_name},
    ).fetchone()
    return row is not None


def upgrade() -> None:
    conn = op.get_bind()
    if not _column_exists(conn, "users", "is_admin"):
        op.add_column(
            "users",
            sa.Column("is_admin", sa.Boolean(), nullable=False, server_default="false"),
        )
    op.alter_column("users", "is_admin", server_default=None)


def downgrade() -> None:
    conn = op.get_bind()
    if _column_exists(conn, "users", "is_admin"):
        op.drop_column("users", "is_admin")
