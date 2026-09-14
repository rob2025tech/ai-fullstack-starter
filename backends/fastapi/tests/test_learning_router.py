from fastapi.testclient import TestClient


def test_get_learning_state_returns_initial_state(client: TestClient):
    response = client.get(
        "/api/v1/learning/state",
        params={
            "user_id": "student-1",
            "concept": "additive-versioning",
        },
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
    client.post(
        "/api/v1/learning/answer",
        json={
            "user_id": "student-1",
            "concept": "additive-versioning",
            "answer": "Removing an existing response field",
        },
    )

    response = client.post(
        "/api/v1/learning/answer",
        json={
            "user_id": "student-1",
            "concept": "additive-versioning",
            "answer": "Adding a new optional field to a response",
        },
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
    client.post(
        "/api/v1/learning/answer",
        json={
            "user_id": "student-1",
            "concept": "additive-versioning",
            "answer": "Removing an existing response field",
        },
    )

    response = client.get(
        "/api/v1/learning/state",
        params={
            "user_id": "student-1",
            "concept": "additive-versioning",
        },
    )

    assert response.status_code == 200

    body = response.json()

    assert body["mastery"] == 0.27
    assert body["attempts"] == 1
    assert body["correct_count"] == 0
    assert body["last_misconception"] is not None
    assert body["next_review_at"] is not None


def test_learning_state_isolated_between_students(client: TestClient):
    client.post(
        "/api/v1/learning/answer",
        json={
            "user_id": "student-1",
            "concept": "additive-versioning",
            "answer": "Adding a new optional field to a response",
        },
    )

    response = client.get(
        "/api/v1/learning/state",
        params={
            "user_id": "student-2",
            "concept": "additive-versioning",
        },
    )

    assert response.status_code == 200

    body = response.json()

    assert body["mastery"] == 0.32
    assert body["attempts"] == 0
    assert body["correct_count"] == 0
