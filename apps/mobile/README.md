# Mobile client (Expo)

Single-screen chat UI consuming the `/api/v1` contract via types from
`packages/api-contract`.

The recommended development workflow uses the Mac's **LAN IP** for both
Expo/Metro and the FastAPI backend. This works for both a **physical iPhone**
and the **iPhone Simulator**.

## Prerequisites

From the repository root:

```bash
nvm use 24
npm ci
```

You also need:

* Xcode and the iOS Simulator for simulator development
* Expo Go on a physical iPhone
* A compatible Expo Go 57 build in the iOS Simulator
* The FastAPI backend running on port `8000`

## 1. Configure the backend URL

Create the mobile environment file:

```bash
cp apps/mobile/.env.example apps/mobile/.env
```

Set the Mac's LAN IP:

```text
EXPO_PUBLIC_API_BASE_URL=http://<MAC-LAN-IP>:8000
```

For example:

```text
EXPO_PUBLIC_API_BASE_URL=http://192.168.0.34:8000
```

Do **not** use `127.0.0.1` for the normal physical-device/Simulator
workflow.

`EXPO_PUBLIC_*` values are bundled when Expo starts, so restart Expo after
changing `.env`.

### Find the Mac's LAN IP

On this Mac, try:

```bash
ipconfig getifaddr en0
```

If that does not return an address, check:

**System Settings → Network**

If the Mac's LAN IP changes, update `apps/mobile/.env` and restart Expo.

---

## 2. Start FastAPI

From the repository root:

```bash
cd backends/fastapi
.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

The `0.0.0.0` binding is important: physical devices and the LAN-based
Simulator must be able to reach the Mac.

Verify the backend locally:

```bash
curl http://127.0.0.1:8000/api/v1/health
```

Expected:

```json
{"status":"ok","version":"1.0.0"}
```

---

## 3. Start Expo/Metro

From the repository root:

```bash
nvm use 24
npm run start --workspace=@ai-fullstack-starter/mobile -- --host lan
```

Use the normal Metro port, **8081**.

Expo should advertise a URL similar to:

```text
exp://192.168.0.34:8081
```

Leave this terminal running.

### Permanent development rule

**Use Expo LAN mode on port `8081` and the Mac's LAN IP.**

Do not normally start a second Metro server on `8082` or another temporary
port.

---

# Physical iPhone

This is the normal workflow for a real iPhone.

### 1. Connect the iPhone and Mac to the same network

The iPhone must be able to reach the Mac over the LAN.

### 2. Start FastAPI

```bash
cd backends/fastapi
.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### 3. Start Expo in LAN mode

From the repository root:

```bash
npm run start --workspace=@ai-fullstack-starter/mobile -- --host lan
```

### 4. Open Expo Go on the iPhone

Scan the QR code displayed by Expo.

The connection is:

```text
Physical iPhone
      │
      ├── Expo/Metro ──> Mac LAN IP :8081
      │
      └── FastAPI ─────> Mac LAN IP :8000
```

No `xcrun simctl` command is needed for a physical iPhone.

---

# iPhone Simulator

The iPhone Simulator uses the same LAN-based Expo workflow.

### 1. Boot the Simulator

```bash
open -a Simulator
```

Or boot a specific simulator through Xcode or `simctl`.

### 2. Start FastAPI

```bash
cd backends/fastapi
.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### 3. Start Expo in LAN mode

From the repository root:

```bash
nvm use 24
npm run start --workspace=@ai-fullstack-starter/mobile -- --host lan
```

### 4. Open the project in Expo Go

Use the Mac's current LAN IP:

```bash
xcrun simctl openurl booted 'exp://<MAC-LAN-IP>:8081'
```

For example:

```bash
xcrun simctl openurl booted 'exp://192.168.0.34:8081'
```

This opens the project in Expo Go.

The connection is:

```text
iPhone Simulator
      │
      │ exp://192.168.0.34:8081
      ▼
     Mac
      │
      ├── Expo/Metro :8081
      │
      └── FastAPI     :8000
