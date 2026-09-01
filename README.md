# AI Fullstack Starter

Reusable starter for AI products: **Next.js web** and **Expo/React
Native mobile** clients behind a **single versioned, language-neutral
API contract**. FastAPI is the first/reference backend; additional
backends (e.g. Node/Express) can implement the same contract without
changing either client.

```text
Next.js web ──┐
              ├── HTTPS /api/v1 (OpenAPI contract) ──► backend implementation
Expo mobile ──┘                                        (FastAPI now, Express later)
```

## Repository layout

```text
apps/
  web/                  # Next.js client (App Router, TypeScript)
  mobile/               # Expo client (TypeScript)
backends/
  fastapi/              # Reference backend implementation
packages/
  api-contract/         # OpenAPI spec (source of truth), generated TS types,
                        # contract conformance tests
docs/architecture/      # ADRs
```

## Status

| Piece | Status |
|---|---|
| Monorepo skeleton + ADRs | Done |
| `packages/api-contract` (OpenAPI + codegen + conformance) | Done |
| `backends/fastapi` (health + chat + SSE + mock provider) | Done |
| `apps/web` | Done |
| `apps/mobile` | Done |

See `docs/architecture/` for the decisions (ADR-001 onward) and
`AGENTS.md` for working instructions.

## Reference repositories (read-only)

Patterns were distilled from, not copied out of:

- `~/Projects/Templates/nextjs` — web scaffolds
- `~/Projects/Templates/react-native-ai-app` — mobile intent (README only)
- `~/Projects/Templates/agent-factory-hackathon` — backend/AI architecture
