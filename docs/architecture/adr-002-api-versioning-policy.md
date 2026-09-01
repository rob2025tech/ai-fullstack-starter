# ADR-002: API versioning policy

- Status: Accepted
- Date: 2026-08-31

## Context

The contract serves deployed-in-the-wild web and mobile clients that
cannot be force-updated simultaneously. Changes must be classifiable
as safe or breaking without negotiation per change.

## Decision

- All endpoints are prefixed with the major version: `/api/v1/...`.
- Within a major version, only additive changes are allowed: new
  endpoints, new optional request fields, new response fields. Clients
  must ignore unknown response fields.
- Breaking changes (removed/renamed fields, changed semantics, changed
  status codes) go to a new major version (`/api/v2`) with an overlap
  period; each bump is recorded in an ADR.
- The contract package versions the spec alongside it (spec `info.version`).

## Consequences

- Additive evolution never requires client releases.
- Optional fields become the default escape hatch; making a field
  required later is a breaking change.
- Backends may serve multiple majors concurrently during overlap.
