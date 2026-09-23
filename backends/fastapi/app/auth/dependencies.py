"""FastAPI dependency providers for session-authenticated requests."""

from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import APIKeyCookie, HTTPAuthorizationCredentials, HTTPBearer

from app.auth.sessions import SessionValidationError, validate_session_token
from app.config.settings import Settings

_COOKIE_SCHEME = APIKeyCookie(name="session", auto_error=False)
_BEARER_SCHEME = HTTPBearer(auto_error=False)

# Deterministic subject used only in local development mode when no token is
# supplied.  Never used in shared-demo or production modes.
_LOCAL_DEMO_SUBJECT = "demo-student"


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


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required",
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_learner_context(
    request: Request,
    cookie_token: str | None = Depends(_COOKIE_SCHEME),
    bearer_creds: HTTPAuthorizationCredentials | None = Depends(_BEARER_SCHEME),
) -> LearnerContext:
    """Extract and validate learner identity from session cookie or bearer token.

    Cookie transport takes precedence when both credentials are present.
    In local deployment mode with no credentials, returns a deterministic
    demo learner without requiring a signing secret.
    """
    settings = _settings_from_request(request)

    # Cookie takes precedence over bearer when both are supplied.
    if cookie_token is not None:
        try:
            claims = validate_session_token(settings, cookie_token)
            return LearnerContext(user_id=claims.sub)
        except SessionValidationError as exc:
            raise _unauthorized() from exc

    if bearer_creds is not None:
        try:
            claims = validate_session_token(settings, bearer_creds.credentials)
            return LearnerContext(user_id=claims.sub)
        except SessionValidationError as exc:
            raise _unauthorized() from exc

    # No credentials supplied.
    if settings.requires_session_auth():
        raise _unauthorized()

    # Local mode: return deterministic demo learner without a signing secret.
    return LearnerContext(user_id=_LOCAL_DEMO_SUBJECT)
