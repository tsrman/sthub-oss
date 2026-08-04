from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.config import get_settings
from app.core.validation import validate_slug
from app.db.session import AsyncSessionLocal, get_db
from app.dependencies import (
    get_current_user_with_login,
    get_current_user_with_login_for_sse,
)
from app.models.streamlit import StreamlitApp
from app.models.streamlit_file import BuildLog, StreamlitFile
from app.models.user import User
from app.schemas.lint import LintRequest, LintResponse
from app.schemas.problem import Problem
from app.schemas.streamlit import (
    DeploymentListResponse,
    DeploymentRead,
    RunResponse,
    SlugCheckResponse,
    StreamlitCreate,
    StreamlitDetail,
    StreamlitListResponse,
    StreamlitOwner,
    StreamlitSummary,
    StreamlitUpdate,
)
from app.services.deployments import DeploymentService
from app.services.file_service import FileService
from app.services.lint_service import LintService
from app.services.quota_service import QuotaService
from app.services.streamlit_service import StreamlitService
from app.services.worker_client import WorkerClient

router = APIRouter(prefix="/streamlits", tags=["streamlits"])
logger = logging.getLogger(__name__)

_STATUS_QUERY_VALUES = {"stopped", "building", "running", "error"}
_RUNTIME_FIELDS = {"slug", "python_version", "cpu_limit", "memory_limit_mb"}
_MUTABLE_FIELDS = (
    "name",
    "slug",
    "description",
    "python_version",
    "cpu_limit",
    "memory_limit_mb",
    "status",
    "version",
)
_MAX_SLUG_LEN = 40


def _owner(login: str, display_name: str) -> StreamlitOwner:
    return StreamlitOwner(login=login, display_name=display_name)


async def _record_deployment(
    db: AsyncSession,
    app: StreamlitApp,
    user: User,
    kind: str,
    result: str,
) -> None:
    """Persist a deployment lifecycle event for auditing/history."""
    service = DeploymentService()
    await service.record(db, app.id, user.id, kind, app.version, result)


def _url_path(login: str, slug: str) -> str:
    return f"/st/{login}/{slug}"


def _public_url(url_path: str) -> str:
    base = get_settings().PUBLIC_HOST.rstrip("/")
    return f"{base}{url_path}" if base else url_path


def _summary(app: StreamlitApp) -> StreamlitSummary:
    owner = app.owner
    url_path = _url_path(owner.login, app.slug)
    return StreamlitSummary(
        id=str(app.id),
        name=app.name,
        slug=app.slug,
        description=app.description,
        status=app.status,  # type: ignore[arg-type]
        cpu_limit=app.cpu_limit,
        memory_limit_mb=app.memory_limit_mb,
        python_version=app.python_version,
        url=url_path,
        public_url=_public_url(url_path),
        version=app.version,
        owner=_owner(owner.login, owner.username),
        created_at=app.created_at,
        updated_at=app.updated_at,
    )


def _detail(app: StreamlitApp, login: str, display_name: str) -> StreamlitDetail:
    url_path = _url_path(login, app.slug)
    return StreamlitDetail(
        id=str(app.id),
        name=app.name,
        slug=app.slug,
        description=app.description,
        status=app.status,  # type: ignore[arg-type]
        cpu_limit=app.cpu_limit,
        memory_limit_mb=app.memory_limit_mb,
        python_version=app.python_version,
        url=url_path,
        public_url=_public_url(url_path),
        version=app.version,
        container_id=app.container_id,
        image_tag=app.image_tag,
        owner=_owner(login, display_name),
        created_at=app.created_at,
        updated_at=app.updated_at,
    )


async def _get_app_or_404(
    app_id: str,
    user: User,
    db: AsyncSession,
) -> StreamlitApp:
    """Fetch a streamlit app by id and return it, converting ValueError to 404.

    Admins can access any streamlit; regular users only their own.
    """
    service = StreamlitService()
    try:
        return await service.get_or_404(db, UUID(app_id), user.id, user.is_admin)
    except ValueError as exc:
        raise HTTPException(
            status_code=404,
            detail={"code": "not_found", "message": "Streamlit not found"},
        ) from exc


