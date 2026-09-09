import { chatStreamEvents, type components } from "@ai-fullstack-starter/api-contract";
import { createSseParser } from "./sse";

type ChatRequest = components["schemas"]["ChatRequest"];
type ChatResponse = components["schemas"]["ChatResponse"];
type ErrorResponse = components["schemas"]["ErrorResponse"];

export const BASE_URL = (
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000"
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

export async function getHealth(): Promise<void> {
  const response = await fetch(`${BASE_URL}/api/v1/health`);
  if (!response.ok) {
    throw await errorFromResponse(response);
  }
}

type LearningAnswerRequest =
  components["schemas"]["LearningAnswerRequest"];
type LearningAnswerResponse =
  components["schemas"]["LearningAnswerResponse"];

export async function answerLearningQuestion(
  request: LearningAnswerRequest,
): Promise<LearningAnswerResponse> {
  let response: Response;

  try {
    response = await fetch(`${BASE_URL}/api/v1/learning/answer`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(request),
    });
  } catch {
    throw new ContractError(
      "provider_unavailable",
      "cannot reach the backend",
    );
  }

  if (!response.ok) {
    throw await errorFromResponse(response);
  }

  return (await response.json()) as LearningAnswerResponse;
}



export interface StreamHandlers {
  onDelta: (content: string) => void;
  onMessage: (response: ChatResponse) => void;
  onError: (error: ContractError) => void;
}

export async function streamChat(
  request: Omit<ChatRequest, "stream">,
  handlers: StreamHandlers,
): Promise<void> {
  let response: Response;
  try {
    response = await fetch(`${BASE_URL}/api/v1/chat`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ ...request, stream: true }),
    });
  } catch {
    handlers.onError(new ContractError("provider_unavailable", "cannot reach the backend"));
    return;
  }
  if (!response.ok || !response.body) {
    handlers.onError(await errorFromResponse(response));
    return;
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  const parser = createSseParser((event) => {
    if (event.name === chatStreamEvents.delta) {
      handlers.onDelta(JSON.parse(event.data).content as string);
    } else if (event.name === chatStreamEvents.message) {
      handlers.onMessage(JSON.parse(event.data) as ChatResponse);
    } else if (event.name === chatStreamEvents.error) {
      const body = JSON.parse(event.data) as ErrorResponse;
      handlers.onError(new ContractError(body.error.code, body.error.message));
    }
  });
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    parser.push(decoder.decode(value, { stream: true }));
  }
}
