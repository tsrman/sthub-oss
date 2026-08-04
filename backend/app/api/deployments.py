from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.db.session import get_db
from app.dependencies import get_current_user_with_login
from app.models.streamlit import StreamlitApp
from app.models.streamlit_file import Deployment
from app.models.user import User
from app.schemas.streamlit import DeploymentListResponse, DeploymentRead

router = APIRouter(prefix="/deployments", tags=["deployments"])


@router.get("", response_model=DeploymentListResponse)
async def list_my_deployments(
    db: AsyncSession = Depends(get_db),
    current: tuple[UUID, str, User] = Depends(get_current_user_with_login),
):
    """Return deployment history for all streamlits owned by the current user."""
    user_id, _, _ = current
    result = await db.execute(
        select(Deployment, StreamlitApp.name, StreamlitApp.slug)
        .options(joinedload(Deployment.actor))
        .join(StreamlitApp, Deployment.streamlit_id == StreamlitApp.id)
        .where(StreamlitApp.user_id == user_id)
        .order_by(Deployment.ts.desc())
    )
    items = []
    for deployment, app_name, app_slug in result.all():
        data = DeploymentRead.model_validate(deployment)
        data.streamlit_name = app_name
        data.streamlit_slug = app_slug
        items.append(data)
    return DeploymentListResponse(items=items)