@router.get("", response_model=StreamlitListResponse)
async def list_streamlits(
    status: str | None = Query(None),
    q: str | None = Query(None),
    owner: str | None = Query(None, description="Filter by owner login (admins only)"),
    db: AsyncSession = Depends(get_db),
    current: tuple[UUID, str, User] = Depends(get_current_user_with_login),
):
    user_id, _, user = current

    if status is not None and status not in _STATUS_QUERY_VALUES:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "validation_error",
                "message": f"Invalid status filter: {status}",
            },
        )

    is_admin = user.is_admin
    base_filter = True if is_admin else StreamlitApp.user_id == user_id

    total_stmt = select(func.count(StreamlitApp.id)).where(base_filter)
    query = (
        select(StreamlitApp).options(joinedload(StreamlitApp.owner)).where(base_filter)
    )

    if is_admin and owner:
        total_stmt = total_stmt.join(StreamlitApp.owner).where(User.login == owner)
        query = query.join(StreamlitApp.owner).where(User.login == owner)

    if status:
        total_stmt = total_stmt.where(StreamlitApp.status == status)
        query = query.where(StreamlitApp.status == status)
    if q:
        escaped = q.replace("%", r"\%").replace("_", r"\_")
        pattern = f"%{escaped}%"
        total_stmt = total_stmt.where(
            (StreamlitApp.name.ilike(pattern, escape="\\"))
            | (StreamlitApp.slug.ilike(pattern, escape="\\"))
        )
        query = query.where(
            (StreamlitApp.name.ilike(pattern, escape="\\"))
            | (StreamlitApp.slug.ilike(pattern, escape="\\"))
        )

    total = (await db.execute(total_stmt)).scalar_one()

    result = await db.execute(query.order_by(StreamlitApp.updated_at.desc()))
    apps = result.scalars().unique().all()

    running_stmt = (
        select(func.count(StreamlitApp.id))
        .where(base_filter)
        .where(StreamlitApp.status == "running")
    )
    if is_admin and owner:
        running_stmt = running_stmt.join(StreamlitApp.owner).where(User.login == owner)
    running = (await db.execute(running_stmt)).scalar_one()

    return StreamlitListResponse(
        items=[_summary(a) for a in apps],
        total=total,
        running=running,
    )


@router.post("", response_model=StreamlitDetail, status_code=201)
async def create_streamlit(
    body: StreamlitCreate,
    db: AsyncSession = Depends(get_db),
    current: tuple[UUID, str, User] = Depends(get_current_user_with_login),
):
    user_id, login, user = current
    slug = validate_slug(body.slug)

    existing = await db.execute(
        select(StreamlitApp).where(
            StreamlitApp.user_id == user_id,
            StreamlitApp.slug == slug,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=409,
            detail={
                "code": "slug_taken",
                "message": "Slug already exists for this user",
            },
        )

    app = StreamlitApp(
        user_id=user_id,
        name=body.name,
        slug=slug,
        description=body.description,
        python_version=body.python_version,
        cpu_limit=body.cpu_limit,
        memory_limit_mb=body.memory_limit_mb,
        status="stopped",
        version=0,
    )
    db.add(app)
    await db.flush()

    fs = FileService()
    await fs.save_file(
        db,
        app.id,
        "app.py",
        'import streamlit as st\n\nst.write("Hello!")',
        "text/x-python",
    )
    await fs.save_file(db, app.id, "requirements.txt", "", "text/plain")

    await db.commit()
    await db.refresh(app)
    logger.info(
        "Created streamlit app_id=%s user_id=%s status=%s slug=%s",
        app.id,
        user_id,
        app.status,
        app.slug,
    )
    return _detail(app, login, user.username)


@router.get("/check-slug", response_model=SlugCheckResponse)
async def check_slug(
    slug: str,
    exclude_id: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current: tuple[UUID, str, User] = Depends(get_current_user_with_login),
):
    user_id, login, _ = current
    try:
        normalized = validate_slug(slug)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail={"code": "validation_error", "message": str(exc)},
        ) from exc

    query = select(StreamlitApp).where(
        StreamlitApp.user_id == user_id,
        StreamlitApp.slug == normalized,
    )
    if exclude_id:
        try:
            query = query.where(StreamlitApp.id != UUID(exclude_id))
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail={
                    "code": "validation_error",
                    "message": f"Invalid exclude_id: {exclude_id}",
                },
            ) from exc
    result = await db.execute(query)
    taken = result.scalar_one_or_none() is not None

    url_path = _url_path(login, normalized)

    return SlugCheckResponse(
        slug=slug,
        normalized=normalized,
        available=not taken,
        url=url_path,
    )


