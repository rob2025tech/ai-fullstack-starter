# ADR-007: Hosted agent authentication and deployment-mode trust boundaries

- Status: Accepted
- Date: 2026-09-25

## Context

ADR-004 deferred authentication to keep the starter's day-1 scope small.
As this starter is extended with an agent control plane (WO-001 through
WO-003), the distinction between local development and a hosted deployment
becomes operationally significant:

- **Local no-auth mode** (`deployment_mode=local`): single-developer
  workstation; mock provider; no secrets required; `user_id` is trusted
  as-supplied from the request body.
- **Hosted mode** (`deployment_mode=production`): multi-user or
  internet-facing deployment; secrets must be configured; client-supplied
  `user_id` is **not** a trusted identity boundary.

Today the backend can be misconfigured into a partially-secured state where
`deployment_mode=production` is set but `SESSION_SECRET` or `CORS_ORIGINS`
are absent, because these checks were scattered across the session module
and runtime dependencies rather than enforced at startup.

## Decision

1. **Fail-closed at startup for production mode.** The `Settings`
   constructor runs a Pydantic `model_validator` that raises a validation
   error before `create_app` wires any middleware, route, or provider
   if any of the following is true when `deployment_mode=production`:
   - `SESSION_SECRET` is absent or whitespace-only.
   - `CORS_ORIGINS` is empty or contains a wildcard (`*`).
   - `OPENAI_API_KEY` is absent or whitespace-only when
     `LLM_PROVIDER=openai`.

2. **Local mode stays secretless.** `deployment_mode=local` with
   `LLM_PROVIDER=mock` constructs with no secrets, uses an ephemeral
   per-process signing key for sessions, and defaults CORS to localhost
   origins.

3. **client-supplied `user_id` is not a hosted identity boundary.**
   The `user_id` field in request bodies is an anonymous scoping hint
   suitable for local/dev use only. In a hosted deployment, identity must
   be established via `Authorization: Bearer <token>` and validated before
   any session or agent state is associated with a user.

4. **Bearer/JWT expectation for hosted paths.** Future protected hosted
   endpoints must require `Authorization: Bearer <token>`. Missing or
   invalid tokens return `401` with the standard error envelope
   (`{"error": {"code": "unauthorized", "message": "..."} }`). This is
   additive relative to v1 per ADR-002; unprotected local endpoints are
   unaffected.

5. **Defense in depth.** The session module (`app.auth.sessions`) retains
   its own validation of `SESSION_SECRET` at token issue/validate time.
   The `Settings` validator is the earliest gate; the session module is a
   second layer.

## Consequences

- A hosted operator who forgets `SESSION_SECRET`, `CORS_ORIGINS`, or
  `OPENAI_API_KEY` receives a readable Pydantic error at process startup
  naming the missing variable (`SESSION_SECRET`, `CORS_ORIGINS`,
  `OPENAI_API_KEY`) before any HTTP traffic is accepted.
- Local and CI development is unaffected: `deployment_mode=local` with
  `LLM_PROVIDER=mock` requires zero secrets.
- `deployment_mode=production` with `LLM_PROVIDER=mock` is a supported
  staging posture: CORS + session-secret are required, but live AI
  credentials are not.
- `user_id` in request bodies remains an anonymous hint with no trust
  semantics; a full identity provider, OAuth server, or role-based
  authorization system is out of scope for this ADR.
- The `401` response code and `Authorization: Bearer <token>` header are
  reserved for future protected endpoints under the existing v1 additive
  policy (ADR-002); no existing endpoint behavior changes.

## local no-auth runbook

```text
DEPLOYMENT_MODE=local
LLM_PROVIDER=mock
# No SESSION_SECRET, no CORS_ORIGINS override, no OPENAI_API_KEY needed.
uvicorn app.main:app --reload --port 8000
```

## production runbook

```text
DEPLOYMENT_MODE=production
SESSION_SECRET=<secrets.token_urlsafe(32)>
CORS_ORIGINS=["https://app.example.com"]
LLM_PROVIDER=openai                      # or mock for staging
OPENAI_API_KEY=<your-key>               # omit if LLM_PROVIDER=mock
uvicorn app.main:app --port 8000
```

If any required variable is missing the process exits with a Pydantic
`ValidationError` listing which setting name must be fixed.
