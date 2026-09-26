import json

import pytest
from fastapi.testclient import TestClient

from app.config.settings import Settings
from app.core.errors import ProviderUnavailableError
from app.main import create_app
from app.providers.llm.base import LLMProvider
from tests.sse_util import parse_sse


# ---------------------------------------------------------------------------
# Fake providers for integration tests
# ---------------------------------------------------------------------------


class _AlwaysUnavailableProvider(LLMProvider):
    """Always raises ProviderUnavailableError — used to test 503 mapping."""

    async def generate(self, prompt: str) -> str:
        raise ProviderUnavailableError("simulated backend unavailability")


@pytest.fixture()
def unavailable_client() -> TestClient:
    """TestClient wired with a provider that always raises ProviderUnavailableError."""
    app = create_app(
        Settings(_env_file=None, provider_max_retries=0),
        llm_provider_override=_AlwaysUnavailableProvider(),
    )
    return TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# Existing chat tests (unchanged)
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# AC-4: Policy-wrapped provider failure → HTTP 503 error envelope
# ---------------------------------------------------------------------------


def test_chat_returns_503_when_provider_unavailable(unavailable_client: TestClient) -> None:
    """POST /api/v1/chat returns 503 with provider_unavailable when policy-wrapped provider fails."""
    response = unavailable_client.post(
        "/api/v1/chat",
        json={"prompt": "ping"},
    )
    assert response.status_code == 503
    body = response.json()
    assert "error" in body
    assert body["error"]["code"] == "provider_unavailable"
    assert isinstance(body["error"]["message"], str)
    assert len(body["error"]["message"]) > 0


def test_chat_error_envelope_structure_on_503(unavailable_client: TestClient) -> None:
    """503 response adheres to the contract ErrorResponse envelope shape."""
    response = unavailable_client.post(
        "/api/v1/chat",
        json={"prompt": "hello"},
    )
    assert response.status_code == 503
    body = response.json()
    # Top-level must be {"error": {"code": ..., "message": ...}}
    assert set(body.keys()) == {"error"}
    error = body["error"]
    assert "code" in error
    assert "message" in error
    assert error["code"] == "provider_unavailable"
