import json

from app.core.errors import ProviderError
from app.providers.llm.base import LLMProvider
from tests.sse_util import parse_sse


class FailingProvider(LLMProvider):
    async def generate(self, prompt: str) -> str:
        raise ProviderError("boom")

    async def stream(self, prompt: str):
        raise ProviderError("boom")
        yield  # unreachable; marks this as an async generator


def test_empty_prompt_is_rejected_with_envelope(client):
    response = client.post("/api/v1/chat", json={"prompt": ""})
    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "invalid_request"
    assert body["error"]["message"]


def test_missing_body_is_rejected_with_envelope(client):
    response = client.post("/api/v1/chat")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_request"


def test_provider_error_maps_to_envelope(client):
    client.app.state.chat_service.provider = FailingProvider()
    response = client.post("/api/v1/chat", json={"prompt": "ping"})
    assert response.status_code == 502
    assert response.json() == {
        "error": {"code": "provider_error", "message": "boom", "details": None}
    }


def test_provider_error_becomes_terminal_sse_event(client):
    client.app.state.chat_service.provider = FailingProvider()
    response = client.post("/api/v1/chat", json={"prompt": "ping", "stream": True})
    assert response.status_code == 200
    events = parse_sse(response.text)
    terminal_name, terminal_data = events[-1]
    assert terminal_name == "error"
    payload = json.loads(terminal_data)
    assert payload["error"]["code"] == "provider_error"
    assert payload["error"]["message"] == "boom"
