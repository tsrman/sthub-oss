from __future__ import annotations

import logging
import mimetypes
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.core.validation import (
    validate_content_type,
    validate_file_path,
)
from app.models import StreamlitFile

logger = logging.getLogger(__name__)

REQUIRED_FILES = {"app.py", "requirements.txt"}


class FileService:
    """Storage and validation for Streamlit application files.

    Note:
        Enforcement of ``MAX_FILES_PER_STREAMLIT`` is point-in-time and
        best-effort under concurrency. Multiple concurrent save operations may
        briefly exceed the limit before the count is rechecked.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.max_file_size = self.settings.MAX_FILE_SIZE_BYTES
        self.max_requirements_size = self.settings.MAX_REQUIREMENTS_SIZE

    async def list_files(
        self,
        db: AsyncSession,
        streamlit_id: UUID,
    ) -> list[StreamlitFile]:
        """Return all files for a streamlit ordered by path."""
        stmt = (
            select(StreamlitFile)
            .where(StreamlitFile.streamlit_id == streamlit_id)
            .order_by(StreamlitFile.path)
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def get_file(
        self,
        db: AsyncSession,
        streamlit_id: UUID,
        path: str,
    ) -> StreamlitFile | None:
        """Return a single file by streamlit and path, or None."""
        # File paths are normalized to lowercase for consistency and to keep
        # required-file protection (app.py, requirements.txt) case-insensitive.
        path = validate_file_path(path.strip().lower())
        return await self._get_file_raw(db, streamlit_id, path)

    async def _get_file_raw(
        self,
        db: AsyncSession,
        streamlit_id: UUID,
        path: str,
    ) -> StreamlitFile | None:
        """Return a single file by streamlit and path, or None.

        The caller is responsible for validating ``path`` before calling this
        helper; no path validation is performed here.
        """
        stmt = (
            select(StreamlitFile)
            .where(StreamlitFile.streamlit_id == streamlit_id)
            .where(StreamlitFile.path == path)
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def save_file(
        self,
        db: AsyncSession,
        streamlit_id: UUID,
        path: str,
        content: str | bytes,
        content_type: str | None = None,
    ) -> StreamlitFile:
        """Create or replace a file."""
        # File paths are normalized to lowercase for consistency and to keep
        # required-file protection (app.py, requirements.txt) case-insensitive.
        path = validate_file_path(path.strip().lower())

        if path == "app.py" and isinstance(content, bytes):
            raise ValueError("app.py must be uploaded as UTF-8 text")

        if content_type is not None:
            content_type = validate_content_type(content_type)

        if isinstance(content, str):
            size = len(content.encode("utf-8"))
        else:
            size = len(content)

        max_size = (
            self.max_requirements_size
            if path == "requirements.txt"
            else self.max_file_size
        )
        if size > max_size:
            logger.warning(
                "File size limit exceeded for streamlit_id=%s path=%s size=%d max=%d",
                streamlit_id,
                path,
                size,
                max_size,
            )
            raise ValueError(f"File size {size} bytes exceeds limit {max_size} bytes")

        existing = await self._get_file_raw(db, streamlit_id, path)
        if existing is None:
            current_count = await self._count_files(db, streamlit_id)
            if current_count >= self.settings.MAX_FILES_PER_STREAMLIT:
                raise ValueError(
                    f"File limit exceeded for streamlit {streamlit_id}: "
                    f"{current_count}/{self.settings.MAX_FILES_PER_STREAMLIT}"
                )
            file = StreamlitFile(
                streamlit_id=streamlit_id,
                path=path,
            )
            db.add(file)
        else:
            file = existing

        file.is_entrypoint = path == "app.py"

        if isinstance(content, str):
            file.content_text = content
            file.content_bytes = None
            if content_type is None:
                guessed, _ = mimetypes.guess_type(path)
                content_type = guessed or "text/plain"
        else:
            file.content_text = None
            file.content_bytes = content
            if content_type is None:
                content_type = (
                    mimetypes.guess_type(path)[0] or "application/octet-stream"
                )

        file.content_type = content_type
        file.updated_at = datetime.now(timezone.utc)

        await db.flush()
        logger.info(
            "Saved file streamlit_id=%s path=%s size=%d content_type=%s",
            streamlit_id,
            path,
            size,
            content_type,
        )
        return file

    async def delete_file(
        self,
        db: AsyncSession,
        streamlit_id: UUID,
        path: str,
    ) -> bool:
        """Delete a file. Returns True if deleted, False if not found.

        Raises:
            ValueError: If the path is invalid or refers to a required file.
        """
        # File paths are normalized to lowercase for consistency and to keep
        # required-file protection (app.py, requirements.txt) case-insensitive.
        path = validate_file_path(path.strip().lower())
        if path in REQUIRED_FILES:
            logger.warning(
                "Attempted deletion of required file streamlit_id=%s path=%s",
                streamlit_id,
                path,
            )
            raise ValueError(f"Cannot delete required file: {path}")

        file = await self._get_file_raw(db, streamlit_id, path)
        if file is None:
            return False

        await db.delete(file)
        await db.flush()
        logger.info("Deleted file streamlit_id=%s path=%s", streamlit_id, path)
        return True

    async def get_entrypoint_content(
        self,
        db: AsyncSession,
        streamlit_id: UUID,
        entrypoint_path: str = "app.py",
    ) -> str | None:
        """Return the decoded text content of the entrypoint file."""
        file = await self.get_file(db, streamlit_id, entrypoint_path)
        if file is None:
            return None
        if file.content_text is not None:
            return file.content_text
        if file.content_bytes is not None:
            try:
                return file.content_bytes.decode("utf-8")
            except UnicodeDecodeError:
                return None
        return None

    async def _count_files(
        self,
        db: AsyncSession,
        streamlit_id: UUID,
    ) -> int:
        stmt = select(func.count(StreamlitFile.id)).where(
            StreamlitFile.streamlit_id == streamlit_id
        )
        result = await db.execute(stmt)
        return result.scalar_one()
