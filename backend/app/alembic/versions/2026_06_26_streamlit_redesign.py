"""streamlit redesign: slug, files, logs, deployments

Revision ID: 2026_06_26_streamlit_redesign
Revises: 02a4a5279a31
Create Date: 2026-06-26 10:00:00.000000

"""

from __future__ import annotations

import base64
import json
import re
import warnings
from typing import Any, Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "2026_06_26_streamlit_redesign"
down_revision: Union[str, Sequence[str], None] = "02a4a5279a31"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

MAX_IDENTIFIER_LEN = 40
# Allows 1-40 chars, no leading/trailing hyphen.
IDENTIFIER_RE = re.compile(
    r"^[a-z0-9]([a-z0-9-]{0," + str(MAX_IDENTIFIER_LEN - 2) + r"}[a-z0-9])?$"
)

# Minimum characters reserved for a collision suffix such as '-1', '-2', etc.
MIN_COLLISION_SUFFIX_ROOM = 3

# Paths that are managed by the core migration, not by extra_files archives.
RESERVED_FILE_PATHS = {"app.py", "requirements.txt"}

# Original defaults from the initial migration (aa22054abc64).
DEFAULT_CODE = 'import streamlit as st\nst.write("Hello!")'
DEFAULT_REQUIREMENTS = ""

# Keep PostgreSQL parameter count well below the 32,767 limit.
CHUNK_SIZE = 1000


def _execute_in_chunks(
    conn,
    statement: "sa.TextClause",
    params: list[dict[str, Any]],
    chunk_size: int = CHUNK_SIZE,
) -> None:
    """Execute a SQL statement repeatedly against batched parameter lists."""
    for i in range(0, len(params), chunk_size):
        conn.execute(statement, params[i : i + chunk_size])


def _normalize_identifier(raw: str, fallback_id: Any, *, kind: str = "u") -> str:
    """PostgreSQL-safe normalization for URL segments (login / slug).

    If truncating to ``MAX_IDENTIFIER_LEN`` would leave no room for a collision
    suffix, the base is capped at ``MAX_IDENTIFIER_LEN - MIN_COLLISION_SUFFIX_ROOM``
    so that ``-1``, ``-2`` can still be appended.  If even that cannot yield a
    valid base, a deterministic ``u-{hex}`` / ``app-{hex}`` fallback is used.
    The fallback is always re-validated and a ``ValueError`` is raised if it
    is somehow still invalid.
    """
    fallback = ""
    if fallback_id is not None:
        # Use the compact hex form of a UUID: lowercase, no hyphens, exactly 32 chars.
        fallback_hex = getattr(
            fallback_id, "hex", str(fallback_id).replace("-", "").lower()
        )
        fallback = f"{kind}-{fallback_hex}"
        if not _is_valid_identifier(fallback):
            raise ValueError(
                f"Generated fallback identifier {fallback!r} is invalid "
                f"(kind={kind!r}, fallback_id={fallback_id!r})"
            )

    if not raw:
        return fallback
    # Lowercase and replace any run of chars outside [a-z0-9-] with a single '-'.
    normalized = re.sub(r"[^a-z0-9-]+", "-", raw.lower())
    # Trim leading/trailing '-'.
    normalized = normalized.strip("-")

    # Reserve room for collision suffixes when the identifier is max-length.
    max_base_len = MAX_IDENTIFIER_LEN - MIN_COLLISION_SUFFIX_ROOM
    if len(normalized) > max_base_len:
        normalized = normalized[:max_base_len].rstrip("-")

    if not normalized or not _is_valid_identifier(normalized):
        return fallback

    return normalized


def _is_valid_identifier(value: str) -> bool:
    return bool(IDENTIFIER_RE.match(value)) and len(value) <= MAX_IDENTIFIER_LEN


