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
