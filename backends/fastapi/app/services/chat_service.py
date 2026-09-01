from collections.abc import AsyncIterator
from uuid import uuid4

from app.models.request_models import ChatRequest
from app.models.response_models import ChatMessage, ChatResponse
from app.providers.llm.base import LLMProvider


class ChatService:
    def __init__(self, provider: LLMProvider) -> None:
        self.provider = provider

    async def complete(self, request: ChatRequest) -> ChatResponse:
        content = await self.provider.generate(request.prompt)
        return self._build_response(content)

    async def stream_events(self, request: ChatRequest) -> AsyncIterator[tuple[str, dict]]:
        parts: list[str] = []
        async for chunk in self.provider.stream(request.prompt):
            parts.append(chunk)
            yield "delta", {"content": chunk}
        yield "message", self._build_response("".join(parts)).model_dump(mode="json")

    @staticmethod
    def _build_response(content: str) -> ChatResponse:
        return ChatResponse(
            message=ChatMessage(
                id=f"msg_{uuid4().hex}",
                role="assistant",
                content=content,
                finish_reason="stop",
            )
        )
