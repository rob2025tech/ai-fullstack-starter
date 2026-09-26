from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.agent.approvals import ApprovalService
from app.agent.loop import AgentLoop, AgentLoopConfig
from app.agent.repository import AgentRepository
from app.agent.tools.registry import ToolRegistry
from app.agent.worker import LocalAgentWorker
from app.config.settings import Settings, settings
from app.core.errors import BackendError
from app.learning.repository import InMemoryLearningRepository
from app.models.error_models import Error, ErrorResponse
from app.providers.llm.base import LLMProvider
from app.providers.llm.policy import ProviderPolicy, ProviderPolicyConfig
from app.providers.llm.registry import build_llm_provider
from app.routers import agent, agent_events, chat, health, learning
from app.learning.service import LearningService
from app.services.chat_service import ChatService
from app.services.teaching_service import TeachingService


def _error_body(code: str, message: str) -> dict:
    return ErrorResponse(error=Error(code=code, message=message)).model_dump(mode="json")


def create_app(
    app_settings: Settings | None = None,
    llm_provider_override: LLMProvider | None = None,
    agent_repository_override: AgentRepository | None = None,
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
    agent_repository_override:
        If provided, use this ``AgentRepository`` instance instead of creating
        a fresh in-memory one.  Useful for tests that need a file-backed or
        pre-populated repository.
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
    app.state.agent_repository = (
        agent_repository_override if agent_repository_override is not None
        else AgentRepository()
    )
    app.state.approval_service = ApprovalService(app.state.agent_repository)
    app.state.tool_registry = ToolRegistry()
    agent_loop = AgentLoop(
        provider=policy,
        registry=app.state.tool_registry,
        approval_service=app.state.approval_service,
        repo=app.state.agent_repository,
        config=AgentLoopConfig(),
    )
    app.state.agent_loop = agent_loop
    app.state.agent_worker = LocalAgentWorker(agent_loop, app.state.agent_repository)
    app.include_router(health.router)
    app.include_router(chat.router)
    app.include_router(learning.router)
    app.include_router(agent.router)
    app.include_router(agent_events.router)

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
