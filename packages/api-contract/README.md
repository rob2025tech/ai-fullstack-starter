# @ai-fullstack-starter/api-contract

The versioned, language-neutral API contract (ADR-001). Everything in
this package exists to keep web, mobile, and every backend
implementation agreeing on one boundary.

## Contents

- `openapi.yaml` — OpenAPI 3.1 spec, the **sole source of truth**.
- `src/generated/schema.ts` — TypeScript types generated from the spec
  (gitignored; regenerate, never hand-edit).
- `src/index.ts` — re-exports generated types plus the SSE event name
  constants (ADR-003).
- `tests/` — offline spec sanity tests (parse, shape, refs, error
  registry).
- `conformance/` — live conformance suite: runs against any backend
  claiming to implement the contract.

## Commands

```bash
npm run generate           # openapi.yaml -> src/generated/schema.ts
npm test                   # offline spec sanity tests
npm run typecheck          # tsc --noEmit
CONTRACT_BASE_URL=http://127.0.0.1:8000 npm run test:conformance
```

## Changing the contract

- Additive-only within v1 (ADR-002): new endpoints, new optional
  request fields, new response fields. Anything else requires
  `/api/v2` plus an ADR.
- Errors must use codes from the `Error.code` registry — never
  exception class names or framework-specific shapes.
- After editing `openapi.yaml`: run `npm run generate`, `npm test`,
  and the conformance suite against the reference backend.

## Error code registry (v1)

| Code | HTTP | Meaning |
|---|---|---|
| `invalid_request` | 422 | Request failed validation |
| `rate_limited` | 429 | Too many requests |
| `internal_error` | 500 | Unexpected server failure |
| `provider_error` | 502 | AI provider errored or returned malformed output |
| `provider_unavailable` | 503 | Provider not configured or unreachable |
