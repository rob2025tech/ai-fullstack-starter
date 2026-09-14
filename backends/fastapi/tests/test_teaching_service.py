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
    provider = FakeTeachingProvider(
        "Adding an optional field preserves compatibility."
    )
    service = TeachingService(provider)

    result = await service.generate("additive-versioning", None)

    assert result is not None
    assert result.explanation == (
        "Adding an optional field preserves compatibility."
    )
    assert result.practice_question == (
        "Your v1 API already returns user_id and mastery. You need to add "
        "next_review_at for newer clients. What is the safest change?"
    )
    assert result.choices == (
        "Add next_review_at as a new optional response field",
        "Remove mastery and replace it with next_review_at",
        "Rename /api/v1/learning/state to /api/v2/learning/state immediately",
        "Change the meaning of mastery so it contains the review date",
    )
    assert len(provider.prompts) == 1
    assert "Target concept: additive-versioning" in provider.prompts[0]


@pytest.mark.anyio
async def test_teaching_service_includes_misconception_in_prompt():
    provider = FakeTeachingProvider(
        "Adding a field is safer than removing one."
    )
    service = TeachingService(provider)

    misconception = (
        'Confuses the correct approach '
        '("Adding a new optional field to a response") with '
        'the distractor "Removing an existing response field".'
    )

    result = await service.generate(
        "additive-versioning",
        misconception,
    )

    assert result is not None
    assert result.explanation == (
        "Adding a field is safer than removing one."
    )
    assert "Known misconception:" in provider.prompts[0]
    assert "Removing an existing response field" in provider.prompts[0]


@pytest.mark.anyio
async def test_teaching_service_falls_back_when_provider_unavailable():
    service = TeachingService(FailingTeachingProvider())

    result = await service.generate(
        "additive-versioning",
        "Confuses additive changes with breaking changes.",
    )

    assert result is not None
    assert "additive api versioning" in result.explanation.lower()
    assert result.practice_question == (
        "Your v1 API already returns user_id and mastery. You need to add "
        "next_review_at for newer clients. What is the safest change?"
    )
    assert result.choices == (
        "Add next_review_at as a new optional response field",
        "Remove mastery and replace it with next_review_at",
        "Rename /api/v1/learning/state to /api/v2/learning/state immediately",
        "Change the meaning of mastery so it contains the review date",
    )


@pytest.mark.anyio
async def test_teaching_service_without_provider_is_deterministic():
    service = TeachingService()

    result = await service.generate("additive-versioning", None)

    assert result is not None
    assert "additive api versioning" in result.explanation.lower()
    assert "next_review_at" in result.practice_question


@pytest.mark.anyio
async def test_teaching_service_returns_none_for_unknown_concept():
    service = TeachingService(FakeTeachingProvider())

    result = await service.generate("未知", None)

    assert result is None
