import json
from collections.abc import AsyncIterator

import httpx

from app.core.errors import ProviderError, ProviderUnavailableError
from app.providers.llm.base import LLMProvider

_TIMEOUT = httpx.Timeout(60.0, connect=10.0)


class OpenAILLMProvider(LLMProvider):
    """Any OpenAI-compatible chat completions endpoint."""

    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._model = model
        self._client = httpx.AsyncClient(
            base_url=base_url,
            timeout=_TIMEOUT,
            transport=transport,
            headers={"Authorization": f"Bearer {api_key}"},
        )

    def _payload(self, prompt: str, stream: bool) -> dict:
        return {
            "model": self._model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": stream,
        }

    async def generate(self, prompt: str) -> str:
        try:
            response = await self._client.post(
                "/chat/completions", json=self._payload(prompt, stream=False)
            )
        except httpx.HTTPError as exc:
            raise ProviderUnavailableError(f"openai provider unreachable: {exc}") from exc
        if response.status_code != 200:
            raise ProviderError(f"openai provider returned HTTP {response.status_code}")
        try:
            content = response.json()["choices"][0]["message"]["content"]
        except (KeyError, IndexError, ValueError) as exc:
            raise ProviderError("openai provider returned malformed output") from exc
        if not content:
            raise ProviderError("openai provider returned empty output")
        return content

    async def stream(self, prompt: str) -> AsyncIterator[str]:
        try:
            async with self._client.stream(
                "POST", "/chat/completions", json=self._payload(prompt, stream=True)
            ) as response:
                if response.status_code != 200:
                    await response.aread()
                    raise ProviderError(
                        f"openai provider returned HTTP {response.status_code}"
                    )
                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        return
                    try:
                        chunk = json.loads(data)["choices"][0]["delta"].get("content")
                    except (KeyError, IndexError, ValueError) as exc:
                        raise ProviderError(
                            "openai provider returned malformed stream chunk"
                        ) from exc
                    if chunk:
                        yield chunk
        except httpx.HTTPError as exc:
            raise ProviderUnavailableError(f"openai provider unreachable: {exc}") from exc

    async def close(self) -> None:
        await self._client.aclose()
