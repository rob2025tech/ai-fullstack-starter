from datetime import datetime, timedelta, timezone

import pytest

from app.learning.quiz import PracticeQuestion, PracticeResult, QuizResult
from app.learning.quiz_content import get_quiz_question, get_retest_question
from app.learning.repository import InMemoryLearningRepository
from app.learning.service import LearningService
from app.learning.teaching import TeachingResponse


class StubTeachingService:
    async def generate(
        self,
        concept: str,
        misconception: str | None,
    ) -> TeachingResponse | None:
        if concept != "additive-versioning":
            return None

        return TeachingResponse(
            explanation="Additive API changes are backward-compatible.",
            practice_question=(
                "You need to add next_review_at to the API response. "
                "What is the safest change?"
            ),
            choices=(
                "Add next_review_at as a new optional response field",
                "Remove an existing response field",
            ),
            practice_correct_answer=(
                "Add next_review_at as a new optional response field"
            ),
        )


def make_service() -> tuple[LearningService, InMemoryLearningRepository]:
    repository = InMemoryLearningRepository()
    service = LearningService(
        repository,
        teaching_service=StubTeachingService(),
    )
    return service, repository


def make_quiz_result(
    concept: str,
    answer: str,
) -> QuizResult:
    question = get_quiz_question(concept)
    assert question is not None

    return QuizResult(
        question=question,
        selected_answer=answer,
        is_correct=(
            answer.strip().lower()
            == question.correct_answer.strip().lower()
        ),
    )


def make_retest_result(
    concept: str,
    answer: str,
) -> QuizResult:
    question = get_retest_question(concept)
    assert question is not None

    return QuizResult(
        question=question,
        selected_answer=answer,
        is_correct=(
            answer.strip().lower()
            == question.correct_answer.strip().lower()
        ),
    )


@pytest.mark.asyncio
async def test_wrong_quiz_answer_triggers_teaching_and_targeted_practice():
    service, repository = make_service()
    now = datetime(2026, 9, 12, 10, 0, tzinfo=timezone.utc)

    result = await service.answer_quiz(
        "student-1",
        make_quiz_result(
            "additive-versioning",
            "Removing an existing response field",
        ),
        now=now,
    )

    assert result.is_correct is False
    assert result.correct_answer == (
        "Adding a new optional field to a response"
    )
    assert result.explanation is not None
    assert "backward-compatible" in result.explanation
    assert result.misconception is not None
    assert result.practice_question is not None
    assert result.practice_question.correct_answer == (
        "Add next_review_at as a new optional response field"
    )

    state = repository.get_or_create("student-1", "additive-versioning")

    assert state.attempts == 1
    assert state.correct_count == 0
    assert state.mastery < 0.32
    assert state.last_misconception is not None
    assert state.next_review_at > now


@pytest.mark.asyncio
async def test_correct_targeted_practice_increases_mastery_and_clears_misconception():
    service, repository = make_service()
    now = datetime(2026, 9, 12, 10, 0, tzinfo=timezone.utc)

    await service.answer_quiz(
        "student-1",
        make_quiz_result(
            "additive-versioning",
            "Removing an existing response field",
        ),
        now=now,
    )

    practice_question = PracticeQuestion(
        concept="additive-versioning",
        question="What is the safest change?",
        choices=(
            "Add next_review_at as a new optional response field",
            "Remove an existing response field",
        ),
        correct_answer="Add next_review_at as a new optional response field",
    )

    result = await service.answer_practice(
        "student-1",
        PracticeResult(
            question=practice_question,
            selected_answer=(
                "Add next_review_at as a new optional response field"
            ),
            is_correct=True,
        ),
        now=now + timedelta(minutes=5),
    )

    assert result.is_correct is True
    assert result.correct_answer == (
        "Add next_review_at as a new optional response field"
    )
    assert result.mastery_after > result.mastery_before
    assert result.explanation is None

    state = repository.get_or_create("student-1", "additive-versioning")

    assert state.attempts == 2
    assert state.correct_count == 1
    assert state.last_misconception is None
    assert state.next_review_at > now


@pytest.mark.asyncio
async def test_fresh_retest_updates_mastery_after_teaching_and_practice():
    service, repository = make_service()
    now = datetime(2026, 9, 12, 10, 0, tzinfo=timezone.utc)

    await service.answer_quiz(
        "student-1",
        make_quiz_result(
            "additive-versioning",
            "Removing an existing response field",
        ),
        now=now,
    )

    practice_question = PracticeQuestion(
        concept="additive-versioning",
        question="What is the safest change?",
        choices=(
            "Add next_review_at as a new optional response field",
            "Remove an existing response field",
        ),
        correct_answer="Add next_review_at as a new optional response field",
    )

    await service.answer_practice(
        "student-1",
        PracticeResult(
            question=practice_question,
            selected_answer=(
                "Add next_review_at as a new optional response field"
            ),
            is_correct=True,
        ),
        now=now + timedelta(minutes=5),
    )

    result = await service.answer_retest(
        "student-1",
        make_retest_result(
            "additive-versioning",
            "Add the new field without removing or changing existing fields",
        ),
        now=now + timedelta(minutes=10),
    )

    assert result.is_correct is True
    assert result.correct_answer == (
        "Add the new field without removing or changing existing fields"
    )
    assert result.mastery_after > result.mastery_before

    state = repository.get_or_create("student-1", "additive-versioning")

    assert state.attempts == 3
    assert state.correct_count == 2
    assert state.last_misconception is None
    assert state.next_review_at > now + timedelta(minutes=10)


@pytest.mark.asyncio
async def test_wrong_retest_records_retest_misconception():
    service, repository = make_service()
    now = datetime(2026, 9, 12, 10, 0, tzinfo=timezone.utc)

    result = await service.answer_retest(
        "student-1",
        make_retest_result(
            "additive-versioning",
            "Replace existing fields",
        ),
        now=now,
    )

    assert result.is_correct is False
    assert result.mastery_after < result.mastery_before

    state = repository.get_or_create("student-1", "additive-versioning")

    assert state.attempts == 1
    assert state.correct_count == 0
    assert state.last_misconception == (
        "The learner did not retrieve the concept correctly "
        "on the retest."
    )
    assert state.next_review_at > now


@pytest.mark.asyncio
async def test_answer_legacy_learning_api_still_updates_state():
    service, repository = make_service()
    now = datetime(2026, 9, 12, 10, 0, tzinfo=timezone.utc)

    result = await service.answer(
        "student-1",
        "additive-versioning",
        "Adding a new optional field to a response",
        now=now,
    )

    assert result.is_correct is True
    assert result.misconception is None
    assert result.mastery_after > result.mastery_before

    state = repository.get_or_create("student-1", "additive-versioning")

    assert state.attempts == 1
    assert state.correct_count == 1
    assert state.last_misconception is None
    assert state.next_review_at > now
