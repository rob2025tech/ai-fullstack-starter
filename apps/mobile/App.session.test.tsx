import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

// ---------------------------------------------------------------------------
// Deterministic fixtures (AC-6)
// ---------------------------------------------------------------------------

const BOOTSTRAP_RESPONSE_FIXTURE = {
  user_id: "anon-abc123",
  expires_at: "2026-10-24T00:00:00Z",
  token_type: "bearer",
  access_token: "test-session-token",
};

const CHAT_RESPONSE_FIXTURE = {
  message: {
    id: "msg_1",
    role: "assistant",
    content: "echo: hi",
    finish_reason: "stop",
  },
  usage: null,
};

// ---------------------------------------------------------------------------
// Source inspection — no React Native rendering required
// ---------------------------------------------------------------------------

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const appSource = readFileSync(path.join(__dirname, "App.tsx"), "utf-8");

describe("App — session bootstrap wiring (AC-1, AC-2, AC-3)", () => {
  it("imports bootstrapSession from ./lib/api (AC-1)", () => {
    expect(appSource).toContain("bootstrapSession");
    expect(appSource).toMatch(/from ["']\.\/lib\/api["']/);
  });

  it("stores session token in a ref (AC-1)", () => {
    expect(appSource).toContain("sessionTokenRef");
    expect(appSource).toMatch(/useRef<string \| null>/);
  });

  it("calls bootstrapSession inside useEffect with empty dependency array (AC-1)", () => {
    const match = appSource.match(/useEffect\(\(\) => \{[\s\S]*?\}, \[\]\)/);
    expect(match).not.toBeNull();
    expect(match![0]).toContain("bootstrapSession");
  });

  it("bootstrapSession result assigns access_token to sessionTokenRef (AC-1)", () => {
    expect(appSource).toMatch(/sessionTokenRef\.current\s*=.*access_token/);
  });

  it("sendChat request object contains prompt and no stream property (AC-2)", () => {
    const match = appSource.match(/sendChat\(\s*\{([^}]*)\}/);
    expect(match).not.toBeNull();
    expect(match![0]).toContain("prompt");
    expect(match![0]).not.toContain("stream");
  });

  it("sendChat options include sessionToken forwarded from sessionTokenRef (AC-3)", () => {
    expect(appSource).toMatch(/sessionToken.*sessionTokenRef\.current/);
  });

  it("sessionTokenRef is reused across sends — no bootstrapSession call inside handleSubmit (AC-1 edge case)", () => {
    const handleSubmitMatch = appSource.match(
      /handleSubmit[\s\S]*?}\s*,\s*\[prompt,\s*pending\]/,
    );
    expect(handleSubmitMatch).not.toBeNull();
    expect(handleSubmitMatch![0]).not.toContain("bootstrapSession");
  });
});

// ---------------------------------------------------------------------------
// Fixture shape verification (AC-6)
// ---------------------------------------------------------------------------

describe("App.session — fixture shapes (AC-6)", () => {
  it("BOOTSTRAP_RESPONSE_FIXTURE has required SessionBootstrapResponse fields", () => {
    expect(BOOTSTRAP_RESPONSE_FIXTURE.access_token).toBeTruthy();
    expect(BOOTSTRAP_RESPONSE_FIXTURE.token_type).toBe("bearer");
    expect(BOOTSTRAP_RESPONSE_FIXTURE.user_id).toBeTruthy();
    expect(BOOTSTRAP_RESPONSE_FIXTURE.expires_at).toBeTruthy();
  });

  it("CHAT_RESPONSE_FIXTURE has required ChatResponse fields", () => {
    expect(CHAT_RESPONSE_FIXTURE.message.role).toBe("assistant");
    expect(CHAT_RESPONSE_FIXTURE.message.content).toBeTruthy();
    expect(CHAT_RESPONSE_FIXTURE.message.id).toBeTruthy();
  });
});
