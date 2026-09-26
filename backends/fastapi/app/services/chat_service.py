from collections.abc import AsyncIterator
from uuid import uuid4

from app.models.request_models import ChatRequest
from app.models.response_models import ChatMessage, ChatResponse
from app.providers.llm.policy import ProviderPolicy


class ChatService:
    def __init__(self, policy: ProviderPolicy) -> None:
        self._policy = policy

    async def complete(self, request: ChatRequest) -> ChatResponse:
        """Generate a chat completion via the provider policy boundary."""
        content = await self._policy.generate(request.prompt)
        return self._build_response(content)

    async def stream_events(self, request: ChatRequest) -> AsyncIterator[tuple[str, dict]]:
        """Stream chat events using the raw provider (streaming policy is out of scope)."""
        parts: list[str] = []
        async for chunk in self._policy.provider.stream(request.prompt):
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
