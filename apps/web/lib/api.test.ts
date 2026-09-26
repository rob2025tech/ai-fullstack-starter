import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  BASE_URL,
  ContractError,
  createAgentSession,
  getAgentEvents,
  getAgentSession,
  streamAgentEvents,
  submitAgentApproval,
  submitAgentTask,
} from "./api";
import {
  approvalRequestedEvent,
  completedEvent,
  errorFixture,
} from "../test/fixtures/agent-events";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function mockFetch(status: number, body: unknown, headers: Record<string, string> = {}) {
  global.fetch = vi.fn().mockResolvedValueOnce({
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
    body: null,
    headers: {
      get: (k: string) => headers[k] ?? null,
    },
  } as unknown as Response);
}

function errorBody(code: string, message: string) {
  return { error: { code, message } };
}

// ---------------------------------------------------------------------------
// createAgentSession
// ---------------------------------------------------------------------------

describe("createAgentSession", () => {
  afterEach(() => vi.restoreAllMocks());

  it("sends POST to /api/v1/agent/sessions with empty body", async () => {
    mockFetch(201, { session_id: "sess-1", status: "active", created_at: "t", updated_at: "t" });
    await createAgentSession();
    expect(global.fetch).toHaveBeenCalledWith(
      `${BASE_URL}/api/v1/agent/sessions`,
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("returns the session from the response body", async () => {
    mockFetch(201, { session_id: "sess-1", status: "active", created_at: "t", updated_at: "t" });
    const session = await createAgentSession({ title: "test" });
    expect(session.session_id).toBe("sess-1");
  });

  it("throws ContractError on non-2xx response", async () => {
    mockFetch(422, errorBody("invalid_request", "bad session"));
    await expect(createAgentSession()).rejects.toMatchObject({
      code: "invalid_request",
      message: "bad session",
    });
  });

  it("throws ContractError when fetch throws (network unreachable)", async () => {
    global.fetch = vi.fn().mockRejectedValueOnce(new TypeError("Network error"));
    await expect(createAgentSession()).rejects.toMatchObject({
      code: "provider_unavailable",
    });
  });
});

// ---------------------------------------------------------------------------
// getAgentSession
// ---------------------------------------------------------------------------

describe("getAgentSession", () => {
  afterEach(() => vi.restoreAllMocks());

  it("sends GET to /api/v1/agent/sessions/{session_id}", async () => {
    mockFetch(200, { session_id: "sess-1", status: "active", created_at: "t", updated_at: "t" });
    await getAgentSession("sess-1");
    expect(global.fetch).toHaveBeenCalledWith(
      `${BASE_URL}/api/v1/agent/sessions/sess-1`,
    );
  });

  it("throws ContractError on 404", async () => {
    mockFetch(422, errorBody("invalid_request", "not found"));
    await expect(getAgentSession("missing")).rejects.toBeInstanceOf(ContractError);
  });
});

// ---------------------------------------------------------------------------
// submitAgentTask
// ---------------------------------------------------------------------------

describe("submitAgentTask", () => {
  afterEach(() => vi.restoreAllMocks());

  it("sends POST /api/v1/agent/sessions/test-session/tasks with prompt in body", async () => {
    mockFetch(202, {
      task_id: "task-1",
      session_id: "test-session",
      status: "pending",
      prompt: "fix login",
      created_at: "t",
      updated_at: "t",
    });
    await submitAgentTask("test-session", { prompt: "fix login" });

    const [url, init] = (global.fetch as ReturnType<typeof vi.fn>).mock.calls[0] as [string, RequestInit];
    expect(url).toBe(`${BASE_URL}/api/v1/agent/sessions/test-session/tasks`);
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body as string)).toMatchObject({ prompt: "fix login" });
  });

  it("returns the task response", async () => {
    mockFetch(202, {
      task_id: "task-1",
      session_id: "test-session",
      status: "pending",
      prompt: "fix login",
      created_at: "t",
      updated_at: "t",
    });
    const task = await submitAgentTask("test-session", { prompt: "fix login" });
    expect(task.task_id).toBe("task-1");
    expect(task.status).toBe("pending");
  });

  it("maps ErrorResponse body into ContractError", async () => {
    mockFetch(422, errorBody("invalid_request", "empty prompt not allowed"));
    await expect(
      submitAgentTask("test-session", { prompt: "" }),
    ).rejects.toMatchObject({
      code: "invalid_request",
      message: "empty prompt not allowed",
    });
  });
});

// ---------------------------------------------------------------------------
// submitAgentApproval
// ---------------------------------------------------------------------------

describe("submitAgentApproval", () => {
  afterEach(() => vi.restoreAllMocks());

  it("sends POST to /api/v1/agent/sessions/{session_id}/approvals/{approval_id}", async () => {
    mockFetch(200, {
      approval_id: "appr-1",
      session_id: "sess-1",
      task_id: "task-1",
      action_type: "file.write",
      action_fingerprint: "sha256:abc",
      status: "approved",
      created_at: "t",
      updated_at: "t",
      expires_at: "t",
    });
    await submitAgentApproval("sess-1", "appr-1", { decision: "approved" });
    const [url] = (global.fetch as ReturnType<typeof vi.fn>).mock.calls[0] as [string];
    expect(url).toBe(`${BASE_URL}/api/v1/agent/sessions/sess-1/approvals/appr-1`);
  });

  it("sends the decision in the request body", async () => {
    mockFetch(200, {
      approval_id: "appr-1",
      session_id: "sess-1",
      task_id: "task-1",
      action_type: "cmd",
      action_fingerprint: "sha256:xyz",
      status: "rejected",
      created_at: "t",
      updated_at: "t",
      expires_at: "t",
    });
    await submitAgentApproval("sess-1", "appr-1", { decision: "rejected", rationale: "too risky" });
    const [, init] = (global.fetch as ReturnType<typeof vi.fn>).mock.calls[0] as [string, RequestInit];
    expect(JSON.parse(init.body as string)).toMatchObject({
      decision: "rejected",
      rationale: "too risky",
    });
  });
});

// ---------------------------------------------------------------------------
// getAgentEvents
// ---------------------------------------------------------------------------

describe("getAgentEvents", () => {
  afterEach(() => vi.restoreAllMocks());

  it("sends GET to the task-scoped events endpoint", async () => {
    mockFetch(200, { events: errorFixture, next_after_sequence: 6 });
    await getAgentEvents("sess-1", "task-1");
    const [url] = (global.fetch as ReturnType<typeof vi.fn>).mock.calls[0] as [string];
    expect(url).toBe(`${BASE_URL}/api/v1/agent/sessions/sess-1/tasks/task-1/events`);
  });

  it("appends after_sequence query param when provided", async () => {
    mockFetch(200, { events: [], next_after_sequence: null });
    await getAgentEvents("sess-1", "task-1", 3);
    const [url] = (global.fetch as ReturnType<typeof vi.fn>).mock.calls[0] as [string];
    expect(url).toBe(
      `${BASE_URL}/api/v1/agent/sessions/sess-1/tasks/task-1/events?after_sequence=3`,
    );
  });

  it("returns ordered events and next_after_sequence cursor", async () => {
    mockFetch(200, { events: errorFixture, next_after_sequence: 6 });
    const result = await getAgentEvents("sess-1", "task-1");
    expect(result.events).toHaveLength(6);
    expect(result.next_after_sequence).toBe(6);
    const sequences = result.events.map((e) => e.sequence);
    expect(sequences).toEqual([...sequences].sort((a, b) => a - b));
  });

  it("returns empty events array and null cursor for a task with no events", async () => {
    mockFetch(200, { events: [], next_after_sequence: null });
    const result = await getAgentEvents("sess-1", "task-1");
    expect(result.events).toEqual([]);
    expect(result.next_after_sequence).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// streamAgentEvents — SSE parsing with mocked ReadableStream
// ---------------------------------------------------------------------------

function buildReadableStream(chunks: string[]): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();
  let index = 0;
  return new ReadableStream<Uint8Array>({
    pull(controller) {
      if (index < chunks.length) {
        controller.enqueue(encoder.encode(chunks[index++]));
      } else {
        controller.close();
      }
    },
  });
}

describe("streamAgentEvents", () => {
  afterEach(() => vi.restoreAllMocks());

  it("calls the task-scoped SSE stream endpoint with after_sequence", async () => {
    global.fetch = vi.fn().mockResolvedValueOnce({
      ok: true,
      status: 200,
      body: buildReadableStream([]),
    } as unknown as Response);

    const handlers = { onEvent: vi.fn(), onError: vi.fn() };
    await streamAgentEvents("sess-1", "task-1", 0, handlers);

    const [url] = (global.fetch as ReturnType<typeof vi.fn>).mock.calls[0] as [string];
    expect(url).toContain("/api/v1/agent/sessions/sess-1/tasks/task-1/events/stream");
    expect(url).toContain("after_sequence=0");
  });

  it("parses approval_requested event frame and calls onEvent", async () => {
    const frame =
      `event: ${approvalRequestedEvent.event_type}\n` +
      `data: ${JSON.stringify(approvalRequestedEvent)}\n\n`;

    global.fetch = vi.fn().mockResolvedValueOnce({
      ok: true,
      status: 200,
      body: buildReadableStream([frame]),
    } as unknown as Response);

    const onEvent = vi.fn();
    await streamAgentEvents("sess-1", "task-1", 4, { onEvent, onError: vi.fn() });
    expect(onEvent).toHaveBeenCalledWith(
      expect.objectContaining({ event_type: "approval_requested", sequence: 5 }),
    );
  });

  it("parses completed event frame and calls onEvent", async () => {
    const frame =
      `event: completed\ndata: ${JSON.stringify(completedEvent)}\n\n`;

    global.fetch = vi.fn().mockResolvedValueOnce({
      ok: true,
      status: 200,
      body: buildReadableStream([frame]),
    } as unknown as Response);

    const onEvent = vi.fn();
    await streamAgentEvents("sess-1", "task-1", 5, { onEvent, onError: vi.fn() });
    expect(onEvent).toHaveBeenCalledWith(
      expect.objectContaining({ event_type: "completed" }),
    );
  });

  it("calls onError when fetch fails", async () => {
    global.fetch = vi.fn().mockRejectedValueOnce(new TypeError("Network error"));
    const onError = vi.fn();
    await streamAgentEvents("sess-1", "task-1", 0, { onEvent: vi.fn(), onError });
    expect(onError).toHaveBeenCalledWith(
      expect.objectContaining({ code: "provider_unavailable" }),
    );
  });

  it("calls onError when the endpoint returns non-2xx", async () => {
    global.fetch = vi.fn().mockResolvedValueOnce({
      ok: false,
      status: 422,
      body: null,
      json: async () => errorBody("invalid_request", "unknown task"),
    } as unknown as Response);

    const onError = vi.fn();
    await streamAgentEvents("sess-1", "task-1", 0, { onEvent: vi.fn(), onError });
    expect(onError).toHaveBeenCalledWith(
      expect.objectContaining({ code: "invalid_request" }),
    );
  });
});

// ---------------------------------------------------------------------------
// ContractError
// ---------------------------------------------------------------------------

describe("ContractError", () => {
  it("is an instance of Error", () => {
    const err = new ContractError("test_code", "test message");
    expect(err).toBeInstanceOf(Error);
    expect(err.name).toBe("ContractError");
    expect(err.code).toBe("test_code");
    expect(err.message).toBe("test message");
  });
});