@router.get("/{app_id}", response_model=StreamlitDetail)
async def get_streamlit(
    app_id: str,
    db: AsyncSession = Depends(get_db),
    current: tuple[UUID, str, User] = Depends(get_current_user_with_login),
):
    user_id, login, user = current
    app = await _get_app_or_404(app_id, user, db)
    return _detail(app, login, user.username)


@router.patch("/{app_id}", response_model=StreamlitDetail)
async def update_streamlit(
    app_id: str,
    body: StreamlitUpdate,
    db: AsyncSession = Depends(get_db),
    current: tuple[UUID, str, User] = Depends(get_current_user_with_login),
):
    user_id, login, user = current
    app = await _get_app_or_404(app_id, user, db)

    data = body.model_dump(exclude_unset=True)

    if app.status == "building" and _RUNTIME_FIELDS & data.keys():
        raise HTTPException(
            status_code=409,
            detail={
                "code": "invalid_state",
                "message": "Cannot change runtime settings while building",
            },
        )

    snapshot = {field: getattr(app, field) for field in _MUTABLE_FIELDS}

    if "slug" in data and data["slug"] != snapshot["slug"]:
        new_slug = validate_slug(data["slug"])
        existing = await db.execute(
            select(StreamlitApp).where(
                StreamlitApp.user_id == user_id,
                StreamlitApp.slug == new_slug,
                StreamlitApp.id != app.id,
            )
        )
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=409,
                detail={"code": "slug_taken", "message": "Slug already taken"},
            )
        app.slug = new_slug

    for field, value in data.items():
        if field == "slug":
            continue
        setattr(app, field, value)

    restart_required = any(
        field in _RUNTIME_FIELDS and field in data and data[field] != snapshot[field]
        for field in data
    )

    if app.status == "running" and restart_required:
        app.version = snapshot["version"] + 1
        app.status = "building"
        await db.commit()
        await db.refresh(app)

        client = WorkerClient()
        try:
            await client.enqueue_build_run(app.id)
        except Exception:
            for field, value in snapshot.items():
                setattr(app, field, value)
            await db.commit()
            raise HTTPException(
                status_code=500,
                detail={
                    "code": "internal_error",
                    "message": "Failed to enqueue worker task",
                },
            )
    else:
        await db.commit()
        await db.refresh(app)

    logger.info(
        "Updated streamlit app_id=%s user_id=%s status=%s version=%s",
        app.id,
        user_id,
        app.status,
        app.version,
    )
    return _detail(app, login, user.username)


