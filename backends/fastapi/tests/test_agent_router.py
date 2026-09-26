"""Integration tests for the agent control-plane router.

Each test builds a minimal FastAPI app with a tmp_path-backed AgentRepository
and exercises the /api/v1/agent endpoints via TestClient.  No LLM provider
or external service is required.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from app.agent.repository import AgentRepository
from app.core.errors import BackendError
from app.models.agent_models import (
    AgentEventResponse,
    AgentSessionResponse,
    AgentStateResponse,
    AgentTaskResponse,
    ApprovalRequestResponse,
)
from app.models.error_models import Error, ErrorResponse
from app.routers import agent as agent_router


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_app(repo: AgentRepository) -> FastAPI:
    """Build a minimal FastAPI app with the agent router and shared error handlers."""
    app = FastAPI()
    app.state.agent_repository = repo
    app.include_router(agent_router.router)

    def _err(code: str, msg: str) -> dict:
        return ErrorResponse(error=Error(code=code, message=msg)).model_dump(mode="json")

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        msg = "; ".join(
            f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors()
        )
        return JSONResponse(status_code=422, content=_err("invalid_request", msg))

    @app.exception_handler(BackendError)
    async def _backend(request: Request, exc: BackendError) -> JSONResponse:
        return JSONResponse(status_code=exc.http_status, content=_err(exc.code, exc.message))

    return app


@pytest.fixture()
def repo(tmp_path: Path) -> AgentRepository:
    return AgentRepository(db_path=tmp_path / "agent.db")


@pytest.fixture()
def client(repo: AgentRepository) -> TestClient:
    return TestClient(_make_app(repo), raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# Deterministic sample request bodies (AC-6)
# ---------------------------------------------------------------------------

_CREATE_SESSION_BODY = {"title": "Test session", "metadata": {"env": "test"}}
_SUBMIT_TASK_BODY = {"prompt": "Write a hello-world Python script"}
_APPROVAL_DECISION_REJECTED = {"decision": "rejected", "rationale": "Not safe"}
_APPROVAL_DECISION_APPROVED = {"decision": "approved"}
_SAMPLE_EVENT_PAYLOAD = {"content": "Hello, world!"}


# ---------------------------------------------------------------------------
# Session tests
# ---------------------------------------------------------------------------


def test_create_session_returns_201(client: TestClient) -> None:
    response = client.post("/api/v1/agent/sessions", json=_CREATE_SESSION_BODY)
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "active"
    assert body["title"] == "Test session"
    assert "session_id" in body
    assert "created_at" in body
    assert "updated_at" in body


def test_create_session_minimal_no_body(client: TestClient) -> None:
    response = client.post("/api/v1/agent/sessions", json={})
    assert response.status_code == 201
    body = response.json()
    assert body["title"] is None


def test_get_session_returns_200(client: TestClient) -> None:
    create_resp = client.post("/api/v1/agent/sessions", json=_CREATE_SESSION_BODY)
    session_id = create_resp.json()["session_id"]

    response = client.get(f"/api/v1/agent/sessions/{session_id}")
    assert response.status_code == 200
    assert response.json()["session_id"] == session_id


def test_get_unknown_session_returns_422(client: TestClient) -> None:
    response = client.get("/api/v1/agent/sessions/does-not-exist")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_request"


# ---------------------------------------------------------------------------
# Task tests (AC-4, AC-5)
# ---------------------------------------------------------------------------


def test_submit_task_returns_202(client: TestClient) -> None:
    session_id = client.post("/api/v1/agent/sessions", json={}).json()["session_id"]
    response = client.post(
        f"/api/v1/agent/sessions/{session_id}/tasks",
        json=_SUBMIT_TASK_BODY,
    )
    assert response.status_code == 202
    body = response.json()
    assert body["session_id"] == session_id
    assert body["status"] == "pending"
    assert body["prompt"] == _SUBMIT_TASK_BODY["prompt"]


def test_submit_task_empty_prompt_returns_422(client: TestClient) -> None:
    """AC-4: Pydantic minLength constraint on SubmitAgentTaskRequest.prompt."""
    session_id = client.post("/api/v1/agent/sessions", json={}).json()["session_id"]
    response = client.post(
        f"/api/v1/agent/sessions/{session_id}/tasks",
        json={"prompt": ""},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_request"


def test_submit_task_missing_prompt_returns_422(client: TestClient) -> None:
    session_id = client.post("/api/v1/agent/sessions", json={}).json()["session_id"]
    response = client.post(
        f"/api/v1/agent/sessions/{session_id}/tasks",
        json={},
    )
    assert response.status_code == 422


def test_submit_task_unknown_session_returns_422(client: TestClient) -> None:
    response = client.post(
        "/api/v1/agent/sessions/ghost-session/tasks",
        json=_SUBMIT_TASK_BODY,
    )
    assert response.status_code == 422
    assert "ghost-session" in response.json()["error"]["message"]


# ---------------------------------------------------------------------------
# Event tests (AC-7)
# ---------------------------------------------------------------------------


def test_list_events_empty_session_returns_empty_array(client: TestClient, repo: AgentRepository) -> None:
    """AC-7: GET events on a new session with no tasks returns an empty list."""
    session_id = client.post("/api/v1/agent/sessions", json={}).json()["session_id"]
    response = client.get(f"/api/v1/agent/sessions/{session_id}/events")
    assert response.status_code == 200
    assert response.json() == []


def test_list_events_ordered_by_sequence(client: TestClient, repo: AgentRepository) -> None:
    """AC-7: Events returned in sequence order."""
    session_id = client.post("/api/v1/agent/sessions", json={}).json()["session_id"]
    # Submit a task — this generates a task_accepted event (sequence 1)
    task_resp = client.post(
        f"/api/v1/agent/sessions/{session_id}/tasks",
        json=_SUBMIT_TASK_BODY,
    )
    task_id = task_resp.json()["task_id"]

    # Manually append a second event
    import uuid
    repo.append_event(
        event_id=str(uuid.uuid4()),
        session_id=session_id,
        task_id=task_id,
        event_type="completed",
        payload={"result": "done"},
    )

    response = client.get(f"/api/v1/agent/sessions/{session_id}/events")
    assert response.status_code == 200
    events = response.json()
    assert len(events) == 2
    sequences = [e["sequence"] for e in events]
    assert sequences == sorted(sequences)
    assert events[0]["event_type"] == "task_accepted"
    assert events[1]["event_type"] == "completed"


def test_stream_events_content_type_is_sse(client: TestClient) -> None:
    """AC-7: GET .../events/stream has content-type containing text/event-stream."""
    session_id = client.post("/api/v1/agent/sessions", json={}).json()["session_id"]
    response = client.get(f"/api/v1/agent/sessions/{session_id}/events/stream")
    assert response.status_code == 200
    assert "text/event-stream" in response.headers["content-type"]


def test_stream_events_replays_persisted_events(client: TestClient, repo: AgentRepository) -> None:
    """SSE stream emits one frame per persisted event then closes."""
    import uuid
    session_id = client.post("/api/v1/agent/sessions", json={}).json()["session_id"]
    task_resp = client.post(
        f"/api/v1/agent/sessions/{session_id}/tasks",
        json=_SUBMIT_TASK_BODY,
    )
    task_id = task_resp.json()["task_id"]
    repo.append_event(
        event_id=str(uuid.uuid4()),
        session_id=session_id,
        task_id=task_id,
        event_type="completed",
    )

    response = client.get(f"/api/v1/agent/sessions/{session_id}/events/stream")
    assert response.status_code == 200
    text = response.text
    # Two SSE frames expected (task_accepted + completed)
    frames = [f for f in text.strip().split("\n\n") if f.strip()]
    assert len(frames) == 2
    # Each frame starts with "event: <type>"
    for frame in frames:
        assert frame.startswith("event: ")


# ---------------------------------------------------------------------------
# Approval tests (AC-8)
# ---------------------------------------------------------------------------


def test_list_approvals_empty_returns_empty(client: TestClient) -> None:
    session_id = client.post("/api/v1/agent/sessions", json={}).json()["session_id"]
    response = client.get(f"/api/v1/agent/sessions/{session_id}/approvals")
    assert response.status_code == 200
    assert response.json() == []


def test_decide_approval_rejected_updates_status(client: TestClient, repo: AgentRepository) -> None:
    """AC-8: Rejection sets status=rejected and does not set consumed_at."""
    session_id = client.post("/api/v1/agent/sessions", json={}).json()["session_id"]
    task_resp = client.post(
        f"/api/v1/agent/sessions/{session_id}/tasks",
        json=_SUBMIT_TASK_BODY,
    )
    task_id = task_resp.json()["task_id"]

    expires = datetime.now(timezone.utc) + timedelta(hours=1)
    approval = repo.create_approval_request(
        approval_id="appr-001",
        session_id=session_id,
        task_id=task_id,
        action_type="write_file",
        action_fingerprint="fp-abc123",
        expires_at=expires,
        action_payload={"path": "/tmp/test.py"},
    )

    response = client.post(
        f"/api/v1/agent/sessions/{session_id}/approvals/{approval.approval_id}",
        json=_APPROVAL_DECISION_REJECTED,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "rejected"
    assert body["consumed_at"] is None  # rejection does not consume


def test_decide_approval_approved_updates_status(client: TestClient, repo: AgentRepository) -> None:
    session_id = client.post("/api/v1/agent/sessions", json={}).json()["session_id"]
    task_resp = client.post(
        f"/api/v1/agent/sessions/{session_id}/tasks",
        json=_SUBMIT_TASK_BODY,
    )
    task_id = task_resp.json()["task_id"]

    expires = datetime.now(timezone.utc) + timedelta(hours=1)
    approval = repo.create_approval_request(
        approval_id="appr-002",
        session_id=session_id,
        task_id=task_id,
        action_type="run_command",
        action_fingerprint="fp-xyz456",
        expires_at=expires,
    )

    response = client.post(
        f"/api/v1/agent/sessions/{session_id}/approvals/{approval.approval_id}",
        json=_APPROVAL_DECISION_APPROVED,
    )
    assert response.status_code == 200
    assert response.json()["status"] == "approved"


def test_decide_approval_unknown_returns_422(client: TestClient) -> None:
    session_id = client.post("/api/v1/agent/sessions", json={}).json()["session_id"]
    response = client.post(
        f"/api/v1/agent/sessions/{session_id}/approvals/no-such-approval",
        json=_APPROVAL_DECISION_REJECTED,
    )
    assert response.status_code == 422


def test_decide_approval_invalid_decision_returns_422(client: TestClient, repo: AgentRepository) -> None:
    session_id = client.post("/api/v1/agent/sessions", json={}).json()["session_id"]
    task_resp = client.post(
        f"/api/v1/agent/sessions/{session_id}/tasks",
        json=_SUBMIT_TASK_BODY,
    )
    task_id = task_resp.json()["task_id"]
    expires = datetime.now(timezone.utc) + timedelta(hours=1)
    approval = repo.create_approval_request(
        approval_id="appr-003",
        session_id=session_id,
        task_id=task_id,
        action_type="write_file",
        action_fingerprint="fp-bad",
        expires_at=expires,
    )
    response = client.post(
        f"/api/v1/agent/sessions/{session_id}/approvals/{approval.approval_id}",
        json={"decision": "maybe"},
    )
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# State tests (AC-5)
# ---------------------------------------------------------------------------


def test_get_state_contains_submitted_task(client: TestClient) -> None:
    """AC-5: GET state returns the submitted task_id."""
    session_id = client.post("/api/v1/agent/sessions", json={}).json()["session_id"]
    task_resp = client.post(
        f"/api/v1/agent/sessions/{session_id}/tasks",
        json=_SUBMIT_TASK_BODY,
    )
    task_id = task_resp.json()["task_id"]

    response = client.get(f"/api/v1/agent/sessions/{session_id}/state")
    assert response.status_code == 200
    body = response.json()
    assert body["session_id"] == session_id
    task_ids = [t["task_id"] for t in body["tasks"]]
    assert task_id in task_ids


def test_get_state_unknown_session_returns_422(client: TestClient) -> None:
    response = client.get("/api/v1/agent/sessions/ghost/state")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_request"


def test_get_state_structure(client: TestClient) -> None:
    """State response includes session, tasks, events, and pending_approvals keys."""
    session_id = client.post("/api/v1/agent/sessions", json={}).json()["session_id"]
    response = client.get(f"/api/v1/agent/sessions/{session_id}/state")
    assert response.status_code == 200
    body = response.json()
    assert "session" in body
    assert "tasks" in body
    assert "events" in body
    assert "pending_approvals" in body
    assert body["session"]["session_id"] == session_id
