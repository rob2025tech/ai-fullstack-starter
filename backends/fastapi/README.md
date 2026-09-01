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

All settings are env-driven with safe defaults (ADR-004 no-auth;
runs secretless):

| Setting | Default | Purpose |
|---|---|---|
| `LLM_PROVIDER` | `mock` | `mock` or `openai` |
| `OPENAI_API_KEY` | unset | Required for `openai` |
| `OPENAI_BASE_URL` | `https://api.openai.com/v1` | Any OpenAI-compatible API |
| `OPENAI_MODEL` | `gpt-4o-mini` | Model name |
| `CORS_ORIGINS` | localhost:3000 | JSON list of allowed origins |
| `CONTRACT_VERSION` | `1.0.0` | Reported by `/api/v1/health` |

## Contract obligations

- Errors always use the `{error: {code, message}}` envelope with codes
  from the contract registry — never exception class names.
- `stream: true` returns SSE: `delta` events then exactly one terminal
  `message` or `error` event.
- Validation failures return 422 with code `invalid_request`.
