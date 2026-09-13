from dataclasses import dataclass
from datetime import datetime

from app.learning.diagnosis import diagnose_answer
from app.learning.mastery import update_mastery
from app.learning.quiz import (
    PracticeQuestion,
    PracticeResult,
    QuizResult,
)
from app.learning.quiz_content import get_retest_question
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


@dataclass(frozen=True)
class AdaptiveQuizResult:
    state: LearningState
    is_correct: bool
    selected_answer: str
    correct_answer: str
    mastery_before: float
    mastery_after: float
    explanation: str | None
    misconception: str | None
    practice_question: PracticeQuestion | None


@dataclass(frozen=True)
class AdaptivePracticeResult:
    state: LearningState
    is_correct: bool
    selected_answer: str
    correct_answer: str
    mastery_before: float
    mastery_after: float
    explanation: str | None


@dataclass(frozen=True)
class AdaptiveRetestResult:
    state: LearningState
    is_correct: bool
    selected_answer: str
    correct_answer: str
    mastery_before: float
    mastery_after: float


class LearningService:
    def __init__(
        self,
        repository: InMemoryLearningRepository,
        teaching_service: TeachingService | None = None,
    ) -> None:
        self.repository = repository
        self.teaching_service = teaching_service or TeachingService()

    def get_state(
        self,
        user_id: str,
        concept: str,
    ) -> LearningState:
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

    async def answer_quiz(
        self,
        user_id: str,
        result: QuizResult,
        *,
        now: datetime,
    ) -> AdaptiveQuizResult:
        """Process a retention quiz attempt and prepare adaptive teaching."""

        state = self.repository.get_or_create(
            user_id,
            result.question.concept,
        )

        mastery_before = state.mastery

        mastery_after = update_mastery(
            mastery_before,
            is_correct=result.is_correct,
            had_misconception=not result.is_correct,
        )

        state.attempts += 1

        if result.is_correct:
            state.correct_count += 1

        state.mastery = mastery_after
        state.last_misconception = (
            None
            if result.is_correct
            else "The learner did not retrieve the concept correctly."
        )
        state.next_review_at = now + review_interval(mastery_after)

        self.repository.save(state)

        teaching = await self.teaching_service.generate(
            result.question.concept,
            state.last_misconception,
        )

        practice_question: PracticeQuestion | None = None

        if teaching is not None and not result.is_correct:
            practice_question = PracticeQuestion(
                concept=result.question.concept,
                question=teaching.practice_question,
                choices=teaching.choices,
                correct_answer=teaching.practice_correct_answer,
            )

        return AdaptiveQuizResult(
            state=state,
            is_correct=result.is_correct,
            selected_answer=result.selected_answer,
            correct_answer=result.question.correct_answer,
            mastery_before=mastery_before,
            mastery_after=mastery_after,
            explanation=(
                teaching.explanation
                if teaching is not None and not result.is_correct
                else None
            ),
            misconception=state.last_misconception,
            practice_question=practice_question,
        )

    async def answer_practice(
        self,
        user_id: str,
        result: PracticeResult,
        *,
        now: datetime,
    ) -> AdaptivePracticeResult:
        """Process targeted practice and update learning state."""

        state = self.repository.get_or_create(
            user_id,
            result.question.concept,
        )

        mastery_before = state.mastery

        mastery_after = update_mastery(
            mastery_before,
            is_correct=result.is_correct,
            had_misconception=not result.is_correct,
        )

        state.attempts += 1

        if result.is_correct:
            state.correct_count += 1
            state.last_misconception = None
        else:
            state.last_misconception = (
                "The learner did not answer the targeted practice "
                "question correctly."
            )

        state.mastery = mastery_after
        state.next_review_at = now + review_interval(mastery_after)

        self.repository.save(state)

        teaching = await self.teaching_service.generate(
            result.question.concept,
            state.last_misconception,
        )

        return AdaptivePracticeResult(
            state=state,
            is_correct=result.is_correct,
            selected_answer=result.selected_answer,
            correct_answer=result.question.correct_answer,
            mastery_before=mastery_before,
            mastery_after=mastery_after,
            explanation=(
                teaching.explanation
                if teaching is not None and not result.is_correct
                else None
            ),
        )

    def get_retest_question(
        self,
        concept: str,
    ):
        """Return a fresh deterministic question for retention verification."""
        return get_retest_question(concept)

    async def answer_retest(
        self,
        user_id: str,
        result: QuizResult,
        *,
        now: datetime,
    ) -> AdaptiveRetestResult:
        """Process a retest after teaching and targeted practice."""

        state = self.repository.get_or_create(
            user_id,
            result.question.concept,
        )

        mastery_before = state.mastery

        mastery_after = update_mastery(
            mastery_before,
            is_correct=result.is_correct,
            had_misconception=not result.is_correct,
        )

        state.attempts += 1

        if result.is_correct:
            state.correct_count += 1
            state.last_misconception = None
        else:
            state.last_misconception = (
                "The learner did not retrieve the concept correctly "
                "on the retest."
            )

        state.mastery = mastery_after
        state.next_review_at = now + review_interval(mastery_after)

        self.repository.save(state)

        return AdaptiveRetestResult(
            state=state,
            is_correct=result.is_correct,
            selected_answer=result.selected_answer,
            correct_answer=result.question.correct_answer,
            mastery_before=mastery_before,
            mastery_after=mastery_after,
        )

    def record_quiz_result(
        self,
        user_id: str,
        result: QuizResult,
        *,
        now: datetime,
    ) -> LearningState:
        """Preserve the existing quiz-result state update API."""

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
