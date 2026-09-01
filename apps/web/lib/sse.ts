export interface SseEvent {
  name: string;
  data: string;
}

/**
 * Incremental SSE parser for fetch streaming: feed raw chunks via push();
 * complete events are delivered as they terminate with a blank line.
 */
export function createSseParser(onEvent: (event: SseEvent) => void): {
  push: (chunk: string) => void;
} {
  let buffer = "";
  return {
    push(chunk: string) {
      buffer += chunk;
      let separator: number;
      while ((separator = buffer.indexOf("\n\n")) !== -1) {
        const raw = buffer.slice(0, separator);
        buffer = buffer.slice(separator + 2);
        let name = "message";
        const dataLines: string[] = [];
        for (const line of raw.split("\n")) {
          if (line.startsWith("event:")) name = line.slice(6).trim();
          else if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
        }
        if (dataLines.length > 0) {
          onEvent({ name, data: dataLines.join("\n") });
        }
      }
    },
  };
}
