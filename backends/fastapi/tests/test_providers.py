import json

import httpx
import pytest

from app.config.settings import Settings
from app.core.errors import ProviderError, ProviderUnavailableError
from app.providers.llm.mock import MockLLMProvider
from app.providers.llm.openai import OpenAILLMProvider
from app.providers.llm.registry import build_llm_provider


async def test_mock_generate_is_deterministic():
    provider = MockLLMProvider()
    assert await provider.generate("ping") == "echo: ping"


async def test_mock_stream_yields_fixed_chunks():
    provider = MockLLMProvider()
    chunks = [chunk async for chunk in provider.stream("ping")]
    assert chunks == ["echo", ": ", "ping"]


def _make_provider(handler) -> OpenAILLMProvider:
    return OpenAILLMProvider(
        api_key="key", base_url="http://test", model="model", transport=httpx.MockTransport(handler)
    )


def _completions_handler(request: httpx.Request) -> httpx.Response:
    body = json.loads(request.content)
    if body.get("stream"):
        lines = [
            'data: {"choices":[{"delta":{"content":"he"}}]}',
            'data: {"choices":[{"delta":{"content":"llo"}}]}',
            "data: [DONE]",
        ]
        return httpx.Response(200, text="\n".join(lines))
    return httpx.Response(200, json={"choices": [{"message": {"content": "hello"}}]})


async def test_openai_generate_parses_content():
    provider = _make_provider(_completions_handler)
    assert await provider.generate("hi") == "hello"


async def test_openai_stream_yields_chunks_until_done():
    provider = _make_provider(_completions_handler)
    chunks = [chunk async for chunk in provider.stream("hi")]
    assert chunks == ["he", "llo"]


async def test_openai_http_error_maps_to_provider_error():
    provider = _make_provider(lambda request: httpx.Response(500, text="oops"))
    with pytest.raises(ProviderError):
        await provider.generate("hi")


async def test_openai_malformed_output_maps_to_provider_error():
    provider = _make_provider(lambda request: httpx.Response(200, json={"choices": []}))
    with pytest.raises(ProviderError):
        await provider.generate("hi")


async def test_openai_connection_error_maps_to_unavailable():
    def raiser(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    provider = _make_provider(raiser)
    with pytest.raises(ProviderUnavailableError):
        await provider.generate("hi")


def test_registry_defaults_to_mock():
    assert isinstance(build_llm_provider(Settings()), MockLLMProvider)


def test_registry_openai_requires_api_key():
    with pytest.raises(ProviderUnavailableError):
        build_llm_provider(Settings(llm_provider="openai"))


def test_registry_rejects_unknown_provider():
    with pytest.raises(ProviderUnavailableError):
        build_llm_provider(Settings(llm_provider="nope"))
