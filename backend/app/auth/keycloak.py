"""Keycloak authentication integration.

Verifies JWT RS256 tokens by fetching JWKS from Keycloak's
openid-configuration endpoint.  Group extraction uses the
standard ``groups`` claim populated by the "groups to token"
mapper in Keycloak.

Uses PyJWT (not python-jose) for reliable signature verification.
"""

from __future__ import annotations

import logging
import ssl
from typing import Any

import jwt  # PyJWT
from jwt import InvalidTokenError, PyJWKClient, PyJWKClientError

from app.config import Settings

logger = logging.getLogger(__name__)


def fetch_jwks_url(settings: Settings) -> str:
    """Return the JWKS URL for the given Keycloak realm."""
    base_url = settings.KEYCLOAK_URL.rstrip("/")
    return f"{base_url}/realms/{settings.KEYCLOAK_REALM}/protocol/openid-connect/certs"


def _make_jwks_client(jwks_url: str, verify_ssl: bool) -> PyJWKClient:
    """Create a PyJWKClient with configurable SSL verification."""
    if verify_ssl:
        ssl_context = ssl.create_default_context()
    else:
        logger.warning(
            "Keycloak SSL verification is disabled for JWKS endpoint %s", jwks_url
        )
        ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
    return PyJWKClient(jwks_url, cache_keys=True, ssl_context=ssl_context)


class KeycloakAuth:
    """Async-aware JWT verifier backed by Keycloak JWKS."""

    def __init__(
        self,
        settings: Settings,
    ) -> None:
        self.settings = settings
        self.keycloak_url = settings.KEYCLOAK_URL.rstrip("/")
        self.public_url = settings.keycloak_public_url
        self._jwks_client: PyJWKClient | None = None

    def _get_jwks_client(self) -> PyJWKClient:
        if self._jwks_client is None:
            jwks_url = (
                f"{self.keycloak_url}/realms/"
                f"{self.settings.KEYCLOAK_REALM}/protocol/openid-connect/certs"
            )
            self._jwks_client = _make_jwks_client(
                jwks_url, self.settings.KEYCLOAK_VERIFY_SSL
            )
        return self._jwks_client

    def _accepted_issuers(self) -> list[str]:
        """Return the list of accepted token issuers.

        Both the internal Keycloak URL (used by the backend to fetch JWKS) and
        the public URL (visible from the browser/frontend) are accepted so that
        tokens obtained via either hostname validate successfully.
        """
        realm = self.settings.KEYCLOAK_REALM
        issuers = [f"{self.keycloak_url}/realms/{realm}"]
        if self.public_url and self.public_url != self.keycloak_url:
            issuers.append(f"{self.public_url}/realms/{realm}")
        return issuers

    def verify_token(self, token: str) -> dict[str, Any]:
        """Verify a JWT (RS256) with audience and issuer checks."""
        client = self._get_jwks_client()
        accepted = self._accepted_issuers()
        last_error: Exception | None = None
        try:
            signing_key = client.get_signing_key_from_jwt(token)
            key = signing_key.key
            for issuer in accepted:
                try:
                    return jwt.decode(
                        token,
                        key,
                        algorithms=["RS256"],
                        issuer=issuer,
                    )
                except InvalidTokenError as exc:
                    last_error = exc
            if last_error:
                raise last_error
        except PyJWKClientError as exc:
            logger.error("JWKS client error while verifying token: %s", exc)
            raise RuntimeError("Keycloak verification service unavailable") from exc
        except jwt.exceptions.PyJWTError as exc:
            logger.error("Token validation error while verifying token: %s", exc)
            raise InvalidTokenError(str(exc)) from exc
        return {}

    verify_token_sync = verify_token  # sync alias

    def get_username(self, claims: dict[str, Any]) -> str:
        """Extract the ``preferred_username`` claim from decoded JWT claims."""
        return claims.get("preferred_username") or claims.get("sub", "unknown")

    def get_groups(self, claims: dict[str, Any]) -> list[str]:
        """Extract the ``groups`` claim (default to empty list)."""
        return get_groups(claims)

    def has_access(self, claims: dict[str, Any], allowed_groups: list[str]) -> bool:
        """Check whether the user's groups intersect with *allowed_groups*."""
        user_groups = set(self.get_groups(claims))
        allowed = set(allowed_groups)
        return bool(user_groups & allowed)

    def get_first_allowed_group(
        self, claims: dict[str, Any], allowed_groups: list[str]
    ) -> str | None:
        """Return the first user group that is present in *allowed_groups*."""
        return get_first_allowed_group(claims, allowed_groups)


def get_groups(claims: dict[str, Any]) -> list[str]:
    """Extract the ``groups`` claim (default to empty list)."""
    groups: list[str] = claims.get("groups", [])
    if groups is None:
        groups = []
    return groups


def get_first_allowed_group(
    claims: dict[str, Any], allowed_groups: list[str]
) -> str | None:
    """Return the first user group that is present in *allowed_groups*.

    The order follows the user's ``groups`` claim.  If none of the user's
    groups are allowed, ``None`` is returned.
    """
    allowed = set(allowed_groups)
    for group in get_groups(claims):
        if group in allowed:
            return group
    return None
