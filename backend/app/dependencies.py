"""FastAPI dependencies (authentication, database session, etc.).

Provides singleton KeycloakAuth instance and user extraction from JWT
tokens.
"""

from __future__ import annotations

import asyncio
import logging
import re
import uuid
from functools import lru_cache
from typing import Any

from fastapi import Depends, Header, HTTPException, status
from jwt.exceptions import DecodeError, ExpiredSignatureError, InvalidTokenError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.keycloak import KeycloakAuth, get_groups
from app.config import Settings, get_settings
from app.core.validation import MAX_LOGIN_LEN, validate_login
from app.db.session import get_db
from app.exceptions import NotInGroupError
from app.models.user import User

logger = logging.getLogger(__name__)

# Reserve room for a numeric collision suffix such as '-1', '-99'.
_MIN_COLLISION_SUFFIX_ROOM = 3
_MAX_BASE_LOGIN_LEN = MAX_LOGIN_LEN - _MIN_COLLISION_SUFFIX_ROOM

# Hard ceiling on login-collision resolution attempts.
_MAX_LOGIN_COLLISION_ATTEMPTS = 100


# ---------------------------------------------------------------------------
# Singleton KeycloakAuth
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def get_keycloak_auth() -> KeycloakAuth:
    """Return a cached (singleton) ``KeycloakAuth`` instance.

    The instance is initialised once from the current Settings and
    reused across the application lifetime.
    """
    settings: Settings = get_settings()
    return KeycloakAuth(settings)


# ---------------------------------------------------------------------------
# Authenticated user dependencies
# ---------------------------------------------------------------------------


async def get_current_user(
    keycloak_auth: KeycloakAuth = Depends(get_keycloak_auth),
    authorization: str | None = Header(None, alias="Authorization"),
    x_authorization: str | None = Header(None, alias="X-Authorization"),
) -> dict[str, Any]:
    """Extract and validate the current user from the Authorization header.

    Accepts token via:
    - ``Authorization: Bearer <token>`` header (standard)
    - ``X-Authorization: Bearer <token>`` header (proxy fallback)

    Query-string tokens are intentionally rejected here; use
    :func:`get_current_user_for_sse` for Server-Sent Events endpoints.

    Returns
    -------
    dict
        The full decoded JWT claims dict.

    Raises
    ------
    HTTPException(401)  -- missing / invalid / expired token
    NotInGroupError     -- user's groups are not in the allowed list
    """
    auth_header = authorization or x_authorization or ""
    return await _validate_token(keycloak_auth, auth_header)


async def get_current_user_for_sse(
    keycloak_auth: KeycloakAuth = Depends(get_keycloak_auth),
    authorization: str | None = Header(None, alias="Authorization"),
    x_authorization: str | None = Header(None, alias="X-Authorization"),
) -> dict[str, Any]:
    """Extract and validate the current user from the Authorization header.

    Accepts token via:
    - ``Authorization: Bearer <token>`` header (standard)
    - ``X-Authorization: Bearer <token>`` header (proxy fallback)

    Query-string tokens are not accepted: the frontend streams SSE with
    ``fetch`` and sends the header, so JWTs never end up in URLs (and the
    access logs that record them).

    Returns
    -------
    dict
        The full decoded JWT claims dict.

    Raises
    ------
    HTTPException(401)  -- missing / invalid / expired token
    NotInGroupError     -- user's groups are not in the allowed list
    """
    auth_header = authorization or x_authorization or ""
    return await _validate_token(keycloak_auth, auth_header)


