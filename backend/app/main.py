import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.router import api_router
from app.config import get_settings
from app.exceptions import NotInGroupError, QuotaExceededError

logger = logging.getLogger(__name__)


async def run_migrations():
    """Run alembic migrations on startup."""
    try:
        result = await asyncio.create_subprocess_exec(
            "alembic",
            "upgrade",
            "head",
            stdout=None,
            stderr=None,
        )
        await result.communicate()
        if result.returncode == 0:
            logger.info("Database migrations applied successfully")
        else:
            logger.error("Database migrations failed with code %d", result.returncode)
    except FileNotFoundError:
        logger.warning("alembic not found — skipping migrations")
    except Exception as e:
        logger.error("Migration error: %s", e)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await run_migrations()
    yield


app = FastAPI(
    title="Streamlit Hosting Platform",
    version="0.1.0",
    lifespan=lifespan,
)

cors_origins = get_settings().cors_allow_origins_list

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)


@app.get("/health")
async def health():
    return {"status": "ok"}


# Mapping from HTTP status code to the contract error code returned in the
# error envelope for every HTTPException raised inside the application.
_STATUS_CODE_TO_ERROR_CODE: dict[int, str] = {
    400: "validation_error",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    409: "invalid_state",
    422: "validation_error",
    500: "internal_error",
}


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Return a unified error envelope for every HTTPException."""
    headers = dict(exc.headers) if exc.headers else {}
    if exc.status_code == 401 and "www-authenticate" not in {
        k.lower() for k in headers
    }:
        headers["WWW-Authenticate"] = "Bearer"

    if (
        isinstance(exc.detail, dict)
        and "code" in exc.detail
        and "message" in exc.detail
    ):
        error = {
            "code": exc.detail["code"],
            "message": exc.detail["message"],
        }
        if "details" in exc.detail:
            error["details"] = exc.detail["details"]
    else:
        code = _STATUS_CODE_TO_ERROR_CODE.get(exc.status_code, "internal_error")
        message = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
        error = {"code": code, "message": message}

    return JSONResponse(
        status_code=exc.status_code,
        content={"error": error},
        headers=headers,
    )


@app.exception_handler(RequestValidationError)
async def request_validation_error_handler(
    request: Request, exc: RequestValidationError
):
    """Return a structured 422 error envelope with Pydantic validation details."""
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "validation_error",
                "message": "Validation failed",
                "details": jsonable_encoder(exc.errors()),
            }
        },
    )


@app.exception_handler(NotInGroupError)
async def not_in_group_handler(request: Request, exc: NotInGroupError):
    return JSONResponse(
        status_code=403,
        content={"error": {"code": "not_in_group", "message": exc.message}},
    )


@app.exception_handler(QuotaExceededError)
async def quota_exceeded_handler(request: Request, exc: QuotaExceededError):
    return JSONResponse(
        status_code=409,
        content={
            "error": {
                "code": exc.code,
                "message": str(exc),
                "details": {"limit": exc.limit, "current": exc.current},
            }
        },
    )
