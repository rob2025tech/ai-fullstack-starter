from datetime import datetime, timezone

from app.learning.repository import (
    InMemoryLearningRepository,
    LearningState,
)


def test_new_learning_state_starts_with_demo_mastery():
    repository = InMemoryLearningRepository()

    state = repository.get_or_create("student-1", "虽然")

    assert state.user_id == "student-1"
    assert state.concept == "虽然"
    assert state.mastery == 0.32
    assert state.attempts == 0
    assert state.correct_count == 0
    assert state.last_misconception is None
    assert state.next_review_at is None


def test_saved_state_persists_for_same_student_and_concept():
    repository = InMemoryLearningRepository()

    state = repository.get_or_create("student-1", "虽然")
    state.mastery = 0.62
    state.attempts = 1
    state.correct_count = 1
    state.last_misconception = "Confuses 虽然 with 因为."
    state.next_review_at = datetime(2026, 9, 15, tzinfo=timezone.utc)

    repository.save(state)

    restored = repository.get_or_create("student-1", "虽然")

    assert restored.mastery == 0.62
    assert restored.attempts == 1
    assert restored.correct_count == 1
    assert restored.last_misconception == "Confuses 虽然 with 因为."
    assert restored.next_review_at == datetime(
        2026, 9, 15, tzinfo=timezone.utc
    )


def test_students_have_isolated_learning_state():
    repository = InMemoryLearningRepository()

    first = repository.get_or_create("student-1", "虽然")
    second = repository.get_or_create("student-2", "虽然")

    first.mastery = 0.62

    assert second.mastery == 0.32


def test_concepts_have_isolated_learning_state():
    repository = InMemoryLearningRepository()

    although = repository.get_or_create("student-1", "虽然")
    because = repository.get_or_create("student-1", "因为")

    although.mastery = 0.62

    assert because.mastery == 0.32


def test_save_can_replace_state_for_same_key():
    repository = InMemoryLearningRepository()

    repository.get_or_create("student-1", "虽然")

    replacement = LearningState(
        user_id="student-1",
        concept="虽然",
        mastery=0.80,
        attempts=3,
        correct_count=2,
    )

    repository.save(replacement)

    restored = repository.get_or_create("student-1", "虽然")

    assert restored == replacement
