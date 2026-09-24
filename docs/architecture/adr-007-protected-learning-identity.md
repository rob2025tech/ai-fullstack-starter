# ADR-007: Protected learning identity and deployment-mode session authority

- Status: Accepted
- Date: 2026-09-24
- Supersedes: [ADR-004](adr-004-no-auth-in-v1.md)

## Context

ADR-004 deferred authentication for v1 and declared the client-supplied
`user_id` field as intentionally spoofable — acceptable for local and
developer starter use. That trade-off is no longer safe as the starter
targets shared-demo and production deployments where multiple learners
share a backend and their adaptive learning progress must be isolated.

Two concrete risks motivated this decision:

1. **Spoofability of learner identity.** `fastapi/app/routers/learning.py`
   accepts `user_id` from the request body today. Any caller can set
   `user_id` to any string, reading or writing another learner's state in
   `InMemoryLearningRepository`, which keys state by `(user_id, concept)`.

2. **Accidental no-secret deployment.** Nothing previously prevented
   starting the FastAPI backend in a multi-user profile without a signing
   secret, creating an inconsistent auth posture that is silent until
   abused.

The v1 contract must remain additive-only (ADR-002). The 401 response
shape has been added to `packages/api-contract/openapi.yaml` for the five
protected learning endpoints without removing any existing 200 or 422
responses. Protected mode is therefore a safe additive evolution of the
existing contract.

## Decision

### Deployment modes

The backend runs in exactly one of three explicitly selected modes,
controlled by the `DEPLOYMENT_MODE` environment variable (default:
`local`):

| Mode | Session requirement | Secret requirement |
|---|---|---|
| `local` | Optional; `user_id` from session context when present | Not required; ephemeral process-scoped secret used |
| `shared-demo` | Required on all protected learning endpoints | Required at startup — fails closed if missing or blank |
| `production` | Required on all protected learning endpoints | Required at startup — fails closed if missing or blank |

`local` mode must be **explicitly selected** by the operator. It does not
inherit silent fallback from a missing `SESSION_SECRET`. A shared-demo or
production backend started without `SESSION_SECRET` raises a validation
error at startup and refuses to serve requests.

### Session authority

FastAPI is the sole session authority in this v1 protected model:

- `backends/fastapi/app/auth/sessions.py` issues and validates signed
  anonymous JWTs (HS256) using a backend-held `SESSION_SECRET`.
- The signed token contains a `sub` claim that becomes the canonical
  learner identifier. No client value can override it.
- Session bootstrap is available at `POST /api/v1/session/bootstrap`.
  The endpoint issues a short-lived signed token without requiring prior
  credentials, making anonymous onboarding seamless for both web and
  mobile.

### Client transport

| Client | Protected learning transport |
|---|---|
| Web (`apps/web`) | HttpOnly secure cookie, set by the backend at session bootstrap; browser attaches it automatically on same-origin requests via `credentials: 'include'` in `web/lib/api.ts` |
| Mobile (`apps/mobile`) | Short-lived bearer token, bootstrapped once per app launch via `bootstrapSession()` in `mobile/lib/api.ts` and stored in a React `useRef`; sent as `Authorization: Bearer <token>` |

Web clients must **not** store bearer tokens in `localStorage` or
`sessionStorage`. Mobile clients must **not** persist tokens to
`AsyncStorage`, `SecureStore`, or the device keychain — the token is
short-lived and re-bootstrapped on each app launch.

### Learner identity is server-derived

In `shared-demo` and `production` modes the backend derives learner
identity exclusively from the validated session token's `sub` claim.
Any `user_id` field supplied in a request body is ignored; the session
subject is used for all reads and writes to `InMemoryLearningRepository`.
Client components (`web/components/adaptive-tutor.tsx`,
`web/components/retention-quiz.tsx`) must not send a hard-coded learner
identifier for protected learning mutations.

### Fail-closed protected mode

