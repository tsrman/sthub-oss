import importlib
import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from fastapi.exceptions import RequestValidationError
from sqlalchemy.exc import IntegrityError

from app.config import Settings
from app.dependencies import (
    DecodeError,
    ExpiredSignatureError,
    InvalidTokenError,
    NotInGroupError,
    _validate_token,
    get_current_user,
    get_current_user_for_sse,
    get_current_user_with_login,
    get_current_user_with_login_and_claims,
)
from app.main import (
    http_exception_handler,
    not_in_group_handler,
    request_validation_error_handler,
)
from app.models.user import User


def _mock_db(scalar_returns):
    """Return a mocked AsyncSession that yields the given scalar results."""
    db = AsyncMock()
    db.add = MagicMock()
    results = [
        MagicMock(scalar_one_or_none=MagicMock(return_value=value))
        for value in scalar_returns
    ]
    db.execute.side_effect = results
    return db


def _integrity_error(constraint_name: str | None = None) -> IntegrityError:
    """Build a SQLAlchemy IntegrityError with the given PostgreSQL constraint name."""
    orig = MagicMock()
    if constraint_name:
        orig.constraint_name = constraint_name
    return IntegrityError("INSERT", {}, orig)


@pytest.mark.asyncio
async def test_get_current_user_with_login_existing_user():
    user = User(
        id=uuid.uuid4(),
        keycloak_sub="sub-existing",
        login="alice",
        username="Alice",
        email="alice@example.com",
    )
    db = _mock_db([user])
    claims = {"sub": "sub-existing", "preferred_username": "Alice"}

    user_id, login, returned_user = await get_current_user_with_login(claims, db)

    assert user_id == user.id
    assert login == "alice"
    assert returned_user is user
    db.execute.assert_awaited_once()
    db.add.assert_not_called()
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_current_user_with_login_auto_provisions():
    db = _mock_db([None, None])
    claims = {
        "sub": "sub-new",
        "preferred_username": "John.Doe",
        "email": "john@example.com",
    }

    user_id, login, user = await get_current_user_with_login(claims, db)

    assert login == "john-doe"
    assert user.keycloak_sub == "sub-new"
    assert user.username == "John.Doe"
    assert user.email == "john@example.com"
    db.add.assert_called_once()
    db.commit.assert_awaited_once()
    db.refresh.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_current_user_with_login_collision_resolved():
    existing = User(
        id=uuid.uuid4(),
        keycloak_sub="sub-other",
        login="john-doe",
        username="john-doe",
        email=None,
    )
    db = _mock_db([None, existing, None])
    claims = {"sub": "sub-new", "preferred_username": "John.Doe"}

    _user_id, login, user = await get_current_user_with_login(claims, db)

    assert login == "john-doe-1"
    assert user.login == "john-doe-1"
    db.add.assert_called_once()
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_current_user_with_login_missing_sub_raises_401():
    db = AsyncMock()

    with pytest.raises(HTTPException) as exc_info:
        await get_current_user_with_login({}, db)

    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_get_current_user_with_login_long_base_resolves_collision_within_40():
    """A 40-character normalized login is truncated so the collision suffix fits."""
    long_name = "a" * 40
    base = long_name[:37]
    existing = User(
        id=uuid.uuid4(),
        keycloak_sub="sub-other",
        login=base,
        username=long_name,
        email=None,
    )
    db = _mock_db([None, existing, None])
    claims = {"sub": "sub-new", "preferred_username": long_name}

    _user_id, login, user = await get_current_user_with_login(claims, db)

    assert login == base + "-1"
    assert len(login) == 39
    assert user.login == base + "-1"
    db.add.assert_called_once()
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_current_user_with_login_same_preferred_username_twice():
    """Two users with the same preferred_username are auto-provisioned without a
    unique violation on ``username``.
    """
    first = User(
        id=uuid.uuid4(),
        keycloak_sub="sub-first",
        login="john-doe",
        username="John.Doe",
        email="john@example.com",
    )

    # First user: no collision.
    db_first = _mock_db([None, None])
    claims_first = {
        "sub": "sub-first",
        "preferred_username": "John.Doe",
        "email": "john@example.com",
    }
    _uid, login_first, user_first = await get_current_user_with_login(
        claims_first, db_first
    )
    assert login_first == "john-doe"
    assert user_first.username == "John.Doe"

    # Second user with the same preferred_username gets a disambiguated login.
    db_second = _mock_db([None, first, None])
    claims_second = {
        "sub": "sub-second",
        "preferred_username": "John.Doe",
        "email": "jane@example.com",
    }
    _uid, login_second, user_second = await get_current_user_with_login(
        claims_second, db_second
    )
    assert login_second == "john-doe-1"
    assert user_second.username == "John.Doe"
    assert user_second.keycloak_sub == "sub-second"


