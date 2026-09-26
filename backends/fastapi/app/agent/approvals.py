"""Exact-once approval service for governed agent actions.

Provides:
  ApprovalStatus          — str enum for the five approval states
  ApprovalRequest         — re-exported from repository (same dataclass)
  ApprovalDecision        — dataclass wrapping a decision + optional rationale
  ApprovalError           — structured exception with reason codes
  compute_action_fingerprint — canonical SHA-256 fingerprint for an action
  ApprovalService         — service coordinating requests, decisions, expiry,
                            and exact-once consumption

Design
------
- Fingerprints use json.dumps(sort_keys=True) so identical payloads with
  different key order produce the same hash.
- ApprovalService is independent from FastAPI; it can be called from routers,
  worker.py, and AgentLoop with no app.Request dependency.
- All timestamp arithmetic uses timezone-aware UTC datetimes; an injectable
  ``clock`` callable makes TTL assertions deterministic in tests.
- Audit events (approval_requested, approval_decided, approval_consumed) are
  appended to the event store inside every state-changing operation.
"""

from __future__ import annotations

import enum
import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable

from app.agent.repository import (
    AgentRepository,
    ApprovalRequest,
    InvalidApprovalTransitionError,
    NotFoundError,
)

# Re-export so callers can import from one place
__all__ = [
    "ApprovalStatus",
    "ApprovalRequest",
    "ApprovalDecision",
    "ApprovalError",
    "ApprovalService",
    "compute_action_fingerprint",
]


# ---------------------------------------------------------------------------
# Status enum
# ---------------------------------------------------------------------------


class ApprovalStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"
    expired = "expired"
    consumed = "consumed"


# ---------------------------------------------------------------------------
# Decision model
# ---------------------------------------------------------------------------


@dataclass
class ApprovalDecision:
    """Wraps a developer's decision on a pending approval."""

    decision: str  # "approved" or "rejected"
    rationale: str | None = None


# ---------------------------------------------------------------------------
# Service exception
# ---------------------------------------------------------------------------


class ApprovalError(Exception):
    """Raised for all approval service-level failures.

    Attributes
    ----------
    reason:
        Machine-readable code: not_found | fingerprint_mismatch | expired |
        rejected | pending | consumed | invalid_transition.
    message:
        Human-readable description.
    approval_id:
        The affected approval identifier, when known.
    """

    def __init__(
        self,
        reason: str,
        message: str,
        *,
        approval_id: str | None = None,
    ) -> None:
        self.reason = reason
        self.message = message
        self.approval_id = approval_id
        super().__init__(message)

    def __repr__(self) -> str:
        return f"ApprovalError(reason={self.reason!r}, approval_id={self.approval_id!r})"


# ---------------------------------------------------------------------------
# Fingerprinting
# ---------------------------------------------------------------------------


