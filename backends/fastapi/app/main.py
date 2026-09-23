from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config.settings import Settings, settings
from app.core.errors import BackendError
from app.learning.repository import InMemoryLearningRepository
from app.models.error_models import Error, ErrorResponse
from app.providers.llm.registry import build_llm_provider
from app.routers import chat, health, learning, session
from app.learning.service import LearningService
from app.services.chat_service import ChatService
from app.services.teaching_service import TeachingService


def _error_body(code: str, message: str) -> dict:
    return ErrorResponse(error=Error(code=code, message=message)).model_dump(mode="json")


def create_app(app_settings: Settings | None = None) -> FastAPI:
    app_settings = app_settings or settings

    # Protected modes disable interactive docs; OpenAPI schema generation remains
    # available via the Python API for drift tests.
    _protected = app_settings.requires_session_auth()
    app = FastAPI(
        title="AI Fullstack Starter API",
        version=app_settings.contract_version,
        description="Reference implementation of the /api/v1 contract.",
        docs_url=None if _protected else "/docs",
        redoc_url=None if _protected else "/redoc",
    )
    app.state.settings = app_settings
    app.add_middleware(
        CORSMiddleware,
        allow_origins=app_settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )
    llm_provider = build_llm_provider(app_settings)
    app.state.chat_service = ChatService(llm_provider)
    app.state.teaching_service = TeachingService(
        None if app_settings.llm_provider == "mock" else llm_provider
    )
    app.state.learning_service = LearningService(
        InMemoryLearningRepository(),
        app.state.teaching_service,
    )
    app.include_router(health.router)
    app.include_router(chat.router)
    app.include_router(session.router)
    app.include_router(learning.router)

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        if exc.status_code == 401:
            return JSONResponse(
                status_code=401,
                content=_error_body("unauthorized", "session authentication required"),
            )
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        message = "; ".join(
            f"{'.'.join(str(part) for part in err['loc'])}: {err['msg']}"
            for err in exc.errors()
        )
        return JSONResponse(status_code=422, content=_error_body("invalid_request", message))

    @app.exception_handler(BackendError)
    async def backend_error_handler(request: Request, exc: BackendError) -> JSONResponse:
        return JSONResponse(status_code=exc.http_status, content=_error_body(exc.code, exc.message))

    @app.exception_handler(Exception)
    async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(
            status_code=500, content=_error_body("internal_error", "unexpected server error")
        )

    return app


app = create_app()
