"""Unit tests for the AI assistant service, config, and endpoints.

These avoid the network and the ``openai`` SDK — they exercise message
assembly, the not-configured guard, the ``ai_configured`` property, and the
thin route handlers.
"""

from __future__ import annotations

import asyncio
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from app.api import ai as ai_mod
from app.config import Settings
from app.schemas.ai import AiStatus, ChatMessage, ChatRequest, FileContext
from app.services.ai_service import AiChatLimiter, AiService, tls_verify


def _collect(agen):
    async def run():
        return [frame async for frame in agen]

    return asyncio.run(run())


def _collect_bounded(agen, timeout: float = 5.0):
    """Collect an async generator, failing the test if it exceeds ``timeout``."""

    async def run():
        async def consume():
            return [frame async for frame in agen]

        return await asyncio.wait_for(consume(), timeout=timeout)

    return asyncio.run(run())


def test_build_messages_injects_file_context():
    svc = AiService(Settings(AI_SYSTEM_PROMPT="SYS", AI_MAX_CONTEXT_CHARS=1000))
    req = ChatRequest(
        messages=[ChatMessage(role="user", content="fix this")],
        context=FileContext(path="app.py", language="python", content="print(1)"),
    )
    msgs = svc._build_messages(req)
    assert msgs[0] == {"role": "system", "content": "SYS"}
    assert "app.py" in msgs[1]["content"]
    assert "print(1)" in msgs[1]["content"]
    assert "fix this" in msgs[1]["content"]


def test_build_messages_truncates_context():
    svc = AiService(Settings(AI_SYSTEM_PROMPT="SYS", AI_MAX_CONTEXT_CHARS=5))
    req = ChatRequest(
        messages=[ChatMessage(role="user", content="hi")],
        context=FileContext(path="a.py", language="python", content="0123456789"),
    )
    msgs = svc._build_messages(req)
    assert "01234" in msgs[1]["content"]
    assert "56789" not in msgs[1]["content"]


def test_build_messages_without_context():
    svc = AiService(Settings(AI_SYSTEM_PROMPT="SYS"))
    req = ChatRequest(messages=[ChatMessage(role="user", content="hi")])
    assert svc._build_messages(req) == [
        {"role": "system", "content": "SYS"},
        {"role": "user", "content": "hi"},
    ]


def test_stream_chat_errors_when_not_configured():
    svc = AiService(Settings(AI_ENABLED=False))
    req = ChatRequest(messages=[ChatMessage(role="user", content="hi")])
    frames = _collect(svc.stream_chat(req))
    assert len(frames) == 1
    assert '"type": "error"' in frames[0]
    assert "not configured" in frames[0]


# ---------------------------------------------------------------------------
# stream_chat via a mocked openai SDK
# ---------------------------------------------------------------------------


def _chunk(text: str):
    return SimpleNamespace(
        choices=[SimpleNamespace(delta=SimpleNamespace(content=text))]
    )


def _fake_openai(create_return=None, create_side_effect=None) -> MagicMock:
    """Fake ``openai`` module whose AsyncOpenAI client returns/raises as given."""
    fake_client = MagicMock()
    fake_client.chat.completions.create = AsyncMock(
        return_value=create_return, side_effect=create_side_effect
    )
    fake_openai = MagicMock()
    fake_openai.AsyncOpenAI.return_value = fake_client
    return fake_openai


def test_stream_chat_streams_deltas_and_done():
    svc = AiService(Settings(AI_ENABLED=True, AI_BASE_URL="http://g/v1"))

    async def stream():
        yield _chunk("hello")
        yield _chunk("world")

    req = ChatRequest(messages=[ChatMessage(role="user", content="hi")])
    with patch.dict(sys.modules, {"openai": _fake_openai(stream())}):
        frames = _collect(svc.stream_chat(req))

    assert '"type": "delta"' in frames[0]
    assert "hello" in frames[0]
    assert "world" in frames[1]
    assert '"type": "done"' in frames[-1]


def test_stream_chat_provider_error_yields_error_frame():
    svc = AiService(Settings(AI_ENABLED=True, AI_BASE_URL="http://g/v1"))
    req = ChatRequest(messages=[ChatMessage(role="user", content="hi")])
    fake = _fake_openai(create_side_effect=RuntimeError("provider down"))
    with patch.dict(sys.modules, {"openai": fake}):
        frames = _collect(svc.stream_chat(req))

    assert len(frames) == 1
    assert '"type": "error"' in frames[0]
    assert "Error contacting the model" in frames[0]


def test_stream_chat_overall_deadline_yields_error_frame():
    """A slow drip-feed stream is cut off by the overall deadline (AI_TIMEOUT)."""
    svc = AiService(Settings(AI_ENABLED=True, AI_BASE_URL="http://g/v1", AI_TIMEOUT=0))

    async def dripping_stream():
        yield _chunk("hello")
        await asyncio.sleep(3600)  # slow drip — the deadline must cut this off
        yield _chunk("world")

    req = ChatRequest(messages=[ChatMessage(role="user", content="hi")])
    with patch.dict(sys.modules, {"openai": _fake_openai(dripping_stream())}):
        frames = _collect_bounded(svc.stream_chat(req))

    assert '"type": "done"' not in "".join(frames)
    assert '"type": "error"' in frames[-1]
    assert "timed out" in frames[-1].lower()


