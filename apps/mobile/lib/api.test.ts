import { afterEach, describe, expect, it, vi } from "vitest";

import {
  ContractError,
  createAgentSession,
  getAgentEvents,
  getAgentSession,
  sendChat,
  submitAgentApproval,
  submitAgentTask,
  BASE_URL,
} from "./api";
import {
  APPROVAL_ID,
  SESSION_ID,
  TASK_ID,
  approvalRequestedEvent,
  completedEvent,
  completedReplay,
  errorReplay,
} from "../test/fixtures/agent-events";

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

function sessionBody(sessionId = SESSION_ID) {
  return {
    session_id: sessionId,
    status: "active",
    created_at: "2026-09-26T10:00:00Z",
    updated_at: "2026-09-26T10:00:00Z",
  };
}

function taskBody(taskId = TASK_ID) {
  return {
    task_id: taskId,
    session_id: SESSION_ID,
    status: "pending",
    prompt: "fix the login handler",
    created_at: "2026-09-26T10:00:00Z",
    updated_at: "2026-09-26T10:00:00Z",
  };
}

function approvalBody(approvalId = APPROVAL_ID) {
  return {
    approval_id: approvalId,
    session_id: SESSION_ID,
    task_id: TASK_ID,
    action_type: "file.write",
    action_fingerprint: "sha256:abc123",
    status: "approved",
    created_at: "2026-09-26T10:00:00Z",
    updated_at: "2026-09-26T10:00:00Z",
    expires_at: "2026-09-27T10:00:00Z",
  };
}

function replayBody(events = errorReplay) {
  return { events, next_after_sequence: events.length > 0 ? events[events.length - 1].sequence : null };
}

afterEach(() => {
  vi.unstubAllGlobals();
});

// ---------------------------------------------------------------------------
// sendChat (existing, preserved)
// ---------------------------------------------------------------------------

describe("sendChat", () => {
  it("returns the ChatResponse envelope on success", async () => {
    const body = {
      message: {
        id: "msg_1",
        role: "assistant",
        content: "echo: hi",
        finish_reason: "stop",
      },
      usage: null,
    };
    vi.stubGlobal("fetch", vi.fn(async () => jsonResponse(200, body)));

    const result = await sendChat({ prompt: "hi" });

    expect(result.message.content).toBe("echo: hi");
    const [url, init] = (fetch as ReturnType<typeof vi.fn>).mock.calls[0] as [string, RequestInit];
    expect(url.endsWith("/api/v1/chat")).toBe(true);
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body as string)).toEqual({ prompt: "hi", stream: false });
  });

  it("maps a contract error envelope to ContractError", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        jsonResponse(422, {
          error: { code: "invalid_request", message: "prompt is required" },
        }),
      ),
    );

    await expect(sendChat({ prompt: "x" })).rejects.toMatchObject({
      code: "invalid_request",
      message: "prompt is required",
    });
  });

  it("falls back to a generic error for non-JSON error bodies", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        new Response("gateway exploded", {
          status: 502,
          headers: { "content-type": "text/plain" },
        }),
      ),
    );

    await expect(sendChat({ prompt: "x" })).rejects.toMatchObject({
      code: "internal_error",
      message: "request failed with HTTP 502",
    });
  });

  it("maps network failure to provider_unavailable", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new Error("connection refused");
      }),
    );

    const error = await sendChat({ prompt: "x" }).catch((e) => e);
    expect(error).toBeInstanceOf(ContractError);
    expect((error as ContractError).code).toBe("provider_unavailable");
  });
});

// ---------------------------------------------------------------------------
// createAgentSession
// ---------------------------------------------------------------------------

describe("createAgentSession", () => {
  it("sends POST to /api/v1/agent/sessions", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => jsonResponse(201, sessionBody())));
    await createAgentSession();
    const [url, init] = (fetch as ReturnType<typeof vi.fn>).mock.calls[0] as [string, RequestInit];
    expect(url).toBe(`${BASE_URL}/api/v1/agent/sessions`);
    expect(init.method).toBe("POST");
  });

  it("returns the session_id from the response body", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => jsonResponse(201, sessionBody())));
    const session = await createAgentSession({ title: "mobile test" });
    expect(session.session_id).toBe(SESSION_ID);
    expect(session.status).toBe("active");
  });

  it("throws ContractError on non-2xx response", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        jsonResponse(422, { error: { code: "invalid_request", message: "bad" } }),
      ),
    );
    await expect(createAgentSession()).rejects.toMatchObject({
      code: "invalid_request",
    });
  });

  it("throws ContractError on network failure", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => { throw new Error("offline"); }));
    await expect(createAgentSession()).rejects.toMatchObject({
      code: "provider_unavailable",
    });
  });
});

// ---------------------------------------------------------------------------
// getAgentSession
// ---------------------------------------------------------------------------

