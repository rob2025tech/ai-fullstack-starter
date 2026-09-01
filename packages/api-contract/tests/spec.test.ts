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
      ].sort(),
    );
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
