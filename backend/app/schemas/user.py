from __future__ import annotations

from pydantic import field_validator

from app.schemas.base import DisplayNameMixin, validate_login_field


class UserResponse(DisplayNameMixin):
    login: str
    email: str
    group: str
    is_admin: bool = False

    @field_validator("login", mode="before")
    @classmethod
    def _validate_login(cls, value: object) -> str:
        return validate_login_field(value)

    model_config = {"from_attributes": True, "extra": "forbid"}
