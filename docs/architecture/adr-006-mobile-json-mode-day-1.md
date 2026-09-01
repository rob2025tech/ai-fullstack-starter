# ADR-006: Mobile client consumes JSON mode on day 1

- Status: Accepted
- Date: 2026-08-31

## Context

ADR-003 puts SSE streaming in the v1 contract, and the web client
streams token deltas. For the Expo mobile client, consuming SSE would
require a third-party polyfill: React Native does not ship
`EventSource` and its `fetch` does not expose streaming response
bodies (community libraries such as `react-native-sse` or
`react-native-fetch-event-source` exist precisely to fill that gap).
Day-1 template policy prefers zero extra runtime dependencies where
the contract already provides an equivalent path.

## Decision

- `apps/mobile` calls `POST /api/v1/chat` in JSON mode
  (`stream: false`, the contract default) and renders the single
  `ChatResponse`.
- The JSON response carries the same `message` shape as the SSE
  terminal `message` event, so switching mobile to streaming later is
  an additive client change: add an SSE transport (polyfill or a
  future native capability) plus delta rendering. No contract, backend,
  or web-client change is involved.
- Backends still must implement both modes (ADR-003 is unchanged);
  the conformance suite continues to cover both.

## Consequences

- Mobile chat shows the full reply at once instead of token deltas
  until someone opts into a streaming transport.
- The mobile client has no third-party networking dependency and stays
  verifiable without device-specific streaming behavior.
- Any future SSE-on-mobile work is scoped entirely inside
  `apps/mobile`.
