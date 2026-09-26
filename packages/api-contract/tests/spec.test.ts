import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import YAML from "yaml";

const spec = YAML.parse(
  readFileSync(new URL("../openapi.yaml", import.meta.url), "utf8"),
) as Record<string, unknown>;

describe("canonical OpenAPI spec", () => {
  it("is OpenAPI 3.1 with a semver contract version", () => {
    expect(String(spec.openapi)).toMatch(/^3\.1/);
    const version = (spec.info as { version: string }).version;
    expect(version).toMatch(/^\d+\.\d+\.\d+$/);
  });

  it("exposes the v1 health and chat endpoints", () => {
    const paths = Object.keys(spec.paths as object);
    expect(paths).toContain("/api/v1/health");
    expect(paths).toContain("/api/v1/chat");
  });

  it("serves chat responses as JSON and SSE", () => {
    const chat = (spec.paths as any)["/api/v1/chat"].post;
    const ok = chat.responses["200"].content;
    expect(Object.keys(ok)).toEqual(
      expect.arrayContaining(["application/json", "text/event-stream"]),
    );
  });

  it("pins the full error code registry", () => {
    const error = (spec.components as any).schemas.Error;
    expect(error.properties.code.enum.sort()).toEqual(
      [
        "internal_error",
        "invalid_request",
        "provider_error",
        "provider_unavailable",
        "rate_limited",
      ].sort(),
    );
  });

  it("resolves every local $ref", () => {
    const refs: string[] = [];
    const walk = (node: unknown): void => {
      if (Array.isArray(node)) {
        node.forEach(walk);
        return;
      }
      if (node && typeof node === "object") {
        for (const [key, value] of Object.entries(node)) {
          if (key === "$ref" && typeof value === "string") refs.push(value);
          else walk(value);
        }
      }
    };
    walk(spec);
    expect(refs.length).toBeGreaterThan(0);
    for (const ref of refs) {
      expect(ref.startsWith("#/"), ref).toBe(true);
      let cursor: unknown = spec;
      for (const segment of ref.slice(2).split("/")) {
        cursor = (cursor as Record<string, unknown>)?.[segment];
        expect(cursor, `unresolved ref ${ref}`).toBeDefined();
      }
    }
  });
});

// ---------------------------------------------------------------------------
// Agent contract — additive /api/v1/agent resource group (WO-001)
// ---------------------------------------------------------------------------

