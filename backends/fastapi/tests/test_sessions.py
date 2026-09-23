import base64
import json

import pytest

from app.auth.sessions import (
    SessionError,
    issue_session,
    validate_session,
)
from app.config.settings import Settings


def test_issue_and_validate_session() -> None:
    settings = Settings(_env_file=None, session_secret="test-secret")

    token = issue_session(settings, "student-123")
    session = validate_session(settings, token)

    assert session.user_id == "student-123"
    assert session.expires_at > 0


def test_tampered_session_is_rejected() -> None:
    settings = Settings(_env_file=None, session_secret="test-secret")

    token = issue_session(settings, "student-123")
    version, payload, signature = token.split(".")
    tampered_payload = base64.urlsafe_b64encode(
        json.dumps(
            {
                "ver": "v1",
                "sub": "attacker",
                "iat": 1,
                "exp": 4_000_000_000,
            },
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
    ).rstrip(b"=").decode()

    tampered = f"{version}.{tampered_payload}.{signature}"

    with pytest.raises(SessionError, match="Invalid session signature"):
        validate_session(settings, tampered)


def test_wrong_secret_is_rejected() -> None:
    issuer = Settings(_env_file=None, session_secret="issuer-secret")
    validator = Settings(_env_file=None, session_secret="different-secret")

    token = issue_session(issuer, "student-123")

    with pytest.raises(SessionError, match="Invalid session signature"):
        validate_session(validator, token)


def test_expired_session_is_rejected() -> None:
    settings = Settings(
        _env_file=None,
        session_secret="test-secret",
        session_ttl_seconds=0,
    )

    with pytest.raises(SessionError, match="session_ttl_seconds"):
        issue_session(settings, "student-123")


def test_shared_demo_requires_session_secret() -> None:
    settings = Settings(
        _env_file=None,
        deployment_mode="shared-demo",
        session_secret=None,
    )

    with pytest.raises(
        SessionError,
        match="SESSION_SECRET must be configured",
    ):
        issue_session(settings, "student-123")


def test_production_requires_session_secret() -> None:
    settings = Settings(
        _env_file=None,
        deployment_mode="production",
        session_secret=None,
    )

    with pytest.raises(
        SessionError,
        match="SESSION_SECRET must be configured",
    ):
        issue_session(settings, "student-123")


def test_local_mode_can_issue_without_configured_secret() -> None:
    settings = Settings(
        _env_file=None,
        deployment_mode="local",
        session_secret=None,
    )

    token = issue_session(settings, "local-student")
    session = validate_session(settings, token)

    assert session.user_id == "local-student"