Protected endpoints (`GET /api/v1/learning/state`,
`POST /api/v1/learning/answer`, `POST /api/v1/learning/quiz/answer`,
`POST /api/v1/learning/quiz/practice`,
`POST /api/v1/learning/quiz/retest`) return a contract-shaped 401
response (`ErrorResponse` with `error.code = "unauthorized"`) when the
session token is absent, expired, or signature-invalid. This response
shape is defined in `packages/api-contract/openapi.yaml` and must be
maintained as the canonical source of truth per ADR-001.

### No external identity provider in v1

This decision records built-in lightweight signed anonymous sessions as
the v1 protected-mode target. It does not require an external identity
provider (OAuth, OIDC, Cognito, Auth0). An external provider integration
would be an additive extension point in a future ADR and major version
per ADR-002.

## Consequences

**Positive:**
- Learner progress in `InMemoryLearningRepository` is isolated by
  session subject across multiple users of the same backend process.
- Operator configuration errors (missing secret in protected mode) are
  caught at startup rather than at first request.
- The CI release gate (`workflows/ci.yml`) exercises all three profiles:
  local no-secret startup, shared-demo fail-closed guard, and
  protected-mode live conformance.
- The 401 contract change is additive; existing local-mode clients are
  unaffected until `DEPLOYMENT_MODE` is changed.

**Negative / trade-offs:**
- In-memory learning state is not durable. Session subjects change on
  each app restart or re-bootstrap. Learner progress is ephemeral until
  a persistent repository implementation is added in a future story.
- Bearer tokens and ephemeral cookies have different refresh semantics;
  token expiry must be handled gracefully in both clients.
- Cross-origin cookie transport requires explicit CORS configuration
  (`Access-Control-Allow-Credentials: true` plus a non-wildcard
  `Access-Control-Allow-Origin`).

**Constraints inherited from prior ADRs:**
- Contract changes remain additive-only within v1 (ADR-002). Future
  protected learning changes must be reflected in
  `packages/api-contract/openapi.yaml` and regenerated TypeScript types
  before release.
- Mobile chat stays on JSON mode; bearer token propagation for learning
  does not require adding SSE polyfills (ADR-006).

## Migration waves

This plan sequences the implementation stories required to move from
the no-auth baseline to a fully protected shared-demo deployment. No
database migration step is included because
`fastapi/app/learning/repository.py` remains an in-memory repository.

| Wave | Scope | Verification |
|---|---|---|
| **1 · Baseline** | Confirm `local` mode continues to serve learning endpoints without a signing secret; ensure no regression in existing tests | `pytest backends/fastapi` exits 0 in local mode |
| **2 · Backend guard** | `Settings` model validator raises at startup when `deployment_mode` is `shared-demo` or `production` and `session_secret` is absent or blank | `pytest tests/test_settings_startup_matrix.py` covers all three profiles; CI fail-closed gate step passes |
| **3 · Protected route integration** | `LearnerContext` FastAPI dependency validates bearer/cookie session and raises 401 on failure; learner identity is derived from token `sub`; client-supplied `user_id` is ignored | `pytest tests/test_learning_router.py tests/learning/test_quiz_router.py` with tampered, expired, and valid session fixtures |
| **4 · Contract and client migration** | 401 responses added to `packages/api-contract/openapi.yaml` for protected endpoints; web uses `credentials: 'include'`; mobile calls `bootstrapSession()` and passes bearer header | `npm test -w @ai-fullstack-starter/api-contract` exits 0; spec drift guard passes |
| **5 · Canary validation** | Conformance suite runs against protected-mode backend at `CONTRACT_BASE_URL`; unauthenticated 401 tests pass | `CONTRACT_BASE_URL=http://127.0.0.1:8000 npm run test:conformance -w @ai-fullstack-starter/api-contract` exits 0 |
| **6 · Rollback** | If any wave fails: revert `DEPLOYMENT_MODE` to `local`; no database rollback required because state is in-memory and ephemeral; re-run full CI | CI green in local mode confirms rollback complete |
