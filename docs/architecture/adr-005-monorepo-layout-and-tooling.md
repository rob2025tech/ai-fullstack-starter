# ADR-005: Monorepo layout and tooling

- Status: Accepted
- Date: 2026-08-31

## Context

The repo holds two clients, one or more backend implementations of the
same contract, and the shared contract package. The backend reference
used `apps/{api,web,mobile}`, which conflates user-facing apps with
interchangeable backend implementations — a problem once a second
backend language arrives.

## Decision

- Layout: `apps/` for user-facing clients (web, mobile), `backends/`
  for contract implementations (fastapi now; e.g. express later),
  `packages/api-contract/` for the shared contract artifact and
  conformance tests, `docs/architecture/` for ADRs.
- Tooling: npm workspaces for the TypeScript packages; per-backend
  Python venvs; GitHub Actions CI.
- No Turborepo/NX initially; revisit only if task-graph or caching
  pain appears.

## Consequences

- Adding a backend in another language is a new directory under
  `backends/` plus CI wiring — clients and contract untouched.
- Workspaces keep contract types one import away from both clients.
- Cost of skipping monorepo tooling: scripts are coordinated manually
  (root package.json scripts) until that hurts.