def _find_streamlit_user_name_constraint(conn) -> str:
    """Return the actual name of the unique constraint on streamlits(user_id, name).

    The matched constraint must cover **exactly** the columns ``user_id`` and
    ``name`` — no more, no less.  Raises a clear error if zero or multiple
    constraints match.
    """
    rows = conn.execute(
        sa.text(
            """
            SELECT tc.constraint_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
              ON tc.constraint_name = kcu.constraint_name
             AND tc.table_schema = kcu.table_schema
            WHERE tc.table_name = 'streamlits'
              AND tc.table_schema = current_schema()
              AND tc.constraint_type = 'UNIQUE'
            GROUP BY tc.constraint_name
            HAVING COUNT(DISTINCT kcu.column_name) = 2
               AND COUNT(DISTINCT kcu.column_name) FILTER (WHERE kcu.column_name IN ('user_id', 'name')) = 2
            """
        )
    ).fetchall()

    if len(rows) == 1:
        return rows[0][0]

    if len(rows) > 1:
        names = [r[0] for r in rows]
        raise ValueError(
            f"Found multiple unique constraints on streamlits covering user_id+name: {names}. "
            "Cannot determine which one to replace."
        )

    raise ValueError(
        "No unique constraint found on streamlits(user_id, name). "
        "Cannot safely replace it with the new owner+slug/name constraints."
    )


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


def _extra_files_column_exists(conn) -> bool:
    return _column_exists(conn, "streamlits", "extra_files")


def _extra_data_column_exists(conn) -> bool:
    return _column_exists(conn, "streamlits", "extra_data")


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


