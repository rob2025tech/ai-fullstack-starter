"""Durable local repository for agent sessions, tasks, events, and approvals.

Uses Python standard-library ``sqlite3`` for backend-local persistence so
coding-agent state survives restarts without introducing an ORM, Redis, or
an external database service.

Design decisions
----------------
- All entities are plain ``dataclass`` objects — independent from FastAPI
  request/response models so transport DTOs can be mapped separately.
- ``metadata``, ``payload``, and ``action_payload`` columns store JSON text;
  helper functions raise ``CorruptedDataError`` on deserialization failure so
  higher layers can map the failure to an ``internal_error`` envelope.
- ``agent_events`` enforces a UNIQUE(task_id, sequence) constraint for
  monotonic per-task ordering.
- ``consume_approval_once`` runs inside a serialized ``BEGIN IMMEDIATE``
  transaction to prevent double-consumption under concurrent access.
- Timestamps are stored as UTC ISO 8601 strings and returned as
  timezone-aware ``datetime`` objects.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Generator


# ---------------------------------------------------------------------------
# Repository-level exceptions
# ---------------------------------------------------------------------------


class RepositoryError(Exception):
    """Base class for repository errors; maps to ``internal_error`` envelope."""


class NotFoundError(RepositoryError):
    """Raised when a requested record does not exist."""


class DuplicateSequenceError(RepositoryError):
    """Raised when appending an event with a (task_id, sequence) that already exists."""


class InvalidApprovalTransitionError(RepositoryError):
    """Raised when an approval cannot be moved to the requested state."""


class CorruptedDataError(RepositoryError):
    """Raised when stored JSON data cannot be deserialized."""


# ---------------------------------------------------------------------------
# Entity dataclasses
# ---------------------------------------------------------------------------


@dataclass
class AgentSession:
    session_id: str
    status: str
    created_at: datetime
    updated_at: datetime
    title: str | None = None
    metadata: dict | None = None


@dataclass
class AgentTask:
    task_id: str
    session_id: str
    status: str
    prompt: str
    created_at: datetime
    updated_at: datetime
    result: str | None = None


@dataclass
class AgentEvent:
    event_id: str
    session_id: str
    task_id: str
    sequence: int
    event_type: str
    created_at: datetime
    payload: dict | None = None


@dataclass
class ApprovalRequest:
    approval_id: str
    session_id: str
    task_id: str
    action_type: str
    action_fingerprint: str
    status: str
    expires_at: datetime
    created_at: datetime
    updated_at: datetime
    action_payload: dict | None = None
    consumed_at: datetime | None = None


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _to_iso(dt: datetime) -> str:
    return dt.isoformat()


def _from_iso(s: str) -> datetime:
    """Parse an ISO 8601 string to a timezone-aware UTC datetime."""
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _encode_json(obj: dict | None) -> str | None:
    if obj is None:
        return None
    return json.dumps(obj)


def _decode_json(s: str | None, field_name: str) -> dict | None:
    if s is None:
        return None
    try:
        result = json.loads(s)
    except json.JSONDecodeError as exc:
        raise CorruptedDataError(f"Invalid JSON in {field_name}: {exc}") from exc
    if not isinstance(result, dict):
        raise CorruptedDataError(
            f"Expected a JSON object for {field_name}, got {type(result).__name__}"
        )
    return result


# ---------------------------------------------------------------------------
# Schema DDL
# ---------------------------------------------------------------------------

_DDL = """
CREATE TABLE IF NOT EXISTS agent_sessions (
    session_id   TEXT PRIMARY KEY,
    status       TEXT NOT NULL,
    title        TEXT,
    metadata     TEXT,
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS agent_tasks (
    task_id      TEXT PRIMARY KEY,
    session_id   TEXT NOT NULL,
    status       TEXT NOT NULL,
    prompt       TEXT NOT NULL,
    result       TEXT,
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_agent_tasks_session_id
    ON agent_tasks(session_id);

CREATE TABLE IF NOT EXISTS agent_events (
    event_id     TEXT PRIMARY KEY,
    session_id   TEXT NOT NULL,
    task_id      TEXT NOT NULL,
    sequence     INTEGER NOT NULL,
    event_type   TEXT NOT NULL,
    payload      TEXT,
    created_at   TEXT NOT NULL,
    UNIQUE(task_id, sequence)
);

CREATE INDEX IF NOT EXISTS idx_agent_events_session_id
    ON agent_events(session_id);
CREATE INDEX IF NOT EXISTS idx_agent_events_task_id
    ON agent_events(task_id);

CREATE TABLE IF NOT EXISTS approval_requests (
    approval_id        TEXT PRIMARY KEY,
    session_id         TEXT NOT NULL,
    task_id            TEXT NOT NULL,
    action_type        TEXT NOT NULL,
    action_payload     TEXT,
    action_fingerprint TEXT NOT NULL,
    status             TEXT NOT NULL,
    expires_at         TEXT NOT NULL,
    consumed_at        TEXT,
    created_at         TEXT NOT NULL,
    updated_at         TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_approval_requests_session_id
    ON approval_requests(session_id);
CREATE INDEX IF NOT EXISTS idx_approval_requests_task_id
    ON approval_requests(task_id);
CREATE INDEX IF NOT EXISTS idx_approval_requests_status
    ON approval_requests(status);
"""


# ---------------------------------------------------------------------------
# Repository
# ---------------------------------------------------------------------------


class AgentRepository:
    """SQLite-backed repository for all agent domain entities.

    Parameters
    ----------
    db_path:
        Filesystem path for the SQLite database file, or ``":memory:"`` for an
        in-process ephemeral store (useful in tests).
    """

    def __init__(self, db_path: str | Path = ":memory:") -> None:
        self._db_path = str(db_path)
        self._conn: sqlite3.Connection | None = None
        self._open()

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    def _open(self) -> None:
        self._conn = sqlite3.connect(
            self._db_path,
            check_same_thread=False,
            isolation_level=None,  # autocommit; transactions are managed explicitly
        )
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL;")
        self._conn.execute("PRAGMA foreign_keys=ON;")
        self._conn.executescript(_DDL)

    def close(self) -> None:
        """Close the database connection."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    @property
    def _db(self) -> sqlite3.Connection:
        if self._conn is None:
            raise RepositoryError("Repository is closed; call _open() or create a new instance.")
        return self._conn

    @contextmanager
    def _transaction(self) -> Generator[sqlite3.Connection, None, None]:
        """Context manager for an explicit serialized transaction."""
        self._db.execute("BEGIN IMMEDIATE")
        try:
            yield self._db
            self._db.execute("COMMIT")
        except BaseException:
            self._db.execute("ROLLBACK")
            raise

    # ------------------------------------------------------------------
    # Session operations
    # ------------------------------------------------------------------

    def create_session(
        self,
        session_id: str,
        status: str = "active",
        title: str | None = None,
        metadata: dict | None = None,
    ) -> AgentSession:
        """Persist a new agent session and return it."""
        now = _now_utc()
        self._db.execute(
            """
            INSERT INTO agent_sessions
                (session_id, status, title, metadata, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                session_id,
                status,
                title,
                _encode_json(metadata),
                _to_iso(now),
                _to_iso(now),
            ),
        )
        return AgentSession(
            session_id=session_id,
            status=status,
            title=title,
            metadata=metadata,
            created_at=now,
            updated_at=now,
        )

    def get_session(self, session_id: str) -> AgentSession | None:
        """Return the session or ``None`` if not found."""
        row = self._db.execute(
            "SELECT * FROM agent_sessions WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        if row is None:
            return None
        return AgentSession(
            session_id=row["session_id"],
            status=row["status"],
            title=row["title"],
            metadata=_decode_json(row["metadata"], "session.metadata"),
            created_at=_from_iso(row["created_at"]),
            updated_at=_from_iso(row["updated_at"]),
        )

    # ------------------------------------------------------------------
    # Task operations
    # ------------------------------------------------------------------

    def create_task(
        self,
        task_id: str,
        session_id: str,
        prompt: str,
        status: str = "pending",
    ) -> AgentTask:
        """Persist a new agent task and return it."""
        now = _now_utc()
        self._db.execute(
            """
            INSERT INTO agent_tasks
                (task_id, session_id, status, prompt, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (task_id, session_id, status, prompt, _to_iso(now), _to_iso(now)),
        )
        return AgentTask(
            task_id=task_id,
            session_id=session_id,
            status=status,
            prompt=prompt,
            created_at=now,
            updated_at=now,
        )

    def get_task(self, task_id: str) -> AgentTask | None:
        """Return the task or ``None`` if not found."""
        row = self._db.execute(
            "SELECT * FROM agent_tasks WHERE task_id = ?",
            (task_id,),
        ).fetchone()
        if row is None:
            return None
        return AgentTask(
            task_id=row["task_id"],
            session_id=row["session_id"],
            status=row["status"],
            prompt=row["prompt"],
            result=row["result"],
            created_at=_from_iso(row["created_at"]),
            updated_at=_from_iso(row["updated_at"]),
        )

    def list_tasks(self, session_id: str) -> list[AgentTask]:
        """Return all tasks for a session ordered by creation time."""
        rows = self._db.execute(
            "SELECT * FROM agent_tasks WHERE session_id = ? ORDER BY created_at ASC",
            (session_id,),
        ).fetchall()
        return [
            AgentTask(
                task_id=r["task_id"],
                session_id=r["session_id"],
                status=r["status"],
                prompt=r["prompt"],
                result=r["result"],
                created_at=_from_iso(r["created_at"]),
                updated_at=_from_iso(r["updated_at"]),
            )
            for r in rows
        ]

    def update_task_status(
        self,
        task_id: str,
        status: str,
        result: str | None = None,
    ) -> AgentTask:
        """Update a task's status (and optional result) and return the updated entity.

        Raises ``NotFoundError`` if the task does not exist.
        """
        now = _now_utc()
        cursor = self._db.execute(
            """
            UPDATE agent_tasks
            SET status = ?, result = ?, updated_at = ?
            WHERE task_id = ?
            """,
            (status, result, _to_iso(now), task_id),
        )
        if cursor.rowcount == 0:
            raise NotFoundError(f"Task not found: {task_id!r}")
        task = self.get_task(task_id)
        assert task is not None  # nosec — we just updated it
        return task

    # ------------------------------------------------------------------
    # Event operations
    # ------------------------------------------------------------------

    def append_event(
        self,
        event_id: str,
        session_id: str,
        task_id: str,
        event_type: str,
        payload: dict | None = None,
    ) -> AgentEvent:
        """Append an event to a task, assigning the next monotonic sequence number.

        The sequence starts at 1 for the first event in a task and increments
        by 1 for each subsequent event.  The UNIQUE(task_id, sequence) constraint
        in the schema prevents duplicates; a violation raises ``DuplicateSequenceError``.
        """
        now = _now_utc()
        try:
            with self._transaction():
                row = self._db.execute(
                    "SELECT COALESCE(MAX(sequence), 0) FROM agent_events WHERE task_id = ?",
                    (task_id,),
                ).fetchone()
                next_seq: int = row[0] + 1
                self._db.execute(
                    """
                    INSERT INTO agent_events
                        (event_id, session_id, task_id, sequence, event_type, payload, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        event_id,
                        session_id,
                        task_id,
                        next_seq,
                        event_type,
                        _encode_json(payload),
                        _to_iso(now),
                    ),
                )
        except sqlite3.IntegrityError as exc:
            raise DuplicateSequenceError(
                f"Duplicate sequence for task {task_id!r}: {exc}"
            ) from exc
        return AgentEvent(
            event_id=event_id,
            session_id=session_id,
            task_id=task_id,
            sequence=next_seq,
            event_type=event_type,
            payload=payload,
            created_at=now,
        )

    def list_events(
        self,
        *,
        session_id: str | None = None,
        task_id: str | None = None,
        after_sequence: int = 0,
    ) -> list[AgentEvent]:
        """Return ordered events filtered by ``task_id`` or ``session_id``.

        Exactly one of ``task_id`` or ``session_id`` must be provided.
        ``after_sequence`` restricts results to events whose sequence is strictly
        greater than the given value (useful for resuming a stream).
        """
        if task_id is not None:
            rows = self._db.execute(
                """
                SELECT * FROM agent_events
                WHERE task_id = ? AND sequence > ?
                ORDER BY sequence ASC
                """,
                (task_id, after_sequence),
            ).fetchall()
        elif session_id is not None:
            rows = self._db.execute(
                """
                SELECT * FROM agent_events
                WHERE session_id = ? AND sequence > ?
                ORDER BY task_id ASC, sequence ASC
                """,
                (session_id, after_sequence),
            ).fetchall()
        else:
            raise RepositoryError("list_events requires at least one of: task_id, session_id")

        return [
            AgentEvent(
                event_id=row["event_id"],
                session_id=row["session_id"],
                task_id=row["task_id"],
                sequence=row["sequence"],
                event_type=row["event_type"],
                payload=_decode_json(row["payload"], "event.payload"),
                created_at=_from_iso(row["created_at"]),
            )
            for row in rows
        ]

    # ------------------------------------------------------------------
    # Approval operations
    # ------------------------------------------------------------------

    def create_approval_request(
        self,
        approval_id: str,
        session_id: str,
        task_id: str,
        action_type: str,
        action_fingerprint: str,
        expires_at: datetime,
        action_payload: dict | None = None,
    ) -> ApprovalRequest:
        """Create a pending approval request and return it."""
        now = _now_utc()
        self._db.execute(
            """
            INSERT INTO approval_requests
                (approval_id, session_id, task_id, action_type, action_payload,
                 action_fingerprint, status, expires_at, consumed_at, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                approval_id,
                session_id,
                task_id,
                action_type,
                _encode_json(action_payload),
                action_fingerprint,
                "pending",
                _to_iso(expires_at),
                None,
                _to_iso(now),
                _to_iso(now),
            ),
        )
        return ApprovalRequest(
            approval_id=approval_id,
            session_id=session_id,
            task_id=task_id,
            action_type=action_type,
            action_payload=action_payload,
            action_fingerprint=action_fingerprint,
            status="pending",
            expires_at=expires_at,
            consumed_at=None,
            created_at=now,
            updated_at=now,
        )

    def list_pending_approvals(self, session_id: str) -> list[ApprovalRequest]:
        """Return all pending approval requests for a session, ordered by creation time."""
        rows = self._db.execute(
            """
            SELECT * FROM approval_requests
            WHERE session_id = ? AND status = 'pending'
            ORDER BY created_at ASC
            """,
            (session_id,),
        ).fetchall()
        return [self._row_to_approval(row) for row in rows]

    def decide_approval(
        self,
        approval_id: str,
        decision: str,
    ) -> ApprovalRequest:
        """Record a developer decision on a pending approval request.

        Parameters
        ----------
        approval_id:
            The approval to update.
        decision:
            Must be ``"approved"`` or ``"rejected"``.

        Raises ``NotFoundError`` if the approval does not exist.
        Raises ``InvalidApprovalTransitionError`` if the decision is invalid or
        the approval is not in ``pending`` status.
        """
        if decision not in ("approved", "rejected"):
            raise InvalidApprovalTransitionError(
                f"Invalid decision {decision!r}. Must be 'approved' or 'rejected'."
            )
        now = _now_utc()
        with self._transaction():
            row = self._db.execute(
                "SELECT * FROM approval_requests WHERE approval_id = ?",
                (approval_id,),
            ).fetchone()
            if row is None:
                raise NotFoundError(f"Approval not found: {approval_id!r}")
            if row["status"] != "pending":
                raise InvalidApprovalTransitionError(
                    f"Cannot decide approval with status {row['status']!r}; must be 'pending'."
                )
            self._db.execute(
                "UPDATE approval_requests SET status = ?, updated_at = ? WHERE approval_id = ?",
                (decision, _to_iso(now), approval_id),
            )
        result = self._get_approval(approval_id)
        assert result is not None  # nosec
        return result

    def consume_approval_once(
        self,
        approval_id: str,
        action_fingerprint: str,
    ) -> ApprovalRequest:
        """Atomically transition an approved approval to ``consumed`` exactly once.

        The approval must be in ``approved`` status, the ``action_fingerprint``
        must match the stored fingerprint, and the approval must not have expired.
        Raises ``InvalidApprovalTransitionError`` for any violation so that the
        caller can emit a structured policy-error event without retrying.

        The state transition is serialized with ``BEGIN IMMEDIATE`` to prevent
        double-consumption under concurrent access.
        """
        now = _now_utc()
        with self._transaction():
            row = self._db.execute(
                "SELECT * FROM approval_requests WHERE approval_id = ?",
                (approval_id,),
            ).fetchone()
            if row is None:
                raise NotFoundError(f"Approval not found: {approval_id!r}")

            current_status = row["status"]
            if current_status == "consumed":
                raise InvalidApprovalTransitionError(
                    f"Approval {approval_id!r} has already been consumed."
                )
            if current_status == "rejected":
                raise InvalidApprovalTransitionError(
                    f"Approval {approval_id!r} was rejected and cannot be consumed."
                )
            if current_status == "expired":
                raise InvalidApprovalTransitionError(
                    f"Approval {approval_id!r} has expired and cannot be consumed."
                )
            if current_status != "approved":
                raise InvalidApprovalTransitionError(
                    f"Cannot consume approval with status {current_status!r}; must be 'approved'."
                )

            stored_fingerprint = row["action_fingerprint"]
            if stored_fingerprint != action_fingerprint:
                raise InvalidApprovalTransitionError(
                    "Action fingerprint mismatch: the proposed action does not match the approved action."
                )

            expires_at = _from_iso(row["expires_at"])
            if now > expires_at:
                # Mark expired atomically inside the same transaction
                self._db.execute(
                    "UPDATE approval_requests SET status = 'expired', updated_at = ? WHERE approval_id = ?",
                    (_to_iso(now), approval_id),
                )
                raise InvalidApprovalTransitionError(
                    f"Approval {approval_id!r} has expired (expired at {expires_at.isoformat()})."
                )

            self._db.execute(
                """
                UPDATE approval_requests
                SET status = 'consumed', consumed_at = ?, updated_at = ?
                WHERE approval_id = ?
                """,
                (_to_iso(now), _to_iso(now), approval_id),
            )

        result = self._get_approval(approval_id)
        assert result is not None  # nosec
        return result

    def get_approval(self, approval_id: str) -> ApprovalRequest | None:
        """Return the approval request or ``None`` if not found."""
        return self._get_approval(approval_id)

    def find_approved_approval(
        self,
        session_id: str,
        task_id: str,
        action_fingerprint: str,
    ) -> "ApprovalRequest | None":
        """Return the oldest approved approval matching session, task, and fingerprint.

        Used by AgentLoop to check whether a mutating/unsafe action has already
        been authorized before attempting to consume it.
        """
        row = self._db.execute(
            """
            SELECT * FROM approval_requests
            WHERE session_id = ? AND task_id = ? AND action_fingerprint = ? AND status = 'approved'
            ORDER BY created_at
            LIMIT 1
            """,
            (session_id, task_id, action_fingerprint),
        ).fetchone()
        if row is None:
            return None
        return self._row_to_approval(row)

    def find_next_runnable_task(self) -> "AgentTask | None":
        """Return the oldest pending task across all sessions, or ``None``.

        Used by LocalAgentWorker to claim the next unit of work.
        """
        row = self._db.execute(
            "SELECT * FROM agent_tasks WHERE status = 'pending' ORDER BY created_at LIMIT 1"
        ).fetchone()
        if row is None:
            return None
        return AgentTask(
            task_id=row["task_id"],
            session_id=row["session_id"],
            status=row["status"],
            prompt=row["prompt"],
            result=row["result"],
            created_at=_from_iso(row["created_at"]),
            updated_at=_from_iso(row["updated_at"]),
        )

    def expire_pending_before(self, cutoff_time: datetime) -> int:
        """Mark all pending or approved approvals whose ``expires_at`` is before *cutoff_time* as expired.

        Both pending and approved records are eligible: an approved record past
        its TTL can no longer authorize a mutating action.

        Returns the number of records updated.
        """
        now = _now_utc()
        cursor = self._db.execute(
            """
            UPDATE approval_requests
            SET status = 'expired', updated_at = ?
            WHERE status IN ('pending', 'approved') AND expires_at < ?
            """,
            (_to_iso(now), _to_iso(cutoff_time)),
        )
        return cursor.rowcount

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _get_approval(self, approval_id: str) -> ApprovalRequest | None:
        row = self._db.execute(
            "SELECT * FROM approval_requests WHERE approval_id = ?",
            (approval_id,),
        ).fetchone()
        if row is None:
            return None
        return self._row_to_approval(row)

    def _row_to_approval(self, row: sqlite3.Row) -> ApprovalRequest:
        return ApprovalRequest(
            approval_id=row["approval_id"],
            session_id=row["session_id"],
            task_id=row["task_id"],
            action_type=row["action_type"],
            action_payload=_decode_json(row["action_payload"], "approval.action_payload"),
            action_fingerprint=row["action_fingerprint"],
            status=row["status"],
            expires_at=_from_iso(row["expires_at"]),
            consumed_at=_from_iso(row["consumed_at"]) if row["consumed_at"] else None,
            created_at=_from_iso(row["created_at"]),
            updated_at=_from_iso(row["updated_at"]),
        )
