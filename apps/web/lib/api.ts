import {
  agentStreamEvents,
  chatStreamEvents,
  type components,
} from "@ai-fullstack-starter/api-contract";

import { createSseParser } from "./sse";

type ChatRequest = components["schemas"]["ChatRequest"];
type ChatResponse = components["schemas"]["ChatResponse"];
type ErrorResponse = components["schemas"]["ErrorResponse"];

// Agent API types from generated contract schema
type CreateAgentSessionRequest =
  components["schemas"]["CreateAgentSessionRequest"];
type AgentSessionResponse = components["schemas"]["AgentSessionResponse"];
type SubmitAgentTaskRequest = components["schemas"]["SubmitAgentTaskRequest"];
type AgentTaskResponse = components["schemas"]["AgentTaskResponse"];
export type AgentEventResponse = components["schemas"]["AgentEventResponse"];
type ApprovalDecisionRequest =
  components["schemas"]["ApprovalDecisionRequest"];
type ApprovalRequestResponse =
  components["schemas"]["ApprovalRequestResponse"];

// AgentEventReplayResponse: task-scoped response shape (WO-013 added to
// openapi.yaml; not yet regenerated into schema.ts).
export interface AgentEventReplayResponse {
  events: AgentEventResponse[];
  next_after_sequence: number | null;
}

type LearningAnswerRequest =
  components["schemas"]["LearningAnswerRequest"];

type LearningAnswerResponse =
  components["schemas"]["LearningAnswerResponse"];

type LearningQuizResponse =
  components["schemas"]["LearningQuizResponse"];

type LearningQuizAnswerRequest =
  components["schemas"]["LearningQuizAnswerRequest"];

type LearningQuizAnswerResponse =
  components["schemas"]["LearningQuizAnswerResponse"];

type LearningPracticeAnswerRequest =
  components["schemas"]["LearningPracticeAnswerRequest"];

type LearningPracticeAnswerResponse =
  components["schemas"]["LearningPracticeAnswerResponse"];

type LearningRetestResponse =
  components["schemas"]["LearningRetestResponse"];

type LearningRetestAnswerRequest =
  components["schemas"]["LearningRetestAnswerRequest"];

type LearningRetestAnswerResponse =
  components["schemas"]["LearningRetestAnswerResponse"];

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

async function errorFromResponse(
  response: Response,
): Promise<ContractError> {
  try {
    const body = (await response.json()) as ErrorResponse;

    if (body?.error?.code) {
      return new ContractError(
        body.error.code,
        body.error.message,
      );
    }
  } catch {
    // Non-JSON error body: fall through to a generic error.
  }

  return new ContractError(
    "internal_error",
    `request failed with HTTP ${response.status}`,
  );
}

export async function getHealth(): Promise<void> {
  const response = await fetch(`${BASE_URL}/api/v1/health`);

  if (!response.ok) {
    throw await errorFromResponse(response);
  }
}

