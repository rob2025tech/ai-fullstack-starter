import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import YAML from "yaml";

const spec = YAML.parse(
  readFileSync(new URL("../openapi.yaml", import.meta.url), "utf8"),
) as Record<string, unknown>;

describe("canonical OpenAPI spec", () => {
  it("is OpenAPI 3.1 with a semver contract version", () => {
    expect(String(spec.openapi)).toMatch(/^3\.1/);
    const version = (spec.info as { version: string }).version;
    expect(version).toMatch(/^\d+\.\d+\.\d+$/);
  });

  it("exposes the v1 health and chat endpoints", () => {
    const paths = Object.keys(spec.paths as object);
    expect(paths).toContain("/api/v1/health");
    expect(paths).toContain("/api/v1/chat");
  });

  it("serves chat responses as JSON and SSE", () => {
    const chat = (spec.paths as any)["/api/v1/chat"].post;
    const ok = chat.responses["200"].content;
    expect(Object.keys(ok)).toEqual(
      expect.arrayContaining(["application/json", "text/event-stream"]),
    );
  });

  it("pins the full error code registry", () => {
    const error = (spec.components as any).schemas.Error;
    expect(error.properties.code.enum.sort()).toEqual(
      [
        "internal_error",
        "invalid_request",
        "provider_error",
        "provider_unavailable",
        "rate_limited",
        "unauthorized",
      ].sort(),
    );
  });

  it("includes unauthorized in the error code registry", () => {
    const error = (spec.components as any).schemas.Error;
    expect(error.properties.code.enum).toContain("unauthorized");
  });

  it("defines cookie and bearer session security schemes", () => {
    const schemes = (spec.components as any).securitySchemes;
    expect(schemes).toBeDefined();
    // Cookie scheme
    expect(schemes.sessionCookie).toBeDefined();
    expect(schemes.sessionCookie.type).toBe("apiKey");
    expect(schemes.sessionCookie.in).toBe("cookie");
    expect(typeof schemes.sessionCookie.name).toBe("string");
    expect(schemes.sessionCookie.name.length).toBeGreaterThan(0);
    // Bearer scheme
    expect(schemes.sessionBearer).toBeDefined();
    expect(schemes.sessionBearer.type).toBe("http");
    expect(schemes.sessionBearer.scheme).toBe("bearer");
  });

  it("defines a reusable Unauthorized response referencing ErrorResponse", () => {
    const responses = (spec.components as any).responses;
    expect(responses.Unauthorized).toBeDefined();
    const schema = responses.Unauthorized.content["application/json"].schema;
    expect(schema.$ref).toBe("#/components/schemas/ErrorResponse");
  });

  it("applies security and 401 to all protected learning operations", () => {
    const paths = spec.paths as any;
    const protectedOps: Array<[string, string]> = [
      ["/api/v1/learning/state", "get"],
      ["/api/v1/learning/answer", "post"],
      ["/api/v1/learning/quiz/answer", "post"],
      ["/api/v1/learning/quiz/practice", "post"],
      ["/api/v1/learning/quiz/retest", "post"],
    ];
    for (const [path, method] of protectedOps) {
      const op = paths[path]?.[method];
      expect(op, `operation ${method.toUpperCase()} ${path}`).toBeDefined();
      // Must declare a 401 response
      expect(
        op.responses["401"],
        `401 missing on ${method.toUpperCase()} ${path}`,
      ).toBeDefined();
      expect(op.responses["401"].$ref).toBe("#/components/responses/Unauthorized");
      // Must declare a security requirement
      expect(
        op.security,
        `security missing on ${method.toUpperCase()} ${path}`,
      ).toBeDefined();
      expect(Array.isArray(op.security)).toBe(true);
      expect(op.security.length).toBeGreaterThan(0);
    }
  });

  it("leaves health and chat endpoints anonymous (no security requirement)", () => {
    const paths = spec.paths as any;
    expect(paths["/api/v1/health"].get.security).toBeUndefined();
    expect(paths["/api/v1/chat"].post.security).toBeUndefined();
  });

  it("resolves every local $ref", () => {
    const refs: string[] = [];
    const walk = (node: unknown): void => {
      if (Array.isArray(node)) {
        node.forEach(walk);
        return;
      }
      if (node && typeof node === "object") {
        for (const [key, value] of Object.entries(node)) {
          if (key === "$ref" && typeof value === "string") refs.push(value);
          else walk(value);
        }
      }
    };
    walk(spec);
    expect(refs.length).toBeGreaterThan(0);
    for (const ref of refs) {
      expect(ref.startsWith("#/"), ref).toBe(true);
      let cursor: unknown = spec;
      for (const segment of ref.slice(2).split("/")) {
        cursor = (cursor as Record<string, unknown>)?.[segment];
        expect(cursor, `unresolved ref ${ref}`).toBeDefined();
      }
    }
  });
});
