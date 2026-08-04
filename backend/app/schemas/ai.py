from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    """A single turn in the assistant conversation."""

    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=20000)

    model_config = {"extra": "forbid"}


class FileContext(BaseModel):
    """The file the user currently has open in the editor."""

    path: str = Field(max_length=512)
    language: str = Field(default="", max_length=40)
    content: str = Field(default="", max_length=100000)

    model_config = {"extra": "forbid"}


class ChatRequest(BaseModel):
    """Request body for the AI assistant chat endpoint."""

    messages: list[ChatMessage] = Field(min_length=1, max_length=40)
    context: FileContext | None = None

    model_config = {"extra": "forbid"}


class AiStatus(BaseModel):
    """Whether the AI assistant is available (no secrets exposed)."""

    enabled: bool
    model: str = ""

    model_config = {"extra": "forbid"}
