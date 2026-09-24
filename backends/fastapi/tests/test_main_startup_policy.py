"""Tests for create_app startup policy.

Covers: mode validation, app.state.settings, credentialed CORS,
docs URL policy, health regression, and HTTP 401 contract envelope.
All fixtures use placeholder settings only — no real secrets.
"""

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.config.settings import Settings
from app.main import create_app

# ---------------------------------------------------------------------------
# Placeholder signing secret — never a real value (AC-5)
# ---------------------------------------------------------------------------

_SECRET = "test-startup-policy-secret-minimum-32-bytes"


# ---------------------------------------------------------------------------
# Fixture helpers
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
# AC-1: Protected-mode app construction fails when session_secret is missing
# ---------------------------------------------------------------------------


def test_shared_demo_without_secret_fails_before_app_returns() -> None:
    """create_app raises ValidationError for shared-demo with no secret (AC-1)."""
    with pytest.raises(ValidationError):
        create_app(
            Settings(_env_file=None, deployment_mode="shared-demo", session_secret=None)
        )


def test_production_without_secret_fails_before_app_returns() -> None:
    """create_app raises ValidationError for production with no secret (AC-1)."""
    with pytest.raises(ValidationError):
        create_app(
            Settings(_env_file=None, deployment_mode="production", session_secret=None)
        )


# ---------------------------------------------------------------------------
# AC-2: Local mode returns app with correct settings on app.state
# ---------------------------------------------------------------------------


def test_local_app_state_settings_deployment_mode() -> None:
    """app.state.settings.deployment_mode is 'local' for a local-mode app (AC-2)."""
    app = create_app(Settings(_env_file=None))
    assert app.state.settings.deployment_mode == "local"


def test_shared_demo_app_state_settings_deployment_mode() -> None:
    """app.state.settings.deployment_mode is 'shared-demo' for shared-demo app (AC-2)."""
    app = create_app(
        Settings(_env_file=None, deployment_mode="shared-demo", session_secret=_SECRET)
    )
    assert app.state.settings.deployment_mode == "shared-demo"


# ---------------------------------------------------------------------------
# AC-3: Auth failure returns HTTP 401 with error.code == "unauthorized"
# ---------------------------------------------------------------------------


def test_auth_failure_returns_401_contract_envelope() -> None:
    """Missing credentials on a protected learning route return the contract envelope (AC-3)."""
    client = _shared_demo_client()
    # GET /api/v1/learning/state requires session auth; no credentials supplied
    response = client.get(
        "/api/v1/learning/state", params={"concept": "additive-versioning"}
    )
    assert response.status_code == 401
    body = response.json()
    assert body["error"]["code"] == "unauthorized"
    assert body["error"]["message"]


def test_auth_failure_on_learning_answer_returns_401_envelope() -> None:
    """POST /api/v1/learning/answer without session returns 401 envelope (AC-3)."""
    client = _shared_demo_client()
    response = client.post(
        "/api/v1/learning/answer",
        json={"concept": "additive-versioning", "answer": "some answer"},
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


# ---------------------------------------------------------------------------
# AC-4: Health check returns 200 in local mode (regression)
# ---------------------------------------------------------------------------


def test_health_returns_200_local_mode() -> None:
    """GET /api/v1/health returns 200 for a local-mode app (AC-4)."""
    client = _local_client()
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"


def test_health_returns_200_shared_demo_mode() -> None:
    """GET /api/v1/health returns 200 even in shared-demo mode (AC-4)."""
    client = _shared_demo_client()
    response = client.get("/api/v1/health")
    assert response.status_code == 200


# ---------------------------------------------------------------------------
# AC-6: CORSMiddleware with allow_credentials=True; docs URL policy
# ---------------------------------------------------------------------------


def test_local_docs_accessible() -> None:
    """/docs and /redoc are available in local mode (AC-6)."""
    client = _local_client()
    assert client.get("/docs").status_code == 200
    assert client.get("/redoc").status_code == 200


def test_protected_docs_disabled() -> None:
    """/docs and /redoc return 404 in shared-demo mode (AC-6)."""
    client = _shared_demo_client()
    assert client.get("/docs").status_code == 404
    assert client.get("/redoc").status_code == 404


def test_cors_allow_credentials_header() -> None:
    """CORS response includes Access-Control-Allow-Credentials: true (AC-6)."""
    client = _local_client()
    response = client.get(
        "/api/v1/health",
        headers={"Origin": "http://localhost:3000"},
    )
    assert response.headers.get("access-control-allow-credentials") == "true"
