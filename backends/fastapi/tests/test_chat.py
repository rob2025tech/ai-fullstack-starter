import json

from tests.sse_util import parse_sse


def test_chat_json_mode_returns_echo(client):
    response = client.post("/api/v1/chat", json={"prompt": "ping", "user_id": "unit"})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    body = response.json()
    message = body["message"]
    assert message["role"] == "assistant"
    assert message["content"] == "echo: ping"
    assert message["finish_reason"] == "stop"
    assert message["id"].startswith("msg_")
    assert body["usage"] is None


def test_chat_stream_mode_emits_deltas_then_terminal_message(client):
    response = client.post("/api/v1/chat", json={"prompt": "ping", "stream": True})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    events = parse_sse(response.text)
    deltas = [json.loads(data) for name, data in events if name == "delta"]
    assert [delta["content"] for delta in deltas] == ["echo", ": ", "ping"]
    terminal_name, terminal_data = events[-1]
    assert terminal_name == "message"
    message = json.loads(terminal_data)["message"]
    assert message["role"] == "assistant"
    assert message["content"] == "echo: ping"
    assert message["finish_reason"] == "stop"


def test_chat_defaults_to_json_mode(client):
    response = client.post("/api/v1/chat", json={"prompt": "ping"})
    assert response.headers["content-type"].startswith("application/json")
