import { describe, expect, it } from "vitest";
import { createSseParser, type SseEvent } from "./sse";

function collect(chunks: string[]): SseEvent[] {
  const events: SseEvent[] = [];
  const parser = createSseParser((event) => events.push(event));
  for (const chunk of chunks) parser.push(chunk);
  return events;
}

describe("createSseParser", () => {
  it("parses complete events with names and data", () => {
    const events = collect([
      'event: delta\ndata: {"content":"he"}\n\nevent: message\ndata: {"message":{}}\n\n',
    ]);
    expect(events).toEqual([
      { name: "delta", data: '{"content":"he"}' },
      { name: "message", data: '{"message":{}}' },
    ]);
  });

  it("handles events split across chunk boundaries", () => {
    const events = collect(["event: del", 'ta\ndata: {"conte', 'nt":"hi"}\n\n']);
    expect(events).toEqual([{ name: "delta", data: '{"content":"hi"}' }]);
  });

  it("defaults the event name to message", () => {
    const events = collect(['data: {"ok":true}\n\n']);
    expect(events).toEqual([{ name: "message", data: '{"ok":true}' }]);
  });

  it("holds back incomplete trailing events", () => {
    const events = collect(['event: delta\ndata: {"content":"a"}\n\nevent: delta\nda']);
    expect(events).toHaveLength(1);
  });
});
