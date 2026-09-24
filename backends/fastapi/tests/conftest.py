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


# ---------------------------------------------------------------------------
# Invalid / expired / missing session fixtures (AC-1)
# ---------------------------------------------------------------------------


@pytest.fixture()
def missing_session_headers() -> dict[str, str]:
    """Empty headers dict — no session credential attached.

    Represents a completely unauthenticated request; simulates a client
    that has never bootstrapped a session.
    """
    return {}


@pytest.fixture()
def tampered_session_headers(shared_demo_client: TestClient) -> dict[str, str]:
    """Valid JWT structure but with the signature portion corrupted post-signing.

    Produced by issuing a legitimately signed token and then flipping a
    single character in the base64url signature segment.  This ensures the
    test exercises signature-verification rejection rather than parser
    rejection of a malformed string.
    """
    token = issue_anonymous_session(
        shared_demo_client.app.state.settings,
        "tampered-test-subject",
    )
    header, payload, sig = token.split(".")
    # Flip the last character to a different base64url character
    last_char = sig[-1]
    replacement = "B" if last_char != "B" else "C"
    corrupted_sig = sig[:-1] + replacement
    tampered = f"{header}.{payload}.{corrupted_sig}"
    return {"Authorization": f"Bearer {tampered}"}


@pytest.fixture()
def expired_session_headers(shared_demo_client: TestClient) -> dict[str, str]:
    """Cryptographically valid JWT whose exp claim is well in the past.

    Issued with ``now=0`` (Unix epoch) so ``exp = session_ttl_seconds``
    (28 800 by default), which expired in 1970 and is guaranteed to fail
    the expiry check without relying on wall-clock sleep.
    """
    token = issue_anonymous_session(
        shared_demo_client.app.state.settings,
        "expired-test-subject",
        now=0,  # iat=0, exp=28800 — expired in 1970
    )
    return {"Authorization": f"Bearer {token}"}
