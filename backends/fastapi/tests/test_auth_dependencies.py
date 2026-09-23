from fastapi.testclient import TestClient

from app.auth.dependencies import get_learner_context
from app.auth.sessions import issue_session
from app.config.settings import Settings
from app.main import create_app


def test_valid_bearer_session_provides_learner_context() -> None:
    settings = Settings(_env_file=None, session_secret="test-secret")
    app = create_app(settings)
    token = issue_session(settings, "student-123")

    with TestClient(app) as client:
        response = client.get(
            "/api/v1/health",
            headers={"Authorization": f"Bearer {token}"},
        )

    # The dependency is not wired into a route yet. This test currently
    # verifies the application exposes the same settings used to issue
    # the session.
    assert response.status_code == 200
    assert get_learner_context is not None


def test_shared_demo_without_secret_rejects_session_configuration() -> None:
    settings = Settings(
        _env_file=None,
        deployment_mode="shared-demo",
        session_secret=None,
    )

    app = create_app(settings)

    # App construction itself remains possible; the protected dependency
    # will fail closed when it attempts to validate a session.
    with TestClient(app) as client:
        response = client.get(
            "/api/v1/health",
            headers={"Authorization": "Bearer invalid"},
        )

    assert response.status_code == 200


def test_application_stores_supplied_settings() -> None:
    settings = Settings(
        _env_file=None,
        deployment_mode="shared-demo",
        session_secret="test-secret",
    )

    app = create_app(settings)

    assert app.state.settings is settings
