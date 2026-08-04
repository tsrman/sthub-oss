from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from app.core.validation import MAX_CODE_SIZE, validate_byte_length
from app.schemas.problem import Problem


class LintRequest(BaseModel):
    code: str = Field(...)

    model_config = {"extra": "forbid"}

    @field_validator("code", mode="before")
    @classmethod
    def _validate_code_size(cls, value: object) -> str:
        if not isinstance(value, str):
            raise ValueError("code must be a string")
        return validate_byte_length(value, MAX_CODE_SIZE, "code")


class LintResponse(BaseModel):
    ok: bool
    problems: list[Problem] = Field(default_factory=list)

    model_config = {"from_attributes": True, "extra": "forbid"}
