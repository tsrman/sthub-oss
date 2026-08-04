import asyncio
import logging
from datetime import timedelta

from arq import cron
from arq.connections import RedisSettings

from app.config import get_settings
from app.db.session import AsyncSessionLocal
from app.worker.context import WorkerContext
from app.worker.docker import DockerManager

logger = logging.getLogger("app.worker")


async def startup(ctx):
    """Initialise worker-level resources."""
    settings = get_settings()
    docker = DockerManager(settings)
    from app.worker.log_streamer import LogStreamerManager

    log_manager = LogStreamerManager(None)  # type: ignore[arg-type]
    worker_ctx = WorkerContext(
        db=AsyncSessionLocal,
        settings=settings,
        docker=docker,
        log_manager=log_manager,
    )
    log_manager.ctx = worker_ctx
    ctx["worker_ctx"] = worker_ctx
    # Per-streamlit asyncio locks used to serialize tasks for the same
    # streamlit_id (see streamlit_task).
    ctx["streamlit_locks"] = {}
    try:
        await log_manager.start_for_running_apps()
    except Exception as exc:
        logger.warning("Could not resume runtime log streamers on startup: %s", exc)
    logger.info(
        "Worker started (queue=%s, max_jobs=%s, job_timeout=%s)",
        settings.ARQ_QUEUE_NAME,
        settings.WORKER_MAX_JOBS,
        settings.WORKER_JOB_TIMEOUT,
    )


async def shutdown(ctx):
    """Release worker-level resources."""
    worker_ctx: WorkerContext | None = ctx.get("worker_ctx")
    if worker_ctx is not None:
        if worker_ctx.log_manager is not None:
            for streamlit_id in list(worker_ctx.log_manager._tasks.keys()):
                await worker_ctx.log_manager.stop(streamlit_id)
        if worker_ctx.docker is not None:
            await worker_ctx.docker.close()
    logger.info("Worker shutdown complete")


async def streamlit_task(ctx, kind: str, streamlit_id: str, *args):
    """Dispatch streamlit jobs to the appropriate handler.

    All streamlit jobs are enqueued as ``streamlit_task`` with ``kind`` as the
    first argument.  Tasks for the same ``streamlit_id`` are serialized
    through a per-id :class:`asyncio.Lock` stored in the worker context (the
    worker is a single process, so an in-process lock is sufficient); tasks
    for different ids still run concurrently.
    """
    from uuid import UUID

    from app.worker.tasks import handle_build_run, handle_remove, handle_stop

    worker_ctx: WorkerContext = ctx["worker_ctx"]
    sid = UUID(streamlit_id)

    locks: dict[str, asyncio.Lock] = ctx.setdefault("streamlit_locks", {})
    lock = locks.setdefault(streamlit_id, asyncio.Lock())

    async with lock:
        if kind == "build_run":
            await handle_build_run(worker_ctx, sid)
        elif kind == "stop":
            await handle_stop(worker_ctx, sid)
        elif kind == "remove":
            container_id = args[0] if args else None
            image_tag = args[1] if len(args) > 1 else None
            await handle_remove(worker_ctx, sid, container_id, image_tag)
        else:
            ctx["logger"].error("unknown streamlit_task kind=%s", kind)


async def reconcile_cron(ctx) -> None:
    """Periodic cron job that reconciles Postgres state with Docker."""
    worker_ctx: WorkerContext = ctx["worker_ctx"]
    from app.worker.reconciler import reconcile_state

    await reconcile_state(worker_ctx)


class WorkerSettings:
    # arq reads these as plain class attributes, not descriptors.
    redis_settings = RedisSettings.from_dsn(get_settings().REDIS_URL)
    queue_name = get_settings().ARQ_QUEUE_NAME
    max_jobs = get_settings().WORKER_MAX_JOBS
    job_timeout = timedelta(seconds=get_settings().WORKER_JOB_TIMEOUT)

    functions = [streamlit_task]
    cron_jobs = [
        cron(reconcile_cron, minute={0, 30}),
    ]
    on_startup = startup
    on_shutdown = shutdown
