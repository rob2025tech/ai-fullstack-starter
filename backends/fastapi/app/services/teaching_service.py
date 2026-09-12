from app.learning.teaching import TeachingResponse, generate_teaching


class TeachingService:
    """Async boundary for adaptive teaching generation.

    The current implementation uses deterministic teaching content.
    A provider-backed implementation can be introduced without changing
    the learning engine or API contract.
    """

    async def generate(
        self,
        concept: str,
        misconception: str | None,
    ) -> TeachingResponse | None:
        return generate_teaching(concept, misconception)
