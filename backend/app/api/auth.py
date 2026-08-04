"""Auth endpoints — Keycloak code exchange and token refresh (BFF flow)."""

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


class TokenRequest(BaseModel):
    code: str | None = None
    redirect_uri: str | None = None
    grant_type: str = Field(default="authorization_code")
    refresh_token: str | None = None


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    expires_in: int


@router.post("/token", response_model=TokenResponse)
async def exchange_code(req: TokenRequest):
    """Exchange an authorization code or refresh a token.

    - ``grant_type=authorization_code``  →  first login (code exchange)
    - ``grant_type=refresh_token``       →  silent token refresh

    Uses the Back-Channel (client credentials) so the client secret
    never leaves the server.
    """
    settings = get_settings()
    token_url = (
        f"{settings.KEYCLOAK_URL}/realms/"
        f"{settings.KEYCLOAK_REALM}/protocol/openid-connect/token"
    )

    data: dict[str, str] = {"grant_type": req.grant_type}

    if req.grant_type == "authorization_code":
        if not req.code or not req.redirect_uri:
            raise HTTPException(400, "code and redirect_uri are required")
        data["code"] = req.code
        data["redirect_uri"] = req.redirect_uri
        data["client_id"] = settings.KEYCLOAK_CLIENT
    elif req.grant_type == "refresh_token":
        if not req.refresh_token:
            raise HTTPException(400, "refresh_token is required")
        data["refresh_token"] = req.refresh_token
    else:
        raise HTTPException(400, f"Unsupported grant_type: {req.grant_type}")

    # Only send client_secret if configured (confidential clients)
    if settings.KEYCLOAK_CLIENT_SECRET:
        data["client_secret"] = settings.KEYCLOAK_CLIENT_SECRET

    # Honour the configured SSL verification policy (self-signed
    # certs are handled by setting KEYCLOAK_VERIFY_SSL=false).
    async with httpx.AsyncClient(
        timeout=15.0, verify=settings.KEYCLOAK_VERIFY_SSL
    ) as client:
        resp = await client.post(token_url, data=data)

    if resp.status_code != 200:
        # Log the Keycloak error server-side; never leak it to the client.
        logger.warning(
            "Keycloak token exchange failed with status %s: %s",
            resp.status_code,
            resp.text[:200],
        )
        raise HTTPException(
            status_code=401,
            detail="Keycloak token exchange failed",
        )

    body = resp.json()
    return TokenResponse(
        access_token=body["access_token"],
        refresh_token=body.get("refresh_token", req.refresh_token or ""),
        expires_in=body.get("expires_in", 300),
    )