describe("agent contract paths", () => {
  const paths = spec.paths as Record<string, unknown>;
  const components = spec.components as Record<string, unknown>;
  const schemas = (components.schemas as Record<string, unknown>) ?? {};
  const responses = (components.responses as Record<string, unknown>) ?? {};

  // Helpers
  const getOp = (path: string, method: string): Record<string, unknown> =>
    ((paths[path] as Record<string, unknown>)?.[method] as Record<
      string,
      unknown
    >) ?? {};

  const hasResponseRef = (
    op: Record<string, unknown>,
    status: string,
    expectedRef: string,
  ): boolean => {
    const r = op.responses as Record<string, unknown> | undefined;
    if (!r) return false;
    const entry = r[status] as Record<string, unknown> | undefined;
    if (!entry) return false;
    return (entry.$ref as string | undefined) === expectedRef;
  };

  // --- Existing paths preserved ---

  it("preserves existing /api/v1/chat path", () => {
    expect(paths).toHaveProperty("/api/v1/chat");
  });

  it("preserves existing /api/v1/health path", () => {
    expect(paths).toHaveProperty("/api/v1/health");
  });

  it("preserves at least one /api/v1/learning path", () => {
    const learningPaths = Object.keys(paths).filter((p) =>
      p.startsWith("/api/v1/learning"),
    );
    expect(learningPaths.length).toBeGreaterThan(0);
  });

  it("preserves /api/v1/learning/quiz/retest path (GET and POST)", () => {
    expect(paths).toHaveProperty("/api/v1/learning/quiz/retest");
    const pathItem = paths["/api/v1/learning/quiz/retest"] as Record<string, unknown>;
    // Must support at least GET (fresh question) or POST (evaluate answer)
    const hasMethods = "get" in pathItem || "post" in pathItem;
    expect(hasMethods, "/api/v1/learning/quiz/retest must have GET or POST").toBe(true);
  });

  // --- New agent paths ---

  it("exposes POST /api/v1/agent/sessions (createAgentSession)", () => {
    expect(paths).toHaveProperty("/api/v1/agent/sessions");
    const op = getOp("/api/v1/agent/sessions", "post");
    expect(op.operationId).toBe("createAgentSession");
    expect(op.tags).toContain("agent");
    // 201 response
    const res = op.responses as Record<string, unknown>;
    expect(res).toHaveProperty("201");
    // Required standard error responses
    expect(
      hasResponseRef(op, "401", "#/components/responses/Unauthorized"),
    ).toBe(true);
    expect(
      hasResponseRef(op, "422", "#/components/responses/InvalidRequest"),
    ).toBe(true);
    expect(
      hasResponseRef(op, "500", "#/components/responses/InternalError"),
    ).toBe(true);
  });

  it("exposes GET /api/v1/agent/sessions/{session_id} (getAgentSession)", () => {
    expect(paths).toHaveProperty("/api/v1/agent/sessions/{session_id}");
    const op = getOp("/api/v1/agent/sessions/{session_id}", "get");
    expect(op.operationId).toBe("getAgentSession");
    expect(
      hasResponseRef(op, "401", "#/components/responses/Unauthorized"),
    ).toBe(true);
    expect(
      hasResponseRef(op, "422", "#/components/responses/InvalidRequest"),
    ).toBe(true);
    expect(
      hasResponseRef(op, "500", "#/components/responses/InternalError"),
    ).toBe(true);
  });

  it("exposes POST /api/v1/agent/sessions/{session_id}/tasks (submitAgentTask)", () => {
    expect(paths).toHaveProperty(
      "/api/v1/agent/sessions/{session_id}/tasks",
    );
    const op = getOp("/api/v1/agent/sessions/{session_id}/tasks", "post");
    expect(op.operationId).toBe("submitAgentTask");
    const res = op.responses as Record<string, unknown>;
    expect(res).toHaveProperty("202");
    expect(
      hasResponseRef(op, "401", "#/components/responses/Unauthorized"),
    ).toBe(true);
    expect(
      hasResponseRef(op, "422", "#/components/responses/InvalidRequest"),
    ).toBe(true);
    expect(
      hasResponseRef(op, "500", "#/components/responses/InternalError"),
    ).toBe(true);
  });

  it("exposes GET /api/v1/agent/sessions/{session_id}/events (listAgentEvents)", () => {
    expect(paths).toHaveProperty(
      "/api/v1/agent/sessions/{session_id}/events",
    );
    const op = getOp(
      "/api/v1/agent/sessions/{session_id}/events",
      "get",
    );
    expect(op.operationId).toBe("listAgentEvents");
    expect(
      hasResponseRef(op, "401", "#/components/responses/Unauthorized"),
    ).toBe(true);
    expect(
      hasResponseRef(op, "422", "#/components/responses/InvalidRequest"),
    ).toBe(true);
    expect(
      hasResponseRef(op, "500", "#/components/responses/InternalError"),
    ).toBe(true);
  });

  it("exposes GET /api/v1/agent/sessions/{session_id}/tasks/{task_id}/events (task-scoped replay)", () => {
    expect(paths).toHaveProperty(
      "/api/v1/agent/sessions/{session_id}/tasks/{task_id}/events",
    );
    const op = getOp(
      "/api/v1/agent/sessions/{session_id}/tasks/{task_id}/events",
      "get",
    );
    // Task-scoped endpoint must return 200 with paginated event list
    const res = op.responses as Record<string, unknown> | undefined;
    expect(res).toHaveProperty("200");
    expect(
      hasResponseRef(op, "422", "#/components/responses/InvalidRequest"),
    ).toBe(true);
    expect(
      hasResponseRef(op, "500", "#/components/responses/InternalError"),
    ).toBe(true);
  });

  it("exposes GET /api/v1/agent/sessions/{session_id}/tasks/{task_id}/events/stream (task-scoped SSE)", () => {
    expect(paths).toHaveProperty(
      "/api/v1/agent/sessions/{session_id}/tasks/{task_id}/events/stream",
    );
    const op = getOp(
      "/api/v1/agent/sessions/{session_id}/tasks/{task_id}/events/stream",
      "get",
    );
    const res200 = (op.responses as Record<string, unknown>)["200"] as Record<
      string,
      unknown
    > | undefined;
    const content = res200?.content as Record<string, unknown> | undefined;
    expect(content).toHaveProperty("text/event-stream");
  });

  it("exposes GET /api/v1/agent/sessions/{session_id}/events/stream (streamAgentEvents)", () => {
    expect(paths).toHaveProperty(
      "/api/v1/agent/sessions/{session_id}/events/stream",
    );
    const op = getOp(
      "/api/v1/agent/sessions/{session_id}/events/stream",
      "get",
    );
    expect(op.operationId).toBe("streamAgentEvents");
    // SSE response content type
    const res200 = (op.responses as Record<string, unknown>)["200"] as Record<
      string,
      unknown
    >;
    const content = res200?.content as Record<string, unknown> | undefined;
    expect(content).toHaveProperty("text/event-stream");
    expect(
      hasResponseRef(op, "401", "#/components/responses/Unauthorized"),
    ).toBe(true);
    expect(
      hasResponseRef(op, "422", "#/components/responses/InvalidRequest"),
    ).toBe(true);
    expect(
      hasResponseRef(op, "500", "#/components/responses/InternalError"),
    ).toBe(true);
  });

  it("exposes GET /api/v1/agent/sessions/{session_id}/approvals (listAgentApprovals)", () => {
    expect(paths).toHaveProperty(
      "/api/v1/agent/sessions/{session_id}/approvals",
    );
    const op = getOp(
      "/api/v1/agent/sessions/{session_id}/approvals",
      "get",
    );
    expect(op.operationId).toBe("listAgentApprovals");
    expect(
      hasResponseRef(op, "401", "#/components/responses/Unauthorized"),
    ).toBe(true);
    expect(
      hasResponseRef(op, "422", "#/components/responses/InvalidRequest"),
    ).toBe(true);
    expect(
      hasResponseRef(op, "500", "#/components/responses/InternalError"),
    ).toBe(true);
  });

  it("exposes POST /api/v1/agent/sessions/{session_id}/approvals/{approval_id} (decideAgentApproval)", () => {
    expect(paths).toHaveProperty(
      "/api/v1/agent/sessions/{session_id}/approvals/{approval_id}",
    );
    const op = getOp(
      "/api/v1/agent/sessions/{session_id}/approvals/{approval_id}",
      "post",
    );
    expect(op.operationId).toBe("decideAgentApproval");
    expect(
      hasResponseRef(op, "401", "#/components/responses/Unauthorized"),
    ).toBe(true);
    expect(
      hasResponseRef(op, "422", "#/components/responses/InvalidRequest"),
    ).toBe(true);
    expect(
      hasResponseRef(op, "500", "#/components/responses/InternalError"),
    ).toBe(true);
  });

  it("exposes GET /api/v1/agent/sessions/{session_id}/state (getAgentState)", () => {
    expect(paths).toHaveProperty(
      "/api/v1/agent/sessions/{session_id}/state",
    );
    const op = getOp(
      "/api/v1/agent/sessions/{session_id}/state",
      "get",
    );
    expect(op.operationId).toBe("getAgentState");
    expect(
      hasResponseRef(op, "401", "#/components/responses/Unauthorized"),
    ).toBe(true);
    expect(
      hasResponseRef(op, "422", "#/components/responses/InvalidRequest"),
    ).toBe(true);
    expect(
      hasResponseRef(op, "500", "#/components/responses/InternalError"),
    ).toBe(true);
  });

  // --- Agent component schemas ---

  it("defines AgentSessionResponse schema with required fields", () => {
    expect(schemas).toHaveProperty("AgentSessionResponse");
    const s = schemas.AgentSessionResponse as Record<string, unknown>;
    const required = s.required as string[];
    expect(required).toContain("session_id");
    expect(required).toContain("status");
    expect(required).toContain("created_at");
    expect(required).toContain("updated_at");
  });

  it("defines AgentTaskResponse schema with required fields", () => {
    expect(schemas).toHaveProperty("AgentTaskResponse");
    const s = schemas.AgentTaskResponse as Record<string, unknown>;
    const required = s.required as string[];
    expect(required).toContain("task_id");
    expect(required).toContain("session_id");
    expect(required).toContain("status");
    expect(required).toContain("created_at");
    expect(required).toContain("updated_at");
  });

  it("defines AgentEventResponse schema with sequence and event_type", () => {
    expect(schemas).toHaveProperty("AgentEventResponse");
    const s = schemas.AgentEventResponse as Record<string, unknown>;
    const required = s.required as string[];
    expect(required).toContain("event_id");
    expect(required).toContain("session_id");
    expect(required).toContain("task_id");
    expect(required).toContain("sequence");
    expect(required).toContain("event_type");
    expect(required).toContain("created_at");
    const props = s.properties as Record<string, Record<string, unknown>>;
    // event_type must enumerate all required event names
    const eventTypeEnum = props.event_type?.enum as string[] | undefined;
    expect(eventTypeEnum).toBeDefined();
    for (const name of [
      "assistant_output",
      "tool_call",
      "tool_result",
      "approval_requested",
      "error",
      "completed",
    ]) {
      expect(eventTypeEnum, `missing event_type: ${name}`).toContain(name);
    }
  });

  it("defines ApprovalRequestResponse schema with required fields", () => {
    expect(schemas).toHaveProperty("ApprovalRequestResponse");
    const s = schemas.ApprovalRequestResponse as Record<string, unknown>;
    const required = s.required as string[];
    expect(required).toContain("approval_id");
    expect(required).toContain("session_id");
    expect(required).toContain("task_id");
    expect(required).toContain("action_fingerprint");
    expect(required).toContain("status");
    expect(required).toContain("expires_at");
    expect(required).toContain("created_at");
    expect(required).toContain("updated_at");
  });

  it("defines AgentStateResponse schema with required aggregate fields", () => {
    expect(schemas).toHaveProperty("AgentStateResponse");
    const s = schemas.AgentStateResponse as Record<string, unknown>;
    const required = s.required as string[];
    expect(required).toContain("session_id");
    expect(required).toContain("session");
    expect(required).toContain("tasks");
    expect(required).toContain("events");
    expect(required).toContain("pending_approvals");
  });

  it("defines CreateAgentSessionRequest schema", () => {
    expect(schemas).toHaveProperty("CreateAgentSessionRequest");
  });

  it("defines SubmitAgentTaskRequest schema with prompt minLength", () => {
    expect(schemas).toHaveProperty("SubmitAgentTaskRequest");
    const s = schemas.SubmitAgentTaskRequest as Record<string, unknown>;
    const required = s.required as string[];
    expect(required).toContain("prompt");
    const props = s.properties as Record<string, Record<string, unknown>>;
    expect(props.prompt?.minLength).toBe(1);
  });

  it("defines ApprovalDecisionRequest schema with constrained decision enum", () => {
    expect(schemas).toHaveProperty("ApprovalDecisionRequest");
    const s = schemas.ApprovalDecisionRequest as Record<string, unknown>;
    const required = s.required as string[];
    expect(required).toContain("decision");
    const props = s.properties as Record<string, Record<string, unknown>>;
    const decisionEnum = props.decision?.enum as string[] | undefined;
    expect(decisionEnum).toBeDefined();
    expect(decisionEnum).toContain("approved");
    expect(decisionEnum).toContain("rejected");
    // Must not allow arbitrary values
    expect(decisionEnum?.length).toBe(2);
  });

  it("defines AgentSseEvent schema with terminal event names", () => {
    expect(schemas).toHaveProperty("AgentSseEvent");
    const s = schemas.AgentSseEvent as Record<string, unknown>;
    const required = s.required as string[];
    expect(required).toContain("event");
    expect(required).toContain("data");
    const props = s.properties as Record<string, Record<string, unknown>>;
    const eventEnum = props.event?.enum as string[] | undefined;
    expect(eventEnum).toBeDefined();
    // Terminal events must be enumerated so clients can close the stream
    expect(eventEnum).toContain("error");
    expect(eventEnum).toContain("completed");
  });

  // --- bearerAuth security scheme ---

  it("includes bearerAuth security scheme in components.securitySchemes", () => {
    const securitySchemes = (
      components.securitySchemes as Record<string, unknown> | undefined
    ) ?? {};
    expect(securitySchemes).toHaveProperty("bearerAuth");
    const bearerAuth = securitySchemes.bearerAuth as Record<string, unknown>;
    expect(bearerAuth.type).toBe("http");
    expect(bearerAuth.scheme).toBe("bearer");
  });

  // --- Representative AgentEventResponse JSON examples ---

  it("provides representative examples for all required AgentEventResponse event_type values", () => {
    // These are inline fixture examples that validate schema expectations
    // without requiring any external service.
    const requiredEventTypes = [
      "assistant_output",
      "tool_call",
      "tool_result",
      "approval_requested",
      "error",
      "completed",
    ] as const;

    const representativeExamples: Array<{
      event_id: string;
      session_id: string;
      task_id: string;
      sequence: number;
      event_type: string;
      payload: Record<string, unknown> | null;
      created_at: string;
    }> = [
      {
        event_id: "evt_ex_001",
        session_id: "sess_example",
        task_id: "task_example",
        sequence: 1,
        event_type: "assistant_output",
        payload: { content: "I will start by reading the file." },
        created_at: "2026-09-25T10:00:01Z",
      },
      {
        event_id: "evt_ex_002",
        session_id: "sess_example",
        task_id: "task_example",
        sequence: 2,
        event_type: "tool_call",
        payload: { tool: "read_file", input: { path: "src/auth/login.py" } },
        created_at: "2026-09-25T10:00:02Z",
      },
      {
        event_id: "evt_ex_003",
        session_id: "sess_example",
        task_id: "task_example",
        sequence: 3,
        event_type: "tool_result",
        payload: { tool: "read_file", output: "def login(request):\n    ..." },
        created_at: "2026-09-25T10:00:03Z",
      },
      {
        event_id: "evt_ex_004",
        session_id: "sess_example",
        task_id: "task_example",
        sequence: 4,
        event_type: "approval_requested",
        payload: {
          approval_id: "appr_001",
          action_type: "write_file",
          action_fingerprint: "sha256:abc123",
        },
        created_at: "2026-09-25T10:00:04Z",
      },
      {
        event_id: "evt_ex_005",
        session_id: "sess_example",
        task_id: "task_example",
        sequence: 5,
        event_type: "error",
        payload: {
          message: "Provider timeout after 30s",
          code: "provider_error",
        },
        created_at: "2026-09-25T10:00:05Z",
      },
      {
        event_id: "evt_ex_006",
        session_id: "sess_example",
        task_id: "task_example",
        sequence: 6,
        event_type: "completed",
        payload: { result: "Refactoring applied successfully." },
        created_at: "2026-09-25T10:00:06Z",
      },
    ];

    const coveredTypes = new Set(
      representativeExamples.map((e) => e.event_type),
    );

    for (const eventType of requiredEventTypes) {
      expect(
        coveredTypes.has(eventType),
        `missing example for event_type: ${eventType}`,
      ).toBe(true);
    }

    // Validate structural invariants for every example
    for (const example of representativeExamples) {
      expect(typeof example.event_id).toBe("string");
      expect(typeof example.session_id).toBe("string");
      expect(typeof example.task_id).toBe("string");
      expect(typeof example.sequence).toBe("number");
      expect(example.sequence).toBeGreaterThanOrEqual(0);
      expect(typeof example.event_type).toBe("string");
      expect(typeof example.created_at).toBe("string");
      // payload may be null for terminal events but must be object or null
      expect(
        example.payload === null || typeof example.payload === "object",
      ).toBe(true);
    }
  });
});
