import { afterEach, describe, expect, it, vi } from "vitest";

import { ContractError, sendChat } from "./api";

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("sendChat", () => {
  it("returns the ChatResponse envelope on success", async () => {
    const body = {
      message: {
        id: "msg_1",
        role: "assistant",
        content: "echo: hi",
        finish_reason: "stop",
      },
      usage: null,
    };
    vi.stubGlobal("fetch", vi.fn(async () => jsonResponse(200, body)));

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
