from app.auth.sessions import issue_anonymous_session
from app.config.settings import Settings
from app.learning.repository import InMemoryLearningRepository
from app.learning.service import LearningService
from app.main import create_app
from fastapi.testclient import TestClient

# Placeholder secret for deterministic shared-demo fixtures (AC-6)
_SECRET = "test-quiz-router-secret-minimum-32bytes"


def make_client() -> TestClient:
    app = create_app()
    app.state.learning_service = LearningService(
        InMemoryLearningRepository(),
    )
    return TestClient(app)


def _shared_demo_client() -> TestClient:
    """TestClient with shared-demo Settings and a fresh in-memory repo (AC-7)."""
    app = create_app(
        Settings(
            _env_file=None,
            deployment_mode="shared-demo",
            session_secret=_SECRET,
        )
    )
    return TestClient(app)


def auth_headers(client: TestClient, user_id: str) -> dict[str, str]:
    token = issue_anonymous_session(
        client.app.state.settings,
        user_id,
    )
    return {"Authorization": f"Bearer {token}"}


def test_get_learning_quiz_returns_question() -> None:
    client = make_client()

    response = client.get(
        "/api/v1/learning/quiz",
        params={"concept": "provider-fallback-pattern"},
    )

    assert response.status_code == 200

    body = response.json()
    assert body["concept"] == "provider-fallback-pattern"
    assert body["question"]
    assert body["choices"]
    assert body["bloom_level"]


def test_get_learning_quiz_unknown_concept_returns_422() -> None:
    client = make_client()

    response = client.get(
        "/api/v1/learning/quiz",
        params={"concept": "unknown-concept"},
    )

    assert response.status_code == 422


def test_answer_learning_quiz_correct_answer_updates_state() -> None:
    client = make_client()
    headers = auth_headers(client, "quiz-student")

    response = client.post(
        "/api/v1/learning/quiz/answer",
        json={
            "user_id": "quiz-student",
            "concept": "provider-fallback-pattern",
            "selected_answer": "So a flaky LLM provider degrades to a deterministic explanation instead of crashing a live demo",
        },
        headers=headers,
    )

    assert response.status_code == 200

    body = response.json()
    assert body["user_id"] == "quiz-student"
    assert body["concept"] == "provider-fallback-pattern"
    assert body["is_correct"] is True
    assert body["mastery_before"] == 0.32
    assert body["mastery_after"] == 0.52
    assert body["attempts"] == 1
    assert body["correct_count"] == 1


def test_answer_learning_quiz_incorrect_answer_updates_state() -> None:
    client = make_client()
    headers = auth_headers(client, "quiz-student")

    response = client.post(
        "/api/v1/learning/quiz/answer",
        json={
            "user_id": "quiz-student",
            "concept": "provider-fallback-pattern",
            "selected_answer": "Always fail immediately when the primary provider is unavailable",
        },
        headers=headers,
    )

    assert response.status_code == 200

    body = response.json()
    assert body["user_id"] == "quiz-student"
    assert body["is_correct"] is False
    assert body["mastery_before"] == 0.32
    assert body["mastery_after"] == 0.27
    assert body["attempts"] == 1
    assert body["correct_count"] == 0


def test_answer_learning_quiz_accumulates_state() -> None:
    client = make_client()
    headers = auth_headers(client, "quiz-student")

    first_response = client.post(
        "/api/v1/learning/quiz/answer",
        json={
            "user_id": "quiz-student",
            "concept": "provider-fallback-pattern",
            "selected_answer": "So a flaky LLM provider degrades to a deterministic explanation instead of crashing a live demo",
        },
        headers=headers,
    )
    assert first_response.status_code == 200

    second_response = client.post(
        "/api/v1/learning/quiz/answer",
        json={
            "user_id": "quiz-student",
            "concept": "provider-fallback-pattern",
            "selected_answer": "So a flaky LLM provider degrades to a deterministic explanation instead of crashing a live demo",
        },
        headers=headers,
    )

    assert second_response.status_code == 200

    body = second_response.json()
    assert body["user_id"] == "quiz-student"
    assert body["is_correct"] is True
    assert body["mastery_before"] == 0.52
    assert body["mastery_after"] == 0.72
    assert body["attempts"] == 2
    assert body["correct_count"] == 2


