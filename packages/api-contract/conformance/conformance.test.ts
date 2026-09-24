import { describe, expect, it } from "vitest";

/**
 * Contract conformance suite (ADR-001). Runs against any live backend
 * that claims to implement the contract:
 *
 *   CONTRACT_BASE_URL=http://127.0.0.1:8000 npm run test:conformance
 *
 * Assertions check the contract only — shapes, status codes, error
 * codes, SSE framing — never implementation details, so the identical
 * suite can gate FastAPI, Express, or any future backend.
 */

const BASE_URL = (
  process.env.CONTRACT_BASE_URL ?? "http://127.0.0.1:8000"
).replace(/\/$/, "");

interface SseEvent {
  name: string;
  data: string;
}

async function collectSseEvents(response: Response): Promise<SseEvent[]> {
  expect(response.body, "SSE response must have a body").not.toBeNull();
  const reader = response.body!.getReader();
  const decoder = new TextDecoder();
  const events: SseEvent[] = [];
  let buffer = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let separator: number;
    while ((separator = buffer.indexOf("\n\n")) !== -1) {
      const raw = buffer.slice(0, separator);
      buffer = buffer.slice(separator + 2);
      let name = "message";
      const dataLines: string[] = [];
      for (const line of raw.split("\n")) {
        if (line.startsWith("event:")) name = line.slice(6).trim();
        else if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
      }
      if (dataLines.length > 0) {
        events.push({ name, data: dataLines.join("\n") });
      }
    }
  }
  return events;
}

function assertErrorEnvelope(body: unknown, expectedCode: string): void {
  expect(body).toHaveProperty("error");
  const error = (body as { error: { code: string; message: string } }).error;
  expect(error.code).toBe(expectedCode);
  expect(typeof error.message).toBe("string");
  expect(error.message.length).toBeGreaterThan(0);
}

describe(`API contract conformance @ ${BASE_URL}`, () => {
  it("GET /api/v1/health returns status ok", async () => {
    const response = await fetch(`${BASE_URL}/api/v1/health`);
    expect(response.status).toBe(200);
    expect(response.headers.get("content-type")).toContain("application/json");
    const body = (await response.json()) as { status: string; version?: string };
    expect(body.status).toBe("ok");
    if (body.version !== undefined) {
      expect(typeof body.version).toBe("string");
    }
  });

  it("POST /api/v1/chat (JSON mode) returns a ChatResponse", async () => {
    const response = await fetch(`${BASE_URL}/api/v1/chat`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ prompt: "ping", user_id: "conformance" }),
    });
    expect(response.status).toBe(200);
    expect(response.headers.get("content-type")).toContain("application/json");
    const body = (await response.json()) as {
      message: {
        id: string;
        role: string;
        content: string;
        finish_reason: string;
      };
      usage?: { input_tokens?: number | null; output_tokens?: number | null } | null;
    };
    expect(typeof body.message.id).toBe("string");
    expect(body.message.role).toBe("assistant");
    expect(typeof body.message.content).toBe("string");
    expect(body.message.content.length).toBeGreaterThan(0);
    expect(["stop", "length"]).toContain(body.message.finish_reason);
    if (body.usage) {
      for (const tokens of [body.usage.input_tokens, body.usage.output_tokens]) {
        if (tokens !== null && tokens !== undefined) {
          expect(Number.isInteger(tokens)).toBe(true);
          expect(tokens).toBeGreaterThanOrEqual(0);
        }
      }
    }
  });

  it("POST /api/v1/chat (SSE mode) streams deltas then a terminal message event", async () => {
    const response = await fetch(`${BASE_URL}/api/v1/chat`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ prompt: "ping", stream: true }),
    });
    expect(response.status).toBe(200);
    expect(response.headers.get("content-type")).toContain("text/event-stream");
    const events = await collectSseEvents(response);
    expect(events.length).toBeGreaterThanOrEqual(1);
    const terminal = events[events.length - 1];
    expect(["message", "error"]).toContain(terminal.name);
    expect(terminal.name, "conformance expects a successful backend").toBe(
      "message",
    );
    const payload = JSON.parse(terminal.data) as {
      message: { role: string; content: string };
    };
    expect(payload.message.role).toBe("assistant");
    expect(payload.message.content.length).toBeGreaterThan(0);
    for (const event of events.slice(0, -1)) {
      expect(event.name).toBe("delta");
      expect(typeof JSON.parse(event.data).content).toBe("string");
    }
  });

  it("rejects an empty prompt with the error envelope", async () => {
    const response = await fetch(`${BASE_URL}/api/v1/chat`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ prompt: "" }),
    });
    expect(response.status).toBe(422);
    expect(response.headers.get("content-type")).toContain("application/json");
    assertErrorEnvelope(await response.json(), "invalid_request");
  });

  // ---------------------------------------------------------------------------
  // Protected learning endpoints — 401 conformance (AC-3, AC-4).
  // These tests require a protected-mode backend
  // (deployment_mode: shared-demo or production).  They assert that
  // unauthenticated requests receive a contract-shaped 401 envelope rather
  // than a FastAPI default detail payload or a 200 with demo state.
  // ---------------------------------------------------------------------------

  it("GET /api/v1/learning/state without credentials returns 401 and unauthorized envelope", async () => {
    const response = await fetch(
      `${BASE_URL}/api/v1/learning/state?concept=additive-versioning`,
    );
    expect(response.status).toBe(401);
    expect(response.headers.get("content-type")).toContain("application/json");
    assertErrorEnvelope(await response.json(), "unauthorized");
  });

  it("POST /api/v1/learning/answer without credentials returns 401 and unauthorized envelope", async () => {
    const response = await fetch(`${BASE_URL}/api/v1/learning/answer`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        concept: "additive-versioning",
        answer: "Adding a new optional field to a response",
      }),
    });
    expect(response.status).toBe(401);
    expect(response.headers.get("content-type")).toContain("application/json");
    assertErrorEnvelope(await response.json(), "unauthorized");
  });

  it("POST /api/v1/learning/quiz/answer without credentials returns 401 and unauthorized envelope", async () => {
    const response = await fetch(`${BASE_URL}/api/v1/learning/quiz/answer`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        concept: "provider-fallback-pattern",
        selected_answer:
          "So a flaky LLM provider degrades to a deterministic explanation instead of crashing a live demo",
      }),
    });
    expect(response.status).toBe(401);
    expect(response.headers.get("content-type")).toContain("application/json");
    assertErrorEnvelope(await response.json(), "unauthorized");
  });

  it("POST /api/v1/learning/quiz/practice without credentials returns 401 and unauthorized envelope", async () => {
    const response = await fetch(`${BASE_URL}/api/v1/learning/quiz/practice`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        concept: "provider-fallback-pattern",
        selected_answer:
          "So a flaky LLM provider degrades to a deterministic explanation instead of crashing a live demo",
      }),
    });
    expect(response.status).toBe(401);
    expect(response.headers.get("content-type")).toContain("application/json");
    assertErrorEnvelope(await response.json(), "unauthorized");
  });

  it("POST /api/v1/learning/quiz/retest without credentials returns 401 and unauthorized envelope", async () => {
    const response = await fetch(`${BASE_URL}/api/v1/learning/quiz/retest`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        concept: "additive-versioning",
        selected_answer:
          "Add the new field without removing or changing existing fields",
      }),
    });
    expect(response.status).toBe(401);
    expect(response.headers.get("content-type")).toContain("application/json");
    assertErrorEnvelope(await response.json(), "unauthorized");
  });
});
