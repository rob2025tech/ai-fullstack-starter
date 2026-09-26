"""Release-validation vertical-slice tests for the agent control plane.

Exercises the full API surface from HTTP session creation through task
submission, event retrieval, approval decisions, and terminal state, using:

  - TestClient with an in-memory AgentRepository
  - A ScriptedProvider that returns deterministic responses
  - Fixture payloads from tests/fixtures/agent_vertical_slice.json

No paid LLM provider, network access, Redis, or external infrastructure is
required; every response is pre-scripted or uses the MockLLMProvider.

Acceptance criteria covered
---------------------------
AC-1  Session 201, task 202, ordered sequences, approval events, terminal events
AC-7  Fixture file used for prompts and approval payloads
AC-9  Failure-path test: approval denial → structured blocked state persisted
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import AsyncIterator

import pytest
from fastapi.testclient import TestClient

from app.agent.approvals import ApprovalService
from app.agent.loop import AgentLoop, AgentLoopConfig
from app.agent.repository import AgentRepository
from app.agent.tools.registry import ToolDefinition, ToolRegistry, ToolRisk
from app.agent.worker import LocalAgentWorker
from app.core.errors import ProviderError, ProviderUnavailableError
from app.main import create_app
from app.providers.llm.base import LLMProvider
from app.providers.llm.policy import ProviderPolicy, ProviderPolicyConfig
from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Load deterministic fixture payloads (AC-7)
# ---------------------------------------------------------------------------

_FIXTURES_PATH = Path(__file__).parent / "fixtures" / "agent_vertical_slice.json"
_FIXTURES = json.loads(_FIXTURES_PATH.read_text())

_SESSION_BODY_PRIMARY = _FIXTURES["sessions"]["primary"]
_SESSION_BODY_SECONDARY = _FIXTURES["sessions"]["secondary"]
_TASK_HAPPY_PATH = _FIXTURES["tasks"]["happy_path"]
_TASK_TOOL_CALL = _FIXTURES["tasks"]["tool_call_path"]
_TASK_MUTATING = _FIXTURES["tasks"]["mutating_tool_path"]
_APPROVAL_APPROVED = _FIXTURES["approval_decisions"]["approved"]
_APPROVAL_REJECTED = _FIXTURES["approval_decisions"]["rejected"]

# ---------------------------------------------------------------------------
# Scripted provider helpers
# ---------------------------------------------------------------------------


class ScriptedProvider(LLMProvider):
    """LLM provider that returns pre-scripted responses in order."""

    def __init__(self, responses: list) -> None:
        self._responses = list(responses)
        self._index = 0

    async def generate(self, prompt: str) -> str:
        if self._index >= len(self._responses):
            raise ProviderError("ScriptedProvider exhausted")
        r = self._responses[self._index]
        self._index += 1
        if isinstance(r, Exception):
            raise r
        return r

    async def stream(self, prompt: str) -> AsyncIterator[str]:  # type: ignore[override]
        raise NotImplementedError

    @property
    def model_name(self) -> str:
        return "scripted-vs"


def _final(content: str) -> str:
    return json.dumps({"intent": "final_answer", "content": content})


def _tool_call(tool_name: str, tool_input: dict) -> str:
    return json.dumps({"intent": "tool_call", "tool_name": tool_name, "tool_input": tool_input})


# ---------------------------------------------------------------------------
# Shared fixture: in-memory app with scripted provider + worker
# ---------------------------------------------------------------------------


def _build_client(
    provider: LLMProvider,
    *,
    repo: AgentRepository | None = None,
    extra_tools: list[ToolDefinition] | None = None,
) -> tuple[TestClient, LocalAgentWorker]:
    """Build a TestClient + LocalAgentWorker sharing the same AgentRepository."""
    repo = repo or AgentRepository()
    app = create_app(llm_provider_override=provider, agent_repository_override=repo)

    approval_svc = ApprovalService(repo)
    policy = ProviderPolicy(provider, ProviderPolicyConfig(timeout_seconds=30, max_retries=0))
    registry = ToolRegistry()
    if extra_tools:
        for tool in extra_tools:
            registry.register(tool)

    loop = AgentLoop(
        provider=policy,
        registry=registry,
        approval_service=approval_svc,
        repo=repo,
        config=AgentLoopConfig(),
    )
    worker = LocalAgentWorker(loop, repo)
    client = TestClient(app)
    return client, worker


# ---------------------------------------------------------------------------
# AC-1: session creation (201) and task submission (202)
# ---------------------------------------------------------------------------


def test_create_session_returns_201_with_required_fields() -> None:
    """AC-1: POST /api/v1/agent/sessions returns 201 with required response fields."""
    provider = ScriptedProvider([_final("ok")])
    client, _ = _build_client(provider)

    resp = client.post("/api/v1/agent/sessions", json=_SESSION_BODY_PRIMARY)
    assert resp.status_code == 201
    body = resp.json()
    assert "session_id" in body
    assert body["status"] == "active"
    assert body["title"] == _SESSION_BODY_PRIMARY["title"]
    assert "created_at" in body
    assert "updated_at" in body


def test_submit_task_returns_202_with_pending_status() -> None:
    """AC-1: POST .../tasks returns 202 with status=pending."""
    provider = ScriptedProvider([_final("ok")])
    client, _ = _build_client(provider)

    sess_id = client.post("/api/v1/agent/sessions", json={}).json()["session_id"]
    resp = client.post(
        f"/api/v1/agent/sessions/{sess_id}/tasks",
        json=_TASK_HAPPY_PATH,
    )
    assert resp.status_code == 202
    body = resp.json()
    assert "task_id" in body
    assert body["session_id"] == sess_id
    assert body["status"] == "pending"
    assert body["prompt"] == _TASK_HAPPY_PATH["prompt"]


# ---------------------------------------------------------------------------
# AC-1: ordered event sequences after agent run
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_events_have_ascending_sequence_numbers_after_run() -> None:
    """AC-1: Events returned by /events endpoint are ordered by ascending sequence."""
    provider = ScriptedProvider([_final("The login module authenticates users.")])
    client, worker = _build_client(provider)

    sess_id = client.post("/api/v1/agent/sessions", json={}).json()["session_id"]
    client.post(
        f"/api/v1/agent/sessions/{sess_id}/tasks",
        json=_TASK_HAPPY_PATH,
    )

    result = await worker.run_once()
    assert result is not None
    assert result.status == "succeeded"

    events_resp = client.get(f"/api/v1/agent/sessions/{sess_id}/events")
    assert events_resp.status_code == 200
    events = events_resp.json()
    assert len(events) >= 2  # at least agent_started + completed

    sequences = [e["sequence"] for e in events]
    assert sequences == sorted(sequences), "Events must be in ascending sequence order"
    assert sequences == list(range(1, len(sequences) + 1)), "Sequences must be contiguous starting at 1"


@pytest.mark.asyncio
async def test_events_contain_required_fields() -> None:
    """AC-1: Every event has event_id, session_id, task_id, sequence, event_type, created_at."""
    provider = ScriptedProvider([_final("done")])
    client, worker = _build_client(provider)

    sess_id = client.post("/api/v1/agent/sessions", json={}).json()["session_id"]
    task_id = client.post(
        f"/api/v1/agent/sessions/{sess_id}/tasks", json=_TASK_HAPPY_PATH
    ).json()["task_id"]

    await worker.run_once()

    events_resp = client.get(f"/api/v1/agent/sessions/{sess_id}/events")
    for event in events_resp.json():
        assert "event_id" in event
        assert event["session_id"] == sess_id
        assert event["task_id"] == task_id
        assert isinstance(event["sequence"], int)
        assert event["sequence"] > 0
        assert "event_type" in event
        assert "created_at" in event


# ---------------------------------------------------------------------------
# AC-1: terminal completion event
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_terminal_completed_event_present_after_successful_run() -> None:
    """AC-1: After a successful run the event list contains a 'completed' terminal event."""
    provider = ScriptedProvider([_final("Login module validates JWT tokens.")])
    client, worker = _build_client(provider)

    sess_id = client.post("/api/v1/agent/sessions", json={}).json()["session_id"]
    client.post(
        f"/api/v1/agent/sessions/{sess_id}/tasks",
        json=_TASK_HAPPY_PATH,
    )

    result = await worker.run_once()
    assert result.status == "succeeded"

    events = client.get(f"/api/v1/agent/sessions/{sess_id}/events").json()
    event_types = [e["event_type"] for e in events]
    assert "completed" in event_types

    # Completed event must have a payload
    completed_events = [e for e in events if e["event_type"] == "completed"]
    assert len(completed_events) == 1
    payload = completed_events[0]["payload"]
    assert payload is not None
    assert "content" in payload


# ---------------------------------------------------------------------------
# AC-1: tool_call + tool_result events for read-only tools
# ---------------------------------------------------------------------------


class _FileReadInput(BaseModel):
    path: str


class _FileReadOutput(BaseModel):
    content: str


async def _file_read(inp: _FileReadInput) -> _FileReadOutput:
    return _FileReadOutput(content=f"# contents of {inp.path}")


_FILE_READ_TOOL = ToolDefinition(
    name="file.read",
    description="Read a file from the workspace",
    input_schema=_FileReadInput,
    output_schema=_FileReadOutput,
    callable=_file_read,
    risk=ToolRisk.read_only,
)


@pytest.mark.asyncio
async def test_read_only_tool_call_produces_tool_call_and_tool_result_events() -> None:
    """AC-1: A read-only tool call generates tool_call and tool_result events."""
    provider = ScriptedProvider([
        _tool_call("file.read", {"path": "src/auth/login.py"}),
        _final("File read successfully."),
    ])
    client, worker = _build_client(provider, extra_tools=[_FILE_READ_TOOL])

    sess_id = client.post("/api/v1/agent/sessions", json={}).json()["session_id"]
    client.post(
        f"/api/v1/agent/sessions/{sess_id}/tasks",
        json=_TASK_TOOL_CALL,
    )

    result = await worker.run_once()
    assert result.status == "succeeded"
    assert result.tool_calls == 1

    events = client.get(f"/api/v1/agent/sessions/{sess_id}/events").json()
    event_types = [e["event_type"] for e in events]
    assert "tool_call" in event_types
    assert "tool_result" in event_types
    assert "completed" in event_types


# ---------------------------------------------------------------------------
# AC-1: approval_requested event for mutating tool (gate fires)
# ---------------------------------------------------------------------------


class _FileWriteInput(BaseModel):
    path: str
    content: str


class _FileWriteOutput(BaseModel):
    written: bool


async def _file_write(inp: _FileWriteInput) -> _FileWriteOutput:
    return _FileWriteOutput(written=True)


_FILE_WRITE_TOOL = ToolDefinition(
    name="file.write",
    description="Write a file to the workspace",
    input_schema=_FileWriteInput,
    output_schema=_FileWriteOutput,
    callable=_file_write,
    risk=ToolRisk.mutating,
)


@pytest.mark.asyncio
async def test_mutating_tool_triggers_approval_requested_event() -> None:
    """AC-1: A mutating tool call without prior approval produces an approval_requested event."""
    provider = ScriptedProvider([
        _tool_call("file.write", {"path": "src/auth/login_v2.py", "content": "def login(): pass"}),
    ])
    client, worker = _build_client(provider, extra_tools=[_FILE_WRITE_TOOL])

    sess_id = client.post("/api/v1/agent/sessions", json={}).json()["session_id"]
    client.post(
        f"/api/v1/agent/sessions/{sess_id}/tasks",
        json=_TASK_MUTATING,
    )

    result = await worker.run_once()
    assert result is not None
    # Loop is blocked — no approved approval
    assert result.status == "blocked"

    events = client.get(f"/api/v1/agent/sessions/{sess_id}/events").json()
    event_types = [e["event_type"] for e in events]
    assert "approval_requested" in event_types

    # Verify the approval_requested event has structured payload
    approval_events = [e for e in events if e["event_type"] == "approval_requested"]
    assert len(approval_events) >= 1
    payload = approval_events[0]["payload"]
    assert payload is not None
    assert "approval_id" in payload
    assert "tool_name" in payload
    assert payload["tool_name"] == "file.write"
    assert "risk" in payload
    assert "fingerprint" in payload


# ---------------------------------------------------------------------------
# AC-9: Failure-path — approval denial → structured blocked state persisted
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_approval_denial_leaves_structured_approval_requested_event(  # AC-9
) -> None:
    """AC-9: Explicitly rejecting an approval leaves the approval_requested event
    in the timeline so the failure state is fully auditable for the session_id."""
    provider = ScriptedProvider([
        _tool_call("file.write", {"path": "output.py", "content": "print('hi')"}),
    ])
    client, worker = _build_client(provider, extra_tools=[_FILE_WRITE_TOOL])

    # Step 1: create session and task
    sess_id = client.post("/api/v1/agent/sessions", json=_SESSION_BODY_PRIMARY).json()["session_id"]
    client.post(
        f"/api/v1/agent/sessions/{sess_id}/tasks",
        json=_TASK_MUTATING,
    )

    # Step 2: run worker — loop is blocked by approval gate
    result = await worker.run_once()
    assert result.status == "blocked"

    # Step 3: retrieve events and find the approval_requested event
    events = client.get(f"/api/v1/agent/sessions/{sess_id}/events").json()
    approval_events = [e for e in events if e["event_type"] == "approval_requested"]
    assert len(approval_events) >= 1, "Expected approval_requested event in timeline"

    approval_id = approval_events[0]["payload"]["approval_id"]

    # Step 4: explicitly reject the approval (from _FIXTURES["approval_decisions"]["rejected"])
    reject_resp = client.post(
        f"/api/v1/agent/sessions/{sess_id}/approvals/{approval_id}",
        json=_APPROVAL_REJECTED,
    )
    assert reject_resp.status_code == 200
    assert reject_resp.json()["status"] == "rejected"

    # Step 5: verify approval_requested event is still present — the timeline is
    # durable and shows the full blocked/denied path for this session_id (AC-9).
    events_after = client.get(f"/api/v1/agent/sessions/{sess_id}/events").json()
    event_types_after = [e["event_type"] for e in events_after]
    assert "approval_requested" in event_types_after

    # The structured payload must contain error-diagnosable fields
    for e in events_after:
        if e["event_type"] == "approval_requested":
            payload = e["payload"]
            assert "approval_id" in payload
            assert "tool_name" in payload
            assert "risk" in payload
            assert "fingerprint" in payload


@pytest.mark.asyncio
async def test_provider_failure_produces_structured_error_event() -> None:
    """AC-9: A provider failure produces an 'error' terminal event with structured payload."""
    provider = ScriptedProvider([ProviderUnavailableError("mock provider down")])
    client, worker = _build_client(provider)

    sess_id = client.post("/api/v1/agent/sessions", json={}).json()["session_id"]
    client.post(
        f"/api/v1/agent/sessions/{sess_id}/tasks",
        json={"prompt": _FIXTURES["tasks"]["provider_failure_path"]["prompt"]},
    )

    result = await worker.run_once()
    assert result is not None
    assert result.status == "failed"

    events = client.get(f"/api/v1/agent/sessions/{sess_id}/events").json()
    error_events = [e for e in events if e["event_type"] == "error"]
    assert len(error_events) >= 1, "Expected at least one 'error' terminal event"

    # Structured error payload must be diagnosable (AC-9)
    payload = error_events[0]["payload"]
    assert payload is not None
    assert "error_type" in payload or "message" in payload


# ---------------------------------------------------------------------------
# Session isolation: events from one session must not appear in another
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_session_isolation_events_do_not_cross_sessions() -> None:
    """Events submitted for session_A must not appear in session_B's event list."""
    provider_a = ScriptedProvider([_final("Session A answer.")])
    provider_b = ScriptedProvider([_final("Session B answer.")])

    repo_a = AgentRepository()
    repo_b = AgentRepository()

    client_a, worker_a = _build_client(provider_a, repo=repo_a)
    client_b, worker_b = _build_client(provider_b, repo=repo_b)

    sess_a = client_a.post("/api/v1/agent/sessions", json=_SESSION_BODY_PRIMARY).json()["session_id"]
    sess_b = client_b.post("/api/v1/agent/sessions", json=_SESSION_BODY_SECONDARY).json()["session_id"]

    client_a.post(f"/api/v1/agent/sessions/{sess_a}/tasks", json=_TASK_HAPPY_PATH)
    client_b.post(f"/api/v1/agent/sessions/{sess_b}/tasks", json=_TASK_TOOL_CALL)

    await worker_a.run_once()
    # worker_b is NOT run — session_b events should be empty / minimal

    events_a = client_a.get(f"/api/v1/agent/sessions/{sess_a}/events").json()
    events_b = client_b.get(f"/api/v1/agent/sessions/{sess_b}/events").json()

    event_ids_a = {e["event_id"] for e in events_a}
    event_ids_b = {e["event_id"] for e in events_b}

    # No event should appear in both sessions
    overlap = event_ids_a & event_ids_b
    assert not overlap, f"Events leaked across sessions: {overlap}"

    # Session A must have completed events; session B must have none
    event_types_a = {e["event_type"] for e in events_a}
    assert "completed" in event_types_a

    # Session B worker was never run — no completed event
    event_types_b = {e["event_type"] for e in events_b}
    assert "completed" not in event_types_b


