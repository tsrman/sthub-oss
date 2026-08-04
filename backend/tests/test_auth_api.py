"""Unit tests for the Keycloak token-exchange endpoint (BFF flow).

``httpx.AsyncClient`` is mocked so no network happens; we assert that the
configured SSL verification flag is honoured and that Keycloak's error body
never leaks into the 401 detail returned to the client.
"""

from __future__ import annotations

import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.api import auth as auth_mod
from app.config import Settings


def _make_response(status_code: int, text: str = "", body: dict | None = None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = text
    resp.json.return_value = body or {}
    return resp


def _mock_client(resp) -> AsyncMock:
    """Build an ``httpx.AsyncClient`` double supporting ``async with``."""
    client = AsyncMock()
    client.post.return_value = resp
    client.__aenter__.return_value = client
    return client


def _code_request() -> auth_mod.TokenRequest:
    return auth_mod.TokenRequest(code="code", redirect_uri="http://app/callback")


async def test_token_exchange_honours_verify_ssl_setting() -> None:
    settings = Settings(KEYCLOAK_VERIFY_SSL=True)
    resp = _make_response(
        200, body={"access_token": "a", "refresh_token": "r", "expires_in": 60}
    )
    with (
        patch.object(auth_mod, "get_settings", return_value=settings),
        patch.object(
            auth_mod.httpx, "AsyncClient", return_value=_mock_client(resp)
        ) as mock_client_cls,
    ):
        await auth_mod.exchange_code(_code_request())

    assert mock_client_cls.call_args.kwargs["verify"] is True


async def test_token_exchange_can_disable_ssl_verification() -> None:
    settings = Settings(KEYCLOAK_VERIFY_SSL=False)
    resp = _make_response(
        200, body={"access_token": "a", "refresh_token": "r", "expires_in": 60}
    )
    with (
        patch.object(auth_mod, "get_settings", return_value=settings),
        patch.object(
            auth_mod.httpx, "AsyncClient", return_value=_mock_client(resp)
        ) as mock_client_cls,
    ):
        await auth_mod.exchange_code(_code_request())

    assert mock_client_cls.call_args.kwargs["verify"] is False


async def test_token_exchange_failure_hides_keycloak_body(caplog) -> None:
    secret_body = '{"error":"invalid_grant","error_description":"top secret"}'
    resp = _make_response(400, text=secret_body)
    with (
        patch.object(auth_mod, "get_settings", return_value=Settings()),
        patch.object(auth_mod.httpx, "AsyncClient", return_value=_mock_client(resp)),
        caplog.at_level(logging.WARNING, logger="app.api.auth"),
        pytest.raises(HTTPException) as exc_info,
    ):
        await auth_mod.exchange_code(_code_request())

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Keycloak token exchange failed"
    assert "invalid_grant" not in exc_info.value.detail
    assert "top secret" not in exc_info.value.detail
    # The Keycloak response body is logged server-side for diagnostics.
    assert "invalid_grant" in caplog.text