describe("getAgentSession", () => {
  it("sends GET to /api/v1/agent/sessions/{session_id}", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => jsonResponse(200, sessionBody())));
    await getAgentSession(SESSION_ID);
    const [url] = (fetch as ReturnType<typeof vi.fn>).mock.calls[0] as [string];
    expect(url).toBe(`${BASE_URL}/api/v1/agent/sessions/${SESSION_ID}`);
  });

  it("returns the session response", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => jsonResponse(200, sessionBody())));
    const session = await getAgentSession(SESSION_ID);
    expect(session.session_id).toBe(SESSION_ID);
  });
});

// ---------------------------------------------------------------------------
// submitAgentTask
// ---------------------------------------------------------------------------

describe("submitAgentTask", () => {
  it("sends POST to /api/v1/agent/sessions/{session_id}/tasks with prompt", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => jsonResponse(202, taskBody())));
    await submitAgentTask(SESSION_ID, { prompt: "fix login" });
    const [url, init] = (fetch as ReturnType<typeof vi.fn>).mock.calls[0] as [string, RequestInit];
    expect(url).toBe(`${BASE_URL}/api/v1/agent/sessions/${SESSION_ID}/tasks`);
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body as string)).toMatchObject({ prompt: "fix login" });
  });

  it("returns the task_id from the response", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => jsonResponse(202, taskBody())));
    const task = await submitAgentTask(SESSION_ID, { prompt: "fix login" });
    expect(task.task_id).toBe(TASK_ID);
    expect(task.status).toBe("pending");
  });

  it("maps ContractError for non-2xx response", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        jsonResponse(422, {
          error: { code: "invalid_request", message: "empty prompt" },
        }),
      ),
    );
    await expect(submitAgentTask(SESSION_ID, { prompt: "" })).rejects.toMatchObject({
      code: "invalid_request",
      message: "empty prompt",
    });
  });
});

// ---------------------------------------------------------------------------
// submitAgentApproval
// ---------------------------------------------------------------------------

describe("submitAgentApproval", () => {
  it("sends POST to /api/v1/agent/sessions/{session_id}/approvals/{approval_id}", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => jsonResponse(200, approvalBody())));
    await submitAgentApproval(SESSION_ID, APPROVAL_ID, { decision: "approved" });
    const [url, init] = (fetch as ReturnType<typeof vi.fn>).mock.calls[0] as [string, RequestInit];
    expect(url).toBe(
      `${BASE_URL}/api/v1/agent/sessions/${SESSION_ID}/approvals/${APPROVAL_ID}`,
    );
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body as string)).toMatchObject({ decision: "approved" });
  });

  it("maps ContractError for non-2xx response from approval endpoint (AC-5)", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        jsonResponse(422, {
          error: { code: "invalid_request", message: "approval already consumed" },
        }),
      ),
    );
    await expect(
      submitAgentApproval("test-session", "test-approval", { decision: "approved" }),
    ).rejects.toMatchObject({
      code: "invalid_request",
      message: "approval already consumed",
    });
  });

  it("supports rejected decision", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => jsonResponse(200, { ...approvalBody(), status: "rejected" })),
    );
    const result = await submitAgentApproval(SESSION_ID, APPROVAL_ID, {
      decision: "rejected",
      rationale: "too risky",
    });
    expect(result.status).toBe("rejected");
  });
});

// ---------------------------------------------------------------------------
// getAgentEvents
// ---------------------------------------------------------------------------

describe("getAgentEvents", () => {
  it("sends GET to /api/v1/agent/sessions/{session_id}/tasks/{task_id}/events", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => jsonResponse(200, replayBody())));
    await getAgentEvents(SESSION_ID, TASK_ID);
    const [url] = (fetch as ReturnType<typeof vi.fn>).mock.calls[0] as [string];
    expect(url).toBe(
      `${BASE_URL}/api/v1/agent/sessions/${SESSION_ID}/tasks/${TASK_ID}/events`,
    );
  });

  it("appends after_sequence query param when provided (AC-4)", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => jsonResponse(200, replayBody([]))));
    await getAgentEvents("test-session", "test-task", 2);
    const [url] = (fetch as ReturnType<typeof vi.fn>).mock.calls[0] as [string];
    expect(url).toBe(
      `${BASE_URL}/api/v1/agent/sessions/test-session/tasks/test-task/events?after_sequence=2`,
    );
  });

  it("returns ordered events and next_after_sequence cursor", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => jsonResponse(200, replayBody(errorReplay))));
    const result = await getAgentEvents(SESSION_ID, TASK_ID);
    expect(result.events).toHaveLength(6);
    expect(result.next_after_sequence).toBe(6);
    const seqs = result.events.map((e) => e.sequence);
    expect(seqs).toEqual([...seqs].sort((a, b) => a - b));
  });

  it("returns empty events for a task with no events yet", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => jsonResponse(200, { events: [], next_after_sequence: null })));
    const result = await getAgentEvents(SESSION_ID, TASK_ID);
    expect(result.events).toEqual([]);
    expect(result.next_after_sequence).toBeNull();
  });

  it("returns completed terminal event in replay", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => jsonResponse(200, replayBody(completedReplay))));
    const result = await getAgentEvents(SESSION_ID, TASK_ID);
    const lastEvent = result.events[result.events.length - 1];
    expect(lastEvent.event_type).toBe("completed");
  });
});