def _table_exists(conn, table_name: str) -> bool:
    row = conn.execute(
        sa.text(
            """
            SELECT 1 FROM information_schema.tables
            WHERE table_name = :table_name
              AND table_schema = current_schema()
            """
        ),
        {"table_name": table_name},
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


def _resolve_login_backfill(conn) -> None:
    """Backfill users.login with normalized values, resolving collisions."""
    rows = conn.execute(
        sa.text("SELECT id, username FROM users ORDER BY id")
    ).fetchall()

    used: set[str] = set()
    updates: list[dict[str, Any]] = []

    for user_id, username in rows:
        base = _normalize_identifier(username, user_id, kind="u")
        if not base or not _is_valid_identifier(base):
            raise ValueError(f"Normalized login {base!r} for user {user_id} is invalid")

        candidate = base
        suffix_num = 1
        while candidate in used:
            suffix = f"-{suffix_num}"
            if len(base) + len(suffix) > MAX_IDENTIFIER_LEN:
                raise ValueError(
                    f"Cannot resolve login collision for user {user_id}: "
                    f"base {base!r} is too long to append a numeric suffix"
                )
            candidate = base + suffix
            suffix_num += 1

        used.add(candidate)
        updates.append({"login": candidate, "id": user_id})

    if updates:
        _execute_in_chunks(
            conn,
            sa.text("UPDATE users SET login = :login WHERE id = :id"),
            updates,
        )

    # --- post-backfill NULL assertion --------------------------------------
    null_count = conn.execute(
        sa.text("SELECT COUNT(*) FROM users WHERE login IS NULL")
    ).scalar()
    if null_count:
        raise ValueError(
            f"Backfill failed: {null_count} user(s) still have NULL login after backfill"
        )


def _resolve_slug_backfill(conn) -> None:
    """Backfill streamlits.slug with normalized values, resolving per-user collisions."""
    rows = conn.execute(
        sa.text("SELECT id, user_id, name FROM streamlits ORDER BY id")
    ).fetchall()

    used_by_user: dict[Any, set[str]] = {}
    updates: list[dict[str, Any]] = []

    for streamlit_id, user_id, name in rows:
        base = _normalize_identifier(name, streamlit_id, kind="app")
        if not base or not _is_valid_identifier(base):
            raise ValueError(
                f"Normalized slug {base!r} for streamlit {streamlit_id} is invalid"
            )

        used = used_by_user.setdefault(user_id, set())
        candidate = base
        suffix_num = 1
        while candidate in used:
            suffix = f"-{suffix_num}"
            if len(base) + len(suffix) > MAX_IDENTIFIER_LEN:
                raise ValueError(
                    f"Cannot resolve slug collision for streamlit {streamlit_id}: "
                    f"base {base!r} is too long to append a numeric suffix"
                )
            candidate = base + suffix
            suffix_num += 1

        used.add(candidate)
        updates.append({"slug": candidate, "id": streamlit_id})

    if updates:
        _execute_in_chunks(
            conn,
            sa.text("UPDATE streamlits SET slug = :slug WHERE id = :id"),
            updates,
        )

    # --- post-backfill NULL assertion --------------------------------------
    null_count = conn.execute(
        sa.text("SELECT COUNT(*) FROM streamlits WHERE slug IS NULL")
    ).scalar()
    if null_count:
        raise ValueError(
            f"Backfill failed: {null_count} streamlit(s) still have NULL slug after backfill"
        )


def _validate_identifiers(conn) -> None:
    """Post-backfill assertion that every login/slug is valid.

    Reports all failing rows (up to 10) in a single error.
    """
    errors: list[str] = []

    bad_logins = conn.execute(
        sa.text(
            """
            SELECT id, login FROM users
            WHERE login !~ :regex OR LENGTH(login) > :max_len
            ORDER BY id
            LIMIT :limit
            """
        ).bindparams(regex=IDENTIFIER_RE.pattern, max_len=MAX_IDENTIFIER_LEN, limit=11)
    ).fetchall()
    for row in bad_logins[:10]:
        errors.append(f"login {row.login!r} for user {row.id}")
    if len(bad_logins) > 10:
        errors.append("and more invalid logins...")

    bad_slugs = conn.execute(
        sa.text(
            """
            SELECT id, slug FROM streamlits
            WHERE slug !~ :regex OR LENGTH(slug) > :max_len
            ORDER BY id
            LIMIT :limit
            """
        ).bindparams(regex=IDENTIFIER_RE.pattern, max_len=MAX_IDENTIFIER_LEN, limit=11)
    ).fetchall()
    for row in bad_slugs[:10]:
        errors.append(f"slug {row.slug!r} for streamlit {row.id}")
    if len(bad_slugs) > 10:
        errors.append("and more invalid slugs...")

    if errors:
        raise ValueError(
            "Validation failed for the following identifiers:\n"
            + "\n".join(f"  - {e}" for e in errors)
        )


def _restore_extra_files(conn) -> None:
    """If an extra_files archive column exists, restore files and drop the column."""
    if not _extra_files_column_exists(conn):
        return

    # Fetch every existing (streamlit_id, path) pair once to avoid N+1 lookups.
    existing_rows = conn.execute(
        sa.text("SELECT streamlit_id, path FROM streamlit_files")
    ).fetchall()
    existing: set[tuple[Any, str]] = set(existing_rows)

    rows = conn.execute(
        sa.text("SELECT id, extra_files FROM streamlits WHERE extra_files IS NOT NULL")
    ).fetchall()

    inserts: list[dict[str, Any]] = []
    for streamlit_id, extra_files in rows:
        if not extra_files:
            continue
        for path, info in extra_files.items():
            if path in RESERVED_FILE_PATHS:
                warnings.warn(
                    f"Skipping reserved extra_files path {path!r} for streamlit {streamlit_id} "
                    "(handled by core migration)"
                )
                continue
            if (streamlit_id, path) in existing:
                continue
            if isinstance(info, dict):
                content_type = info.get("content_type", "text/plain")
                content_text = info.get("content_text")
                b64 = info.get("content_bytes_b64")
                is_entrypoint = info.get("is_entrypoint", False)
                # Emit content_bytes whenever the archive contains a b64 payload,
                # even if it decodes to empty bytes.
                if b64 is not None:
                    try:
                        content_bytes = base64.b64decode(b64)
                    except Exception as exc:
                        raise ValueError(
                            f"Failed to decode base64 for extra file {path!r} "
                            f"in streamlit {streamlit_id}: {exc}"
                        ) from exc
                else:
                    content_bytes = None
            else:
                content_type = "text/plain"
                content_text = info
                content_bytes = None
                is_entrypoint = False

            inserts.append(
                {
                    "streamlit_id": streamlit_id,
                    "path": path,
                    "content_type": content_type,
                    "content_text": content_text,
                    "content_bytes": content_bytes,
                    "is_entrypoint": is_entrypoint,
                }
            )

    if inserts:
        _execute_in_chunks(
            conn,
            sa.text(
                """
                INSERT INTO streamlit_files
                    (streamlit_id, path, content_type, content_text, content_bytes, is_entrypoint)
                VALUES
                    (:streamlit_id, :path, :content_type, :content_text, :content_bytes, :is_entrypoint)
                """
            ),
            inserts,
        )

    op.drop_column("streamlits", "extra_files")


def _archive_extra_files(conn) -> None:
    """Dump non-core streamlit_files into a temporary extra_files JSONB column."""
    if not _extra_files_column_exists(conn):
        op.add_column(
            "streamlits",
            sa.Column("extra_files", postgresql.JSONB(), nullable=True),
        )

    # Clear any stale archive data so a rerun after partial failure is clean.
    conn.execute(sa.text("UPDATE streamlits SET extra_files = NULL"))

    rows = conn.execute(
        sa.text(
            """
            SELECT streamlit_id, path, content_type, content_text, content_bytes, is_entrypoint
            FROM streamlit_files
            WHERE path NOT IN ('app.py', 'requirements.txt')
            ORDER BY streamlit_id, path
            """
        )
    ).fetchall()

    by_streamlit: dict[Any, dict[str, dict[str, Any]]] = {}
    for (
        streamlit_id,
        path,
        content_type,
        content_text,
        content_bytes,
        is_entrypoint,
    ) in rows:
        info: dict[str, Any] = {
            "content_type": content_type,
            "content_text": content_text,
            "is_entrypoint": is_entrypoint,
        }
        # Preserve empty byte sequences by checking for None, not truthiness.
        if content_bytes is not None:
            info["content_bytes_b64"] = base64.b64encode(content_bytes).decode("ascii")
        by_streamlit.setdefault(streamlit_id, {})[path] = info

    if by_streamlit:
        updates = [
            {"files": json.dumps(files), "id": streamlit_id}
            for streamlit_id, files in by_streamlit.items()
        ]
        _execute_in_chunks(
            conn,
            sa.text(
                "UPDATE streamlits SET extra_files = CAST(:files AS jsonb) WHERE id = :id"
            ),
            updates,
        )


def _archive_version_columns(conn) -> None:
    """Preserve version/python_version/image_tag so a subsequent upgrade can restore them."""
    if not _extra_data_column_exists(conn):
        op.add_column(
            "streamlits",
            sa.Column("extra_data", postgresql.JSONB(), nullable=True),
        )

    # Clear any stale archive data so a rerun after partial failure is clean.
    conn.execute(sa.text("UPDATE streamlits SET extra_data = NULL"))

    # Archive unconditionally for every streamlit row.  Non-nullable columns
    # (version, python_version) always have values; nullable image_tag is
    # stored as JSON null when NULL.
    conn.execute(
        sa.text(
            """
            UPDATE streamlits
            SET extra_data = jsonb_build_object(
                'version', version,
                'python_version', python_version,
                'image_tag', to_jsonb(image_tag)
            )
            """
        )
    )


def _restore_archived_version_columns(conn) -> None:
    """Restore version columns from an extra_data archive left by a previous downgrade."""
    if not _extra_data_column_exists(conn):
        return

    conn.execute(
        sa.text(
            """
            UPDATE streamlits
            SET version = COALESCE((extra_data->>'version')::integer, 0),
                python_version = COALESCE(extra_data->>'python_version', '3.11'),
                image_tag = extra_data->>'image_tag'
            WHERE extra_data IS NOT NULL
            """
        )
    )

    op.drop_column("streamlits", "extra_data")


def upgrade() -> None:
    conn = op.get_bind()

    # --- users: add login -------------------------------------------------
    op.add_column(
        "users", sa.Column("login", sa.String(length=MAX_IDENTIFIER_LEN), nullable=True)
    )

    # --- streamlits: add slug/version/python_version/image_tag ------------
    op.add_column(
        "streamlits",
        sa.Column("slug", sa.String(length=MAX_IDENTIFIER_LEN), nullable=True),
    )
    op.add_column(
        "streamlits",
        sa.Column("version", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "streamlits",
        sa.Column(
            "python_version",
            sa.String(length=10),
            nullable=False,
            server_default="3.11",
        ),
    )
    op.add_column(
        "streamlits",
        sa.Column("image_tag", sa.String(length=255), nullable=True),
    )

    # --- create streamlit_files -------------------------------------------
    op.create_table(
        "streamlit_files",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("streamlit_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("path", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=100), nullable=False),
        sa.Column("content_text", sa.Text(), nullable=True),
        sa.Column("content_bytes", sa.LargeBinary(), nullable=True),
        sa.Column(
            "is_entrypoint", sa.Boolean(), nullable=False, server_default="false"
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("streamlit_id", "path"),
        sa.ForeignKeyConstraint(
            ["streamlit_id"], ["streamlits.id"], ondelete="CASCADE"
        ),
    )
    op.create_index(
        "ix_streamlit_files_streamlit_id",
        "streamlit_files",
        ["streamlit_id"],
        unique=False,
    )

    # --- migrate existing code/requirements into streamlit_files ----------
    # Idempotent: skip streamlits that already have app.py / requirements.txt.
    conn.execute(
        sa.text(
            """
            INSERT INTO streamlit_files
                (streamlit_id, path, content_type, content_text, is_entrypoint)
            SELECT s.id, 'app.py', 'text/x-python', COALESCE(s.code, :default_code), true
            FROM streamlits s
            WHERE NOT EXISTS (
                SELECT 1 FROM streamlit_files sf
                WHERE sf.streamlit_id = s.id AND sf.path = 'app.py'
            )
            """
        ),
        {"default_code": DEFAULT_CODE},
    )
    conn.execute(
        sa.text(
            """
            INSERT INTO streamlit_files
                (streamlit_id, path, content_type, content_text, is_entrypoint)
            SELECT s.id, 'requirements.txt', 'text/plain', COALESCE(s.requirements, :default_requirements), false
            FROM streamlits s
            WHERE NOT EXISTS (
                SELECT 1 FROM streamlit_files sf
                WHERE sf.streamlit_id = s.id AND sf.path = 'requirements.txt'
            )
            """
        ),
        {"default_requirements": DEFAULT_REQUIREMENTS},
    )

    # --- restore any extra files archived by a previous downgrade ---------
    _restore_extra_files(conn)

    # --- restore version columns archived by a previous downgrade ---------
    _restore_archived_version_columns(conn)

    # --- drop server defaults; application layer supplies these values ------
    op.alter_column("streamlits", "version", server_default=None)
    op.alter_column("streamlits", "python_version", server_default=None)

    # --- remove code/requirements from streamlits -------------------------
    op.drop_column("streamlits", "code")
    op.drop_column("streamlits", "requirements")

    # --- create build_logs ------------------------------------------------
    op.create_table(
        "build_logs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("streamlit_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "ts",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("stage", sa.String(length=50), nullable=False),
        sa.Column("level", sa.String(length=20), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["streamlit_id"], ["streamlits.id"], ondelete="CASCADE"
        ),
    )
    op.create_index(
        "ix_build_logs_streamlit_id", "build_logs", ["streamlit_id"], unique=False
    )

    # --- create deployments -----------------------------------------------
    op.create_table(
        "deployments",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "ts",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("streamlit_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("result", sa.String(length=20), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["streamlit_id"], ["streamlits.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_deployments_streamlit_id", "deployments", ["streamlit_id"], unique=False
    )

    # --- backfill login/slug safely ---------------------------------------
    _resolve_login_backfill(conn)
    _resolve_slug_backfill(conn)

    # --- validate backfilled values ---------------------------------------
    _validate_identifiers(conn)

    # --- only now make login/slug NOT NULL and unique ---------------------
    op.alter_column("streamlits", "slug", nullable=False)
    op.alter_column("users", "login", nullable=False)

    old_constraint = _find_streamlit_user_name_constraint(conn)
    op.drop_constraint(old_constraint, "streamlits", type_="unique")

    op.create_unique_constraint(
        "uq_streamlits_owner_slug", "streamlits", ["user_id", "slug"]
    )
    op.create_unique_constraint(
        "uq_streamlits_owner_name", "streamlits", ["user_id", "name"]
    )
    op.create_unique_constraint("uq_users_login", "users", ["login"])


def downgrade() -> None:
    conn = op.get_bind()

    if _index_exists(conn, "deployments", "ix_deployments_streamlit_id"):
        op.drop_index("ix_deployments_streamlit_id", table_name="deployments")
    if _table_exists(conn, "deployments"):
        op.drop_table("deployments")

    if _index_exists(conn, "build_logs", "ix_build_logs_streamlit_id"):
        op.drop_index("ix_build_logs_streamlit_id", table_name="build_logs")
    if _table_exists(conn, "build_logs"):
        op.drop_table("build_logs")

    # --- restore code/requirements columns with original defaults ----------
    op.add_column(
        "streamlits",
        sa.Column(
            "code",
            sa.Text(),
            server_default=DEFAULT_CODE,
            nullable=True,
        ),
    )
    op.add_column(
        "streamlits",
        sa.Column(
            "requirements",
            sa.Text(),
            server_default=DEFAULT_REQUIREMENTS,
            nullable=True,
        ),
    )
    op.execute(
        """
        UPDATE streamlits s
        SET code = sf.content_text
        FROM streamlit_files sf
        WHERE sf.streamlit_id = s.id AND sf.path = 'app.py'
        """
    )
    op.execute(
        """
        UPDATE streamlits s
        SET requirements = sf.content_text
        FROM streamlit_files sf
        WHERE sf.streamlit_id = s.id AND sf.path = 'requirements.txt'
        """
    )
    # Critical: ensure every row has values before setting NOT NULL.
    # Rows that had no app.py / requirements.txt files get the original defaults.
    # Use two separate UPDATEs so a restored code is not clobbered when only
    # requirements is missing, and vice versa.
    conn.execute(
        sa.text("UPDATE streamlits SET code = :default_code WHERE code IS NULL"),
        {"default_code": DEFAULT_CODE},
    )
    conn.execute(
        sa.text(
            "UPDATE streamlits SET requirements = :default_requirements WHERE requirements IS NULL"
        ),
        {"default_requirements": DEFAULT_REQUIREMENTS},
    )
    # Original migration defined both columns as NOT NULL.
    op.alter_column("streamlits", "code", nullable=False)
    op.alter_column("streamlits", "requirements", nullable=False)

    # --- archive non-core files before dropping streamlit_files ------------
    _archive_extra_files(conn)

    # --- archive version columns before dropping them ----------------------
    _archive_version_columns(conn)

    if _index_exists(conn, "streamlit_files", "ix_streamlit_files_streamlit_id"):
        op.drop_index("ix_streamlit_files_streamlit_id", table_name="streamlit_files")
    if _table_exists(conn, "streamlit_files"):
        op.drop_table("streamlit_files")

    # --- restore original (user_id, name) unique constraint ----------------
    if _constraint_exists(conn, "streamlits", "uq_streamlits_owner_slug"):
        op.drop_constraint("uq_streamlits_owner_slug", "streamlits", type_="unique")
    if _constraint_exists(conn, "streamlits", "uq_streamlits_owner_name"):
        op.drop_constraint("uq_streamlits_owner_name", "streamlits", type_="unique")

    op.create_unique_constraint(
        "streamlits_user_id_name_key", "streamlits", ["user_id", "name"]
    )

    if _column_exists(conn, "streamlits", "image_tag"):
        op.drop_column("streamlits", "image_tag")
    if _column_exists(conn, "streamlits", "python_version"):
        op.drop_column("streamlits", "python_version")
    if _column_exists(conn, "streamlits", "version"):
        op.drop_column("streamlits", "version")
    if _column_exists(conn, "streamlits", "slug"):
        op.drop_column("streamlits", "slug")

    if _constraint_exists(conn, "users", "uq_users_login"):
        op.drop_constraint("uq_users_login", "users", type_="unique")
    if _column_exists(conn, "users", "login"):
        op.drop_column("users", "login")