```

---

# Why LAN mode is the standard workflow

Expo's `--localhost` mode caused problems in this development environment.

During debugging, Metro under `--localhost` listened on IPv6 loopback:

```text
[::1]:8081
```

while Expo Go was given bundle URLs involving:

```text
127.0.0.1:8081
```

The resulting behavior was inconsistent:

* `localhost` could reach Metro in some contexts.
* `[::1]` could reach Metro from Simulator Safari.
* `127.0.0.1` could not reach that Metro listener.
* Expo Go could not reliably load the project using the localhost URLs.
* Opening the IPv6 Expo URL caused Expo Go to crash in its network-interceptor
  code before the application JavaScript ran.

The LAN workflow avoids this localhost/IPv4/IPv6 ambiguity.

Therefore, use:

```bash
npm run start --workspace=@ai-fullstack-starter/mobile -- --host lan
```

and:

```text
exp://<MAC-LAN-IP>:8081
```

Do **not** use these as the normal workflow:

```bash
npm run start --workspace=@ai-fullstack-starter/mobile -- --localhost
```

```text
exp://127.0.0.1:8081
```

```text
exp://[::1]:8081
```

---

# Troubleshooting

## Check whether Metro is running

```bash
lsof -nP -iTCP:8081 -sTCP:LISTEN
```

Normally there should be one Metro/Node process listening on `8081`.

You can also verify Metro directly from the Mac:

```bash
curl http://<MAC-LAN-IP>:8081
```

A JSON Expo manifest indicates that Metro is responding.

## Check the backend

```bash
curl http://127.0.0.1:8000/api/v1/health
```

If the backend is running but devices cannot connect, make sure it was started
with:

```bash
--host 0.0.0.0
```

rather than only:

```bash
--host 127.0.0.1
```

## Check for a leftover temporary Metro server

If you previously used another port:

```bash
lsof -nP -iTCP:8082 -sTCP:LISTEN
```

A normal clean setup should not need anything on `8082`.

If an old temporary Metro process is still running, stop it before restarting
the normal `8081` workflow.

## Restart after changing `.env`

Because `EXPO_PUBLIC_API_BASE_URL` is bundled into the app, changing `.env`
requires restarting Expo.

Stop Metro with `Ctrl-C`, then run:

```bash
npm run start --workspace=@ai-fullstack-starter/mobile -- --host lan
```

## Simulator cannot open the project

Make sure:

1. The Simulator is booted.
2. FastAPI is running on `0.0.0.0:8000`.
3. Metro is running in LAN mode on `8081`.
4. `.env` contains the Mac's current LAN IP.
5. The URL uses the Mac's LAN IP rather than `127.0.0.1` or `[::1]`.

Then run:

```bash
xcrun simctl openurl booted 'exp://<MAC-LAN-IP>:8081'
```

If Expo Go itself is malfunctioning, reinstall a Simulator Expo Go build
compatible with SDK 57 rather than assuming the currently installed build is
correct.

---

# Native workflows

Native directories are generated and are not committed.

For a native iOS build:

```bash
npm run ios -w @ai-fullstack-starter/mobile
```

For Android:

```bash
npm run android -w @ai-fullstack-starter/mobile
```

These are separate from the normal Expo Go development workflow.

For ordinary JavaScript/UI development, use Expo Go with the LAN workflow
documented above.

---

# Scripts

```bash
npm test             # vitest (contract client)
npm run typecheck    # tsc --noEmit
npm run export       # expo export (headless bundle check)
```

---

# Architecture notes

* Day-1 uses the contract's **JSON mode** (`stream: false`): React Native
  fetch streaming is inconsistent across platforms, and the non-streaming
  response is the same `ChatResponse` shape the SSE terminal `message` event
  carries. Switching to SSE later is additive — no contract change needed
  (ADR-003).
* Contract types come from `@ai-fullstack-starter/api-contract`.
* After a spec change, regenerate the contract:

```bash
npm run generate -w @ai-fullstack-starter/api-contract
```

* `metro.config.js` watches the repository root so the workspace package is
  bundled directly from source.

---

# Protected learning transport

Learning mutation endpoints (`POST /api/v1/learning/answer`,
`POST /api/v1/learning/quiz/answer`, `POST /api/v1/learning/quiz/practice`,
`POST /api/v1/learning/quiz/retest`) require session authentication in
`shared-demo` and `production` deployment modes. Expo and React Native
clients use **bearer-token transport** because React Native networking does
not share the browser cookie lifecycle.

## Token bootstrap via `mobile/lib/api.ts`

Call `bootstrapSession()` from `mobile/lib/api.ts` once on app mount to
obtain a short-lived signed token:

```ts
import { bootstrapSession } from './lib/api';

