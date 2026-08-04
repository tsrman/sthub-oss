from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.base import IdStr, UtcDatetime
from app.schemas.streamlit import StreamlitOwner


# NOTE: HistoryEvent is primarily constructed from a dict in the service layer.
# `from_attributes` is enabled to follow the shared response convention, but
# the ORM Deployment model lacks `action`, `streamlit_name`, and `url`, so
# attribute-based construction is not expected in practice.
class HistoryEvent(BaseModel):
    id: IdStr
    ts: UtcDatetime
    streamlit_id: IdStr
    streamlit_name: str
    url: str
    kind: Literal["create", "build", "deploy", "start", "stop", "error"]
    action: str
    version: int = Field(ge=0)
    actor: StreamlitOwner
    result: Literal["ok", "fail", "neutral"]

    model_config = {"from_attributes": True, "extra": "forbid"}


class DeploymentListResponse(BaseModel):
    items: list[HistoryEvent]
    total: int = Field(ge=0)
    next_cursor: str | None = None

    model_config = {"from_attributes": True, "extra": "forbid"}
