from abc import ABC, abstractmethod
from collections.abc import AsyncIterator


class LLMProvider(ABC):
    @abstractmethod
    async def generate(self, prompt: str) -> str: ...

    async def stream(self, prompt: str) -> AsyncIterator[str]:
        yield await self.generate(prompt)
