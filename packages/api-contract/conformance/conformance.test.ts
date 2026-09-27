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

  // -------------------------------------------------------------------------
  // Agent control plane
  // -------------------------------------------------------------------------

  async function createSession(title?: string): Promise<string> {
    const resp = await fetch(`${BASE_URL}/api/v1/agent/sessions`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(title === undefined ? {} : { title }),
    });
    expect(resp.status).toBe(201);
    return ((await resp.json()) as { session_id: string }).session_id;
  }

  async function submitTask(sessionId: string, prompt: string): Promise<string> {
    const resp = await fetch(
      `${BASE_URL}/api/v1/agent/sessions/${sessionId}/tasks`,
      {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ prompt }),
      },
    );
    expect(resp.status).toBe(202);
    return ((await resp.json()) as { task_id: string }).task_id;
  }

  it("POST /api/v1/agent/sessions creates a session (201) with required fields", async () => {
    const resp = await fetch(`${BASE_URL}/api/v1/agent/sessions`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ title: "conformance-session-create" }),
    });
    expect(resp.status).toBe(201);
    expect(resp.headers.get("content-type")).toContain("application/json");
    const body = (await resp.json()) as {
      session_id: string;
      status: string;
      created_at: string;
      updated_at: string;
    };
    expect(typeof body.session_id).toBe("string");
    expect(body.session_id.length).toBeGreaterThan(0);
    expect(body.status).toBe("active");
    expect(typeof body.created_at).toBe("string");
    expect(typeof body.updated_at).toBe("string");
  });

  it("GET /api/v1/agent/sessions/{session_id} retrieves the created session", async () => {
    const sessionId = await createSession();
    const resp = await fetch(`${BASE_URL}/api/v1/agent/sessions/${sessionId}`);
    expect(resp.status).toBe(200);
    const body = (await resp.json()) as { session_id: string; status: string };
    expect(body.session_id).toBe(sessionId);
    expect(body.status).toBe("active");
  });

  it("POST .../tasks accepts a task (202) with pending status", async () => {
    const sessionId = await createSession();
    const resp = await fetch(
      `${BASE_URL}/api/v1/agent/sessions/${sessionId}/tasks`,
      {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ prompt: "conformance task submission test" }),
      },
    );
    expect(resp.status).toBe(202);
    expect(resp.headers.get("content-type")).toContain("application/json");
    const body = (await resp.json()) as {
      task_id: string;
      session_id: string;
      status: string;
      prompt: string;
    };
    expect(typeof body.task_id).toBe("string");
    expect(body.task_id.length).toBeGreaterThan(0);
    expect(body.session_id).toBe(sessionId);
    expect(body.status).toBe("pending");
    expect(body.prompt).toBe("conformance task submission test");
  });

  it("POST .../tasks rejects an empty prompt with the error envelope", async () => {
    const sessionId = await createSession();
    const resp = await fetch(
      `${BASE_URL}/api/v1/agent/sessions/${sessionId}/tasks`,
      {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ prompt: "" }),
      },
    );
    expect(resp.status).toBe(422);
    assertErrorEnvelope(await resp.json(), "invalid_request");
  });

  it("GET .../events returns session events conforming to the event schema", async () => {
    const sessionId = await createSession("conformance-event-types");
    await submitTask(sessionId, "conformance event type assertion");

    const resp = await fetch(
      `${BASE_URL}/api/v1/agent/sessions/${sessionId}/events`,
    );
    expect(resp.status).toBe(200);
    expect(resp.headers.get("content-type")).toContain("application/json");
    const events = (await resp.json()) as Array<{
      event_id: string;
      session_id: string;
      task_id: string;
      sequence: number;
      event_type: string;
      created_at: string;
    }>;
    expect(Array.isArray(events)).toBe(true);

    // The full event-type registry pinned by the canonical contract.
    const allowedEventTypes = new Set([
      "assistant_output",
      "tool_call",
      "tool_result",
      "approval_requested",
      "approval_decided",
      "approval_consumed",
      "error",
      "completed",
      "task_accepted",
      "agent_started",
    ]);
    for (const event of events) {
      expect(typeof event.event_id).toBe("string");
      expect(event.session_id).toBe(sessionId);
      expect(typeof event.task_id).toBe("string");
      expect(typeof event.sequence).toBe("number");
      expect(event.sequence).toBeGreaterThan(0);
      expect(
        allowedEventTypes.has(event.event_type),
        `unexpected event_type: ${event.event_type}`,
      ).toBe(true);
      expect(typeof event.created_at).toBe("string");
    }
  });

  it("GET .../tasks/{task_id}/events returns a JSON replay page", async () => {
    const sessionId = await createSession();
    const taskId = await submitTask(sessionId, "conformance event replay test");

    const resp = await fetch(
      `${BASE_URL}/api/v1/agent/sessions/${sessionId}/tasks/${taskId}/events`,
    );
    expect(resp.status).toBe(200);
    expect(resp.headers.get("content-type")).toContain("application/json");
    const body = (await resp.json()) as {
      events: Array<{ task_id: string; event_type: string; sequence: number }>;
      next_after_sequence: number | null;
    };
    expect(Array.isArray(body.events)).toBe(true);
    expect("next_after_sequence" in body).toBe(true);
    // Submission records a task_accepted event, so replay is non-empty.
    expect(body.events.length).toBeGreaterThanOrEqual(1);
    for (const event of body.events) {
      expect(event.task_id).toBe(taskId);
    }
    expect(body.events[0].event_type).toBe("task_accepted");
  });

  it("GET .../tasks/{task_id}/events/stream replays events as SSE", async () => {
    const sessionId = await createSession();
    const taskId = await submitTask(sessionId, "conformance sse test");

    const resp = await fetch(
      `${BASE_URL}/api/v1/agent/sessions/${sessionId}/tasks/${taskId}/events/stream`,
    );
    expect(resp.status).toBe(200);
    expect(resp.headers.get("content-type")).toContain("text/event-stream");

    const events = await collectSseEvents(resp);
    expect(events.length).toBeGreaterThanOrEqual(1);
    for (const event of events) {
      const payload = JSON.parse(event.data) as {
        task_id: string;
        sequence: number;
        event_type: string;
      };
      // Frame name matches the event_type carried in the data payload.
      expect(event.name).toBe(payload.event_type);
      expect(payload.task_id).toBe(taskId);
      expect(typeof payload.sequence).toBe("number");
      expect(payload.sequence).toBeGreaterThan(0);
    }
  });

  it("rejects an unknown session with the error envelope", async () => {
    const resp = await fetch(
      `${BASE_URL}/api/v1/agent/sessions/no-such-session/tasks/no-such-task/events`,
    );
    expect(resp.status).toBe(422);
    assertErrorEnvelope(await resp.json(), "invalid_request");
  });

  it("POST .../approvals/{approval_id} rejects an unknown approval with the error envelope", async () => {
    const sessionId = await createSession();
    const resp = await fetch(
      `${BASE_URL}/api/v1/agent/sessions/${sessionId}/approvals/nonexistent-approval`,
      {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ decision: "approved" }),
      },
    );
    // The contract registers 422 invalid_request for unknown identifiers;
    // 404 is not part of the v1 error surface.
    expect(resp.status).toBe(422);
    assertErrorEnvelope(await resp.json(), "invalid_request");
  });

  it("GET .../state returns a consolidated session snapshot", async () => {
    const sessionId = await createSession();
    const taskId = await submitTask(sessionId, "conformance state test");

    const resp = await fetch(
      `${BASE_URL}/api/v1/agent/sessions/${sessionId}/state`,
    );
    expect(resp.status).toBe(200);
    expect(resp.headers.get("content-type")).toContain("application/json");
    const body = (await resp.json()) as {
      session_id: string;
      session: { session_id: string; status: string };
      tasks: Array<{ task_id: string; status: string }>;
      events: Array<{ task_id: string; event_type: string }>;
      pending_approvals: unknown[];
    };
    expect(body.session_id).toBe(sessionId);
    expect(body.session.session_id).toBe(sessionId);
    expect(body.tasks.length).toBe(1);
    expect(body.tasks[0].task_id).toBe(taskId);
    expect(Array.isArray(body.events)).toBe(true);
    expect(Array.isArray(body.pending_approvals)).toBe(true);
  });
});
