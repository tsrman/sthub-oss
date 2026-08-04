from __future__ import annotations

from typing import Literal

from pydantic import AliasChoices, BaseModel, Field

from app.schemas.base import UtcDatetime


class LogLine(BaseModel):
    ts: UtcDatetime
    level: Literal["DEBUG", "INFO", "WARNING", "ERROR"]
    source: str = Field(
        validation_alias=AliasChoices("stage", "source"),
        serialization_alias="source",
    )
    message: str

    model_config = {"from_attributes": True, "extra": "forbid"}


class LogListResponse(BaseModel):
    items: list[LogLine]
    next_since: UtcDatetime | None = None

    model_config = {"from_attributes": True, "extra": "forbid"}
