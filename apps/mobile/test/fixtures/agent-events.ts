/**
 * Deterministic AgentEvent replay fixtures for mobile tests.
 *
 * Covers sequences 1–6 with all required event types:
 *   agent_started, assistant_output, tool_call, tool_result,
 *   approval_requested, error (and alternate completed set).
 */

import type { AgentEventResponse } from "../../lib/api";

export const SESSION_ID = "test-session";
export const TASK_ID = "test-task";
export const APPROVAL_ID = "appr-001";

export const agentStartedEvent: AgentEventResponse = {
  event_id: "evt-001",
  session_id: SESSION_ID,
  task_id: TASK_ID,
  sequence: 1,
  event_type: "agent_started",
  payload: { max_iterations: 20, max_tool_calls: 50, task_timeout_seconds: 300 },
  created_at: "2026-09-26T10:00:01Z",
};

export const assistantOutputEvent: AgentEventResponse = {
  event_id: "evt-002",
  session_id: SESSION_ID,
  task_id: TASK_ID,
  sequence: 2,
  event_type: "assistant_output",
  payload: { content: "I will start by reading the auth module." },
  created_at: "2026-09-26T10:00:02Z",
};

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

export const approvalRequestedEvent: AgentEventResponse = {
  event_id: "evt-005",
  session_id: SESSION_ID,
  task_id: TASK_ID,
  sequence: 5,
  event_type: "approval_requested",
  payload: {
    approval_id: APPROVAL_ID,
    tool_name: "file.write",
    risk: "mutating",
    fingerprint: "sha256:abc123",
  },
  created_at: "2026-09-26T10:00:05Z",
};

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

/** Ordered sequence 1–6 ending with error. */
export const errorReplay: AgentEventResponse[] = [
  agentStartedEvent,
  assistantOutputEvent,
  toolCallEvent,
  toolResultEvent,
  approvalRequestedEvent,
  errorEvent,
];

/** Ordered sequence 1–6 ending with completed. */
export const completedReplay: AgentEventResponse[] = [
  agentStartedEvent,
  assistantOutputEvent,
  toolCallEvent,
  toolResultEvent,
  approvalRequestedEvent,
  completedEvent,
];
