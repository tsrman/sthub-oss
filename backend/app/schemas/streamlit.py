from __future__ import annotations

from typing import Literal

from pydantic import (
    AliasChoices,
    BaseModel,
    Field,
    ValidationInfo,
    field_validator,
    model_validator,
)

from app.core.validation import validate_slug
from app.schemas.base import (
    DisplayNameMixin,
    IdStr,
    UtcDatetime,
    strip_name_field,
    validate_login_field,
)

PYTHON_VERSION_PATTERN = r"^(3\.10|3\.11|3\.12)$"


class StreamlitCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    slug: str = Field(..., min_length=1, max_length=40)
    description: str | None = Field(default=None, max_length=5000)
    python_version: str = Field(
        default="3.11",
        pattern=PYTHON_VERSION_PATTERN,
    )
    cpu_limit: float = Field(
        default=1.0,
        ge=0.1,
        le=4.0,
    )
    memory_limit_mb: int = Field(
        default=512,
        ge=64,
        le=4096,
    )

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


class StreamlitUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    slug: str | None = Field(default=None, min_length=1, max_length=40)
    description: str | None = Field(default=None, max_length=5000)
    python_version: str | None = Field(
        default=None,
        pattern=PYTHON_VERSION_PATTERN,
    )
    cpu_limit: float | None = Field(
        default=None,
        ge=0.1,
        le=4.0,
    )
    memory_limit_mb: int | None = Field(
        default=None,
        ge=64,
        le=4096,
    )

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


class StreamlitOwner(DisplayNameMixin):
    login: str

    @field_validator("login", mode="before")
    @classmethod
    def _validate_login(cls, value: object) -> str:
        return validate_login_field(value)

    model_config = {"from_attributes": True, "extra": "forbid"}


class StreamlitSummary(BaseModel):
    id: IdStr
    name: str = Field(min_length=1, max_length=100)
    slug: str = Field(min_length=1, max_length=40)
    description: str | None = Field(default=None, max_length=5000)
    status: Literal["stopped", "building", "running", "error"]
    cpu_limit: float = Field(ge=0.1, le=4.0)
    memory_limit_mb: int = Field(ge=64, le=4096)
    python_version: str = Field(pattern=PYTHON_VERSION_PATTERN)
    url: str = Field(validation_alias=AliasChoices("url_path", "url"))
    public_url: str
    version: int = Field(ge=0)
    owner: StreamlitOwner
    created_at: UtcDatetime
    updated_at: UtcDatetime

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

    model_config = {"from_attributes": True, "extra": "forbid"}


class StreamlitDetail(StreamlitSummary):
    container_id: str | None = None
    image_tag: str | None = None

    model_config = {"from_attributes": True, "extra": "forbid"}


class StreamlitListResponse(BaseModel):
    items: list[StreamlitSummary]
    total: int = Field(ge=0)
    running: int = Field(ge=0)

    model_config = {"from_attributes": True, "extra": "forbid"}


class SlugCheckResponse(BaseModel):
    slug: str = Field(min_length=1, max_length=100)
    available: bool
    normalized: str = ""
    url: str

    @model_validator(mode="after")
    def _set_normalized(self) -> "SlugCheckResponse":
        self.normalized = validate_slug(self.slug)
        return self

    @model_validator(mode="after")
    def _check_url(self, info: ValidationInfo) -> "SlugCheckResponse":
        if not self.url.startswith("/st/"):
            raise ValueError("url must start with '/st/'")
        if not self.url.endswith(f"/{self.normalized}"):
            raise ValueError(f"url must end with '/{self.normalized}'")
        if info.context:
            login = info.context.get("login")
            if login is not None:
                expected = f"/st/{validate_login_field(login)}/{self.normalized}"
                if self.url != expected:
                    raise ValueError(
                        f"url must be exactly '/st/{login}/{self.normalized}'"
                    )
        return self

    model_config = {"from_attributes": True, "extra": "forbid"}


class RunResponse(BaseModel):
    id: IdStr
    status: Literal["stopped", "building", "running", "error"]
    version: int | None = None

    model_config = {"from_attributes": True, "extra": "forbid"}


class DeploymentActor(DisplayNameMixin):
    login: str

    model_config = {"from_attributes": True, "extra": "forbid"}


class DeploymentRead(BaseModel):
    id: IdStr
    ts: UtcDatetime
    kind: str = Field(min_length=1, max_length=20)
    version: int = Field(ge=0)
    result: str = Field(min_length=1, max_length=20)
    streamlit_name: str = Field(default="", min_length=0, max_length=100)
    streamlit_slug: str = Field(default="", min_length=0, max_length=63)
    actor: DeploymentActor

    model_config = {"from_attributes": True, "extra": "forbid"}


class DeploymentListResponse(BaseModel):
    items: list[DeploymentRead]

    model_config = {"from_attributes": True, "extra": "forbid"}