def test_answer_learning_quiz_unknown_concept_returns_422() -> None:
    client = make_client()
    headers = auth_headers(client, "quiz-student")

    response = client.post(
        "/api/v1/learning/quiz/answer",
        json={
            "user_id": "quiz-student",
            "concept": "unknown-concept",
            "selected_answer": "anything",
        },
        headers=headers,
    )

    assert response.status_code == 422


def test_client_user_id_cannot_override_authenticated_quiz_identity() -> None:
    client = make_client()
    headers = auth_headers(client, "quiz-student")

    response = client.post(
        "/api/v1/learning/quiz/answer",
        json={
            "user_id": "attacker-selected-student",
            "concept": "provider-fallback-pattern",
            "selected_answer": "So a flaky LLM provider degrades to a deterministic explanation instead of crashing a live demo",
        },
        headers=headers,
    )

    assert response.status_code == 200

    body = response.json()

    assert body["user_id"] == "quiz-student"
    assert body["mastery_after"] == 0.52


def test_answer_learning_practice_requires_authenticated_identity() -> None:
    client = make_client()

    response = client.post(
        "/api/v1/learning/quiz/practice",
        json={
            "user_id": "quiz-student",
            "concept": "provider-fallback-pattern",
            "selected_answer": "anything",
        },
    )

    assert response.status_code == 401


def test_answer_learning_practice_uses_authenticated_identity() -> None:
    client = make_client()
    headers = auth_headers(client, "quiz-student")

    response = client.post(
        "/api/v1/learning/quiz/practice",
        json={
            "user_id": "attacker-selected-student",
            "concept": "provider-fallback-pattern",
            "selected_answer": "anything",
        },
        headers=headers,
    )

    assert response.status_code == 200

    body = response.json()

    assert body["user_id"] == "quiz-student"


def test_answer_learning_retest_requires_authenticated_identity() -> None:
    client = make_client()

    response = client.post(
        "/api/v1/learning/quiz/retest",
        json={
            "user_id": "quiz-student",
            "concept": "additive-versioning",
            "selected_answer": "anything",
        },
    )

    assert response.status_code == 401


def test_answer_learning_retest_uses_authenticated_identity() -> None:
    client = make_client()
    headers = auth_headers(client, "quiz-student")

    response = client.post(
        "/api/v1/learning/quiz/retest",
        json={
            "user_id": "attacker-selected-student",
            "concept": "additive-versioning",
            "selected_answer": "Add the new field without removing or changing existing fields",
        },
        headers=headers,
    )

    assert response.status_code == 200

    body = response.json()

    assert body["user_id"] == "quiz-student"


def test_answer_learning_quiz_without_user_id_uses_trusted_identity() -> None:
    client = make_client()
    headers = auth_headers(client, "learner-a")

    response = client.post(
        "/api/v1/learning/quiz/answer",
        json={
            "concept": "provider-fallback-pattern",
            "selected_answer": "So a flaky LLM provider degrades to a deterministic explanation instead of crashing a live demo",
        },
        headers=headers,
    )

    assert response.status_code == 200

    body = response.json()
    assert body["user_id"] == "learner-a"
    assert body["is_correct"] is True


def test_answer_learning_practice_without_user_id_uses_trusted_identity() -> None:
    client = make_client()
    headers = auth_headers(client, "learner-a")

    response = client.post(
        "/api/v1/learning/quiz/practice",
        json={
            "concept": "provider-fallback-pattern",
            "selected_answer": "anything",
        },
        headers=headers,
    )

    assert response.status_code == 200

    body = response.json()
    assert body["user_id"] == "learner-a"


