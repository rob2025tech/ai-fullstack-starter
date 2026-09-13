from app.learning.teaching import generate_teaching


def test_teaching_for_additive_versioning_explains_concept():
    result = generate_teaching("additive-versioning", None)

    assert result is not None
    assert "backward-compatible" in result.explanation
    assert "breaking change" in result.explanation
    assert "next_review_at" in result.practice_question
    assert result.practice_correct_answer == (
        "Add next_review_at as a new optional response field"
    )
    assert result.choices[0] == result.practice_correct_answer


def test_teaching_addresses_known_misconception():
    misconception = (
        'Confuses the correct approach '
        '("Adding a new optional field to a response") with '
        'the distractor "Removing an existing response field".'
    )

    result = generate_teaching("additive-versioning", misconception)

    assert result is not None
    assert "backward-compatible" in result.explanation
    assert misconception in result.explanation
    assert result.practice_correct_answer == (
        "Add next_review_at as a new optional response field"
    )


def test_teaching_returns_none_for_unknown_concept():
    assert generate_teaching("unknown-concept", None) is None
