# FastAPI reference backend

Reference implementation of the `/api/v1` contract
(`packages/api-contract/openapi.yaml`). Python >= 3.12.

## Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-lock.txt
```

## Run

```bash
.venv/bin/uvicorn app.main:app --reload --port 8000
```

With defaults the backend uses the deterministic mock provider, so it
runs with zero secrets. Copy `.env.example` to `.env` and set
`LLM_PROVIDER=openai` plus `OPENAI_API_KEY` for a real provider
(any OpenAI-compatible endpoint via `OPENAI_BASE_URL`).

## Test

```bash
.venv/bin/pytest                 # unit suite (mock provider; no network)
.venv/bin/ruff check .
```

Contract verification (run from the repo root, server must be up):

```bash
npm run test:conformance -w @ai-fullstack-starter/api-contract
```

The drift-guard test (`tests/test_contract_drift.py`) fails if the
emitted OpenAPI diverges from the canonical spec in endpoints, status
codes, schema shapes, or the error-code registry.

## Configuration

All settings are env-driven with safe defaults. See `.env.example` for
the full list. Key settings:

| Setting | Default | Purpose |
|---|---|---|
| `DEPLOYMENT_MODE` | `local` | `local`, `shared-demo`, or `production` |
| `LLM_PROVIDER` | `mock` | `mock` or `openai` |
| `OPENAI_API_KEY` | unset | Required when `LLM_PROVIDER=openai` |
| `OPENAI_BASE_URL` | `https://api.openai.com/v1` | Any OpenAI-compatible API |
| `OPENAI_MODEL` | `gpt-4o-mini` | Model name |
| `CORS_ORIGINS` | localhost:3000 | JSON list of allowed origins |
| `SESSION_SECRET` | unset | Required for `shared-demo` and `production` |
| `CONTRACT_VERSION` | `1.0.0` | Reported by `/api/v1/health` |

## Deployment modes

### `local` (default)

Runs secretless with the mock provider. No `SESSION_SECRET` or
`OPENAI_API_KEY` required. CORS defaults to localhost:3000. Suitable
for development and CI.

### `shared-demo`

Shared ephemeral deployment. `SESSION_SECRET` must be configured; the
session module rejects session operations at runtime if it is missing.
No fail-closed startup gate.

### `production`

Fail-closed at startup. The `Settings` constructor raises a Pydantic
validation error before `create_app` wires any middleware or routes if:

- `SESSION_SECRET` is absent or whitespace-only
- `CORS_ORIGINS` is empty or contains a wildcard (`*`)
- `OPENAI_API_KEY` is absent or whitespace-only when `LLM_PROVIDER=openai`

The mock provider does not require `OPENAI_API_KEY` even in production
mode; use it to stage a deployment without live AI credentials.

## Contract obligations

- Errors always use the `{error: {code, message}}` envelope with codes
  from the contract registry — never exception class names.
- `stream: true` returns SSE: `delta` events then exactly one terminal
  `message` or `error` event.
- Validation failures return 422 with code `invalid_request`.
