from app.core.errors import ProviderError, ProviderUnavailableError
from app.learning.teaching import TeachingResponse, generate_teaching
from app.providers.llm.base import LLMProvider


class TeachingService:
    """Generate adaptive teaching with deterministic fallback."""

    def __init__(self, provider: LLMProvider | None = None) -> None:
        self.provider = provider

    async def generate(
        self,
        concept: str,
        misconception: str | None,
    ) -> TeachingResponse | None:
        fallback = generate_teaching(concept, misconception)
        if fallback is None:
            return None

        if self.provider is None:
            return fallback

        prompt = self._build_prompt(concept, misconception)

        try:
            explanation = await self.provider.generate(prompt)
        except (ProviderError, ProviderUnavailableError):
            return fallback

        return TeachingResponse(
            explanation=explanation,
            practice_question=fallback.practice_question,
            choices=fallback.choices,
            practice_correct_answer=fallback.practice_correct_answer,
        )

    @staticmethod
    def _build_prompt(
        concept: str,
        misconception: str | None,
    ) -> str:
        misconception_text = misconception or "No known misconception."

        return (
            "You are an adaptive language tutor. "
            "Explain the target concept clearly and briefly for a student. "
            "Address the student's misconception when one is provided. "
            "Do not invent facts. "
            "Return only the teaching explanation, with no labels or JSON.\n\n"
            f"Target concept: {concept}\n"
            f"Known misconception: {misconception_text}"
        )
