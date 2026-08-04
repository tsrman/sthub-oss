from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class Problem(BaseModel):
    line: int = Field(..., ge=1)
    column: int = Field(..., ge=1)
    severity: Literal["error", "warning"]
    message: str
    code: str = ""

    model_config = {"from_attributes": True, "extra": "forbid"}
