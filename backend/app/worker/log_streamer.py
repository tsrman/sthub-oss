from __future__ import annotations

import asyncio
import logging
from uuid import UUID

from sqlalchemy import select

from app.models.streamlit import StreamlitApp
from app.worker.context import WorkerContext
from app.worker.tasks import _record_build_logs

logger = logging.getLogger("app.worker.log_streamer")

_RUNTIME_POLL_INTERVAL = 3.0


class LogStreamerManager:
    """Manage background tasks that tail runtime logs from running containers.

    The manager writes log lines to the same ``build_logs`` table as build logs,
    using stage ``runtime``. This keeps the SSE logs endpoint simple: it streams
    every log entry for a streamlit, regardless of whether it came from the build
    or the running container.
    """

    def __init__(self, ctx: WorkerContext | None = None) -> None:
        self.ctx = ctx
        self._tasks: dict[UUID, asyncio.Task[None]] = {}

    async def start(self, streamlit_id: UUID, container_id: str) -> None:
        """Start a background streamer for *container_id*."""
        if streamlit_id in self._tasks:
            logger.debug("streamlit_id=%s already streaming", streamlit_id)
            return
        logger.info(
            "Starting runtime log streamer for streamlit_id=%s container=%s",
            streamlit_id,
            container_id,
        )
        task = asyncio.create_task(
            _stream_container_logs(self.ctx, streamlit_id, container_id),
            name=f"log-streamer-{streamlit_id}",
        )
        self._tasks[streamlit_id] = task

    async def stop(self, streamlit_id: UUID) -> None:
        """Stop the streamer for *streamlit_id* if it exists."""
        task = self._tasks.pop(streamlit_id, None)
        if task is None:
            return
        logger.info("Stopping runtime log streamer for streamlit_id=%s", streamlit_id)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    async def start_for_running_apps(self) -> None:
        """Resume streamers for all apps already marked as running in Postgres."""
        async with self.ctx.db_session() as session:
            result = await session.execute(
                select(StreamlitApp).where(StreamlitApp.status == "running")
            )
            apps = result.scalars().all()

        for app in apps:
            if app.container_id:
                await self.start(app.id, app.container_id)
            else:
                logger.warning(
                    "streamlit_id=%s is running but has no container_id", app.id
                )


def _new_lines(prev: list[str], current: list[str]) -> list[str]:
    """Return the lines from *current* that were not already seen in *prev*.

    ``prev`` is the previous ``tail`` sample of the same container log. The
    largest overlap between the tail of ``prev`` and the head of ``current``
    marks already-recorded lines; only the remainder is new. When there is no
    overlap (log rotated or a new container) every line of ``current`` is new.
    Unlike content-based dedup this keeps legitimately repeated lines.
    """
    max_overlap = min(len(prev), len(current))
    for size in range(max_overlap, 0, -1):
        if prev[-size:] == current[:size]:
            return current[size:]
    return current


async def _stream_container_logs(
    ctx: WorkerContext,
    streamlit_id: UUID,
    container_id: str,
) -> None:
    """Poll container logs and append new lines to ``build_logs``."""
    prev_lines: list[str] = []
    docker = ctx.docker
    if docker is None:
        logger.error("docker manager not available, cannot stream logs")
        return

    while True:
        lines: list[str] | None
        try:
            lines = await docker.stream_logs(container_id, tail=200)
        except Exception as exc:
            logger.warning(
                "Failed to fetch logs for streamlit_id=%s container=%s: %s",
                streamlit_id,
                container_id,
                exc,
            )
            lines = None

        if lines is not None:
            new_lines = _new_lines(prev_lines, lines)
            if new_lines:
                await _record_build_logs(
                    ctx, streamlit_id, "runtime", "info", new_lines
                )
            prev_lines = lines

        try:
            await asyncio.sleep(_RUNTIME_POLL_INTERVAL)
        except asyncio.CancelledError:
            logger.debug("Log streamer for streamlit_id=%s cancelled", streamlit_id)
            raise
