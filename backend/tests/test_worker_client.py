import asyncio
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from arq.connections import RedisSettings

from app.config import Settings
from app.services.worker_client import WorkerClient
from app.worker.settings import WorkerSettings


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture
def settings():
    return Settings(
        REDIS_URL="redis://localhost:6379/0", ARQ_QUEUE_NAME="arq:streamlit"
    )


@pytest.fixture
def client(settings):
    return WorkerClient(settings=settings)


@pytest.fixture
def mock_pool():
    pool = AsyncMock()
    pool.enqueue_job = AsyncMock(return_value=AsyncMock(job_id="mock-job-id"))
    return pool


@pytest.fixture
def patched_create_pool(mock_pool):
    with patch(
        "app.services.worker_client.create_pool",
        new_callable=AsyncMock,
        return_value=mock_pool,
    ) as p:
        yield p


def test_enqueue_build_run(client, mock_pool, patched_create_pool):
    streamlit_id = uuid.uuid4()

    job_id = _run(client.enqueue_build_run(streamlit_id))

    assert job_id == "mock-job-id"
    patched_create_pool.assert_awaited_once()
    mock_pool.enqueue_job.assert_awaited_once_with(
        "streamlit_task",
        "build_run",
        str(streamlit_id),
        _queue_name="arq:streamlit",
    )
    mock_pool.close.assert_awaited_once()


def test_enqueue_stop(client, mock_pool, patched_create_pool):
    streamlit_id = uuid.uuid4()

    job_id = _run(client.enqueue_stop(streamlit_id))

    assert job_id == "mock-job-id"
    patched_create_pool.assert_awaited_once()
    mock_pool.enqueue_job.assert_awaited_once_with(
        "streamlit_task",
        "stop",
        str(streamlit_id),
        _queue_name="arq:streamlit",
    )
    mock_pool.close.assert_awaited_once()


def test_enqueue_remove_with_container_and_image(
    client, mock_pool, patched_create_pool
):
    streamlit_id = uuid.uuid4()
    container_id = "container-abc"
    image_tag = "sthub/user-app:v1"

    job_id = _run(client.enqueue_remove(streamlit_id, container_id, image_tag))

    assert job_id == "mock-job-id"
    patched_create_pool.assert_awaited_once()
    mock_pool.enqueue_job.assert_awaited_once_with(
        "streamlit_task",
        "remove",
        str(streamlit_id),
        container_id,
        image_tag,
        _queue_name="arq:streamlit",
    )
    mock_pool.close.assert_awaited_once()


def test_enqueue_remove_without_container_and_image(
    client, mock_pool, patched_create_pool
):
    streamlit_id = uuid.uuid4()

    _run(client.enqueue_remove(streamlit_id, None, None))

    args = mock_pool.enqueue_job.await_args.args
    assert args == ("streamlit_task", "remove", str(streamlit_id), None, None)


def test_each_call_creates_its_own_pool_and_closes(client):
    pool1 = AsyncMock()
    pool1.enqueue_job = AsyncMock(return_value=AsyncMock(job_id="job-1"))
    pool2 = AsyncMock()
    pool2.enqueue_job = AsyncMock(return_value=AsyncMock(job_id="job-2"))

    with patch(
        "app.services.worker_client.create_pool",
        new_callable=AsyncMock,
        side_effect=[pool1, pool2],
    ) as create:
        streamlit_id1 = uuid.uuid4()
        streamlit_id2 = uuid.uuid4()
        _run(client.enqueue_build_run(streamlit_id1))
        _run(client.enqueue_stop(streamlit_id2))

    assert create.await_count == 2
    pool1.close.assert_awaited_once()
    pool2.close.assert_awaited_once()


def test_job_id_is_not_passed_to_arq(client, mock_pool, patched_create_pool):
    # Jobs must not pin a fixed arq job ID: arq drops enqueue_job silently when
    # a job/result with the same ID already exists (results are kept for 1h).
    streamlit_id = uuid.uuid4()

    _run(client.enqueue_build_run(streamlit_id))

    assert mock_pool.enqueue_job.await_count == 1
    assert "_job_id" not in mock_pool.enqueue_job.await_args.kwargs


def test_enqueue_returns_none_raises_runtime_error(
    client, mock_pool, patched_create_pool
):
    # arq returns None when it refused the job; that must surface as an error
    # so callers get a 500 instead of silently losing the task.
    streamlit_id = uuid.uuid4()
    mock_pool.enqueue_job.return_value = None

    with pytest.raises(RuntimeError, match="failed to enqueue"):
        _run(client.enqueue_build_run(streamlit_id))

    mock_pool.close.assert_awaited_once()


def test_enqueue_failure_propagates_and_pool_is_closed(
    client, mock_pool, patched_create_pool
):
    streamlit_id = uuid.uuid4()
    mock_pool.enqueue_job.side_effect = ConnectionError("redis is down")

    with pytest.raises(ConnectionError, match="redis is down"):
        _run(client.enqueue_build_run(streamlit_id))

    mock_pool.close.assert_awaited_once()


def test_settings_arq_queue_name_default():
    settings = Settings()
    assert settings.ARQ_QUEUE_NAME == "arq:streamlit"


def test_worker_settings_are_plain_attributes():
    # WorkerSettings must expose arq config as evaluated values, not descriptors.
    assert isinstance(WorkerSettings.redis_settings, RedisSettings)
    assert WorkerSettings.queue_name == "arq:streamlit"
    assert not isinstance(WorkerSettings.redis_settings, property)
    assert not isinstance(WorkerSettings.queue_name, property)
    assert "streamlit_task" in [fn.__name__ for fn in WorkerSettings.functions]
