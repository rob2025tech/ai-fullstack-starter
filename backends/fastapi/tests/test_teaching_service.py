import pytest

from app.core.errors import ProviderUnavailableError
from app.providers.llm.base import LLMProvider
from app.services.teaching_service import TeachingService


class FakeTeachingProvider(LLMProvider):
    def __init__(self, response: str = "LLM explanation") -> None:
        self.response = response
        self.prompts: list[str] = []

    async def generate(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self.response


class FailingTeachingProvider(LLMProvider):
    async def generate(self, prompt: str) -> str:
        raise ProviderUnavailableError("provider unavailable")


@pytest.mark.anyio
async def test_teaching_service_uses_provider_for_explanation():
    provider = FakeTeachingProvider("Although introduces a contrast.")
    service = TeachingService(provider)

    result = await service.generate("虽然", None)

    assert result is not None
    assert result.explanation == "Although introduces a contrast."
    assert result.practice_question == "Which meaning best matches 虽然?"
    assert result.choices == ("although / even though", "because")
    assert len(provider.prompts) == 1
    assert "Target concept: 虽然" in provider.prompts[0]


@pytest.mark.anyio
async def test_teaching_service_includes_misconception_in_prompt():
    provider = FakeTeachingProvider("虽然 means although, not because.")
    service = TeachingService(provider)

    result = await service.generate(
        "虽然",
        "Confuses 虽然 (although / even though) with 因为 (because).",
    )

    assert result is not None
    assert result.explanation == "虽然 means although, not because."
    assert "Known misconception:" in provider.prompts[0]
    assert "因为" in provider.prompts[0]


@pytest.mark.anyio
async def test_teaching_service_falls_back_when_provider_unavailable():
    service = TeachingService(FailingTeachingProvider())

    result = await service.generate(
        "虽然",
        "Confuses 虽然 (although / even though) with 因为 (because).",
    )

    assert result is not None
    assert "因为 means because" in result.explanation
    assert result.practice_question == "Which meaning best matches 虽然?"
    assert result.choices == ("although / even though", "because")


@pytest.mark.anyio
async def test_teaching_service_without_provider_is_deterministic():
    service = TeachingService()

    result = await service.generate("虽然", None)

    assert result is not None
    assert "although / even though" in result.explanation
    assert "因为" not in result.explanation


@pytest.mark.anyio
async def test_teaching_service_returns_none_for_unknown_concept():
    service = TeachingService(FakeTeachingProvider())

    result = await service.generate("未知", None)

    assert result is None
