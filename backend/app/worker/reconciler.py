from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID

from docker.errors import NotFound
from sqlalchemy import select

from app.models.streamlit import StreamlitApp
from app.worker.context import WorkerContext

logger = logging.getLogger("app.worker")


async def reconcile_state(ctx: WorkerContext) -> dict[str, int]:
    """Align Postgres state with actual Docker containers.

    Scans all streamlits that are marked as ``running`` and verifies that the
    recorded container still exists.  Containers that have disappeared are
    treated as stopped: the record is updated to ``stopped`` and ``container_id``
    is cleared. Also stops the associated runtime log streamer.

    Apps stuck in ``building`` for longer than ``WORKER_JOB_TIMEOUT`` (e.g. the
    worker crashed mid-build) are marked as ``error``.

    Returns a summary dict with the number of checked, corrected, failed and
    stale_building records.
    """
    corrected = 0
    failed = 0
    stale_building = await _reconcile_stale_building(ctx)

    if ctx.docker is None:
        logger.error("docker manager not available, skipping reconciliation")
        return {
            "checked": 0,
            "corrected": 0,
            "failed": 0,
            "stale_building": stale_building,
        }

    async with ctx.db_session() as session:
        result = await session.execute(
            select(StreamlitApp).where(StreamlitApp.status == "running")
        )
        apps = result.scalars().all()

    checked = len(apps)
    logger.info("Reconciling %d running streamlit(s)", checked)

    for app in apps:
        if not app.container_id:
            logger.warning(
                "streamlit_id=%s is running without container_id, marking stopped",
                app.id,
            )
            ok = await _mark_stopped(ctx, app.id)
            if ok:
                corrected += 1
            else:
                failed += 1
            continue

        # The docker-py client is synchronous, so calls go through threads.
        try:
            container = await asyncio.to_thread(
                ctx.docker._client_sync().containers.get, app.container_id
            )
        except NotFound:
            logger.warning(
                "streamlit_id=%s container=%s no longer exists, marking stopped",
                app.id,
                app.container_id,
            )
            ok = await _mark_stopped(ctx, app.id)
            if ok:
                corrected += 1
            else:
                failed += 1
            continue
        except Exception as exc:
            # Transient Docker errors must not stop healthy apps.
            logger.warning(
                "streamlit_id=%s container=%s could not be inspected (%s), "
                "leaving record unchanged",
                app.id,
                app.container_id,
                exc,
            )
            failed += 1
            continue

        state = container.attrs.get("State", {})
        is_running = state.get("Running", False)
        if not is_running:
            logger.warning(
                "streamlit_id=%s container=%s is not running, removing it and "
                "marking stopped",
                app.id,
                app.container_id,
            )
            try:
                await asyncio.to_thread(container.remove, force=True)
            except Exception as exc:
                logger.warning(
                    "streamlit_id=%s container=%s could not be removed (%s)",
                    app.id,
                    app.container_id,
                    exc,
                )
                failed += 1
                continue
            ok = await _mark_stopped(ctx, app.id)
            if ok:
                corrected += 1
            else:
                failed += 1

    return {
        "checked": checked,
        "corrected": corrected,
        "failed": failed,
        "stale_building": stale_building,
    }


async def _reconcile_stale_building(ctx: WorkerContext) -> int:
    """Mark apps stuck in ``building`` longer than the job timeout as ``error``.

    A build that outlived ``WORKER_JOB_TIMEOUT`` means the worker died or the
    job was aborted without reaching a final status update.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(
        seconds=ctx.settings.WORKER_JOB_TIMEOUT
    )

    async with ctx.db_session() as session:
        result = await session.execute(
            select(StreamlitApp).where(StreamlitApp.status == "building")
        )
        building_apps = result.scalars().all()

    marked = 0
    for app in building_apps:
        updated_at = app.updated_at
        if updated_at is None:
            continue
        if updated_at.tzinfo is None:
            updated_at = updated_at.replace(tzinfo=timezone.utc)
        if updated_at >= cutoff:
            continue
        logger.warning(
            "streamlit_id=%s stuck in building since %s, marking error",
            app.id,
            app.updated_at,
        )
        if await _mark_error(ctx, app.id):
            marked += 1
    return marked


async def _mark_error(ctx: WorkerContext, streamlit_id: UUID) -> bool:
    async with ctx.db_session() as session:
        result = await session.execute(
            select(StreamlitApp).where(StreamlitApp.id == streamlit_id)
        )
        app = result.scalar_one_or_none()
        if app is None:
            return False
        app.status = "error"
        await session.commit()
        logger.info("streamlit_id=%s marked as error", streamlit_id)
        return True


async def _mark_stopped(ctx: WorkerContext, streamlit_id: UUID) -> bool:
    if ctx.log_manager is not None:
        await ctx.log_manager.stop(streamlit_id)

    async with ctx.db_session() as session:
        result = await session.execute(
            select(StreamlitApp).where(StreamlitApp.id == streamlit_id)
        )
        app = result.scalar_one_or_none()
        if app is None:
            return False
        app.status = "stopped"
        app.container_id = None
        await session.commit()
        logger.info("streamlit_id=%s marked as stopped", streamlit_id)
        return True