// On app mount — store in a React ref, not AsyncStorage or SecureStore
const session = await bootstrapSession();
// session.access_token is the signed bearer token
```

Store the token in a `React.useRef` for the lifetime of the app session.
Do **not** persist it to `AsyncStorage`, `SecureStore`, the keychain, or
any other durable storage — the token is short-lived and must be
re-bootstrapped on each app launch.

## Authorization header propagation

Pass the session token to `sendChat` and any future protected learning
helpers via the `sessionToken` option in `mobile/lib/api.ts`:

```ts
await sendChat({ prompt }, { sessionToken: session.access_token });
```

For protected learning endpoints, set the `Authorization` header:

```ts
headers: { 'Authorization': 'Bearer <token>' }
```

Replace `<token>` with the value returned by `bootstrapSession()`. Never
commit a real token or signing secret to source.

## Learner identity is backend-derived

The backend derives learner identity exclusively from the signed session
token. Any `user_id` field in a request body is ignored by protected
endpoints. Do not pass a hard-coded learner identifier from the mobile
client for learning mutations.

## Secrets stay in the backend

`EXPO_PUBLIC_*` variables are bundled into the app binary and are visible
to anyone who inspects it. Do **not** place session signing secrets, API
keys, or long-lived tokens in `EXPO_PUBLIC_API_BASE_URL` or any other
`EXPO_PUBLIC_*` variable. All secret values live in backend configuration
(see `backends/fastapi/app/config/settings.py`).

## JSON-mode chat is unchanged (ADR-006)

Protected learning bearer transport does **not** require SSE support.
`POST /api/v1/chat` continues to use `stream: false` JSON mode on day-one
mobile (ADR-006). Adding an `Authorization` header to future learning calls
is orthogonal to the chat transport — it does not change the chat endpoint
shape and does not require an SSE polyfill.

## Error handling

A `401 Unauthorized` response from a learning endpoint means the session
token is absent or expired. The `error.code` field in the response body
will be `"unauthorized"` (defined in `packages/api-contract/openapi.yaml`).
Re-bootstrap the session by calling `bootstrapSession()` again.

## Contract reference

Protected learning request and response shapes are governed by
`packages/api-contract/openapi.yaml`. TypeScript types are generated from
the spec — never hand-edit files under `packages/api-contract/src/generated/`.
Regenerate after any spec change:

```bash
npm run generate -w @ai-fullstack-starter/api-contract
```

---

# Quick reference

## Physical iPhone

```text
1. Mac + iPhone on same LAN
2. apps/mobile/.env → EXPO_PUBLIC_API_BASE_URL=http://<MAC-LAN-IP>:8000
3. FastAPI → 0.0.0.0:8000
4. Expo → --host lan → :8081
5. Scan Expo QR code with Expo Go
```

## iPhone Simulator

```text
1. Boot Simulator
2. apps/mobile/.env → EXPO_PUBLIC_API_BASE_URL=http://<MAC-LAN-IP>:8000
3. FastAPI → 0.0.0.0:8000
4. Expo → --host lan → :8081
5. xcrun simctl openurl booted 'exp://<MAC-LAN-IP>:8081'
```

**Permanent rule:** Expo LAN + port `8081` + Mac LAN IP for both physical
iPhone and iPhone Simulator.
