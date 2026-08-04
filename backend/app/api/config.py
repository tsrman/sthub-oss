from fastapi import APIRouter
from pydantic import BaseModel

from app.config import get_settings

router = APIRouter(prefix="/config", tags=["config"])


class KeycloakConfig(BaseModel):
    url: str
    realm: str
    client: str  # SPA client ID for frontend


class PublicConfig(BaseModel):
    keycloak: KeycloakConfig


@router.get("", response_model=PublicConfig)
async def get_public_config():
    """Public endpoint returning frontend configuration (no auth required)."""
    settings = get_settings()
    return PublicConfig(
        keycloak=KeycloakConfig(
            url=settings.keycloak_public_url,
            realm=settings.KEYCLOAK_REALM,
            client=settings.KEYCLOAK_CLIENT,
        )
    )
