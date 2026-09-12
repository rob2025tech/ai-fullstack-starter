from datetime import datetime, timezone

import pytest

from app.learning.quiz import QuizQuestion, QuizResult
from app.learning.repository import InMemoryLearningRepository
from app.learning.service import LearningService


def make_quiz_result(
    *,
    is_correct: bool,
    concept: str = "staged git diff",
) -> QuizResult:
    question = QuizQuestion(
        concept=concept,
        question="Which command shows changes staged for the next commit?",
        choices=("git diff", "git diff --cached", "git status", "git log"),
        correct_answer="git diff --cached",
        bloom_level="remember",
    )

    return QuizResult(
        question=question,
        selected_answer=(
            "git diff --cached" if is_correct else "git status"
        ),
        is_correct=is_correct,
    )


def test_quiz_result_updates_mastery_and_review_schedule():
    repository = InMemoryLearningRepository()
    service = LearningService(repository)
    now = datetime(2026, 9, 12, 10, 0, tzinfo=timezone.utc)

    result = make_quiz_result(is_correct=True)

    state = service.record_quiz_result(
        "student-1",
        result,
        now=now,
    )

    assert state.attempts == 1
    assert state.correct_count == 1
    assert state.mastery == 0.52
    assert state.next_review_at == datetime(
        2026,
        9,
        15,
        10,
        0,
        tzinfo=timezone.utc,
    )


def test_incorrect_quiz_result_updates_mastery_without_llm_teaching():
    repository = InMemoryLearningRepository()
    service = LearningService(repository)
    now = datetime(2026, 9, 12, 10, 0, tzinfo=timezone.utc)

    result = make_quiz_result(is_correct=False)

    state = service.record_quiz_result(
        "student-1",
        result,
        now=now,
    )

    assert state.attempts == 1
    assert state.correct_count == 0
    assert state.mastery == 0.27
    assert state.last_misconception is None
    assert state.next_review_at == datetime(
        2026,
        9,
        13,
        10,
        0,
        tzinfo=timezone.utc,
    )


def test_multiple_quiz_results_accumulate_learning_state():
    repository = InMemoryLearningRepository()
    service = LearningService(repository)
    now = datetime(2026, 9, 12, 10, 0, tzinfo=timezone.utc)

    incorrect = make_quiz_result(is_correct=False)
    correct = make_quiz_result(is_correct=True)

    service.record_quiz_result(
        "student-1",
        incorrect,
        now=now,
    )

    state = service.record_quiz_result(
        "student-1",
        correct,
        now=now,
    )

    assert state.attempts == 2
    assert state.correct_count == 1
    assert state.mastery == pytest.approx(0.47)
