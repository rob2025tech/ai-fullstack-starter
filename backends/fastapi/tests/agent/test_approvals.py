"""Unit and integration tests for the exact-once approval service.

All tests use in-memory AgentRepository and an injectable fake clock;
no sleeps, no filesystem access, no external services.
asyncio_mode=auto (pyproject.toml) is not needed here — all methods are sync.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.agent.approvals import (
    ApprovalDecision,
    ApprovalError,
    ApprovalService,
    ApprovalStatus,
    compute_action_fingerprint,
)
from app.agent.repository import AgentRepository


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_FIXED_TIME = datetime(2099, 6, 1, 12, 0, 0, tzinfo=timezone.utc)


def _make_clock(dt: datetime = _FIXED_TIME):
    return lambda: dt


@pytest.fixture()
def repo() -> AgentRepository:
    r = AgentRepository()
    r.create_session("sess-1")
    r.create_task("task-1", "sess-1", "test prompt")
    return r


@pytest.fixture()
def svc(repo: AgentRepository) -> ApprovalService:
    return ApprovalService(repo, clock=_make_clock())


# ---------------------------------------------------------------------------
# compute_action_fingerprint
# ---------------------------------------------------------------------------


def test_fingerprint_deterministic_for_same_input() -> None:
    fp1 = compute_action_fingerprint("s", "t", "file.write", "mutating", {"path": "a.txt"})
    fp2 = compute_action_fingerprint("s", "t", "file.write", "mutating", {"path": "a.txt"})
    assert fp1 == fp2


def test_fingerprint_same_for_different_key_order() -> None:
    fp1 = compute_action_fingerprint(
        "s", "t", "file.write", "mutating", {"path": "a.txt", "overwrite": False}
    )
    fp2 = compute_action_fingerprint(
        "s", "t", "file.write", "mutating", {"overwrite": False, "path": "a.txt"}
    )
    assert fp1 == fp2


def test_fingerprint_differs_for_different_path() -> None:
    fp1 = compute_action_fingerprint("s", "t", "file.write", "mutating", {"path": "a.txt"})
    fp2 = compute_action_fingerprint("s", "t", "file.write", "mutating", {"path": "b.txt"})
    assert fp1 != fp2


def test_fingerprint_differs_for_different_tool() -> None:
    fp1 = compute_action_fingerprint("s", "t", "file.write", "mutating", {"path": "a.txt"})
    fp2 = compute_action_fingerprint("s", "t", "command.run", "mutating", {"path": "a.txt"})
    assert fp1 != fp2


def test_fingerprint_is_hex_string() -> None:
    fp = compute_action_fingerprint("s", "t", "file.write", "mutating", {})
    assert len(fp) == 64
    assert all(c in "0123456789abcdef" for c in fp)


# ---------------------------------------------------------------------------
# request_approval
# ---------------------------------------------------------------------------


def test_request_approval_sets_pending_status(svc: ApprovalService) -> None:
    approval = svc.request_approval("sess-1", "task-1", "file.write", "mutating", {"path": "x"})
    assert approval.status == ApprovalStatus.pending


def test_request_approval_sets_ttl_to_900_seconds(repo: AgentRepository) -> None:
    fixed = datetime(2099, 6, 1, 10, 0, 0, tzinfo=timezone.utc)
    svc = ApprovalService(repo, ttl_seconds=900, clock=lambda: fixed)
    approval = svc.request_approval("sess-1", "task-1", "file.write", "mutating", {"path": "x"})
    assert approval.expires_at == fixed + timedelta(seconds=900)


def test_request_approval_custom_ttl(repo: AgentRepository) -> None:
    fixed = datetime(2099, 6, 1, 10, 0, 0, tzinfo=timezone.utc)
    svc = ApprovalService(repo, ttl_seconds=300, clock=lambda: fixed)
    approval = svc.request_approval("sess-1", "task-1", "file.write", "mutating", {"path": "x"})
    assert approval.expires_at == fixed + timedelta(seconds=300)


def test_request_approval_stores_fingerprint(svc: ApprovalService) -> None:
    payload = {"path": "a.txt", "overwrite": False}
    expected_fp = compute_action_fingerprint("sess-1", "task-1", "file.write", "mutating", payload)
    approval = svc.request_approval("sess-1", "task-1", "file.write", "mutating", payload)
    assert approval.action_fingerprint == expected_fp


def test_request_approval_appends_event(repo: AgentRepository, svc: ApprovalService) -> None:
    svc.request_approval("sess-1", "task-1", "file.write", "mutating", {"path": "x"})
    events = repo.list_events(task_id="task-1")
    event_types = [e.event_type for e in events]
    assert "approval_requested" in event_types


# ---------------------------------------------------------------------------
# decide
# ---------------------------------------------------------------------------


def test_decide_approve_transitions_to_approved(repo: AgentRepository, svc: ApprovalService) -> None:
    approval = svc.request_approval("sess-1", "task-1", "file.write", "mutating", {})
    result = svc.decide(approval.approval_id, ApprovalDecision(decision="approved"))
    assert result.status == ApprovalStatus.approved


def test_decide_reject_transitions_to_rejected(repo: AgentRepository, svc: ApprovalService) -> None:
    approval = svc.request_approval("sess-1", "task-1", "file.write", "mutating", {})
    result = svc.decide(approval.approval_id, ApprovalDecision(decision="rejected"))
    assert result.status == ApprovalStatus.rejected


def test_decide_approve_appends_event(repo: AgentRepository, svc: ApprovalService) -> None:
    approval = svc.request_approval("sess-1", "task-1", "file.write", "mutating", {})
    svc.decide(approval.approval_id, ApprovalDecision(decision="approved"))
    events = repo.list_events(task_id="task-1")
    types = [e.event_type for e in events]
    assert "approval_decided" in types


def test_decide_idempotent_approve(repo: AgentRepository, svc: ApprovalService) -> None:
    approval = svc.request_approval("sess-1", "task-1", "file.write", "mutating", {})
    r1 = svc.decide(approval.approval_id, ApprovalDecision(decision="approved"))
    r2 = svc.decide(approval.approval_id, ApprovalDecision(decision="approved"))
    assert r1.status == r2.status == ApprovalStatus.approved


def test_decide_idempotent_reject(repo: AgentRepository, svc: ApprovalService) -> None:
    approval = svc.request_approval("sess-1", "task-1", "file.write", "mutating", {})
    r1 = svc.decide(approval.approval_id, ApprovalDecision(decision="rejected"))
    r2 = svc.decide(approval.approval_id, ApprovalDecision(decision="rejected"))
    assert r1.status == r2.status == ApprovalStatus.rejected


def test_decide_not_found_raises() -> None:
    svc = ApprovalService(AgentRepository())
    with pytest.raises(ApprovalError) as exc_info:
        svc.decide("nonexistent-id", ApprovalDecision(decision="approved"))
    assert exc_info.value.reason == "not_found"


def test_decide_already_approved_then_rejected_raises(
    repo: AgentRepository, svc: ApprovalService
) -> None:
    approval = svc.request_approval("sess-1", "task-1", "file.write", "mutating", {})
    svc.decide(approval.approval_id, ApprovalDecision(decision="approved"))
    with pytest.raises(ApprovalError) as exc_info:
        svc.decide(approval.approval_id, ApprovalDecision(decision="rejected"))
    assert exc_info.value.reason == ApprovalStatus.approved


# ---------------------------------------------------------------------------
# expire_due_approvals
# ---------------------------------------------------------------------------


def test_expire_due_approvals_marks_expired(repo: AgentRepository) -> None:
    # Two approvals that expire soon (TTL ends at 2026-01-01T00:15:00)
    early = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    # One approval that expires far in the future
    far_future = datetime(2200, 1, 1, tzinfo=timezone.utc)
    svc_early = ApprovalService(repo, ttl_seconds=900, clock=lambda: early)
    svc_far = ApprovalService(repo, ttl_seconds=900, clock=lambda: far_future)

    a1 = svc_early.request_approval("sess-1", "task-1", "file.write", "mutating", {"p": "1"})
    a2 = svc_early.request_approval("sess-1", "task-1", "file.write", "mutating", {"p": "2"})
    a3 = svc_far.request_approval("sess-1", "task-1", "file.write", "mutating", {"p": "3"})

    # Sweep at a point after a1/a2 expired (2026-01-01T00:15) but before a3 (2200)
    sweep_at = datetime(2027, 1, 1, tzinfo=timezone.utc)
    svc_sweep = ApprovalService(repo, clock=lambda: sweep_at)
    count = svc_sweep.expire_due_approvals()
    assert count == 2

    assert repo.get_approval(a1.approval_id).status == ApprovalStatus.expired
    assert repo.get_approval(a2.approval_id).status == ApprovalStatus.expired
    assert repo.get_approval(a3.approval_id).status == ApprovalStatus.pending


def test_expire_due_no_expired_returns_zero(repo: AgentRepository, svc: ApprovalService) -> None:
    svc.request_approval("sess-1", "task-1", "file.write", "mutating", {})
    # Sweep at the same time (no expired yet)
    count = svc.expire_due_approvals()
    assert count == 0


# ---------------------------------------------------------------------------
# consume_approval
# ---------------------------------------------------------------------------


def _request_and_approve(svc: ApprovalService, payload: dict) -> tuple[str, str]:
    """Helper: request approval, approve it, return (approval_id, fingerprint)."""
    approval = svc.request_approval("sess-1", "task-1", "file.write", "mutating", payload)
    svc.decide(approval.approval_id, ApprovalDecision(decision="approved"))
    fp = compute_action_fingerprint("sess-1", "task-1", "file.write", "mutating", payload)
    return approval.approval_id, fp


def test_consume_approval_transitions_to_consumed(
    repo: AgentRepository, svc: ApprovalService
) -> None:
    approval_id, fp = _request_and_approve(svc, {"path": "out.txt"})
    result = svc.consume_approval(approval_id, "sess-1", "task-1", "file.write", fp)
    assert result.status == ApprovalStatus.consumed


def test_consume_approval_exactly_once(repo: AgentRepository, svc: ApprovalService) -> None:
    approval_id, fp = _request_and_approve(svc, {"path": "out.txt"})
    svc.consume_approval(approval_id, "sess-1", "task-1", "file.write", fp)
    with pytest.raises(ApprovalError) as exc_info:
        svc.consume_approval(approval_id, "sess-1", "task-1", "file.write", fp)
    assert exc_info.value.reason == "consumed"


def test_consume_approval_appends_event(repo: AgentRepository, svc: ApprovalService) -> None:
    approval_id, fp = _request_and_approve(svc, {"path": "out.txt"})
    svc.consume_approval(approval_id, "sess-1", "task-1", "file.write", fp)
    events = repo.list_events(task_id="task-1")
    types = [e.event_type for e in events]
    assert "approval_consumed" in types


def test_consume_session_mismatch_raises(repo: AgentRepository, svc: ApprovalService) -> None:
    approval_id, fp = _request_and_approve(svc, {})
    with pytest.raises(ApprovalError) as exc_info:
        svc.consume_approval(approval_id, "wrong-sess", "task-1", "file.write", fp)
    assert exc_info.value.reason == "fingerprint_mismatch"


def test_consume_task_mismatch_raises(repo: AgentRepository, svc: ApprovalService) -> None:
    approval_id, fp = _request_and_approve(svc, {})
    with pytest.raises(ApprovalError) as exc_info:
        svc.consume_approval(approval_id, "sess-1", "wrong-task", "file.write", fp)
    assert exc_info.value.reason == "fingerprint_mismatch"


def test_consume_tool_name_mismatch_raises(repo: AgentRepository, svc: ApprovalService) -> None:
    approval_id, fp = _request_and_approve(svc, {})
    with pytest.raises(ApprovalError) as exc_info:
        svc.consume_approval(approval_id, "sess-1", "task-1", "command.run", fp)
    assert exc_info.value.reason == "fingerprint_mismatch"


def test_consume_fingerprint_mismatch_raises(repo: AgentRepository, svc: ApprovalService) -> None:
    approval_id, _ = _request_and_approve(svc, {"path": "a.txt"})
    wrong_fp = compute_action_fingerprint("sess-1", "task-1", "file.write", "mutating", {"path": "b.txt"})
    with pytest.raises(ApprovalError) as exc_info:
        svc.consume_approval(approval_id, "sess-1", "task-1", "file.write", wrong_fp)
    assert exc_info.value.reason == "fingerprint_mismatch"


def test_consume_rejected_approval_raises(repo: AgentRepository, svc: ApprovalService) -> None:
    approval = svc.request_approval("sess-1", "task-1", "file.write", "mutating", {})
    svc.decide(approval.approval_id, ApprovalDecision(decision="rejected"))
    fp = compute_action_fingerprint("sess-1", "task-1", "file.write", "mutating", {})
    with pytest.raises(ApprovalError) as exc_info:
        svc.consume_approval(approval.approval_id, "sess-1", "task-1", "file.write", fp)
    assert exc_info.value.reason == "rejected"


def test_consume_pending_approval_raises(repo: AgentRepository, svc: ApprovalService) -> None:
    approval = svc.request_approval("sess-1", "task-1", "file.write", "mutating", {})
    fp = compute_action_fingerprint("sess-1", "task-1", "file.write", "mutating", {})
    with pytest.raises(ApprovalError) as exc_info:
        svc.consume_approval(approval.approval_id, "sess-1", "task-1", "file.write", fp)
    assert exc_info.value.reason == "pending"


def test_consume_expired_approval_raises(repo: AgentRepository) -> None:
    # Create an approval that expires in 2026
    early = datetime(2026, 1, 1, tzinfo=timezone.utc)
    svc = ApprovalService(repo, ttl_seconds=900, clock=lambda: early)
    approval = svc.request_approval("sess-1", "task-1", "file.write", "mutating", {})
    svc.decide(approval.approval_id, ApprovalDecision(decision="approved"))

    # Force expiry via a sweep from far in the future
    future_svc = ApprovalService(repo, clock=lambda: datetime(2200, 1, 1, tzinfo=timezone.utc))
    future_svc.expire_due_approvals()

    assert repo.get_approval(approval.approval_id).status == ApprovalStatus.expired

    fp = compute_action_fingerprint("sess-1", "task-1", "file.write", "mutating", {})
    with pytest.raises(ApprovalError) as exc_info:
        svc.consume_approval(approval.approval_id, "sess-1", "task-1", "file.write", fp)
    assert exc_info.value.reason == "expired"


def test_consume_not_found_raises(repo: AgentRepository, svc: ApprovalService) -> None:
    with pytest.raises(ApprovalError) as exc_info:
        svc.consume_approval("no-such-id", "sess-1", "task-1", "file.write", "fp")
    assert exc_info.value.reason == "not_found"


# ---------------------------------------------------------------------------
# Full integration test (AC-6)
# ---------------------------------------------------------------------------


def test_full_lifecycle_integration() -> None:
    """Request → approve → consume produces all three audit events and correct final state."""
    repo = AgentRepository()
    repo.create_session("sess-A")
    repo.create_task("task-A", "sess-A", "write a file")

    svc = ApprovalService(repo)
    payload = {"path": "output.txt", "overwrite": False}

    # Request
    approval = svc.request_approval(
        session_id="sess-A",
        task_id="task-A",
        tool_name="file.write",
        risk="mutating",
        input_payload=payload,
        action_payload={"description": "write results"},
    )
    assert approval.status == ApprovalStatus.pending

    # Approve
    approved = svc.decide(approval.approval_id, ApprovalDecision(decision="approved"))
    assert approved.status == ApprovalStatus.approved

    # Consume
    fp = compute_action_fingerprint("sess-A", "task-A", "file.write", "mutating", payload)
    consumed = svc.consume_approval(
        approval.approval_id, "sess-A", "task-A", "file.write", fp
    )
    assert consumed.status == ApprovalStatus.consumed

    # Audit trail
    events = repo.list_events(task_id="task-A")
    event_types = [e.event_type for e in events]
    assert "approval_requested" in event_types
    assert "approval_decided" in event_types
    assert "approval_consumed" in event_types

    # Second consume must fail
    with pytest.raises(ApprovalError) as exc_info:
        svc.consume_approval(approval.approval_id, "sess-A", "task-A", "file.write", fp)
    assert exc_info.value.reason == "consumed"


# ---------------------------------------------------------------------------
# app.state wiring test
# ---------------------------------------------------------------------------


def test_create_app_exposes_approval_service() -> None:
    from app.main import create_app
    app = create_app()
    assert hasattr(app.state, "approval_service")
    assert isinstance(app.state.approval_service, ApprovalService)