def test_answer_learning_retest_without_user_id_uses_trusted_identity() -> None:
    client = make_client()
    headers = auth_headers(client, "learner-b")

    response = client.post(
        "/api/v1/learning/quiz/retest",
        json={
            "concept": "additive-versioning",
            "selected_answer": "Add the new field without removing or changing existing fields",
        },
        headers=headers,
    )

    assert response.status_code == 200

    body = response.json()
    assert body["user_id"] == "learner-b"


# ---------------------------------------------------------------------------
# AC-5: Two-session isolation — learner_alpha spoofing learner_beta's user_id
# must not mutate learner_beta's state partition
# ---------------------------------------------------------------------------


def test_quiz_answer_alpha_cannot_mutate_beta_state() -> None:
    """learner_alpha sends user_id=learner_beta but beta's state is unaffected (AC-5)."""
    client = _shared_demo_client()

    alpha_headers = auth_headers(client, "learner-alpha")
    beta_headers = auth_headers(client, "learner-beta")

    # Capture learner-beta's initial state
    beta_initial = client.get(
        "/api/v1/learning/state",
        params={"concept": "provider-fallback-pattern"},
        headers=beta_headers,
    )
    assert beta_initial.status_code == 200
    beta_initial_attempts = beta_initial.json()["attempts"]

    # learner-alpha submits quiz/answer but spoofs user_id as learner-beta
    alpha_response = client.post(
        "/api/v1/learning/quiz/answer",
        json={
            "user_id": "learner-beta",  # spoofed — must be ignored
            "concept": "provider-fallback-pattern",
            "selected_answer": "So a flaky LLM provider degrades to a deterministic explanation instead of crashing a live demo",
        },
        headers=alpha_headers,
    )
    assert alpha_response.status_code == 200
    # Response user_id reflects alpha's session, not the spoofed beta
    assert alpha_response.json()["user_id"] == "learner-alpha"

    # learner-beta's state must be unchanged
    beta_after = client.get(
        "/api/v1/learning/state",
        params={"concept": "provider-fallback-pattern"},
        headers=beta_headers,
    )
    assert beta_after.status_code == 200
    assert beta_after.json()["attempts"] == beta_initial_attempts


# ---------------------------------------------------------------------------
# AC-7: Protected mode — all three quiz mutation endpoints return 401 with
# the contract envelope when no session is provided
# ---------------------------------------------------------------------------


def test_tampered_bearer_token_returns_401_for_quiz_answer() -> None:
    """A tampered JWT is rejected with 401 on quiz/answer in protected mode (AC-4, AC-6)."""
    client = _shared_demo_client()
    response = client.post(
        "/api/v1/learning/quiz/answer",
        json={
            "concept": "provider-fallback-pattern",
            "selected_answer": "So a flaky LLM provider degrades to a deterministic explanation instead of crashing a live demo",
        },
        headers={"Authorization": "Bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJhdHRhY2tlciJ9.tampered-sig"},
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


def test_quiz_answer_without_session_returns_401_in_protected_mode() -> None:
    """POST /api/v1/learning/quiz/answer returns 401 envelope without session (AC-7)."""
    client = _shared_demo_client()
    response = client.post(
        "/api/v1/learning/quiz/answer",
        json={
            "concept": "provider-fallback-pattern",
            "selected_answer": "So a flaky LLM provider degrades to a deterministic explanation instead of crashing a live demo",
        },
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


def test_quiz_practice_without_session_returns_401_in_protected_mode() -> None:
    """POST /api/v1/learning/quiz/practice returns 401 envelope without session (AC-7)."""
    client = _shared_demo_client()
    response = client.post(
        "/api/v1/learning/quiz/practice",
        json={"concept": "provider-fallback-pattern", "selected_answer": "anything"},
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


def test_quiz_retest_without_session_returns_401_in_protected_mode() -> None:
    """POST /api/v1/learning/quiz/retest returns 401 envelope without session (AC-7)."""
    client = _shared_demo_client()
    response = client.post(
        "/api/v1/learning/quiz/retest",
        json={"concept": "additive-versioning", "selected_answer": "anything"},
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"
