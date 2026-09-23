from fastapi.testclient import TestClient

from app.auth.sessions import issue_anonymous_session


def _auth_headers(client: TestClient, user_id: str) -> dict[str, str]:
    token = issue_anonymous_session(
        client.app.state.settings,
        user_id,
    )
    return {"Authorization": f"Bearer {token}"}


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
