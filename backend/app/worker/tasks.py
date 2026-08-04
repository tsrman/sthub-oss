from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models.streamlit import StreamlitApp
from app.models.streamlit_file import StreamlitFile
from app.models.user import User
from app.worker.context import WorkerContext

logger = logging.getLogger("app.worker")


async def _load_app(ctx: WorkerContext, streamlit_id: UUID) -> StreamlitApp | None:
    async with ctx.db_session() as session:
        result = await session.execute(
            select(StreamlitApp).where(StreamlitApp.id == streamlit_id)
        )
        return result.scalar_one_or_none()


async def _load_files(ctx: WorkerContext, streamlit_id: UUID) -> dict[str, str | bytes]:
    async with ctx.db_session() as session:
        result = await session.execute(
            select(StreamlitFile).where(StreamlitFile.streamlit_id == streamlit_id)
        )
        files: dict[str, str | bytes] = {}
        for file in result.scalars().all():
            if file.content_text is not None:
                files[file.path] = file.content_text
            elif file.content_bytes is not None:
                files[file.path] = file.content_bytes
            else:
                files[file.path] = ""
        return files


async def _load_owner(ctx: WorkerContext, user_id: UUID) -> User | None:
    async with ctx.db_session() as session:
        result = await session.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()


_UNSET = object()


async def _update_status(
    ctx: WorkerContext,
    streamlit_id: UUID,
    status: str,
    container_id: str | None | object = _UNSET,
    image_tag: str | None | object = _UNSET,
) -> None:
    async with ctx.db_session() as session:
        result = await session.execute(
            select(StreamlitApp).where(StreamlitApp.id == streamlit_id)
        )
        app = result.scalar_one_or_none()
        if app is None:
            logger.warning(
                "streamlit_id=%s not found while updating status", streamlit_id
            )
            return
        app.status = status
        if container_id is not _UNSET:
            app.container_id = container_id  # type: ignore[assignment]
        if image_tag is not _UNSET:
            app.image_tag = image_tag  # type: ignore[assignment]
        await session.commit()


async def _record_build_log(
    ctx: WorkerContext,
    streamlit_id: UUID,
    stage: str,
    level: str,
    message: str,
) -> None:
    from app.models.streamlit_file import BuildLog

    async with ctx.db_session() as session:
        session.add(
            BuildLog(
                streamlit_id=streamlit_id,
                stage=stage,
                level=level,
                message=message,
            )
        )
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()


async def _record_build_logs(
    ctx: WorkerContext,
    streamlit_id: UUID,
    stage: str,
    level: str,
    messages: list[str],
) -> None:
    """Record multiple build-log lines in a single transaction."""
    if not messages:
        return
    from app.models.streamlit_file import BuildLog

    async with ctx.db_session() as session:
        session.add_all(
            [
                BuildLog(
                    streamlit_id=streamlit_id,
                    stage=stage,
                    level=level,
                    message=message,
                )
                for message in messages
            ]
        )
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()


async def handle_build_run(
    ctx: WorkerContext,
    streamlit_id: UUID,
) -> None:
    logger.info("handle_build_run streamlit_id=%s", streamlit_id)

    app = await _load_app(ctx, streamlit_id)
    if app is None:
        logger.error("streamlit_id=%s not found for build_run", streamlit_id)
        return

    files = await _load_files(ctx, streamlit_id)
    requirements = files.get("requirements.txt", "")
    if isinstance(requirements, bytes):
        requirements = requirements.decode("utf-8", errors="replace")

    owner = await _load_owner(ctx, app.user_id)
    if owner is None:
        logger.error("owner not found for streamlit_id=%s", streamlit_id)
        await _update_status(ctx, streamlit_id, "error")
        return

    await _update_status(ctx, streamlit_id, "building")

    docker = ctx.docker
    if docker is None:
        logger.error("docker manager not available")
        await _update_status(ctx, streamlit_id, "error")
        return

    build_result = await docker.build_image(
        streamlit_id,
        owner.login,
        app.slug,
        app.version,
        files,
        requirements,
    )

    stage = "build"
    await _record_build_logs(
        ctx, streamlit_id, stage, "info", build_result.get("logs") or []
    )

    if not build_result["success"]:
        logger.error(
            "build failed for streamlit_id=%s: %s", streamlit_id, build_result["error"]
        )
        await _record_build_log(
            ctx, streamlit_id, stage, "error", build_result["error"] or "build failed"
        )
        await _update_status(ctx, streamlit_id, "error")
        return

    image_tag = build_result["image_tag"]

    # Stop any existing container before running the new image.
    if app.container_id:
        await docker.stop_container(app.container_id)

    run_result = await docker.run_container(
        streamlit_id,
        owner.login,
        app.slug,
        app.version,
        app.cpu_limit,
        app.memory_limit_mb,
    )

    if not run_result["success"]:
        logger.error(
            "run failed for streamlit_id=%s: %s", streamlit_id, run_result["error"]
        )
        await _record_build_log(
            ctx, streamlit_id, "run", "error", run_result["error"] or "run failed"
        )
        await _update_status(ctx, streamlit_id, "error", image_tag=image_tag)
        return

    await _update_status(
        ctx,
        streamlit_id,
        "running",
        container_id=run_result["container_id"],
        image_tag=image_tag,
    )
    logger.info(
        "streamlit_id=%s is running container_id=%s image=%s",
        streamlit_id,
        run_result["container_id"],
        image_tag,
    )

    if ctx.log_manager is not None and run_result.get("container_id"):
        await ctx.log_manager.start(streamlit_id, run_result["container_id"])


async def handle_stop(
    ctx: WorkerContext,
    streamlit_id: UUID,
) -> None:
    logger.info("handle_stop streamlit_id=%s", streamlit_id)

    app = await _load_app(ctx, streamlit_id)
    if app is None:
        logger.warning("streamlit_id=%s not found for stop", streamlit_id)
        return

    docker = ctx.docker
    if docker is None:
        logger.error("docker manager not available")
        return

    if ctx.log_manager is not None:
        await ctx.log_manager.stop(streamlit_id)

    if app.container_id:
        stop_result = await docker.stop_container(app.container_id)
        if not stop_result.get("success", True):
            # The container could not be stopped/removed. Mark the app as
            # "error" (not "stopped") and keep container_id so the container
            # does not leak untracked; the reconciler/user can retry later.
            logger.error(
                "failed to stop container %s for streamlit_id=%s: %s",
                app.container_id,
                streamlit_id,
                stop_result.get("error"),
            )
            await _update_status(ctx, streamlit_id, "error")
            return

    await _update_status(ctx, streamlit_id, "stopped", container_id=None)


async def handle_remove(
    ctx: WorkerContext,
    streamlit_id: UUID,
    container_id: str | None,
    image_tag: str | None,
) -> None:
    logger.info(
        "handle_remove streamlit_id=%s container_id=%s image_tag=%s",
        streamlit_id,
        container_id,
        image_tag,
    )

    docker = ctx.docker
    if docker is None:
        logger.error("docker manager not available")
        return

    if ctx.log_manager is not None:
        await ctx.log_manager.stop(streamlit_id)

    if container_id:
        await docker.remove_container(container_id)
    if image_tag:
        await docker.remove_image(image_tag)
