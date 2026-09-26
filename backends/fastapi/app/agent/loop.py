"""Bounded provider-agnostic agent execution loop.

Provides:
  AgentLoopConfig   — configurable limits (max_iterations, max_tool_calls,
                      task_timeout_seconds)
  AgentLoopResult   — terminal result with status, final_answer, and metrics
  AgentLoopError    — structured exception for loop-level failures
  AgentLoop         — the main loop class with an async ``run()`` method

Design
------
- AgentLoop depends only on ProviderPolicy, ToolRegistry, ApprovalService, and
  AgentRepository interfaces; no concrete provider adapters are imported.
- Provider responses are parsed for a simple JSON intent protocol::

      {"intent": "tool_call", "tool_name": "file.read", "tool_input": {...}}
      {"intent": "final_answer", "content": "..."}

  Any response that does not match either schema is treated as a plain-text
  final answer, enabling natural LLM responses to terminate the loop.
- Limit checks (iteration, tool-call, timeout) occur at the TOP of every
  iteration before any provider or tool I/O.
- An injectable ``clock`` callable makes timeout assertions deterministic in
  tests without time.sleep().
- Every state transition appends a structured event to the persistence store
  so the full run is auditable after the loop returns.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable

from app.agent.approvals import ApprovalError, ApprovalService, compute_action_fingerprint
from app.agent.repository import AgentRepository
from app.agent.tools.registry import ToolInvocationError, ToolRegistry, ToolRisk
from app.core.errors import ProviderError, ProviderUnavailableError
from app.providers.llm.policy import ProviderPolicy

__all__ = [
    "AgentLoop",
    "AgentLoopConfig",
    "AgentLoopResult",
    "AgentLoopError",
]


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass
class AgentLoopConfig:
    """Configurable limits for a single AgentLoop run.

    Attributes
    ----------
    max_iterations:
        Maximum number of provider generate calls before the loop fails with
        ``loop_limit``.
    max_tool_calls:
        Maximum cumulative tool invocations before the loop fails with
        ``tool_limit``.
    task_timeout_seconds:
        Overall wall-clock budget (in seconds) measured from the first
        iteration.  Checked at the top of every iteration via the injectable
        clock.
    """

    max_iterations: int = 20
    max_tool_calls: int = 50
    task_timeout_seconds: float = 300.0


# ---------------------------------------------------------------------------
# Result
# ---------------------------------------------------------------------------


@dataclass
class AgentLoopResult:
    """Terminal result returned by ``AgentLoop.run``.

    Attributes
    ----------
    status:
        One of ``succeeded``, ``failed``, ``timed_out``, ``blocked``,
        or ``cancelled``.
    task_id:
        The task that was executed.
    final_answer:
        The final answer string when ``status == "succeeded"``.
    error:
        Machine-readable reason string when ``status != "succeeded"``.
    iterations:
        Number of provider generate calls made.
    tool_calls:
        Cumulative number of tool invocations made.
    """

    status: str
    task_id: str
    final_answer: str | None = None
    error: str | None = None
    iterations: int = 0
    tool_calls: int = 0


# ---------------------------------------------------------------------------
# Exception
# ---------------------------------------------------------------------------


class AgentLoopError(Exception):
    """Raised for loop-level configuration or initialisation failures.

    Normal runtime failures (provider errors, tool errors, limit breaches) are
    returned as ``AgentLoopResult`` with an appropriate status; this exception
    is reserved for programming errors that should not happen at runtime.
    """

    def __init__(self, reason: str, message: str) -> None:
        self.reason = reason
        self.message = message
        super().__init__(message)


# ---------------------------------------------------------------------------
# Intent parsing
# ---------------------------------------------------------------------------

_TOOL_CALL_INTENT = "tool_call"
_FINAL_ANSWER_INTENT = "final_answer"


def _parse_intent(response: str) -> dict:
    """Parse the provider response into a typed intent dict.

    Returns one of:
    - ``{"type": "final_answer", "content": str}``
    - ``{"type": "tool_call", "tool_name": str, "tool_input": dict}``
    - ``{"type": "malformed", "content": str, "reason": str}``
    """
    stripped = response.strip()
    # Try to parse as JSON
    try:
        data = json.loads(stripped)
    except json.JSONDecodeError:
        # Non-JSON: treat as plain-text final answer
        return {"type": _FINAL_ANSWER_INTENT, "content": response}

    if not isinstance(data, dict):
        return {"type": _FINAL_ANSWER_INTENT, "content": response}

    intent = data.get("intent")

    if intent == _FINAL_ANSWER_INTENT:
        content = data.get("content", "")
        if not isinstance(content, str):
            content = json.dumps(content)
        return {"type": _FINAL_ANSWER_INTENT, "content": content}

    if intent == _TOOL_CALL_INTENT:
        tool_name = data.get("tool_name")
        tool_input = data.get("tool_input")
        if not isinstance(tool_name, str) or not tool_name:
            return {
                "type": "malformed",
                "content": response,
                "reason": "tool_call intent missing valid tool_name",
            }
        if not isinstance(tool_input, dict):
            return {
                "type": "malformed",
                "content": response,
                "reason": "tool_call intent missing valid tool_input dict",
            }
        return {"type": _TOOL_CALL_INTENT, "tool_name": tool_name, "tool_input": tool_input}

    # Unknown intent: treat as final answer
    return {"type": _FINAL_ANSWER_INTENT, "content": response}


# ---------------------------------------------------------------------------
# Loop
# ---------------------------------------------------------------------------


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


class AgentLoop:
    """Provider-agnostic bounded agent execution loop.

    Parameters
    ----------
    provider:
        ``ProviderPolicy`` instance used for all generate calls.
    registry:
        ``ToolRegistry`` containing all available tools.
    approval_service:
        ``ApprovalService`` used to gate mutating and unsafe tool actions.
    repo:
        ``AgentRepository`` for task state and event persistence.
    config:
        Loop limits; defaults to ``AgentLoopConfig()``.
    clock:
        Callable returning the current UTC datetime.  Inject a fake clock in
        tests to make timeout assertions deterministic.
    """

    def __init__(
        self,
        provider: ProviderPolicy,
        registry: ToolRegistry,
        approval_service: ApprovalService,
        repo: AgentRepository,
        config: AgentLoopConfig | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._provider = provider
        self._registry = registry
        self._approval_service = approval_service
        self._repo = repo
        self._config = config or AgentLoopConfig()
        self._clock = clock or _now_utc

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def run(self, session_id: str, task_id: str) -> AgentLoopResult:
        """Execute the agent loop for the given session and task.

        Updates task status from ``pending`` → ``running`` → terminal state.
        Appends structured events for every significant state transition.

        Returns an ``AgentLoopResult`` with a terminal status on all paths;
        never raises an exception (unhandled errors are caught and persisted).
        """
        # Load and validate task
        task = self._repo.get_task(task_id)
        if task is None:
            return AgentLoopResult(
                status="failed",
                task_id=task_id,
                error="task_not_found",
            )

        # Transition to running
        self._repo.update_task_status(task_id, "running")

        # Emit agent_started
        self._emit_event(
            session_id,
            task_id,
            "agent_started",
            {
                "max_iterations": self._config.max_iterations,
                "max_tool_calls": self._config.max_tool_calls,
                "task_timeout_seconds": self._config.task_timeout_seconds,
            },
        )

        start_time = self._clock()
        iterations = 0
        tool_calls = 0
        # Build running context; the provider receives the full accumulated prompt.
        context_parts: list[str] = [task.prompt]

        try:
            while True:
                # ---- Limit checks (before any I/O) ----------------------
                if iterations >= self._config.max_iterations:
                    self._emit_event(
                        session_id,
                        task_id,
                        "error",
                        {"error_type": "loop_limit", "iterations": iterations},
                    )
                    self._repo.update_task_status(task_id, "failed", result="loop_limit")
                    return AgentLoopResult(
                        status="failed",
                        task_id=task_id,
                        error="loop_limit",
                        iterations=iterations,
                        tool_calls=tool_calls,
                    )

                elapsed = (self._clock() - start_time).total_seconds()
                if elapsed >= self._config.task_timeout_seconds:
                    self._emit_event(
                        session_id,
                        task_id,
                        "error",
                        {
                            "error_type": "task_timeout",
                            "elapsed_seconds": elapsed,
                            "timeout_seconds": self._config.task_timeout_seconds,
                        },
                    )
                    self._repo.update_task_status(task_id, "timed_out", result="task_timeout")
                    return AgentLoopResult(
                        status="timed_out",
                        task_id=task_id,
                        error="task_timeout",
                        iterations=iterations,
                        tool_calls=tool_calls,
                    )

                # ---- Provider call --------------------------------------
                iterations += 1
                prompt = "\n\n".join(context_parts)
                try:
                    response = await self._provider.generate(prompt)
                except ProviderUnavailableError as exc:
                    self._emit_event(
                        session_id,
                        task_id,
                        "error",
                        {"error_type": "provider_unavailable", "message": exc.message},
                    )
                    self._repo.update_task_status(
                        task_id, "failed", result="provider_unavailable"
                    )
                    return AgentLoopResult(
                        status="failed",
                        task_id=task_id,
                        error="provider_unavailable",
                        iterations=iterations,
                        tool_calls=tool_calls,
                    )
                except ProviderError as exc:
                    self._emit_event(
                        session_id,
                        task_id,
                        "error",
                        {"error_type": "provider_error", "message": exc.message},
                    )
                    self._repo.update_task_status(task_id, "failed", result="provider_error")
                    return AgentLoopResult(
                        status="failed",
                        task_id=task_id,
                        error="provider_error",
                        iterations=iterations,
                        tool_calls=tool_calls,
                    )

                # Emit raw assistant output for audit
                self._emit_event(
                    session_id,
                    task_id,
                    "assistant_output",
                    {"content": response},
                )

                # ---- Intent parsing -------------------------------------
                intent = _parse_intent(response)

                if intent["type"] == _FINAL_ANSWER_INTENT:
                    content: str = intent["content"]
                    self._emit_event(
                        session_id,
                        task_id,
                        "completed",
                        {"content": content, "iterations": iterations, "tool_calls": tool_calls},
                    )
                    self._repo.update_task_status(task_id, "succeeded", result=content)
                    return AgentLoopResult(
                        status="succeeded",
                        task_id=task_id,
                        final_answer=content,
                        iterations=iterations,
                        tool_calls=tool_calls,
                    )

                if intent["type"] == "malformed":
                    reason: str = intent.get("reason", "malformed_response")
                    self._emit_event(
                        session_id,
                        task_id,
                        "error",
                        {"error_type": "malformed_response", "reason": reason},
                    )
                    self._repo.update_task_status(task_id, "failed", result="malformed_response")
                    return AgentLoopResult(
                        status="failed",
                        task_id=task_id,
                        error="malformed_response",
                        iterations=iterations,
                        tool_calls=tool_calls,
                    )

                # intent["type"] == "tool_call"
                tool_name: str = intent["tool_name"]
                tool_input: dict = intent["tool_input"]

                # ---- Tool call limit ------------------------------------
                if tool_calls >= self._config.max_tool_calls:
                    self._emit_event(
                        session_id,
                        task_id,
                        "error",
                        {"error_type": "tool_limit", "tool_calls": tool_calls},
                    )
                    self._repo.update_task_status(task_id, "failed", result="tool_limit")
                    return AgentLoopResult(
                        status="failed",
                        task_id=task_id,
                        error="tool_limit",
                        iterations=iterations,
                        tool_calls=tool_calls,
                    )

                # ---- Tool lookup ----------------------------------------
                tool_def = self._registry.get(tool_name)
                if tool_def is None:
                    self._emit_event(
                        session_id,
                        task_id,
                        "error",
                        {"error_type": "unknown_tool", "tool_name": tool_name},
                    )
                    self._repo.update_task_status(task_id, "failed", result="unknown_tool")
                    return AgentLoopResult(
                        status="failed",
                        task_id=task_id,
                        error="unknown_tool",
                        iterations=iterations,
                        tool_calls=tool_calls,
                    )

                # ---- Approval gate for mutating / unsafe tools ----------
                if tool_def.risk in (ToolRisk.mutating, ToolRisk.unsafe):
                    result = await self._handle_approval_gate(
                        session_id=session_id,
                        task_id=task_id,
                        tool_name=tool_name,
                        tool_input=tool_input,
                        risk=tool_def.risk,
                        iterations=iterations,
                        tool_calls=tool_calls,
                    )
                    if result is not None:
                        # Approval not available; result is a terminal AgentLoopResult
                        return result

                # ---- Emit tool_call event with sequence ------------------
                tool_calls += 1
                self._emit_event(
                    session_id,
                    task_id,
                    "tool_call",
                    {
                        "tool_name": tool_name,
                        "tool_input": tool_input,
                        "risk": tool_def.risk.value,
                        "sequence": tool_calls,
                    },
                )

                # ---- Invoke tool ----------------------------------------
                try:
                    tool_result = await self._registry.invoke(tool_name, tool_input)
                except ToolInvocationError as exc:
                    self._emit_event(
                        session_id,
                        task_id,
                        "error",
                        {
                            "error_type": "tool_error",
                            "tool_name": tool_name,
                            "reason": exc.reason,
                        },
                    )
                    self._repo.update_task_status(task_id, "failed", result="tool_error")
                    return AgentLoopResult(
                        status="failed",
                        task_id=task_id,
                        error="tool_error",
                        iterations=iterations,
                        tool_calls=tool_calls,
                    )

                # ---- Emit tool_result event ------------------------------
                output_data = (
                    tool_result.output.model_dump()
                    if hasattr(tool_result.output, "model_dump")
                    else {}
                )
                self._emit_event(
                    session_id,
                    task_id,
                    "tool_result",
                    {
                        "tool_name": tool_name,
                        "output": output_data,
                        "sequence": tool_calls,
                    },
                )

                # Append observation to context so the provider sees it next iteration
                context_parts.append(
                    f"Tool {tool_name} result: {json.dumps(output_data, separators=(',', ':'))}"
                )

        except Exception as exc:
            # Catch-all: persist before re-surfacing as a failed result
            self._emit_event(
                session_id,
                task_id,
                "error",
                {"error_type": "error", "message": str(exc)},
            )
            try:
                self._repo.update_task_status(task_id, "failed", result="error")
            except Exception:
                pass
            return AgentLoopResult(
                status="failed",
                task_id=task_id,
                error="error",
                iterations=iterations,
                tool_calls=tool_calls,
            )

    # ------------------------------------------------------------------
    # Approval gate helper
    # ------------------------------------------------------------------

    async def _handle_approval_gate(
        self,
        *,
        session_id: str,
        task_id: str,
        tool_name: str,
        tool_input: dict,
        risk: ToolRisk,
        iterations: int,
        tool_calls: int,
    ) -> AgentLoopResult | None:
        """Check for an approved approval and consume it, or request one.

        Returns ``None`` when an approval was successfully consumed (caller
        should proceed with tool invocation).  Returns a terminal
        ``AgentLoopResult`` when no approved approval exists.
        """
        fingerprint = compute_action_fingerprint(
            session_id, task_id, tool_name, risk.value, tool_input
        )

        # Look for an existing approved approval for this exact action
        approved = self._repo.find_approved_approval(session_id, task_id, fingerprint)

        if approved is not None:
            # Consume it atomically
            try:
                self._approval_service.consume_approval(
                    approved.approval_id,
                    session_id,
                    task_id,
                    tool_name,
                    fingerprint,
                )
                return None  # Gate passed
            except ApprovalError as exc:
                # Approval was consumed by a concurrent worker or expired
                self._emit_event(
                    session_id,
                    task_id,
                    "error",
                    {
                        "error_type": "approval_error",
                        "tool_name": tool_name,
                        "reason": exc.reason,
                    },
                )
                self._repo.update_task_status(task_id, "failed", result="approval_error")
                return AgentLoopResult(
                    status="failed",
                    task_id=task_id,
                    error="approval_error",
                    iterations=iterations,
                    tool_calls=tool_calls,
                )

        # No approved approval — create a pending request and stop
        approval = self._approval_service.request_approval(
            session_id, task_id, tool_name, risk.value, tool_input
        )
        self._emit_event(
            session_id,
            task_id,
            "approval_requested",
            {
                "approval_id": approval.approval_id,
                "tool_name": tool_name,
                "risk": risk.value,
                "fingerprint": fingerprint,
            },
        )
        self._repo.update_task_status(task_id, "blocked", result="approval_requested")
        return AgentLoopResult(
            status="blocked",
            task_id=task_id,
            error="approval_requested",
            iterations=iterations,
            tool_calls=tool_calls,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _emit_event(
        self,
        session_id: str,
        task_id: str,
        event_type: str,
        payload: dict,
    ) -> None:
        self._repo.append_event(
            event_id=str(uuid.uuid4()),
            session_id=session_id,
            task_id=task_id,
            event_type=event_type,
            payload=payload,
        )