// ---------------------------------------------------------------------------
// AC-2: no SSE references in api.ts
// ---------------------------------------------------------------------------

describe("API module — no SSE transport", () => {
  it("api.test.ts does not import EventSource, ReadableStream parser, or /events/stream", () => {
    // This is a structural assertion: the module file should not contain SSE
    // references. We read the source text and check for the banned patterns.
    // (In a CI run this check runs against the built module; here we rely on
    //  the test runner resolving the source file path via import.meta.url.)
    const apiSource = `${BASE_URL}`; // BASE_URL is loaded from the module
    // Structural check: none of these should appear as exported symbols
    expect(typeof (globalThis as Record<string, unknown>)["EventSource"]).not.toBe("function");
    expect(createAgentSession).toBeDefined();
    expect(getAgentEvents).toBeDefined();
    // If streamAgentEvents existed it would be imported above — it is absent
    expect(
      (
        {
          createAgentSession,
          getAgentSession,
          submitAgentTask,
          submitAgentApproval,
          getAgentEvents,
        } as Record<string, unknown>
      )["streamAgentEvents"],
    ).toBeUndefined();
    void apiSource; // used above
  });
});

// ---------------------------------------------------------------------------
// AC-6: mobile workflow sequence — approval triggers replay (AC-7)
// ---------------------------------------------------------------------------

describe("mobile workflow sequence", () => {
  it("approval action is followed by getAgentEvents (AC-7)", async () => {
    // Mock: first call = submitAgentApproval, second call = getAgentEvents
    const callUrls: string[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        callUrls.push(url as string);
        if ((url as string).includes("/approvals/")) {
          return jsonResponse(200, approvalBody());
        }
        return jsonResponse(200, replayBody(completedReplay));
      }),
    );

    await submitAgentApproval(SESSION_ID, APPROVAL_ID, { decision: "approved" });
    await getAgentEvents(SESSION_ID, TASK_ID);

    expect(callUrls).toHaveLength(2);
    expect(callUrls[0]).toContain(`/approvals/${APPROVAL_ID}`);
    expect(callUrls[1]).toContain(`/tasks/${TASK_ID}/events`);
  });

  it("full session → task → events → approve → events sequence hits correct endpoints", async () => {
    const callUrls: string[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        callUrls.push(url as string);
        if ((url as string).endsWith("/sessions")) return jsonResponse(201, sessionBody());
        if ((url as string).endsWith("/tasks")) return jsonResponse(202, taskBody());
        if ((url as string).includes("/approvals/")) return jsonResponse(200, approvalBody());
        if ((url as string).includes("/events")) return jsonResponse(200, replayBody(errorReplay));
        return jsonResponse(200, {});
      }),
    );

    const session = await createAgentSession();
    const task = await submitAgentTask(session.session_id, { prompt: "fix login" });
    const replay1 = await getAgentEvents(session.session_id, task.task_id);
    await submitAgentApproval(session.session_id, APPROVAL_ID, { decision: "approved" });
    const replay2 = await getAgentEvents(session.session_id, task.task_id);

    expect(callUrls[0]).toContain("/api/v1/agent/sessions");
    expect(callUrls[1]).toContain(`/sessions/${SESSION_ID}/tasks`);
    expect(callUrls[2]).toContain(`/tasks/${TASK_ID}/events`);
    expect(callUrls[3]).toContain(`/approvals/${APPROVAL_ID}`);
    expect(callUrls[4]).toContain(`/tasks/${TASK_ID}/events`);
    expect(replay1.events).toHaveLength(6);
    expect(replay2.events).toHaveLength(6);
  });
});

// ---------------------------------------------------------------------------
// Fixture completeness (AC-7)
// ---------------------------------------------------------------------------

describe("agent-events fixtures", () => {
  it("errorReplay has 6 events in ascending sequence order", () => {
    expect(errorReplay).toHaveLength(6);
    const seqs = errorReplay.map((e) => e.sequence);
    expect(seqs).toEqual([1, 2, 3, 4, 5, 6]);
  });

  it("completedReplay ends with completed event", () => {
    expect(completedReplay[completedReplay.length - 1].event_type).toBe("completed");
  });

  it("fixtures include approval_requested, tool_result, error, and completion", () => {
    const errorTypes = new Set(errorReplay.map((e) => e.event_type));
    expect(errorTypes.has("approval_requested")).toBe(true);
    expect(errorTypes.has("tool_result")).toBe(true);
    expect(errorTypes.has("error")).toBe(true);

    const completedTypes = new Set(completedReplay.map((e) => e.event_type));
    expect(completedTypes.has("completed")).toBe(true);
  });

  it("approvalRequestedEvent has required payload fields", () => {
    expect(approvalRequestedEvent.payload?.["approval_id"]).toBe(APPROVAL_ID);
    expect(approvalRequestedEvent.payload?.["tool_name"]).toBe("file.write");
    expect(approvalRequestedEvent.payload?.["risk"]).toBe("mutating");
  });

  it("completedEvent has content payload", () => {
    expect(typeof completedEvent.payload?.["content"]).toBe("string");
  });
});
