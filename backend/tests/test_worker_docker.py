from __future__ import annotations

from unittest.mock import MagicMock
from uuid import UUID

import pytest

from app.config import get_settings
from app.worker.docker import DockerManager


@pytest.fixture
def settings():
    return get_settings()


@pytest.fixture
def manager(settings):
    return DockerManager(settings)


@pytest.fixture
def mock_client(manager):
    client = MagicMock()
    manager._client = client
    return client


async def test_image_tag(manager):
    tag = manager._image_tag("user", "app", 3)
    assert tag == "sthub/user-app:3"


async def test_container_name(manager):
    sid = UUID("11111111-1111-1111-1111-111111111111")
    assert manager._container_name(sid) == "sthub-11111111-1111-1111-1111-111111111111"


async def test_labels(manager):
    sid = UUID("11111111-1111-1111-1111-111111111111")
    labels = manager._labels("user", "app", sid)
    assert labels["traefik.enable"] == "true"
    assert "PathPrefix(`/st/user/app`)" in labels[f"traefik.http.routers.st-{sid}.rule"]
    assert labels["sthub.user"] == "user"


async def test_write_context_dockerfile_uses_root_for_pip_install(manager, tmp_path):
    manager._write_context(tmp_path, {"app.py": "x"}, "streamlit\n", "/st/user/app")
    dockerfile = (tmp_path / "Dockerfile").read_text(encoding="utf-8")

    # The base image sets USER streamlit; pip install needs root and the base
    # image is PEP 668 managed, so --break-system-packages is required.
    assert (
        "RUN pip install --no-cache-dir --break-system-packages -r requirements.txt"
        in dockerfile
    )
    pip_idx = dockerfile.index("RUN pip install")
    root_idx = dockerfile.index("USER root")
    user_idx = dockerfile.index("USER streamlit")
    cmd_idx = dockerfile.index("CMD")
    assert root_idx < pip_idx < user_idx < cmd_idx


async def test_build_image_success(manager, mock_client):
    image = MagicMock()
    image.id = "sha256:abc"
    mock_client.images.build.return_value = (image, [{"stream": "step 1"}])

    result = await manager.build_image(
        UUID("11111111-1111-1111-1111-111111111111"),
        "user",
        "app",
        1,
        {"app.py": "import streamlit as st"},
        "streamlit\n",
    )

    assert result["success"] is True
    assert result["image_tag"] == "sthub/user-app:1"
    assert result["image_id"] == "sha256:abc"
    assert "step 1" in result["logs"]
    mock_client.images.build.assert_called_once()
    assert mock_client.images.build.call_args.kwargs.get("nocache") is None


async def test_build_image_failure(manager, mock_client):
    from docker.errors import BuildError

    mock_client.images.build.side_effect = BuildError(
        "Build failed", build_log=[{"stream": "error line"}]
    )

    result = await manager.build_image(
        UUID("11111111-1111-1111-1111-111111111111"),
        "user",
        "app",
        1,
        {"app.py": "import streamlit as st"},
        "streamlit\n",
    )

    assert result["success"] is False
    assert result["image_id"] is None
    assert result["logs"] == ["error line"]
    assert result["error"] == "Build failed"
    mock_client.images.build.assert_called_once()
    assert mock_client.images.build.call_args.kwargs.get("nocache") is None


async def test_build_image_retries_only_stale_cache_export_failure(
    manager, mock_client
):
    from docker.errors import BuildError

    image = MagicMock(id="sha256:retry")
    stale = BuildError(
        "failed to export image: No such image: sha256:deadbeef",
        build_log=[{"stream": "cached layer"}],
    )
    mock_client.images.build.side_effect = [
        stale,
        (image, [{"stream": "rebuilt layer"}]),
    ]

    result = await manager.build_image(
        UUID("11111111-1111-1111-1111-111111111111"),
        "user",
        "app",
        1,
        {"app.py": "import streamlit as st"},
        "streamlit\n",
    )

    assert result["success"] is True
    assert result["image_id"] == "sha256:retry"
    assert result["logs"] == ["cached layer", "rebuilt layer"]
    assert mock_client.images.build.call_count == 2
    assert mock_client.images.build.call_args_list[0].kwargs.get("nocache") is None
    assert mock_client.images.build.call_args_list[1].kwargs["nocache"] is True


