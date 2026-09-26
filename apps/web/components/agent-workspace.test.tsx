/**
 * Agent workspace component tests.
 *
 * These tests exercise the pure helper functions exported from the component
 * (formatEventType, extractApproval) without requiring DOM rendering or
 * @testing-library/react, keeping the test environment as "node".
 *
 * ContractError mapping from agent endpoints is verified in api.test.ts.
 */

import { describe, expect, it } from "vitest";
import { extractApproval, formatEventType } from "./agent-workspace";
import type { AgentEventResponse } from "../lib/api";
import {
  approvalRequestedEvent,
  assistantOutputEvent,
  toolCallEvent,
} from "../test/fixtures/agent-events";

// ---------------------------------------------------------------------------
// formatEventType
// ---------------------------------------------------------------------------

describe("formatEventType", () => {
  it("converts snake_case event type to Title Case words", () => {
    expect(formatEventType("assistant_output")).toBe("Assistant Output");
    expect(formatEventType("tool_call")).toBe("Tool Call");
    expect(formatEventType("approval_requested")).toBe("Approval Requested");
    expect(formatEventType("completed")).toBe("Completed");
    expect(formatEventType("error")).toBe("Error");
  });

  it("handles single-word event types", () => {
    expect(formatEventType("completed")).toBe("Completed");
    expect(formatEventType("error")).toBe("Error");
  });
});

// ---------------------------------------------------------------------------
// extractApproval
// ---------------------------------------------------------------------------

describe("extractApproval", () => {
  it("returns null for non-approval events", () => {
    expect(extractApproval(assistantOutputEvent)).toBeNull();
    expect(extractApproval(toolCallEvent)).toBeNull();
  });

  it("extracts approval metadata from an approval_requested event", () => {
    const appr = extractApproval(approvalRequestedEvent);
    expect(appr).not.toBeNull();
    expect(appr?.approval_id).toBe("appr-001");
    expect(appr?.tool_name).toBe("file.write");
    expect(appr?.risk).toBe("mutating");
    expect(appr?.fingerprint).toBe("sha256:abc123");
    expect(appr?.submitting).toBe(false);
    expect(appr?.error).toBeNull();
  });

  it("returns null when approval_requested event has no payload", () => {
    const event: AgentEventResponse = {
      ...approvalRequestedEvent,
      payload: null,
    };
    expect(extractApproval(event)).toBeNull();
  });

  it("returns null when approval_id is missing from payload", () => {
    const event: AgentEventResponse = {
      ...approvalRequestedEvent,
      payload: { tool_name: "file.write", risk: "mutating" },
    };
    expect(extractApproval(event)).toBeNull();
  });

  it("sets default tool_name and risk when missing from payload", () => {
    const event: AgentEventResponse = {
      ...approvalRequestedEvent,
      payload: { approval_id: "appr-999" },
    };
    const appr = extractApproval(event);
    expect(appr?.tool_name).toBe("unknown");
    expect(appr?.risk).toBe("mutating");
  });
});

// ---------------------------------------------------------------------------
// Fixture completeness (AC-6)
// ---------------------------------------------------------------------------

import {
  agentStartedEvent,
  completedEvent,
  completedFixture,
  errorEvent,
  errorFixture,
  toolResultEvent,
} from "../test/fixtures/agent-events";

describe("agent-events fixtures", () => {
  it("errorFixture has 6 events in ascending sequence order", () => {
    expect(errorFixture).toHaveLength(6);
    const sequences = errorFixture.map((e) => e.sequence);
    expect(sequences).toEqual([1, 2, 3, 4, 5, 6]);
  });

  it("completedFixture has 6 events ending with completed", () => {
    expect(completedFixture).toHaveLength(6);
    expect(completedFixture[completedFixture.length - 1].event_type).toBe(
      "completed",
    );
  });

  it("fixtures cover all required event types", () => {
    const types = new Set(errorFixture.map((e) => e.event_type));
    expect(types.has("assistant_output")).toBe(true);
    expect(types.has("tool_call")).toBe(true);
    expect(types.has("tool_result")).toBe(true);
    expect(types.has("approval_requested")).toBe(true);
    expect(types.has("error")).toBe(true);
  });

  it("approval_requested event has approval_id and tool_name in payload", () => {
    expect(approvalRequestedEvent.payload?.["approval_id"]).toBe("appr-001");
    expect(approvalRequestedEvent.payload?.["tool_name"]).toBe("file.write");
  });

  it("completed event has content payload", () => {
    expect(typeof completedEvent.payload?.["content"]).toBe("string");
    expect((completedEvent.payload?.["content"] as string).length).toBeGreaterThan(0);
  });

  it("each fixture event has the required fields", () => {
    const allEvents = [
      agentStartedEvent,
      assistantOutputEvent,
      toolCallEvent,
      toolResultEvent,
      approvalRequestedEvent,
      errorEvent,
      completedEvent,
    ];
    for (const event of allEvents) {
      expect(typeof event.event_id).toBe("string");
      expect(typeof event.session_id).toBe("string");
      expect(typeof event.task_id).toBe("string");
      expect(typeof event.sequence).toBe("number");
      expect(event.sequence).toBeGreaterThan(0);
      expect(typeof event.event_type).toBe("string");
      expect(typeof event.created_at).toBe("string");
    }
  });
});
