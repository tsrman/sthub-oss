from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.exceptions import QuotaExceededError
from app.models import StreamlitApp

logger = logging.getLogger(__name__)

RUNNING_STATUS = "running"


class QuotaService:
    """Enforces per-user running-apps quota.

    Note:
        Quota checks are point-in-time counts and do not prevent races between
        concurrent operations (e.g. two simultaneous start requests may both pass
        the check while the final running count exceeds the limit).
    """

    def __init__(self, max_running: int | None = None) -> None:
        settings = get_settings()
        self.max_running = (
            max_running
            if max_running is not None
            else settings.MAX_RUNNING_APPS_PER_USER
        )

    async def count_running(self, db: AsyncSession, user_id: UUID) -> int:
        """Return the number of running streamlit apps for a user."""
        stmt = (
            select(func.count(StreamlitApp.id))
            .where(StreamlitApp.user_id == user_id)
            .where(StreamlitApp.status == RUNNING_STATUS)
        )
        result = await db.execute(stmt)
        return result.scalar_one()

    async def check_running_quota(self, db: AsyncSession, user_id: UUID) -> None:
        """Raise QuotaExceededError if the user already reached the running limit."""
        count = await self.count_running(db, user_id)
        if count >= self.max_running:
            logger.warning(
                "Quota exceeded for user_id=%s: %s/%s",
                user_id,
                count,
                self.max_running,
            )
            raise QuotaExceededError(
                message=f"Running-app quota exceeded: {count}/{self.max_running}",
                limit=self.max_running,
                current=count,
            )
