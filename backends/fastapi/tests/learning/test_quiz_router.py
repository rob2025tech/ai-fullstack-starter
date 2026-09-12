from app.main import create_app
from app.learning.service import LearningService
from app.learning.repository import InMemoryLearningRepository
from fastapi.testclient import TestClient
# from datetime import datetime, timezone


def make_client() -> TestClient:
    app = create_app()
    app.state.learning_service = LearningService(
        InMemoryLearningRepository(),
    )
    return TestClient(app)


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
    assert body["bloom_level"] == "analyze"
    assert "correct_answer" not in body


def test_get_learning_quiz_unknown_concept_returns_422() -> None:
    client = make_client()

    response = client.get(
        "/api/v1/learning/quiz",
        params={"concept": "does-not-exist"},
    )

    assert response.status_code == 422

    body = response.json()

    assert body["error"]["code"] == "invalid_request"


def test_answer_learning_quiz_correct_updates_mastery() -> None:
    client = make_client()

    quiz_response = client.get(
        "/api/v1/learning/quiz",
        params={"concept": "provider-fallback-pattern"},
    )
    assert quiz_response.status_code == 200

    question = quiz_response.json()

    response = client.post(
        "/api/v1/learning/quiz/answer",
        json={
            "user_id": "quiz-student",
            "concept": "provider-fallback-pattern",
            "selected_answer": (
                "So a flaky LLM provider degrades to a deterministic "
                "explanation instead of crashing a live demo"
            ),
        },
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
    assert body["next_review_at"]

    # The GET response must never expose the answer.
    assert "correct_answer" not in question


def test_answer_learning_quiz_incorrect_updates_mastery() -> None:
    client = make_client()

    response = client.post(
        "/api/v1/learning/quiz/answer",
        json={
            "user_id": "quiz-student",
            "concept": "provider-fallback-pattern",
            "selected_answer": (
                "Because FastAPI requires every exception to be caught "
                "inside services"
            ),
        },
    )

    assert response.status_code == 200

    body = response.json()

    assert body["is_correct"] is False
    assert body["mastery_before"] == 0.32
    assert body["mastery_after"] == 0.27
    assert body["attempts"] == 1
    assert body["correct_count"] == 0
    assert body["next_review_at"]


def test_answer_learning_quiz_accumulates_learning_state() -> None:
    client = make_client()

    correct_answer = (
        "So a flaky LLM provider degrades to a deterministic "
        "explanation instead of crashing a live demo"
    )

    first = client.post(
        "/api/v1/learning/quiz/answer",
        json={
            "user_id": "quiz-student",
            "concept": "provider-fallback-pattern",
            "selected_answer": correct_answer,
        },
    )

    assert first.status_code == 200
    assert first.json()["mastery_after"] == 0.52

    second = client.post(
        "/api/v1/learning/quiz/answer",
        json={
            "user_id": "quiz-student",
            "concept": "provider-fallback-pattern",
            "selected_answer": correct_answer,
        },
    )

    assert second.status_code == 200

    body = second.json()

    assert body["is_correct"] is True
    assert body["mastery_before"] == 0.52
    assert body["mastery_after"] == 0.72
    assert body["attempts"] == 2
    assert body["correct_count"] == 2


def test_answer_learning_quiz_unknown_concept_returns_422() -> None:
    client = make_client()

    response = client.post(
        "/api/v1/learning/quiz/answer",
        json={
            "user_id": "quiz-student",
            "concept": "does-not-exist",
            "selected_answer": "anything",
        },
    )

    assert response.status_code == 422

    body = response.json()

    assert body["error"]["code"] == "invalid_request"
