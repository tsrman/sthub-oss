from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends

from app.auth.keycloak import get_first_allowed_group
from app.config import get_settings
from app.dependencies import get_current_user_with_login_and_claims
from app.models.user import User
from app.schemas.user import UserResponse

router = APIRouter(tags=["users"])


@router.get("/me", response_model=UserResponse)
async def get_me(
    current: tuple[UUID, str, User, dict[str, Any]] = Depends(
        get_current_user_with_login_and_claims
    ),
):
    _user_id, _login, user, claims = current

    group = get_first_allowed_group(claims, get_settings().allowed_groups_list) or ""

    return UserResponse(
        login=user.login,
        display_name=user.username,
        email=user.email or "",
        group=group,
        is_admin=bool(user.is_admin),
    )
