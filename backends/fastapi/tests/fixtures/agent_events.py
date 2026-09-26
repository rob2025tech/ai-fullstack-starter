"""Deterministic AgentEvent fixture data for agent event router tests.

``create_task_events(repo)`` populates an in-memory AgentRepository with a
canonical set of events covering every supported event_type so that router
and service tests can rely on predictable sequence numbers and event shapes
without running the real agent loop.

Fixed identifiers
-----------------
SESSION_ID = "test-session"
TASK_ID    = "test-task"

Event sequence
--------------
1  agent_started      — loop configuration
2  assistant_output   — LLM text fragment
3  tool_call          — read_file invocation
4  tool_result        — file content returned
5  approval_requested — file.write requires human approval
6  error              — terminal failure event (provider timeout)
7  completed          — terminal success event (overrides error in separate fixture)
"""

from __future__ import annotations

from app.agent.repository import AgentRepository

SESSION_ID = "test-session"
TASK_ID = "test-task"

# Deterministic event IDs so assertions can reference them by name if needed
_EVT_IDS = {
    "agent_started": "evt-001",
    "assistant_output": "evt-002",
    "tool_call": "evt-003",
    "tool_result": "evt-004",
    "approval_requested": "evt-005",
    "error": "evt-006",
}

_COMPLETED_ID = "evt-007"

_EVENTS = [
    (
        "evt-001",
        "agent_started",
        {"max_iterations": 20, "max_tool_calls": 50, "task_timeout_seconds": 300.0},
    ),
    (
        "evt-002",
        "assistant_output",
        {"content": "I will start by reading the login handler."},
    ),
    (
        "evt-003",
        "tool_call",
        {"tool_name": "repo.read", "tool_input": {"path": "src/auth/login.py"}, "sequence": 1},
    ),
    (
        "evt-004",
        "tool_result",
        {"tool_name": "repo.read", "output": {"content": "def login(request): ..."}, "sequence": 1},
    ),
    (
        "evt-005",
        "approval_requested",
        {
            "approval_id": "appr-001",
            "tool_name": "file.write",
            "risk": "mutating",
            "fingerprint": "sha256:abc123",
        },
    ),
    (
        "evt-006",
        "error",
        {"error_type": "provider_unavailable", "message": "Provider timeout after 30s"},
    ),
]

_COMPLETED_EVENTS = _EVENTS[:-1] + [
    (
        _COMPLETED_ID,
        "completed",
        {"content": "Refactoring applied successfully.", "iterations": 3, "tool_calls": 1},
    ),
]


def create_task_events(
    repo: AgentRepository,
    *,
    terminal: str = "error",
) -> tuple[str, str]:
    """Populate *repo* with a canonical set of task events.

    Parameters
    ----------
    repo:
        An ``AgentRepository`` instance (typically in-memory) to populate.
    terminal:
        ``"error"`` (default) ends the sequence with an error event;
        ``"completed"`` ends with a completed event.

    Returns
    -------
    (session_id, task_id) — the fixed identifiers used for all events.
    """
    repo.create_session(SESSION_ID)
    repo.create_task(TASK_ID, SESSION_ID, "Refactor the login handler")

    events = _COMPLETED_EVENTS if terminal == "completed" else _EVENTS
    for event_id, event_type, payload in events:
        repo.append_event(
            event_id=event_id,
            session_id=SESSION_ID,
            task_id=TASK_ID,
            event_type=event_type,
            payload=payload,
        )
    return SESSION_ID, TASK_ID
