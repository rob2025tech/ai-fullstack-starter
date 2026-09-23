import {
  chatStreamEvents,
  type components,
} from "@ai-fullstack-starter/api-contract";

import { createSseParser } from "./sse";

type ChatRequest = components["schemas"]["ChatRequest"];
type ChatResponse = components["schemas"]["ChatResponse"];
type ErrorResponse = components["schemas"]["ErrorResponse"];

type LearningStateResponse =
  components["schemas"]["LearningStateResponse"];

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

function jsonPost(body: unknown): RequestInit {
  return {
    method: "POST",
    headers: { "content-type": "application/json" },
    credentials: "include",
    body: JSON.stringify(body),
  };
}

export async function getHealth(): Promise<void> {
  const response = await fetch(`${BASE_URL}/api/v1/health`);

  if (!response.ok) {
    throw await errorFromResponse(response);
  }
}

export async function getLearningState(
  concept: string,
): Promise<LearningStateResponse> {
  let response: Response;

  try {
    response = await fetch(
      `${BASE_URL}/api/v1/learning/state?concept=${encodeURIComponent(concept)}`,
      { credentials: "include" },
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

  return (await response.json()) as LearningStateResponse;
}

export async function answerLearningQuestion(
  request: LearningAnswerRequest,
): Promise<LearningAnswerResponse> {
  let response: Response;

  try {
    response = await fetch(
      `${BASE_URL}/api/v1/learning/answer`,
      jsonPost({
        concept: request.concept,
        answer: request.answer,
      }),
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
      jsonPost({
        concept: request.concept,
        selected_answer: request.selected_answer,
      }),
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
      jsonPost({
        concept: request.concept,
        selected_answer: request.selected_answer,
      }),
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
      jsonPost({
        concept: request.concept,
        selected_answer: request.selected_answer,
      }),
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
