from fastapi.testclient import TestClient

from app.auth.sessions import issue_anonymous_session
from app.config.settings import Settings
from app.main import create_app

# Placeholder secret used only in deterministic test fixtures (AC-5)
_SECRET = "test-learning-router-secret-minimum-32b"


def _auth_headers(client: TestClient, user_id: str) -> dict[str, str]:
    token = issue_anonymous_session(
        client.app.state.settings,
        user_id,
    )
    return {"Authorization": f"Bearer {token}"}


def _shared_demo_client() -> TestClient:
    """Shared-demo TestClient with a placeholder signing secret (AC-6)."""
    return TestClient(
        create_app(
            Settings(
                _env_file=None,
                deployment_mode="shared-demo",
                session_secret=_SECRET,
            )
        )
    )


def test_get_learning_state_returns_initial_state(client: TestClient):
    response = client.get(
        "/api/v1/learning/state",
        params={
            "user_id": "student-1",
            "concept": "additive-versioning",
        },
        headers=_auth_headers(client, "student-1"),
    )

    assert response.status_code == 200
    assert response.json() == {
        "user_id": "student-1",
        "concept": "additive-versioning",
        "mastery": 0.32,
        "attempts": 0,
        "correct_count": 0,
        "last_misconception": None,
        "next_review_at": None,
    }


def test_answer_wrong_response_updates_learning_state(client: TestClient):
    response = client.post(
        "/api/v1/learning/answer",
        json={
            "user_id": "student-1",
            "concept": "additive-versioning",
            "answer": "Removing an existing response field",
        },
        headers=_auth_headers(client, "student-1"),
    )

    assert response.status_code == 200

    body = response.json()

    assert body["user_id"] == "student-1"
    assert body["concept"] == "additive-versioning"
    assert body["is_correct"] is False
    assert body["misconception"] is not None
    assert "Removing an existing response field" in body["misconception"]
    assert body["mastery_before"] == 0.32
    assert body["mastery_after"] == 0.27
    assert body["attempts"] == 1
    assert body["correct_count"] == 0
    assert body["next_review_at"] is not None


def test_answer_correct_response_updates_learning_state(client: TestClient):
    headers = _auth_headers(client, "student-1")

    client.post(
        "/api/v1/learning/answer",
        json={
            "user_id": "student-1",
            "concept": "additive-versioning",
            "answer": "Removing an existing response field",
        },
        headers=headers,
    )

    response = client.post(
        "/api/v1/learning/answer",
        json={
            "user_id": "student-1",
            "concept": "additive-versioning",
            "answer": "Adding a new optional field to a response",
        },
        headers=headers,
    )

    assert response.status_code == 200

    body = response.json()

    assert body["is_correct"] is True
    assert body["misconception"] is None
    assert body["mastery_before"] == 0.27
    assert body["mastery_after"] == 0.47000000000000003
    assert body["attempts"] == 2
    assert body["correct_count"] == 1


def test_learning_state_persists_between_requests(client: TestClient):
    headers = _auth_headers(client, "student-1")

    client.post(
        "/api/v1/learning/answer",
        json={
            "user_id": "student-1",
            "concept": "additive-versioning",
            "answer": "Removing an existing response field",
        },
        headers=headers,
    )

    response = client.get(
        "/api/v1/learning/state",
        params={
            "user_id": "student-1",
            "concept": "additive-versioning",
        },
        headers=headers,
    )

    assert response.status_code == 200

    body = response.json()

    assert body["mastery"] == 0.27
    assert body["attempts"] == 1
    assert body["correct_count"] == 0
    assert body["last_misconception"] is not None
    assert body["next_review_at"] is not None


def test_learning_state_isolated_between_students(client: TestClient):
    student_one_headers = _auth_headers(client, "student-1")
    student_two_headers = _auth_headers(client, "student-2")

    client.post(
        "/api/v1/learning/answer",
        json={
            "user_id": "student-1",
            "concept": "additive-versioning",
            "answer": "Adding a new optional field to a response",
        },
        headers=student_one_headers,
    )

    response = client.get(
        "/api/v1/learning/state",
        params={
            "user_id": "student-2",
            "concept": "additive-versioning",
        },
        headers=student_two_headers,
    )

    assert response.status_code == 200

    body = response.json()

    assert body["mastery"] == 0.32
    assert body["attempts"] == 0
    assert body["correct_count"] == 0