async def _validate_token(
    keycloak_auth: KeycloakAuth,
    auth_header: str,
) -> dict[str, Any]:
    """Validate a Bearer token and return decoded claims.

    Raises
    ------
    HTTPException(401)  -- missing / invalid / expired token
    NotInGroupError     -- user's groups are not in the allowed list
    """
    if not auth_header:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header is missing",
            headers={"WWW-Authenticate": "Bearer"},
        )

    scheme, _, token = auth_header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Authorization header format; expected 'Bearer <token>'",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        claims = await asyncio.to_thread(keycloak_auth.verify_token_sync, token)
    except (InvalidTokenError, ExpiredSignatureError, DecodeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    except RuntimeError as exc:
        logger.exception("Keycloak verification failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Keycloak verification service unavailable",
        ) from exc

    # Check group membership
    settings: Settings = get_settings()
    if not keycloak_auth.has_access(claims, settings.allowed_groups_list):
        logger.warning(
            "Access denied for user '%s' — groups %s not in allowed %s",
            keycloak_auth.get_username(claims),
            keycloak_auth.get_groups(claims),
            settings.allowed_groups_list,
        )
        raise NotInGroupError("User is not in an allowed group")

    return claims


def _get_constraint_name(exc: IntegrityError) -> str | None:
    """Return the PostgreSQL constraint name from a SQLAlchemy IntegrityError."""
    orig = getattr(exc, "orig", None)
    if orig is not None:
        name = getattr(orig, "constraint_name", None)
        if name:
            return name
        # Some DBAPI drivers stash the original exception on __cause__/__context__.
        cause = getattr(orig, "__cause__", None) or getattr(orig, "__context__", None)
        if cause is not None:
            name = getattr(cause, "constraint_name", None)
            if name:
                return name
    return None


async def _get_or_provision_user(
    claims: dict[str, Any],
    db: AsyncSession,
) -> tuple[uuid.UUID, str, User]:
    """Look up (or auto-provision) the local ``User`` record.

    Matches on the Keycloak ``sub`` claim (``User.keycloak_sub``).  When a user
    logs in for the first time, a ``login`` is derived from
    ``preferred_username`` by lowercasing and replacing any character not in
    ``[a-z0-9-]`` with a hyphen.  Login collisions are resolved by appending
    ``-1``, ``-2``, ... up to a reasonable limit.

    Returns
    -------
    tuple[UUID, str, User]
        The (database primary key, login, User row) triple.
    """
    keycloak_sub = claims.get("sub", "")
    if not keycloak_sub:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token is missing 'sub' claim",
        )

    result = await db.execute(select(User).where(User.keycloak_sub == keycloak_sub))
    user = result.scalar_one_or_none()

    settings = get_settings()
    is_admin = settings.KEYCLOAK_ADMIN_GROUP in get_groups(claims)

    if user is not None:
        # Synchronise admin flag with the current Keycloak group membership.
        # ``is_admin`` is None only for unflushed test objects; in production it
        # is always a boolean because of the NOT NULL constraint.
        if user.is_admin is not None and user.is_admin != is_admin:
            user.is_admin = is_admin
            await db.commit()
        return user.id, user.login, user

    username = claims.get("preferred_username") or keycloak_sub
    email = claims.get("email")

    # Enforce column length limits before any DB operation.
    username = str(username)[:100]
    if email is not None:
        email = str(email)[:255]

    login = re.sub(r"[^a-z0-9-]+", "-", str(username).lower()).strip("-")
    fallback_sub = keycloak_sub.replace("-", "")[: _MAX_BASE_LOGIN_LEN - 2]
    fallback_login = "u-" + fallback_sub
    try:
        validate_login(fallback_login)
    except ValueError as exc:
        logger.exception("Unable to derive a valid fallback login")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unable to derive a valid login",
        ) from exc

    if not login:
        login = fallback_login

    # Cap the base so that a collision suffix (e.g. '-99') still fits within
    # the 40-character login limit.
    base_login = login[:_MAX_BASE_LOGIN_LEN].rstrip("-")
    if not base_login:
        base_login = fallback_login

    for suffix in range(_MAX_LOGIN_COLLISION_ATTEMPTS):
        candidate = base_login if suffix == 0 else f"{base_login}-{suffix}"
        try:
            validate_login(candidate)
        except ValueError as exc:
            logger.warning(
                "Generated login candidate %r is invalid: %s", candidate, exc
            )
            continue

        existing_result = await db.execute(select(User).where(User.login == candidate))
        if existing_result.scalar_one_or_none() is not None:
            continue

        user = User(
            keycloak_sub=keycloak_sub,
            login=candidate,
            username=username,
            email=email,
            is_admin=is_admin,
        )
        db.add(user)
        try:
            await db.commit()
        except IntegrityError as exc:
            await db.rollback()
            constraint_name = _get_constraint_name(exc)

            if constraint_name == "uq_users_login":
                # Another request took the generated login; try the next suffix.
                continue

            if constraint_name == "users_keycloak_sub_key":
                # Another request created the user with the same Keycloak sub.
                result = await db.execute(
                    select(User).where(User.keycloak_sub == keycloak_sub)
                )
                user = result.scalar_one_or_none()
                if user is not None:
                    logger.info(
                        "Concurrent provisioning resolved for sub=%s; using existing user %s",
                        keycloak_sub,
                        user.login,
                    )
                    return user.id, user.login, user

                # The conflicting row is not visible — this should not happen and
                # indicates a consistency problem worth treating as a server error.
                logger.error(
                    "users_keycloak_sub_key integrity error but no matching user for sub=%s",
                    keycloak_sub,
                )
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to provision user account",
                ) from exc

            # Any other integrity problem is unexpected and should alert operators.
            logger.exception("Unexpected IntegrityError while provisioning user")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to provision user account",
            ) from exc
        else:
            await db.refresh(user)
            logger.info(
                "Auto-provisioned user '%s' as '%s' (sub=%s)",
                username,
                candidate,
                keycloak_sub,
            )
            return user.id, user.login, user

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Unable to resolve a unique login",
    )


async def get_current_user_with_login(
    claims: dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> tuple[uuid.UUID, str, User]:
    """Return the current user's (id, login, User row).

    See :func:`_get_or_provision_user` for details on auto-provisioning.
    """
    return await _get_or_provision_user(claims, db)


async def get_current_user_with_login_for_sse(
    claims: dict[str, Any] = Depends(get_current_user_for_sse),
    db: AsyncSession = Depends(get_db),
) -> tuple[uuid.UUID, str, User]:
    """Return the current user's (id, login, User row) for SSE endpoints.

    See :func:`_get_or_provision_user` for details on auto-provisioning.
    """
    return await _get_or_provision_user(claims, db)


async def get_current_user_with_login_and_claims(
    claims: dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> tuple[uuid.UUID, str, User, dict[str, Any]]:
    """Return the current user's (id, login, User row, JWT claims).

    Token validation is performed once by :func:`get_current_user` and the
    claims are forwarded together with the local ``User`` record.
    """
    user_id, login, user = await _get_or_provision_user(claims, db)
    return user_id, login, user, claims


async def get_current_user_id(
    current: tuple[uuid.UUID, str, User] = Depends(get_current_user_with_login),
) -> tuple[uuid.UUID, User]:
    """Return the current user's (id, User row).

    Builds on :func:`get_current_user_with_login` so the user record is
    auto-provisioned if necessary.
    """
    return current[0], current[2]


async def get_current_user_id_for_sse(
    current: tuple[uuid.UUID, str, User] = Depends(get_current_user_with_login_for_sse),
) -> tuple[uuid.UUID, User]:
    """Return the current user's (id, User row) for SSE endpoints.

    Builds on :func:`get_current_user_with_login_for_sse` so the user record
    is auto-provisioned if necessary.
    """
    return current[0], current[2]
