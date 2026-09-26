"""Unit tests for AgentLoop (backends/fastapi/app/agent/loop.py).

All tests use:
- In-memory AgentRepository with pre-created session and task.
- ScriptedProvider that returns pre-configured responses in order.
- Injectable fake clock for deterministic timeout assertions.
- Fake tool implementations that do not touch the filesystem.
No network, filesystem, or subprocess calls occur in these tests.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import AsyncIterator

import pytest

from app.agent.approvals import ApprovalDecision, ApprovalService
from app.agent.loop import AgentLoop, AgentLoopConfig, AgentLoopResult
from app.agent.repository import AgentRepository
from app.agent.tools.registry import ToolDefinition, ToolRegistry, ToolRisk, ToolInvocationError
from app.core.errors import ProviderError, ProviderUnavailableError
from app.providers.llm.base import LLMProvider
from app.providers.llm.policy import ProviderPolicy, ProviderPolicyConfig
from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Helpers: scripted provider
# ---------------------------------------------------------------------------


class ScriptedProvider(LLMProvider):
    """Returns pre-scripted responses in sequence; raises on exhaustion."""

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


def _malformed_tool_call() -> str:
    return json.dumps({"intent": "tool_call"})  # missing tool_name and tool_input


# ---------------------------------------------------------------------------
# Helpers: fake tools
# ---------------------------------------------------------------------------


class EchoInput(BaseModel):
    message: str


class EchoOutput(BaseModel):
    echoed: str


class WriteInput(BaseModel):
    path: str
    content: str


class WriteOutput(BaseModel):
    path: str
    bytes_written: int


async def _echo_tool(inp: EchoInput) -> EchoOutput:
    return EchoOutput(echoed=inp.message)


async def _write_tool(inp: WriteInput) -> WriteOutput:
    return WriteOutput(path=inp.path, bytes_written=len(inp.content.encode()))


ECHO_TOOL = ToolDefinition(
    name="echo",
    description="Echo input back",
    input_schema=EchoInput,
    output_schema=EchoOutput,
    callable=_echo_tool,
    risk=ToolRisk.read_only,
)

WRITE_TOOL = ToolDefinition(
    name="file.write",
    description="Write a file (mutating)",
    input_schema=WriteInput,
    output_schema=WriteOutput,
    callable=_write_tool,
    risk=ToolRisk.mutating,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def repo() -> AgentRepository:
    r = AgentRepository()
    r.create_session("sess-1")
    r.create_task("task-1", "sess-1", "test task prompt")
    return r


@pytest.fixture()
def registry() -> ToolRegistry:
    reg = ToolRegistry()
    reg.register(ECHO_TOOL)
    reg.register(WRITE_TOOL)
    return reg


@pytest.fixture()
def approval_svc(repo: AgentRepository) -> ApprovalService:
    return ApprovalService(repo)


def _make_loop(
    provider: LLMProvider,
    registry: ToolRegistry,
    approval_svc: ApprovalService,
    repo: AgentRepository,
    config: AgentLoopConfig | None = None,
    clock=None,
) -> AgentLoop:
    policy = ProviderPolicy(provider, ProviderPolicyConfig(timeout_seconds=30, max_retries=0))
    return AgentLoop(
        provider=policy,
        registry=registry,
        approval_service=approval_svc,
        repo=repo,
        config=config,
        clock=clock,
    )


# ---------------------------------------------------------------------------
# AC-3: final answer path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_final_answer_appends_started_and_completed_events(
    repo: AgentRepository,
    registry: ToolRegistry,
    approval_svc: ApprovalService,
) -> None:
    provider = ScriptedProvider([_final_answer("All done.")])
    loop = _make_loop(provider, registry, approval_svc, repo)
    result = await loop.run("sess-1", "task-1")

    assert result.status == "succeeded"
    assert result.final_answer == "All done."

    events = repo.list_events(task_id="task-1")
    event_types = [e.event_type for e in events]
    assert "agent_started" in event_types
    assert "completed" in event_types
    # No tool invocation
    assert "tool_call" not in event_types
    assert "tool_result" not in event_types


@pytest.mark.asyncio
async def test_final_answer_does_not_invoke_registry(
    repo: AgentRepository,
    registry: ToolRegistry,
    approval_svc: ApprovalService,
) -> None:
    provider = ScriptedProvider([_final_answer("Done")])
    loop = _make_loop(provider, registry, approval_svc, repo)
    result = await loop.run("sess-1", "task-1")
    assert result.status == "succeeded"
    assert result.tool_calls == 0


@pytest.mark.asyncio
async def test_plain_text_response_treated_as_final_answer(
    repo: AgentRepository,
    registry: ToolRegistry,
    approval_svc: ApprovalService,
) -> None:
    provider = ScriptedProvider(["This is a plain text response."])
    loop = _make_loop(provider, registry, approval_svc, repo)
    result = await loop.run("sess-1", "task-1")
    assert result.status == "succeeded"
    assert result.final_answer == "This is a plain text response."


# ---------------------------------------------------------------------------
# AC-4: tool call path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tool_call_invokes_registry_and_appends_events(
    repo: AgentRepository,
    registry: ToolRegistry,
    approval_svc: ApprovalService,
) -> None:
    provider = ScriptedProvider([
        _tool_call("echo", {"message": "hello"}),
        _final_answer("Echo done"),
    ])
    loop = _make_loop(provider, registry, approval_svc, repo)
    result = await loop.run("sess-1", "task-1")

    assert result.status == "succeeded"
    assert result.tool_calls == 1

    events = repo.list_events(task_id="task-1")
    event_types = [e.event_type for e in events]
    assert "tool_call" in event_types
    assert "tool_result" in event_types


@pytest.mark.asyncio
async def test_tool_call_events_have_monotonic_sequence(
    repo: AgentRepository,
    registry: ToolRegistry,
    approval_svc: ApprovalService,
) -> None:
    provider = ScriptedProvider([
        _tool_call("echo", {"message": "first"}),
        _tool_call("echo", {"message": "second"}),
        _final_answer("All done"),
    ])
    loop = _make_loop(provider, registry, approval_svc, repo)
    result = await loop.run("sess-1", "task-1")
    assert result.tool_calls == 2

    events = repo.list_events(task_id="task-1")
    tool_call_events = [e for e in events if e.event_type == "tool_call"]
    assert len(tool_call_events) == 2
    # Events are stored with monotonic sequence numbers by the repository
    sequences = [e.sequence for e in tool_call_events]
    assert sequences == sorted(sequences)
    assert len(set(sequences)) == len(sequences)  # all unique


@pytest.mark.asyncio
async def test_tool_result_payload_contains_tool_name(
    repo: AgentRepository,
    registry: ToolRegistry,
    approval_svc: ApprovalService,
) -> None:
    provider = ScriptedProvider([
        _tool_call("echo", {"message": "ping"}),
        _final_answer("done"),
    ])
    loop = _make_loop(provider, registry, approval_svc, repo)
    await loop.run("sess-1", "task-1")

    events = repo.list_events(task_id="task-1")
    tool_result_events = [e for e in events if e.event_type == "tool_result"]
    assert len(tool_result_events) == 1
    assert tool_result_events[0].payload["tool_name"] == "echo"


# ---------------------------------------------------------------------------
# AC-5: limit handling
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_max_iterations_terminates_with_loop_limit(
    repo: AgentRepository,
    registry: ToolRegistry,
    approval_svc: ApprovalService,
) -> None:
    # Provider always returns a tool call so the loop never self-terminates
    provider = ScriptedProvider([_tool_call("echo", {"message": "x"})] * 10)
    config = AgentLoopConfig(max_iterations=2, max_tool_calls=100, task_timeout_seconds=3600)
    loop = _make_loop(provider, registry, approval_svc, repo, config=config)
    result = await loop.run("sess-1", "task-1")

    assert result.status == "failed"
    assert result.error == "loop_limit"

    events = repo.list_events(task_id="task-1")
    error_events = [e for e in events if e.event_type == "error"]
    assert any(e.payload.get("error_type") == "loop_limit" for e in error_events)


@pytest.mark.asyncio
async def test_max_tool_calls_terminates_with_tool_limit(
    repo: AgentRepository,
    registry: ToolRegistry,
    approval_svc: ApprovalService,
) -> None:
    provider = ScriptedProvider([_tool_call("echo", {"message": "x"})] * 10)
    config = AgentLoopConfig(max_iterations=100, max_tool_calls=2, task_timeout_seconds=3600)
    loop = _make_loop(provider, registry, approval_svc, repo, config=config)
    result = await loop.run("sess-1", "task-1")

    assert result.status == "failed"
    assert result.error == "tool_limit"

    events = repo.list_events(task_id="task-1")
    error_events = [e for e in events if e.event_type == "error"]
    assert any(e.payload.get("error_type") == "tool_limit" for e in error_events)


@pytest.mark.asyncio
async def test_task_timeout_terminates_with_timed_out(
    repo: AgentRepository,
    registry: ToolRegistry,
    approval_svc: ApprovalService,
) -> None:
    _start = datetime(2099, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    calls = [0]

    def _clock() -> datetime:
        # First call returns start time; second returns far in the future
        if calls[0] == 0:
            calls[0] += 1
            return _start
        return _start + timedelta(hours=1)

    provider = ScriptedProvider([_tool_call("echo", {"message": "x"})] * 5)
    config = AgentLoopConfig(max_iterations=100, max_tool_calls=100, task_timeout_seconds=10)
    loop = _make_loop(provider, registry, approval_svc, repo, config=config, clock=_clock)
    result = await loop.run("sess-1", "task-1")

    assert result.status == "timed_out"
    assert result.error == "task_timeout"

    events = repo.list_events(task_id="task-1")
    error_events = [e for e in events if e.event_type == "error"]
    assert any(e.payload.get("error_type") == "task_timeout" for e in error_events)


# ---------------------------------------------------------------------------
# AC-6: provider failure
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_provider_unavailable_error_becomes_failed_result(
    repo: AgentRepository,
    registry: ToolRegistry,
    approval_svc: ApprovalService,
) -> None:
    provider = ScriptedProvider([ProviderUnavailableError("Service down")])
    loop = _make_loop(provider, registry, approval_svc, repo)
    result = await loop.run("sess-1", "task-1")

    assert result.status == "failed"
    assert result.error == "provider_unavailable"

    events = repo.list_events(task_id="task-1")
    error_events = [e for e in events if e.event_type == "error"]
    assert any(e.payload.get("error_type") == "provider_unavailable" for e in error_events)


@pytest.mark.asyncio
async def test_provider_error_becomes_failed_result(
    repo: AgentRepository,
    registry: ToolRegistry,
    approval_svc: ApprovalService,
) -> None:
    provider = ScriptedProvider([ProviderError("Non-transient error")])
    loop = _make_loop(provider, registry, approval_svc, repo)
    result = await loop.run("sess-1", "task-1")

    assert result.status == "failed"
    assert result.error == "provider_error"


# ---------------------------------------------------------------------------
# AC-4 / malformed tool call
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_malformed_tool_call_becomes_failed_result(
    repo: AgentRepository,
    registry: ToolRegistry,
    approval_svc: ApprovalService,
) -> None:
    provider = ScriptedProvider([_malformed_tool_call()])
    loop = _make_loop(provider, registry, approval_svc, repo)
    result = await loop.run("sess-1", "task-1")

    assert result.status == "failed"
    assert result.error == "malformed_response"

    events = repo.list_events(task_id="task-1")
    error_events = [e for e in events if e.event_type == "error"]
    assert any(e.payload.get("error_type") == "malformed_response" for e in error_events)


# ---------------------------------------------------------------------------
# Approval-required for mutating tool
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mutating_tool_without_approval_returns_blocked(
    repo: AgentRepository,
    registry: ToolRegistry,
    approval_svc: ApprovalService,
) -> None:
    provider = ScriptedProvider([
        _tool_call("file.write", {"path": "out.txt", "content": "hello"}),
    ])
    loop = _make_loop(provider, registry, approval_svc, repo)
    result = await loop.run("sess-1", "task-1")

    assert result.status == "blocked"
    assert result.error == "approval_requested"

    events = repo.list_events(task_id="task-1")
    event_types = [e.event_type for e in events]
    assert "approval_requested" in event_types
    # Tool should NOT have been invoked
    assert "tool_result" not in event_types


@pytest.mark.asyncio
async def test_mutating_tool_with_pre_approved_approval_executes(
    repo: AgentRepository,
    registry: ToolRegistry,
    approval_svc: ApprovalService,
) -> None:
    from app.agent.approvals import ApprovalDecision, compute_action_fingerprint

    tool_input = {"path": "out.txt", "content": "hello"}
    fingerprint = compute_action_fingerprint(
        "sess-1", "task-1", "file.write", "mutating", tool_input
    )
    # Pre-create and approve
    approval = approval_svc.request_approval(
        "sess-1", "task-1", "file.write", "mutating", tool_input
    )
    approval_svc.decide(approval.approval_id, ApprovalDecision(decision="approved"))

    provider = ScriptedProvider([
        _tool_call("file.write", tool_input),
        _final_answer("file written"),
    ])
    loop = _make_loop(provider, registry, approval_svc, repo)
    result = await loop.run("sess-1", "task-1")

    assert result.status == "succeeded"
    assert result.tool_calls == 1


# ---------------------------------------------------------------------------
# Unknown tool
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unknown_tool_name_fails_task(
    repo: AgentRepository,
    registry: ToolRegistry,
    approval_svc: ApprovalService,
) -> None:
    provider = ScriptedProvider([_tool_call("no.such.tool", {})])
    loop = _make_loop(provider, registry, approval_svc, repo)
    result = await loop.run("sess-1", "task-1")

    assert result.status == "failed"
    assert result.error == "unknown_tool"

    events = repo.list_events(task_id="task-1")
    error_events = [e for e in events if e.event_type == "error"]
    assert any(e.payload.get("error_type") == "unknown_tool" for e in error_events)


# ---------------------------------------------------------------------------
# Task not found
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_with_nonexistent_task_returns_failed(
    repo: AgentRepository,
    registry: ToolRegistry,
    approval_svc: ApprovalService,
) -> None:
    provider = ScriptedProvider([_final_answer("done")])
    loop = _make_loop(provider, registry, approval_svc, repo)
    result = await loop.run("sess-1", "nonexistent-task")
    assert result.status == "failed"
    assert result.error == "task_not_found"


# ---------------------------------------------------------------------------
# Task status transitions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_successful_run_updates_task_to_succeeded(
    repo: AgentRepository,
    registry: ToolRegistry,
    approval_svc: ApprovalService,
) -> None:
    provider = ScriptedProvider([_final_answer("done")])
    loop = _make_loop(provider, registry, approval_svc, repo)
    await loop.run("sess-1", "task-1")
    task = repo.get_task("task-1")
    assert task is not None
    assert task.status == "succeeded"


@pytest.mark.asyncio
async def test_provider_error_updates_task_to_failed(
    repo: AgentRepository,
    registry: ToolRegistry,
    approval_svc: ApprovalService,
) -> None:
    provider = ScriptedProvider([ProviderUnavailableError("down")])
    loop = _make_loop(provider, registry, approval_svc, repo)
    await loop.run("sess-1", "task-1")
    task = repo.get_task("task-1")
    assert task is not None
    assert task.status == "failed"
