import { afterEach, describe, expect, it, vi } from "vitest";

import { BASE_URL, ContractError, bootstrapSession, sendChat } from "./api";

// ---------------------------------------------------------------------------
// Deterministic response fixtures (AC-6)
// ---------------------------------------------------------------------------

const CHAT_RESPONSE_FIXTURE = {
  message: {
    id: "msg_1",
    role: "assistant",
    content: "echo: hi",
    finish_reason: "stop",
  },
  usage: null,
};

const SESSION_BOOTSTRAP_RESPONSE_FIXTURE = {
  user_id: "anon-abc123",
  expires_at: "2026-10-24T00:00:00Z",
  token_type: "bearer",
  access_token: "test-session-token",
};

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

afterEach(() => {
  vi.unstubAllGlobals();
});

// ---------------------------------------------------------------------------
// bootstrapSession (AC-2, AC-6)
// ---------------------------------------------------------------------------

describe("bootstrapSession", () => {
  it("calls the bootstrap endpoint and returns the session token (AC-2)", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => jsonResponse(200, SESSION_BOOTSTRAP_RESPONSE_FIXTURE)),
    );

    const result = await bootstrapSession();

    expect(result.access_token).toBe("test-session-token");
    expect(result.token_type).toBe("bearer");
    expect(result.user_id).toBe("anon-abc123");
    const [url, init] = (fetch as ReturnType<typeof vi.fn>).mock.calls[0] as [string, RequestInit];
    expect(url).toBe(`${BASE_URL}/api/v1/session/bootstrap`);
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body as string)).toEqual({ transport: "bearer" });
  });

  it("throws ContractError on non-2xx response (AC-2)", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        jsonResponse(401, {
          error: { code: "unauthorized", message: "session authentication required" },
        }),
      ),
    );

    await expect(bootstrapSession()).rejects.toMatchObject({
      code: "unauthorized",
      message: "session authentication required",
    });
  });

  it("throws ContractError with provider_unavailable on network failure", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new Error("connection refused");
      }),
    );

    const error = await bootstrapSession().catch((e) => e);
    expect(error).toBeInstanceOf(ContractError);
    expect((error as ContractError).code).toBe("provider_unavailable");
  });
});

// ---------------------------------------------------------------------------
// sendChat — bearer token behavior (AC-3, AC-4)
// ---------------------------------------------------------------------------

describe("sendChat — bearer token", () => {
  it("sends Authorization: Bearer header when sessionToken is supplied (AC-4)", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => jsonResponse(200, CHAT_RESPONSE_FIXTURE)),
    );

    await sendChat({ prompt: "hello" }, { sessionToken: "test-session-token" });

    const [url, init] = (fetch as ReturnType<typeof vi.fn>).mock.calls[0] as [string, RequestInit];
    expect(url).toBe(`${BASE_URL}/api/v1/chat`);
    const headers = init.headers as Record<string, string>;
    expect(headers["authorization"]).toBe("Bearer test-session-token");
  });

  it("still sends stream: false in body when session token is provided (AC-3)", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => jsonResponse(200, CHAT_RESPONSE_FIXTURE)),
    );

    await sendChat({ prompt: "hello" }, { sessionToken: "test-session-token" });

    const [, init] = (fetch as ReturnType<typeof vi.fn>).mock.calls[0] as [string, RequestInit];
    expect(JSON.parse(init.body as string)).toMatchObject({ prompt: "hello", stream: false });
  });

  it("omits Authorization header when no sessionToken is provided (AC-4)", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => jsonResponse(200, CHAT_RESPONSE_FIXTURE)),
    );

    await sendChat({ prompt: "hello" });

    const [, init] = (fetch as ReturnType<typeof vi.fn>).mock.calls[0] as [string, RequestInit];
    const headers = init.headers as Record<string, string>;
    expect(headers["authorization"]).toBeUndefined();
  });

  it("omits Authorization header when sessionToken is empty string (AC-4 edge case)", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => jsonResponse(200, CHAT_RESPONSE_FIXTURE)),
    );

    await sendChat({ prompt: "hello" }, { sessionToken: "" });

    const [, init] = (fetch as ReturnType<typeof vi.fn>).mock.calls[0] as [string, RequestInit];
    const headers = init.headers as Record<string, string>;
    expect(headers["authorization"]).toBeUndefined();
  });
});

// ---------------------------------------------------------------------------
// sendChat — original behavior preserved (AC-3)
// ---------------------------------------------------------------------------

describe("sendChat", () => {
  it("returns the ChatResponse envelope on success", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => jsonResponse(200, CHAT_RESPONSE_FIXTURE)));

    const result = await sendChat({ prompt: "hi" });

    expect(result.message.content).toBe("echo: hi");
    const [url, init] = (fetch as ReturnType<typeof vi.fn>).mock.calls[0] as [string, RequestInit];
    expect(url.endsWith("/api/v1/chat")).toBe(true);
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body as string)).toEqual({ prompt: "hi", stream: false });
  });

  it("maps a contract error envelope to ContractError", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        jsonResponse(422, {
          error: { code: "invalid_request", message: "prompt is required" },
        }),
      ),
    );

    await expect(sendChat({ prompt: "x" })).rejects.toMatchObject({
      code: "invalid_request",
      message: "prompt is required",
    });
  });

  it("falls back to a generic error for non-JSON error bodies", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        new Response("gateway exploded", {
          status: 502,
          headers: { "content-type": "text/plain" },
        }),
      ),
    );

    await expect(sendChat({ prompt: "x" })).rejects.toMatchObject({
      code: "internal_error",
      message: "request failed with HTTP 502",
    });
  });

  it("maps network failure to provider_unavailable", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new Error("connection refused");
      }),
    );

    const error = await sendChat({ prompt: "x" }).catch((e) => e);
    expect(error).toBeInstanceOf(ContractError);
    expect((error as ContractError).code).toBe("provider_unavailable");
  });
});

// ---------------------------------------------------------------------------
// Fixture shape verification (AC-6)
// ---------------------------------------------------------------------------

describe("fixture shapes", () => {
  it("CHAT_RESPONSE_FIXTURE has required ChatResponse fields", () => {
    expect(CHAT_RESPONSE_FIXTURE.message.id).toBeTruthy();
    expect(CHAT_RESPONSE_FIXTURE.message.role).toBe("assistant");
    expect(CHAT_RESPONSE_FIXTURE.message.content).toBeTruthy();
  });

  it("SESSION_BOOTSTRAP_RESPONSE_FIXTURE has required SessionBootstrapResponse fields", () => {
    expect(SESSION_BOOTSTRAP_RESPONSE_FIXTURE.user_id).toBeTruthy();
    expect(SESSION_BOOTSTRAP_RESPONSE_FIXTURE.expires_at).toBeTruthy();
    expect(SESSION_BOOTSTRAP_RESPONSE_FIXTURE.token_type).toBe("bearer");
    expect(SESSION_BOOTSTRAP_RESPONSE_FIXTURE.access_token).toBeTruthy();
  });
});
