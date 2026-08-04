from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.streamlit import StreamlitApp
from app.services.lint_service import LintService


class StreamlitService:
    def __init__(self, lint_service: LintService | None = None):
        self.lint = lint_service or LintService()

    def validate_requirements(self, requirements: str) -> tuple[bool, list[str]]:
        return self.lint.validate_requirements(requirements)

    async def check_syntax(self, code: str) -> list[dict[str, Any]]:
        return await self.lint.check_syntax(code)

    async def get_or_404(
        self,
        db: AsyncSession,
        app_id: UUID,
        user_id: UUID,
        is_admin: bool = False,
    ) -> StreamlitApp:
        filters = [StreamlitApp.id == app_id]
        if not is_admin:
            filters.append(StreamlitApp.user_id == user_id)
        result = await db.execute(select(StreamlitApp).where(*filters))
        app = result.scalar_one_or_none()
        if not app:
            raise ValueError("Streamlit not found")
        return app
