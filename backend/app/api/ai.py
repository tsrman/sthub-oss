from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from app.config import get_settings
from app.dependencies import get_current_user
from app.schemas.ai import AiStatus, ChatRequest
from app.services.ai_service import AiChatLimiter, AiService

router = APIRouter(prefix="/ai", tags=["ai"])
_chat_limiter = AiChatLimiter()


async def _stream_with_slot(
    user_key: str, stream: AsyncIterator[str]
) -> AsyncIterator[str]:
    """Relay the chat stream and always release the user's slot at the end."""
    try:
        async for frame in stream:
            yield frame
    finally:
        _chat_limiter.release(user_key)


@router.get("/status", response_model=AiStatus)
async def ai_status(claims: dict = Depends(get_current_user)):
    """Report whether the AI assistant is available (no secrets exposed)."""
    settings = get_settings()
    return AiStatus(
        enabled=settings.ai_configured,
        model=settings.AI_MODEL if settings.ai_configured else "",
    )


@router.post("/chat")
async def ai_chat(
    body: ChatRequest,
    claims: dict = Depends(get_current_user),
):
    """Stream an assistant reply as SSE.

    Authenticated via the standard ``Authorization`` header (the browser reads
    the stream with ``fetch``, not ``EventSource``). Each user may hold at most
    two concurrent streams; further requests are rejected with 429.
    """
    service = AiService()
    user_key = str(claims.get("sub", "unknown"))
    if not _chat_limiter.try_acquire(user_key):
        raise HTTPException(
            status_code=429,
            detail={
                "code": "too_many_requests",
                "message": "Too many concurrent requests to the AI assistant",
            },
        )
    return StreamingResponse(
        _stream_with_slot(user_key, service.stream_chat(body)),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