def compute_action_fingerprint(
    session_id: str,
    task_id: str,
    tool_name: str,
    risk: str,
    input_payload: dict,
) -> str:
    """Return a canonical SHA-256 hex digest for an action.

    Key order in *input_payload* is normalized by ``sort_keys=True`` so
    semantically identical payloads always produce the same fingerprint.
    """
    material = json.dumps(
        {
            "session_id": session_id,
            "task_id": task_id,
            "tool_name": tool_name,
            "risk": risk,
            "input": input_payload,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _map_repo_error(exc: Exception, approval_id: str) -> ApprovalError:
    """Convert a repository transition error to an ApprovalError with a reason code."""
    msg = str(exc).lower()
    if "consumed" in msg:
        return ApprovalError("consumed", str(exc), approval_id=approval_id)
    if "expired" in msg:
        return ApprovalError("expired", str(exc), approval_id=approval_id)
    if "rejected" in msg:
        return ApprovalError("rejected", str(exc), approval_id=approval_id)
    if "fingerprint" in msg:
        return ApprovalError("fingerprint_mismatch", str(exc), approval_id=approval_id)
    if "pending" in msg:
        return ApprovalError("pending", str(exc), approval_id=approval_id)
    return ApprovalError("invalid_transition", str(exc), approval_id=approval_id)


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class ApprovalService:
    """Coordinate approval lifecycle with exact-once consume semantics.

    Parameters
    ----------
    repo:
        The durable ``AgentRepository`` used for persistence and event logging.
    ttl_seconds:
        Approval TTL in seconds.  Default is 900 (15 minutes).
    clock:
        Callable returning the current UTC datetime.  Defaults to
        ``datetime.now(timezone.utc)``.  Inject a fake clock in tests for
        deterministic TTL assertions.
    """

    def __init__(
        self,
        repo: AgentRepository,
        ttl_seconds: int = 900,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._repo = repo
        self._ttl_seconds = ttl_seconds
        self._clock = clock or _now_utc

    # ------------------------------------------------------------------
    # request_approval
    # ------------------------------------------------------------------

    def request_approval(
        self,
        session_id: str,
        task_id: str,
        tool_name: str,
        risk: str,
        input_payload: dict,
        action_payload: dict | None = None,
    ) -> ApprovalRequest:
        """Create a pending approval request and append an audit event.

        Parameters
        ----------
        session_id / task_id:
            Binding identifiers that consume_approval will verify.
        tool_name:
            The tool requesting authorization (e.g. ``"file.write"``).
        risk:
            ToolRisk value string (e.g. ``"mutating"``).
        input_payload:
            The normalized tool input dict that will be fingerprinted.
        action_payload:
            Optional human-readable payload stored alongside the request.
        """
        fingerprint = compute_action_fingerprint(
            session_id, task_id, tool_name, risk, input_payload
        )
        now = self._clock()
        expires_at = now + timedelta(seconds=self._ttl_seconds)
        approval_id = str(uuid.uuid4())

        approval = self._repo.create_approval_request(
            approval_id=approval_id,
            session_id=session_id,
            task_id=task_id,
            action_type=tool_name,
            action_fingerprint=fingerprint,
            expires_at=expires_at,
            action_payload=action_payload,
        )
        self._repo.append_event(
            event_id=str(uuid.uuid4()),
            session_id=session_id,
            task_id=task_id,
            event_type="approval_requested",
            payload={
                "approval_id": approval_id,
                "tool_name": tool_name,
                "risk": risk,
                "expires_at": expires_at.isoformat(),
            },
        )
        return approval

    # ------------------------------------------------------------------
    # decide
    # ------------------------------------------------------------------

    def decide(
        self,
        approval_id: str,
        decision: ApprovalDecision,
    ) -> ApprovalRequest:
        """Record an approved or rejected decision on a pending approval.

        Idempotent: repeating the same decision returns the current record
        without error.  Raising a different decision on a non-pending approval
        raises ``ApprovalError``.
        """
        existing = self._repo.get_approval(approval_id)
        if existing is None:
            raise ApprovalError(
                "not_found",
                f"Approval {approval_id!r} not found",
                approval_id=approval_id,
            )

        # Idempotent: already decided with the same decision
        if existing.status == decision.decision:
            return existing

        if existing.status != ApprovalStatus.pending:
            raise ApprovalError(
                existing.status,
                f"Cannot decide approval in status {existing.status!r}",
                approval_id=approval_id,
            )

        if decision.decision not in ("approved", "rejected"):
            raise ApprovalError(
                "invalid_transition",
                f"Invalid decision {decision.decision!r}; must be 'approved' or 'rejected'",
                approval_id=approval_id,
            )

        try:
            approval = self._repo.decide_approval(approval_id, decision.decision)
        except (NotFoundError, InvalidApprovalTransitionError) as exc:
            raise ApprovalError(
                "invalid_transition", str(exc), approval_id=approval_id
            ) from exc

        self._repo.append_event(
            event_id=str(uuid.uuid4()),
            session_id=approval.session_id,
            task_id=approval.task_id,
            event_type="approval_decided",
            payload={
                "approval_id": approval_id,
                "decision": decision.decision,
                "rationale": decision.rationale,
            },
        )
        return approval

    # ------------------------------------------------------------------
    # expire_due_approvals
    # ------------------------------------------------------------------

    def expire_due_approvals(self) -> int:
        """Expire all pending approvals whose TTL has elapsed.

        Returns the number of approvals transitioned to ``expired``.
        This is a demand-driven sweep; no background task is required.
        """
        now = self._clock()
        return self._repo.expire_pending_before(now)

    # ------------------------------------------------------------------
    # consume_approval
    # ------------------------------------------------------------------

    def consume_approval(
        self,
        approval_id: str,
        session_id: str,
        task_id: str,
        tool_name: str,
        action_fingerprint: str,
    ) -> ApprovalRequest:
        """Atomically consume an approved approval exactly once.

        Verifies session_id, task_id, and tool_name before delegating to
        the repository's atomic consume transition.  Appends an audit event
        on success.

        Raises ``ApprovalError`` with an appropriate reason code on any
        mismatch, wrong status, or duplicate consume attempt.
        """
        existing = self._repo.get_approval(approval_id)
        if existing is None:
            raise ApprovalError(
                "not_found",
                f"Approval {approval_id!r} not found",
                approval_id=approval_id,
            )

        # Verify binding fields before attempting the atomic transition
        mismatches: list[str] = []
        if existing.session_id != session_id:
            mismatches.append("session_id")
        if existing.task_id != task_id:
            mismatches.append("task_id")
        if existing.action_type != tool_name:
            mismatches.append("tool_name")
        if mismatches:
            raise ApprovalError(
                "fingerprint_mismatch",
                f"Approval binding mismatch: {', '.join(mismatches)}",
                approval_id=approval_id,
            )

        # Fast-path status checks before the serialized DB transaction
        status = existing.status
        if status == ApprovalStatus.consumed:
            raise ApprovalError(
                "consumed",
                f"Approval {approval_id!r} has already been consumed",
                approval_id=approval_id,
            )
        if status == ApprovalStatus.rejected:
            raise ApprovalError(
                "rejected",
                f"Approval {approval_id!r} was rejected",
                approval_id=approval_id,
            )
        if status == ApprovalStatus.expired:
            raise ApprovalError(
                "expired",
                f"Approval {approval_id!r} has expired",
                approval_id=approval_id,
            )
        if status == ApprovalStatus.pending:
            raise ApprovalError(
                "pending",
                f"Approval {approval_id!r} is still pending (not yet approved)",
                approval_id=approval_id,
            )

        # Atomic consume via repository
        try:
            consumed = self._repo.consume_approval_once(approval_id, action_fingerprint)
        except NotFoundError as exc:
            raise ApprovalError(
                "not_found", str(exc), approval_id=approval_id
            ) from exc
        except InvalidApprovalTransitionError as exc:
            raise _map_repo_error(exc, approval_id) from exc

        self._repo.append_event(
            event_id=str(uuid.uuid4()),
            session_id=consumed.session_id,
            task_id=consumed.task_id,
            event_type="approval_consumed",
            payload={
                "approval_id": approval_id,
                "tool_name": tool_name,
            },
        )
        return consumed
