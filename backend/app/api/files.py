from __future__ import annotations

import base64
import logging
import mimetypes
from typing import TYPE_CHECKING
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.dependencies import get_current_user_with_login
from app.models.user import User
from app.schemas.streamlit_file import (
    StreamlitFileCreate,
    StreamlitFileRead,
    StreamlitFileSummary,
    StreamlitFileUpdate,
    StreamlitFilesResponse,
)
from app.services.file_service import FileService
from app.services.streamlit_service import StreamlitService

if TYPE_CHECKING:
    from app.models.streamlit import StreamlitApp
    from app.models.streamlit_file import StreamlitFile

router = APIRouter(prefix="/streamlits/{app_id}/files", tags=["files"])
logger = logging.getLogger(__name__)

_BINARY_CONTENT_TYPE_PREFIXES = (
    "image/",
    "audio/",
    "video/",
    "font/",
    "application/pdf",
    "application/octet-stream",
)
_TEXT_CONTENT_TYPES = {
    "image/svg+xml",
}


def _is_binary_content_type(content_type: str) -> bool:
    return (
        content_type.startswith(_BINARY_CONTENT_TYPE_PREFIXES)
        and content_type not in _TEXT_CONTENT_TYPES
    )


def _decode_content(
    body: StreamlitFileCreate | StreamlitFileUpdate,
    path: str,
) -> str | bytes:
    """Return text content or base64-decoded bytes for binary uploads."""
    content_type = body.content_type
    if content_type is None:
        content_type = mimetypes.guess_type(path)[0] or "text/plain"

    if _is_binary_content_type(content_type):
        try:
            return base64.b64decode(body.content, validate=True)
        except Exception as exc:
            raise HTTPException(
                status_code=400,
                detail={
                    "code": "validation_error",
                    "message": "Binary content must be base64-encoded",
                },
            ) from exc

    return body.content


def _map_service_error(exc: ValueError) -> HTTPException:
    message = str(exc)
    if "exceeds limit" in message:
        return HTTPException(
            status_code=413,
            detail={"code": "file_too_large", "message": message},
        )
    if "File limit exceeded" in message:
        return HTTPException(
            status_code=409,
            detail={"code": "file_limit_exceeded", "message": message},
        )
    return HTTPException(
        status_code=400,
        detail={"code": "validation_error", "message": message},
    )


def _file_to_response(
    file: StreamlitFile, *, as_base64: bool = False
) -> StreamlitFileRead | Response:
    # StreamlitFile may be passed as an ORM instance; Response serializes bytes.
    if file.content_bytes is not None:
        if as_base64:
            return StreamlitFileRead(
                id=str(file.id),
                path=file.path,
                content_type=file.content_type,
                is_entrypoint=file.is_entrypoint,
                updated_at=file.updated_at,
                content=base64.b64encode(file.content_bytes).decode("ascii"),
            )
        return Response(
            content=file.content_bytes,
            media_type=file.content_type,
        )
    return StreamlitFileRead.model_validate(file)


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


@router.get("", response_model=StreamlitFilesResponse)
async def list_files(
    app_id: str,
    db: AsyncSession = Depends(get_db),
    current: tuple[UUID, str, User] = Depends(get_current_user_with_login),
):
    _, _, user = current
    await _get_app_or_404(app_id, user, db)
    files = await FileService().list_files(db, UUID(app_id))
    return StreamlitFilesResponse(
        items=[StreamlitFileSummary.model_validate(f) for f in files],
        total=len(files),
    )


@router.get("/{path:path}", response_model=StreamlitFileRead)
async def get_file(
    app_id: str,
    path: str,
    base64: bool = Query(False, description="Return binary content as base64 string"),
    db: AsyncSession = Depends(get_db),
    current: tuple[UUID, str, User] = Depends(get_current_user_with_login),
):
    _, _, user = current
    await _get_app_or_404(app_id, user, db)
    try:
        file = await FileService().get_file(db, UUID(app_id), path)
    except ValueError as exc:
        raise _map_service_error(exc) from exc
    if file is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "not_found", "message": "File not found"},
        )
    return _file_to_response(file, as_base64=base64)


@router.put("/{path:path}", response_model=StreamlitFileRead)
async def put_file(
    app_id: str,
    path: str,
    body: StreamlitFileCreate,
    db: AsyncSession = Depends(get_db),
    current: tuple[UUID, str, User] = Depends(get_current_user_with_login),
):
    _, _, user = current
    await _get_app_or_404(app_id, user, db)
    content = _decode_content(body, path)
    try:
        file = await FileService().save_file(
            db, UUID(app_id), path, content, body.content_type
        )
        await db.commit()
    except ValueError as exc:
        raise _map_service_error(exc) from exc
    return _file_to_response(file)


@router.patch("/{path:path}", response_model=StreamlitFileRead)
async def update_file(
    app_id: str,
    path: str,
    body: StreamlitFileUpdate,
    db: AsyncSession = Depends(get_db),
    current: tuple[UUID, str, User] = Depends(get_current_user_with_login),
):
    _, _, user = current
    await _get_app_or_404(app_id, user, db)
    content = _decode_content(body, path)
    try:
        file = await FileService().save_file(
            db, UUID(app_id), path, content, body.content_type
        )
        await db.commit()
    except ValueError as exc:
        raise _map_service_error(exc) from exc
    return _file_to_response(file)


@router.delete("/{path:path}", status_code=204)
async def delete_file(
    app_id: str,
    path: str,
    db: AsyncSession = Depends(get_db),
    current: tuple[UUID, str, User] = Depends(get_current_user_with_login),
) -> Response:
    _, _, user = current
    await _get_app_or_404(app_id, user, db)
    try:
        deleted = await FileService().delete_file(db, UUID(app_id), path)
        await db.commit()
    except ValueError as exc:
        raise _map_service_error(exc) from exc
    if not deleted:
        raise HTTPException(
            status_code=404,
            detail={"code": "not_found", "message": "File not found"},
        )
    return Response(status_code=204)
