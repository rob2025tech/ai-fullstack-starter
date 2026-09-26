"""Unit tests for AgentEvent persistence and replay filtering (AC-4).

Tests the repository-level event store directly (no HTTP layer) to verify:
- after_sequence pagination
- empty-task replay
- terminal event serialization
"""

from __future__ import annotations

import pytest

from app.agent.repository import AgentRepository
from tests.fixtures.agent_events import SESSION_ID, TASK_ID, create_task_events


@pytest.fixture()
def repo_with_events() -> AgentRepository:
    repo = AgentRepository()
    create_task_events(repo, terminal="error")
    return repo


@pytest.fixture()
def repo_completed_events() -> AgentRepository:
    repo = AgentRepository()
    create_task_events(repo, terminal="completed")
    return repo


@pytest.fixture()
def repo_empty() -> AgentRepository:
    repo = AgentRepository()
    repo.create_session(SESSION_ID)
    repo.create_task(TASK_ID, SESSION_ID, "empty task")
    return repo


# ---------------------------------------------------------------------------
# AC-4: replay filtering with after_sequence
# ---------------------------------------------------------------------------


def test_list_events_returns_all_when_after_sequence_is_zero(
    repo_with_events: AgentRepository,
) -> None:
    events = repo_with_events.list_events(task_id=TASK_ID, after_sequence=0)
    assert len(events) == 6  # 6 events in the fixture


def test_list_events_after_sequence_returns_only_later_events(
    repo_with_events: AgentRepository,
) -> None:
    events = repo_with_events.list_events(task_id=TASK_ID, after_sequence=3)
    assert all(e.sequence > 3 for e in events)
    assert len(events) == 3  # sequences 4, 5, 6


def test_list_events_after_sequence_at_end_returns_empty(
    repo_with_events: AgentRepository,
) -> None:
    events = repo_with_events.list_events(task_id=TASK_ID, after_sequence=999)
    assert events == []


def test_list_events_empty_task_returns_empty_list(
    repo_empty: AgentRepository,
) -> None:
    events = repo_empty.list_events(task_id=TASK_ID, after_sequence=0)
    assert events == []


# ---------------------------------------------------------------------------
# AC-4: event ordering
# ---------------------------------------------------------------------------


def test_list_events_are_in_ascending_sequence_order(
    repo_with_events: AgentRepository,
) -> None:
    events = repo_with_events.list_events(task_id=TASK_ID)
    sequences = [e.sequence for e in events]
    assert sequences == sorted(sequences)


def test_list_events_sequences_are_unique(repo_with_events: AgentRepository) -> None:
    events = repo_with_events.list_events(task_id=TASK_ID)
    sequences = [e.sequence for e in events]
    assert len(sequences) == len(set(sequences))


# ---------------------------------------------------------------------------
# AC-4: event field completeness
# ---------------------------------------------------------------------------


def test_list_events_all_fields_present(repo_with_events: AgentRepository) -> None:
    events = repo_with_events.list_events(task_id=TASK_ID)
    for event in events:
        assert event.event_id
        assert event.session_id == SESSION_ID
        assert event.task_id == TASK_ID
        assert event.sequence > 0
        assert event.event_type
        assert event.created_at is not None


# ---------------------------------------------------------------------------
# AC-4: terminal event serialization
# ---------------------------------------------------------------------------


def test_error_terminal_event_has_expected_payload(
    repo_with_events: AgentRepository,
) -> None:
    events = repo_with_events.list_events(task_id=TASK_ID)
    error_events = [e for e in events if e.event_type == "error"]
    assert len(error_events) == 1
    assert error_events[0].payload is not None
    assert "error_type" in error_events[0].payload


def test_completed_terminal_event_has_expected_payload(
    repo_completed_events: AgentRepository,
) -> None:
    events = repo_completed_events.list_events(task_id=TASK_ID)
    completed_events = [e for e in events if e.event_type == "completed"]
    assert len(completed_events) == 1
    assert completed_events[0].payload is not None
    assert "content" in completed_events[0].payload


def test_approval_requested_event_has_approval_id(
    repo_with_events: AgentRepository,
) -> None:
    events = repo_with_events.list_events(task_id=TASK_ID)
    appr_events = [e for e in events if e.event_type == "approval_requested"]
    assert len(appr_events) == 1
    assert appr_events[0].payload is not None
    assert "approval_id" in appr_events[0].payload


# ---------------------------------------------------------------------------
# AC-4: fixture completeness — all required event types are present
# ---------------------------------------------------------------------------


def test_fixture_contains_all_required_event_types(
    repo_with_events: AgentRepository,
) -> None:
    events = repo_with_events.list_events(task_id=TASK_ID)
    event_types = {e.event_type for e in events}
    required = {
        "agent_started",
        "assistant_output",
        "tool_call",
        "tool_result",
        "approval_requested",
        "error",
    }
    assert required.issubset(event_types), (
        f"Missing event types: {required - event_types}"
    )


def test_completed_fixture_contains_completed_event(
    repo_completed_events: AgentRepository,
) -> None:
    events = repo_completed_events.list_events(task_id=TASK_ID)
    event_types = {e.event_type for e in events}
    assert "completed" in event_types
    assert "error" not in event_types
