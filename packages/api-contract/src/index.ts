export type * from "./generated/schema.js";

/**
 * SSE event names emitted by POST /api/v1/chat when stream=true (ADR-003).
 * The terminal event is exactly one of `message` (success) or `error`.
 */
export const chatStreamEvents = {
  delta: "delta",
  message: "message",
  error: "error",
} as const;

export type ChatStreamEventName =
  (typeof chatStreamEvents)[keyof typeof chatStreamEvents];

/**
 * SSE event names emitted by the agent event streams:
 * GET /api/v1/agent/sessions/{session_id}/events/stream and
 * GET /api/v1/agent/sessions/{session_id}/tasks/{task_id}/events/stream.
 * Each frame's `event` name matches the AgentEventResponse `event_type`
 * and its `data` payload is a JSON-serialised AgentEventResponse.
 * The streams replay persisted events and close after the last frame.
 */
export const agentStreamEvents = {
  assistantOutput: "assistant_output",
  toolCall: "tool_call",
  toolResult: "tool_result",
  approvalRequested: "approval_requested",
  approvalDecided: "approval_decided",
  approvalConsumed: "approval_consumed",
  error: "error",
  completed: "completed",
  taskAccepted: "task_accepted",
  agentStarted: "agent_started",
} as const;

export type AgentStreamEventName =
  (typeof agentStreamEvents)[keyof typeof agentStreamEvents];
