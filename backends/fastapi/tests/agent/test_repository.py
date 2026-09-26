"""Durable repository tests for the agent domain.

These tests verify that agent sessions, tasks, events, and approvals are
persisted correctly to a local SQLite file and survive a repository
close-and-reopen cycle.  No provider calls or external services are used.
All timestamps are deterministic relative to pytest fixture construction.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.agent.repository import (
    AgentEvent,
    AgentRepository,
    AgentSession,
    AgentTask,
    ApprovalRequest,
    CorruptedDataError,
    DuplicateSequenceError,
    InvalidApprovalTransitionError,
    NotFoundError,
    RepositoryError,
)


# ---------------------------------------------------------------------------
# Deterministic fixture helpers
# ---------------------------------------------------------------------------

def _session_id() -> str:
    return f"sess_{uuid.uuid4().hex[:12]}"


def _task_id() -> str:
    return f"task_{uuid.uuid4().hex[:12]}"


def _event_id() -> str:
    return f"evt_{uuid.uuid4().hex[:12]}"


def _approval_id() -> str:
    return f"appr_{uuid.uuid4().hex[:12]}"


# --- Session metadata fixtures ---

SAMPLE_SESSION_METADATA: dict = {
    "client": "web",
    "workspace_root": "/home/dev/project",
    "tags": ["coding", "refactor"],
}

SAMPLE_SESSION_TITLE = "Refactor login handler"


# --- Task prompt fixtures ---

SAMPLE_TASK_PROMPT = (
    "Refactor the login handler in src/auth/login.py to extract "
    "validation logic into a standalone validate_credentials() helper."
)

SAMPLE_TASK_PROMPT_B = (
    "Add docstrings to all public functions in src/auth/sessions.py."
)


# --- Event payload fixtures (no secrets) ---

ASSISTANT_OUTPUT_PAYLOAD: dict = {
    "content": "I'll start by reading the login handler to understand the current structure.",
}

TOOL_CALL_PAYLOAD: dict = {
    "tool": "read_file",
    "input": {"path": "src/auth/login.py"},
}

TOOL_RESULT_PAYLOAD: dict = {
    "tool": "read_file",
    "output": "def login(request):\n    user = request.json.get('user')\n    pwd = request.json.get('password')\n    return authenticate(user, pwd)\n",
}

APPROVAL_REQUESTED_PAYLOAD: dict = {
    "approval_id": "appr_placeholder",
    "action_type": "write_file",
    "action_fingerprint": "sha256:abc123def456",
}

ERROR_PAYLOAD: dict = {
    "message": "Provider timeout after 30s.",
    "code": "provider_error",
}

COMPLETED_PAYLOAD: dict = {
    "result": "Refactoring applied. Created validate_credentials() in src/auth/login.py.",
}


# --- Approval fingerprint fixtures ---

SAMPLE_ACTION_FINGERPRINT = "sha256:abc123def456789deadbeef"
SAMPLE_ACTION_TYPE = "write_file"
SAMPLE_ACTION_PAYLOAD: dict = {
    "path": "src/auth/login.py",
    "content_hash": "sha256:newcontent",
}


def _future_expiry(minutes: int = 15) -> datetime:
    return datetime.now(timezone.utc) + timedelta(minutes=minutes)


def _past_expiry(seconds: int = 1) -> datetime:
    return datetime.now(timezone.utc) - timedelta(seconds=seconds)


# ---------------------------------------------------------------------------
# Pytest fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def repo(tmp_path: Path) -> AgentRepository:
    """An AgentRepository backed by a temporary SQLite file."""
    db_file = tmp_path / "agent_test.db"
    repository = AgentRepository(db_path=db_file)
    yield repository
    repository.close()


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    """Return only the path so tests can reopen the repository manually."""
    return tmp_path / "agent_reopen_test.db"


# ---------------------------------------------------------------------------
# AC-1: Entity fields
# ---------------------------------------------------------------------------


class TestEntityFields:
    def test_agent_session_has_required_fields(self, repo: AgentRepository) -> None:
        sid = _session_id()
        session = repo.create_session(
            session_id=sid,
            title=SAMPLE_SESSION_TITLE,
            metadata=SAMPLE_SESSION_METADATA,
        )
        assert session.session_id == sid
        assert session.status == "active"
        assert session.title == SAMPLE_SESSION_TITLE
        assert session.metadata == SAMPLE_SESSION_METADATA
        assert isinstance(session.created_at, datetime)
        assert isinstance(session.updated_at, datetime)
        assert session.created_at.tzinfo is not None

    def test_agent_task_has_required_fields(self, repo: AgentRepository) -> None:
        sid = _session_id()
        repo.create_session(session_id=sid)
        tid = _task_id()
        task = repo.create_task(task_id=tid, session_id=sid, prompt=SAMPLE_TASK_PROMPT)
        assert task.task_id == tid
        assert task.session_id == sid
        assert task.status == "pending"
        assert task.prompt == SAMPLE_TASK_PROMPT
        assert isinstance(task.created_at, datetime)
        assert isinstance(task.updated_at, datetime)

    def test_agent_event_has_sequence_field(self, repo: AgentRepository) -> None:
        sid = _session_id()
        tid = _task_id()
        repo.create_session(session_id=sid)
        repo.create_task(task_id=tid, session_id=sid, prompt=SAMPLE_TASK_PROMPT)
        event = repo.append_event(
            event_id=_event_id(),
            session_id=sid,
            task_id=tid,
            event_type="assistant_output",
            payload=ASSISTANT_OUTPUT_PAYLOAD,
        )
        assert event.event_id is not None
        assert event.session_id == sid
        assert event.task_id == tid
        assert event.sequence == 1
        assert event.event_type == "assistant_output"
        assert event.payload == ASSISTANT_OUTPUT_PAYLOAD
        assert isinstance(event.created_at, datetime)

    def test_approval_request_has_required_fields(self, repo: AgentRepository) -> None:
        sid = _session_id()
        tid = _task_id()
        aid = _approval_id()
        repo.create_session(session_id=sid)
        repo.create_task(task_id=tid, session_id=sid, prompt=SAMPLE_TASK_PROMPT)
        expiry = _future_expiry()
        approval = repo.create_approval_request(
            approval_id=aid,
            session_id=sid,
            task_id=tid,
            action_type=SAMPLE_ACTION_TYPE,
            action_fingerprint=SAMPLE_ACTION_FINGERPRINT,
            expires_at=expiry,
            action_payload=SAMPLE_ACTION_PAYLOAD,
        )
        assert approval.approval_id == aid
        assert approval.session_id == sid
        assert approval.task_id == tid
        assert approval.action_type == SAMPLE_ACTION_TYPE
        assert approval.action_fingerprint == SAMPLE_ACTION_FINGERPRINT
        assert approval.status == "pending"
        assert approval.action_payload == SAMPLE_ACTION_PAYLOAD
        assert isinstance(approval.created_at, datetime)
        assert isinstance(approval.updated_at, datetime)
        assert isinstance(approval.expires_at, datetime)
        assert approval.consumed_at is None


# ---------------------------------------------------------------------------
# AC-2: Table initialization and schema constraints
# ---------------------------------------------------------------------------


class TestSchemaConstraints:
    def test_duplicate_session_id_raises(self, repo: AgentRepository) -> None:
        sid = _session_id()
        repo.create_session(session_id=sid)
        with pytest.raises(Exception):
            repo.create_session(session_id=sid)

    def test_duplicate_task_id_raises(self, repo: AgentRepository) -> None:
        sid = _session_id()
        tid = _task_id()
        repo.create_session(session_id=sid)
        repo.create_task(task_id=tid, session_id=sid, prompt=SAMPLE_TASK_PROMPT)
        with pytest.raises(Exception):
            repo.create_task(task_id=tid, session_id=sid, prompt="Another prompt")


# ---------------------------------------------------------------------------
# AC-3: Repository method signatures
# ---------------------------------------------------------------------------


class TestRepositoryMethods:
    def test_all_required_methods_exist(self) -> None:
        required = [
            "create_session",
            "get_session",
            "create_task",
            "get_task",
            "update_task_status",
            "append_event",
            "list_events",
            "create_approval_request",
            "list_pending_approvals",
            "decide_approval",
            "consume_approval_once",
        ]
        for method_name in required:
            assert hasattr(AgentRepository, method_name), (
                f"AgentRepository is missing required method: {method_name}"
            )
            assert callable(getattr(AgentRepository, method_name))


# ---------------------------------------------------------------------------
# AC-4: Durability — close and reopen
# ---------------------------------------------------------------------------


class TestDurability:
    def test_session_survives_repository_reopen(self, db_path: Path) -> None:
        sid = _session_id()
        # Write
        repo1 = AgentRepository(db_path=db_path)
        repo1.create_session(
            session_id=sid,
            title=SAMPLE_SESSION_TITLE,
            metadata=SAMPLE_SESSION_METADATA,
        )
        repo1.close()

        # Reopen and read back
        repo2 = AgentRepository(db_path=db_path)
        session = repo2.get_session(sid)
        repo2.close()

        assert session is not None
        assert session.session_id == sid
        assert session.title == SAMPLE_SESSION_TITLE
        assert session.metadata == SAMPLE_SESSION_METADATA

    def test_task_survives_repository_reopen(self, db_path: Path) -> None:
        sid = _session_id()
        tid = _task_id()
        # Write
        repo1 = AgentRepository(db_path=db_path)
        repo1.create_session(session_id=sid)
        repo1.create_task(task_id=tid, session_id=sid, prompt=SAMPLE_TASK_PROMPT)
        repo1.close()

        # Reopen and read back
        repo2 = AgentRepository(db_path=db_path)
        session = repo2.get_session(sid)
        task = repo2.get_task(tid)
        repo2.close()

        assert session is not None
        assert session.session_id == sid
        assert task is not None
        assert task.task_id == tid
        assert task.session_id == sid
        assert task.prompt == SAMPLE_TASK_PROMPT

    def test_events_survive_repository_reopen(self, db_path: Path) -> None:
        sid = _session_id()
        tid = _task_id()
        eid = _event_id()
        # Write
        repo1 = AgentRepository(db_path=db_path)
        repo1.create_session(session_id=sid)
        repo1.create_task(task_id=tid, session_id=sid, prompt=SAMPLE_TASK_PROMPT)
        repo1.append_event(
            event_id=eid,
            session_id=sid,
            task_id=tid,
            event_type="assistant_output",
            payload=ASSISTANT_OUTPUT_PAYLOAD,
        )
        repo1.close()

        # Reopen and list events
        repo2 = AgentRepository(db_path=db_path)
        events = repo2.list_events(task_id=tid)
        repo2.close()

        assert len(events) == 1
        assert events[0].event_id == eid
        assert events[0].sequence == 1
        assert events[0].payload == ASSISTANT_OUTPUT_PAYLOAD


# ---------------------------------------------------------------------------
# AC-5: Session isolation
# ---------------------------------------------------------------------------


class TestSessionIsolation:
    def test_events_for_task_a_do_not_appear_in_task_b(
        self, repo: AgentRepository
    ) -> None:
        sid_a = _session_id()
        sid_b = _session_id()
        tid_a = _task_id()
        tid_b = _task_id()

        repo.create_session(session_id=sid_a)
        repo.create_session(session_id=sid_b)
        repo.create_task(task_id=tid_a, session_id=sid_a, prompt=SAMPLE_TASK_PROMPT)
        repo.create_task(task_id=tid_b, session_id=sid_b, prompt=SAMPLE_TASK_PROMPT_B)

        # Append events to task_a
        for payload in [ASSISTANT_OUTPUT_PAYLOAD, TOOL_CALL_PAYLOAD, TOOL_RESULT_PAYLOAD]:
            repo.append_event(
                event_id=_event_id(),
                session_id=sid_a,
                task_id=tid_a,
                event_type="assistant_output",
                payload=payload,
            )

        # Append one event to task_b
        repo.append_event(
            event_id=_event_id(),
            session_id=sid_b,
            task_id=tid_b,
            event_type="task_accepted",
            payload=None,
        )

        events_a = repo.list_events(task_id=tid_a)
        events_b = repo.list_events(task_id=tid_b)

        assert len(events_a) == 3
        assert len(events_b) == 1

        # No event from task_a appears in task_b's results
        a_event_ids = {e.event_id for e in events_a}
        b_event_ids = {e.event_id for e in events_b}
        assert a_event_ids.isdisjoint(b_event_ids)

    def test_approvals_for_session_a_do_not_appear_for_session_b(
        self, repo: AgentRepository
    ) -> None:
        sid_a = _session_id()
        sid_b = _session_id()
        tid_a = _task_id()
        tid_b = _task_id()

        repo.create_session(session_id=sid_a)
        repo.create_session(session_id=sid_b)
        repo.create_task(task_id=tid_a, session_id=sid_a, prompt=SAMPLE_TASK_PROMPT)
        repo.create_task(task_id=tid_b, session_id=sid_b, prompt=SAMPLE_TASK_PROMPT_B)

        # Create an approval for session_a only
        repo.create_approval_request(
            approval_id=_approval_id(),
            session_id=sid_a,
            task_id=tid_a,
            action_type=SAMPLE_ACTION_TYPE,
            action_fingerprint=SAMPLE_ACTION_FINGERPRINT,
            expires_at=_future_expiry(),
        )

        pending_a = repo.list_pending_approvals(sid_a)
        pending_b = repo.list_pending_approvals(sid_b)

        assert len(pending_a) == 1
        assert len(pending_b) == 0

    def test_tasks_for_different_sessions_are_independent(
        self, repo: AgentRepository
    ) -> None:
        sid_a = _session_id()
        sid_b = _session_id()
        tid_a = _task_id()
        tid_b = _task_id()

        repo.create_session(session_id=sid_a)
        repo.create_session(session_id=sid_b)
        repo.create_task(task_id=tid_a, session_id=sid_a, prompt=SAMPLE_TASK_PROMPT)
        repo.create_task(task_id=tid_b, session_id=sid_b, prompt=SAMPLE_TASK_PROMPT_B)

        task_a = repo.get_task(tid_a)
        task_b = repo.get_task(tid_b)

        assert task_a is not None and task_a.session_id == sid_a
        assert task_b is not None and task_b.session_id == sid_b
        assert task_a.task_id != task_b.task_id


# ---------------------------------------------------------------------------
# AC-6: Fixture helpers exercised
# ---------------------------------------------------------------------------


class TestFixtureHelpers:
    def test_all_event_type_payloads_store_and_retrieve(
        self, repo: AgentRepository
    ) -> None:
        """Validates each representative event_type payload round-trips through SQLite."""
        sid = _session_id()
        tid = _task_id()
        repo.create_session(session_id=sid)
        repo.create_task(task_id=tid, session_id=sid, prompt=SAMPLE_TASK_PROMPT)

        payloads = [
            ("assistant_output", ASSISTANT_OUTPUT_PAYLOAD),
            ("tool_call", TOOL_CALL_PAYLOAD),
            ("tool_result", TOOL_RESULT_PAYLOAD),
            ("approval_requested", APPROVAL_REQUESTED_PAYLOAD),
            ("error", ERROR_PAYLOAD),
            ("completed", COMPLETED_PAYLOAD),
        ]

        for event_type, payload in payloads:
            repo.append_event(
                event_id=_event_id(),
                session_id=sid,
                task_id=tid,
                event_type=event_type,
                payload=payload,
            )

        events = repo.list_events(task_id=tid)
        assert len(events) == len(payloads)

        for i, (event_type, payload) in enumerate(payloads):
            assert events[i].event_type == event_type
            assert events[i].payload == payload
            assert events[i].sequence == i + 1

    def test_sample_approval_fingerprint_fixture_is_deterministic(
        self, repo: AgentRepository
    ) -> None:
        sid = _session_id()
        tid = _task_id()
        repo.create_session(session_id=sid)
        repo.create_task(task_id=tid, session_id=sid, prompt=SAMPLE_TASK_PROMPT)

        aid = _approval_id()
        approval = repo.create_approval_request(
            approval_id=aid,
            session_id=sid,
            task_id=tid,
            action_type=SAMPLE_ACTION_TYPE,
            action_fingerprint=SAMPLE_ACTION_FINGERPRINT,
            expires_at=_future_expiry(),
            action_payload=SAMPLE_ACTION_PAYLOAD,
        )
        assert approval.action_fingerprint == SAMPLE_ACTION_FINGERPRINT
        assert approval.action_payload == SAMPLE_ACTION_PAYLOAD


# ---------------------------------------------------------------------------
# AC-7: Approval consume_approval_once — exact-once guarantee
# ---------------------------------------------------------------------------


class TestApprovalConsumption:
    def _setup_approved_approval(
        self, repo: AgentRepository
    ) -> tuple[str, str, str, str]:
        """Create a session, task, and approval, then approve it.

        Returns (session_id, task_id, approval_id, action_fingerprint).
        """
        sid = _session_id()
        tid = _task_id()
        aid = _approval_id()
        repo.create_session(session_id=sid)
        repo.create_task(task_id=tid, session_id=sid, prompt=SAMPLE_TASK_PROMPT)
        repo.create_approval_request(
            approval_id=aid,
            session_id=sid,
            task_id=tid,
            action_type=SAMPLE_ACTION_TYPE,
            action_fingerprint=SAMPLE_ACTION_FINGERPRINT,
            expires_at=_future_expiry(),
            action_payload=SAMPLE_ACTION_PAYLOAD,
        )
        repo.decide_approval(approval_id=aid, decision="approved")
        return sid, tid, aid, SAMPLE_ACTION_FINGERPRINT

    def test_consume_approval_once_returns_consumed_status(
        self, repo: AgentRepository
    ) -> None:
        _, _, aid, fingerprint = self._setup_approved_approval(repo)
        result = repo.consume_approval_once(aid, fingerprint)
        assert result.approval_id == aid
        assert result.status == "consumed"
        assert result.consumed_at is not None

    def test_second_consume_raises_invalid_transition(
        self, repo: AgentRepository
    ) -> None:
        """Second call for the same approval_id must fail — exact-once guarantee."""
        _, _, aid, fingerprint = self._setup_approved_approval(repo)
        repo.consume_approval_once(aid, fingerprint)
        with pytest.raises(InvalidApprovalTransitionError):
            repo.consume_approval_once(aid, fingerprint)

    def test_consume_with_wrong_fingerprint_raises(
        self, repo: AgentRepository
    ) -> None:
        _, _, aid, _ = self._setup_approved_approval(repo)
        with pytest.raises(InvalidApprovalTransitionError, match="fingerprint"):
            repo.consume_approval_once(aid, "sha256:wrongfingerprint")

    def test_consume_pending_approval_raises(self, repo: AgentRepository) -> None:
        sid = _session_id()
        tid = _task_id()
        aid = _approval_id()
        repo.create_session(session_id=sid)
        repo.create_task(task_id=tid, session_id=sid, prompt=SAMPLE_TASK_PROMPT)
        repo.create_approval_request(
            approval_id=aid,
            session_id=sid,
            task_id=tid,
            action_type=SAMPLE_ACTION_TYPE,
            action_fingerprint=SAMPLE_ACTION_FINGERPRINT,
            expires_at=_future_expiry(),
        )
        # Still pending — not yet approved
        with pytest.raises(InvalidApprovalTransitionError):
            repo.consume_approval_once(aid, SAMPLE_ACTION_FINGERPRINT)

    def test_consume_rejected_approval_raises(self, repo: AgentRepository) -> None:
        sid = _session_id()
        tid = _task_id()
        aid = _approval_id()
        repo.create_session(session_id=sid)
        repo.create_task(task_id=tid, session_id=sid, prompt=SAMPLE_TASK_PROMPT)
        repo.create_approval_request(
            approval_id=aid,
            session_id=sid,
            task_id=tid,
            action_type=SAMPLE_ACTION_TYPE,
            action_fingerprint=SAMPLE_ACTION_FINGERPRINT,
            expires_at=_future_expiry(),
        )
        repo.decide_approval(approval_id=aid, decision="rejected")
        with pytest.raises(InvalidApprovalTransitionError):
            repo.consume_approval_once(aid, SAMPLE_ACTION_FINGERPRINT)

    def test_consume_expired_approval_raises(self, repo: AgentRepository) -> None:
        sid = _session_id()
        tid = _task_id()
        aid = _approval_id()
        repo.create_session(session_id=sid)
        repo.create_task(task_id=tid, session_id=sid, prompt=SAMPLE_TASK_PROMPT)
        repo.create_approval_request(
            approval_id=aid,
            session_id=sid,
            task_id=tid,
            action_type=SAMPLE_ACTION_TYPE,
            action_fingerprint=SAMPLE_ACTION_FINGERPRINT,
            expires_at=_past_expiry(),  # already expired
        )
        # Manually approve it (bypassing decide_approval validation for this edge case)
        repo._db.execute(
            "UPDATE approval_requests SET status = 'approved' WHERE approval_id = ?",
            (aid,),
        )
        with pytest.raises(InvalidApprovalTransitionError, match="expired"):
            repo.consume_approval_once(aid, SAMPLE_ACTION_FINGERPRINT)

    def test_consume_unknown_approval_id_raises_not_found(
        self, repo: AgentRepository
    ) -> None:
        with pytest.raises(NotFoundError):
            repo.consume_approval_once("appr_does_not_exist", SAMPLE_ACTION_FINGERPRINT)


# ---------------------------------------------------------------------------
# Additional edge-case tests
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_get_session_returns_none_for_unknown_id(
        self, repo: AgentRepository
    ) -> None:
        result = repo.get_session("sess_does_not_exist")
        assert result is None

    def test_get_task_returns_none_for_unknown_id(
        self, repo: AgentRepository
    ) -> None:
        result = repo.get_task("task_does_not_exist")
        assert result is None

    def test_update_task_status_raises_for_unknown_task(
        self, repo: AgentRepository
    ) -> None:
        with pytest.raises(NotFoundError):
            repo.update_task_status("task_does_not_exist", "running")

    def test_event_sequence_starts_at_one(self, repo: AgentRepository) -> None:
        sid = _session_id()
        tid = _task_id()
        repo.create_session(session_id=sid)
        repo.create_task(task_id=tid, session_id=sid, prompt=SAMPLE_TASK_PROMPT)
        event = repo.append_event(
            event_id=_event_id(),
            session_id=sid,
            task_id=tid,
            event_type="task_accepted",
        )
        assert event.sequence == 1

    def test_event_sequence_increments_per_task(self, repo: AgentRepository) -> None:
        sid = _session_id()
        tid = _task_id()
        repo.create_session(session_id=sid)
        repo.create_task(task_id=tid, session_id=sid, prompt=SAMPLE_TASK_PROMPT)
        for i in range(1, 5):
            event = repo.append_event(
                event_id=_event_id(),
                session_id=sid,
                task_id=tid,
                event_type="assistant_output",
                payload={"step": i},
            )
            assert event.sequence == i

    def test_event_sequences_are_independent_per_task(
        self, repo: AgentRepository
    ) -> None:
        """Sequences for task_a and task_b both start at 1 and do not interfere."""
        sid = _session_id()
        tid_a = _task_id()
        tid_b = _task_id()
        repo.create_session(session_id=sid)
        repo.create_task(task_id=tid_a, session_id=sid, prompt=SAMPLE_TASK_PROMPT)
        repo.create_task(task_id=tid_b, session_id=sid, prompt=SAMPLE_TASK_PROMPT_B)

        # Append 3 events to task_a
        for _ in range(3):
            repo.append_event(
                event_id=_event_id(),
                session_id=sid,
                task_id=tid_a,
                event_type="assistant_output",
            )

        # First event for task_b must still be sequence 1
        evt_b = repo.append_event(
            event_id=_event_id(),
            session_id=sid,
            task_id=tid_b,
            event_type="task_accepted",
        )
        assert evt_b.sequence == 1

    def test_list_events_after_sequence_filters_correctly(
        self, repo: AgentRepository
    ) -> None:
        sid = _session_id()
        tid = _task_id()
        repo.create_session(session_id=sid)
        repo.create_task(task_id=tid, session_id=sid, prompt=SAMPLE_TASK_PROMPT)
        for _ in range(5):
            repo.append_event(
                event_id=_event_id(),
                session_id=sid,
                task_id=tid,
                event_type="assistant_output",
            )

        # After sequence 2 → should return events with sequence 3, 4, 5
        events = repo.list_events(task_id=tid, after_sequence=2)
        assert len(events) == 3
        assert [e.sequence for e in events] == [3, 4, 5]

    def test_update_task_status_persists_result(self, repo: AgentRepository) -> None:
        sid = _session_id()
        tid = _task_id()
        repo.create_session(session_id=sid)
        repo.create_task(task_id=tid, session_id=sid, prompt=SAMPLE_TASK_PROMPT)
        updated = repo.update_task_status(
            tid, "succeeded", result="Refactoring applied."
        )
        assert updated.status == "succeeded"
        assert updated.result == "Refactoring applied."

    def test_decide_approval_invalid_decision_raises(
        self, repo: AgentRepository
    ) -> None:
        sid = _session_id()
        tid = _task_id()
        aid = _approval_id()
        repo.create_session(session_id=sid)
        repo.create_task(task_id=tid, session_id=sid, prompt=SAMPLE_TASK_PROMPT)
        repo.create_approval_request(
            approval_id=aid,
            session_id=sid,
            task_id=tid,
            action_type=SAMPLE_ACTION_TYPE,
            action_fingerprint=SAMPLE_ACTION_FINGERPRINT,
            expires_at=_future_expiry(),
        )
        with pytest.raises(InvalidApprovalTransitionError):
            repo.decide_approval(aid, "maybe")

    def test_decide_non_pending_approval_raises(self, repo: AgentRepository) -> None:
        sid = _session_id()
        tid = _task_id()
        aid = _approval_id()
        repo.create_session(session_id=sid)
        repo.create_task(task_id=tid, session_id=sid, prompt=SAMPLE_TASK_PROMPT)
        repo.create_approval_request(
            approval_id=aid,
            session_id=sid,
            task_id=tid,
            action_type=SAMPLE_ACTION_TYPE,
            action_fingerprint=SAMPLE_ACTION_FINGERPRINT,
            expires_at=_future_expiry(),
        )
        repo.decide_approval(aid, "approved")
        # Second decide on already-approved → must fail
        with pytest.raises(InvalidApprovalTransitionError):
            repo.decide_approval(aid, "rejected")

    def test_list_events_requires_session_or_task_id(
        self, repo: AgentRepository
    ) -> None:
        with pytest.raises(RepositoryError):
            repo.list_events()

    def test_append_event_with_null_payload(self, repo: AgentRepository) -> None:
        sid = _session_id()
        tid = _task_id()
        repo.create_session(session_id=sid)
        repo.create_task(task_id=tid, session_id=sid, prompt=SAMPLE_TASK_PROMPT)
        event = repo.append_event(
            event_id=_event_id(),
            session_id=sid,
            task_id=tid,
            event_type="task_accepted",
            payload=None,
        )
        assert event.payload is None
        # Read back
        events = repo.list_events(task_id=tid)
        assert events[0].payload is None

    def test_session_metadata_round_trips_through_sqlite(
        self, repo: AgentRepository
    ) -> None:
        sid = _session_id()
        repo.create_session(
            session_id=sid, metadata=SAMPLE_SESSION_METADATA
        )
        recovered = repo.get_session(sid)
        assert recovered is not None
        assert recovered.metadata == SAMPLE_SESSION_METADATA