async def test_build_image_returns_retry_failure_after_stale_cache_error(
    manager, mock_client
):
    from docker.errors import BuildError

    stale = BuildError(
        "failed to export image: No such image: sha256:deadbeef",
        build_log=[{"stream": "cached layer"}],
    )
    retry = BuildError("RETRY failed", build_log=[{"stream": "retry layer"}])
    mock_client.images.build.side_effect = [stale, retry]

    result = await manager.build_image(
        UUID("11111111-1111-1111-1111-111111111111"),
        "user",
        "app",
        1,
        {"app.py": "import streamlit as st"},
        "streamlit\n",
    )

    assert result == {
        "success": False,
        "image_tag": "sthub/user-app:1",
        "image_id": None,
        "logs": ["cached layer", "retry layer"],
        "error": "RETRY failed",
    }
    assert mock_client.images.build.call_count == 2
    assert mock_client.images.build.call_args_list[0].kwargs.get("nocache") is None
    assert mock_client.images.build.call_args_list[1].kwargs["nocache"] is True


async def test_run_container_success(manager, mock_client, monkeypatch):
    # Thread scheduling is outside this unit's contract and hangs in some
    # sandboxed pytest environments. Keep the DockerManager call path real.
    async def call_directly(function, *args, **kwargs):
        return function(*args, **kwargs)

    monkeypatch.setattr("app.worker.docker.asyncio.to_thread", call_directly)
    container = MagicMock()
    container.id = "container-id-123"
    mock_client.containers.run.return_value = container

    result = await manager.run_container(
        UUID("11111111-1111-1111-1111-111111111111"),
        "user",
        "app",
        1,
    )

    assert result["success"] is True
    assert result["container_id"] == "container-id-123"
    call_kwargs = mock_client.containers.run.call_args.kwargs
    assert call_kwargs["name"].startswith("sthub-")
    assert call_kwargs["network"] == manager.settings.DOCKER_NETWORK
    assert call_kwargs["cap_drop"] == ["ALL"]
    assert call_kwargs["restart_policy"] == {"Name": "unless-stopped"}
    assert call_kwargs["healthcheck"] == {
        "test": [
            "CMD",
            "python",
            "-c",
            "import urllib.request; urllib.request.urlopen("
            "'http://127.0.0.1:8501/st/user/app/_stcore/health', timeout=3)",
        ],
        "interval": 10_000_000_000,
        "timeout": 3_000_000_000,
        "retries": 5,
        "start_period": 20_000_000_000,
    }
    assert call_kwargs["tmpfs"] == {
        "/tmp": "rw,noexec,nosuid,size=64m",
        "/streamlit-runtime": "rw,noexec,nosuid,size=32m",
    }
    # No per-app limits were passed, so the global settings apply verbatim.
    assert call_kwargs["mem_limit"] == manager.settings.CONTAINER_MEMORY
    assert (
        call_kwargs["mem_reservation"] == manager.settings.CONTAINER_MEMORY_RESERVATION
    )
    assert call_kwargs["cpu_quota"] == manager.settings.CONTAINER_CPU_QUOTA


async def test_run_container_applies_per_app_limits(manager, mock_client, monkeypatch):
    """A streamlit's own cpu/memory limits must reach the container."""

    async def call_directly(function, *args, **kwargs):
        return function(*args, **kwargs)

    monkeypatch.setattr("app.worker.docker.asyncio.to_thread", call_directly)
    container = MagicMock()
    container.id = "container-id-456"
    mock_client.containers.run.return_value = container

    result = await manager.run_container(
        UUID("11111111-1111-1111-1111-111111111111"),
        "user",
        "app",
        1,
        cpu_limit=0.5,
        memory_limit_mb=256,
    )

    assert result["success"] is True
    call_kwargs = mock_client.containers.run.call_args.kwargs
    assert call_kwargs["mem_limit"] == 256 * 1024 * 1024
    assert call_kwargs["cpu_quota"] == 50_000
    assert call_kwargs["cpu_period"] == manager.settings.CONTAINER_CPU_PERIOD


