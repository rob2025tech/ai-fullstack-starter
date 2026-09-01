# ADR-003: SSE streaming in the v1 chat endpoint

- Status: Accepted
- Date: 2026-08-31

## Context

Both target clients are chat experiences; token-by-token streaming is
the expected UX. Shipping JSON-only first and adding streaming later
would force rebuilding the clients' rendering paths and add a second
contract negotiation round. Server-Sent Events work over plain HTTPS
on both web and React Native without protocol extras (no WebSocket
infrastructure).

## Decision

- `POST /api/v1/chat` accepts a boolean `stream` field.
  - `stream: false` (default) → single JSON response.
  - `stream: true` → `text/event-stream` with typed events: token
    deltas, then a terminal event carrying the complete message
    metadata (finish reason, usage when available).
- Streaming errors are delivered as a terminal error event using the
  same error-code registry as JSON responses, then the stream closes.
- Every backend implementation must support both modes; the
  conformance suite covers both.

## Consequences

- Backends carry slightly more day-1 complexity (event framing,
  client-disconnect handling).
- Clients can share one streaming-render abstraction across web and
  mobile.
- Adding future transports (e.g. WebSocket for bidirectional tools)
  remains an additive v1 change or a v2 topic.
