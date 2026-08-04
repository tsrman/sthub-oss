from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest

from app.config import get_settings
from app.worker.context import WorkerContext
from app.worker.reconciler import reconcile_state


@pytest.fixture
def streamlit_id():
    return UUID("11111111-1111-1111-1111-111111111111")


@pytest.fixture
def mock_app(streamlit_id):
    app = MagicMock()
    app.id = streamlit_id
    app.container_id = "container-123"
    return app


@pytest.fixture
def building_apps():
    return []


@pytest.fixture
def mock_session(mock_app, building_apps):
    session = AsyncMock()

    def execute_side_effect(query):
        compiled = str(query.compile(compile_kwargs={"literal_binds": True}))
        result = MagicMock()
        if "'building'" in compiled:
            result.scalars.return_value = MagicMock(
                all=MagicMock(return_value=building_apps)
            )
        else:
            result.scalars.return_value = MagicMock(
                all=MagicMock(return_value=[mock_app])
            )
        result.scalar_one_or_none.return_value = mock_app
        return result

    session.execute = AsyncMock(side_effect=execute_side_effect)
    session.add = MagicMock()
    return session


@pytest.fixture
def mock_db_session_factory(mock_session):
    def factory():
        return mock_session

    return factory


@pytest.fixture
def mock_docker():
    docker = MagicMock()
    docker._client = MagicMock()
    container = MagicMock()
    container.attrs = {"State": {"Running": True}}
    docker._client_sync = MagicMock(return_value=docker._client)
    # docker-py's containers.get is synchronous; the reconciler must call it
    # via asyncio.to_thread, so the mock stays a plain MagicMock.
    docker._client.containers.get = MagicMock(return_value=container)
    return docker


@pytest.fixture
def ctx(mock_db_session_factory, mock_docker):
    return WorkerContext(
        db=mock_db_session_factory,
        settings=get_settings(),
        docker=mock_docker,
    )


async def test_reconcile_state_no_docker(ctx):
    ctx.docker = None
    result = await reconcile_state(ctx)
    assert result == {"checked": 0, "corrected": 0, "failed": 0, "stale_building": 0}


async def test_reconcile_state_running_container_still_running(
    ctx, mock_app, mock_docker
):
    result = await reconcile_state(ctx)
    assert result["checked"] == 1
    assert result["corrected"] == 0
    assert result["failed"] == 0
    assert mock_app.status != "stopped"
    # A healthy container must never be removed by the reconciler.
    mock_docker._client.containers.get.return_value.remove.assert_not_called()


async def test_reconcile_state_stopped_container_marked_stopped(
    ctx, mock_app, mock_docker
):
    container = mock_docker._client.containers.get.return_value
    container.attrs = {"State": {"Running": False}}
    result = await reconcile_state(ctx)
    assert result["checked"] == 1
    assert result["corrected"] == 1
    assert mock_app.status == "stopped"
    assert mock_app.container_id is None
    # The dead container is removed from Docker as well.
    container.remove.assert_called_once_with(force=True)


async def test_reconcile_state_missing_container_marked_stopped(
    ctx, mock_app, mock_docker
):
    from docker.errors import NotFound

    mock_docker._client.containers.get.side_effect = NotFound("no such container")
    result = await reconcile_state(ctx)
    assert result["checked"] == 1
    assert result["corrected"] == 1
    assert mock_app.status == "stopped"


async def test_reconcile_state_docker_error_does_not_mark_stopped(
    ctx, mock_app, mock_docker
):
    # Transient Docker errors (daemon restart, network) must not stop apps:
    # the record is left alone and the failure is counted instead.
    mock_docker._client.containers.get.side_effect = Exception("daemon down")
    result = await reconcile_state(ctx)
    assert result["checked"] == 1
    assert result["corrected"] == 0
    assert result["failed"] == 1
    assert mock_app.status != "stopped"
    assert mock_app.container_id == "container-123"


async def test_reconcile_state_no_container_id_marked_stopped(ctx, mock_app):
    mock_app.container_id = None
    result = await reconcile_state(ctx)
    assert result["checked"] == 1
    assert result["corrected"] == 1
    assert mock_app.status == "stopped"


async def test_reconcile_state_stale_building_marked_error(
    ctx, mock_app, building_apps
):
    # An app stuck in "building" longer than WORKER_JOB_TIMEOUT is failed.
    stale_app = MagicMock()
    stale_app.id = UUID("33333333-3333-3333-3333-333333333333")
    stale_app.status = "building"
    timeout = ctx.settings.WORKER_JOB_TIMEOUT
    stale_app.updated_at = datetime.now(timezone.utc) - timedelta(seconds=2 * timeout)
    building_apps.append(stale_app)

    result = await reconcile_state(ctx)

    assert result["stale_building"] == 1
    # _mark_error loads the row through scalar_one_or_none (mocked as mock_app).
    assert mock_app.status == "error"


async def test_reconcile_state_recent_building_left_alone(ctx, mock_app, building_apps):
    recent_app = MagicMock()
    recent_app.id = UUID("44444444-4444-4444-4444-444444444444")
    recent_app.status = "building"
    recent_app.updated_at = datetime.now(timezone.utc)
    building_apps.append(recent_app)

    result = await reconcile_state(ctx)

    assert result["stale_building"] == 0
    assert mock_app.status != "error"