# ---------------------------------------------------------------------------
# _validate_token strict verification
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_validate_token_missing_header():
    auth = MagicMock()
    with pytest.raises(HTTPException) as exc_info:
        await _validate_token(auth, "")

    assert exc_info.value.status_code == 401
    assert "missing" in exc_info.value.detail.lower()
    assert exc_info.value.headers["WWW-Authenticate"] == "Bearer"


@pytest.mark.asyncio
async def test_validate_token_invalid_scheme():
    auth = MagicMock()
    with pytest.raises(HTTPException) as exc_info:
        await _validate_token(auth, "Basic token")

    assert exc_info.value.status_code == 401
    auth.verify_token_sync.assert_not_called()


@patch("app.dependencies.get_settings")
@pytest.mark.asyncio
async def test_validate_token_success(mock_settings):
    mock_settings.return_value.allowed_groups_list = ["streamlit-users"]
    auth = MagicMock()
    auth.verify_token_sync.return_value = {
        "sub": "uuid",
        "groups": ["streamlit-users"],
    }
    auth.has_access.return_value = True

    claims = await _validate_token(auth, "Bearer valid-token")

    assert claims["sub"] == "uuid"
    auth.verify_token_sync.assert_called_once_with("valid-token")


@patch("app.dependencies.get_settings")
@pytest.mark.asyncio
async def test_validate_token_runtime_error_raises_500(mock_settings):
    mock_settings.return_value.allowed_groups_list = ["streamlit-users"]
    auth = MagicMock()
    auth.verify_token_sync.side_effect = RuntimeError("verify blew up")

    with pytest.raises(HTTPException) as exc_info:
        await _validate_token(auth, "Bearer token")

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == "Keycloak verification service unavailable"


@pytest.mark.parametrize(
    "exc_cls",
    [
        InvalidTokenError,
        ExpiredSignatureError,
        DecodeError,
    ],
)
@patch("app.dependencies.get_settings")
@pytest.mark.asyncio
async def test_validate_token_pyjwt_errors_raise_401(mock_settings, exc_cls):
    mock_settings.return_value.allowed_groups_list = ["streamlit-users"]
    auth = MagicMock()
    auth.verify_token_sync.side_effect = exc_cls("bad token")

    with pytest.raises(HTTPException) as exc_info:
        await _validate_token(auth, "Bearer invalid-token")

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Invalid or expired token"
    assert exc_info.value.headers["WWW-Authenticate"] == "Bearer"
    auth.verify_token_sync.assert_called_once_with("invalid-token")


@patch("app.dependencies.get_settings")
@pytest.mark.asyncio
async def test_validate_token_forbidden(mock_settings):
    mock_settings.return_value.allowed_groups_list = ["streamlit-users"]
    auth = MagicMock()
    auth.verify_token_sync.return_value = {"sub": "uuid", "groups": ["other-group"]}
    auth.has_access.return_value = False

    with pytest.raises(NotInGroupError, match="not in an allowed group"):
        await _validate_token(auth, "Bearer valid-token")


