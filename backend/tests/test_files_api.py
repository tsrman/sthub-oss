"""Integration tests for the streamlit files API endpoints.

Tests use a real PostgreSQL database created on the existing test-container
postgres instance (port 5438).  Auth and the DB session are overridden via
FastAPI dependency overrides.
"""

from __future__ import annotations

import asyncio
import base64
import os
import subprocess
import sys
import uuid
from typing import Any
from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# Test database bootstrap (must happen before app imports)
# ---------------------------------------------------------------------------

_TEST_DB_HOST = "127.0.0.1"
_TEST_DB_PORT = 5438
_TEST_DB_USER = "streamlit"
_TEST_DB_PASSWORD = "streamlit"
_TEST_DB_NAME = "streamlit_test_files_api"
_TEST_ADMIN_DB_URL = f"postgresql+asyncpg://{_TEST_DB_USER}:{_TEST_DB_PASSWORD}@{_TEST_DB_HOST}:{_TEST_DB_PORT}/streamlit_registry"
TEST_DB_URL = f"postgresql+asyncpg://{_TEST_DB_USER}:{_TEST_DB_PASSWORD}@{_TEST_DB_HOST}:{_TEST_DB_PORT}/{_TEST_DB_NAME}"


def _to_asyncpg_url(url: str) -> str:
    return url.replace("postgresql+asyncpg", "postgresql")


async def _prepare_test_database() -> None:
    import asyncpg

    conn = await asyncpg.connect(_to_asyncpg_url(_TEST_ADMIN_DB_URL))
    try:
        await conn.execute(f"DROP DATABASE IF EXISTS {_TEST_DB_NAME} WITH (FORCE)")
        await conn.execute(f"CREATE DATABASE {_TEST_DB_NAME}")
    finally:
        await conn.close()


asyncio.run(_prepare_test_database())

os.environ["DATABASE_URL"] = TEST_DB_URL
os.environ["PUBLIC_HOST"] = ""

from app.config import Settings, get_settings  # noqa: E402

get_settings.cache_clear()

# ---------------------------------------------------------------------------
# Application imports (after env/database URL is configured)
# ---------------------------------------------------------------------------

from fastapi.testclient import TestClient  # noqa: E402

from app.dependencies import get_current_user_with_login  # noqa: E402
from app.db.session import get_db  # noqa: E402
from app.main import app  # noqa: E402

# ---------------------------------------------------------------------------
# Test constants and helpers
# ---------------------------------------------------------------------------

TEST_USER_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")
OTHER_USER_ID = uuid.UUID("33333333-3333-3333-3333-333333333333")
TEST_LOGIN = "test-user"
TEST_USERNAME = "Test User"


class SimpleUser:
    id = TEST_USER_ID
    login = TEST_LOGIN
    username = TEST_USERNAME
    keycloak_sub = "sub-test-files"
    email = "test@example.com"
    is_admin = False


class OtherUser:
    id = OTHER_USER_ID
    login = "other-user"
    username = "Other User"
    is_admin = False
    keycloak_sub = "sub-other-files"
    email = "other@example.com"


async def override_get_db():
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

    engine = create_async_engine(TEST_DB_URL, echo=False)
    AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)
    async with AsyncSessionLocal() as session:
        yield session
    await engine.dispose()


def override_auth() -> tuple[uuid.UUID, str, SimpleUser]:
    return (TEST_USER_ID, TEST_LOGIN, SimpleUser())


async def _run_db_query(sql: str, *args: Any) -> None:
    import asyncpg

    conn = await asyncpg.connect(_to_asyncpg_url(TEST_DB_URL))
    try:
        await conn.execute(sql, *args)
    finally:
        await conn.close()


async def _insert_test_user(user: Any) -> None:
    await _run_db_query(
        "INSERT INTO users (id, keycloak_sub, login, username, email, is_admin) VALUES ($1, $2, $3, $4, $5, $6)",
        user.id,
        user.keycloak_sub,
        user.login,
        user.username,
        user.email,
        getattr(user, "is_admin", False),
    )


async def _run_migrations() -> None:
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        env={**os.environ, "DATABASE_URL": TEST_DB_URL},
        check=True,
    )


def _create_app(client: TestClient, **overrides: Any) -> dict[str, Any]:
    suffix = uuid.uuid4().hex[:8]
    slug = overrides.get("slug", f"app-{suffix}")
    body = {
        "name": overrides.get("name", f"App {suffix}"),
        "slug": slug,
        "description": "test app",
        "python_version": "3.11",
        "cpu_limit": 1.0,
        "memory_limit_mb": 512,
    }
    body.update(overrides)
    response = client.post("/api/v1/streamlits", json=body)
    assert response.status_code == 201, response.text
    return response.json()


