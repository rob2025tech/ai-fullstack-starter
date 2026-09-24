import pytest
from fastapi.testclient import TestClient

from app.auth.sessions import issue_anonymous_session
from app.config.settings import Settings
from app.main import create_app

# ---------------------------------------------------------------------------
# Shared deterministic test constants (AC-4)
# ---------------------------------------------------------------------------

# Placeholder secret for protected-mode test fixtures — never used in production.
_SHARED_SECRET = "test-shared-demo-secret-minimum-32bytes"

# Known concept that exists in quiz_content.py — used across learning suites.
KNOWN_CONCEPT = "additive-versioning"


# ---------------------------------------------------------------------------
# Local-mode client fixture (existing)
# ---------------------------------------------------------------------------


@pytest.fixture()
def client() -> TestClient:
    return TestClient(create_app(Settings(_env_file=None)))


# ---------------------------------------------------------------------------
# Shared-demo client and signed session fixtures (AC-4)
# ---------------------------------------------------------------------------


@pytest.fixture()
def shared_demo_client() -> TestClient:
    """TestClient in shared-demo deployment mode with a deterministic signing secret."""
    return TestClient(
        create_app(
            Settings(
                _env_file=None,
                deployment_mode="shared-demo",
                session_secret=_SHARED_SECRET,
            )
        )
    )


@pytest.fixture()
def learner_alpha_headers(shared_demo_client: TestClient) -> dict[str, str]:
    """Signed bearer token headers for the deterministic 'learner-alpha' subject."""
    token = issue_anonymous_session(
        shared_demo_client.app.state.settings,
        "learner-alpha",
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def learner_beta_headers(shared_demo_client: TestClient) -> dict[str, str]:
    """Signed bearer token headers for the deterministic 'learner-beta' subject."""
    token = issue_anonymous_session(
        shared_demo_client.app.state.settings,
        "learner-beta",
    )
    return {"Authorization": f"Bearer {token}"}
