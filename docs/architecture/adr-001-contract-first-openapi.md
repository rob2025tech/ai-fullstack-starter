# ADR-001: Contract-first, language-neutral OpenAPI spec

- Status: Accepted
- Date: 2026-08-31

## Context

Two client languages (TypeScript web, TypeScript mobile) and multiple
future backend languages (FastAPI now, Node/Express later) must agree
on one API. The backend reference repo (`agent-factory-hackathon`)
showed two failure modes to avoid:

- Doc-vs-code drift: its `docs/architecture/api-contract.md` described
  endpoints that were never built and self-tagged as stale, while the
  real contract lived only in Pydantic models.
- Language leaks: its error payload exposed Python exception class
  names, and a request field (`backend`) existed but was ignored.

## Decision

- `packages/api-contract/openapi.yaml` (OpenAPI 3.1) is the sole
  source of truth for the API boundary. It is hand-maintained and
  independent of any backend implementation.
- Clients consume TypeScript types generated from this spec (e.g. via
  `openapi-typescript`); generated output lives under
  `packages/api-contract/src/generated/` and is gitignored.
- Backends implement the spec. FastAPI additionally runs a CI drift
  guard comparing its emitted OpenAPI against the canonical spec.
- A shared conformance suite (request → expected response shape,
  parameterized by base URL) runs against every backend implementation.
- Error payloads use a fixed registry of stable, language-neutral
  error codes — never exception class names or framework shapes.

## Consequences

- Every API change starts in the spec and gets reviewed there.
- Clients never depend on a Python- or Node-specific artifact, so a
  new backend language can be added without client changes.
- Cost: codegen step in the build, plus the drift-guard and
  conformance jobs in CI.
