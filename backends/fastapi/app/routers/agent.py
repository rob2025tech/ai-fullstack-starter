"""FastAPI router for the agent control-plane endpoints under /api/v1/agent.

The router is intentionally not wired into app.main.create_app yet; that
wiring is handled in a separate work order.  Mount this router on a test app
via ``app.include_router(agent.router)`` and set
``app.state.agent_repository`` to an ``AgentRepository`` instance.
"""

import json
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from app.agent.repository import (
    AgentRepository,
    InvalidApprovalTransitionError,
    NotFoundError,
)
from app.core.errors import InvalidRequestError
from app.models.agent_models import (
    AgentEventResponse,
    AgentSessionResponse,
    AgentStateResponse,
    AgentTaskResponse,
    ApprovalDecisionRequest,
    ApprovalRequestResponse,
    CreateAgentSessionRequest,
    SubmitAgentTaskRequest,
)
from app.models.error_models import ErrorResponse

router = APIRouter(prefix="/api/v1/agent", tags=["agent"])

_DEFAULT_APPROVAL_TTL_SECONDS = 3600


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_repo(request: Request) -> AgentRepository:
    return request.app.state.agent_repository  # type: ignore[no-any-return]


def _session_response(session) -> AgentSessionResponse:
    return AgentSessionResponse(
        session_id=session.session_id,
        status=session.status,  # type: ignore[arg-type]
        title=session.title,
        created_at=session.created_at,
        updated_at=session.updated_at,
        metadata=session.metadata,
    )


def _task_response(task) -> AgentTaskResponse:
    return AgentTaskResponse(
        task_id=task.task_id,
        session_id=task.session_id,
        status=task.status,  # type: ignore[arg-type]
        prompt=task.prompt,
        result=task.result,
        created_at=task.created_at,
        updated_at=task.updated_at,
    )


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


def _approval_response(approval) -> ApprovalRequestResponse:
    return ApprovalRequestResponse(
        approval_id=approval.approval_id,
        session_id=approval.session_id,
        task_id=approval.task_id,
        action_type=approval.action_type,
        action_payload=approval.action_payload,
        action_fingerprint=approval.action_fingerprint,
        status=approval.status,  # type: ignore[arg-type]
        expires_at=approval.expires_at,
        consumed_at=approval.consumed_at,
        created_at=approval.created_at,
        updated_at=approval.updated_at,
    )


# ---------------------------------------------------------------------------
# Session routes
# ---------------------------------------------------------------------------