@pytest.fixture(scope="module")
def client():
    import app.main as main_module

    async def noop_migrations():
        pass

    original_run_migrations = main_module.run_migrations
    main_module.run_migrations = noop_migrations

    app.dependency_overrides[get_current_user_with_login] = override_auth
    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as test_client:
        asyncio.run(_run_migrations())
        asyncio.run(_insert_test_user(SimpleUser()))
        asyncio.run(_insert_test_user(OtherUser()))
        yield test_client

    app.dependency_overrides.clear()
    main_module.run_migrations = original_run_migrations


@pytest.fixture(scope="session", autouse=True)
def _cleanup_test_database():
    yield
    asyncio.run(_prepare_test_database())


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_list_files(client: TestClient) -> None:
    created = _create_app(client, slug="list-files", name="List Files")
    response = client.get(f"/api/v1/streamlits/{created['id']}/files")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2
    paths = {item["path"] for item in data["items"]}
    assert paths == {"app.py", "requirements.txt"}
    for item in data["items"]:
        assert "id" in item
        assert "content_type" in item
        assert "is_entrypoint" in item
        assert "updated_at" in item


def test_get_text_file(client: TestClient) -> None:
    created = _create_app(client, slug="get-text", name="Get Text")
    response = client.get(f"/api/v1/streamlits/{created['id']}/files/app.py")
    assert response.status_code == 200
    data = response.json()
    assert data["path"] == "app.py"
    assert data["content_type"] == "text/x-python"
    assert data["is_entrypoint"] is True
    assert "content" in data


def test_get_nested_text_file(client: TestClient) -> None:
    created = _create_app(client, slug="get-nested", name="Get Nested")
    response = client.put(
        f"/api/v1/streamlits/{created['id']}/files/.streamlit/config.toml",
        json={"content": "[server]\nport = 8501", "content_type": "application/toml"},
    )
    assert response.status_code == 200, response.text

    response = client.get(
        f"/api/v1/streamlits/{created['id']}/files/.streamlit/config.toml"
    )
    assert response.status_code == 200
    data = response.json()
    assert data["path"] == ".streamlit/config.toml"
    assert "[server]" in data["content"]


