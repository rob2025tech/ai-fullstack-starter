# Web client (Next.js)

Chat UI consuming the `/api/v1` contract via types generated in
`packages/api-contract`. No secrets live here — only the backend base
URL (`NEXT_PUBLIC_API_BASE_URL`, default `http://127.0.0.1:8000`).

## Run

```bash
# from the repo root; backend must be running (see backends/fastapi)
npm run dev -w @ai-fullstack-starter/web
```

Then open http://localhost:3000 and send a prompt — the mock backend
echoes it back, streamed token-by-token over SSE.

## Scripts

```bash
npm run dev    # dev server (Turbopack default in Next 16)
npm run build  # production build
npm test       # vitest (SSE parser)
npm run lint   # eslint flat config
```

## Notes

- Next 16: read `node_modules/next/dist/docs/` before making framework
  changes — see the repo-root AGENTS.md.
- Streaming path: `fetch` + ReadableStream + `lib/sse.ts` parser; the
  terminal `message` or `error` event ends the stream (ADR-003).
- Contract types come from `@ai-fullstack-starter/api-contract`; run
  `npm run generate -w @ai-fullstack-starter/api-contract` after any
  spec change.

## Protected learning transport

Learning mutation endpoints (`POST /api/v1/learning/answer`,
`POST /api/v1/learning/quiz/answer`, `POST /api/v1/learning/quiz/practice`,
`POST /api/v1/learning/quiz/retest`) require session authentication in
`shared-demo` and `production` deployment modes. The backend issues an
HttpOnly session cookie at `POST /api/v1/session/bootstrap`; the browser
then attaches it automatically on subsequent same-origin requests.

### Credential propagation in `web/lib/api.ts`

All protected learning requests must flow through `web/lib/api.ts` with
`credentials: 'include'` so the browser attaches the session cookie:

```ts
fetch(`${BASE_URL}/api/v1/learning/answer`, {
  method: 'POST',
  credentials: 'include',   // required for HttpOnly cookie transport
  headers: { 'content-type': 'application/json' },
  body: JSON.stringify(payload),
})
```

When `NEXT_PUBLIC_API_BASE_URL` points to a different origin the server
must respond with `Access-Control-Allow-Credentials: true` and an explicit
`Access-Control-Allow-Origin` header (not `*`) for the cookie to be
forwarded. Verify the CORS configuration in `backends/fastapi/app/config/`
before enabling cross-origin protected-mode learning.

### Learner identity is backend-derived

`web/components/retention-quiz.tsx` and `web/components/adaptive-tutor.tsx`
must **not** send or rely on a hard-coded learner identifier (e.g.,
`"demo-student"`) for protected learning mutations. The backend derives
learner identity exclusively from the session context; any `user_id` value
included in a request body is ignored by protected endpoints. Remove
client-side `user_id` fields before enabling protected-mode deployment.

### Error handling

A `401 Unauthorized` response from a learning endpoint means the session
cookie is absent or expired. The `error.code` field in the response body
will be `"unauthorized"` (defined in `packages/api-contract/openapi.yaml`).
Surface this state to the user and prompt a reload — the browser will
re-bootstrap a session cookie on the next page load.

### Contract reference

Protected learning request and response shapes are governed by
`packages/api-contract/openapi.yaml`. TypeScript types are generated from
the spec — never hand-edit files under `packages/api-contract/src/generated/`.
Regenerate after any spec change:

```bash
npm run generate -w @ai-fullstack-starter/api-contract
```
