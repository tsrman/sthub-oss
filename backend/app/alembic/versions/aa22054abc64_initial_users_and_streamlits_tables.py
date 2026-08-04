"""initial: users and streamlits tables

Revision ID: aa22054abc64
Revises:
Create Date: 2026-06-23 03:12:54.593252

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "aa22054abc64"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column(
            "id",
            sa.dialects.postgresql.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("keycloak_sub", sa.String(length=255), nullable=False),
        sa.Column("username", sa.String(length=100), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=True,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("keycloak_sub"),
        sa.UniqueConstraint("username"),
    )
    op.create_index(
        op.f("ix_users_keycloak_sub"), "users", ["keycloak_sub"], unique=False
    )
    op.create_index(op.f("ix_users_username"), "users", ["username"], unique=True)

    op.create_table(
        "streamlits",
        sa.Column(
            "id",
            sa.dialects.postgresql.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("user_id", sa.dialects.postgresql.UUID(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "code",
            sa.Text(),
            server_default='import streamlit as st\nst.write("Hello!")',
            nullable=False,
        ),
        sa.Column("requirements", sa.Text(), server_default="", nullable=False),
        sa.Column("container_id", sa.String(length=255), nullable=True),
        sa.Column(
            "status", sa.String(length=20), server_default="stopped", nullable=False
        ),
        sa.Column("port", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=True,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "name"),
    )
    op.create_index(
        op.f("ix_streamlits_status"), "streamlits", ["status"], unique=False
    )
    op.create_index(
        op.f("ix_streamlits_user_id"), "streamlits", ["user_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_streamlits_user_id"), table_name="streamlits")
    op.drop_index(op.f("ix_streamlits_status"), table_name="streamlits")
    op.drop_table("streamlits")
    op.drop_index(op.f("ix_users_username"), table_name="users")
    op.drop_index(op.f("ix_users_keycloak_sub"), table_name="users")
    op.drop_table("users")
