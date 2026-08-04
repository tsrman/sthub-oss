from __future__ import annotations

from typing import Self

from pydantic import BaseModel, Field, ValidationInfo, field_validator, model_validator

from app.core.validation import (
    get_max_file_size,
    get_max_requirements_size,
    validate_byte_length,
    validate_content_type,
)
from app.schemas.base import IdStr, UtcDatetime, validate_path_field


class _StreamlitFileContentMixin(BaseModel):
    """Enforce the stricter requirements.txt size limit when path is known.

    For schemas that include ``path`` (e.g. ``StreamlitFileRead``) the check
    uses the field directly. For request bodies without a ``path`` field
    (``StreamlitFileCreate``/``StreamlitFileUpdate``) callers must pass the
    URL path via ``ValidationInfo.context["path"]``.
    """

    @model_validator(mode="after")
    def _validate_requirements_size(self, info: ValidationInfo) -> Self:
        path = getattr(self, "path", None)
        if path is None:
            if info.context is None or "path" not in info.context:
                # Path is unknown at request-body validation time; the service
                # layer enforces the stricter requirements.txt size limit.
                return self
            path = info.context["path"]
        if path == "requirements.txt":
            validate_byte_length(self.content, get_max_requirements_size(), "content")
        return self


class StreamlitFileSummary(BaseModel):
    id: IdStr
    path: str
    content_type: str
    is_entrypoint: bool
    updated_at: UtcDatetime

    @field_validator("path", mode="before")
    @classmethod
    def _validate_path(cls, value: object) -> str:
        return validate_path_field(value)

    model_config = {"from_attributes": True, "extra": "forbid"}


class StreamlitFileCreate(_StreamlitFileContentMixin):
    content: str = Field(...)
    content_type: str | None = Field(default=None)

    model_config = {"extra": "forbid"}

    @field_validator("content", mode="before")
    @classmethod
    def _validate_content_size(cls, value: object) -> str:
        if not isinstance(value, str):
            raise ValueError("content must be a string")
        return validate_byte_length(value, get_max_file_size(), "content")

    @field_validator("content_type", mode="before")
    @classmethod
    def _validate_content_type(cls, value: object) -> str | None:
        if value is None:
            return None
        return validate_content_type(value)


# StreamlitFileUpdate and StreamlitFileCreate currently share the same shape,
# but they are defined independently so future divergences (e.g. optional partial
# updates) do not leak into creation.
class StreamlitFileUpdate(_StreamlitFileContentMixin):
    content: str = Field(...)
    content_type: str | None = Field(default=None)

    model_config = {"extra": "forbid"}

    @field_validator("content", mode="before")
    @classmethod
    def _validate_content_size(cls, value: object) -> str:
        if not isinstance(value, str):
            raise ValueError("content must be a string")
        return validate_byte_length(value, get_max_file_size(), "content")

    @field_validator("content_type", mode="before")
    @classmethod
    def _validate_content_type(cls, value: object) -> str | None:
        if value is None:
            return None
        return validate_content_type(value)


class StreamlitFileMetadata(BaseModel):
    id: IdStr
    path: str
    content_type: str
    is_entrypoint: bool

    @field_validator("path", mode="before")
    @classmethod
    def _validate_path(cls, value: object) -> str:
        return validate_path_field(value)

    model_config = {"from_attributes": True, "extra": "forbid"}


class StreamlitFileRead(_StreamlitFileContentMixin, StreamlitFileMetadata):
    """Full file representation returned by the API.

    Note:
        ``content`` is intended for text files only. Binary files should be
        served through a dedicated raw-bytes endpoint; this schema does not
        round-trip binary ``content_bytes`` as a string.
    """

    content: str = Field(...)
    updated_at: UtcDatetime

    @field_validator("content", mode="before")
    @classmethod
    def _validate_content_size(cls, value: object) -> str:
        if not isinstance(value, str):
            raise ValueError("content must be a string")
        return validate_byte_length(value, get_max_file_size(), "content")

    @field_validator("content_type", mode="before")
    @classmethod
    def _validate_content_type(cls, value: object) -> str:
        return validate_content_type(value)

    model_config = {"from_attributes": True, "extra": "forbid"}


class StreamlitFileListResponse(BaseModel):
    items: list[StreamlitFileSummary]
    total: int = Field(ge=0)

    model_config = {"from_attributes": True, "extra": "forbid"}


# Alias matching the API contract name used by the files router.
StreamlitFilesResponse = StreamlitFileListResponse
