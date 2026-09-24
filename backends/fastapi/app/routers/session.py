import secrets
import time
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Request, Response

from app.auth.sessions import issue_anonymous_session
from app.config.settings import Settings
from app.models.error_models import ErrorResponse
from app.models.session_models import SessionBootstrapRequest, SessionBootstrapResponse

router = APIRouter(prefix="/api/v1", tags=["session"])

_COOKIE_NAME = "session"


def _issue_bootstrap(
    settings: Settings,
    transport: Literal["cookie", "bearer"],
    response: Response,
) -> SessionBootstrapResponse:
    subject = f"anon-{secrets.token_urlsafe(8)}"
    now = int(time.time())
    exp = now + settings.session_ttl_seconds
    expires_at = datetime.fromtimestamp(exp, tz=timezone.utc).isoformat()
    token = issue_anonymous_session(settings, subject, now=now)

    if transport == "cookie":
        response.set_cookie(
            key=_COOKIE_NAME,
            value=token,
            httponly=True,
            samesite="lax",
        )
        return SessionBootstrapResponse(
            user_id=subject,
            expires_at=expires_at,
            token_type="cookie",
            access_token=None,
        )
    return SessionBootstrapResponse(
        user_id=subject,
        expires_at=expires_at,
        token_type="bearer",
        access_token=token,
    )


@router.post(
    "/session",
    response_model=SessionBootstrapResponse,
    responses={
        422: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def bootstrap_session(
    body: SessionBootstrapRequest,
    raw_request: Request,
    response: Response,
) -> SessionBootstrapResponse:
    settings: Settings = raw_request.app.state.settings
    return _issue_bootstrap(settings, body.transport, response)


@router.post(
    "/session/bootstrap",
    response_model=SessionBootstrapResponse,
    responses={
        422: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def bootstrap_session_legacy(
    body: SessionBootstrapRequest,
    raw_request: Request,
    response: Response,
) -> SessionBootstrapResponse:
    settings: Settings = raw_request.app.state.settings
    return _issue_bootstrap(settings, body.transport, response)
