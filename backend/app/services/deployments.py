from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.models.streamlit_file import Deployment


class DeploymentService:
    """Record and retrieve deployment lifecycle events for a streamlit app."""

    async def record(
        self,
        db: AsyncSession,
        streamlit_id: UUID,
        actor_id: UUID,
        kind: str,
        version: int,
        result: str,
    ) -> Deployment:
        deployment = Deployment(
            streamlit_id=streamlit_id,
            actor_id=actor_id,
            kind=kind,
            version=version,
            result=result,
        )
        db.add(deployment)
        await db.commit()
        await db.refresh(deployment)
        return deployment

    async def list_by_streamlit(
        self,
        db: AsyncSession,
        streamlit_id: UUID,
    ) -> list[Deployment]:
        result = await db.execute(
            select(Deployment)
            .options(joinedload(Deployment.actor))
            .where(Deployment.streamlit_id == streamlit_id)
            .order_by(Deployment.ts.desc())
        )
        return list(result.scalars().unique().all())
