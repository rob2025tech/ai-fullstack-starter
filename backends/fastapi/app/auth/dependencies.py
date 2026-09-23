"""FastAPI dependency providers for session-authenticated requests."""

from dataclasses import dataclass

from fastapi import Header, HTTPException, Request, status

from app.auth.sessions import SessionValidationError, validate_session_token
from app.config.settings import Settings


@dataclass(frozen=True)
class LearnerContext:
    user_id: str


def _settings_from_request(request: Request) -> Settings:
    settings = getattr(request.app.state, "settings", None)
    if settings is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Application settings are unavailable",
        )
    return settings


def get_learner_context(
    request: Request,
    authorization: str | None = Header(default=None),
) -> LearnerContext:
    settings = _settings_from_request(request)

    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )

    scheme, _, token = authorization.partition(" ")

    if scheme.lower() != "bearer" or not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication scheme",
        )

    try:
        claims = validate_session_token(settings, token)
    except SessionValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session",
        ) from exc

    return LearnerContext(user_id=claims.sub)
