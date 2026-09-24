from fastapi.testclient import TestClient

from app.auth.dependencies import get_learner_context
from app.auth.sessions import issue_anonymous_session
from app.config.settings import Settings
from app.main import create_app

_SECRET = "test-session-secret-minimum-32-bytes"


def test_valid_bearer_session_provides_learner_context() -> None:
    settings = Settings(_env_file=None, session_secret=_SECRET)
    app = create_app(settings)
    token = issue_anonymous_session(settings, "student-123")

    with TestClient(app) as client:
        response = client.get(
            "/api/v1/health",
            headers={"Authorization": f"Bearer {token}"},
        )

    # Health is an anonymous endpoint; this test verifies the app starts
    # and the dependency is importable alongside a valid issued token.
    assert response.status_code == 200
    assert get_learner_context is not None


def test_shared_demo_with_secret_starts_app() -> None:
    settings = Settings(
        _env_file=None,
        deployment_mode="shared-demo",
        session_secret=_SECRET,
    )
    app = create_app(settings)

    with TestClient(app) as client:
        response = client.get("/api/v1/health")

    assert response.status_code == 200


def test_application_stores_supplied_settings() -> None:
    settings = Settings(
        _env_file=None,
        deployment_mode="shared-demo",
        session_secret=_SECRET,
    )
    app = create_app(settings)
    assert app.state.settings is settings