@router.post(
    "/sessions",
    response_model=AgentSessionResponse,
    status_code=201,
    responses={401: {"model": ErrorResponse}, 422: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def create_session(
    body: CreateAgentSessionRequest,
    raw_request: Request,
) -> AgentSessionResponse:
    repo = _get_repo(raw_request)
    session = repo.create_session(
        session_id=str(uuid.uuid4()),
        title=body.title,
        metadata=body.metadata,
    )
    return _session_response(session)


@router.get(
    "/sessions/{session_id}",
    response_model=AgentSessionResponse,
    responses={401: {"model": ErrorResponse}, 422: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def get_session(
    session_id: str,
    raw_request: Request,
) -> AgentSessionResponse:
    repo = _get_repo(raw_request)
    session = repo.get_session(session_id)
    if session is None:
        raise InvalidRequestError(f"Session not found: {session_id!r}")
    return _session_response(session)


# ---------------------------------------------------------------------------
# Task routes
# ---------------------------------------------------------------------------


@router.post(
    "/sessions/{session_id}/tasks",
    response_model=AgentTaskResponse,
    status_code=202,
    responses={401: {"model": ErrorResponse}, 422: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def submit_task(
    session_id: str,
    body: SubmitAgentTaskRequest,
    raw_request: Request,
) -> AgentTaskResponse:
    repo = _get_repo(raw_request)
    session = repo.get_session(session_id)
    if session is None:
        raise InvalidRequestError(f"Session not found: {session_id!r}")

    task_id = str(uuid.uuid4())
    task = repo.create_task(
        task_id=task_id,
        session_id=session_id,
        prompt=body.prompt.strip(),
    )
    # Emit a task_accepted event so consumers can observe submission
    repo.append_event(
        event_id=str(uuid.uuid4()),
        session_id=session_id,
        task_id=task_id,
        event_type="task_accepted",
        payload={"prompt": body.prompt},
    )
    return _task_response(task)


# ---------------------------------------------------------------------------
# Event routes
# ---------------------------------------------------------------------------


@router.get(
    "/sessions/{session_id}/events",
    response_model=list[AgentEventResponse],
    responses={401: {"model": ErrorResponse}, 422: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def list_events(
    session_id: str,
    raw_request: Request,
    after_sequence: int = 0,
) -> list[AgentEventResponse]:
    repo = _get_repo(raw_request)
    session = repo.get_session(session_id)
    if session is None:
        raise InvalidRequestError(f"Session not found: {session_id!r}")
    events = repo.list_events(session_id=session_id, after_sequence=after_sequence)
    return [_event_response(e) for e in events]


@router.get(
    "/sessions/{session_id}/events/stream",
    responses={401: {"model": ErrorResponse}, 422: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def stream_events(
    session_id: str,
    raw_request: Request,
    after_sequence: int = 0,
) -> StreamingResponse:
    repo = _get_repo(raw_request)
    session = repo.get_session(session_id)
    if session is None:
        raise InvalidRequestError(f"Session not found: {session_id!r}")

    events = repo.list_events(session_id=session_id, after_sequence=after_sequence)

    async def _generate():
        for event in events:
            dto = _event_response(event)
            data = dto.model_dump(mode="json")
            # SSE frame: "event: <event_type>\ndata: <json>\n\n"
            yield f"event: {dto.event_type}\ndata: {json.dumps(data)}\n\n"

    return StreamingResponse(_generate(), media_type="text/event-stream")


# ---------------------------------------------------------------------------
# Approval routes
# ---------------------------------------------------------------------------


@router.get(
    "/sessions/{session_id}/approvals",
    response_model=list[ApprovalRequestResponse],
    responses={401: {"model": ErrorResponse}, 422: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def list_approvals(
    session_id: str,
    raw_request: Request,
) -> list[ApprovalRequestResponse]:
    repo = _get_repo(raw_request)
    session = repo.get_session(session_id)
    if session is None:
        raise InvalidRequestError(f"Session not found: {session_id!r}")
    approvals = repo.list_pending_approvals(session_id)
    return [_approval_response(a) for a in approvals]


@router.post(
    "/sessions/{session_id}/approvals/{approval_id}",
    response_model=ApprovalRequestResponse,
    responses={401: {"model": ErrorResponse}, 422: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def decide_approval(
    session_id: str,
    approval_id: str,
    body: ApprovalDecisionRequest,
    raw_request: Request,
) -> ApprovalRequestResponse:
    repo = _get_repo(raw_request)
    session = repo.get_session(session_id)
    if session is None:
        raise InvalidRequestError(f"Session not found: {session_id!r}")

    try:
        approval = repo.decide_approval(approval_id, body.decision)
    except NotFoundError as exc:
        raise InvalidRequestError(str(exc)) from exc
    except InvalidApprovalTransitionError as exc:
        raise InvalidRequestError(str(exc)) from exc

    if approval.session_id != session_id:
        raise InvalidRequestError(
            f"Approval {approval_id!r} does not belong to session {session_id!r}"
        )
    return _approval_response(approval)


# ---------------------------------------------------------------------------
# State route
# ---------------------------------------------------------------------------


@router.get(
    "/sessions/{session_id}/state",
    response_model=AgentStateResponse,
    responses={401: {"model": ErrorResponse}, 422: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def get_session_state(
    session_id: str,
    raw_request: Request,
) -> AgentStateResponse:
    repo = _get_repo(raw_request)
    session = repo.get_session(session_id)
    if session is None:
        raise InvalidRequestError(f"Session not found: {session_id!r}")

    tasks = repo.list_tasks(session_id)

    events = repo.list_events(session_id=session_id)
    pending_approvals = repo.list_pending_approvals(session_id)

    return AgentStateResponse(
        session_id=session_id,
        session=_session_response(session),
        tasks=[_task_response(t) for t in tasks],
        events=[_event_response(e) for e in events],
        pending_approvals=[_approval_response(a) for a in pending_approvals],
    )
