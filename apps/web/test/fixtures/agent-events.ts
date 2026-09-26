/**
 * Deterministic AgentEvent fixtures for web tests.
 *
 * Covers sequences 1–6 with all mandatory event types:
 *   agent_started, assistant_output, tool_call, tool_result,
 *   approval_requested, error (and an alternate completed set).
 */

import type { AgentEventResponse } from "../../lib/api";

export const SESSION_ID = "test-session";
export const TASK_ID = "test-task";

/** Sequence 1: agent started */
export const agentStartedEvent: AgentEventResponse = {
  event_id: "evt-001",
  session_id: SESSION_ID,
  task_id: TASK_ID,
  sequence: 1,
  event_type: "agent_started",
  payload: { max_iterations: 20, max_tool_calls: 50, task_timeout_seconds: 300 },
  created_at: "2026-09-26T10:00:01Z",
};

/** Sequence 2: assistant output */
export const assistantOutputEvent: AgentEventResponse = {
  event_id: "evt-002",
  session_id: SESSION_ID,
  task_id: TASK_ID,
  sequence: 2,
  event_type: "assistant_output",
  payload: { content: "I will start by reading the login handler." },
  created_at: "2026-09-26T10:00:02Z",
};

/** Sequence 3: tool call */
export const toolCallEvent: AgentEventResponse = {
  event_id: "evt-003",
  session_id: SESSION_ID,
  task_id: TASK_ID,
  sequence: 3,
  event_type: "tool_call",
  payload: {
    tool_name: "repo.read",
    tool_input: { path: "src/auth/login.py" },
    sequence: 1,
  },
  created_at: "2026-09-26T10:00:03Z",
};

/** Sequence 4: tool result */
export const toolResultEvent: AgentEventResponse = {
  event_id: "evt-004",
  session_id: SESSION_ID,
  task_id: TASK_ID,
  sequence: 4,
  event_type: "tool_result",
  payload: {
    tool_name: "repo.read",
    output: { content: "def login(request): ..." },
    sequence: 1,
  },
  created_at: "2026-09-26T10:00:04Z",
};

/** Sequence 5: approval requested */
export const approvalRequestedEvent: AgentEventResponse = {
  event_id: "evt-005",
  session_id: SESSION_ID,
  task_id: TASK_ID,
  sequence: 5,
  event_type: "approval_requested",
  payload: {
    approval_id: "appr-001",
    tool_name: "file.write",
    risk: "mutating",
    fingerprint: "sha256:abc123",
  },
  created_at: "2026-09-26T10:00:05Z",
};

/** Sequence 6a: terminal error */
export const errorEvent: AgentEventResponse = {
  event_id: "evt-006",
  session_id: SESSION_ID,
  task_id: TASK_ID,
  sequence: 6,
  event_type: "error",
  payload: {
    error_type: "provider_unavailable",
    message: "Provider timeout after 30s",
  },
  created_at: "2026-09-26T10:00:06Z",
};

/** Sequence 6b: terminal completion (alternate fixture) */
export const completedEvent: AgentEventResponse = {
  event_id: "evt-007",
  session_id: SESSION_ID,
  task_id: TASK_ID,
  sequence: 6,
  event_type: "completed",
  payload: {
    content: "Refactoring applied successfully.",
    iterations: 3,
    tool_calls: 1,
  },
  created_at: "2026-09-26T10:00:06Z",
};

/** Ordered sequence ending with error (sequences 1–5 + error). */
export const errorFixture: AgentEventResponse[] = [
  agentStartedEvent,
  assistantOutputEvent,
  toolCallEvent,
  toolResultEvent,
  approvalRequestedEvent,
  errorEvent,
];

/** Ordered sequence ending with completion (sequences 1–5 + completed). */
export const completedFixture: AgentEventResponse[] = [
  agentStartedEvent,
  assistantOutputEvent,
  toolCallEvent,
  toolResultEvent,
  approvalRequestedEvent,
  completedEvent,
];