def test_put_text_file(client: TestClient) -> None:
    created = _create_app(client, slug="put-text", name="Put Text")
    response = client.put(
        f"/api/v1/streamlits/{created['id']}/files/utils.py",
        json={"content": "def helper():\n    pass", "content_type": "text/x-python"},
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["path"] == "utils.py"
    assert data["content"] == "def helper():\n    pass"
    assert data["is_entrypoint"] is False


def test_put_binary_file(client: TestClient) -> None:
    created = _create_app(client, slug="put-binary", name="Put Binary")
    raw = b"\x89PNG\r\n\x1a\nhello"
    encoded = base64.b64encode(raw).decode("ascii")
    response = client.put(
        f"/api/v1/streamlits/{created['id']}/files/image.png",
        json={"content": encoded, "content_type": "image/png"},
    )
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "image/png"
    assert response.content == raw


def test_get_binary_file(client: TestClient) -> None:
    created = _create_app(client, slug="get-binary", name="Get Binary")
    raw = b"\x89PNG\r\n\x1a\nworld"
    encoded = base64.b64encode(raw).decode("ascii")
    put_response = client.put(
        f"/api/v1/streamlits/{created['id']}/files/logo.png",
        json={"content": encoded, "content_type": "image/png"},
    )
    assert put_response.status_code == 200

    response = client.get(f"/api/v1/streamlits/{created['id']}/files/logo.png")
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert response.content == raw


def test_get_binary_file_as_base64(client: TestClient) -> None:
    created = _create_app(client, slug="get-binary-b64", name="Get Binary B64")
    raw = b"\x89PNG\r\n\x1a\nworld"
    encoded = base64.b64encode(raw).decode("ascii")
    put_response = client.put(
        f"/api/v1/streamlits/{created['id']}/files/logo.png",
        json={"content": encoded, "content_type": "image/png"},
    )
    assert put_response.status_code == 200

    # Regression: the base64 query flag used to shadow the ``base64`` module
    # inside the handler, producing a 500 on this exact request.
    response = client.get(
        f"/api/v1/streamlits/{created['id']}/files/logo.png?base64=true"
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["content"] == encoded
    assert data["content_type"] == "image/png"


def test_patch_text_file(client: TestClient) -> None:
    created = _create_app(client, slug="patch-text", name="Patch Text")
    response = client.patch(
        f"/api/v1/streamlits/{created['id']}/files/app.py",
        json={"content": "import streamlit as st\n\nst.title('Updated')"},
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["path"] == "app.py"
    assert "Updated" in data["content"]


def test_delete_file(client: TestClient) -> None:
    created = _create_app(client, slug="delete-file", name="Delete File")
    response = client.put(
        f"/api/v1/streamlits/{created['id']}/files/temp.py",
        json={"content": "x = 1"},
    )
    assert response.status_code == 200

    response = client.delete(f"/api/v1/streamlits/{created['id']}/files/temp.py")
    assert response.status_code == 204
    assert response.content == b""

    response = client.get(f"/api/v1/streamlits/{created['id']}/files/temp.py")
    assert response.status_code == 404


def test_delete_required_file_rejected(client: TestClient) -> None:
    created = _create_app(client, slug="delete-required", name="Delete Required")
    for path in ("app.py", "requirements.txt"):
        response = client.delete(f"/api/v1/streamlits/{created['id']}/files/{path}")
        assert response.status_code == 400, path
        assert response.json()["error"]["code"] == "validation_error", path


def test_get_file_not_found(client: TestClient) -> None:
    created = _create_app(client, slug="get-missing", name="Get Missing")
    response = client.get(f"/api/v1/streamlits/{created['id']}/files/missing.py")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_delete_file_not_found(client: TestClient) -> None:
    created = _create_app(client, slug="delete-missing", name="Delete Missing")
    response = client.delete(f"/api/v1/streamlits/{created['id']}/files/missing.py")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_app_not_found(client: TestClient) -> None:
    fake_id = uuid.uuid4()
    response = client.get(f"/api/v1/streamlits/{fake_id}/files")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_app_belongs_to_user(client: TestClient) -> None:
    """A user cannot access files of another user's app."""
    created = _create_app(client, slug="owner-only", name="Owner Only")

    def other_auth() -> tuple[uuid.UUID, str, OtherUser]:
        return (OTHER_USER_ID, OtherUser.login, OtherUser())

    app.dependency_overrides[get_current_user_with_login] = other_auth
    try:
        response = client.get(f"/api/v1/streamlits/{created['id']}/files")
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "not_found"
    finally:
        app.dependency_overrides[get_current_user_with_login] = override_auth


def test_path_validation(client: TestClient) -> None:
    created = _create_app(client, slug="bad-path", name="Bad Path")
    # URL-path traversal is normalized before routing; test an invalid extension.
    response = client.put(
        f"/api/v1/streamlits/{created['id']}/files/bad.exe",
        json={"content": "x = 1"},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "validation_error"


def test_size_limit(client: TestClient) -> None:
    created = _create_app(client, slug="size-limit", name="Size Limit")
    limited_settings = Settings(MAX_FILE_SIZE_BYTES=10)

    with patch(
        "app.services.file_service.get_settings",
        return_value=limited_settings,
    ):
        response = client.put(
            f"/api/v1/streamlits/{created['id']}/files/big.py",
            json={"content": "x" * 11},
        )
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "file_too_large"


def test_file_count_limit(client: TestClient) -> None:
    created = _create_app(client, slug="count-limit", name="Count Limit")
    # Default files are app.py and requirements.txt; allow two more files.
    limited_settings = Settings(MAX_FILES_PER_STREAMLIT=4)

    with patch(
        "app.services.file_service.get_settings",
        return_value=limited_settings,
    ):
        response = client.put(
            f"/api/v1/streamlits/{created['id']}/files/one.py",
            json={"content": "x = 1"},
        )
        assert response.status_code == 200

        response = client.put(
            f"/api/v1/streamlits/{created['id']}/files/two.py",
            json={"content": "x = 2"},
        )
        assert response.status_code == 200

        response = client.put(
            f"/api/v1/streamlits/{created['id']}/files/three.py",
            json={"content": "x = 3"},
        )
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "file_limit_exceeded"


def test_put_invalid_content_type(client: TestClient) -> None:
    created = _create_app(client, slug="bad-ctype", name="Bad Content Type")
    response = client.put(
        f"/api/v1/streamlits/{created['id']}/files/app.py",
        json={"content": "x = 1", "content_type": "not-a-mime-type"},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_put_binary_with_invalid_base64(client: TestClient) -> None:
    created = _create_app(client, slug="bad-b64", name="Bad Base64")
    response = client.put(
        f"/api/v1/streamlits/{created['id']}/files/image.png",
        json={"content": "not-valid-base64!", "content_type": "image/png"},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "validation_error"
