from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from app.core.validation import (
    MAX_CODE_SIZE,
    MAX_REQUIREMENTS_SIZE,
    validate_byte_length,
)
from app.schemas.base import strip_name_field


class Template(BaseModel):
    id: str
    name: str = Field(min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=5000)
    badge: str | None = Field(default=None)
    tags: list[str] = Field(default_factory=list)
    code: str = Field(...)
    requirements: str = Field(...)

    @field_validator("name", mode="before")
    @classmethod
    def _strip_name(cls, value: object) -> str:
        return strip_name_field(value)

    @field_validator("code", mode="before")
    @classmethod
    def _validate_code_size(cls, value: object) -> str:
        if not isinstance(value, str):
            raise ValueError("code must be a string")
        return validate_byte_length(value, MAX_CODE_SIZE, "code")

    @field_validator("requirements", mode="before")
    @classmethod
    def _validate_requirements_size(cls, value: object) -> str:
        if not isinstance(value, str):
            raise ValueError("requirements must be a string")
        return validate_byte_length(value, MAX_REQUIREMENTS_SIZE, "requirements")

    model_config = {"from_attributes": True, "extra": "forbid"}


class TemplateListResponse(BaseModel):
    items: list[Template]

    model_config = {"from_attributes": True, "extra": "forbid"}
