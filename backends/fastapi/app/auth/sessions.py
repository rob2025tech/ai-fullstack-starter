"""Signed anonymous session primitives for the FastAPI backend.

Issues and validates compact JWTs (HS256) using configuration from
:class:`app.config.settings.Settings`.  Framework-independent: can be
exercised without a running FastAPI application.

Exported surface
----------------
- :class:`SessionClaims`        — typed, trusted claim set
- :class:`SessionValidationError` — raised on any invalid token
- :func:`issue_anonymous_session` — produce a signed token
- :func:`validate_session_token`  — verify and decode a token
"""

from __future__ import annotations

import secrets
import time
from dataclasses import dataclass
from typing import Any

import jwt
from jwt.exceptions import InvalidTokenError

from app.config.settings import Settings

_ALGORITHM = "HS256"

# Process-scoped ephemeral secret for local-mode convenience (never written to
# disk or logs; regenerated on each process restart).
_ephemeral_local_secret: str | None = None


class SessionValidationError(Exception):
    """Raised when a session token cannot be issued or validated.

    Intentionally carries no raw token, signature, or secret detail so it
    is safe to propagate to an HTTP layer that surfaces the message.
    """


@dataclass(frozen=True)
class SessionClaims:
    """Decoded, trusted claims extracted from a validated session token."""

    sub: str
    iss: str
    iat: int
    exp: int


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _resolve_secret(settings: Settings) -> str:
    """Return the active signing secret, or raise :class:`SessionValidationError`."""
    global _ephemeral_local_secret  # noqa: PLW0603

    if settings.session_secret:
        return settings.session_secret

    if settings.deployment_mode == "local":
        # Generate a stable process-scoped secret so local tokens survive across
        # multiple calls within the same process without requiring configuration.
        if _ephemeral_local_secret is None:
            _ephemeral_local_secret = secrets.token_urlsafe(32)
        return _ephemeral_local_secret

    raise SessionValidationError(
        "session_secret must be configured for non-local deployments"
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def issue_anonymous_session(
    settings: Settings,
    subject: str,
    *,
    now: int | None = None,
) -> str:
    """Issue a signed anonymous session token for a learner subject.

    Args:
        settings: Application settings providing secret, issuer, and TTL.
        subject: Learner identifier embedded as the ``sub`` JWT claim.
        now: Optional Unix timestamp to use as the issuance time.  When
            omitted the real system clock is used.  Inject a fixed value
            in unit tests to produce deterministic tokens.

    Returns:
        A compact JWT string (``header.payload.signature``).

    Raises:
        :class:`SessionValidationError`: If *subject* is empty or blank,
            or if no signing secret is available.
    """
    if not subject or not subject.strip():
        raise SessionValidationError("subject must not be empty")

    secret = _resolve_secret(settings)

    if now is None:
        now = int(time.time())

    payload: dict[str, Any] = {
        "sub": subject,
        "iss": settings.session_issuer,
        "iat": now,
        "exp": now + settings.session_ttl_seconds,
    }

    return jwt.encode(payload, secret, algorithm=_ALGORITHM)


def validate_session_token(
    settings: Settings,
    token: str,
    *,
    now: int | None = None,
) -> SessionClaims:
    """Validate a signed session token and return trusted claims.

    Args:
        settings: Application settings providing secret and issuer.
        token: Compact JWT string to validate.
        now: Optional Unix timestamp to use when checking expiry.  When
            provided, PyJWT's built-in clock is bypassed and this value is
            used instead.  Inject a fixed value in unit tests to control
            expiry boundaries without sleeping.

    Returns:
        A :class:`SessionClaims` instance with decoded, trusted claims.

    Raises:
        :class:`SessionValidationError`: For expired, tampered, malformed,
            wrong-issuer, or missing-subject tokens, or when no signing
            secret is available.
    """
    secret = _resolve_secret(settings)

    # When a custom ``now`` is injected, disable PyJWT's built-in expiry check
    # so we can perform the boundary comparison with the provided timestamp.
    decode_options: dict[str, Any] = {}
    if now is not None:
        decode_options["verify_exp"] = False

    try:
        payload = jwt.decode(
            token,
            secret,
            algorithms=[_ALGORITHM],
            issuer=settings.session_issuer,
            options=decode_options,
        )
    except jwt.ExpiredSignatureError as exc:
        raise SessionValidationError("session token has expired") from exc
    except jwt.InvalidIssuerError as exc:
        raise SessionValidationError("session token issuer mismatch") from exc
    except InvalidTokenError as exc:
        raise SessionValidationError("invalid session token") from exc

    # Manual expiry check when a custom ``now`` is provided.
    if now is not None:
        exp = payload.get("exp")
        if not isinstance(exp, int) or now >= exp:
            raise SessionValidationError("session token has expired")

    sub = payload.get("sub")
    if not isinstance(sub, str) or not sub:
        raise SessionValidationError("session token missing or empty subject")

    return SessionClaims(
        sub=sub,
        iss=str(payload.get("iss", "")),
        iat=int(payload.get("iat", 0)),
        exp=int(payload.get("exp", 0)),
    )
