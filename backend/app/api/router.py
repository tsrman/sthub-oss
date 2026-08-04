from fastapi import APIRouter

from app.api.streamlits import router as streamlits_router
from app.api.files import router as files_router
from app.api.lint import router as lint_router
from app.api.users import router as users_router
from app.api.config import router as config_router
from app.api.auth import router as auth_router
from app.api.deployments import router as deployments_router
from app.api.ai import router as ai_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(config_router)
api_router.include_router(auth_router)
api_router.include_router(streamlits_router)
api_router.include_router(files_router)
api_router.include_router(deployments_router)
api_router.include_router(lint_router)
api_router.include_router(users_router)
api_router.include_router(ai_router)