def test_ai_configured_property():
    assert Settings(AI_ENABLED=True, AI_BASE_URL="http://g/v1").ai_configured is True
    assert Settings(AI_ENABLED=True, AI_API_KEY="k").ai_configured is True
    assert Settings(AI_ENABLED=False, AI_BASE_URL="http://g/v1").ai_configured is False
    assert (
        Settings(AI_ENABLED=True, AI_BASE_URL="", AI_API_KEY="").ai_configured is False
    )


def test_tls_verify_custom_ca():
    assert tls_verify(
        Settings(AI_VERIFY_SSL=True, AI_CA_CERT="/etc/ssl/custom-ca.pem")
    ) == ("/etc/ssl/custom-ca.pem")


def test_tls_verify_disabled():
    assert tls_verify(Settings(AI_VERIFY_SSL=False, AI_CA_CERT="/x")) is False


def test_tls_verify_system_default():
    assert tls_verify(Settings(AI_VERIFY_SSL=True, AI_CA_CERT="")) is True


def test_ai_configuration_does_not_expose_gateway_details():
    settings = Settings(
        AI_ENABLED=True,
        AI_BASE_URL="https://llm.example.com/v1",
        AI_API_KEY="secret",
    )
    status = AiStatus(enabled=settings.ai_configured, model=settings.AI_MODEL)
    assert status.model == settings.AI_MODEL
    assert "llm.example.com" not in status.model_dump_json()
    assert "secret" not in status.model_dump_json()


def test_ai_status_endpoint(monkeypatch):
    monkeypatch.setattr(
        ai_mod,
        "get_settings",
        lambda: Settings(AI_ENABLED=True, AI_BASE_URL="http://g/v1", AI_MODEL="m"),
    )
    res = asyncio.run(ai_mod.ai_status(claims={}))
    assert res.enabled is True
    assert res.model == "m"


def test_ai_status_endpoint_disabled(monkeypatch):
    monkeypatch.setattr(
        ai_mod, "get_settings", lambda: Settings(AI_ENABLED=False, AI_MODEL="m")
    )
    res = asyncio.run(ai_mod.ai_status(claims={}))
    assert res.enabled is False
    assert res.model == ""


def test_ai_chat_endpoint_returns_event_stream():
    req = ChatRequest(messages=[ChatMessage(role="user", content="hi")])
    res = asyncio.run(ai_mod.ai_chat(body=req, claims={}))
    assert res.media_type == "text/event-stream"


def test_ai_endpoints_require_authorization_header():
    """Requests without a token are rejected before anything touches the LLM."""
    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)

    res = client.post(
        "/api/v1/ai/chat",
        json={"messages": [{"role": "user", "content": "hi"}]},
    )
    assert res.status_code == 401

    res = client.get("/api/v1/ai/status")
    assert res.status_code == 401


# ---------------------------------------------------------------------------
# Per-user concurrency limit on /ai/chat
# ---------------------------------------------------------------------------


def test_chat_limiter_allows_up_to_limit_per_user():
    limiter = AiChatLimiter(limit=2)
    assert limiter.try_acquire("u1") is True
    assert limiter.try_acquire("u1") is True
    assert limiter.try_acquire("u1") is False
    # Another user is unaffected.
    assert limiter.try_acquire("u2") is True


def test_chat_limiter_release_frees_slot():
    limiter = AiChatLimiter(limit=1)
    assert limiter.try_acquire("u1") is True
    assert limiter.try_acquire("u1") is False
    limiter.release("u1")
    assert limiter.try_acquire("u1") is True
    assert limiter.active_count("u1") == 1


def test_chat_limiter_release_unknown_user_is_noop():
    limiter = AiChatLimiter(limit=1)
    limiter.release("ghost")
    assert limiter.active_count("ghost") == 0


def _post_chat(claims: dict, limiter: AiChatLimiter):
    """POST /api/v1/ai/chat with overridden auth and the given limiter."""
    from fastapi.testclient import TestClient

    from app.dependencies import get_current_user
    from app.main import app

    app.dependency_overrides[get_current_user] = lambda: claims
    try:
        with patch.object(ai_mod, "_chat_limiter", limiter):
            return TestClient(app).post(
                "/api/v1/ai/chat",
                json={"messages": [{"role": "user", "content": "hi"}]},
            )
    finally:
        app.dependency_overrides.clear()


def test_ai_chat_endpoint_returns_429_when_slots_exhausted():
    limiter = AiChatLimiter(limit=2)
    assert limiter.try_acquire("user-busy")
    assert limiter.try_acquire("user-busy")

    res = _post_chat({"sub": "user-busy"}, limiter)

    assert res.status_code == 429
    assert res.json()["error"]["code"] == "too_many_requests"


def test_ai_chat_endpoint_releases_slot_after_stream():
    limiter = AiChatLimiter(limit=2)

    res = _post_chat({"sub": "user-free"}, limiter)

    assert res.status_code == 200
    # AI is not configured in tests → terminal error frame, stream completes.
    assert '"type": "error"' in res.text
    assert limiter.active_count("user-free") == 0


def test_ai_chat_endpoint_creates_service_per_request(monkeypatch):
    """The AiService is built inside the handler, not once at import time."""
    created: list[object] = []

    class FakeService:
        def __init__(self):
            created.append(self)

        async def stream_chat(self, body):
            yield 'data: {"type": "done"}\n\n'

    monkeypatch.setattr(ai_mod, "AiService", FakeService)
    req = ChatRequest(messages=[ChatMessage(role="user", content="hi")])

    asyncio.run(ai_mod.ai_chat(body=req, claims={"sub": "u"}))
    asyncio.run(ai_mod.ai_chat(body=req, claims={"sub": "u"}))

    assert len(created) == 2
