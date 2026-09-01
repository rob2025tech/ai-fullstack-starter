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
