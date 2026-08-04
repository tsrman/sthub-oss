"""drop username unique constraint/index

Revision ID: d268fd7131b3
Revises: 2026_06_26_streamlit_redesign
Create Date: 2026-06-27 01:40:00.000000

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d268fd7131b3"
down_revision: Union[str, Sequence[str], None] = "2026_06_26_streamlit_redesign"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _find_username_unique_constraint(conn) -> str | None:
    """Return the name of the unique constraint covering exactly ``users.username``.

    Returns ``None`` if no such constraint exists.
    """
    rows = conn.execute(
        sa.text(
            """
            SELECT tc.constraint_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
              ON tc.constraint_name = kcu.constraint_name
             AND tc.table_schema = kcu.table_schema
            WHERE tc.table_name = 'users'
              AND tc.table_schema = current_schema()
              AND tc.constraint_type = 'UNIQUE'
            GROUP BY tc.constraint_name
            HAVING COUNT(DISTINCT kcu.column_name) = 1
               AND COUNT(DISTINCT kcu.column_name)
                   FILTER (WHERE kcu.column_name = 'username') = 1
            """
        )
    ).fetchall()
    return rows[0][0] if rows else None


def _find_username_unique_index(conn) -> str | None:
    """Return the name of an explicit single-column unique index on ``users.username``.

    Excludes indexes that are backing unique constraints, leaving only
    separately-created unique indexes (e.g. ``ix_users_username``).
    Returns ``None`` if no such index exists.
    """
    rows = conn.execute(
        sa.text(
            """
            SELECT i.indexname
            FROM pg_indexes i
            JOIN pg_class idx_cls ON idx_cls.relname = i.indexname
            JOIN pg_index idx ON idx.indexrelid = idx_cls.oid
            JOIN pg_class tbl ON tbl.oid = idx.indrelid
            JOIN pg_namespace nsp ON nsp.oid = tbl.relnamespace
            JOIN pg_attribute attr
              ON attr.attrelid = tbl.oid
             AND attr.attnum = ANY(idx.indkey)
            WHERE tbl.relname = 'users'
              AND nsp.nspname = current_schema()
              AND idx.indisunique = true
              AND i.indexname NOT IN (
                  SELECT constraint_name
                  FROM information_schema.table_constraints
                  WHERE table_name = 'users'
                    AND table_schema = current_schema()
                    AND constraint_type = 'UNIQUE'
              )
            GROUP BY i.indexname
            HAVING COUNT(DISTINCT attr.attnum) = 1
               AND bool_or(attr.attname = 'username')
            """
        )
    ).fetchall()
    return rows[0][0] if rows else None


def _constraint_exists(conn, table_name: str, constraint_name: str) -> bool:
    row = conn.execute(
        sa.text(
            """
            SELECT 1 FROM information_schema.table_constraints
            WHERE table_name = :table_name
              AND constraint_name = :constraint_name
              AND table_schema = current_schema()
            """
        ),
        {"table_name": table_name, "constraint_name": constraint_name},
    ).fetchone()
    return row is not None


def _index_exists(conn, table_name: str, index_name: str) -> bool:
    row = conn.execute(
        sa.text(
            """
            SELECT 1 FROM pg_indexes
            WHERE tablename = :table_name
              AND indexname = :index_name
              AND schemaname = current_schema()
            """
        ),
        {"table_name": table_name, "index_name": index_name},
    ).fetchone()
    return row is not None


def upgrade() -> None:
    conn = op.get_bind()

    constraint_name = _find_username_unique_constraint(conn)
    if constraint_name:
        op.drop_constraint(constraint_name, "users", type_="unique")

    index_name = _find_username_unique_index(conn)
    if index_name:
        op.drop_index(index_name, table_name="users")


def downgrade() -> None:
    conn = op.get_bind()

    if not _constraint_exists(conn, "users", "users_username_key"):
        op.create_unique_constraint("users_username_key", "users", ["username"])

    if not _index_exists(conn, "users", "ix_users_username"):
        op.create_index("ix_users_username", "users", ["username"], unique=True)
