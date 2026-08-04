"""Runtime context shared by arq worker tasks."""

from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING, AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

if TYPE_CHECKING:
    from app.config import Settings
    from app.worker.docker import DockerManager
    from app.worker.log_streamer import LogStreamerManager


@dataclass
class WorkerContext:
    """Holds resources needed by worker task handlers.

    Tasks obtain a database session through :meth:`db_session`, which handles
    commit/rollback automatically.
    """

    db: async_sessionmaker[AsyncSession]
    settings: "Settings"
    docker: "DockerManager | None" = None
    log_manager: "LogStreamerManager | None" = None

    @asynccontextmanager
    async def db_session(self) -> AsyncIterator[AsyncSession]:
        """Provide an async SQLAlchemy session with automatic commit/rollback."""
        session = self.db()
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        else:
            await session.commit()
        finally:
            await session.close()
