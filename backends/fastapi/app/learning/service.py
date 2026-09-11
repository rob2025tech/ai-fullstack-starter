from dataclasses import dataclass
from datetime import datetime

from app.learning.diagnosis import diagnose_answer
from app.learning.mastery import update_mastery
from app.learning.repository import (
    InMemoryLearningRepository,
    LearningState,
)
from app.learning.scheduler import review_interval
from app.learning.teaching import TeachingResponse, generate_teaching


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
    ) -> None:
        self.repository = repository

    def get_state(
        self,
        user_id: str,
        concept: str,
    ) -> LearningState:
        return self.repository.get_or_create(user_id, concept)

    def answer(
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

        teaching = generate_teaching(
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
