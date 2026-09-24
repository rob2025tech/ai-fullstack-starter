"""Startup settings matrix tests.

Proves three explicit deployment-mode profiles:
  1. local without secret — starts successfully, serves anonymous traffic
  2. shared-demo without secret — raises ValidationError before app is returned
  3. shared-demo with valid secret — starts successfully, health returns 200

Covers the whitespace-only secret edge case and confirms local mode never
requires a signing secret or OPENAI_API_KEY.  No real secrets are used.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.config.settings import Settings
from app.main import create_app

# ---------------------------------------------------------------------------
# Deterministic placeholder — never a real value (AC-5)
# ---------------------------------------------------------------------------

_PLACEHOLDER_SECRET = "test-startup-matrix-secret-minimum-32-bytes"


# ---------------------------------------------------------------------------
# Profile 1: local without secret (AC-1, AC-6)
# ---------------------------------------------------------------------------


def test_local_no_secret_creates_app_successfully() -> None:
    """create_app with local mode and no session_secret returns a FastAPI app (AC-1, AC-6)."""
    app = create_app(Settings(_env_file=None, deployment_mode="local", session_secret=None))
    assert isinstance(app, FastAPI)
    assert app.state.settings.deployment_mode == "local"


def test_local_no_secret_serves_health() -> None:
    """Local mode without a secret serves GET /api/v1/health → 200 (AC-4)."""
    app = create_app(Settings(_env_file=None, deployment_mode="local"))
    response = TestClient(app).get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_local_no_openai_key_creates_app_successfully() -> None:
    """Local mode with the deterministic mock provider requires no OPENAI_API_KEY (AC-5)."""
    app = create_app(
        Settings(_env_file=None, deployment_mode="local", openai_api_key=None)
    )
    assert isinstance(app, FastAPI)


# ---------------------------------------------------------------------------
# Profile 2: shared-demo without secret (AC-2, AC-6)
# ---------------------------------------------------------------------------


def test_shared_demo_missing_secret_raises_validation_error() -> None:
    """Settings(..., deployment_mode='shared-demo', session_secret=None) raises ValidationError (AC-2, AC-6)."""
    with pytest.raises(ValidationError) as exc_info:
        Settings(_env_file=None, deployment_mode="shared-demo", session_secret=None)
    assert "session_secret" in str(exc_info.value)
    assert "shared-demo" in str(exc_info.value)


def test_shared_demo_whitespace_secret_raises_validation_error() -> None:
    """Whitespace-only session_secret is treated the same as a missing secret (edge case)."""
    with pytest.raises(ValidationError):
        Settings(_env_file=None, deployment_mode="shared-demo", session_secret="   ")


def test_shared_demo_empty_string_secret_raises_validation_error() -> None:
    """Empty-string session_secret raises ValidationError in shared-demo mode (AC-2)."""
    with pytest.raises(ValidationError):
        Settings(_env_file=None, deployment_mode="shared-demo", session_secret="")


def test_production_missing_secret_raises_validation_error() -> None:
    """Production mode without a session_secret raises ValidationError (AC-6)."""
    with pytest.raises(ValidationError):
        Settings(_env_file=None, deployment_mode="production", session_secret=None)


# ---------------------------------------------------------------------------
# Profile 3: shared-demo with valid secret (AC-3, AC-6)
# ---------------------------------------------------------------------------


def test_shared_demo_valid_secret_creates_app_successfully() -> None:
    """create_app with shared-demo + non-empty secret returns a FastAPI app (AC-3, AC-6)."""
    app = create_app(
        Settings(
            _env_file=None,
            deployment_mode="shared-demo",
            session_secret=_PLACEHOLDER_SECRET,
        )
    )
    assert isinstance(app, FastAPI)
    assert app.state.settings.deployment_mode == "shared-demo"
    assert app.state.settings.requires_session_auth() is True


def test_shared_demo_valid_secret_health_returns_200() -> None:
    """Shared-demo app with a valid secret serves GET /api/v1/health → 200 (AC-3, AC-4)."""
    app = create_app(
        Settings(
            _env_file=None,
            deployment_mode="shared-demo",
            session_secret=_PLACEHOLDER_SECRET,
        )
    )
    response = TestClient(app).get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_shared_demo_valid_secret_blocks_unauthenticated_learning() -> None:
    """Protected learning endpoint returns 401 even when the app constructed successfully (AC-3)."""
    app = create_app(
        Settings(
            _env_file=None,
            deployment_mode="shared-demo",
            session_secret=_PLACEHOLDER_SECRET,
        )
    )
    response = TestClient(app).get(
        "/api/v1/learning/state", params={"concept": "additive-versioning"}
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"
