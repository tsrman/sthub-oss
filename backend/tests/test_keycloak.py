import ssl
from unittest.mock import MagicMock, patch

import pytest
from jwt import InvalidTokenError
from jwt.exceptions import InvalidKeyError

from app.auth.keycloak import KeycloakAuth, _make_jwks_client, get_first_allowed_group
from app.config import Settings


@pytest.fixture
def auth() -> KeycloakAuth:
    return KeycloakAuth(
        Settings(KEYCLOAK_ALLOWED_GROUPS="streamlit-users,streamlit-admins")
    )


def test_get_username_returns_preferred_username(auth: KeycloakAuth) -> None:
    claims = {"preferred_username": "alice", "sub": "uuid-1"}
    assert auth.get_username(claims) == "alice"


def test_get_username_falls_back_to_sub(auth: KeycloakAuth) -> None:
    claims = {"sub": "uuid-2"}
    assert auth.get_username(claims) == "uuid-2"


def test_get_username_falls_back_to_sub_for_explicit_none_preferred_username(
    auth: KeycloakAuth,
) -> None:
    claims = {"preferred_username": None, "sub": "uuid-3"}
    assert auth.get_username(claims) == "uuid-3"


def test_get_username_falls_back_to_sub_for_empty_preferred_username(
    auth: KeycloakAuth,
) -> None:
    claims = {"preferred_username": "", "sub": "uuid-4"}
    assert auth.get_username(claims) == "uuid-4"


def test_get_username_unknown_when_both_missing(auth: KeycloakAuth) -> None:
    assert auth.get_username({}) == "unknown"


def test_get_groups_defaults_to_empty_list(auth: KeycloakAuth) -> None:
    assert auth.get_groups({}) == []


def test_get_groups_handles_none_claim(auth: KeycloakAuth) -> None:
    assert auth.get_groups({"groups": None}) == []


def test_get_groups_returns_groups(auth: KeycloakAuth) -> None:
    claims = {"groups": ["streamlit-users", "streamlit-admins"]}
    assert auth.get_groups(claims) == ["streamlit-users", "streamlit-admins"]


def test_has_access_true_when_group_matches(auth: KeycloakAuth) -> None:
    claims = {"groups": ["streamlit-users"]}
    assert auth.has_access(claims, ["streamlit-users", "streamlit-admins"]) is True


def test_has_access_false_when_no_group_matches(auth: KeycloakAuth) -> None:
    claims = {"groups": ["other-group"]}
    assert auth.has_access(claims, ["streamlit-users"]) is False


def test_has_access_false_when_groups_none(auth: KeycloakAuth) -> None:
    claims = {"groups": None}
    assert auth.has_access(claims, ["streamlit-users"]) is False


def test_get_first_allowed_group_method_returns_first_match(auth: KeycloakAuth) -> None:
    claims = {"groups": ["streamlit-admins", "streamlit-users"]}
    allowed = ["streamlit-users", "streamlit-admins"]
    assert auth.get_first_allowed_group(claims, allowed) == "streamlit-admins"


def test_get_first_allowed_group_method_returns_none_when_no_match(
    auth: KeycloakAuth,
) -> None:
    claims = {"groups": ["other-group"]}
    assert auth.get_first_allowed_group(claims, ["streamlit-users"]) is None


def test_get_first_allowed_group_method_handles_none_groups(auth: KeycloakAuth) -> None:
    claims = {"groups": None}
    assert auth.get_first_allowed_group(claims, ["streamlit-users"]) is None


def test_get_first_allowed_group_module_level_wrapper_handles_none() -> None:
    # Module-level wrapper should be resilient to a missing/None groups claim.
    assert get_first_allowed_group({"groups": None}, ["streamlit-users"]) is None


def test_get_first_allowed_group_module_level_wrapper_returns_match() -> None:
    claims = {"groups": ["streamlit-users", "streamlit-admins"]}
    assert get_first_allowed_group(claims, ["streamlit-admins"]) == "streamlit-admins"


def test_keycloak_url_normalized_strips_trailing_slash():
    settings = Settings(KEYCLOAK_URL="http://keycloak:8080/")
    auth = KeycloakAuth(settings)
    assert auth.keycloak_url == "http://keycloak:8080"


def test_make_jwks_client_uses_verified_ssl_when_enabled():
    jwks_url = "https://keycloak/realms/r/protocol/openid-connect/certs"
    with (
        patch("ssl.create_default_context") as mock_ctx,
        patch("app.auth.keycloak.PyJWKClient") as mock_client,
    ):
        mock_ctx.return_value = MagicMock()
        _make_jwks_client(jwks_url, verify_ssl=True)
        mock_ctx.assert_called_once()
        mock_client.assert_called_once()
        _, kwargs = mock_client.call_args
        assert kwargs["ssl_context"] is mock_ctx.return_value


def test_make_jwks_client_skips_ssl_verification_when_disabled():
    jwks_url = "https://keycloak/realms/r/protocol/openid-connect/certs"
    with (
        patch("ssl.SSLContext") as mock_ctx,
        patch("app.auth.keycloak.PyJWKClient") as mock_client,
    ):
        instance = MagicMock()
        mock_ctx.return_value = instance
        _make_jwks_client(jwks_url, verify_ssl=False)
        mock_ctx.assert_called_once_with(ssl.PROTOCOL_TLS_CLIENT)
        assert instance.check_hostname is False
        assert instance.verify_mode == ssl.CERT_NONE
        mock_client.assert_called_once()
        _, kwargs = mock_client.call_args
        assert kwargs["ssl_context"] is instance


def test_make_jwks_client_logs_warning_when_ssl_disabled(caplog):
    jwks_url = "https://keycloak/realms/r/protocol/openid-connect/certs"
    with (
        patch("ssl.SSLContext") as mock_ctx,
        patch("app.auth.keycloak.PyJWKClient"),
    ):
        mock_ctx.return_value = MagicMock()
        with caplog.at_level("WARNING", logger="app.auth.keycloak"):
            _make_jwks_client(jwks_url, verify_ssl=False)

    assert "SSL verification is disabled" in caplog.text


def test_verify_token_converts_invalid_key_error(auth: KeycloakAuth) -> None:
    invalid_key_exc = InvalidKeyError("bad key")
    with (
        patch.object(auth, "_get_jwks_client") as mock_get_client,
        patch("app.auth.keycloak.jwt.decode") as mock_decode,
    ):
        mock_key = MagicMock()
        mock_key.key = "key"
        mock_client = MagicMock()
        mock_client.get_signing_key_from_jwt.return_value = mock_key
        mock_get_client.return_value = mock_client
        mock_decode.side_effect = invalid_key_exc

        with pytest.raises(InvalidTokenError) as exc_info:
            auth.verify_token("token")

    assert exc_info.value.__cause__ is invalid_key_exc
