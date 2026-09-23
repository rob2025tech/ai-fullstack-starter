import base64
import hashlib
import hmac
import json
import secrets
import time
from dataclasses import dataclass
from typing import Final

from app.config.settings import Settings

SESSION_VERSION: Final = "v1"
SESSION_ALGORITHM: Final = "HS256"

_ephemeral_session_secret: str | None = None


class SessionError(ValueError):
    """Raised when a session token is invalid or cannot be issued."""


@dataclass(frozen=True)
class Session:
    user_id: str
    expires_at: int


def _encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode((value + padding).encode("ascii"))


def _sign(signing_input: str, secret: str) -> str:
    signature = hmac.new(
        secret.encode("utf-8"),
        signing_input.encode("ascii"),
        hashlib.sha256,
    ).digest()
    return _encode(signature)


def _get_signing_secret(settings: Settings) -> str:
    global _ephemeral_session_secret

    if settings.session_secret:
        return settings.session_secret

    if settings.deployment_mode == "local":
        if _ephemeral_session_secret is None:
            _ephemeral_session_secret = secrets.token_urlsafe(32)
        return _ephemeral_session_secret

    raise SessionError(
        "SESSION_SECRET must be configured for shared-demo or production"
    )


def validate_session_configuration(settings: Settings) -> None:
    if settings.session_ttl_seconds <= 0:
        raise SessionError("session_ttl_seconds must be greater than zero")

    if settings.deployment_mode != "local" and not settings.session_secret:
        raise SessionError(
            "SESSION_SECRET must be configured for shared-demo or production"
        )


def issue_session(settings: Settings, user_id: str) -> str:
    if not user_id:
        raise SessionError("user_id must not be empty")

    validate_session_configuration(settings)

    now = int(time.time())
    expires_at = now + settings.session_ttl_seconds

    payload = {
        "ver": SESSION_VERSION,
        "sub": user_id,
        "iat": now,
        "exp": expires_at,
    }

    payload_bytes = json.dumps(
        payload,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")

    encoded_payload = _encode(payload_bytes)
    signing_input = f"{SESSION_VERSION}.{encoded_payload}"
    signature = _sign(signing_input, _get_signing_secret(settings))

    return f"{signing_input}.{signature}"


def validate_session(settings: Settings, token: str) -> Session:
    validate_session_configuration(settings)

    parts = token.split(".")
    if len(parts) != 3:
        raise SessionError("Malformed session token")

    version, encoded_payload, provided_signature = parts

    if version != SESSION_VERSION:
        raise SessionError("Unsupported session token version")

    signing_input = f"{version}.{encoded_payload}"
    expected_signature = _sign(signing_input, _get_signing_secret(settings))

    if not hmac.compare_digest(provided_signature, expected_signature):
        raise SessionError("Invalid session signature")

    try:
        payload = json.loads(_decode(encoded_payload))
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SessionError("Malformed session payload") from exc

    if payload.get("ver") != SESSION_VERSION:
        raise SessionError("Invalid session version")

    user_id = payload.get("sub")
    expires_at = payload.get("exp")

    if not isinstance(user_id, str) or not user_id:
        raise SessionError("Invalid session subject")

    if not isinstance(expires_at, int):
        raise SessionError("Invalid session expiration")

    if expires_at <= int(time.time()):
        raise SessionError("Session expired")

    return Session(user_id=user_id, expires_at=expires_at)
