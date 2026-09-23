"""Tests for POST /api/v1/session and POST /api/v1/session/bootstrap routes.

All fixtures are deterministic and run without external services.
Signing uses placeholder settings only.
"""

from fastapi.testclient import TestClient

from app.auth.sessions import SessionValidationError, validate_session_token
from app.config.settings import Settings
from app.main import create_app

_SECRET = "test-session-secret-minimum-32-bytes"

# ---------------------------------------------------------------------------
# Fixture helpers (AC-6)
# ---------------------------------------------------------------------------


def _local_client() -> TestClient:
    return TestClient(create_app(Settings(_env_file=None)))


def _shared_demo_client() -> TestClient:
    return TestClient(
        create_app(
            Settings(
                _env_file=None,
                deployment_mode="shared-demo",
                session_secret=_SECRET,
            )
        )
    )


# ---------------------------------------------------------------------------
# AC-1 / AC-5: POST /api/v1/session returns 200 in local and shared-demo mode
# ---------------------------------------------------------------------------


def test_post_session_local_bearer_returns_200() -> None:
    client = _local_client()
    response = client.post("/api/v1/session", json={"transport": "bearer"})
    assert response.status_code == 200


def test_post_session_shared_demo_bearer_returns_200() -> None:
    client = _shared_demo_client()
    response = client.post("/api/v1/session", json={"transport": "bearer"})
    assert response.status_code == 200


def test_post_session_local_cookie_transport_sets_cookie() -> None:
    """AC-1: cookie transport sets a session cookie in the response."""
    client = _local_client()
    response = client.post("/api/v1/session", json={"transport": "cookie"})
    assert response.status_code == 200
    assert "session" in response.cookies
    body = response.json()
    assert body["token_type"] == "cookie"
    assert body["access_token"] is None
    assert body["user_id"]
    assert body["expires_at"]


def test_post_session_bearer_transport_returns_access_token() -> None:
    """AC-1: bearer transport returns access_token in JSON body."""
    client = _local_client()
    response = client.post("/api/v1/session", json={"transport": "bearer"})
    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"] is not None
    assert len(body["access_token"]) > 0
    assert body["user_id"]
    assert body["expires_at"]


def test_post_session_default_transport_is_cookie() -> None:
    """Empty body should default to cookie transport."""
    client = _local_client()
    response = client.post("/api/v1/session", json={})
    assert response.status_code == 200
    assert response.json()["token_type"] == "cookie"


# ---------------------------------------------------------------------------
# AC-4 / AC-2: Issued token validates through sessions.py
# ---------------------------------------------------------------------------


def test_post_session_issued_bearer_token_validates() -> None:
    """Bearer token from the route validates through validate_session_token."""
    settings = Settings(_env_file=None)
    client = TestClient(create_app(settings))
    response = client.post("/api/v1/session", json={"transport": "bearer"})
    assert response.status_code == 200

    token = response.json()["access_token"]
    user_id = response.json()["user_id"]

    claims = validate_session_token(settings, token)
    assert claims.sub == user_id


def test_post_session_tampered_bearer_token_is_rejected() -> None:
    """AC-4: tampered token is rejected by validate_session_token."""
    settings = Settings(_env_file=None)
    client = TestClient(create_app(settings))
    response = client.post("/api/v1/session", json={"transport": "bearer"})
    token = response.json()["access_token"]

    # Corrupt the signature part (last segment of the JWT)
    parts = token.split(".")
    parts[-1] = parts[-1][:-4] + "XXXX"
    tampered = ".".join(parts)

    try:
        validate_session_token(settings, tampered)
        assert False, "Expected SessionValidationError for tampered token"
    except SessionValidationError:
        pass


def test_post_session_expired_token_is_rejected() -> None:
    """AC-4: expired token is rejected when validated with a future timestamp."""
    settings = Settings(_env_file=None, session_ttl_seconds=3600)
    client = TestClient(create_app(settings))
    response = client.post("/api/v1/session", json={"transport": "bearer"})
    token = response.json()["access_token"]

    # Validate at a timestamp past expiry (TTL + 1 second past exp boundary)
    import time
    future_now = int(time.time()) + 3601

    try:
        validate_session_token(settings, token, now=future_now)
        assert False, "Expected SessionValidationError for expired token"
    except SessionValidationError:
        pass


# ---------------------------------------------------------------------------
# AC-3 / AC-5: POST /api/v1/session/bootstrap (WO-006 path) also works
# ---------------------------------------------------------------------------


def test_post_session_bootstrap_path_returns_200() -> None:
    """The WO-006 bootstrap path still issues a valid session."""
    client = _local_client()
    response = client.post("/api/v1/session/bootstrap", json={"transport": "bearer"})
    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"] is not None


def test_post_session_bootstrap_shared_demo_returns_200() -> None:
    client = _shared_demo_client()
    response = client.post("/api/v1/session/bootstrap", json={"transport": "bearer"})
    assert response.status_code == 200


# ---------------------------------------------------------------------------
# AC-7: Protected-mode startup with missing secret fails securely (WO-001)
# ---------------------------------------------------------------------------


def test_shared_demo_without_secret_rejects_configuration() -> None:
    """Settings validator rejects shared-demo with no session_secret at startup."""
    from pydantic import ValidationError
    import pytest

    with pytest.raises(ValidationError):
        Settings(_env_file=None, deployment_mode="shared-demo", session_secret=None)
