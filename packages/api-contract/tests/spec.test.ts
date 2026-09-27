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

describe("agent contract", () => {
  const paths = spec.paths as Record<string, any>;
  const schemas = (spec.components as any).schemas as Record<string, any>;

  it("exposes the v1 agent control-plane paths", () => {
    const expected = [
      "/api/v1/agent/sessions",
      "/api/v1/agent/sessions/{session_id}",
      "/api/v1/agent/sessions/{session_id}/tasks",
      "/api/v1/agent/sessions/{session_id}/events",
      "/api/v1/agent/sessions/{session_id}/events/stream",
      "/api/v1/agent/sessions/{session_id}/approvals",
      "/api/v1/agent/sessions/{session_id}/approvals/{approval_id}",
      "/api/v1/agent/sessions/{session_id}/state",
      "/api/v1/agent/sessions/{session_id}/tasks/{task_id}/events",
      "/api/v1/agent/sessions/{session_id}/tasks/{task_id}/events/stream",
    ];
    for (const path of expected) {
      expect(paths, `missing agent path ${path}`).toHaveProperty(path);
    }
  });

  it("creates sessions with 201 and accepts tasks with 202", () => {
    expect(paths["/api/v1/agent/sessions"].post.responses).toHaveProperty("201");
    expect(paths["/api/v1/agent/sessions/{session_id}/tasks"].post.responses).toHaveProperty("202");
  });

  it("serves the agent event streams as SSE", () => {
    for (const stream of [
      "/api/v1/agent/sessions/{session_id}/events/stream",
      "/api/v1/agent/sessions/{session_id}/tasks/{task_id}/events/stream",
    ]) {
      const ok = paths[stream].get.responses["200"];
      expect(Object.keys(ok.content), stream).toContain("text/event-stream");
    }
  });

  it("pins the full agent event type registry", () => {
    const eventType = schemas.AgentEventResponse.properties.event_type;
    expect([...eventType.enum].sort()).toEqual(
      [
        "agent_started",
        "approval_consumed",
        "approval_decided",
        "approval_requested",
        "assistant_output",
        "completed",
        "error",
        "task_accepted",
        "tool_call",
        "tool_result",
      ].sort(),
    );
  });

  it("pins the task and approval status registries", () => {
    expect([...schemas.AgentTaskResponse.properties.status.enum].sort()).toEqual(
      [
        "blocked",
        "cancelled",
        "failed",
        "pending",
        "running",
        "succeeded",
        "timed_out",
      ].sort(),
    );
    expect(
      [...schemas.ApprovalRequestResponse.properties.status.enum].sort(),
    ).toEqual(["approved", "consumed", "expired", "pending", "rejected"].sort());
  });
});
