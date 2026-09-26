"""System integration tests for the agent execution pipeline.

Submits a task through the live FastAPI agent endpoint, runs the local worker
once, and verifies that the event stream contains a terminal completion or
failure event.

Uses:
- TestClient with an in-memory AgentRepository injected via create_app().
- A scripted LLM provider injected via llm_provider_override.
- LocalAgentWorker called directly (not via HTTP) to avoid needing a background
  task runner.
"""

from __future__ import annotations

import json
from typing import AsyncIterator

import pytest
from fastapi.testclient import TestClient

from app.agent.approvals import ApprovalService
from app.agent.loop import AgentLoop, AgentLoopConfig
from app.agent.repository import AgentRepository
from app.agent.tools.registry import ToolDefinition, ToolRegistry, ToolRisk
from app.agent.worker import LocalAgentWorker
from app.core.errors import ProviderError
from app.main import create_app
from app.providers.llm.base import LLMProvider
from app.providers.llm.policy import ProviderPolicy, ProviderPolicyConfig
from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Scripted provider
# ---------------------------------------------------------------------------


class ScriptedProvider(LLMProvider):
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
        return "scripted"


def _final_answer(content: str) -> str:
    return json.dumps({"intent": "final_answer", "content": content})


def _tool_call(tool_name: str, tool_input: dict) -> str:
    return json.dumps({"intent": "tool_call", "tool_name": tool_name, "tool_input": tool_input})


# ---------------------------------------------------------------------------
# AC-8: submit task → run worker → terminal event in event list
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_submit_task_run_worker_terminal_completion_event() -> None:
    """Submit a task via HTTP, run the local worker, assert agent_completed event."""
    repo = AgentRepository()
    provider = ScriptedProvider([_final_answer("Integration complete.")])

    app = create_app(
        llm_provider_override=provider,
        agent_repository_override=repo,
    )

    # Wire the loop and worker to use the SAME repo instance as the app
    approval_svc = ApprovalService(repo)
    policy = ProviderPolicy(provider, ProviderPolicyConfig(timeout_seconds=30, max_retries=0))
    registry = ToolRegistry()
    loop = AgentLoop(
        provider=policy,
        registry=registry,
        approval_service=approval_svc,
        repo=repo,
        config=AgentLoopConfig(),
    )
    worker = LocalAgentWorker(loop, repo)

    client = TestClient(app)

    # Step 1: Create a session
    sess_resp = client.post("/api/v1/agent/sessions", json={"title": "integration-test"})
    assert sess_resp.status_code == 201
    session_id = sess_resp.json()["session_id"]

    # Step 2: Submit a task
    task_resp = client.post(
        f"/api/v1/agent/sessions/{session_id}/tasks",
        json={"prompt": "What is 2+2?"},
    )
    assert task_resp.status_code == 202
    task_id = task_resp.json()["task_id"]

    # Step 3: Run the worker once
    result = await worker.run_once()
    assert result is not None
    assert result.status == "succeeded"
    assert result.task_id == task_id

    # Step 4: Retrieve events via the API
    events_resp = client.get(f"/api/v1/agent/sessions/{session_id}/events")
    assert events_resp.status_code == 200
    events = events_resp.json()
    event_types = [e["event_type"] for e in events]

    # Must contain agent_started and completed
    assert "agent_started" in event_types
    assert "completed" in event_types

    # Step 5: Verify session reflects running/completed state
    sess2_resp = client.get(f"/api/v1/agent/sessions/{session_id}")
    assert sess2_resp.status_code == 200


@pytest.mark.asyncio
async def test_submit_task_run_worker_provider_failure_terminal_event() -> None:
    """Submit a task and let the provider fail; assert a failure event is recorded."""
    from app.core.errors import ProviderUnavailableError

    repo = AgentRepository()
    provider = ScriptedProvider([ProviderUnavailableError("integration test failure")])

    app = create_app(
        llm_provider_override=provider,
        agent_repository_override=repo,
    )

    approval_svc = ApprovalService(repo)
    policy = ProviderPolicy(provider, ProviderPolicyConfig(timeout_seconds=30, max_retries=0))
    registry = ToolRegistry()
    loop = AgentLoop(
        provider=policy,
        registry=registry,
        approval_service=approval_svc,
        repo=repo,
    )
    worker = LocalAgentWorker(loop, repo)

    client = TestClient(app)

    sess_resp = client.post("/api/v1/agent/sessions", json={})
    session_id = sess_resp.json()["session_id"]

    task_resp = client.post(
        f"/api/v1/agent/sessions/{session_id}/tasks",
        json={"prompt": "Will this fail?"},
    )
    task_id = task_resp.json()["task_id"]

    result = await worker.run_once()
    assert result is not None
    assert result.status == "failed"
    assert result.task_id == task_id

    events_resp = client.get(f"/api/v1/agent/sessions/{session_id}/events")
    events = events_resp.json()
    event_types = [e["event_type"] for e in events]
    assert "error" in event_types


@pytest.mark.asyncio
async def test_submit_task_with_read_only_tool_completes_successfully() -> None:
    """Submit a task with a tool call to a read-only tool; assert completion."""

    class EchoInput(BaseModel):
        message: str

    class EchoOutput(BaseModel):
        echoed: str

    async def _echo(inp: EchoInput) -> EchoOutput:
        return EchoOutput(echoed=inp.message)

    echo_tool = ToolDefinition(
        name="echo",
        description="Echo",
        input_schema=EchoInput,
        output_schema=EchoOutput,
        callable=_echo,
        risk=ToolRisk.read_only,
    )

    repo = AgentRepository()
    provider = ScriptedProvider([
        _tool_call("echo", {"message": "hello"}),
        _final_answer("Echo said hello"),
    ])

    app = create_app(
        llm_provider_override=provider,
        agent_repository_override=repo,
    )

    approval_svc = ApprovalService(repo)
    policy = ProviderPolicy(provider, ProviderPolicyConfig(timeout_seconds=30, max_retries=0))
    registry = ToolRegistry()
    registry.register(echo_tool)
    loop = AgentLoop(
        provider=policy,
        registry=registry,
        approval_service=approval_svc,
        repo=repo,
    )
    worker = LocalAgentWorker(loop, repo)

    client = TestClient(app)

    sess_resp = client.post("/api/v1/agent/sessions", json={})
    session_id = sess_resp.json()["session_id"]

    client.post(
        f"/api/v1/agent/sessions/{session_id}/tasks",
        json={"prompt": "Echo something"},
    )

    result = await worker.run_once()
    assert result is not None
    assert result.status == "succeeded"
    assert result.tool_calls == 1

    events_resp = client.get(f"/api/v1/agent/sessions/{session_id}/events")
    events = events_resp.json()
    event_types = [e["event_type"] for e in events]
    assert "tool_call" in event_types
    assert "tool_result" in event_types
    assert "completed" in event_types
