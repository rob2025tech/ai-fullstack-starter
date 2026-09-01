def parse_sse(text: str) -> list[tuple[str, str]]:
    events: list[tuple[str, str]] = []
    for block in text.split("\n\n"):
        if not block.strip():
            continue
        name = "message"
        data_lines: list[str] = []
        for line in block.split("\n"):
            if line.startswith("event:"):
                name = line[6:].strip()
            elif line.startswith("data:"):
                data_lines.append(line[5:].strip())
        if data_lines:
            events.append((name, "\n".join(data_lines)))
    return events
