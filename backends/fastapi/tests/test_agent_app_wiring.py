"""App-factory integration tests for agent endpoint wiring.

Uses TestClient(create_app()) directly — no manually mounted router.
The default in-memory repository gives each app instance isolated state.
"""

from fastapi.testclient import TestClient

from app.main import create_app

# Deterministic JSON bodies committed per AC-6
_CREATE_SESSION = {"title": "Wiring integration test session", "metadata": {"source": "test"}}
_SUBMIT_TASK = {"prompt": "Print hello world in Python"}


def _client() -> TestClient:
    return TestClient(create_app(), raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# AC-2: app.state carries the agent repository
# ---------------------------------------------------------------------------


def test_create_app_has_agent_repository() -> None:
    """AC-4: create_app() attaches agent_repository to app.state."""
    app = create_app()
    assert hasattr(app.state, "agent_repository")


# ---------------------------------------------------------------------------
# AC-2: POST /api/v1/agent/sessions returns 201
# ---------------------------------------------------------------------------


def test_create_session_via_factory_returns_201() -> None:
    """AC-2: TestClient(create_app()).post('/api/v1/agent/sessions') → 201."""
    client = _client()
    response = client.post("/api/v1/agent/sessions", json=_CREATE_SESSION)
    assert response.status_code == 201
    body = response.json()
    assert "session_id" in body
    assert body["status"] == "active"


def test_create_session_minimal_body() -> None:
    client = _client()
    response = client.post("/api/v1/agent/sessions", json={})
    assert response.status_code == 201


# ---------------------------------------------------------------------------
# AC-5: Full workflow via create_app()
# ---------------------------------------------------------------------------


def test_submit_task_via_factory_returns_202() -> None:
    """AC-5: POST /tasks on a real create_app() instance returns 202."""
    client = _client()
    session_id = client.post("/api/v1/agent/sessions", json={}).json()["session_id"]
    response = client.post(
        f"/api/v1/agent/sessions/{session_id}/tasks",
        json=_SUBMIT_TASK,
    )
    assert response.status_code == 202
    body = response.json()
    assert body["session_id"] == session_id
    assert body["status"] == "pending"


def test_list_events_via_factory() -> None:
    """AC-5: GET /events returns ordered events after task submission."""
    client = _client()
    session_id = client.post("/api/v1/agent/sessions", json={}).json()["session_id"]
    client.post(f"/api/v1/agent/sessions/{session_id}/tasks", json=_SUBMIT_TASK)

    response = client.get(f"/api/v1/agent/sessions/{session_id}/events")
    assert response.status_code == 200
    events = response.json()
    assert isinstance(events, list)
    assert len(events) >= 1  # task_accepted event emitted on submission


def test_get_state_returns_submitted_task_id() -> None:
    """AC-4 / AC-5: GET /state returns task_id after submission."""
    client = _client()
    session_id = client.post("/api/v1/agent/sessions", json={}).json()["session_id"]
    task_id = client.post(
        f"/api/v1/agent/sessions/{session_id}/tasks",
        json=_SUBMIT_TASK,
    ).json()["task_id"]

    response = client.get(f"/api/v1/agent/sessions/{session_id}/state")
    assert response.status_code == 200
    body = response.json()
    assert body["session_id"] == session_id
    task_ids = [t["task_id"] for t in body["tasks"]]
    assert task_id in task_ids


# ---------------------------------------------------------------------------
# AC-7 regression: existing routes still work
# ---------------------------------------------------------------------------


def test_health_still_returns_200() -> None:
    """AC-7: GET /api/v1/health unaffected by agent wiring."""
    client = _client()
    response = client.get("/api/v1/health")
    assert response.status_code == 200


def test_chat_still_returns_200() -> None:
    """AC-7: POST /api/v1/chat unaffected by agent wiring."""
    client = _client()
    response = client.post("/api/v1/chat", json={"prompt": "ping"})
    assert response.status_code == 200


def test_learning_state_still_works() -> None:
    """AC-7: GET /api/v1/learning/state unaffected by agent wiring."""
    client = _client()
    response = client.get("/api/v1/learning/state", params={"concept": "present_perfect"})
    # Returns 200 (state with no mastery) or 401 if learner context needed
    assert response.status_code in (200, 401, 422)


# ---------------------------------------------------------------------------
# Multiple create_app() calls don't share agent state
# ---------------------------------------------------------------------------


def test_multiple_create_app_calls_have_isolated_repositories() -> None:
    client1 = _client()
    client2 = _client()

    # Create a session in client1's app
    sid = client1.post("/api/v1/agent/sessions", json={}).json()["session_id"]

    # client2's app knows nothing about it
    response = client2.get(f"/api/v1/agent/sessions/{sid}")
    assert response.status_code == 422
