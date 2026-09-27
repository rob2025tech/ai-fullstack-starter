from app.core.errors import BackendError
from app.learning.teaching import TeachingResponse, generate_teaching
from app.providers.llm.policy import ProviderPolicy


class TeachingService:
    """Generate adaptive teaching with deterministic fallback.

    When a ``ProviderPolicy`` is supplied, the service attempts an LLM-enhanced
    explanation.  Any ``BackendError`` (timeout, unavailability, payload limit,
    or provider failure) causes the service to return the deterministic fallback
    instead of propagating the error, because teaching enhancements are optional.
    """

    def __init__(self, policy: ProviderPolicy | None = None) -> None:
        self._policy = policy

    async def generate(
        self,
        concept: str,
        misconception: str | None,
    ) -> TeachingResponse | None:
        fallback = generate_teaching(concept, misconception)
        if fallback is None:
            return None

        if self._policy is None:
            return fallback

        prompt = self._build_prompt(concept, misconception)

        try:
            explanation = await self._policy.generate(prompt)
        except BackendError:
            # All provider-policy failures are non-fatal for teaching enrichment;
            # return the deterministic template instead.
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
