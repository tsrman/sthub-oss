"""AI code-assistant service.

Talks to the model through a self-hosted OpenAI-compatible gateway using the
``openai`` SDK. The API key and endpoint live in backend settings only — the
frontend never talks to the gateway directly. ``AI_BASE_URL`` points the SDK at
the self-hosted gateway.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator

from app.config import Settings, get_settings
from app.schemas.ai import ChatRequest

logger = logging.getLogger(__name__)


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def tls_verify(settings: Settings) -> bool | str:
    """Resolve the httpx ``verify`` value for the gateway connection.

    Returns the custom CA bundle path when configured, ``False`` to disable
    verification, or ``True`` to use the system trust store.
    """
    if not settings.AI_VERIFY_SSL:
        return False
    if settings.AI_CA_CERT:
        return settings.AI_CA_CERT
    return True


class AiChatLimiter:
    """Limits concurrent chat streams per user.

    Plain in-memory counters — sufficient for the single Control API instance.
    """

    def __init__(self, limit: int = 2) -> None:
        self._limit = limit
        self._active: dict[str, int] = {}

    def try_acquire(self, user_key: str) -> bool:
        """Reserve a chat slot for the user; False when the limit is reached."""
        active = self._active.get(user_key, 0)
        if active >= self._limit:
            return False
        self._active[user_key] = active + 1
        return True

    def release(self, user_key: str) -> None:
        """Return a previously reserved slot (safe to call for unknown users)."""
        active = self._active.get(user_key, 0)
        if active <= 1:
            self._active.pop(user_key, None)
        else:
            self._active[user_key] = active - 1

    def active_count(self, user_key: str) -> int:
        """Return the number of slots currently held by the user."""
        return self._active.get(user_key, 0)


class AiService:
    """Streams chat completions from the configured LLM gateway as SSE events."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    def _build_messages(self, req: ChatRequest) -> list[dict]:
        settings = self._settings
        messages: list[dict] = [
            {"role": "system", "content": settings.AI_SYSTEM_PROMPT}
        ]
        turns = [{"role": m.role, "content": m.content} for m in req.messages]
        # Attach the open file as context to the latest user turn.
        if req.context and req.context.content.strip() and turns:
            content = req.context.content[: settings.AI_MAX_CONTEXT_CHARS]
            note = (
                f"Open file `{req.context.path}` "
                f"(language: {req.context.language or 'text'}):\n"
                f"```{req.context.language}\n{content}\n```\n\n"
            )
            for i in range(len(turns) - 1, -1, -1):
                if turns[i]["role"] == "user":
                    turns[i]["content"] = note + turns[i]["content"]
                    break
        messages.extend(turns)
        return messages

    async def stream_chat(self, req: ChatRequest) -> AsyncIterator[str]:
        """Yield SSE frames: ``{type: "delta", text}`` … then ``{type: "done"}``.

        Errors are surfaced as a terminal ``{type: "error", message}`` frame
        rather than raised, so the open SSE stream closes cleanly.
        """
        settings = self._settings
        if not settings.ai_configured:
            yield _sse(
                {"type": "error", "message": "The AI assistant is not configured"}
            )
            return

        try:
            import httpx
            from openai import AsyncOpenAI
        except ImportError:  # pragma: no cover - dependency guard
            logger.error("openai SDK is not installed")
            yield _sse({"type": "error", "message": "The AI assistant is unavailable"})
            return

        # Verify the gateway's certificate against the custom CA bundle when
        # provided; fall back to system CAs, or disable verification if asked.
        http_client = httpx.AsyncClient(
            verify=tls_verify(settings), timeout=float(settings.AI_TIMEOUT)
        )
        client = AsyncOpenAI(
            # The gateway may not require a key; send a placeholder so the SDK
            # constructs (it rejects an empty api_key).
            api_key=settings.AI_API_KEY or "not-needed",
            base_url=settings.AI_BASE_URL or None,
            timeout=float(settings.AI_TIMEOUT),
            http_client=http_client,
        )

        messages = self._build_messages(req)
        try:
            stream = await client.chat.completions.create(
                model=settings.AI_MODEL,
                messages=messages,
                max_tokens=settings.AI_MAX_TOKENS,
                stream=True,
            )
            # Overall deadline for the whole stream: the httpx timeout only
            # bounds the gap between chunks, so a slow drip-feed would
            # otherwise hold the connection open forever.
            async with asyncio.timeout(float(settings.AI_TIMEOUT)):
                async for chunk in stream:
                    if not chunk.choices:
                        continue
                    text = chunk.choices[0].delta.content
                    if text:
                        yield _sse({"type": "delta", "text": text})
            yield _sse({"type": "done"})
        except TimeoutError:
            logger.warning("AI chat stream exceeded the overall deadline")
            yield _sse(
                {
                    "type": "error",
                    "message": "Timed out waiting for the model to respond",
                }
            )
        except Exception:  # noqa: BLE001 - surface any provider failure to the UI
            logger.exception("AI chat streaming failed")
            yield _sse({"type": "error", "message": "Error contacting the model"})
        finally:
            await http_client.aclose()
