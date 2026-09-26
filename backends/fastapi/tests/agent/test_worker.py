"""Unit tests for LocalAgentWorker (backends/fastapi/app/agent/worker.py).

All tests use in-memory AgentRepository and scripted providers.
"""

from __future__ import annotations

import json
from typing import AsyncIterator

import pytest

from app.agent.approvals import ApprovalService
from app.agent.loop import AgentLoop, AgentLoopConfig
from app.agent.repository import AgentRepository
from app.agent.tools.registry import ToolDefinition, ToolRegistry, ToolRisk
from app.agent.worker import LocalAgentWorker
from app.core.errors import ProviderUnavailableError
from app.providers.llm.base import LLMProvider
from app.providers.llm.policy import ProviderPolicy, ProviderPolicyConfig
from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Scripted provider (same pattern as test_loop.py)
# ---------------------------------------------------------------------------


class ScriptedProvider(LLMProvider):
    def __init__(self, responses: list) -> None:
        self._responses = list(responses)
        self._index = 0

    async def generate(self, prompt: str) -> str:
        if self._index >= len(self._responses):
            from app.core.errors import ProviderError
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
# Fixtures
# ---------------------------------------------------------------------------


class EchoInput(BaseModel):
    message: str


class EchoOutput(BaseModel):
    echoed: str


async def _echo(inp: EchoInput) -> EchoOutput:
    return EchoOutput(echoed=inp.message)


ECHO_TOOL = ToolDefinition(
    name="echo",
    description="Echo",
    input_schema=EchoInput,
    output_schema=EchoOutput,
    callable=_echo,
    risk=ToolRisk.read_only,
)


@pytest.fixture()
def repo() -> AgentRepository:
    r = AgentRepository()
    r.create_session("sess-1")
    r.create_task("task-1", "sess-1", "worker test prompt")
    return r


@pytest.fixture()
def registry() -> ToolRegistry:
    reg = ToolRegistry()
    reg.register(ECHO_TOOL)
    return reg


@pytest.fixture()
def approval_svc(repo: AgentRepository) -> ApprovalService:
    return ApprovalService(repo)


def _make_worker(
    responses: list,
    repo: AgentRepository,
    registry: ToolRegistry,
    approval_svc: ApprovalService,
    config: AgentLoopConfig | None = None,
) -> LocalAgentWorker:
    provider = ScriptedProvider(responses)
    policy = ProviderPolicy(provider, ProviderPolicyConfig(timeout_seconds=30, max_retries=0))
    loop = AgentLoop(
        provider=policy,
        registry=registry,
        approval_service=approval_svc,
        repo=repo,
        config=config,
    )
    return LocalAgentWorker(loop, repo)


# ---------------------------------------------------------------------------
# AC-7: worker claims and updates task
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_once_claims_pending_task_and_sets_succeeded(
    repo: AgentRepository,
    registry: ToolRegistry,
    approval_svc: ApprovalService,
) -> None:
    worker = _make_worker([_final_answer("done")], repo, registry, approval_svc)
    result = await worker.run_once()

    assert result is not None
    assert result.status == "succeeded"
    task = repo.get_task("task-1")
    assert task is not None
    assert task.status == "succeeded"


@pytest.mark.asyncio
async def test_run_once_returns_none_when_no_tasks(
    repo: AgentRepository,
    registry: ToolRegistry,
    approval_svc: ApprovalService,
) -> None:
    # No pending tasks (all start as pending but repo has one — exhaust it first)
    worker = _make_worker([_final_answer("done")], repo, registry, approval_svc)
    await worker.run_once()  # consume the only task

    # Now no pending tasks remain
    result = await worker.run_once()
    assert result is None


@pytest.mark.asyncio
async def test_run_once_updates_failed_task_on_provider_error(
    repo: AgentRepository,
    registry: ToolRegistry,
    approval_svc: ApprovalService,
) -> None:
    worker = _make_worker([ProviderUnavailableError("down")], repo, registry, approval_svc)
    result = await worker.run_once()

    assert result is not None
    assert result.status == "failed"
    task = repo.get_task("task-1")
    assert task is not None
    assert task.status == "failed"


@pytest.mark.asyncio
async def test_run_task_targets_specific_task(
    repo: AgentRepository,
    registry: ToolRegistry,
    approval_svc: ApprovalService,
) -> None:
    # Create a second task
    repo.create_task("task-2", "sess-1", "second prompt")
    worker = _make_worker([_final_answer("task 2 done")], repo, registry, approval_svc)
    result = await worker.run_task("sess-1", "task-2")

    assert result.status == "succeeded"
    task2 = repo.get_task("task-2")
    assert task2 is not None
    assert task2.status == "succeeded"

    # task-1 remains pending
    task1 = repo.get_task("task-1")
    assert task1 is not None
    assert task1.status == "pending"


@pytest.mark.asyncio
async def test_worker_processes_multiple_tasks_sequentially(
    repo: AgentRepository,
    registry: ToolRegistry,
    approval_svc: ApprovalService,
) -> None:
    repo.create_task("task-2", "sess-1", "second prompt")
    # Two separate workers, each with one scripted response
    worker1 = _make_worker([_final_answer("first")], repo, registry, approval_svc)
    worker2 = _make_worker([_final_answer("second")], repo, registry, approval_svc)

    r1 = await worker1.run_once()
    r2 = await worker2.run_once()

    assert r1 is not None and r1.status == "succeeded"
    assert r2 is not None and r2.status == "succeeded"

    # Both tasks completed
    t1 = repo.get_task("task-1")
    t2 = repo.get_task("task-2")
    assert t1 is not None and t1.status == "succeeded"
    assert t2 is not None and t2.status == "succeeded"


@pytest.mark.asyncio
async def test_run_once_with_tool_call_succeeds(
    repo: AgentRepository,
    registry: ToolRegistry,
    approval_svc: ApprovalService,
) -> None:
    worker = _make_worker(
        [
            _tool_call("echo", {"message": "hi"}),
            _final_answer("echoed"),
        ],
        repo,
        registry,
        approval_svc,
    )
    result = await worker.run_once()
    assert result is not None
    assert result.status == "succeeded"
    assert result.tool_calls == 1


@pytest.mark.asyncio
async def test_worker_captures_unhandled_loop_exception_as_failure(
    repo: AgentRepository,
    registry: ToolRegistry,
    approval_svc: ApprovalService,
) -> None:
    # Use a BrokenProvider that raises an unexpected exception type not handled by the loop
    class BrokenProvider(LLMProvider):
        async def generate(self, prompt: str) -> str:
            raise RuntimeError("something totally unexpected")

        async def stream(self, prompt: str) -> AsyncIterator[str]:  # type: ignore[override]
            raise NotImplementedError

        @property
        def model_name(self) -> str:
            return "broken"

    policy = ProviderPolicy(
        BrokenProvider(), ProviderPolicyConfig(timeout_seconds=30, max_retries=0)
    )
    loop = AgentLoop(
        provider=policy,
        registry=registry,
        approval_service=approval_svc,
        repo=repo,
    )
    worker = LocalAgentWorker(loop, repo)
    result = await worker.run_once()

    # The loop wraps RuntimeError as a ProviderError → failed result
    assert result is not None
    assert result.status == "failed"
