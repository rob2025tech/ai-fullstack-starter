from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config.settings import Settings, settings
from app.core.errors import BackendError
from app.learning.repository import InMemoryLearningRepository
from app.models.error_models import Error, ErrorResponse
from app.providers.llm.base import LLMProvider
from app.providers.llm.policy import ProviderPolicy, ProviderPolicyConfig
from app.providers.llm.registry import build_llm_provider
from app.routers import chat, health, learning
from app.learning.service import LearningService
from app.services.chat_service import ChatService
from app.services.teaching_service import TeachingService


def _error_body(code: str, message: str) -> dict:
    return ErrorResponse(error=Error(code=code, message=message)).model_dump(mode="json")


def create_app(
    app_settings: Settings | None = None,
    llm_provider_override: LLMProvider | None = None,
) -> FastAPI:
    """Create and configure the FastAPI application.

    Parameters
    ----------
    app_settings:
        Application settings; uses the module-level singleton when omitted.
    llm_provider_override:
        If provided, use this ``LLMProvider`` instead of calling
        ``build_llm_provider``.  Intended for integration tests that need
        to inject a specific provider (e.g. a failing stub).
    """
    app_settings = app_settings or settings
    app = FastAPI(
        title="AI Fullstack Starter API",
        version=app_settings.contract_version,
        description="Reference implementation of the /api/v1 contract.",
    )
    app.state.settings = app_settings
    app.add_middleware(
        CORSMiddleware,
        allow_origins=app_settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )
    llm_provider = llm_provider_override or build_llm_provider(app_settings)
    policy_config = ProviderPolicyConfig(
        timeout_seconds=app_settings.provider_timeout_seconds,
        max_retries=app_settings.provider_max_retries,
        max_payload_bytes=app_settings.provider_max_payload_bytes,
    )
    policy = ProviderPolicy(llm_provider, policy_config)
    app.state.chat_service = ChatService(policy)
    app.state.teaching_service = TeachingService(
        None if app_settings.llm_provider == "mock" and llm_provider_override is None else policy
    )
    app.state.learning_service = LearningService(
        InMemoryLearningRepository(),
        app.state.teaching_service,
    )
    app.include_router(health.router)
    app.include_router(chat.router)
    app.include_router(learning.router)

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
