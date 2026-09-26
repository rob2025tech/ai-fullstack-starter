"""Router tests for GET /api/v1/agent/sessions/{session_id}/tasks/{task_id}/events
and GET /api/v1/agent/sessions/{session_id}/tasks/{task_id}/events/stream.

AC-2: JSON replay returns 200, application/json, events ordered [1, 2, 3].
AC-3: SSE stream returns 200, text/event-stream, typed frames with task_id+sequence.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app.agent.repository import AgentRepository
from app.main import create_app
from tests.fixtures.agent_events import SESSION_ID, TASK_ID, create_task_events


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def client_with_events() -> TestClient:
    """TestClient with a pre-populated AgentRepository (6 events, terminal=error)."""
    repo = AgentRepository()
    create_task_events(repo, terminal="error")
    app = create_app(agent_repository_override=repo)
    return TestClient(app)


@pytest.fixture()
def client_with_completed_events() -> TestClient:
    """TestClient with 6 events ending in 'completed'."""
    repo = AgentRepository()
    create_task_events(repo, terminal="completed")
    app = create_app(agent_repository_override=repo)
    return TestClient(app)


@pytest.fixture()
def client_empty() -> TestClient:
    """TestClient with a session+task but no events."""
    repo = AgentRepository()
    repo.create_session(SESSION_ID)
    repo.create_task(TASK_ID, SESSION_ID, "empty task")
    app = create_app(agent_repository_override=repo)
    return TestClient(app)


# ---------------------------------------------------------------------------
# AC-2: JSON replay
# ---------------------------------------------------------------------------


def test_get_task_events_returns_200(client_with_events: TestClient) -> None:
    resp = client_with_events.get(
        f"/api/v1/agent/sessions/{SESSION_ID}/tasks/{TASK_ID}/events"
    )
    assert resp.status_code == 200


def test_get_task_events_content_type_is_json(client_with_events: TestClient) -> None:
    resp = client_with_events.get(
        f"/api/v1/agent/sessions/{SESSION_ID}/tasks/{TASK_ID}/events"
    )
    assert "application/json" in resp.headers["content-type"]


def test_get_task_events_returns_events_in_sequence_order(
    client_with_events: TestClient,
) -> None:
    resp = client_with_events.get(
        f"/api/v1/agent/sessions/{SESSION_ID}/tasks/{TASK_ID}/events"
    )
    body = resp.json()
    events = body["events"]
    sequences = [e["sequence"] for e in events]
    assert sequences == sorted(sequences)
    assert sequences == [1, 2, 3, 4, 5, 6]


def test_get_task_events_response_shape(client_with_events: TestClient) -> None:
    resp = client_with_events.get(
        f"/api/v1/agent/sessions/{SESSION_ID}/tasks/{TASK_ID}/events"
    )
    body = resp.json()
    assert "events" in body
    assert "next_after_sequence" in body
    event = body["events"][0]
    assert "event_id" in event
    assert "session_id" in event
    assert "task_id" in event
    assert "sequence" in event
    assert "event_type" in event
    assert "created_at" in event


def test_get_task_events_next_after_sequence_is_last_sequence(
    client_with_events: TestClient,
) -> None:
    resp = client_with_events.get(
        f"/api/v1/agent/sessions/{SESSION_ID}/tasks/{TASK_ID}/events"
    )
    body = resp.json()
    assert body["next_after_sequence"] == body["events"][-1]["sequence"]


def test_get_task_events_empty_task_returns_empty_list(
    client_empty: TestClient,
) -> None:
    resp = client_empty.get(
        f"/api/v1/agent/sessions/{SESSION_ID}/tasks/{TASK_ID}/events"
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["events"] == []
    assert body["next_after_sequence"] is None


def test_get_task_events_after_sequence_filters_correctly(
    client_with_events: TestClient,
) -> None:
    resp = client_with_events.get(
        f"/api/v1/agent/sessions/{SESSION_ID}/tasks/{TASK_ID}/events?after_sequence=3"
    )
    body = resp.json()
    sequences = [e["sequence"] for e in body["events"]]
    assert all(s > 3 for s in sequences)


def test_get_task_events_after_sequence_beyond_last_returns_empty(
    client_with_events: TestClient,
) -> None:
    resp = client_with_events.get(
        f"/api/v1/agent/sessions/{SESSION_ID}/tasks/{TASK_ID}/events?after_sequence=9999"
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["events"] == []


def test_get_task_events_unknown_session_returns_422(
    client_with_events: TestClient,
) -> None:
    resp = client_with_events.get(
        f"/api/v1/agent/sessions/no-such-session/tasks/{TASK_ID}/events"
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "invalid_request"


def test_get_task_events_unknown_task_returns_422(
    client_with_events: TestClient,
) -> None:
    resp = client_with_events.get(
        f"/api/v1/agent/sessions/{SESSION_ID}/tasks/no-such-task/events"
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "invalid_request"


def test_get_task_events_contains_expected_event_types(
    client_with_events: TestClient,
) -> None:
    resp = client_with_events.get(
        f"/api/v1/agent/sessions/{SESSION_ID}/tasks/{TASK_ID}/events"
    )
    event_types = {e["event_type"] for e in resp.json()["events"]}
    assert "agent_started" in event_types
    assert "assistant_output" in event_types
    assert "tool_call" in event_types
    assert "approval_requested" in event_types


# ---------------------------------------------------------------------------
# AC-3: SSE stream
# ---------------------------------------------------------------------------


def test_stream_task_events_returns_200(client_with_events: TestClient) -> None:
    resp = client_with_events.get(
        f"/api/v1/agent/sessions/{SESSION_ID}/tasks/{TASK_ID}/events/stream"
    )
    assert resp.status_code == 200


def test_stream_task_events_content_type_is_event_stream(
    client_with_events: TestClient,
) -> None:
    resp = client_with_events.get(
        f"/api/v1/agent/sessions/{SESSION_ID}/tasks/{TASK_ID}/events/stream"
    )
    assert "text/event-stream" in resp.headers["content-type"]


def _parse_sse(raw: str) -> list[dict]:
    """Parse raw SSE text into list of {name, data} dicts."""
    frames = []
    for block in raw.split("\n\n"):
        block = block.strip()
        if not block:
            continue
        name = "message"
        data_lines = []
        for line in block.split("\n"):
            if line.startswith("event:"):
                name = line[6:].strip()
            elif line.startswith("data:"):
                data_lines.append(line[5:].strip())
        if data_lines:
            frames.append({"name": name, "data": "\n".join(data_lines)})
    return frames


def test_stream_task_events_frames_have_typed_event_names(
    client_with_events: TestClient,
) -> None:
    resp = client_with_events.get(
        f"/api/v1/agent/sessions/{SESSION_ID}/tasks/{TASK_ID}/events/stream"
    )
    frames = _parse_sse(resp.text)
    assert len(frames) > 0
    names = {f["name"] for f in frames}
    # Must include at least one typed event name
    assert names & {"agent_started", "assistant_output", "tool_call", "error", "completed"}


def test_stream_task_events_data_contains_task_id_and_sequence(
    client_with_events: TestClient,
) -> None:
    resp = client_with_events.get(
        f"/api/v1/agent/sessions/{SESSION_ID}/tasks/{TASK_ID}/events/stream"
    )
    frames = _parse_sse(resp.text)
    for frame in frames:
        payload = json.loads(frame["data"])
        assert payload["task_id"] == TASK_ID
        assert isinstance(payload["sequence"], int)
        assert payload["sequence"] > 0


def test_stream_task_events_terminal_error_frame_present(
    client_with_events: TestClient,
) -> None:
    """Fixture ends with error event — stream must include an 'error' frame."""
    resp = client_with_events.get(
        f"/api/v1/agent/sessions/{SESSION_ID}/tasks/{TASK_ID}/events/stream"
    )
    frames = _parse_sse(resp.text)
    names = [f["name"] for f in frames]
    assert "error" in names


def test_stream_task_events_terminal_completed_frame_present(
    client_with_completed_events: TestClient,
) -> None:
    """Fixture ends with completed event — stream must include a 'completed' frame."""
    resp = client_with_completed_events.get(
        f"/api/v1/agent/sessions/{SESSION_ID}/tasks/{TASK_ID}/events/stream"
    )
    frames = _parse_sse(resp.text)
    names = [f["name"] for f in frames]
    assert "completed" in names


def test_stream_task_events_empty_task_returns_200_with_no_frames(
    client_empty: TestClient,
) -> None:
    resp = client_empty.get(
        f"/api/v1/agent/sessions/{SESSION_ID}/tasks/{TASK_ID}/events/stream"
    )
    assert resp.status_code == 200
    frames = _parse_sse(resp.text)
    assert frames == []


def test_stream_task_events_after_sequence_filters_frames(
    client_with_events: TestClient,
) -> None:
    resp = client_with_events.get(
        f"/api/v1/agent/sessions/{SESSION_ID}/tasks/{TASK_ID}/events/stream?after_sequence=3"
    )
    frames = _parse_sse(resp.text)
    for frame in frames:
        payload = json.loads(frame["data"])
        assert payload["sequence"] > 3


def test_stream_task_events_unknown_session_returns_422(
    client_with_events: TestClient,
) -> None:
    resp = client_with_events.get(
        "/api/v1/agent/sessions/no-such-session/tasks/no-such-task/events/stream"
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "invalid_request"


def test_stream_task_events_frame_count_matches_event_count(
    client_with_events: TestClient,
) -> None:
    """Number of SSE frames must equal number of stored events."""
    resp = client_with_events.get(
        f"/api/v1/agent/sessions/{SESSION_ID}/tasks/{TASK_ID}/events/stream"
    )
    frames = _parse_sse(resp.text)
    json_resp = client_with_events.get(
        f"/api/v1/agent/sessions/{SESSION_ID}/tasks/{TASK_ID}/events"
    ).json()
    assert len(frames) == len(json_resp["events"])