def test_client_user_id_cannot_override_authenticated_identity(
    client: TestClient,
):
    headers = _auth_headers(client, "student-1")

    response = client.post(
        "/api/v1/learning/answer",
        json={
            "user_id": "student-2",
            "concept": "additive-versioning",
            "answer": "Adding a new optional field to a response",
        },
        headers=headers,
    )

    assert response.status_code == 200

    body = response.json()

    # The request claimed student-2, but the authenticated session is student-1.
    assert body["user_id"] == "student-1"
    assert body["mastery_after"] == 0.52

    student_one_state = client.get(
        "/api/v1/learning/state",
        params={
            "user_id": "student-1",
            "concept": "additive-versioning",
        },
        headers=headers,
    )

    assert student_one_state.status_code == 200
    assert student_one_state.json()["attempts"] == 1
    assert student_one_state.json()["correct_count"] == 1


# ---------------------------------------------------------------------------
# AC-6: Protected mode — missing session returns 401 with contract envelope
# ---------------------------------------------------------------------------


def test_get_learning_state_without_session_returns_401_in_protected_mode() -> None:
    """GET /api/v1/learning/state without credentials in shared-demo returns 401 (AC-6)."""
    client = _shared_demo_client()
    response = client.get(
        "/api/v1/learning/state",
        params={"concept": "additive-versioning"},
    )
    assert response.status_code == 401
    body = response.json()
    assert body["error"]["code"] == "unauthorized"
    assert body["error"]["message"]


def test_answer_learning_without_session_returns_401_in_protected_mode() -> None:
    """POST /api/v1/learning/answer without credentials in shared-demo returns 401 (AC-6)."""
    client = _shared_demo_client()
    response = client.post(
        "/api/v1/learning/answer",
        json={"concept": "additive-versioning", "answer": "Adding a new optional field"},
    )
    assert response.status_code == 401
    body = response.json()
    assert body["error"]["code"] == "unauthorized"


def test_tampered_bearer_token_returns_401_in_protected_mode() -> None:
    """A structurally valid but signature-tampered JWT is rejected with 401 (AC-4)."""
    client = _shared_demo_client()
    response = client.post(
        "/api/v1/learning/answer",
        json={"concept": "additive-versioning", "answer": "anything"},
        headers={"Authorization": "Bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJhdHRhY2tlciJ9.tampered-signature"},
    )
    assert response.status_code == 401
    body = response.json()
    assert body["error"]["code"] == "unauthorized"


def test_learner_alpha_answer_then_state_reflects_session_identity(
    shared_demo_client: TestClient,
    learner_alpha_headers: dict[str, str],
) -> None:
    """learner-alpha posts /answer then /state — attempts increments and user_id matches session (AC-2)."""
    shared_demo_client.post(
        "/api/v1/learning/answer",
        json={"concept": "additive-versioning", "answer": "Adding a new optional field to a response"},
        headers=learner_alpha_headers,
    )

    state_response = shared_demo_client.get(
        "/api/v1/learning/state",
        params={"concept": "additive-versioning"},
        headers=learner_alpha_headers,
    )

    assert state_response.status_code == 200
    body = state_response.json()
    assert body["user_id"] == "learner-alpha"
    assert body["attempts"] == 1
    assert body["correct_count"] == 1


def test_session_derived_identity_is_isolated_in_protected_mode() -> None:
    """Two learners in shared-demo mode see separate state partitions (AC-4, AC-6)."""
    client = _shared_demo_client()

    alpha_token = issue_anonymous_session(client.app.state.settings, "learner-alpha")
    beta_token = issue_anonymous_session(client.app.state.settings, "learner-beta")
    alpha_headers = {"Authorization": f"Bearer {alpha_token}"}
    beta_headers = {"Authorization": f"Bearer {beta_token}"}

    # learner-alpha answers correctly
    client.post(
        "/api/v1/learning/answer",
        json={"concept": "additive-versioning", "answer": "Adding a new optional field to a response"},
        headers=alpha_headers,
    )

    # learner-beta should still see pristine state
    beta_state = client.get(
        "/api/v1/learning/state",
        params={"concept": "additive-versioning"},
        headers=beta_headers,
    )
    assert beta_state.status_code == 200
    body = beta_state.json()
    assert body["user_id"] == "learner-beta"
    assert body["attempts"] == 0
