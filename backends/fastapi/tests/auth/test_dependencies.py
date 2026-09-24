"""Tests for app.auth.dependencies.get_learner_context.

Uses minimal FastAPI TestClient routes so cookie, bearer, both-transport,
missing-credential, invalid-token, and local-fallback paths can all be
verified in isolation without touching the full learning router.
"""

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.auth.dependencies import LearnerContext, _LOCAL_DEMO_SUBJECT, get_learner_context
from app.auth.sessions import issue_anonymous_session
from app.config.settings import Settings

# ---------------------------------------------------------------------------
# Fixtures — placeholder settings and token helpers (no real secrets)
# ---------------------------------------------------------------------------

_SECRET = "test-session-secret-minimum-32-bytes"

_LOCAL_SETTINGS = Settings(_env_file=None)
_SHARED_SETTINGS = Settings(
    _env_file=None,
    deployment_mode="shared-demo",
    session_secret=_SECRET,
)


def _make_app(settings: Settings) -> TestClient:
    """Build a minimal FastAPI app with a /whoami route guarded by get_learner_context."""
    app = FastAPI()
    app.state.settings = settings

    @app.get("/whoami")
    def whoami(learner: LearnerContext = Depends(get_learner_context)) -> dict:
        return {"user_id": learner.user_id}

    return TestClient(app)


def _cookie_token(subject: str, settings: Settings = _SHARED_SETTINGS) -> str:
    return issue_anonymous_session(settings, subject)


def _bearer_token(subject: str, settings: Settings = _SHARED_SETTINGS) -> str:
    return issue_anonymous_session(settings, subject)


# ---------------------------------------------------------------------------
# AC-1: Valid session cookie returns LearnerContext.user_id from claims
# ---------------------------------------------------------------------------


def test_valid_cookie_returns_learner_context() -> None:
    client = _make_app(_SHARED_SETTINGS)
    token = _cookie_token("cookie-learner")

    response = client.get("/whoami", cookies={"session": token})

    assert response.status_code == 200
    assert response.json()["user_id"] == "cookie-learner"


# ---------------------------------------------------------------------------
# AC-2: Valid bearer token returns LearnerContext.user_id from claims
# ---------------------------------------------------------------------------


def test_valid_bearer_returns_learner_context() -> None:
    client = _make_app(_SHARED_SETTINGS)
    token = _bearer_token("bearer-learner")

    response = client.get(
        "/whoami",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["user_id"] == "bearer-learner"


# ---------------------------------------------------------------------------
# AC-3: Cookie takes precedence over bearer when both are supplied
# ---------------------------------------------------------------------------


def test_cookie_takes_precedence_over_bearer() -> None:
    client = _make_app(_SHARED_SETTINGS)
    cookie_token = _cookie_token("cookie-priority-user")
    bearer_token = _bearer_token("bearer-secondary-user")

    response = client.get(
        "/whoami",
        cookies={"session": cookie_token},
        headers={"Authorization": f"Bearer {bearer_token}"},
    )

    assert response.status_code == 200
    # Cookie value wins; bearer-secondary-user must NOT appear.
    assert response.json()["user_id"] == "cookie-priority-user"


# ---------------------------------------------------------------------------
# AC-4: Missing credential in protected mode fails before route logic
# ---------------------------------------------------------------------------


def test_missing_credential_in_shared_demo_returns_401() -> None:
    client = _make_app(_SHARED_SETTINGS)

    response = client.get("/whoami")

    assert response.status_code == 401


def test_missing_credential_in_production_returns_401() -> None:
    prod_settings = Settings(
        _env_file=None,
        deployment_mode="production",
        session_secret=_SECRET,
    )
    client = _make_app(prod_settings)

    response = client.get("/whoami")

    assert response.status_code == 401


# ---------------------------------------------------------------------------
# Local mode fallback — no credentials needed, no secret required
# ---------------------------------------------------------------------------


def test_local_mode_no_credentials_returns_demo_learner() -> None:
    client = _make_app(_LOCAL_SETTINGS)

    response = client.get("/whoami")

    assert response.status_code == 200
    assert response.json()["user_id"] == _LOCAL_DEMO_SUBJECT


def test_local_mode_valid_cookie_uses_token_identity() -> None:
    local_settings = Settings(_env_file=None)
    client = _make_app(local_settings)
    # Local mode uses an ephemeral secret; issue with the same settings instance.
    token = issue_anonymous_session(local_settings, "local-named-learner")

    response = client.get("/whoami", cookies={"session": token})

    assert response.status_code == 200
    assert response.json()["user_id"] == "local-named-learner"


# ---------------------------------------------------------------------------
# Invalid / malformed token paths
# ---------------------------------------------------------------------------


def test_invalid_cookie_token_returns_401() -> None:
    client = _make_app(_SHARED_SETTINGS)

    response = client.get("/whoami", cookies={"session": "not.a.valid.jwt"})

    assert response.status_code == 401


def test_invalid_bearer_token_returns_401() -> None:
    client = _make_app(_SHARED_SETTINGS)

    response = client.get(
        "/whoami",
        headers={"Authorization": "Bearer not.a.valid.jwt"},
    )

    assert response.status_code == 401


def test_wrong_secret_bearer_token_returns_401() -> None:
    other_settings = Settings(
        _env_file=None,
        deployment_mode="shared-demo",
        session_secret="different-secret-value-also-32bytes!",
    )
    token = issue_anonymous_session(other_settings, "attacker")

    client = _make_app(_SHARED_SETTINGS)
    response = client.get(
        "/whoami",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 401
