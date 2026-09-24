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

---

## Protected-mode learning rollout checklist

Use this checklist to promote a `shared-demo` or `production` deployment
with protected learning enabled. Execute each phase in order. Do not
advance to the next phase until all items in the current phase pass.

**Detailed configuration guidance lives in the component READMEs:**

- Architecture decision: [`docs/architecture/README.md`](docs/architecture/README.md) → ADR-007
- Backend deployment modes and secrets: [`backends/fastapi/README.md`](backends/fastapi/README.md)
- Web cookie transport: [`apps/web/README.md`](apps/web/README.md)
- Mobile bearer transport: [`apps/mobile/README.md`](apps/mobile/README.md)
- Contract workflows: [`packages/api-contract/README.md`](packages/api-contract/README.md)

---

### Phase 1 — Pre-rollout gates

Run all of the following from the repository root before deploying to
a shared or production environment. Every command must exit 0.

```bash
# 1. Regenerate and validate the OpenAPI contract
npm run generate -w @ai-fullstack-starter/api-contract
npm test -w @ai-fullstack-starter/api-contract
npm run typecheck -w @ai-fullstack-starter/api-contract

# 2. Backend lint and full test suite (includes startup matrix,
#    protected session fixture tests, and contract drift guard)
cd backends/fastapi && .venv/bin/ruff check . && .venv/bin/pytest -q
cd "$OLDPWD"

# 3. Web build and type check
npm run typecheck -w @ai-fullstack-starter/web
npm test -w @ai-fullstack-starter/web
npm run build -w @ai-fullstack-starter/web

# 4. Mobile type check and export
npm run typecheck -w @ai-fullstack-starter/mobile
npm test -w @ai-fullstack-starter/mobile

# 5. Fail-closed startup validation — must exit nonzero
DEPLOYMENT_MODE=shared-demo backends/fastapi/.venv/bin/python -c "
from app.config.settings import Settings
try:
    Settings(_env_file=None)
    raise SystemExit('ERROR: shared-demo must fail without SESSION_SECRET')
except Exception as e:
    print(f'OK: startup correctly rejected: {e}')
" && echo "PASS: fail-closed check"

# 6. Protected-mode live conformance
#    Start backend with a CI-only placeholder secret, then run conformance
cd backends/fastapi
DEPLOYMENT_MODE=shared-demo \
SESSION_SECRET=pre-rollout-ci-only-placeholder-not-for-production \
.venv/bin/uvicorn app.main:app --port 8000 &
SERVER_PID=$!
trap 'kill "$SERVER_PID" 2>/dev/null' EXIT
sleep 2
CONTRACT_BASE_URL=http://127.0.0.1:8000 \
npm run test:conformance -w @ai-fullstack-starter/api-contract
kill "$SERVER_PID"
cd "$OLDPWD"
```

---

### Phase 2 — Canary validation

Deploy the new artifact to a canary target using the production
`SESSION_SECRET` and `DEPLOYMENT_MODE=shared-demo` (or `production`).
Then verify each item below before expanding the rollout.

#### Health (public endpoint — must always return 200)

```bash
curl -sf http://<CANARY_HOST>/api/v1/health
# Expected: {"status":"ok","version":"1.0.0"}
```

A green health check confirms the backend started and is serving
requests. It does **not** confirm that protected learning is enforced —
complete the remaining canary items.

#### Unauthenticated protected learning — must return 401

```bash
# GET /learning/state without a session → 401 unauthorized
curl -s http://<CANARY_HOST>/api/v1/learning/state?concept=additive-versioning
# Expected: {"error":{"code":"unauthorized","message":"..."}}

# POST /quiz/answer without a session → 401 unauthorized
curl -s -X POST http://<CANARY_HOST>/api/v1/learning/quiz/answer \
  -H 'content-type: application/json' \
  -d '{"concept":"provider-fallback-pattern","selected_answer":"any"}'
# Expected: {"error":{"code":"unauthorized","message":"..."}}
```

If either returns 200, the backend is running in `local` mode or
authentication is not enforced. **Do not go live** — trigger rollback.

#### Authenticated protected learning — must return 200

Bootstrap a session and verify that a signed request updates the
caller's own learner state:

```bash
# 1. Bootstrap session
SESSION_RESPONSE=$(curl -s -X POST http://<CANARY_HOST>/api/v1/session/bootstrap \
  -H 'content-type: application/json' \
  -d '{"transport":"bearer"}')
TOKEN=$(echo "$SESSION_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

# 2. Submit a quiz answer with the session token
curl -s -X POST http://<CANARY_HOST>/api/v1/learning/quiz/answer \
  -H 'content-type: application/json' \
  -H "authorization: Bearer $TOKEN" \
  -d '{"concept":"provider-fallback-pattern","selected_answer":"So a flaky LLM provider degrades to a deterministic explanation instead of crashing a live demo"}'
# Expected: {"user_id":"<session-subject>","is_correct":true,...}
```

