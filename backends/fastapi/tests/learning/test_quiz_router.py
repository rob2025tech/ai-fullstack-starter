from app.auth.sessions import issue_session
from app.learning.repository import InMemoryLearningRepository
from app.learning.service import LearningService
from app.main import create_app
from fastapi.testclient import TestClient


def make_client() -> TestClient:
    app = create_app()
    app.state.learning_service = LearningService(
        InMemoryLearningRepository(),
    )
    return TestClient(app)


def auth_headers(client: TestClient, user_id: str) -> dict[str, str]:
    token = issue_session(
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
    client = _shared_demo_client()

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
    client = _shared_demo_client()

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