# ---------------------------------------------------------------------------
# SSE endpoints authenticate via the Authorization header only
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_current_user_rejects_query_token():
    auth = MagicMock()
    auth.verify_token_sync.assert_not_called()

    with pytest.raises(HTTPException) as exc_info:
        await get_current_user(
            keycloak_auth=auth,
            authorization=None,
            x_authorization=None,
        )

    assert exc_info.value.status_code == 401
    assert "missing" in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_get_current_user_for_sse_accepts_authorization_header():
    auth = MagicMock()
    auth.verify_token_sync.return_value = {"sub": "uuid", "groups": ["streamlit-users"]}
    auth.has_access.return_value = True

    claims = await get_current_user_for_sse(
        keycloak_auth=auth,
        authorization="Bearer raw-token",
        x_authorization=None,
    )

    assert claims["sub"] == "uuid"
    auth.verify_token_sync.assert_called_once_with("raw-token")


def test_get_current_user_for_sse_has_no_query_token_param():
    """The query-string token fallback is removed from the SSE dependency."""
    import inspect

    assert "token" not in inspect.signature(get_current_user_for_sse).parameters


@pytest.mark.asyncio
async def test_get_current_user_for_sse_rejects_missing_header():
    auth = MagicMock()

    with pytest.raises(HTTPException) as exc_info:
        await get_current_user_for_sse(
            keycloak_auth=auth,
            authorization=None,
            x_authorization=None,
        )

    assert exc_info.value.status_code == 401
    auth.verify_token_sync.assert_not_called()


def test_sse_logs_endpoint_rejects_query_token_without_header():
    """A ``?token=`` query param is not accepted; the header is required."""
    import base64
    import json as json_module

    from fastapi.testclient import TestClient

    from app.main import app

    def _b64(raw: bytes) -> str:
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()

    # A structurally valid JWT: with the old fallback the request would proceed
    # to JWKS verification (failing with 401/500 only there), never rejected
    # up front for the missing Authorization header.
    token = ".".join(
        [
            _b64(json_module.dumps({"alg": "RS256", "kid": "k"}).encode()),
            _b64(json_module.dumps({"sub": "x"}).encode()),
            _b64(b"fake-signature"),
        ]
    )

    response = TestClient(app).get(
        f"/api/v1/streamlits/{uuid.uuid4()}/logs?token={token}"
    )

    assert response.status_code == 401
    assert "missing" in response.json()["error"]["message"].lower()


# ---------------------------------------------------------------------------
# Defensive preferred_username handling
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_current_user_with_login_none_username_uses_sub():
    db = _mock_db([None, None])
    claims = {"sub": "sub-new", "preferred_username": None, "email": None}

    _uid, login, user = await get_current_user_with_login(claims, db)

    assert user.username == "sub-new"
    assert login == "sub-new"


@pytest.mark.asyncio
async def test_get_current_user_with_login_missing_username_uses_sub():
    db = _mock_db([None, None])
    claims = {"sub": "sub-new", "email": None}

    _uid, login, user = await get_current_user_with_login(claims, db)

    assert user.username == "sub-new"
    assert login == "sub-new"