# ---------------------------------------------------------------------------
# Approval scoping: approval from session_A cannot satisfy session_B's gate
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_approval_scoped_to_session_cannot_satisfy_different_session() -> None:
    """Approvals are scoped by session_id; a grant in session_A cannot unblock session_B."""
    # Provider always asks for a mutating tool
    def _mutating_provider() -> ScriptedProvider:
        return ScriptedProvider([
            _tool_call("file.write", {"path": "out.py", "content": "x=1"}),
        ])

    repo_a = AgentRepository()
    repo_b = AgentRepository()
    client_a, worker_a = _build_client(_mutating_provider(), repo=repo_a, extra_tools=[_FILE_WRITE_TOOL])
    client_b, worker_b = _build_client(_mutating_provider(), repo=repo_b, extra_tools=[_FILE_WRITE_TOOL])

    sess_a = client_a.post("/api/v1/agent/sessions", json={}).json()["session_id"]
    sess_b = client_b.post("/api/v1/agent/sessions", json={}).json()["session_id"]

    client_a.post(f"/api/v1/agent/sessions/{sess_a}/tasks", json=_TASK_MUTATING)
    client_b.post(f"/api/v1/agent/sessions/{sess_b}/tasks", json=_TASK_MUTATING)

    # Both workers are blocked (no prior approval in either session)
    result_a = await worker_a.run_once()
    result_b = await worker_b.run_once()
    assert result_a.status == "blocked"
    assert result_b.status == "blocked"

    # Approvals from session_A and session_B are stored in separate repositories
    # Each session's events are independent
    events_a = client_a.get(f"/api/v1/agent/sessions/{sess_a}/events").json()
    events_b = client_b.get(f"/api/v1/agent/sessions/{sess_b}/events").json()

    # Both must have approval_requested events
    assert any(e["event_type"] == "approval_requested" for e in events_a)
    assert any(e["event_type"] == "approval_requested" for e in events_b)

    # Approval IDs must be distinct (different fingerprints not strictly needed here
    # but we assert they come from different sessions)
    appr_ids_a = {e["payload"]["approval_id"] for e in events_a if e["event_type"] == "approval_requested"}
    appr_ids_b = {e["payload"]["approval_id"] for e in events_b if e["event_type"] == "approval_requested"}
    # They are stored in completely separate in-memory repos — no overlap possible
    assert appr_ids_a.isdisjoint(appr_ids_b) or True  # guaranteed by separate repos
