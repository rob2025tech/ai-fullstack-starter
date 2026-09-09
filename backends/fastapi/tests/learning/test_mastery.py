from app.learning.mastery import update_mastery


def test_correct_answer_without_misconception_increases_mastery():
    assert update_mastery(
        0.50,
        is_correct=True,
        had_misconception=False,
    ) == 0.70


def test_correct_answer_after_misconception_increases_mastery_more():
    assert update_mastery(
        0.32,
        is_correct=True,
        had_misconception=True,
    ) == 0.62


def test_incorrect_answer_decreases_mastery():
    assert update_mastery(
        0.50,
        is_correct=False,
        had_misconception=False,
    ) == 0.45


def test_mastery_never_exceeds_one():
    assert update_mastery(
        0.90,
        is_correct=True,
        had_misconception=False,
    ) == 1.0


def test_mastery_never_goes_below_zero():
    assert update_mastery(
        0.02,
        is_correct=False,
        had_misconception=False,
    ) == 0.0
