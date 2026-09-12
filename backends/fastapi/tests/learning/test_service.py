from datetime import datetime, timedelta, timezone

import pytest

from app.learning.repository import InMemoryLearningRepository
from app.learning.service import LearningService


@pytest.mark.anyio
async def test_answer_updates_misconception_and_mastery():
    repository = InMemoryLearningRepository()
    service = LearningService(repository)
    now = datetime(2026, 9, 12, 10, 0, tzinfo=timezone.utc)

    result = await service.answer(
        "student-1",
        "虽然",
        "because",
        now=now,
    )

    assert result.is_correct is False
    assert result.misconception is not None
    assert "因为" in result.misconception
    assert result.mastery_before == 0.32
    assert result.mastery_after == 0.27
    assert result.state.attempts == 1
    assert result.state.correct_count == 0
    assert result.state.last_misconception == result.misconception
    assert result.state.next_review_at == now + timedelta(days=1)

    assert result.teaching is not None
    assert "因为 means because" in result.teaching.explanation
    assert result.teaching.practice_question == (
        "Which meaning best matches 虽然?"
    )
    assert result.teaching.choices == (
        "although / even though",
        "because",
    )


@pytest.mark.anyio
async def test_correct_answer_after_misconception_improves_mastery():
    repository = InMemoryLearningRepository()
    service = LearningService(repository)
    now = datetime(2026, 9, 12, 10, 0, tzinfo=timezone.utc)

    await service.answer(
        "student-1",
        "虽然",
        "because",
        now=now,
    )

    result = await service.answer(
        "student-1",
        "虽然",
        "although",
        now=now + timedelta(days=1),
    )

    assert result.is_correct is True
    assert result.misconception is None
    assert result.mastery_before == 0.27
    assert result.mastery_after == pytest.approx(0.47)
    assert result.state.attempts == 2
    assert result.state.correct_count == 1
    assert result.state.last_misconception is None
    assert result.state.next_review_at == now + timedelta(days=4)

    assert result.teaching is not None
    assert "although / even though" in result.teaching.explanation
    assert "因为" not in result.teaching.explanation
    assert result.teaching.choices == (
        "although / even though",
        "because",
    )


@pytest.mark.anyio
async def test_learning_state_is_reused_between_answers():
    repository = InMemoryLearningRepository()
    service = LearningService(repository)
    now = datetime(2026, 9, 12, 10, 0, tzinfo=timezone.utc)

    first = await service.answer(
        "student-1",
        "虽然",
        "although",
        now=now,
    )

    second = service.get_state("student-1", "虽然")

    assert second is first.state
    assert second.mastery == 0.52
    assert second.attempts == 1
    assert second.correct_count == 1


@pytest.mark.anyio
async def test_different_students_have_independent_learning_progress():
    repository = InMemoryLearningRepository()
    service = LearningService(repository)
    now = datetime(2026, 9, 12, 10, 0, tzinfo=timezone.utc)

    first = await service.answer(
        "student-1",
        "虽然",
        "although",
        now=now,
    )

    second = service.get_state("student-2", "虽然")

    assert first.mastery_after == 0.52
    assert second.mastery == 0.32
    assert second.attempts == 0
    assert second.correct_count == 0
