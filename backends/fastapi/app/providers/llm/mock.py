from collections.abc import AsyncIterator

from app.providers.llm.base import LLMProvider


class MockLLMProvider(LLMProvider):
    """Deterministic provider so the backend runs and tests without secrets."""

    async def generate(self, prompt: str) -> str:
        return f"echo: {prompt}"

    async def stream(self, prompt: str) -> AsyncIterator[str]:
        for chunk in ("echo", ": ", prompt):
            yield chunk
