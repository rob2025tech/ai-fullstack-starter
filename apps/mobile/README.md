# Mobile client (Expo)

Single-screen chat UI consuming the `/api/v1` contract via types from
`packages/api-contract`. No secrets live here — only the backend base
URL (`EXPO_PUBLIC_API_BASE_URL`, default `http://127.0.0.1:8000`).

## Run

```bash
# from the repo root; backend must be running (see backends/fastapi)
npm run start -w @ai-fullstack-starter/mobile   # Metro dev server
```

Native directories are generated, not committed. To run on a
simulator/emulator use the native workflow (generates `ios/` or
`android/` on first run):

```bash
npm run ios -w @ai-fullstack-starter/mobile     # expo run:ios
npm run android -w @ai-fullstack-starter/mobile # expo run:android
```

Alternatively, scan the QR code from `expo start` with Expo Go if the
installed SDK is still supported there.

Note: `http://127.0.0.1` only works from a simulator on the same
machine. A physical device needs the machine's LAN IP in
`EXPO_PUBLIC_API_BASE_URL` (copy `.env.example` to `.env`).

## Scripts

```bash
npm test             # vitest (contract client)
npm run typecheck    # tsc --noEmit
npm run export       # expo export (headless bundle check)
```

## Notes

- Day-1 uses the contract's **JSON mode** (`stream: false`): React
  Native fetch streaming is inconsistent across platforms, and the
  non-streaming response is the same `ChatResponse` shape the SSE
  terminal `message` event carries. Switching to SSE later is additive
  — no contract change needed (ADR-003).
- Contract types come from `@ai-fullstack-starter/api-contract`; run
  `npm run generate -w @ai-fullstack-starter/api-contract` after any
  spec change. `metro.config.js` watches the repo root so the workspace
  package is bundled directly from source.
