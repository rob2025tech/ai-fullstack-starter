# ADR-004: No authentication in v1

- Status: Superseded by [ADR-007](adr-007-protected-learning-identity.md)
- Date: 2026-08-31

## Context

This is a starter template optimized for zero-friction first run. The
backend reference shipped `user_id` without any auth, and deciding an
auth model now would either bloat day-1 scope (JWT endpoints on every
future backend) or bake in a weak choice (a static shared token).

## Decision

- v1 has no authentication. Requests carry a client-supplied anonymous
  `user_id` used only for scoping (e.g. conversation grouping); it is
  not an identity.
- The contract reserves no auth mechanism; no headers are defined yet.
- Auth (bearer/JWT) is deferred to a future ADR, to be decided before
  any hosted deployment of the starter.

## Consequences

- Fastest possible onboarding; both clients and every backend skip
  auth code for now.
- `user_id` is spoofable by design — acceptable for local/dev starter
  use, and documented as such.
- Adding auth later is an additive contract change (new header + 401
  semantics), compatible with ADR-002.