Verify that `user_id` in the response matches the session subject, not
a client-supplied value.

#### Web cookie propagation

Open `apps/web` against the canary backend. Use browser dev tools to
confirm:

1. `POST /api/v1/session/bootstrap` sets an HttpOnly session cookie.
2. Subsequent requests to `web/components/adaptive-tutor.tsx` and
   `web/components/retention-quiz.tsx` include the cookie and return
   200 (not 401).
3. No hard-coded `user_id` appears in the request payloads.

#### Mobile bearer token propagation

Run `apps/mobile` against the canary backend. Verify:

1. App mount calls `bootstrapSession()` via `mobile/lib/api.ts`.
2. Learning requests include `Authorization: Bearer <token>` and
   return 200 (not 401).
3. No signing secret or token value appears in `EXPO_PUBLIC_*`
   variables or bundled source.

---

### Phase 3 — Go / no-go criteria

**Go — all of the following must be true:**

- [ ] Phase 1 pre-rollout gates: all commands exit 0
- [ ] `/api/v1/health` returns 200 on canary
- [ ] Unauthenticated `/api/v1/learning/state` returns 401 on canary
- [ ] Authenticated `POST /api/v1/learning/quiz/answer` returns 200 with session-derived `user_id`
- [ ] Web cookie session propagation verified — no 401 from `adaptive-tutor.tsx` or `retention-quiz.tsx`
- [ ] Mobile bearer token propagation verified — no 401 from `mobile/lib/api.ts` learning calls
- [ ] Interactive docs (`/docs`, `/redoc`) return 404 on canary — confirms protected-mode startup

**No-go / rollback triggers — rollback immediately if any of the following occur:**

- [ ] Backend refuses to start in shared-demo or production mode → startup validation failed
- [ ] `cd backends/fastapi && .venv/bin/pytest tests/test_contract_drift.py -q` exits nonzero → contract drift against `packages/api-contract/openapi.yaml`
- [ ] Unauthenticated `/api/v1/learning/state` returns 200 instead of 401 → authentication not enforced
- [ ] Spike in 401 responses during canary traffic for sessions that were bootstrapped successfully → session validation regression
- [ ] `web/components/retention-quiz.tsx` or `web/components/adaptive-tutor.tsx` flows fail with 401 after successful cookie bootstrap → web cookie transport broken
- [ ] Mobile learning calls return 401 after successful `bootstrapSession()` → bearer token propagation broken
- [ ] `npm run generate -w @ai-fullstack-starter/api-contract` followed by `npm test -w @ai-fullstack-starter/api-contract` exits nonzero → OpenAPI spec drift

---

### Phase 4 — Rollback

If a no-go trigger fires, execute these steps in order:

```bash
# 1. Redeploy the previous known-good artifact
#    (Replace <PREVIOUS_TAG> with the last passing release reference)
#    Use the same deployment mechanism used for the canary promotion.

# 2. Restore the prior protected-mode configuration
#    Re-supply SESSION_SECRET and DEPLOYMENT_MODE from managed secrets
#    for the previous release.  Do not revert to local mode in a
#    shared or production environment — restore the prior protected config.

# 3. Confirm /api/v1/health on the reverted deployment
curl -sf http://<HOST>/api/v1/health
# Expected: {"status":"ok","version":"<PREVIOUS_VERSION>"}

# 4. Confirm 401 enforcement is restored
curl -s http://<HOST>/api/v1/learning/state?concept=additive-versioning
# Expected: {"error":{"code":"unauthorized","message":"..."}}

# 5. Re-run the pre-rollout conformance gate against the restored backend
CONTRACT_BASE_URL=http://<HOST> \
npm run test:conformance -w @ai-fullstack-starter/api-contract
```

> **⚠ In-memory learner state is not durable.**
> `fastapi/app/learning/repository.py` stores all learner progress in
> memory. Any progress recorded during the canary window is lost after
> process restart. Do not promise learner-state restoration to users
> during rollback. Durable persistence requires a future repository
> implementation.

#### Rollback complete when:

- [ ] `/api/v1/health` returns 200 with the previous version string
- [ ] Unauthenticated `/api/v1/learning/state` returns 401 (protected mode still active)
- [ ] Contract conformance suite exits 0 against the restored backend
- [ ] Incident documented with rollback trigger, affected session count, and timeline
