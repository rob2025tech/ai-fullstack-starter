# AGENTS.md

Working instructions for AI coding agents modifying this repository.

This document has three tiers:

- **Verified Facts** — repository state confirmed from code and config.
- **Engineering Rules** — durable conventions; follow them on every change.
- **Recommendations** — guidance that usually helps; use judgment.

---

# I. Verified Facts

## Purpose

Reusable starter for AI products: Next.js web and Expo/React Native
mobile clients behind a single versioned, language-neutral API
contract (`/api/v1`). FastAPI is the first/reference backend; a future
Node/Express backend can implement the same contract without changing
either client.

## Repository Status

Day-1 vertical slice complete as of 2026-08-31: contract package,
FastAPI reference backend, Next.js web client, and Expo mobile client.
Check the status table in `README.md` before assuming any additional
package exists.

## Repository Structure

```text
apps/web/               # Next.js client
apps/mobile/            # Expo client
backends/fastapi/       # Reference backend implementation
packages/api-contract/  # OpenAPI spec, generated TS types, conformance tests
docs/architecture/      # ADRs (ADR-001 onward)
.github/workflows/      # CI
```

## API Contract

- `packages/api-contract/openapi.yaml` (OpenAPI 3.1) is the sole source
  of truth (ADR-001). Clients consume types generated from it; every
  backend implements it and passes the shared conformance suite.
- v1 surface: `GET /api/v1/health`; `POST /api/v1/chat` with JSON or
  SSE streaming modes (ADR-003); stable error-code envelope.
- No authentication in v1; requests carry an anonymous `user_id`
  (ADR-004).

## Tooling

- Node 24 (`.node-version`), npm workspaces; no Turborepo (ADR-005).
- Python 3.13 per backend (requires-python >= 3.12), each with its own
  venv and a pinned `requirements-lock.txt`.

## Reference Repositories (READ-ONLY)

- `~/Projects/Templates/nextjs`
- `~/Projects/Templates/react-native-ai-app`
- `~/Projects/Templates/agent-factory-hackathon`

---

# II. Engineering Rules

1. The OpenAPI spec is the boundary. Contract changes are additive-only
   within v1; breaking changes require `/api/v2` plus an ADR (ADR-002).
2. Nothing language-specific crosses the contract: no exception class
   names, framework error shapes, or backend-internal identifiers in
   responses or error payloads. Errors use the registered error codes.
3. Clients consume only generated contract types. Regenerate them;
   never hand-edit files under `packages/api-contract/src/generated/`.
4. Never put secrets in `apps/web` or `apps/mobile`. `NEXT_PUBLIC_*`
   and Expo env vars carry non-secrets only (e.g. the API base URL).
   All AI provider keys live in backend configuration.
5. Backends must run with zero secrets: every setting is env-driven,
   validated, defaulted, and falls back to the deterministic mock
   provider.
6. The reference repositories listed above are read-only. Port
   patterns; do not copy their files or their project-specific
   semantics (see ADR-001 context for what was excluded).
7. Git: short imperative commit messages; never commit secrets or
   `.env` files; record decisions as ADRs.

---

# III. Recommendations

1. Make the smallest change that satisfies the task; read the files you
   touch before editing.
2. Before changing behavior that looks odd, check for an ADR — it may
   be intentional.
3. Default to the mock provider in tests; mark tests needing live
   services with an `integration` marker and keep them deselected by
   default.
4. In `apps/web`: this project targets Next 16, which has breaking
   changes relative to older training data. Once dependencies are
   installed, read the relevant guides in `node_modules/next/dist/docs/`
   before writing Next.js code, and heed deprecation notices.
5. In `apps/mobile`: the client deliberately consumes the contract's
   JSON mode (ADR-006). Do not add SSE polyfills or a streaming
   transport without revisiting that ADR.
6. Run the relevant test subset while working and report actual
   passed/skipped counts — never assume a fixed baseline.
