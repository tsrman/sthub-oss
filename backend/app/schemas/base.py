from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import (
    AfterValidator,
    AliasChoices,
    AwareDatetime,
    BaseModel,
    BeforeValidator,
    Field,
)

from app.core.validation import validate_file_path, validate_login


def _ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("Datetime must be timezone-aware")
    if value.utcoffset().total_seconds() != 0:  # type: ignore
        raise ValueError("Datetime must be in UTC")
    return value


UtcDatetime = Annotated[AwareDatetime, AfterValidator(_ensure_utc)]


class ErrorDetail(BaseModel):
    code: str = Field(pattern=r"^[a-z0-9_]+$")
    message: str
    details: dict | None = None

    model_config = {"from_attributes": True, "extra": "forbid"}


class ErrorResponse(BaseModel):
    error: ErrorDetail

    model_config = {"from_attributes": True, "extra": "forbid"}


class DisplayNameMixin(BaseModel):
    """Mixin that maps ``username`` to the contract field ``display_name``."""

    display_name: str = Field(
        serialization_alias="display_name",
        validation_alias=AliasChoices("username", "display_name"),
    )


def _id_to_str(value: object) -> str:
    if isinstance(value, UUID):
        return str(value)
    if not isinstance(value, str):
        raise ValueError(f"expected str or UUID, got {type(value).__name__}")
    if value == "":
        raise ValueError("id cannot be empty")
    return value


IdStr = Annotated[str, BeforeValidator(_id_to_str)]
"""String identifier that accepts slug-style IDs or UUIDs.

UUID objects are coerced to their canonical string representation.
Empty strings are rejected.
"""


def validate_login_field(value: object) -> str:
    """Validate a raw login value for Pydantic field validators."""
    if not isinstance(value, str):
        raise ValueError("login must be a string")
    return validate_login(value)


def validate_path_field(value: object) -> str:
    """Validate a raw file path value for Pydantic field validators."""
    if not isinstance(value, str):
        raise ValueError("path must be a string")
    return validate_file_path(value)


def strip_name_field(value: object) -> str | None:
    """Strip and validate a display name for Pydantic field validators.

    Accepts ``None`` so the helper can be reused for optional name fields.
    """
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("name must be a string")
    value = value.strip()
    if not value:
        raise ValueError("name cannot be empty")
    return value
