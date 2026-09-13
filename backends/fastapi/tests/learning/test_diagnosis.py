from app.learning.diagnosis import diagnose_answer


def test_correct_answer_for_additive_versioning():
    result = diagnose_answer(
        "additive-versioning",
        "Adding a new optional field to a response",
    )

    assert result.is_correct is True
    assert result.misconception is None


def test_detects_breaking_change_misconception():
    result = diagnose_answer(
        "additive-versioning",
        "Removing an existing response field",
    )

    assert result.is_correct is False
    assert result.misconception is not None
    assert "Adding a new optional field to a response" in result.misconception
    assert "Removing an existing response field" in result.misconception


def test_unknown_answer_is_incorrect_without_specific_misconception():
    result = diagnose_answer(
        "additive-versioning",
        "some unknown answer",
    )

    assert result.is_correct is False
    assert result.misconception is None


def test_unknown_concept_does_not_crash():
    result = diagnose_answer("unknown-concept", "anything")

    assert result.is_correct is False
    assert result.misconception is None