@router.delete("/{app_id}", status_code=204)
async def delete_streamlit(
    app_id: str,
    db: AsyncSession = Depends(get_db),
    current: tuple[UUID, str, User] = Depends(get_current_user_with_login),
) -> Response:
    user_id, _, user = current
    app = await _get_app_or_404(app_id, user, db)

    # Enqueue first: only a successfully scheduled remove justifies the
    # "delete completed" history entry and the row deletion below.
    client = WorkerClient()
    try:
        await client.enqueue_remove(app.id, app.container_id, app.image_tag)
    except Exception:
        raise HTTPException(
            status_code=500,
            detail={
                "code": "internal_error",
                "message": "Failed to enqueue worker task",
            },
        )

    await _record_deployment(db, app, user, "delete", "completed")

    await db.delete(app)
    await db.commit()
    logger.info(
        "Deleted streamlit app_id=%s user_id=%s status=%s",
        app.id,
        user_id,
        app.status,
    )
    return Response(status_code=204)


@router.post("/{app_id}/run", response_model=RunResponse, status_code=202)
async def run_streamlit(
    app_id: str,
    db: AsyncSession = Depends(get_db),
    current: tuple[UUID, str, User] = Depends(get_current_user_with_login),
):
    user_id, login, user = current
    app = await _get_app_or_404(app_id, user, db)

    if app.status == "running" and app.container_id:
        return RunResponse(id=str(app.id), status="running", version=app.version)

    if app.status == "building":
        raise HTTPException(
            status_code=409,
            detail={"code": "invalid_state", "message": "Already building"},
        )

    quota = QuotaService()
    await quota.check_running_quota(db, user_id)

    original_status = app.status
    original_version = app.version
    app.version += 1
    app.status = "building"
    await db.commit()
    await db.refresh(app)

    client = WorkerClient()
    try:
        await client.enqueue_build_run(app.id)
    except Exception:
        app.status = original_status
        app.version = original_version
        await db.commit()
        raise HTTPException(
            status_code=500,
            detail={
                "code": "internal_error",
                "message": "Failed to enqueue worker task",
            },
        )

    await _record_deployment(db, app, user, "run", "started")

    logger.info(
        "Ran streamlit app_id=%s user_id=%s status=%s version=%s",
        app.id,
        user_id,
        app.status,
        app.version,
    )
    return RunResponse(id=str(app.id), status="building", version=app.version)


@router.post("/{app_id}/stop", response_model=RunResponse, status_code=202)
async def stop_streamlit(
    app_id: str,
    db: AsyncSession = Depends(get_db),
    current: tuple[UUID, str, User] = Depends(get_current_user_with_login),
):
    user_id, _, user = current
    app = await _get_app_or_404(app_id, user, db)

    if app.status == "stopped":
        return RunResponse(id=str(app.id), status="stopped", version=app.version)

    original_status = app.status
    app.status = "stopped"
    await db.commit()
    await db.refresh(app)

    client = WorkerClient()
    try:
        await client.enqueue_stop(app.id)
    except Exception:
        app.status = original_status
        await db.commit()
        raise HTTPException(
            status_code=500,
            detail={
                "code": "internal_error",
                "message": "Failed to enqueue worker task",
            },
        )

    await _record_deployment(db, app, user, "stop", "completed")

    logger.info(
        "Stopped streamlit app_id=%s user_id=%s status=%s version=%s",
        app.id,
        user_id,
        app.status,
        app.version,
    )
    return RunResponse(id=str(app.id), status="stopped", version=app.version)


@router.post("/{app_id}/restart", response_model=RunResponse, status_code=202)
async def restart_streamlit(
    app_id: str,
    db: AsyncSession = Depends(get_db),
    current: tuple[UUID, str, User] = Depends(get_current_user_with_login),
):
    user_id, _, user = current
    app = await _get_app_or_404(app_id, user, db)

    if app.status == "building":
        raise HTTPException(
            status_code=409,
            detail={"code": "invalid_state", "message": "Already building"},
        )

    original_status = app.status
    original_version = app.version
    app.version += 1
    app.status = "building"
    await db.commit()
    await db.refresh(app)

    client = WorkerClient()
    try:
        await client.enqueue_build_run(app.id)
    except Exception:
        app.status = original_status
        app.version = original_version
        await db.commit()
        raise HTTPException(
            status_code=500,
            detail={
                "code": "internal_error",
                "message": "Failed to enqueue worker task",
            },
        )

    await _record_deployment(db, app, user, "restart", "started")

    logger.info(
        "Restarted streamlit app_id=%s user_id=%s status=%s version=%s",
        app.id,
        user_id,
        app.status,
        app.version,
    )
    return RunResponse(id=str(app.id), status="building", version=app.version)


