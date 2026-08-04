from __future__ import annotations

from pydantic import AliasChoices, BaseModel, Field, field_validator

from app.core.validation import (
    MAX_CODE_SIZE,
    MAX_REQUIREMENTS_SIZE,
    validate_byte_length,
    validate_slug,
)
from app.schemas.base import (
    DisplayNameMixin,
    IdStr,
    UtcDatetime,
    strip_name_field,
    validate_login_field,
)
from app.schemas.streamlit import PYTHON_VERSION_PATTERN


def _legacy_resource_field(name: str):
    if name == "cpu_limit":
        return Field(
            default=None,
            ge=0.1,
            le=4.0,
            serialization_alias="cpu",
            validation_alias=AliasChoices("cpu", "cpu_limit"),
        )
    if name == "memory_limit_mb":
        return Field(
            default=None,
            ge=64,
            le=4096,
            serialization_alias="ram_gb",
            validation_alias=AliasChoices("ram_gb", "memory_limit_mb"),
        )
    if name == "python_version":
        return Field(
            default="3.11",
            pattern=PYTHON_VERSION_PATTERN,
            serialization_alias="python",
            validation_alias=AliasChoices("python", "python_version"),
        )
    raise ValueError(f"Unknown resource field: {name}")


class LegacyStreamlitOwner(DisplayNameMixin):
    login: str

    @field_validator("login", mode="before")
    @classmethod
    def _validate_login(cls, value: object) -> str:
        return validate_login_field(value)

    model_config = {"from_attributes": True}


class LegacyStreamlitCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    slug: str = Field(..., min_length=1, max_length=40)
    description: str | None = Field(default=None, max_length=5000)
    python_version: str = _legacy_resource_field("python_version")
    cpu_limit: float | None = _legacy_resource_field("cpu_limit")
    memory_limit_mb: int | None = _legacy_resource_field("memory_limit_mb")
    code: str | None = None
    requirements: str | None = None

    model_config = {"extra": "forbid"}

    @field_validator("name", mode="before")
    @classmethod
    def _strip_name(cls, value: object) -> str:
        return strip_name_field(value)

    @field_validator("slug", mode="before")
    @classmethod
    def _validate_slug(cls, value: object) -> str:
        if not isinstance(value, str):
            raise ValueError("slug must be a string")
        return validate_slug(value)

    @field_validator("code", mode="before")
    @classmethod
    def _validate_code_size(cls, value: object) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError("code must be a string")
        return validate_byte_length(value, MAX_CODE_SIZE, "code")

    @field_validator("requirements", mode="before")
    @classmethod
    def _validate_requirements_size(cls, value: object) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError("requirements must be a string")
        return validate_byte_length(value, MAX_REQUIREMENTS_SIZE, "requirements")


class LegacyStreamlitUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    slug: str | None = Field(default=None, min_length=1, max_length=40)
    description: str | None = Field(default=None, max_length=5000)
    python_version: str | None = Field(
        default=None,
        pattern=PYTHON_VERSION_PATTERN,
        serialization_alias="python",
        validation_alias=AliasChoices("python", "python_version"),
    )
    cpu_limit: float | None = _legacy_resource_field("cpu_limit")
    memory_limit_mb: int | None = _legacy_resource_field("memory_limit_mb")

    model_config = {"extra": "forbid"}

    @field_validator("name", mode="before")
    @classmethod
    def _strip_name(cls, value: object) -> str | None:
        return strip_name_field(value)

    @field_validator("slug", mode="before")
    @classmethod
    def _validate_slug(cls, value: object) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError("slug must be a string")
        return validate_slug(value)


class LegacyStreamlitResponse(BaseModel):
    id: IdStr
    name: str = Field(min_length=1, max_length=100)
    slug: str
    description: str | None = None
    status: str
    cpu_limit: float | None = _legacy_resource_field("cpu_limit")
    memory_limit_mb: int | None = _legacy_resource_field("memory_limit_mb")
    python_version: str = _legacy_resource_field("python_version")
    url: str = Field(
        serialization_alias="url",
        validation_alias=AliasChoices("url_path", "url"),
    )
    public_url: str
    version: int
    owner: LegacyStreamlitOwner
    created_at: UtcDatetime
    updated_at: UtcDatetime

    model_config = {"from_attributes": True}


class LegacyStreamlitListResponse(BaseModel):
    items: list[LegacyStreamlitResponse]
    total: int
    running: int

    model_config = {"from_attributes": True}
