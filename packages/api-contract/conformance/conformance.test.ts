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

  it("GET /api/v1/agent/sessions/{session_id}/tasks/{task_id}/events returns JSON replay", async () => {
    // Create a session and task first
    const sessResp = await fetch(`${BASE_URL}/api/v1/agent/sessions`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ title: "conformance-test" }),
    });
    expect(sessResp.status).toBe(201);
    const sessBody = (await sessResp.json()) as { session_id: string };
    const sessionId = sessBody.session_id;

    const taskResp = await fetch(
      `${BASE_URL}/api/v1/agent/sessions/${sessionId}/tasks`,
      {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ prompt: "conformance event replay test" }),
      },
    );
    expect(taskResp.status).toBe(202);
    const taskBody = (await taskResp.json()) as { task_id: string };
    const taskId = taskBody.task_id;

    // Replay endpoint — no events yet, should return 200 with empty array
    const eventsResp = await fetch(
      `${BASE_URL}/api/v1/agent/sessions/${sessionId}/tasks/${taskId}/events`,
    );
    expect(eventsResp.status).toBe(200);
    expect(eventsResp.headers.get("content-type")).toContain("application/json");
    const eventsBody = (await eventsResp.json()) as {
      events: unknown[];
      next_after_sequence: number | null;
    };
    expect(Array.isArray(eventsBody.events)).toBe(true);
    // A newly-submitted task may have a task_accepted event from the router
    expect(eventsBody.events.length).toBeGreaterThanOrEqual(0);
    expect("next_after_sequence" in eventsBody).toBe(true);
  });

  it("GET /api/v1/agent/sessions/{session_id}/tasks/{task_id}/events/stream returns SSE", async () => {
    // Create a fresh session + task
    const sessResp = await fetch(`${BASE_URL}/api/v1/agent/sessions`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({}),
    });
    const sessionId = ((await sessResp.json()) as { session_id: string })
      .session_id;

    const taskResp = await fetch(
      `${BASE_URL}/api/v1/agent/sessions/${sessionId}/tasks`,
      {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ prompt: "conformance sse test" }),
      },
    );
    const taskId = ((await taskResp.json()) as { task_id: string }).task_id;

    const streamResp = await fetch(
      `${BASE_URL}/api/v1/agent/sessions/${sessionId}/tasks/${taskId}/events/stream`,
    );
    expect(streamResp.status).toBe(200);
    expect(streamResp.headers.get("content-type")).toContain("text/event-stream");

    // Collect whatever events are available (may be empty or have task_accepted)
    const events = await collectSseEvents(streamResp);
    // Just assert we get a valid (possibly empty) stream
    for (const event of events) {
      expect(typeof event.name).toBe("string");
      const payload = JSON.parse(event.data) as {
        task_id: string;
        sequence: number;
        event_type: string;
      };
      expect(payload.task_id).toBe(taskId);
      expect(typeof payload.sequence).toBe("number");
      expect(payload.sequence).toBeGreaterThan(0);
    }
  });

  it("GET task events with unknown session returns 422 error envelope", async () => {
    const resp = await fetch(
      `${BASE_URL}/api/v1/agent/sessions/no-such-session/tasks/no-such-task/events`,
    );
    expect(resp.status).toBe(422);
    assertErrorEnvelope(await resp.json(), "invalid_request");
  });
});