export async function answerLearningQuestion(
  request: LearningAnswerRequest,
): Promise<LearningAnswerResponse> {
  let response: Response;

  try {
    response = await fetch(`${BASE_URL}/api/v1/learning/answer`, {
      method: "POST",
      headers: {
        "content-type": "application/json",
      },
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

export async function getLearningQuiz(
  concept: string,
): Promise<LearningQuizResponse> {
  let response: Response;

  try {
    response = await fetch(
      `${BASE_URL}/api/v1/learning/quiz?concept=${encodeURIComponent(concept)}`,
    );
  } catch {
    throw new ContractError(
      "provider_unavailable",
      "cannot reach the backend",
    );
  }

  if (!response.ok) {
    throw await errorFromResponse(response);
  }

  return (await response.json()) as LearningQuizResponse;
}

export async function answerLearningQuiz(
  request: LearningQuizAnswerRequest,
): Promise<LearningQuizAnswerResponse> {
  let response: Response;

  try {
    response = await fetch(
      `${BASE_URL}/api/v1/learning/quiz/answer`,
      {
        method: "POST",
        headers: {
          "content-type": "application/json",
        },
        body: JSON.stringify(request),
      },
    );
  } catch {
    throw new ContractError(
      "provider_unavailable",
      "cannot reach the backend",
    );
  }

  if (!response.ok) {
    throw await errorFromResponse(response);
  }

  return (await response.json()) as LearningQuizAnswerResponse;
}

export async function answerLearningPractice(
  request: LearningPracticeAnswerRequest,
): Promise<LearningPracticeAnswerResponse> {
  let response: Response;

  try {
    response = await fetch(
      `${BASE_URL}/api/v1/learning/quiz/practice`,
      {
        method: "POST",
        headers: {
          "content-type": "application/json",
        },
        body: JSON.stringify(request),
      },
    );
  } catch {
    throw new ContractError(
      "provider_unavailable",
      "cannot reach the backend",
    );
  }

  if (!response.ok) {
    throw await errorFromResponse(response);
  }

  return (await response.json()) as LearningPracticeAnswerResponse;
}

export async function getLearningRetest(
  concept: string,
): Promise<LearningRetestResponse> {
  let response: Response;

  try {
    response = await fetch(
      `${BASE_URL}/api/v1/learning/quiz/retest?concept=${encodeURIComponent(concept)}`,
    );
  } catch {
    throw new ContractError(
      "provider_unavailable",
      "cannot reach the backend",
    );
  }

  if (!response.ok) {
    throw await errorFromResponse(response);
  }

  return (await response.json()) as LearningRetestResponse;
}

export async function answerLearningRetest(
  request: LearningRetestAnswerRequest,
): Promise<LearningRetestAnswerResponse> {
  let response: Response;

  try {
    response = await fetch(
      `${BASE_URL}/api/v1/learning/quiz/retest`,
      {
        method: "POST",
        headers: {
          "content-type": "application/json",
        },
        body: JSON.stringify(request),
      },
    );
  } catch {
    throw new ContractError(
      "provider_unavailable",
      "cannot reach the backend",
    );
  }

  if (!response.ok) {
    throw await errorFromResponse(response);
  }

  return (await response.json()) as LearningRetestAnswerResponse;
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
      headers: {
        "content-type": "application/json",
      },
      body: JSON.stringify({
        ...request,
        stream: true,
      }),
    });
  } catch {
    handlers.onError(
      new ContractError(
        "provider_unavailable",
        "cannot reach the backend",
      ),
    );
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
      handlers.onDelta(
        JSON.parse(event.data).content as string,
      );
    } else if (event.name === chatStreamEvents.message) {
      handlers.onMessage(
        JSON.parse(event.data) as ChatResponse,
      );
    } else if (event.name === chatStreamEvents.error) {
      const body = JSON.parse(event.data) as ErrorResponse;

      handlers.onError(
        new ContractError(
          body.error.code,
          body.error.message,
        ),
      );
    }
  });

  for (;;) {
    const { done, value } = await reader.read();

    if (done) {
      break;
    }

    parser.push(
      decoder.decode(value, {
        stream: true,
      }),
    );
  }
}

// ---------------------------------------------------------------------------
// Agent API helpers
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
    throw new ContractError(
      "provider_unavailable",
      "cannot reach the backend",
    );
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
    response = await fetch(
      `${BASE_URL}/api/v1/agent/sessions/${sessionId}`,
    );
  } catch {
    throw new ContractError(
      "provider_unavailable",
      "cannot reach the backend",
    );
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
    throw new ContractError(
      "provider_unavailable",
      "cannot reach the backend",
    );
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
    throw new ContractError(
      "provider_unavailable",
      "cannot reach the backend",
    );
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
    throw new ContractError(
      "provider_unavailable",
      "cannot reach the backend",
    );
  }

  if (!response.ok) {
    throw await errorFromResponse(response);
  }

  return (await response.json()) as AgentEventReplayResponse;
}

export interface AgentEventStreamHandlers {
  onEvent: (event: AgentEventResponse) => void;
  onError: (error: ContractError) => void;
}

export async function streamAgentEvents(
  sessionId: string,
  taskId: string,
  afterSequence: number,
  handlers: AgentEventStreamHandlers,
): Promise<void> {
  const url =
    `${BASE_URL}/api/v1/agent/sessions/${sessionId}/tasks/${taskId}/events/stream` +
    `?after_sequence=${afterSequence}`;

  let response: Response;

  try {
    response = await fetch(url);
  } catch {
    handlers.onError(
      new ContractError(
        "provider_unavailable",
        "cannot reach the backend",
      ),
    );
    return;
  }

  if (!response.ok || !response.body) {
    handlers.onError(await errorFromResponse(response));
    return;
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();

  const parser = createSseParser((sseEvent) => {
    // Skip error frames coming from the stream itself
    if (sseEvent.name === agentStreamEvents.error) {
      try {
        const body = JSON.parse(sseEvent.data) as ErrorResponse;
        handlers.onError(
          new ContractError(
            body.error?.code ?? "internal_error",
            body.error?.message ?? "stream error",
          ),
        );
      } catch {
        handlers.onError(
          new ContractError("internal_error", "stream error"),
        );
      }
      return;
    }

    try {
      const payload = JSON.parse(sseEvent.data) as AgentEventResponse;
      handlers.onEvent(payload);
    } catch {
      // skip malformed frames
    }
  });

  for (;;) {
    const { done, value } = await reader.read();

    if (done) {
      break;
    }

    parser.push(decoder.decode(value, { stream: true }));
  }
}