@pytest.mark.asyncio
async def test_get_current_user_with_login_empty_normalized_username_uses_fallback():
    """A preferred_username that normalizes to empty falls back to a valid login."""
    db = _mock_db([None, None])
    claims = {"sub": "sub-new", "preferred_username": "---", "email": None}

    _uid, login, user = await get_current_user_with_login(claims, db)

    assert login == "u-subnew"
    assert user.login == "u-subnew"
    db.add.assert_called_once()
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_current_user_with_login_handles_race_on_commit():
    """If another request provisions the user between check and commit, reuse it."""
    existing = User(
        id=uuid.uuid4(),
        keycloak_sub="sub-race",
        login="alice",
        username="Alice",
        email=None,
    )
    db = _mock_db([None, None, existing])
    db.commit.side_effect = _integrity_error("users_keycloak_sub_key")
    claims = {"sub": "sub-race", "preferred_username": "Alice"}

    user_id, login, user = await get_current_user_with_login(claims, db)

    assert login == "alice"
    assert user is existing
    db.add.assert_called_once()
    db.commit.assert_awaited_once()
    db.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_current_user_with_login_login_collision_race_recovered():
    """If another request takes the generated login, the next suffix is attempted."""
    db = _mock_db([None, None, None, None])
    db.commit.side_effect = [
        _integrity_error("uq_users_login"),
        None,
    ]
    claims = {"sub": "sub-new", "preferred_username": "John.Doe"}

    _uid, login, user = await get_current_user_with_login(claims, db)

    assert login == "john-doe-1"
    assert user.login == "john-doe-1"
    assert db.commit.await_count == 2
    db.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_current_user_with_login_sub_race_without_existing_raises_500():
    """If the sub-key constraint fires but the row cannot be re-fetched, fail safe."""
    db = AsyncMock()
    db.add = MagicMock()
    db.commit.side_effect = _integrity_error("users_keycloak_sub_key")
    execute_result = MagicMock()
    execute_result.scalar_one_or_none.return_value = None
    db.execute.return_value = execute_result
    claims = {"sub": "sub-race", "preferred_username": "Alice"}

    with pytest.raises(HTTPException) as exc_info:
        await get_current_user_with_login(claims, db)

    assert exc_info.value.status_code == 500
    assert db.execute.await_count == 3  # initial lookup + login check + race re-query


@pytest.mark.asyncio
async def test_get_current_user_with_login_unknown_integrity_error_raises_500():
    """An IntegrityError on an unknown constraint is treated as a server error."""
    db = AsyncMock()
    db.add = MagicMock()
    db.commit.side_effect = _integrity_error("some_other_constraint")
    execute_result = MagicMock()
    execute_result.scalar_one_or_none.return_value = None
    db.execute.return_value = execute_result
    claims = {"sub": "sub-race", "preferred_username": "Alice"}

    with pytest.raises(HTTPException) as exc_info:
        await get_current_user_with_login(claims, db)

    assert exc_info.value.status_code == 500
    assert db.add.call_count == 1


@pytest.mark.asyncio
async def test_get_current_user_with_login_truncates_username_and_email():
    """Long ``preferred_username`` and ``email`` values are truncated to column limits."""
    db = _mock_db([None, None])
    long_username = "u" * 150
    long_email = "e" * 300 + "@example.com"
    claims = {
        "sub": "sub-new",
        "preferred_username": long_username,
        "email": long_email,
    }

    _uid, login, user = await get_current_user_with_login(claims, db)

    assert len(user.username) == 100
    assert user.username == "u" * 100
    assert user.email == long_email[:255]
    assert len(login) <= 40


# ---------------------------------------------------------------------------
# get_current_user_with_login_and_claims
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_current_user_with_login_and_claims_returns_claims():
    user = User(
        id=uuid.uuid4(),
        keycloak_sub="sub-existing",
        login="alice",
        username="Alice",
        email="alice@example.com",
    )
    db = _mock_db([user])
    claims = {"sub": "sub-existing", "preferred_username": "Alice"}

    (
        user_id,
        login,
        returned_user,
        returned_claims,
    ) = await get_current_user_with_login_and_claims(claims, db)

    assert user_id == user.id
    assert login == "alice"
    assert returned_user is user
    assert returned_claims is claims


# ---------------------------------------------------------------------------
# Global auth error handler
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_http_exception_handler_401():
    request = MagicMock()
    exc = HTTPException(status_code=401, detail="Missing token")

    response = await http_exception_handler(request, exc)

    assert response.status_code == 401
    assert json.loads(response.body) == {
        "error": {"code": "unauthorized", "message": "Missing token"}
    }
    assert response.headers["www-authenticate"] == "Bearer"


