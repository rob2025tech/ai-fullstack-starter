// Mobile day-1 uses the contract's JSON mode (stream defaults to false):
// React Native fetch streaming is inconsistent across platforms, and the
// non-streaming POST /api/v1/chat response is the same ChatResponse shape
// the SSE terminal `message` event carries. Enabling SSE later is additive
// and requires no contract change (ADR-003).
import type { components } from "@ai-fullstack-starter/api-contract";

type ChatRequest = components["schemas"]["ChatRequest"];
type ChatResponse = components["schemas"]["ChatResponse"];
type ErrorResponse = components["schemas"]["ErrorResponse"];
type SessionBootstrapRequest = components["schemas"]["SessionBootstrapRequest"];
type SessionBootstrapResponse = components["schemas"]["SessionBootstrapResponse"];

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

export async function bootstrapSession(): Promise<SessionBootstrapResponse> {
  const reqBody: SessionBootstrapRequest = { transport: "bearer" };
  let response: Response;
  try {
    response = await fetch(`${BASE_URL}/api/v1/session/bootstrap`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(reqBody),
    });
  } catch {
    throw new ContractError("provider_unavailable", "cannot reach the backend");
  }
  if (!response.ok) {
    throw await errorFromResponse(response);
  }
  return (await response.json()) as SessionBootstrapResponse;
}

export interface SendChatOptions {
  sessionToken?: string;
}

export async function sendChat(
  request: Omit<ChatRequest, "stream">,
  options?: SendChatOptions,
): Promise<ChatResponse> {
  const headers: Record<string, string> = { "content-type": "application/json" };
  if (options?.sessionToken) {
    headers["authorization"] = `Bearer ${options.sessionToken}`;
  }
  let response: Response;
  try {
    response = await fetch(`${BASE_URL}/api/v1/chat`, {
      method: "POST",
      headers,
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
