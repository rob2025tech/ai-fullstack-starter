// Mobile day-1 uses the contract's JSON mode (stream defaults to false):
// React Native fetch streaming is inconsistent across platforms, and the
// non-streaming POST /api/v1/chat response is the same ChatResponse shape
// the SSE terminal `message` event carries. Enabling SSE later is additive
// and requires no contract change (ADR-003).
//
// Agent workflow follows the same JSON-only posture (ADR-006): the mobile
// client polls the JSON replay endpoint instead of opening an SSE stream.
import type { components } from "@ai-fullstack-starter/api-contract";

type ChatRequest = components["schemas"]["ChatRequest"];
type ChatResponse = components["schemas"]["ChatResponse"];
type ErrorResponse = components["schemas"]["ErrorResponse"];

// Agent API types from generated contract schema
type CreateAgentSessionRequest =
  components["schemas"]["CreateAgentSessionRequest"];
export type AgentSessionResponse =
  components["schemas"]["AgentSessionResponse"];
type SubmitAgentTaskRequest = components["schemas"]["SubmitAgentTaskRequest"];
export type AgentTaskResponse = components["schemas"]["AgentTaskResponse"];
export type AgentEventResponse = components["schemas"]["AgentEventResponse"];
type ApprovalDecisionRequest =
  components["schemas"]["ApprovalDecisionRequest"];
export type ApprovalRequestResponse =
  components["schemas"]["ApprovalRequestResponse"];

// AgentEventReplayResponse: task-scoped response shape added in WO-013.
// Not yet regenerated into schema.ts; defined locally to match openapi.yaml.
export interface AgentEventReplayResponse {
  events: AgentEventResponse[];
  next_after_sequence: number | null;
}

export const BASE_URL = (
  process.env.EXPO_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000"
).replace(/\/$/, "");

export class ContractError extends Error {
  constructor(
    readonly code: string,
    message: string,
  ) {
    super(message);
    this.name = "ContractError";
  }
}

async function errorFromResponse(response: Response): Promise<ContractError> {
  try {
    const body = (await response.json()) as ErrorResponse;
    if (body?.error?.code) {
      return new ContractError(body.error.code, body.error.message);
    }
  } catch {
    // Non-JSON error body: fall through to a generic error.
  }
  return new ContractError("internal_error", `request failed with HTTP ${response.status}`);
}

export async function sendChat(request: Omit<ChatRequest, "stream">): Promise<ChatResponse> {
  let response: Response;
  try {
    response = await fetch(`${BASE_URL}/api/v1/chat`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ ...request, stream: false }),
    });
  } catch {
    throw new ContractError("provider_unavailable", "cannot reach the backend");
  }
  if (!response.ok) {
    throw await errorFromResponse(response);
  }
  return (await response.json()) as ChatResponse;
}

// ---------------------------------------------------------------------------
// Agent API helpers — JSON-only, no SSE (ADR-006)
// ---------------------------------------------------------------------------

export async function createAgentSession(
  request?: CreateAgentSessionRequest,
): Promise<AgentSessionResponse> {
  let response: Response;
  try {
    response = await fetch(`${BASE_URL}/api/v1/agent/sessions`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(request ?? {}),
    });
  } catch {
    throw new ContractError("provider_unavailable", "cannot reach the backend");
  }
  if (!response.ok) {
    throw await errorFromResponse(response);
  }
  return (await response.json()) as AgentSessionResponse;
}

export async function getAgentSession(
  sessionId: string,
): Promise<AgentSessionResponse> {
  let response: Response;
  try {
    response = await fetch(`${BASE_URL}/api/v1/agent/sessions/${sessionId}`);
  } catch {
    throw new ContractError("provider_unavailable", "cannot reach the backend");
  }
  if (!response.ok) {
    throw await errorFromResponse(response);
  }
  return (await response.json()) as AgentSessionResponse;
}

export async function submitAgentTask(
  sessionId: string,
  request: SubmitAgentTaskRequest,
): Promise<AgentTaskResponse> {
  let response: Response;
  try {
    response = await fetch(
      `${BASE_URL}/api/v1/agent/sessions/${sessionId}/tasks`,
      {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(request),
      },
    );
  } catch {
    throw new ContractError("provider_unavailable", "cannot reach the backend");
  }
  if (!response.ok) {
    throw await errorFromResponse(response);
  }
  return (await response.json()) as AgentTaskResponse;
}

export async function submitAgentApproval(
  sessionId: string,
  approvalId: string,
  request: ApprovalDecisionRequest,
): Promise<ApprovalRequestResponse> {
  let response: Response;
  try {
    response = await fetch(
      `${BASE_URL}/api/v1/agent/sessions/${sessionId}/approvals/${approvalId}`,
      {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(request),
      },
    );
  } catch {
    throw new ContractError("provider_unavailable", "cannot reach the backend");
  }
  if (!response.ok) {
    throw await errorFromResponse(response);
  }
  return (await response.json()) as ApprovalRequestResponse;
}

export async function getAgentEvents(
  sessionId: string,
  taskId: string,
  afterSequence?: number,
): Promise<AgentEventReplayResponse> {
  let url = `${BASE_URL}/api/v1/agent/sessions/${sessionId}/tasks/${taskId}/events`;
  if (afterSequence !== undefined) {
    url += `?after_sequence=${afterSequence}`;
  }
  let response: Response;
  try {
    response = await fetch(url);
  } catch {
    throw new ContractError("provider_unavailable", "cannot reach the backend");
  }
  if (!response.ok) {
    throw await errorFromResponse(response);
  }
  return (await response.json()) as AgentEventReplayResponse;
}