@pytest.mark.asyncio
async def test_http_exception_handler_401_preserves_www_authenticate():
    request = MagicMock()
    exc = HTTPException(
        status_code=401,
        detail="Custom",
        headers={"WWW-Authenticate": 'Bearer error="invalid_token"'},
    )

    response = await http_exception_handler(request, exc)

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == 'Bearer error="invalid_token"'


@pytest.mark.asyncio
async def test_http_exception_handler_403():
    request = MagicMock()
    exc = HTTPException(status_code=403, detail="No access")

    response = await http_exception_handler(request, exc)

    assert response.status_code == 403
    assert json.loads(response.body) == {
        "error": {"code": "forbidden", "message": "No access"}
    }
    assert "www-authenticate" not in {k.lower() for k in response.headers.keys()}


@pytest.mark.asyncio
async def test_http_exception_handler_maps_422_to_validation_error():
    request = MagicMock()
    exc = HTTPException(status_code=422, detail="Validation error")

    response = await http_exception_handler(request, exc)

    assert response.status_code == 422
    assert json.loads(response.body) == {
        "error": {"code": "validation_error", "message": "Validation error"}
    }


@pytest.mark.asyncio
async def test_not_in_group_handler_returns_distinct_error_code():
    request = MagicMock()
    exc = NotInGroupError("User is not in an allowed group")

    response = await not_in_group_handler(request, exc)

    assert response.status_code == 403
    assert json.loads(response.body) == {
        "error": {
            "code": "not_in_group",
            "message": "User is not in an allowed group",
        }
    }


@pytest.mark.asyncio
async def test_http_exception_handler_uses_custom_detail_code():
    request = MagicMock()
    exc = HTTPException(
        status_code=409,
        detail={"code": "slug_taken", "message": "Slug already taken"},
    )

    response = await http_exception_handler(request, exc)

    assert response.status_code == 409
    assert json.loads(response.body) == {
        "error": {"code": "slug_taken", "message": "Slug already taken"}
    }


@pytest.mark.asyncio
async def test_request_validation_error_handler_returns_envelope():
    request = MagicMock()
    exc = RequestValidationError(errors=[{"loc": ["body", "name"], "msg": "required"}])

    response = await request_validation_error_handler(request, exc)

    assert response.status_code == 422
    body = json.loads(response.body)
    assert body == {
        "error": {
            "code": "validation_error",
            "message": "Validation failed",
            "details": [{"loc": ["body", "name"], "msg": "required"}],
        }
    }


@pytest.mark.parametrize(
    "status_code, expected_code",
    [
        (400, "validation_error"),
        (404, "not_found"),
        (409, "invalid_state"),
        (422, "validation_error"),
        (500, "internal_error"),
    ],
)
@pytest.mark.asyncio
async def test_http_exception_handler_maps_status_to_error_code(
    status_code, expected_code
):
    request = MagicMock()
    exc = HTTPException(status_code=status_code, detail="Something happened")

    response = await http_exception_handler(request, exc)

    assert response.status_code == status_code
    assert json.loads(response.body) == {
        "error": {"code": expected_code, "message": "Something happened"}
    }


# ---------------------------------------------------------------------------
# Configurable CORS origins
# ---------------------------------------------------------------------------


def test_settings_cors_allow_origins_property():
    assert Settings().cors_allow_origins_list == ["*"]

    settings = Settings(
        CORS_ALLOW_ORIGINS="https://app.example.com, https://admin.example.com"
    )
    assert settings.cors_allow_origins_list == [
        "https://app.example.com",
        "https://admin.example.com",
    ]


def test_main_uses_configured_cors_origins(monkeypatch):
    from app import config, main

    monkeypatch.setenv("CORS_ALLOW_ORIGINS", "https://frontend.example.com")
    config.get_settings.cache_clear()
    try:
        importlib.reload(config)
        importlib.reload(main)
        assert main.cors_origins == ["https://frontend.example.com"]
    finally:
        monkeypatch.delenv("CORS_ALLOW_ORIGINS", raising=False)
        config.get_settings.cache_clear()
        importlib.reload(config)
        importlib.reload(main)
