"""Unit tests for the runtime log streamer."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest

from app.worker.context import WorkerContext
from app.worker.log_streamer import LogStreamerManager, _stream_container_logs

SID = UUID("11111111-1111-1111-1111-111111111111")
SID2 = UUID("22222222-2222-2222-2222-222222222222")


def _ctx(*, db=None, docker=None) -> WorkerContext:
    return WorkerContext(db=db or MagicMock(), settings=MagicMock(), docker=docker)


# ---------------------------------------------------------------------------
# LogStreamerManager.start / stop
# ---------------------------------------------------------------------------


async def test_start_is_idempotent_and_stop_cancels() -> None:
    manager = LogStreamerManager(_ctx())

    async def fake_stream(*_args, **_kwargs):
        await asyncio.sleep(3600)

    with patch(
        "app.worker.log_streamer._stream_container_logs", side_effect=fake_stream
    ):
        await manager.start(SID, "c1")
        first = manager._tasks[SID]
        await manager.start(SID, "c1")  # second call is a no-op
        assert len(manager._tasks) == 1
        assert manager._tasks[SID] is first

        await manager.stop(SID)
        assert SID not in manager._tasks
        assert first.cancelled()

    # Stopping an unknown id is a safe no-op.
    await manager.stop(SID)


# ---------------------------------------------------------------------------
# _stream_container_logs
# ---------------------------------------------------------------------------


async def test_stream_logs_without_docker_returns() -> None:
    # No docker manager → should log and return immediately, no exception.
    await _stream_container_logs(_ctx(docker=None), SID, "c1")


async def test_stream_logs_dedupes_across_polls() -> None:
    docker = MagicMock()
    # Two poll iterations; "line-b" is the overlap and must not be re-recorded.
    docker.stream_logs = AsyncMock(
        side_effect=[["line-a", "line-b"], ["line-b", "line-c"]]
    )
    ctx = _ctx(docker=docker)

    batches: list[list[str]] = []

    async def fake_record(_ctx, _sid, _stage, _level, lines):
        batches.append(list(lines))

    # First sleep returns, second sleep breaks the loop.
    with (
        patch("app.worker.log_streamer._record_build_logs", side_effect=fake_record),
        patch(
            "app.worker.log_streamer.asyncio.sleep",
            side_effect=[None, asyncio.CancelledError],
        ),
    ):
        with pytest.raises(asyncio.CancelledError):
            await _stream_container_logs(ctx, SID, "c1")

    # "line-b" seen in poll 1 is skipped in poll 2; one batch per poll.
    assert batches == [["line-a", "line-b"], ["line-c"]]


async def test_stream_logs_preserves_repeated_lines() -> None:
    docker = MagicMock()
    # Identical lines repeat legitimately; content-based dedup must not drop
    # them. The second identical poll adds nothing new.
    docker.stream_logs = AsyncMock(side_effect=[["x", "x"], ["x", "x"]])
    ctx = _ctx(docker=docker)

    batches: list[list[str]] = []

    async def fake_record(_ctx, _sid, _stage, _level, lines):
        batches.append(list(lines))

    with (
        patch("app.worker.log_streamer._record_build_logs", side_effect=fake_record),
        patch(
            "app.worker.log_streamer.asyncio.sleep",
            side_effect=[None, asyncio.CancelledError],
        ),
    ):
        with pytest.raises(asyncio.CancelledError):
            await _stream_container_logs(ctx, SID, "c1")

    assert batches == [["x", "x"]]


async def test_stream_logs_no_overlap_records_everything() -> None:
    docker = MagicMock()
    # No common suffix/prefix (log rotated or container replaced): the whole
    # new sample is recorded.
    docker.stream_logs = AsyncMock(side_effect=[["a", "b"], ["c", "d"]])
    ctx = _ctx(docker=docker)

    batches: list[list[str]] = []

    async def fake_record(_ctx, _sid, _stage, _level, lines):
        batches.append(list(lines))

    with (
        patch("app.worker.log_streamer._record_build_logs", side_effect=fake_record),
        patch(
            "app.worker.log_streamer.asyncio.sleep",
            side_effect=[None, asyncio.CancelledError],
        ),
    ):
        with pytest.raises(asyncio.CancelledError):
            await _stream_container_logs(ctx, SID, "c1")

    assert batches == [["a", "b"], ["c", "d"]]


async def test_stream_logs_handles_docker_error() -> None:
    docker = MagicMock()
    docker.stream_logs = AsyncMock(side_effect=RuntimeError("docker down"))
    ctx = _ctx(docker=docker)

    with (
        patch("app.worker.log_streamer._record_build_logs", new=AsyncMock()) as rec,
        patch(
            "app.worker.log_streamer.asyncio.sleep",
            side_effect=asyncio.CancelledError,
        ),
    ):
        with pytest.raises(asyncio.CancelledError):
            await _stream_container_logs(ctx, SID, "c1")

    # Fetch failed → no lines recorded, but the loop survives the error.
    rec.assert_not_called()


# ---------------------------------------------------------------------------
# start_for_running_apps
# ---------------------------------------------------------------------------


async def test_start_for_running_apps_starts_only_apps_with_container() -> None:
    app_ok = SimpleNamespace(id=SID, container_id="c1")
    app_no_container = SimpleNamespace(id=SID2, container_id=None)

    session = AsyncMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = [app_ok, app_no_container]
    session.execute = AsyncMock(return_value=result)

    manager = LogStreamerManager(_ctx(db=lambda: session))
    manager.start = AsyncMock()

    await manager.start_for_running_apps()

    manager.start.assert_awaited_once_with(SID, "c1")
