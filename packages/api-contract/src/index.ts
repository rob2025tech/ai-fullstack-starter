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
 * SSE event names emitted by
 * GET /api/v1/agent/sessions/{session_id}/tasks/{task_id}/events/stream.
 * Terminal events are `completed` (success) and `error` (failure);
 * clients must close the stream after receiving either.
 */
export const agentStreamEvents = {
  agentStarted: "agent_started",
  assistantOutput: "assistant_output",
  toolCall: "tool_call",
  toolResult: "tool_result",
  approvalRequested: "approval_requested",
  approvalDecided: "approval_decided",
  error: "error",
  completed: "completed",
  taskAccepted: "task_accepted",
} as const;

export type AgentStreamEventName =
  (typeof agentStreamEvents)[keyof typeof agentStreamEvents];
