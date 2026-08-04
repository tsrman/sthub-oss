import inspect
from datetime import timedelta

import pytest
from arq.connections import RedisSettings

from app.config import Settings
from app.worker.docker import DockerManager
from app.worker.settings import WorkerSettings, shutdown, startup, streamlit_task


def test_worker_settings_can_be_imported():
    assert WorkerSettings is not None


def test_worker_settings_redis_settings_is_redis_settings():
    assert isinstance(WorkerSettings.redis_settings, RedisSettings)


def test_worker_settings_queue_name_matches_config():
    settings = Settings()
    assert WorkerSettings.queue_name == settings.ARQ_QUEUE_NAME


def test_worker_settings_functions_contain_streamlit_task():
    names = [fn.__name__ for fn in WorkerSettings.functions]
    assert "streamlit_task" in names


def test_worker_settings_max_jobs_is_int():
    assert isinstance(WorkerSettings.max_jobs, int)
    assert WorkerSettings.max_jobs > 0


def test_worker_settings_job_timeout_is_timedelta():
    assert isinstance(WorkerSettings.job_timeout, timedelta)
    assert WorkerSettings.job_timeout.total_seconds() > 0


def test_startup_is_coroutine():
    assert inspect.iscoroutinefunction(startup)


def test_shutdown_is_coroutine():
    assert inspect.iscoroutinefunction(shutdown)


def test_streamlit_task_is_coroutine():
    assert inspect.iscoroutinefunction(streamlit_task)


@pytest.mark.asyncio
async def test_streamlit_task_dispatches_to_handlers():
    from unittest.mock import AsyncMock, MagicMock, patch
    from uuid import UUID

    from app.worker.context import WorkerContext

    worker_ctx = MagicMock(spec=WorkerContext)
    ctx = {
        "logger": __import__("logging").getLogger("test.worker"),
        "worker_ctx": worker_ctx,
    }

    with patch("app.worker.tasks.handle_build_run", new=AsyncMock()) as mock_build:
        await streamlit_task(ctx, "build_run", "11111111-1111-1111-1111-111111111111")

    mock_build.assert_awaited_once_with(
        worker_ctx, UUID("11111111-1111-1111-1111-111111111111")
    )


@pytest.mark.asyncio
async def test_streamlit_task_serializes_same_streamlit_id():
    import asyncio
    from unittest.mock import AsyncMock, MagicMock, patch

    from app.worker.context import WorkerContext

    events: list[str] = []

    async def slow_handler(_ctx, sid):
        events.append(f"start-{sid}")
        await asyncio.sleep(0.05)
        events.append(f"end-{sid}")

    worker_ctx = MagicMock(spec=WorkerContext)
    ctx = {
        "logger": __import__("logging").getLogger("test.worker"),
        "worker_ctx": worker_ctx,
    }
    sid = "11111111-1111-1111-1111-111111111111"

    with patch("app.worker.tasks.handle_build_run", new=AsyncMock()) as mock_build:
        mock_build.side_effect = slow_handler
        await asyncio.gather(
            streamlit_task(ctx, "build_run", sid),
            streamlit_task(ctx, "build_run", sid),
        )

    # The second task must not start before the first one finished.
    assert events == [f"start-{sid}", f"end-{sid}", f"start-{sid}", f"end-{sid}"]


@pytest.mark.asyncio
async def test_streamlit_task_different_ids_run_in_parallel():
    import asyncio
    from unittest.mock import AsyncMock, MagicMock, patch

    from app.worker.context import WorkerContext

    events: list[str] = []

    async def slow_handler(_ctx, sid):
        events.append(f"start-{sid}")
        await asyncio.sleep(0.05)
        events.append(f"end-{sid}")

    worker_ctx = MagicMock(spec=WorkerContext)
    ctx = {
        "logger": __import__("logging").getLogger("test.worker"),
        "worker_ctx": worker_ctx,
    }
    sid1 = "11111111-1111-1111-1111-111111111111"
    sid2 = "22222222-2222-2222-2222-222222222222"

    with patch("app.worker.tasks.handle_build_run", new=AsyncMock()) as mock_build:
        mock_build.side_effect = slow_handler
        await asyncio.gather(
            streamlit_task(ctx, "build_run", sid1),
            streamlit_task(ctx, "build_run", sid2),
        )

    # Both tasks start before either of them finishes.
    assert set(events[:2]) == {f"start-{sid1}", f"start-{sid2}"}
    assert set(events[2:]) == {f"end-{sid1}", f"end-{sid2}"}


@pytest.mark.asyncio
async def test_startup_creates_worker_context():
    ctx = {}
    await startup(ctx)
    worker_ctx = ctx.get("worker_ctx")
    assert worker_ctx is not None
    assert worker_ctx.docker is not None
    assert isinstance(worker_ctx.docker, DockerManager)
    assert ctx["streamlit_locks"] == {}
    await shutdown(ctx)


@pytest.mark.asyncio
async def test_shutdown_tolerates_missing_context():
    ctx = {}
    await shutdown(ctx)  # should not raise


def test_worker_settings_are_plain_attributes():
    # arq evaluates these as class attributes, not descriptors/properties.
    assert not isinstance(WorkerSettings.redis_settings, property)
    assert not isinstance(WorkerSettings.queue_name, property)
    assert not isinstance(WorkerSettings.max_jobs, property)
    assert not isinstance(WorkerSettings.job_timeout, property)