def _copy_slug(base: str, suffix: str) -> str:
    """Build a copy slug candidate that stays within length limits."""
    max_base_len = _MAX_SLUG_LEN - len(suffix)
    if max_base_len < 1:
        raise ValueError("Cannot form a valid copy slug: base too long")
    trimmed = base[:max_base_len].rstrip("-")
    candidate = f"{trimmed}{suffix}"
    return validate_slug(candidate)


async def _generate_duplicate_slug(
    db: AsyncSession,
    user_id: UUID,
    base_slug: str,
) -> str:
    """Generate a unique slug for a duplicated app."""
    suffixes = ["-copy"] + [f"-copy-{i}" for i in range(1, 1000)]
    for suffix in suffixes:
        candidate = _copy_slug(base_slug, suffix)
        existing = await db.execute(
            select(StreamlitApp).where(
                StreamlitApp.user_id == user_id,
                StreamlitApp.slug == candidate,
            )
        )
        if existing.scalar_one_or_none() is None:
            return candidate
    raise HTTPException(
        status_code=500,
        detail={
            "code": "internal_error",
            "message": "Unable to generate a unique copy slug",
        },
    )


@router.post("/{app_id}/duplicate", response_model=StreamlitDetail, status_code=201)
async def duplicate_streamlit(
    app_id: str,
    db: AsyncSession = Depends(get_db),
    current: tuple[UUID, str, User] = Depends(get_current_user_with_login),
):
    user_id, login, user = current
    app = await _get_app_or_404(app_id, user, db)

    new_slug = await _generate_duplicate_slug(db, user_id, app.slug)
    copy_suffix = " (copy)"
    max_name_len = 100
    if len(app.name) + len(copy_suffix) > max_name_len:
        truncated_name = app.name[: max_name_len - len(copy_suffix)]
        new_name = f"{truncated_name}{copy_suffix}"
    else:
        new_name = f"{app.name}{copy_suffix}"

    new_app = StreamlitApp(
        user_id=user_id,
        name=new_name,
        slug=new_slug,
        description=app.description,
        python_version=app.python_version,
        cpu_limit=app.cpu_limit,
        memory_limit_mb=app.memory_limit_mb,
        status="stopped",
        version=0,
    )
    db.add(new_app)
    await db.flush()

    files_result = await db.execute(
        select(StreamlitFile).where(StreamlitFile.streamlit_id == app.id)
    )
    for src in files_result.scalars().all():
        db.add(
            StreamlitFile(
                streamlit_id=new_app.id,
                path=src.path,
                content_type=src.content_type,
                content_text=src.content_text,
                content_bytes=src.content_bytes,
                is_entrypoint=src.is_entrypoint,
            )
        )

    await db.commit()
    await db.refresh(new_app)
    logger.info(
        "Duplicated streamlit original_app_id=%s new_app_id=%s user_id=%s status=%s",
        app.id,
        new_app.id,
        user_id,
        new_app.status,
    )
    return _detail(new_app, login, user.username)


# ---------------------------------------------------------------------------
# Build logs (Server-Sent Events)
# ---------------------------------------------------------------------------

_SSE_POLL_INTERVAL = 1.0
_SSE_PING_INTERVAL = 15.0


