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

All settings are env-driven via `app/config/settings.py`. The backend
runs in one of three deployment modes controlled by `DEPLOYMENT_MODE`.

| Setting | Default | Purpose |
|---|---|---|
| `LLM_PROVIDER` | `mock` | `mock` or `openai` |
| `OPENAI_API_KEY` | unset | Required for `openai` |
| `OPENAI_BASE_URL` | `https://api.openai.com/v1` | Any OpenAI-compatible API |
| `OPENAI_MODEL` | `gpt-4o-mini` | Model name |
| `CORS_ORIGINS` | `["http://localhost:3000","http://127.0.0.1:3000"]` | JSON list of allowed origins |
| `CONTRACT_VERSION` | `1.0.0` | Reported by `/api/v1/health` |
| `DEPLOYMENT_MODE` | `local` | `local`, `shared-demo`, or `production` |
| `SESSION_SECRET` | unset | Required (non-blank) for `shared-demo` and `production` |
| `SESSION_ISSUER` | `ai-fullstack-starter` | JWT `iss` claim |
| `SESSION_TTL_SECONDS` | `28800` (8 h) | Session token lifetime |

## Deployment-mode matrix

| Mode | Session auth required | `SESSION_SECRET` required | Startup with missing secret | Learning endpoints in protected mode |
|---|---|---|---|---|
| `local` | No — optional session context | No — ephemeral process-scoped secret used | Starts normally | Serve state using session context when present; allow unauthenticated access |
| `shared-demo` | Yes — 401 on all protected learning endpoints | **Yes — fails closed** | Raises `ValueError` and refuses to start | Return 401 for requests without a valid signed session |
| `production` | Yes — 401 on all protected learning endpoints | **Yes — fails closed** | Raises `ValueError` and refuses to start | Return 401 for requests without a valid signed session |

`local` mode must be **explicitly selected** by setting `DEPLOYMENT_MODE=local`.
It is not a silent fallback for a missing `SESSION_SECRET` in `shared-demo` or
`production` — those modes fail closed at startup before serving any request.

Verify fail-closed behavior locally:

```bash
# Expected: ValueError at startup — must not start without a secret
DEPLOYMENT_MODE=shared-demo .venv/bin/python -c "
from app.config.settings import Settings
Settings(_env_file=None)
"

# Expected: starts normally in local mode, no secret required
.venv/bin/uvicorn app.main:app --port 8000
```

## Managed secrets

`SESSION_SECRET` is the only secret value required by the backend at
runtime. It signs and verifies learner session JWTs (HS256) and must be
managed outside the repository:

```bash
# shared-demo or production startup — supply via environment only
SESSION_SECRET=<managed-session-signing-secret> \
DEPLOYMENT_MODE=shared-demo \
.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
```

**Never** place `SESSION_SECRET` or any signing secret in:
- `.env` files committed to the repository
- `NEXT_PUBLIC_*` or `EXPO_PUBLIC_*` variables (bundled into client binaries)
- Web or mobile source code

`LLM_PROVIDER=mock` (the default) runs with zero LLM secrets. Set
`OPENAI_API_KEY` only in backends that need a live provider.

## CORS credentials policy

`app/main.py` wires `CORSMiddleware` with `allow_credentials=True` so
HttpOnly session cookies are forwarded for browser-based web clients.

| Client type | Cookie transport | `allow_credentials` | `allow_origins` |
|---|---|---|---|
| Web browser (`apps/web`) | HttpOnly cookie; requires `credentials: 'include'` in fetch | Must be `True` | Must be an **explicit list** — wildcard `*` is rejected by browsers when `credentials: include` |
| Mobile Expo/React Native (`apps/mobile`) | Bearer token in `Authorization` header | Not required (no cookies) | Can be a list or `*` if mobile-only, but shared config uses the explicit list |

**Important:** Never set `allow_origins=["*"]` when `allow_credentials=True`.
Browsers reject credentialed cross-origin responses with a wildcard origin.
Set `CORS_ORIGINS` to the exact list of frontend origins for the deployment:

```bash
CORS_ORIGINS='["https://your-web-app.example.com"]' \
SESSION_SECRET=<managed-session-signing-secret> \
DEPLOYMENT_MODE=shared-demo \
.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## Endpoint exposure

### Public (no session required in any mode)

| Path | Method | Description |
|---|---|---|
| `/api/v1/health` | GET | Liveness check; returns `{"status":"ok"}` |
| `/api/v1/chat` | POST | Chat completions (JSON and SSE modes) |
| `/api/v1/session/bootstrap` | POST | Issues a signed anonymous session token |
| `/api/v1/learning/quiz` | GET | Retrieves a quiz question (no state mutation) |
| `/api/v1/learning/quiz/retest` | GET | Retrieves a retest question (no state mutation) |

### Protected in `shared-demo` and `production` (returns 401 without a valid session)

| Path | Method | Description |
|---|---|---|
| `/api/v1/learning/state` | GET | Reads learner progress for a concept |
| `/api/v1/learning/answer` | POST | Records a free-text learning answer |
| `/api/v1/learning/quiz/answer` | POST | Records a quiz answer |
| `/api/v1/learning/quiz/practice` | POST | Records a practice answer |
| `/api/v1/learning/quiz/retest` | POST | Records a retest answer |

A missing, expired, or signature-invalid session token returns
`{"error": {"code": "unauthorized", "message": "..."}}` with HTTP 401.
The full response shape is defined in `packages/api-contract/openapi.yaml`.

> **Note:** In `local` mode all endpoints above accept requests without a
> session token (existing unauthenticated behaviour). Learner identity
> falls back to the session context when a valid token is present or to an
> ephemeral identifier when absent. Do not depend on local-mode behaviour
> for multi-user deployments.

## Interactive documentation exposure

`app/main.py` controls the FastAPI interactive docs URLs based on
`DEPLOYMENT_MODE`:

| Endpoint | `local` | `shared-demo` / `production` |
|---|---|---|
| `/docs` (Swagger UI) | **Enabled** | **Disabled** (returns 404) |
| `/redoc` (ReDoc) | **Enabled** | **Disabled** (returns 404) |
| `/openapi.json` | Available | Available (used by the CI drift guard) |

In `shared-demo` and `production` the interactive docs are disabled to
avoid exposing endpoint shapes to anonymous users. The raw OpenAPI schema
at `/openapi.json` remains available because the CI contract drift test
(`tests/test_contract_drift.py`) reads it to verify alignment with
`packages/api-contract/openapi.yaml`.

If you need interactive docs behind a protected deployment, serve the
static Swagger UI bundle separately after requiring authentication rather
than re-enabling `/docs` with a public backend.

## Contract obligations

- Errors always use the `{error: {code, message}}` envelope with codes
  from the contract registry — never exception class names.
- `stream: true` returns SSE: `delta` events then exactly one terminal
  `message` or `error` event.
- Validation failures return 422 with code `invalid_request`.
- Protected learning endpoints return 401 with code `unauthorized` for
  missing or invalid sessions in `shared-demo` and `production` modes.
- All canonical endpoint shapes are defined in
  `packages/api-contract/openapi.yaml`; run the conformance suite to
  validate a live deployment:

```bash
# From the repo root — server must be running in protected mode
CONTRACT_BASE_URL=http://127.0.0.1:8000 \
npm run test:conformance -w @ai-fullstack-starter/api-contract
```
