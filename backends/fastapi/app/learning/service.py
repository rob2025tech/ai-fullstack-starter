from dataclasses import dataclass
from datetime import datetime

from app.learning.diagnosis import diagnose_answer
from app.learning.mastery import update_mastery
from app.learning.quiz import QuizResult
from app.learning.repository import (
    InMemoryLearningRepository,
    LearningState,
)
from app.learning.scheduler import review_interval
from app.learning.teaching import TeachingResponse
from app.services.teaching_service import TeachingService


@dataclass(frozen=True)
class LearningResult:
    state: LearningState
    is_correct: bool
    misconception: str | None
    mastery_before: float
    mastery_after: float
    teaching: TeachingResponse | None


class LearningService:
    def __init__(
        self,
        repository: InMemoryLearningRepository,
        teaching_service: TeachingService | None = None,
    ) -> None:
        self.repository = repository
        self.teaching_service = teaching_service or TeachingService()

    def get_state(self, user_id: str, concept: str) -> LearningState:
        return self.repository.get_or_create(user_id, concept)

    async def answer(
        self,
        user_id: str,
        concept: str,
        answer: str,
        *,
        now: datetime,
    ) -> LearningResult:
        state = self.repository.get_or_create(user_id, concept)
        diagnosis = diagnose_answer(concept, answer)

        mastery_before = state.mastery
        mastery_after = update_mastery(
            mastery_before,
            is_correct=diagnosis.is_correct,
            had_misconception=diagnosis.misconception is not None,
        )

        state.attempts += 1

        if diagnosis.is_correct:
            state.correct_count += 1

        state.mastery = mastery_after
        state.last_misconception = diagnosis.misconception
        state.next_review_at = now + review_interval(mastery_after)

        self.repository.save(state)

        teaching = await self.teaching_service.generate(
            concept,
            diagnosis.misconception,
        )

        return LearningResult(
            state=state,
            is_correct=diagnosis.is_correct,
            misconception=diagnosis.misconception,
            mastery_before=mastery_before,
            mastery_after=mastery_after,
            teaching=teaching,
        )

    def record_quiz_result(
        self,
        user_id: str,
        result: QuizResult,
        *,
        now: datetime,
    ) -> LearningState:
        state = self.repository.get_or_create(
            user_id,
            result.question.concept,
        )

        mastery_before = state.mastery
        mastery_after = update_mastery(
            mastery_before,
            is_correct=result.is_correct,
            had_misconception=False,
        )

        state.attempts += 1

        if result.is_correct:
            state.correct_count += 1

        state.mastery = mastery_after
        state.last_misconception = None
        state.next_review_at = now + review_interval(mastery_after)

        self.repository.save(state)

        return state