async def _stream_build_logs(
    streamlit_id: UUID,
) -> AsyncIterator[str]:
    """Poll build logs from the DB and yield SSE ``data:`` lines."""
    last_ts: datetime | None = None
    last_id: UUID | None = None
    ping_every = max(1, int(_SSE_PING_INTERVAL / _SSE_POLL_INTERVAL))
    ping_counter = 0

    while True:
        async with AsyncSessionLocal() as db:
            query = (
                select(BuildLog)
                .where(BuildLog.streamlit_id == streamlit_id)
                .order_by(BuildLog.ts.asc(), BuildLog.id.asc())
            )
            if last_ts is not None and last_id is not None:
                query = query.where(
                    ((BuildLog.ts == last_ts) & (BuildLog.id > last_id))
                    | (BuildLog.ts > last_ts)
                )

            result = await db.execute(query)
            for log in result.scalars().all():
                payload = json.dumps(
                    {
                        "time": log.ts.isoformat(),
                        "level": log.level,
                        "src": log.stage,
                        "msg": log.message,
                    },
                    ensure_ascii=False,
                )
                yield f"data: {payload}\n\n"
                last_ts = log.ts
                last_id = log.id

        ping_counter += 1
        if ping_counter >= ping_every:
            yield ":ping\n\n"
            ping_counter = 0
        await asyncio.sleep(_SSE_POLL_INTERVAL)


async def _snapshot_build_logs(
    db: AsyncSession,
    streamlit_id: UUID,
) -> AsyncIterator[str]:
    """Yield all stored build logs once and then stop."""
    result = await db.execute(
        select(BuildLog)
        .where(BuildLog.streamlit_id == streamlit_id)
        .order_by(BuildLog.ts.asc(), BuildLog.id.asc())
    )
    for log in result.scalars().all():
        payload = json.dumps(
            {
                "time": log.ts.isoformat(),
                "level": log.level,
                "src": log.stage,
                "msg": log.message,
            },
            ensure_ascii=False,
        )
        yield f"data: {payload}\n\n"


@router.get("/{app_id}/logs")
async def stream_build_logs(
    app_id: str,
    follow: bool = Query(True, description="Keep connection open and stream new logs"),
    db: AsyncSession = Depends(get_db),
    current: tuple[UUID, str, User] = Depends(get_current_user_with_login_for_sse),
):
    """Stream build/run logs for a streamlit app as SSE.

    The endpoint accepts the JWT via the ``Authorization`` header or as a
    ``?token=`` query parameter so that browser ``EventSource`` can be used.
    """
    _, _, user = current
    await _get_app_or_404(app_id, user, db)

    stream = (
        _stream_build_logs(UUID(app_id))
        if follow
        else _snapshot_build_logs(db, UUID(app_id))
    )
    return StreamingResponse(
        stream,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ---------------------------------------------------------------------------
# Deployment history
# ---------------------------------------------------------------------------


@router.get("/{app_id}/deployments", response_model=DeploymentListResponse)
async def list_deployments(
    app_id: str,
    db: AsyncSession = Depends(get_db),
    current: tuple[UUID, str, User] = Depends(get_current_user_with_login),
):
    """Return the deployment/action history for a streamlit app."""
    _, _, user = current
    await _get_app_or_404(app_id, user, db)

    service = DeploymentService()
    deployments = await service.list_by_streamlit(db, UUID(app_id))
    return DeploymentListResponse(
        items=[DeploymentRead.model_validate(d) for d in deployments]
    )


@router.post("/{app_id}/lint", response_model=LintResponse)
async def lint_streamlit(
    app_id: str,
    body: LintRequest,
    db: AsyncSession = Depends(get_db),
    current: tuple[UUID, str, User] = Depends(get_current_user_with_login),
):
    """Check Python syntax for code associated with a streamlit app.

    Verifies the caller can access the app before running the linter.
    """
    _, _, user = current
    await _get_app_or_404(app_id, user, db)

    errors = await LintService().check_syntax(body.code)
    return LintResponse(
        ok=len(errors) == 0,
        problems=[Problem(**e) for e in errors],
    )
