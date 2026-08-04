"""Integration tests for the streamlits API endpoints.

Tests use a real PostgreSQL database created on the existing test-container
postgres instance (port 5438).  Auth, the worker client and the DB session are
overridden via FastAPI dependency overrides.
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import uuid
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

# ---------------------------------------------------------------------------
# Test database bootstrap (must happen before app imports)
# ---------------------------------------------------------------------------

_TEST_DB_HOST = "127.0.0.1"
_TEST_DB_PORT = 5438
_TEST_DB_USER = "streamlit"
_TEST_DB_PASSWORD = "streamlit"
_TEST_DB_NAME = "streamlit_test_api"
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

# Make sure a previously cached Settings object does not override the env values
# we just set before the application builds its engine/alembic URL.
from app.config import get_settings  # noqa: E402

get_settings.cache_clear()

# ---------------------------------------------------------------------------
# Application imports (after env/database URL is configured)
# ---------------------------------------------------------------------------

from fastapi.testclient import TestClient  # noqa: E402

from app.dependencies import (  # noqa: E402
    get_current_user_with_login,
    get_current_user_with_login_for_sse,
)
from app.db.session import get_db  # noqa: E402
from app.exceptions import QuotaExceededError  # noqa: E402
from app.main import app  # noqa: E402
import app.api.streamlits as streamlits_module  # noqa: E402

# ---------------------------------------------------------------------------
# Test constants and helpers
# ---------------------------------------------------------------------------

TEST_USER_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
TEST_LOGIN = "test-user"
TEST_USERNAME = "Test User"


class SimpleUser:
    id = TEST_USER_ID
    login = TEST_LOGIN
    username = TEST_USERNAME
    keycloak_sub = "sub-test"
    email = "test@example.com"
    is_admin = False


class FakeWorkerClient:
    calls: list[tuple[Any, ...]] = []
    should_fail: bool = False

    @classmethod
    def reset(cls) -> None:
        cls.calls = []
        cls.should_fail = False

    async def enqueue_build_run(self, streamlit_id: uuid.UUID) -> str:
        if self.should_fail:
            raise RuntimeError("enqueue failure")
        sid = str(streamlit_id)
        self.calls.append(("build_run", sid))
        return sid

    async def enqueue_stop(self, streamlit_id: uuid.UUID) -> str:
        if self.should_fail:
            raise RuntimeError("enqueue failure")
        sid = str(streamlit_id)
        self.calls.append(("stop", sid))
        return sid

    async def enqueue_remove(
        self,
        streamlit_id: uuid.UUID,
        container_id: str | None,
        image_tag: str | None,
    ) -> str:
        if self.should_fail:
            raise RuntimeError("enqueue failure")
        sid = str(streamlit_id)
        self.calls.append(("remove", sid, container_id, image_tag))
        return sid


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


async def _insert_test_user() -> None:
    await _run_db_query(
        "INSERT INTO users (id, keycloak_sub, login, username, email, is_admin) VALUES ($1, $2, $3, $4, $5, $6)",
        TEST_USER_ID,
        SimpleUser.keycloak_sub,
        TEST_LOGIN,
        TEST_USERNAME,
        SimpleUser.email,
        False,
    )


async def _set_app_status(
    app_id: str,
    *,
    status: str,
    container_id: str | None = None,
    image_tag: str | None = None,
) -> None:
    await _run_db_query(
        "UPDATE streamlits SET status=$1, container_id=$2, image_tag=$3 WHERE id=$4",
        status,
        container_id,
        image_tag,
        uuid.UUID(app_id),
    )


async def _count_streamlit_files(app_id: str) -> int:
    import asyncpg

    conn = await asyncpg.connect(_to_asyncpg_url(TEST_DB_URL))
    try:
        return await conn.fetchval(
            "SELECT COUNT(*) FROM streamlit_files WHERE streamlit_id=$1",
            uuid.UUID(app_id),
        )
    finally:
        await conn.close()


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


async def _run_migrations() -> None:
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        env={**os.environ, "DATABASE_URL": TEST_DB_URL},
        check=True,
    )


@pytest.fixture(scope="module")
def client():
    # Disable the automatic migration run inside the app lifespan; we run
    # migrations ourselves so the subprocess uses the test DB URL reliably.
    import app.main as main_module

    async def noop_migrations():
        pass

    original_run_migrations = main_module.run_migrations
    main_module.run_migrations = noop_migrations

    original_worker = streamlits_module.WorkerClient
    streamlits_module.WorkerClient = FakeWorkerClient

    app.dependency_overrides[get_current_user_with_login] = override_auth
    app.dependency_overrides[get_current_user_with_login_for_sse] = override_auth
    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as test_client:
        asyncio.run(_run_migrations())
        asyncio.run(_insert_test_user())
        FakeWorkerClient.reset()
        yield test_client

    app.dependency_overrides.clear()
    streamlits_module.WorkerClient = original_worker
    main_module.run_migrations = original_run_migrations


@pytest.fixture(autouse=True)
def _reset_worker_calls():
    FakeWorkerClient.reset()
    yield


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_create_streamlit(client: TestClient) -> None:
    response = client.post(
        "/api/v1/streamlits",
        json={
            "name": "Create Test",
            "slug": "create-test",
            "description": "hello",
            "python_version": "3.11",
            "cpu_limit": 1.0,
            "memory_limit_mb": 512,
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Create Test"
    assert data["slug"] == "create-test"
    assert data["status"] == "stopped"
    assert data["version"] == 0
    assert data["url"] == "/st/test-user/create-test"
    assert data["owner"]["login"] == TEST_LOGIN
    assert data["owner"]["display_name"] == TEST_USERNAME


def test_create_streamlit_slug_taken(client: TestClient) -> None:
    _create_app(client, slug="taken-slug", name="Taken One")
    response = client.post(
        "/api/v1/streamlits",
        json={
            "name": "Taken Two",
            "slug": "taken-slug",
            "python_version": "3.11",
            "cpu_limit": 1.0,
            "memory_limit_mb": 512,
        },
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "slug_taken"


def test_create_streamlit_duplicate_name_allowed(client: TestClient) -> None:
    first = _create_app(client, slug="name-slug-1", name="Same Name")
    response = client.post(
        "/api/v1/streamlits",
        json={
            "name": "Same Name",
            "slug": "name-slug-2",
            "python_version": "3.11",
            "cpu_limit": 1.0,
            "memory_limit_mb": 512,
        },
    )
    assert response.status_code == 201
    second = response.json()
    assert second["name"] == "Same Name"
    assert second["slug"] == "name-slug-2"
    assert second["id"] != first["id"]


def test_get_streamlit(client: TestClient) -> None:
    created = _create_app(client, slug="get-slug", name="Get Me")
    response = client.get(f"/api/v1/streamlits/{created['id']}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == created["id"]
    assert data["slug"] == "get-slug"


def test_get_streamlit_not_found(client: TestClient) -> None:
    response = client.get(f"/api/v1/streamlits/{uuid.uuid4()}")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_list_streamlits(client: TestClient) -> None:
    _create_app(client, slug="list-1", name="List One")
    created2 = _create_app(client, slug="list-2", name="List Two")
    asyncio.run(_set_app_status(created2["id"], status="running", container_id="c1"))

    response = client.get("/api/v1/streamlits")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 2
    assert data["running"] >= 1
    ids = {item["id"] for item in data["items"]}
    assert created2["id"] in ids

    # status filter
    response = client.get("/api/v1/streamlits?status=running")
    assert response.status_code == 200
    data = response.json()
    assert all(item["status"] == "running" for item in data["items"])

    # search filter
    response = client.get("/api/v1/streamlits?q=list-2")
    assert response.status_code == 200
    data = response.json()
    assert any(item["slug"] == "list-2" for item in data["items"])


def test_update_streamlit(client: TestClient) -> None:
    created = _create_app(client, slug="update-slug", name="Update Me")
    response = client.patch(
        f"/api/v1/streamlits/{created['id']}",
        json={"name": "Updated Name", "memory_limit_mb": 1024},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Updated Name"
    assert data["memory_limit_mb"] == 1024
    assert data["slug"] == "update-slug"


def test_update_streamlit_slug_taken(client: TestClient) -> None:
    first = _create_app(client, slug="slug-first", name="First")
    second = _create_app(client, slug="slug-second", name="Second")
    response = client.patch(
        f"/api/v1/streamlits/{second['id']}",
        json={"slug": first["slug"]},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "slug_taken"


def test_update_streamlit_slug_while_building(client: TestClient) -> None:
    created = _create_app(client, slug="building-slug", name="Building")
    asyncio.run(_set_app_status(created["id"], status="building"))
    response = client.patch(
        f"/api/v1/streamlits/{created['id']}",
        json={"slug": "building-slug-new"},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "invalid_state"


def test_update_streamlit_restarts_when_running(client: TestClient) -> None:
    created = _create_app(client, slug="running-slug", name="Running")
    asyncio.run(
        _set_app_status(
            created["id"],
            status="running",
            container_id="container-123",
            image_tag="img:v1",
        )
    )

    response = client.patch(
        f"/api/v1/streamlits/{created['id']}",
        json={"memory_limit_mb": 2048},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "building"
    assert data["memory_limit_mb"] == 2048
    assert ("build_run", created["id"]) in FakeWorkerClient.calls


def test_delete_streamlit(client: TestClient) -> None:
    created = _create_app(client, slug="delete-slug", name="Delete Me")
    response = client.delete(f"/api/v1/streamlits/{created['id']}")
    assert response.status_code == 204
    assert response.content == b""

    assert ("remove", created["id"], None, None) in FakeWorkerClient.calls

    response = client.get(f"/api/v1/streamlits/{created['id']}")
    assert response.status_code == 404


def test_run_streamlit(client: TestClient) -> None:
    created = _create_app(client, slug="run-slug", name="Run Me")
    response = client.post(f"/api/v1/streamlits/{created['id']}/run")
    assert response.status_code == 202
    data = response.json()
    assert data["status"] == "building"
    assert data["version"] == 1
    assert ("build_run", created["id"]) in FakeWorkerClient.calls

    # Verify DB status
    detail = client.get(f"/api/v1/streamlits/{created['id']}")
    assert detail.json()["status"] == "building"
    assert detail.json()["version"] == 1


def test_run_streamlit_already_running(client: TestClient) -> None:
    created = _create_app(client, slug="already-run-slug", name="Already Running")
    asyncio.run(
        _set_app_status(
            created["id"],
            status="running",
            container_id="container-running",
        )
    )
    response = client.post(f"/api/v1/streamlits/{created['id']}/run")
    assert response.status_code == 202
    data = response.json()
    assert data["status"] == "running"
    assert data["version"] == 0
    assert FakeWorkerClient.calls == []


def test_stop_streamlit(client: TestClient) -> None:
    created = _create_app(client, slug="stop-slug", name="Stop Me")
    asyncio.run(_set_app_status(created["id"], status="running", container_id="c-stop"))

    response = client.post(f"/api/v1/streamlits/{created['id']}/stop")
    assert response.status_code == 202
    data = response.json()
    assert data["status"] == "stopped"
    assert ("stop", created["id"]) in FakeWorkerClient.calls

    detail = client.get(f"/api/v1/streamlits/{created['id']}")
    assert detail.json()["status"] == "stopped"


def test_stop_streamlit_already_stopped(client: TestClient) -> None:
    created = _create_app(client, slug="already-stop-slug", name="Already Stopped")
    response = client.post(f"/api/v1/streamlits/{created['id']}/stop")
    assert response.status_code == 202
    data = response.json()
    assert data["status"] == "stopped"
    assert FakeWorkerClient.calls == []


def test_update_streamlit_description_only_no_restart(client: TestClient) -> None:
    created = _create_app(client, slug="desc-only-slug", name="Desc Only")
    asyncio.run(
        _set_app_status(
            created["id"],
            status="running",
            container_id="container-123",
            image_tag="img:v1",
        )
    )

    response = client.patch(
        f"/api/v1/streamlits/{created['id']}",
        json={"name": "New Name", "description": "New description"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "New Name"
    assert data["description"] == "New description"
    assert data["status"] == "running"
    assert data["version"] == 0
    assert FakeWorkerClient.calls == []


def test_run_streamlit_enqueue_failure_rolls_back(client: TestClient) -> None:
    created = _create_app(client, slug="run-fail-slug", name="Run Fail")
    FakeWorkerClient.should_fail = True

    response = client.post(f"/api/v1/streamlits/{created['id']}/run")
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "internal_error"

    detail = client.get(f"/api/v1/streamlits/{created['id']}")
    assert detail.json()["status"] == "stopped"
    assert detail.json()["version"] == 0


def test_stop_streamlit_enqueue_failure_rolls_back(client: TestClient) -> None:
    created = _create_app(client, slug="stop-fail-slug", name="Stop Fail")
    asyncio.run(_set_app_status(created["id"], status="running", container_id="c1"))
    FakeWorkerClient.should_fail = True

    response = client.post(f"/api/v1/streamlits/{created['id']}/stop")
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "internal_error"

    detail = client.get(f"/api/v1/streamlits/{created['id']}")
    assert detail.json()["status"] == "running"


def test_update_streamlit_enqueue_failure_rolls_back(client: TestClient) -> None:
    created = _create_app(client, slug="update-fail-slug", name="Update Fail")
    asyncio.run(
        _set_app_status(
            created["id"],
            status="running",
            container_id="container-123",
            image_tag="img:v1",
        )
    )
    FakeWorkerClient.should_fail = True

    response = client.patch(
        f"/api/v1/streamlits/{created['id']}",
        json={"memory_limit_mb": 2048},
    )
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "internal_error"

    detail = client.get(f"/api/v1/streamlits/{created['id']}")
    data = detail.json()
    assert data["status"] == "running"
    assert data["version"] == 0
    assert data["memory_limit_mb"] == 512


def test_delete_streamlit_enqueue_failure_preserves_record(client: TestClient) -> None:
    created = _create_app(client, slug="delete-fail-slug", name="Delete Fail")
    FakeWorkerClient.should_fail = True

    response = client.delete(f"/api/v1/streamlits/{created['id']}")
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "internal_error"

    detail = client.get(f"/api/v1/streamlits/{created['id']}")
    assert detail.status_code == 200


def test_delete_streamlit_enqueue_failure_records_no_history(
    client: TestClient,
) -> None:
    """A failed delete must not leave a bogus "delete completed" history entry."""
    created = _create_app(client, slug="delete-fail-hist", name="Delete Fail Hist")
    FakeWorkerClient.should_fail = True

    response = client.delete(f"/api/v1/streamlits/{created['id']}")
    assert response.status_code == 500

    deployments = client.get(f"/api/v1/streamlits/{created['id']}/deployments")
    assert deployments.status_code == 200
    assert deployments.json()["items"] == []


def test_delete_records_deployment_after_enqueue(client: TestClient) -> None:
    """History is written only after the remove task was successfully enqueued."""
    app = _create_app(client, slug="delete-order", name="Delete Order")
    recorded: list[tuple[str, str]] = []

    original_record = streamlits_module.DeploymentService.record

    async def spy_record(self, db, streamlit_id, actor_id, kind, version, result):
        # The worker enqueue must already have happened when history is written.
        assert ("remove", str(streamlit_id), None, None) in FakeWorkerClient.calls
        recorded.append((kind, result))
        return await original_record(
            self, db, streamlit_id, actor_id, kind, version, result
        )

    with patch.object(streamlits_module.DeploymentService, "record", spy_record):
        response = client.delete(f"/api/v1/streamlits/{app['id']}")

    assert response.status_code == 204
    assert ("remove", app["id"], None, None) in FakeWorkerClient.calls
    assert recorded == [("delete", "completed")]

    # The app itself is gone.
    assert client.get(f"/api/v1/streamlits/{app['id']}").status_code == 404


def test_list_streamlits_invalid_status(client: TestClient) -> None:
    response = client.get("/api/v1/streamlits?status=invalid")
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "validation_error"


def test_check_slug_invalid_exclude_id(client: TestClient) -> None:
    response = client.get(
        "/api/v1/streamlits/check-slug?slug=available-slug&exclude_id=not-a-uuid"
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "validation_error"


def test_check_slug_available(client: TestClient) -> None:
    response = client.get("/api/v1/streamlits/check-slug?slug=available-slug")
    assert response.status_code == 200
    data = response.json()
    assert data["available"] is True
    assert data["normalized"] == "available-slug"
    assert data["url"] == "/st/test-user/available-slug"


def test_check_slug_taken(client: TestClient) -> None:
    _create_app(client, slug="taken-check-slug", name="Taken Check")
    response = client.get("/api/v1/streamlits/check-slug?slug=taken-check-slug")
    assert response.status_code == 200
    data = response.json()
    assert data["available"] is False


def test_check_slug_invalid(client: TestClient) -> None:
    response = client.get("/api/v1/streamlits/check-slug?slug=-bad-")
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "validation_error"


def test_run_streamlit_quota_exceeded(client: TestClient) -> None:
    created = _create_app(client, slug="quota-slug", name="Quota")

    class RaisingQuotaService:
        def __init__(self, *args, **kwargs):
            pass

        async def check_running_quota(self, db, user_id):
            raise QuotaExceededError(
                message="Quota exceeded",
                limit=1,
                current=1,
            )

    with patch.object(streamlits_module, "QuotaService", RaisingQuotaService):
        response = client.post(f"/api/v1/streamlits/{created['id']}/run")

    assert response.status_code == 409
    error = response.json()["error"]
    assert error["code"] == "quota_exceeded"
    assert error["details"] == {"limit": 1, "current": 1}
    # App should remain untouched.
    detail = client.get(f"/api/v1/streamlits/{created['id']}")
    assert detail.json()["status"] == "stopped"


def test_update_runtime_field_while_building_rejected(client: TestClient) -> None:
    created = _create_app(client, slug="build-runtime-slug", name="Build Runtime")
    asyncio.run(_set_app_status(created["id"], status="building"))

    runtime_fields = {
        "cpu_limit": 2.0,
        "memory_limit_mb": 1024,
        "python_version": "3.12",
        "slug": "build-runtime-new",
    }
    for field, value in runtime_fields.items():
        response = client.patch(
            f"/api/v1/streamlits/{created['id']}",
            json={field: value},
        )
        assert response.status_code == 409, field
        assert response.json()["error"]["code"] == "invalid_state", field

    # Non-runtime updates are still allowed while building.
    response = client.patch(
        f"/api/v1/streamlits/{created['id']}",
        json={"description": "updated while building"},
    )
    assert response.status_code == 200
    assert response.json()["description"] == "updated while building"


def test_restart_streamlit(client: TestClient) -> None:
    created = _create_app(client, slug="restart-slug", name="Restart Me")
    asyncio.run(
        _set_app_status(
            created["id"],
            status="running",
            container_id="c-restart",
            image_tag="img:v1",
        )
    )

    response = client.post(f"/api/v1/streamlits/{created['id']}/restart")
    assert response.status_code == 202
    data = response.json()
    assert data["status"] == "building"
    assert data["version"] == 1
    assert data["id"] == created["id"]
    assert ("build_run", created["id"]) in FakeWorkerClient.calls

    detail = client.get(f"/api/v1/streamlits/{created['id']}")
    assert detail.json()["status"] == "building"
    assert detail.json()["version"] == 1


def test_restart_streamlit_while_building(client: TestClient) -> None:
    created = _create_app(client, slug="restart-build-slug", name="Restart Building")
    asyncio.run(_set_app_status(created["id"], status="building"))

    response = client.post(f"/api/v1/streamlits/{created['id']}/restart")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "invalid_state"


def test_duplicate_streamlit(client: TestClient) -> None:
    original = _create_app(client, slug="dup-slug", name="Dup App")

    response = client.post(f"/api/v1/streamlits/{original['id']}/duplicate")
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Dup App (copy)"
    assert data["slug"] == "dup-slug-copy"
    assert data["status"] == "stopped"
    assert data["version"] == 0
    assert data["description"] == original["description"]
    assert data["python_version"] == original["python_version"]
    assert data["cpu_limit"] == original["cpu_limit"]
    assert data["memory_limit_mb"] == original["memory_limit_mb"]
    assert data["id"] != original["id"]


def test_duplicate_streamlit_slug_collision(client: TestClient) -> None:
    original = _create_app(client, slug="dup-collide", name="Original")
    _create_app(client, slug="dup-collide-copy", name="Copy One")

    response = client.post(f"/api/v1/streamlits/{original['id']}/duplicate")
    assert response.status_code == 201
    assert response.json()["slug"] == "dup-collide-copy-1"


def test_duplicate_streamlit_copies_files(client: TestClient) -> None:
    original = _create_app(client, slug="dup-files", name="Original Files")
    original_count = asyncio.run(_count_streamlit_files(original["id"]))
    assert original_count == 2  # app.py + requirements.txt

    duplicated = client.post(f"/api/v1/streamlits/{original['id']}/duplicate").json()
    new_count = asyncio.run(_count_streamlit_files(duplicated["id"]))
    assert new_count == original_count


def test_list_streamlits_q_wildcard_escaped(client: TestClient) -> None:
    _create_app(client, slug="wild-app", name="Wildcard App")

    for wildcard in ("_", "%"):
        response = client.get(f"/api/v1/streamlits?q={wildcard}")
        assert response.status_code == 200, wildcard
        assert response.json()["items"] == [], wildcard


async def _insert_build_logs(streamlit_id: str, messages: list[str]) -> None:
    import asyncpg

    conn = await asyncpg.connect(_to_asyncpg_url(TEST_DB_URL))
    try:
        for idx, msg in enumerate(messages):
            await conn.execute(
                "INSERT INTO build_logs (streamlit_id, stage, level, message) "
                "VALUES ($1, $2, $3, $4)",
                uuid.UUID(streamlit_id),
                "build",
                "info" if idx == 0 else "error",
                msg,
            )
    finally:
        await conn.close()


def test_stream_build_logs(client: TestClient) -> None:
    app = _create_app(client, slug="log-stream", name="Log Stream")
    messages = ["build started", "build failed"]
    asyncio.run(_insert_build_logs(app["id"], messages))

    response = client.get(
        f"/api/v1/streamlits/{app['id']}/logs?follow=false",
        headers={"Accept": "text/event-stream"},
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")

    lines = response.text.strip().split("\n\n")
    data_lines = [line for line in lines if line.startswith("data:")]
    assert len(data_lines) >= 2
    parsed = [json.loads(line[len("data: ") :]) for line in data_lines]
    assert [p["msg"] for p in parsed[:2]] == messages


def test_run_records_deployment(client: TestClient) -> None:
    app = _create_app(client, slug="deploy-run", name="Deploy Run")
    with patch.object(
        streamlits_module.QuotaService, "check_running_quota", return_value=None
    ):
        response = client.post(f"/api/v1/streamlits/{app['id']}/run")
    assert response.status_code == 202

    response = client.get(f"/api/v1/streamlits/{app['id']}/deployments")
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 1
    assert data["items"][0]["kind"] == "run"
    assert data["items"][0]["result"] == "started"
    assert data["items"][0]["actor"]["login"] == TEST_LOGIN


def test_stop_records_deployment(client: TestClient) -> None:
    app = _create_app(client, slug="deploy-stop", name="Deploy Stop")
    asyncio.run(
        _set_app_status(
            app["id"], status="running", container_id="c123", image_tag="tag"
        )
    )

    response = client.post(f"/api/v1/streamlits/{app['id']}/stop")
    assert response.status_code == 202

    response = client.get(f"/api/v1/streamlits/{app['id']}/deployments")
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 1
    assert data["items"][0]["kind"] == "stop"
    assert data["items"][0]["result"] == "completed"


def test_delete_records_deployment(client: TestClient) -> None:
    app = _create_app(client, slug="deploy-delete", name="Deploy Delete")

    response = client.delete(f"/api/v1/streamlits/{app['id']}")
    assert response.status_code == 204

    response = client.get(f"/api/v1/streamlits/{app['id']}/deployments")
    assert response.status_code == 404


def test_global_deployments_includes_name_and_slug(client: TestClient) -> None:
    app = _create_app(client, slug="deploy-global", name="Deploy Global")
    with patch.object(
        streamlits_module.QuotaService, "check_running_quota", return_value=None
    ):
        run = client.post(f"/api/v1/streamlits/{app['id']}/run")
    assert run.status_code == 202

    response = client.get("/api/v1/deployments")
    assert response.status_code == 200
    data = response.json()
    item = next(it for it in data["items"] if it["streamlit_slug"] == "deploy-global")
    assert item["streamlit_name"] == "Deploy Global"
    assert item["kind"] == "run"
    assert item["actor"]["login"] == TEST_LOGIN


def test_global_deployments_empty_for_new_user(client: TestClient) -> None:
    response = client.get("/api/v1/deployments")
    assert response.status_code == 200
    assert "items" in response.json()


def test_lint_streamlit_ok(client: TestClient) -> None:
    created = _create_app(client, slug="lint-ok", name="Lint OK")

    with patch.object(
        streamlits_module.LintService, "check_syntax", new=AsyncMock(return_value=[])
    ):
        response = client.post(
            f"/api/v1/streamlits/{created['id']}/lint",
            json={"code": "import streamlit as st\nst.write('ok')"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["problems"] == []


def test_lint_streamlit_with_problems(client: TestClient) -> None:
    created = _create_app(client, slug="lint-problems", name="Lint Problems")
    problems = [
        {
            "line": 1,
            "column": 1,
            "severity": "error",
            "message": "unused import",
            "code": "F401",
        }
    ]

    with patch.object(
        streamlits_module.LintService,
        "check_syntax",
        new=AsyncMock(return_value=problems),
    ):
        response = client.post(
            f"/api/v1/streamlits/{created['id']}/lint",
            json={"code": "import os\n"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is False
    assert len(data["problems"]) == 1
    assert data["problems"][0]["message"] == "unused import"


def test_lint_streamlit_not_found(client: TestClient) -> None:
    response = client.post(
        f"/api/v1/streamlits/{uuid.uuid4()}/lint",
        json={"code": "x = 1"},
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_lint_streamlit_belongs_to_user(client: TestClient) -> None:
    """A user cannot lint code against another user's app."""
    created = _create_app(client, slug="lint-owner", name="Lint Owner")

    class OtherUser:
        id = uuid.UUID("44444444-4444-4444-4444-444444444444")
        login = "other-user"
        username = "Other User"
        keycloak_sub = "sub-other-lint"
        email = "other@example.com"
        is_admin = False

    def other_auth() -> tuple[uuid.UUID, str, OtherUser]:
        return (OtherUser.id, OtherUser.login, OtherUser())

    app.dependency_overrides[get_current_user_with_login] = other_auth
    try:
        response = client.post(
            f"/api/v1/streamlits/{created['id']}/lint",
            json={"code": "x = 1"},
        )
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "not_found"
    finally:
        app.dependency_overrides[get_current_user_with_login] = override_auth


@pytest.fixture(scope="session", autouse=True)
def _cleanup_test_database():
    yield
    asyncio.run(_prepare_test_database())
