from fastapi import APIRouter, Depends

from app.dependencies import get_current_user
from app.schemas.lint import LintRequest, LintResponse
from app.schemas.problem import Problem
from app.services.lint_service import LintService

router = APIRouter(tags=["lint"])
service = LintService()


@router.post("/lint", response_model=LintResponse)
async def lint_code(
    body: LintRequest,
    claims: dict = Depends(get_current_user),
):
    errors = await service.check_syntax(body.code)
    return LintResponse(
        ok=len(errors) == 0,
        problems=[Problem(**e) for e in errors],
    )


@router.get("/allowed-packages")
async def list_allowed_packages(
    claims: dict = Depends(get_current_user),
):
    from app.config import get_settings

    settings = get_settings()
    return {"packages": sorted(settings.allowed_packages_set)}
