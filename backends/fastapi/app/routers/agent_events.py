"""FastAPI router for task-scoped agent event replay and SSE streaming.

Endpoints:
  GET /api/v1/agent/sessions/{session_id}/tasks/{task_id}/events
      JSON replay of all persisted events for a task, sorted by sequence.
      Supports `after_sequence` pagination.

  GET /api/v1/agent/sessions/{session_id}/tasks/{task_id}/events/stream
      SSE stream replaying all persisted events for a task.  Each frame
      uses the event_type as the event name and a JSON-serialised
      AgentEventResponse as the data payload.  The stream closes after
      all current events are emitted.

Design notes
------------
- Both handlers are read-only projections of the persisted AgentEvent store;
  they do not trigger execution, modify state, or buffer events in memory.
- The router reads ``app.state.agent_repository`` via the same helper pattern
  used by the existing agent router.
- SSE failures that occur before streaming begins return a JSON error envelope;
  failures that occur after the first byte would need a terminal SSE error frame
  (not possible in this snapshot-replay design since the event list is loaded
  upfront before the stream begins).
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from app.agent.repository import AgentRepository
from app.core.errors import InvalidRequestError
from app.models.agent_models import (
    AgentEventReplayResponse,
    AgentEventResponse,
)
from app.models.error_models import ErrorResponse

router = APIRouter(prefix="/api/v1/agent", tags=["agent"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_repo(request: Request) -> AgentRepository:
    return request.app.state.agent_repository  # type: ignore[no-any-return]


def _event_response(event) -> AgentEventResponse:
    return AgentEventResponse(
        event_id=event.event_id,
        session_id=event.session_id,
        task_id=event.task_id,
        sequence=event.sequence,
        event_type=event.event_type,  # type: ignore[arg-type]
        payload=event.payload,
        created_at=event.created_at,
    )


# ---------------------------------------------------------------------------
# JSON replay endpoint
# ---------------------------------------------------------------------------


@router.get(
    "/sessions/{session_id}/tasks/{task_id}/events",
    response_model=AgentEventReplayResponse,
    responses={
        401: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def get_task_events(
    session_id: str,
    task_id: str,
    raw_request: Request,
    after_sequence: int = 0,
) -> AgentEventReplayResponse:
    """Return ordered events for a specific task.

    Parameters
    ----------
    session_id:
        The agent session identifier.
    task_id:
        The task identifier within the session.
    after_sequence:
        Return only events with sequence > this value (default 0 = all events).
    """
    repo = _get_repo(raw_request)

    if repo.get_session(session_id) is None:
        raise InvalidRequestError(f"Session not found: {session_id!r}")
    if repo.get_task(task_id) is None:
        raise InvalidRequestError(f"Task not found: {task_id!r}")

    events = repo.list_events(task_id=task_id, after_sequence=after_sequence)
    event_responses = [_event_response(e) for e in events]
    next_after = events[-1].sequence if events else None

    return AgentEventReplayResponse(
        events=event_responses,
        next_after_sequence=next_after,
    )


# ---------------------------------------------------------------------------
# SSE stream endpoint
# ---------------------------------------------------------------------------


@router.get(
    "/sessions/{session_id}/tasks/{task_id}/events/stream",
    responses={
        200: {"content": {"text/event-stream": {"schema": {"type": "string"}}}},
        401: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def stream_task_events(
    session_id: str,
    task_id: str,
    raw_request: Request,
    after_sequence: int = 0,
) -> StreamingResponse:
    """Stream persisted events for a task as Server-Sent Events.

    Each SSE frame has:
    - ``event:`` set to the event_type (e.g. ``assistant_output``, ``completed``)
    - ``data:`` set to the JSON-serialised ``AgentEventResponse``

    The stream closes after all current events have been emitted.
    """
    repo = _get_repo(raw_request)

    if repo.get_session(session_id) is None:
        raise InvalidRequestError(f"Session not found: {session_id!r}")
    if repo.get_task(task_id) is None:
        raise InvalidRequestError(f"Task not found: {task_id!r}")

    # Load the snapshot before starting the stream so validation errors surface
    # as JSON error envelopes rather than mid-stream partial frames.
    events = repo.list_events(task_id=task_id, after_sequence=after_sequence)

    async def _generate():
        for event in events:
            event_resp = _event_response(event)
            data = json.dumps(
                event_resp.model_dump(mode="json"),
                separators=(",", ":"),
            )
            yield f"event: {event.event_type}\ndata: {data}\n\n"

    return StreamingResponse(_generate(), media_type="text/event-stream")
