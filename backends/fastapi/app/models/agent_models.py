"""Pydantic request/response DTOs for the agent control-plane API.

Mirrors the schemas defined in packages/api-contract/openapi.yaml under the
``agent`` tag.  Field constraints are intentionally kept in sync with the
OpenAPI spec (e.g. ``prompt`` minLength, ``decision`` enum).
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------


class CreateAgentSessionRequest(BaseModel):
    title: str | None = None
    metadata: dict | None = None


class SubmitAgentTaskRequest(BaseModel):
    prompt: str = Field(min_length=1)
    metadata: dict | None = None


class ApprovalDecisionRequest(BaseModel):
    decision: Literal["approved", "rejected"]
    rationale: str | None = None


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------

AgentSessionStatus = Literal["active", "idle", "completed", "error"]
AgentTaskStatus = Literal[
    "pending", "running", "succeeded", "failed", "cancelled", "timed_out", "blocked"
]
AgentEventType = Literal[
    "assistant_output",
    "tool_call",
    "tool_result",
    "approval_requested",
    "approval_decided",
    "error",
    "completed",
    "task_accepted",
    "agent_started",
]
ApprovalStatus = Literal["pending", "approved", "rejected", "expired", "consumed"]


class AgentSessionResponse(BaseModel):
    session_id: str
    status: AgentSessionStatus
    title: str | None = None
    created_at: datetime
    updated_at: datetime
    metadata: dict | None = None


class AgentTaskResponse(BaseModel):
    task_id: str
    session_id: str
    status: AgentTaskStatus
    prompt: str
    result: str | None = None
    created_at: datetime
    updated_at: datetime


class AgentEventResponse(BaseModel):
    event_id: str
    session_id: str
    task_id: str
    sequence: int
    event_type: AgentEventType
    payload: dict | None = None
    created_at: datetime


class ApprovalRequestResponse(BaseModel):
    approval_id: str
    session_id: str
    task_id: str
    action_type: str
    action_payload: dict | None = None
    action_fingerprint: str
    status: ApprovalStatus
    expires_at: datetime
    consumed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class AgentStateResponse(BaseModel):
    session_id: str
    session: AgentSessionResponse
    tasks: list[AgentTaskResponse]
    events: list[AgentEventResponse]
    pending_approvals: list[ApprovalRequestResponse]
