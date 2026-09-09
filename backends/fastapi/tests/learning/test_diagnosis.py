from app.learning.diagnosis import diagnose_answer


def test_correct_answer_for_yinwei_contrast():
    result = diagnose_answer("虽然", "although")

    assert result.is_correct is True
    assert result.misconception is None


def test_detects_confusion_with_yinwei():
    result = diagnose_answer("虽然", "because")

    assert result.is_correct is False
    assert result.misconception == (
        "Confuses 虽然 (although / even though) with 因为 (because)."
    )


def test_unknown_answer_is_incorrect_without_specific_misconception():
    result = diagnose_answer("虽然", "tomorrow")

    assert result.is_correct is False
    assert result.misconception is None


def test_unknown_concept_does_not_crash():
    result = diagnose_answer("unknown", "although")

    assert result.is_correct is False
    assert result.misconception is None