async def test_run_container_caps_reservation_at_the_app_memory_limit(
    manager, mock_client, monkeypatch
):
    """Docker rejects a reservation above the limit, so it must be pulled down."""

    async def call_directly(function, *args, **kwargs):
        return function(*args, **kwargs)

    monkeypatch.setattr("app.worker.docker.asyncio.to_thread", call_directly)
    container = MagicMock()
    container.id = "container-id-789"
    mock_client.containers.run.return_value = container

    # The default reservation is 128m; a 64 MB app limit sits below it.
    await manager.run_container(
        UUID("11111111-1111-1111-1111-111111111111"),
        "user",
        "app",
        1,
        memory_limit_mb=64,
    )

    call_kwargs = mock_client.containers.run.call_args.kwargs
    assert call_kwargs["mem_limit"] == 64 * 1024 * 1024
    assert call_kwargs["mem_reservation"] == 64 * 1024 * 1024


async def test_run_container_api_error_returns_failure(manager, mock_client):
    from docker.errors import APIError

    # e.g. 409 Conflict from a duplicate container name: the failure must be
    # reported, not raised, so the caller can mark the app as "error".
    mock_client.containers.run.side_effect = APIError("409 Conflict")

    result = await manager.run_container(
        UUID("11111111-1111-1111-1111-111111111111"),
        "user",
        "app",
        1,
    )

    assert result["success"] is False
    assert result["container_id"] is None
    assert "409 Conflict" in result["error"]


async def test_run_container_removes_existing_container_before_run(
    manager, mock_client
):
    events = []
    existing = MagicMock()
    existing.remove.side_effect = lambda **kwargs: events.append("remove")
    mock_client.containers.get.return_value = existing
    new_container = MagicMock()
    new_container.id = "new-id"

    def fake_run(*args, **kwargs):
        events.append("run")
        return new_container

    mock_client.containers.run.side_effect = fake_run

    result = await manager.run_container(
        UUID("11111111-1111-1111-1111-111111111111"),
        "user",
        "app",
        1,
    )

    assert result["success"] is True
    mock_client.containers.get.assert_called_once_with(
        "sthub-11111111-1111-1111-1111-111111111111"
    )
    existing.remove.assert_called_once_with(force=True)
    assert events == ["remove", "run"]


async def test_run_container_without_existing_container(manager, mock_client):
    from docker.errors import NotFound

    mock_client.containers.get.side_effect = NotFound("no such container")
    container = MagicMock()
    container.id = "container-id-123"
    mock_client.containers.run.return_value = container

    result = await manager.run_container(
        UUID("11111111-1111-1111-1111-111111111111"),
        "user",
        "app",
        1,
    )

    assert result["success"] is True
    assert result["container_id"] == "container-id-123"


async def test_stop_container_success(manager, mock_client):
    container = MagicMock()
    mock_client.containers.get.return_value = container

    result = await manager.stop_container("container-id-123")

    assert result["success"] is True
    container.stop.assert_called_once_with(timeout=10)
    container.remove.assert_called_once_with(force=True)


async def test_stop_container_failure_returns_error(manager, mock_client):
    container = MagicMock()
    container.stop.side_effect = RuntimeError("daemon refused")
    mock_client.containers.get.return_value = container

    result = await manager.stop_container("container-id-123")

    assert result["success"] is False
    assert "daemon refused" in result["error"]


async def test_remove_image_success(manager, mock_client):
    result = await manager.remove_image("sthub/user-app:1")

    assert result["success"] is True
    mock_client.images.remove.assert_called_once_with("sthub/user-app:1", force=True)


async def test_stream_logs_success(manager, mock_client):
    container = MagicMock()
    container.logs.return_value = b"line1\nline2\n"
    mock_client.containers.get.return_value = container

    lines = await manager.stream_logs("container-id-123", tail=10)

    assert lines == ["line1", "line2"]


async def test_stream_logs_missing_container_returns_empty(manager, mock_client):
    from docker.errors import NotFound

    mock_client.containers.get.side_effect = NotFound("no such container")

    lines = await manager.stream_logs("container-id-123", tail=10)

    assert lines == []


async def test_close_closes_client(manager, mock_client):
    await manager.close()
    assert manager._client is None
