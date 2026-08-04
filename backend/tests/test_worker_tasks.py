from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest

from app.config import get_settings
from app.worker.context import WorkerContext
from app.worker.tasks import handle_build_run, handle_remove, handle_stop


@pytest.fixture
def streamlit_id():
    return UUID("11111111-1111-1111-1111-111111111111")


@pytest.fixture
def user_id():
    return UUID("22222222-2222-2222-2222-222222222222")


@pytest.fixture
def mock_app(streamlit_id, user_id):
    app = MagicMock()
    app.id = streamlit_id
    app.user_id = user_id
    app.slug = "app"
    app.version = 3
    app.container_id = "old-container-id"
    app.image_tag = "sthub/user-app:2"
    return app


@pytest.fixture
def mock_user(user_id):
    user = MagicMock()
    user.id = user_id
    user.login = "user"
    return user


@pytest.fixture
def mock_session(mock_app, mock_user):
    session = AsyncMock()

    def execute_side_effect(query):
        result = MagicMock()
        result.scalars.return_value = MagicMock(all=MagicMock(return_value=[]))
        # Distinguish owner lookup (users table) from app lookup (streamlits).
        if "users" in str(query):
            result.scalar_one_or_none.return_value = mock_user
        else:
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
    docker.build_image = AsyncMock(
        return_value={
            "success": True,
            "image_tag": "sthub/user-app:3",
            "image_id": "sha256:abc",
            "logs": ["build ok"],
            "error": None,
        }
    )
    docker.run_container = AsyncMock(
        return_value={
            "success": True,
            "container_id": "new-container-id",
            "error": None,
        }
    )
    docker.stop_container = AsyncMock(return_value={"success": True})
    docker.remove_container = AsyncMock(return_value={"success": True})
    docker.remove_image = AsyncMock(return_value={"success": True})
    return docker


@pytest.fixture
def ctx(mock_db_session_factory, mock_docker):
    return WorkerContext(
        db=mock_db_session_factory,
        settings=get_settings(),
        docker=mock_docker,
    )


async def test_handle_build_run_success(ctx, streamlit_id, mock_docker, mock_app):
    await handle_build_run(ctx, streamlit_id)

    mock_docker.build_image.assert_awaited_once()
    mock_docker.stop_container.assert_awaited_once_with("old-container-id")
    mock_docker.run_container.assert_awaited_once()
    assert mock_app.status == "running"
    assert mock_app.container_id == "new-container-id"
    assert mock_app.image_tag == "sthub/user-app:3"


async def test_handle_build_run_build_failure(ctx, streamlit_id, mock_docker, mock_app):
    mock_docker.build_image.return_value = {
        "success": False,
        "image_tag": "sthub/user-app:3",
        "logs": ["build failed"],
        "error": "pip install failed",
    }

    await handle_build_run(ctx, streamlit_id)

    mock_docker.run_container.assert_not_awaited()
    assert mock_app.status == "error"


async def test_handle_build_run_missing_app(ctx, streamlit_id, mock_docker):
    # Override the session to return None for the app lookup.
    session = ctx.db
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    session.session = AsyncMock()
    session.session.execute = AsyncMock(return_value=result)
    # Easier: patch _load_app to return None.
    with patch("app.worker.tasks._load_app", return_value=None):
        await handle_build_run(ctx, streamlit_id)

    mock_docker.build_image.assert_not_awaited()


async def test_handle_build_run_missing_owner_marks_error(
    ctx, streamlit_id, mock_docker, mock_app
):
    with patch("app.worker.tasks._load_owner", new=AsyncMock(return_value=None)):
        await handle_build_run(ctx, streamlit_id)

    mock_docker.build_image.assert_not_awaited()
    assert mock_app.status == "error"


async def test_handle_build_run_run_failure_marks_error(
    ctx, streamlit_id, mock_docker, mock_app
):
    # A failed run (e.g. Docker API error) must surface as "error", not leave
    # the app stuck in "building" forever.
    mock_docker.run_container.return_value = {
        "success": False,
        "container_id": None,
        "error": "409 Conflict",
    }

    await handle_build_run(ctx, streamlit_id)

    assert mock_app.status == "error"
    # The built image tag is kept, container_id is not overwritten.
    assert mock_app.image_tag == "sthub/user-app:3"
    assert mock_app.container_id == "old-container-id"


async def test_load_files_reads_text_bytes_and_empty(streamlit_id):
    from app.worker.tasks import _load_files

    text_file = MagicMock(path="app.py", content_text="code", content_bytes=None)
    bytes_file = MagicMock(path="data.bin", content_text=None, content_bytes=b"\x00")
    empty_file = MagicMock(path="empty.txt", content_text=None, content_bytes=None)

    session = AsyncMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = [text_file, bytes_file, empty_file]
    session.execute = AsyncMock(return_value=result)

    ctx = WorkerContext(db=lambda: session, settings=get_settings())

    files = await _load_files(ctx, streamlit_id)

    assert files == {"app.py": "code", "data.bin": b"\x00", "empty.txt": ""}


async def test_handle_stop_success(ctx, streamlit_id, mock_docker, mock_app):
    await handle_stop(ctx, streamlit_id)

    mock_docker.stop_container.assert_awaited_once_with("old-container-id")
    assert mock_app.status == "stopped"
    assert mock_app.container_id is None


async def test_handle_stop_without_container_marks_stopped(
    ctx, streamlit_id, mock_docker, mock_app
):
    mock_app.container_id = None

    await handle_stop(ctx, streamlit_id)

    mock_docker.stop_container.assert_not_awaited()
    assert mock_app.status == "stopped"
    assert mock_app.container_id is None


async def test_handle_stop_failure_marks_error_and_keeps_container(
    ctx, streamlit_id, mock_docker, mock_app
):
    # A failed stop must not silently leak the container: the app is marked
    # "error" and container_id is kept so the container stays tracked.
    mock_docker.stop_container.return_value = {
        "success": False,
        "error": "daemon refused to stop container",
    }

    await handle_stop(ctx, streamlit_id)

    mock_docker.stop_container.assert_awaited_once_with("old-container-id")
    assert mock_app.status == "error"
    assert mock_app.container_id == "old-container-id"


async def test_handle_remove_success(ctx, streamlit_id, mock_docker):
    await handle_remove(ctx, streamlit_id, "container-id", "sthub/user-app:2")

    mock_docker.remove_container.assert_awaited_once_with("container-id")
    mock_docker.remove_image.assert_awaited_once_with("sthub/user-app:2")


async def test_record_build_logs_inserts_all_lines_in_one_batch(
    ctx, streamlit_id, mock_session
):
    from app.worker.tasks import _record_build_logs

    await _record_build_logs(ctx, streamlit_id, "runtime", "info", ["a", "b"])

    # All lines go in a single add_all, not one insert per line.
    mock_session.add_all.assert_called_once()
    logs = list(mock_session.add_all.call_args.args[0])
    assert [log.message for log in logs] == ["a", "b"]
    assert {log.stage for log in logs} == {"runtime"}
    assert {log.level for log in logs} == {"info"}
    assert mock_session.commit.await_count >= 1


async def test_record_build_logs_empty_list_is_noop(ctx, streamlit_id, mock_session):
    from app.worker.tasks import _record_build_logs

    await _record_build_logs(ctx, streamlit_id, "runtime", "info", [])

    mock_session.add_all.assert_not_called()
